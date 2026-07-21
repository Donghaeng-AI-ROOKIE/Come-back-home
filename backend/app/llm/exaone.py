"""LG EXAONE — Phase 2 동선 예측의 두뇌.

역할 (아키텍처 결정사항):
- Top-down: 페르소나 맥락을 읽어 prior(전략확률·끌림점 가중치·반경 파라미터)만 출력.
  좌표를 직접 예측하지 않는다 (LLM calibration 한계).
- 마음 예측: 혼란도·목적지 변경 등 심리 상태 추론. 마음이 바뀔 때만 호출.

서빙: OpenAI 호환 chat completions (Mi:dm 과 같은 규약). settings 에
exaone_base_url(endpoint URL) / exaone_model(endpoint ID) / exaone_api_key 를
채우면 chat() 실호출 가능, 비어 있으면 스텁 모드.
generate_prior 는 실프롬프트 연동됨 — 출력은 phase2.guardrail 검증을 거쳐서만
파이프라인에 들어간다. predict_mind 실연동은 게이지·트리거 작업에서.
"""

from __future__ import annotations

import json
import urllib.request

from app.config import settings
from app.llm.base import LLMClient
from app.phase2 import guardrail
from app.schemas.persona import Persona, PersonaType
from app.schemas.prediction import LognormalParams, MindState, PriorParams
from app.schemas.report import MissingReport

# Koester 프로파일별 이동 거리 lognormal 파라미터 (km).
# 치매 = ISRID **Urban** 도메인 원표 정합 (2026-07-12 재교정, 출처 대조 완료):
#   ISRID Dementia Urban (n=336): 25%=0.3 / 50%=1.1 / 75%=3.2 / 95%=12.6 km
#   — Koester, Lost Person Behavior (dbS Productions); Laing 2013
#     "Analysis of Missing Dementia Persons in an Urban Environment" Table 1 재인용.
#   lognormal(μ=0.095, σ=1.48) 적합값 = 0.40/1.1/3.0/12.6 → 4개 분위수 모두 일치.
# 이전 값(μ=0.47, σ=1.53)은 ISRID Dry 지형 값으로 추정 — 도시 서비스와 도메인 불일치,
# 문서의 "95% 6.4km" 해석은 어느 도메인과도 불일치(문서 오류).
# 모집단 prior 는 넓게 유지한다: 개인 이질성(0.3km 배회~대중교통 12km)이 섞인 값이고,
# 개인화(EXAONE radius_level·끌림점)가 분포를 옮기고 좁히는 방향으로 소비한다.
# 좁은 σ 는 가드레일(μ±0.4) 위에서 먼 끌림점 페르소나를 구조적으로 표현 불가하게 만든다.
# ⚠️ 지적장애는 Urban 분위수 원표 미확보 — σ 유지, 원 Koester 표 대조 검증 필요
#   (현 σ 로는 95%≈28km 로 비현실적).
_KOESTER_PARAMS: dict[PersonaType, LognormalParams] = {
    PersonaType.dementia: LognormalParams(mu=0.095, sigma=1.48),               # ISRID Urban: 50% 1.1km, 95% 12.6km
    PersonaType.intellectual_disability: LognormalParams(mu=0.89, sigma=1.50), # 중앙값 ~2.4km — σ 검증 필요
}

# Hashimoto 2022 6전략 — 프로파일별 기본 확률 (placeholder, 논문 값으로 교체 대상)
_STRATEGY_PRIORS: dict[PersonaType, dict[str, float]] = {
    PersonaType.dementia: {
        "route_following": 0.30, "direction_keeping": 0.25, "random_walk": 0.15,
        "backtracking": 0.05, "staying_put": 0.10, "landmark_seeking": 0.15,
    },
    PersonaType.intellectual_disability: {
        "route_following": 0.25, "direction_keeping": 0.20, "random_walk": 0.15,
        "backtracking": 0.10, "staying_put": 0.15, "landmark_seeking": 0.15,
    },
}


# ── 목적지 예측 (prior 생성) 프롬프트 ──────────────────────────────
# 좌표·거리(km)를 직접 묻지 않는다 — LLM calibration 한계(아키텍처 결정사항).
# 수치는 전략확률만 받고, 끌림점·반경은 상/중/하 정성 등급으로 받아
# guardrail 이 고정 매핑으로 수치화한다.
_PRIOR_SYSTEM = """\
너는 실종자 수색(SAR) 행동 분석 전문가다. 실종자의 프로필과 보호자가 알려준 \
평소 행동 사실을 읽고, 어디로 향했을지에 대한 사전 분포 파라미터를 추정한다.

6가지 이동 전략:
- route_following: 아는 길·익숙한 경로를 따라감
- direction_keeping: 한 방향으로 계속 직진
- random_walk: 방향성 없이 배회
- backtracking: 왔던 길을 되돌아감
- staying_put: 한 곳에 머무름
- landmark_seeking: 특정 장소(끌림점)를 향해 이동

출력 규칙:
- JSON 객체 하나만 출력한다. JSON 밖에 어떤 문장도 쓰지 않는다.
- strategy_probs: 6개 전략 모두 포함, 값의 합이 1.
- attraction_levels: 주어진 끌림점 라벨마다 "상"/"중"/"하" 중 하나. \
주어지지 않은 라벨을 만들어내지 않는다. 키는 괄호의 근거 표시를 뺀 라벨 원문 그대로. \
끌림점의 근거를 등급에 반영한다: 과거 실종 때 실제 발견된 곳 > 보호자가 반복 지향을 \
직접 관찰 > 지나가듯 언급만.
- radius_level: 같은 유형의 평균적인 실종자보다 멀리 이동할 사람이면 "상", \
비슷하면 "중", 가까이 머물 사람이면 "하".
- reasoning: 판단 근거 2~3문장 (한국어)."""

_PRIOR_FEWSHOT_USER = """\
[실종자]
- 유형: 치매 노인, 나이: 82세
- 끌림점:
  - 옛 직장(방직공장) — 근거: 과거 실종 때 실제 발견된 곳
  - 단골 목욕탕 — 근거: 지나가듯 언급만
- 평소 행동 사실:
  - 해질녘이면 옛 직장 방향으로 걸어가는 습관이 있음
  - 30년 다닌 출퇴근길은 지금도 정확히 기억함
  - 최근 집 앞에서도 방향을 헷갈린 적이 두 번 있음
- 실종 상황: 18:20 자택 앞에서 마지막 목격, 현재 2시간 경과"""

_PRIOR_FEWSHOT_ASSISTANT = """\
{"strategy_probs": {"route_following": 0.35, "direction_keeping": 0.15, \
"random_walk": 0.10, "backtracking": 0.05, "staying_put": 0.05, "landmark_seeking": 0.30}, \
"attraction_levels": {"옛 직장(방직공장)": "상", "단골 목욕탕": "하"}, \
"radius_level": "중", \
"reasoning": "옛 직장은 과거 실종 때 실제 발견된 곳이고 해질녘 그 방향으로 걷는 습관도 \
있어 최상위 끌림점으로 봤다. 목욕탕은 언급만 있어 낮게 뒀다. 출퇴근길 기억이 뚜렷해 \
익숙한 경로 추종 확률을 높였고, 최근 방향 혼동이 있어 배회 가능성도 남겼다. \
보행 능력에 특이사항이 없어 이동 반경은 유형 평균 수준으로 판단했다."}"""

_TYPE_LABEL = {
    PersonaType.dementia: "치매 노인",
    PersonaType.intellectual_disability: "지적장애인",
}

# ── 마음 재해석 (H·A 트리거 발동 시) 프롬프트 ──────────────────────
# 회의 원칙: 게이지를 자연어로 번역해 주고 좌표는 주지 않는다.
# 출력도 자연어 판단 + 정성 등급만 — 수치화는 guardrail 이 한다.
_MIND_SYSTEM = """\
너는 실종자 수색(SAR) 행동 분석 전문가다. 이동 중인 실종자의 내면 상태가 \
임계를 넘었다는 보고를 받고, 지금 이 사람의 마음 상태와 목표를 재해석한다.
예: 치매 노인이라면 현재를 과거로 착각(time-shifting)해 '집'이 현재 집이 아니라 \
옛집을 뜻하게 될 수 있다.

출력 규칙:
- JSON 객체 하나만 출력한다. JSON 밖에 어떤 문장도 쓰지 않는다.
- status: 현재 마음 상태 한 구절 (예: "옛집으로 돌아가려 함", "불안해서 큰길을 찾음")
- confusion_level: 혼란 정도 "상"/"중"/"하"
- goal_label: 주어진 끌림점 후보 중 지금 향할 곳 하나. 방향을 바꿀 이유가 없거나 \
후보에 없는 곳이면 null. 후보에 없는 장소를 지어내지 않는다.
- reasoning: 근거 1~2문장 (한국어)."""


# 마음 재해석에 텍스트로만 반영할 취약성 축(2-B) — PriorParams 3필드 어디에도
# 안 맞는 마음축 취약성형. 출력은 기존 sanitize_mind() 가 그대로 검증하므로
# 입력을 풍부하게 해줄 뿐 안전장치는 안 건드린다.
_VULN_AXIS_KO = {
    "hazard_awareness_vulnerability": "위험 인식",
    "communication_approach_vulnerability": "의사소통·낯선사람 반응",
    "wayfinding_error_recovery_deficit": "길찾기·경로회복",
    "distress_induced_movement_reactivity": "불안 시 이동 반응",
    "aversive_context_escape": "불편 회피 행동",
    "transition_routine_disruption": "루틴 변화 취약성",
}


def _axis_level_ko(score: float) -> str:
    return "낮음" if score < 0.3 else ("중간" if score < 0.7 else "높음")


# 환경 레이어 거리 필드 → 장면 문장 조각. 임계는 "지금 눈에 들어오는가"
# 기준의 잠정값 — 물가는 익사 위험이라 더 멀리서도 알린다.
_SCENE_FEATURES: list[tuple[str, float, str]] = [
    ("water_m", 100.0, "물가"),
    ("market_m", 60.0, "시장"),
    ("park_m", 60.0, "공원"),
    ("forest_m", 60.0, "수풀"),
]


def build_scene_text(env: dict | None) -> str | None:
    """노드 환경 dict → 자연어 장면 1줄. 임계 밖이면 None.

    좌표 불가침 원칙 유지 — 위경도가 아니라 "지금 무엇이 보이는가"의 국소
    의미 텍스트만 준다 (대형 그래프 추론은 LLM 불가, 국소 장면은 가능).

    방향(끌림/회피) 판단은 여기서 하드코딩하지 않는다. 같은 "물가 30m"라도
    좋아하는 사람과 무서워하는 사람이 다르게 반응하므로, 사실만 주고 해석은
    페르소나 맥락을 함께 보는 EXAONE 이 한다. 아동 제거(PR #47)로 물가
    하드코딩이 사라진 뒤 water 가 수집만 되고 소비처가 없던 결손을 이 경로로
    복원한다 — 알고리즘이 방향을 정하지 않으므로 근거 없는 확신이 안 생긴다.
    """
    if not env:
        return None
    parts = []
    for key, threshold_m, korean in _SCENE_FEATURES:
        dist = env.get(key)
        if isinstance(dist, (int, float)) and dist <= threshold_m:
            parts.append(f"{korean} {round(dist)}m")
    land = env.get("landcover_l3") or env.get("landcover_l1")
    if land:
        parts.append(str(land))
    return ", ".join(parts) if parts else None


def _build_mind_input(
    persona: Persona,
    gauge_report: str,
    labels: list[str],
    prior: PriorParams | None = None,
    scene: str | None = None,
) -> str:
    lines = [
        "[실종자]",
        f"- 유형: {_TYPE_LABEL[persona.type]}, 나이: {persona.age}세",
    ]
    if persona.behavior_notes:
        lines.append("- 평소 행동 사실:")
        lines += [f"  - {note}" for note in persona.behavior_notes]
    if persona.axis_scores:
        vuln = [f"{_VULN_AXIS_KO[k]}: {_axis_level_ko(v)}"
                for k, v in persona.axis_scores.items() if k in _VULN_AXIS_KO]
        if vuln:
            lines.append("[특성] " + ", ".join(vuln))
    if prior is not None:
        top_strategy = max(prior.strategy_probs, key=prior.strategy_probs.get)
        lines.append(f"[예측된 이동 성향] 주 전략: {top_strategy}")
        if prior.attraction_weights:
            top_label = max(prior.attraction_weights, key=prior.attraction_weights.get)
            lines.append(f"[유력 목적지 후보] {top_label}")
    lines.append(f"[현재 상태] {gauge_report}")
    if scene:
        lines.append(f"[주변 장면] {scene}")
    lines.append(f"[끌림점 후보] {', '.join(labels) if labels else '(없음)'}")
    lines.append("[질문] 이 사람은 지금 어떤 마음 상태이고, 어디로 향하려 하는가?")
    return "\n".join(lines)


_EVIDENCE_KO = {
    "previous_missing_found": "과거 실종 때 실제 발견된 곳",
    "caregiver_report": "보호자가 반복 지향을 직접 관찰",
    "mention_only": "지나가듯 언급만",
}


def _build_prior_input(persona: Persona | None, report: MissingReport) -> str:
    lines = ["[실종자]"]
    if persona:
        lines.append(f"- 유형: {_TYPE_LABEL[persona.type]}, 나이: {persona.age}세")
        if persona.attraction_points:
            # 근거 태그를 사람 말로 붙인다 — attraction_levels 의 키는 라벨 원문이어야
            # 하므로 근거는 별도 주석 위치(— 근거: …)에만 둔다 (few-shot 이 시연).
            lines.append("- 끌림점:")
            for ap in persona.attraction_points:
                ev = _EVIDENCE_KO.get(ap.evidence, _EVIDENCE_KO["mention_only"])
                lines.append(f"  - {ap.label} — 근거: {ev}")
        if persona.behavior_notes:
            lines.append("- 평소 행동 사실:")
            lines += [f"  - {note}" for note in persona.behavior_notes]
    else:
        lines.append(f"- 유형: {_TYPE_LABEL[report.missing_type]} (사전 등록 정보 없음)")
    lines.append(f"- 실종 상황: {report.lkp_time:%H:%M} 마지막 목격")
    return "\n".join(lines)


class ExaoneClient(LLMClient):
    name = "LG EXAONE"

    def __init__(self) -> None:
        super().__init__(settings.exaone_api_key)
        self.base_url = settings.exaone_base_url.rstrip("/")
        self.model = settings.exaone_model
        # 실호출 입·출력 기록 — E2E 대시보드가 "EXAONE 이 뭘 받고 뭘 뱉었나"를
        # 보여주는 유일한 통로 (스텁 모드에서는 기록 없음). 최근 것만 유지.
        self.call_log: list[dict] = []

    def _log_call(self, kind: str, prompt: str, response: str) -> None:
        self.call_log.append({"kind": kind, "prompt": prompt, "response": response})
        del self.call_log[:-50]

    @property
    def is_stub(self) -> bool:
        # 키·URL·모델이 모두 있어야 실동작 (Mi:dm 과 동일 규약)
        return not (self.api_key and self.base_url and self.model)

    # ── OpenAI 호환 chat completions ────────────────────────────────
    def _chat_url(self) -> str:
        base = self.base_url
        if base.endswith("/chat/completions"):
            return base
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    def chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.3,
        max_tokens: int = 512,
        enable_thinking: bool = False,
    ) -> str:
        """messages=[{role, content}...] → assistant content 문자열.

        K-EXAONE 은 reasoning 모델(답 전에 '생각'을 먼저 씀, 서버 기본 켜짐)이라
        thinking 을 켠 채 두면 max_tokens 를 생각에 다 쓰고 content 없이 잘릴 수
        있다 (실측: 512토큰 전부 reasoning, finish_reason=length). 우리 파이프라인은
        짧은 구조화 출력을 자주 받는 용도라 기본 꺼둔다.
        """
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "chat_template_kwargs": {"enable_thinking": enable_thinking},
        }).encode("utf-8")
        req = urllib.request.Request(
            self._chat_url(),
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=settings.llm_timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        message = data["choices"][0]["message"]
        content = message.get("content")
        if content is None:
            finish = data["choices"][0].get("finish_reason")
            raise RuntimeError(
                f"{self.name}: content 없는 응답 (finish_reason={finish}) — "
                "reasoning 이 max_tokens 를 소진했을 가능성. max_tokens 를 늘리거나 "
                "enable_thinking=False 인지 확인하세요."
            )
        return content

    def _call_api(self, prompt: str, **kwargs) -> str:
        return self.chat([{"role": "user", "content": prompt}], **kwargs)

    def generate_prior(self, persona: Persona | None, report: MissingReport) -> PriorParams:
        """Few-shot CoT 로 개인 맥락 → prior 생성. 출력은 가드레일 통과 후에만 사용.

        스텁 모드(키 없음) 또는 호출·파싱 실패 시: 프로파일 통계 기본값.
        """
        default = self._default_prior(persona, report)
        if self.is_stub:
            prior = default
        else:
            prior_input = _build_prior_input(persona, report)
            try:
                raw = self.chat(
                    [
                        {"role": "system", "content": _PRIOR_SYSTEM},
                        {"role": "user", "content": _PRIOR_FEWSHOT_USER},
                        {"role": "assistant", "content": _PRIOR_FEWSHOT_ASSISTANT},
                        {"role": "user", "content": prior_input},
                    ],
                    temperature=0.2,
                    max_tokens=700,
                )
                self._log_call("prior", prior_input, raw)
                data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
                prior = guardrail.sanitize_prior(data, persona, default)
            except Exception as e:  # noqa: BLE001 — LLM 실패가 예측 자체를 막으면 안 됨
                prior = default.model_copy(update={
                    "reasoning": f"[폴백] EXAONE prior 실패({type(e).__name__}) — 통계 기본값 사용"})

        # 축점수(phase0.axis_scoring) 반영 — 스텁이든 실호출이든 항상 실행.
        # 가드레일 안에만 넣으면 스텁 모드(로컬 개발 기본값)에서 효과가 안 보인다.
        axis_scores = persona.axis_scores if persona else {}
        return guardrail.apply_axis_scores(prior, axis_scores, persona, default.radius_lognormal)

    def _default_prior(self, persona: Persona | None, report: MissingReport) -> PriorParams:
        """프로파일 통계 기본값 — 스텁 모드이자 가드레일의 항목별 폴백 기준.

        끌림점 가중치는 AttractionPoint.weight(= evidence 계수) 정규화 —
        LLM 등급이 없는 경로라 곱셈 병합의 evidence 항만 남는 형태다.
        """
        mtype = report.missing_type
        attraction: dict[str, float] = {}
        if persona and persona.attraction_points:
            total = sum(p.weight for p in persona.attraction_points)
            attraction = {p.label: p.weight / total for p in persona.attraction_points}
        return PriorParams(
            strategy_probs=dict(_STRATEGY_PRIORS[mtype]),
            attraction_weights=attraction,
            radius_lognormal=_KOESTER_PARAMS[mtype],
            reasoning="[스텁] 프로파일 통계 기본값 사용 — EXAONE 연동 후 개인 맥락 반영",
        )

    def reinterpret_mind(
        self,
        persona: Persona,
        current: MindState,
        gauge_report: str,
        labels: list[str],
        prior: PriorParams | None = None,
        scene: str | None = None,
    ) -> tuple[MindState, str | None]:
        """H·A 게이지 발동 시 마음·목표 재해석 — 시뮬레이션 워커가 호출.

        prior: 이번 예측의 목적지 prior(전략확률·끌림점가중치) — 마음 재해석이
        "예측된 이동 성향"을 참고 문맥으로 쓸 수 있게 전달(작업 3). 없어도 동작.
        scene: 현재 노드의 주변 장면 텍스트(`build_scene_text`) — 외인성 자극을
        마음 재해석에 공급한다(PR #21 과제2 1단계). 없어도 동작.

        반환: (검증된 MindState, 새 목표 끌림점 라벨 또는 None).
        스텁 모드·실패 시: 혼란도 +0.2 휴리스틱, 목표 유지.
        """
        fallback = (MindState(status="혼란 심화",
                              confusion=min(1.0, current.confusion + 0.2),
                              changed=True), None)
        if self.is_stub:
            return fallback
        mind_input = _build_mind_input(persona, gauge_report, labels, prior, scene)
        try:
            raw = self.chat(
                [
                    {"role": "system", "content": _MIND_SYSTEM},
                    {"role": "user", "content": mind_input},
                ],
                temperature=0.3,
                max_tokens=400,
            )
            self._log_call("mind", mind_input, raw)
            data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        except Exception:  # noqa: BLE001 — LLM 실패가 시뮬레이션을 막으면 안 됨
            return fallback
        return guardrail.sanitize_mind(data, current, labels)

    def predict_mind(self, current: MindState, observations: list[str]) -> MindState:
        """제보 관찰 문장 기반 마음 예측 — 상태 변화가 의심될 때만 호출 (비용 원칙).

        스텁: observations 에 심리 단서가 있으면 혼란도를 올리고 상태 변경.
        (시뮬레이션 내부의 게이지 발동 재해석은 reinterpret_mind 가 담당.)
        """
        # TODO: 제보 파이프라인에서 실관찰이 쌓이면 EXAONE 추론으로 교체
        cues = [o for o in observations if any(k in o for k in ("울", "뛰", "헤매", "불안"))]
        if cues:
            return MindState(status="혼란 심화", confusion=min(1.0, current.confusion + 0.2), changed=True)
        return current.model_copy(update={"changed": False})

    def summarize_case(self, case_summary: str) -> str:
        """보호자·경찰용 수색 리포트 생성 (Solar Pro 와 협업)."""
        # TODO: API 연동
        return f"[스텁 리포트] {case_summary}"

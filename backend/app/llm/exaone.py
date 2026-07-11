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

# Koester 프로파일별 이동 거리 lognormal 파라미터 (km) — 아키텍처 문서 값 (2026-07-11 교정)
#   치매: 50%가 1.6km, 95%가 6.4km 이내 / 아동은 문서의 1~3세 값(연령대 세분화 전 잠정)
_KOESTER_PARAMS: dict[PersonaType, LognormalParams] = {
    PersonaType.dementia: LognormalParams(mu=0.47, sigma=1.53),                # 중앙값 ~1.6km
    PersonaType.child: LognormalParams(mu=-1.2, sigma=1.4),                    # 중앙값 ~0.3km (1~3세)
    PersonaType.intellectual_disability: LognormalParams(mu=0.89, sigma=1.50), # 중앙값 ~2.4km
}

# Hashimoto 2022 6전략 — 프로파일별 기본 확률 (placeholder, 논문 값으로 교체 대상)
_STRATEGY_PRIORS: dict[PersonaType, dict[str, float]] = {
    PersonaType.dementia: {
        "route_following": 0.30, "direction_keeping": 0.25, "random_walk": 0.15,
        "backtracking": 0.05, "staying_put": 0.10, "landmark_seeking": 0.15,
    },
    PersonaType.child: {
        "route_following": 0.20, "direction_keeping": 0.10, "random_walk": 0.20,
        "backtracking": 0.15, "staying_put": 0.25, "landmark_seeking": 0.10,
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
주어지지 않은 라벨을 만들어내지 않는다.
- radius_level: 같은 유형의 평균적인 실종자보다 멀리 이동할 사람이면 "상", \
비슷하면 "중", 가까이 머물 사람이면 "하".
- reasoning: 판단 근거 2~3문장 (한국어)."""

_PRIOR_FEWSHOT_USER = """\
[실종자]
- 유형: 치매 노인, 나이: 82세
- 끌림점: 옛 직장(방직공장), 단골 목욕탕
- 평소 행동 사실:
  - 해질녘이면 옛 직장 방향으로 걸어가는 습관이 있음
  - 30년 다닌 출퇴근길은 지금도 정확히 기억함
  - 최근 집 앞에서도 방향을 헷갈린 적이 두 번 있음
- 실종 상황: 18:20 자택 앞에서 마지막 목격, 현재 2시간 경과"""

_PRIOR_FEWSHOT_ASSISTANT = """\
{"strategy_probs": {"route_following": 0.35, "direction_keeping": 0.15, \
"random_walk": 0.10, "backtracking": 0.05, "staying_put": 0.05, "landmark_seeking": 0.30}, \
"attraction_levels": {"옛 직장(방직공장)": "상", "단골 목욕탕": "중"}, \
"radius_level": "중", \
"reasoning": "해질녘 옛 직장 방향 습관과 출퇴근길 기억이 뚜렷해 익숙한 경로 추종과 \
끌림점 지향 확률을 높게 봤다. 최근 방향 혼동이 있어 배회 가능성도 남겼다. \
보행 능력에 특이사항이 없어 이동 반경은 유형 평균 수준으로 판단했다."}"""

_TYPE_LABEL = {
    PersonaType.dementia: "치매 노인",
    PersonaType.child: "아동",
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


def _build_mind_input(persona: Persona, gauge_report: str, labels: list[str]) -> str:
    lines = [
        "[실종자]",
        f"- 유형: {_TYPE_LABEL[persona.type]}, 나이: {persona.age}세",
    ]
    if persona.behavior_notes:
        lines.append("- 평소 행동 사실:")
        lines += [f"  - {note}" for note in persona.behavior_notes]
    lines.append(f"[현재 상태] {gauge_report}")
    lines.append(f"[끌림점 후보] {', '.join(labels) if labels else '(없음)'}")
    lines.append("[질문] 이 사람은 지금 어떤 마음 상태이고, 어디로 향하려 하는가?")
    return "\n".join(lines)


def _build_prior_input(persona: Persona | None, report: MissingReport) -> str:
    lines = ["[실종자]"]
    if persona:
        lines.append(f"- 유형: {_TYPE_LABEL[persona.type]}, 나이: {persona.age}세")
        if persona.attraction_points:
            labels = ", ".join(ap.label for ap in persona.attraction_points)
            lines.append(f"- 끌림점: {labels}")
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
            return default
        try:
            raw = self.chat(
                [
                    {"role": "system", "content": _PRIOR_SYSTEM},
                    {"role": "user", "content": _PRIOR_FEWSHOT_USER},
                    {"role": "assistant", "content": _PRIOR_FEWSHOT_ASSISTANT},
                    {"role": "user", "content": _build_prior_input(persona, report)},
                ],
                temperature=0.2,
                max_tokens=700,
            )
            data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        except Exception as e:  # noqa: BLE001 — LLM 실패가 예측 자체를 막으면 안 됨
            return default.model_copy(update={
                "reasoning": f"[폴백] EXAONE prior 실패({type(e).__name__}) — 통계 기본값 사용"})
        return guardrail.sanitize_prior(data, persona, default)

    def _default_prior(self, persona: Persona | None, report: MissingReport) -> PriorParams:
        """프로파일 통계 기본값 — 스텁 모드이자 가드레일의 항목별 폴백 기준."""
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
    ) -> tuple[MindState, str | None]:
        """H·A 게이지 발동 시 마음·목표 재해석 — 시뮬레이션 워커가 호출.

        반환: (검증된 MindState, 새 목표 끌림점 라벨 또는 None).
        스텁 모드·실패 시: 혼란도 +0.2 휴리스틱, 목표 유지.
        """
        fallback = (MindState(status="혼란 심화",
                              confusion=min(1.0, current.confusion + 0.2),
                              changed=True), None)
        if self.is_stub:
            return fallback
        try:
            raw = self.chat(
                [
                    {"role": "system", "content": _MIND_SYSTEM},
                    {"role": "user", "content": _build_mind_input(persona, gauge_report, labels)},
                ],
                temperature=0.3,
                max_tokens=400,
            )
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

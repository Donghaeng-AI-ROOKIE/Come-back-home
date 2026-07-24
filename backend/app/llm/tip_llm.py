"""Phase 3 시민 제보 구조화 전용 LLM 클라이언트 — 모델 미정.

역할은 딱 둘: (1) 자유텍스트 제보를 슬롯 JSON으로 구조화, (2) 구체성·일관성
상/중/하 등급 판정. 다턴 대화가 아니라 1회성 추출+분류라 가벼운 모델로 충분
— 그래서 Mi:dm(Phase 0 온보딩 대화 전용)과 분리했다(2026-07-21).

서빙: settings 에 tip_llm_base_url(endpoint URL) / tip_llm_model(endpoint ID) /
tip_llm_api_key 를 채우면 실동작, 비어 있으면 결정적 스텁으로 폴백(모델 미정인
동안에도 파이프라인이 그대로 동작). 모델이 정해지면 이 세 값만 채우면 되고
(OpenAI 호환 chat completions 전제), 그 값 형태가 다르면 이 파일만 고치면 된다
— tip_flow.py 등 소비처는 그대로.
"""

from __future__ import annotations

import json
import re
import urllib.request

from app.config import settings
from app.llm.base import LLMClient

_CLOCK_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_TIME_KINDS = ("relative", "absolute", "vague", "none")


class TipLLMClient(LLMClient):
    name = "Tip 구조화 LLM (모델 미정)"

    def __init__(self) -> None:
        super().__init__(settings.tip_llm_api_key)
        self.base_url = settings.tip_llm_base_url.rstrip("/")
        self.model = settings.tip_llm_model
        self.call_failures = 0  # 호출 실패 누적 — 장애 감지용(현재 소비처 없음, midm 패턴과 통일)

    @property
    def is_stub(self) -> bool:
        return not (self.api_key and self.base_url and self.model)

    # ── OpenAI 호환 chat completions ────────────────────────────────
    def _chat_url(self) -> str:
        base = self.base_url
        if base.endswith("/chat/completions"):
            return base
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    def chat(self, messages: list[dict], *, temperature: float = 0.1, max_tokens: int = 400) -> str:
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
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
        return data["choices"][0]["message"]["content"]

    def _call_api(self, prompt: str, **kwargs) -> str:
        return self.chat([{"role": "user", "content": prompt}], **kwargs)

    # ── Phase 3 시민 제보 구조화 ─────────────────────────────────────
    def structure_tip(self, text: str) -> dict:
        """구어체 시민 제보 → 구조화 데이터.

        반환: {location_text, time_text, time_kind, time_minutes_ago, time_clock,
               appearance_cues, direction, specificity("상"/"중"/"하")}.
        specificity 는 신뢰도 p 의 구체성 항 입력 — LLM 에 숫자를 직접 받지 않고
        상/중/하 등급만 받아 trust 가 고정값으로 매핑한다 (가드레일 패턴).
        time_kind/time_minutes_ago/time_clock 도 같은 가드레일 패턴: LLM 은 시민이
        "명시한" 값만 뽑고(relative/absolute), 상대→절대시각 산술은
        app.phase3.time_resolve 가 결정론적으로 한다 — LLM 이 몇 분 전인지
        추측해서 숫자를 지어내면 안 되므로 여기서 값 형태만 검증한다.
        스텁: 키워드 휴리스틱으로 필드 채움 비율 → 등급.
        """
        if self.is_stub:
            return _stub_structure_tip(text)
        try:
            raw = self.chat(
                [
                    {"role": "system", "content": _TIP_STRUCTURE_SYSTEM},
                    {"role": "user", "content": text},
                ],
                temperature=0.1,
                max_tokens=400,
            )
            data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        except Exception:  # noqa: BLE001 — 호출·파싱 실패 → 휴리스틱 폴백.
            # LLM 실패가 제보 접수를 막으면 안 된다 (실측: 엔드포인트 만료 410 이
            # 500 으로 전파돼 제보가 통째로 거부되던 문제).
            self.call_failures += 1
            return _stub_structure_tip(text)
        level = data.get("specificity")
        time_kind = data.get("time_kind") if data.get("time_kind") in _TIME_KINDS else "none"
        minutes_ago = data.get("time_minutes_ago")
        if time_kind != "relative" or not isinstance(minutes_ago, int) or minutes_ago < 0:
            minutes_ago = None
        clock = data.get("time_clock")
        if time_kind != "absolute" or not _CLOCK_RE.match(str(clock or "")):
            clock = None
        return {
            "location_text": data.get("location_text"),
            "time_text": data.get("time_text"),
            "time_kind": time_kind,
            "time_minutes_ago": minutes_ago,
            "time_clock": clock,
            "appearance_cues": data.get("appearance_cues") or [],
            "direction": data.get("direction"),
            "specificity": level if level in ("상", "중", "하") else "중",
        }

    def next_tip_question(self, structured: dict) -> str | None:
        """확장용 — 현재 흐름(자유텍스트+위치 조건부 되묻기)은 안 쓴다.

        고정 4개(위치·시각·인상착의·행동/방향)를 순서대로, 확보 안 된 것부터.
        향후 다턴 세션화 시 재활용 자리로 남겨둔다.
        """
        if not structured.get("location_text"):
            return _TIP_Q_LOCATION
        if not structured.get("time_text"):
            return _TIP_Q_TIME
        if not structured.get("appearance_cues"):
            return _TIP_Q_APPEARANCE
        if not structured.get("direction"):
            return _TIP_Q_DIRECTION
        return None


# ── 질문 뱅크 (확장용 — 현재 흐름은 위치만 조건부 되묻기, 8절 참고) ──────
_TIP_Q_LOCATION = "어디서 보셨어요? 근처 건물이나 가게 이름을 알려주세요."
_TIP_Q_TIME = "몇 시쯤이었을까요? 방금 전인가요, 아까쯤인가요?"
_TIP_Q_APPEARANCE = "무엇을 입고 있었는지, 어떤 모습이었는지 기억나세요?"
_TIP_Q_DIRECTION = "그때 뭘 하고 계셨나요? 어느 쪽으로 가셨어요?"

_TIP_STRUCTURE_SYSTEM = """\
너는 실종자 목격 제보를 정리하는 보조원이다. 시민의 구어체 제보에서 아래를 뽑아 \
JSON 객체 하나만 출력한다 (JSON 밖 문장 금지). 없는 정보는 지어내지 말고 null.

- location_text: 목격 장소 (건물·가게·교차로 등), 없으면 null
- time_text: 목격 시각 표현 ("방금", "30분 전", "3시쯤"), 없으면 null
- time_kind: "relative"(N분/시간 전, 방금) / "absolute"(N시 등 시계 표현) / \
"vague"(아까·좀전 등 모호) / "none"(시각 언급 없음)
- time_minutes_ago: time_kind가 relative일 때만 정수(방금=0, "30분 전"=30, \
"2시간 전"=120). 아니면 null
- time_clock: time_kind가 absolute일 때만 "HH:MM" 24시간(오전/오후 반영). 아니면 null
- appearance_cues: 옷차림·외모 단서 문자열 배열, 없으면 []
- direction: 이동 방향·행동 ("골목 쪽", "북쪽으로"), 없으면 null
- specificity: 제보의 구체성·일관성 등급 "상"/"중"/"하" 중 하나. \
장소·시각·외모가 모두 구체적이고 앞뒤가 맞으면 "상", 하나만 있거나 모호하면 "하".

⚠️ 시민이 명시하지 않은 시각을 추측해서 숫자를 만들지 마라. 모호하면 vague, \
언급이 없으면 none."""


_STUB_HOURS_AGO_RE = re.compile(r"(\d+)\s*시간\s*전")
_STUB_MINUTES_AGO_RE = re.compile(r"(\d+)\s*분\s*전")


def _stub_time_kind(text: str) -> tuple[str, int | None]:
    """스텁 상대시각 파싱 — 절대시각("3시쯤")은 오전/오후 중의성이 있어 스텁에선
    보수적으로 시도하지 않는다(vague 로 남김, 실LLM 만 absolute 를 낸다)."""
    if "방금" in text or "지금" in text:
        return "relative", 0
    m = _STUB_HOURS_AGO_RE.search(text)
    if m:
        return "relative", int(m.group(1)) * 60
    m = _STUB_MINUTES_AGO_RE.search(text)
    if m:
        return "relative", int(m.group(1))
    if any(k in text for k in ("분", "시", "아까", "전")):
        return "vague", None
    return "none", None


def _stub_structure_tip(text: str) -> dict:
    """스텁·폴백 — 키워드 휴리스틱. LLM 없이 필드 채움 정도로 등급 근사."""
    cues = [k for k in ("점퍼", "셔츠", "바지", "모자", "치마", "코트", "운동화") if k in text]
    behavior = [k for k in ("울", "뛰", "헤매", "앉아", "두리번") if k in text]
    time_kind, minutes_ago = _stub_time_kind(text)
    filled = sum([
        any(k in text for k in ("역", "앞", "동", "로", "길", "편의점", "시장", "공원")),  # 장소 흔적
        time_kind != "none",                                                              # 시각 흔적
        bool(cues),                                                                        # 외모
    ])
    level = "상" if filled >= 3 else ("중" if filled == 2 else "하")
    return {
        "location_text": None, "time_text": None,
        "time_kind": time_kind, "time_minutes_ago": minutes_ago, "time_clock": None,
        "appearance_cues": cues, "direction": behavior[0] if behavior else None,
        "specificity": level,
    }

"""Phase 3 시민 제보 구조화 전용 LLM 클라이언트 — Mi:dm 2.0 Mini.

역할은 딱 둘: (1) 자유텍스트 제보를 슬롯 JSON으로 구조화, (2) 구체성·일관성
상/중/하 등급 판정. 다턴 대화가 아니라 1회성 추출+분류라 가벼운 모델로 충분
— 그래서 Mi:dm(Phase 0 온보딩 대화 전용)과 분리했다(2026-07-21).

모델 선정: 4파전(Mi:dm 2.0 Mini·A.X-4.0-Light·Solar-mini·EXAONE 4.0) 실측
비교로 Mi:dm 2.0 Mini 확정(2026-07-29, 균형정확도 76.4%로 1위 — 상세는
experiments/tip_llm_compare/). GPU 서버에 원본 모델을 직접 호스팅해 연결까지
완료(2026-07-30).

서빙: settings 에 tip_llm_base_url(endpoint URL) / tip_llm_model(endpoint ID) /
tip_llm_api_key 를 채우면 실동작, 비어 있으면 결정적 스텁으로 폴백. 다른
서빙 방식(엔드포인트 형태 등)으로 바꿀 땐 이 파일만 고치면 된다 —
tip_flow.py 등 소비처는 그대로.
"""

from __future__ import annotations

import json
import re

from app.config import settings
from app.llm.base import LLMClient

_CLOCK_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_TIME_KINDS = ("relative", "absolute", "vague", "none")
_MERIDIEMS = ("am", "pm")


class TipLLMClient(LLMClient):
    name = "Tip 구조화 LLM (Mi:dm 2.0 Mini)"

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
        import uuid

        from app.llm.usage_ledger import logged_json_request
        run_id = "tip-structure:" + str(uuid.uuid4())
        data = logged_json_request(self._chat_url(), {
            "model": self.model, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens,
        }, headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            provider="Mi:dm Mini (self-hosted)", model=self.model, role="tip_structure",
            run_id=run_id, logical_request_id=run_id, billing_basis="self_hosted_gpu",
            timeout=min(settings.llm_timeout, settings.tip_llm_timeout),
            ledger_path=settings.research_usage_ledger_path)
        return data["choices"][0]["message"]["content"]

    def _call_api(self, prompt: str, **kwargs) -> str:
        return self.chat([{"role": "user", "content": prompt}], **kwargs)

    # ── Phase 3 시민 제보 구조화 ─────────────────────────────────────
    def structure_tip(self, text: str) -> dict:
        """구어체 시민 제보 → 구조화 데이터.

        반환: {location_text, time_text, time_kind, time_minutes_ago, time_clock,
               time_meridiem, appearance_cues, direction, specificity("상"/"중"/"하")}.
        specificity 는 신뢰도 p 의 구체성 항 입력 — LLM 에 숫자를 직접 받지 않고
        상/중/하 등급만 받아 trust 가 고정값으로 매핑한다 (가드레일 패턴).
        time_kind/time_minutes_ago/time_clock/time_meridiem 도 같은 가드레일 패턴:
        LLM 은 시민이 "명시한" 값만 뽑고(relative/absolute), 상대→절대시각 산술과
        오전/오후 판단은 app.phase3.time_resolve 가 결정론적으로 한다 — LLM 이 몇 분
        전인지, 오전인지 오후인지 추측해서 지어내면 안 되므로 여기서 값 형태만 검증한다.
        time_clock 은 시민이 말한 숫자 그대로("1시 15분" → "01:15"), time_meridiem 은
        시민이 오전/오후를 밝혔을 때만 "am"/"pm", 아니면 None 이다.
        스텁(키 없는 개발 모드): 키워드 휴리스틱으로 필드 채움 비율 → 등급.
        호출·파싱 실패(운영): 판정 없음(_unjudged_tip) — 단어로 추정하지 않는다.
        """
        if self.is_stub:
            return _stub_structure_tip(text)
        try:
            raw = self.chat(
                [
                    {"role": "system", "content": _TIP_STRUCTURE_SYSTEM},
                    {"role": "user", "content": text},
                ],
                temperature=settings.tip_llm_temp_structure,
                max_tokens=400,
            )
            data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        except Exception:  # noqa: BLE001 — 호출·파싱 실패 → 판정 없음.
            # LLM 실패가 제보 접수를 막으면 안 된다 (실측: 엔드포인트 만료 410 이
            # 500 으로 전파돼 제보가 통째로 거부되던 문제). 그렇다고 키워드로 등급·시각을
            # 추정하지 않는다(2026-09-26 결정: 운영 경로에서 규칙 기반 단어 매핑 금지) —
            # 구체성 항은 빠지고(trust 재정규화) 시각은 명시값·접수 시각으로 간다.
            self.call_failures += 1
            return _unjudged_tip()
        level = data.get("specificity")
        time_kind = data.get("time_kind") if data.get("time_kind") in _TIME_KINDS else "none"
        minutes_ago = data.get("time_minutes_ago")
        if time_kind != "relative" or not isinstance(minutes_ago, int) or minutes_ago < 0:
            minutes_ago = None
        clock = data.get("time_clock")
        if time_kind != "absolute" or not isinstance(clock, str) or not _CLOCK_RE.match(clock):
            clock = None
        meridiem = data.get("time_meridiem")
        if clock is None or meridiem not in _MERIDIEMS:
            meridiem = None
        return {
            "location_text": data.get("location_text"),
            "time_text": data.get("time_text"),
            "time_kind": time_kind,
            "time_minutes_ago": minutes_ago,
            "time_clock": clock,
            "time_meridiem": meridiem,
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
- time_clock: time_kind가 absolute일 때만 시민이 말한 시계 숫자 그대로 "HH:MM". 오전/오후를 \
더하거나 빼서 바꾸지 마라("1시 15분" → "01:15", "오후 3시" → "03:00", "13시 20분" → "13:20", \
"자정"·"밤 12시" → "00:00", "정오" → "12:00"). 아니면 null
- time_meridiem: 시민이 오전/오후를 밝혔을 때만 "am"(오전·새벽·아침) 또는 "pm"(오후·낮·저녁, \
"정오"). 밝히지 않았거나 "밤"처럼 자정 앞뒤로 갈리는 말이면 null. 오전/오후는 서버가 시점으로 \
고르므로 추측하지 마라
- appearance_cues: 옷차림·외모 단서 문자열 배열, 없으면 []
- direction: 이동 방향·행동 ("골목 쪽", "북쪽으로"), 없으면 null
- specificity: 제보의 구체성·일관성 등급 "상"/"중"/"하" 중 하나. 세 요소(장소·시각·외모)가 \
각각 "구체적"인지로 센다.
  · 장소가 구체적 = "근처"·"쪽"·"어디"처럼 위치를 흐리는 표현 없이 단정적으로 짚음. 상호·출구· \
교차로처럼 이름이 있는 곳뿐 아니라 "편의점", "버스정류장 벤치", "시장 골목"처럼 종류가 뚜렷한 \
곳도 포함. 모호 = 위치추정 표현이 붙어 흐려짐("공원 근처", "이 근처", "동네").
  · 시각이 구체적 = 시계·수치 표현("3시쯤", "30분 전", "방금"). 모호 = "아까", "좀전"처럼 \
특정 못 함.
  · 외모가 구체적 = 색+품목 등 식별 단서("빨간 패딩"). 모호 = "것 같아요", "정확힌 모르겠어요" \
처럼 불확실 표현이 붙거나 단서 자체가 없음.
  등급: "상" = 세 요소가 모두 구체적이고 앞뒤가 맞음. "중" = 구체적 요소가 1~2개, 또는 \
구체적 요소는 0개지만 세 요소가 전부 언급은 됨(모두 모호해도 언급 자체는 있음). "하" = 구체적 \
요소가 0개이고 언급된 요소도 1개 이하(2개 이상이 아예 언급 자체 없음)라 좁힐 단서가 없음.
  ※ 이동방향·행동은 등급 판정에 넣지 않는다(장소·시각·외모 3요소만).

⚠️ 시민이 명시하지 않은 시각을 추측해서 숫자를 만들지 마라. 모호하면 vague, \
언급이 없으면 none. "1시 15분"처럼 오전/오후가 없으면 time_clock "01:15", time_meridiem null 이다."""


_STUB_HOURS_AGO_RE = re.compile(r"(\d+)\s*시간\s*전")
_STUB_MINUTES_AGO_RE = re.compile(r"(\d+)\s*분\s*전")
# "오후 1시 15분", "3시쯤", "11시 반". "2시간"(경과)·"시장"(단어)은 시계 시각이 아니다.
_STUB_CLOCK_RE = re.compile(
    r"(?:(오전|새벽|아침)|(오후|낮|저녁))?\s*(?<!\d)(\d{1,2})\s*시(?!간)(?:\s*(\d{1,2})\s*분|\s*(반))?")


def _stub_time_kind(text: str) -> dict:
    """스텁 시각 파싱 → {time_kind, time_minutes_ago, time_clock, time_meridiem}.

    절대시각("1시 15분")은 말한 숫자 그대로 time_clock 에 두고, 오전/오후는 말했을 때만
    채운다 — 실LLM 계약과 같다. 오전/오후 중의성은 time_resolve 가 시점으로 푼다.
    """
    out = {"time_kind": "none", "time_minutes_ago": None, "time_clock": None, "time_meridiem": None}
    if "방금" in text or "지금" in text:
        return {**out, "time_kind": "relative", "time_minutes_ago": 0}
    m = _STUB_HOURS_AGO_RE.search(text)
    if m:
        return {**out, "time_kind": "relative", "time_minutes_ago": int(m.group(1)) * 60}
    m = _STUB_MINUTES_AGO_RE.search(text)
    if m:
        return {**out, "time_kind": "relative", "time_minutes_ago": int(m.group(1))}
    m = _STUB_CLOCK_RE.search(text)
    if m:
        hour = int(m.group(3))
        minute = 30 if m.group(5) else int(m.group(4) or 0)
        if hour <= 23 and minute <= 59:
            meridiem = "am" if m.group(1) else ("pm" if m.group(2) else None)
            return {**out, "time_kind": "absolute", "time_clock": f"{hour:02d}:{minute:02d}",
                    "time_meridiem": meridiem}
    if any(k in text for k in ("분", "시", "아까", "전")):
        return {**out, "time_kind": "vague"}
    return out


def _unjudged_tip() -> dict:
    """구조화 판정이 없을 때 — 아무 필드도 추정하지 않는다(구체성 None = 신뢰도 항 제외)."""
    return {
        "location_text": None, "time_text": None,
        "time_kind": "none", "time_minutes_ago": None, "time_clock": None, "time_meridiem": None,
        "appearance_cues": [], "direction": None, "specificity": None,
    }


def _stub_structure_tip(text: str) -> dict:
    """키 없는 개발 모드 스텁 — 키워드 휴리스틱. LLM 없이 필드 채움 정도로 등급 근사.

    운영(키 설정)에서는 실행되지 않는다. 호출 실패 폴백은 _unjudged_tip 이다.
    """
    cues = [k for k in ("점퍼", "셔츠", "바지", "모자", "치마", "코트", "운동화") if k in text]
    behavior = [k for k in ("울", "뛰", "헤매", "앉아", "두리번") if k in text]
    slots = _stub_time_kind(text)
    filled = sum([
        any(k in text for k in ("역", "앞", "동", "로", "길", "편의점", "시장", "공원")),  # 장소 흔적
        slots["time_kind"] != "none",                                                     # 시각 흔적
        bool(cues),                                                                        # 외모
    ])
    level = "상" if filled >= 3 else ("중" if filled == 2 else "하")
    return {
        "location_text": None, "time_text": None,
        **slots,
        "appearance_cues": cues, "direction": behavior[0] if behavior else None,
        "specificity": level,
    }

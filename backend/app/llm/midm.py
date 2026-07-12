"""KT Mi:dm — Phase 0 온보딩 인터뷰 챗봇 + Phase 3 시민 제보 구조화.

Phase 0 역할(노트 설계): '다음에 어느 슬롯을 물을지'는 검색(phase0.retrieval)이 정하고,
Mi:dm 은 그 슬롯을 (1) 자연스러운 존댓말 질문으로 문장화, (2) 직전 답변에서 슬롯값
추출 — 두 가지만 한다. 프롬프트는 phase0.prompts 참고.

서빙: KT 믿음 endpoint (OpenAI 호환 chat completions). settings 에
midm_base_url(endpoint URL) / midm_model(endpoint ID) / midm_api_key 를 채우면 실동작,
비어 있으면 결정적 스텁으로 폴백(키 없이 파이프라인 유지).
"""

from __future__ import annotations

import json
import urllib.request

from app.config import settings
from app.llm.base import LLMClient
from app.phase0 import prompts
from app.phase0.slots import SlotSpec
from app.schemas.persona import PersonaType


class MidmClient(LLMClient):
    name = "KT Mi:dm"

    def __init__(self) -> None:
        super().__init__(settings.midm_api_key)
        self.base_url = settings.midm_base_url.rstrip("/")
        self.model = settings.midm_model

    @property
    def is_stub(self) -> bool:
        # 키·URL·모델이 모두 있어야 실동작
        return not (self.api_key and self.base_url and self.model)

    # ── OpenAI 호환 chat completions ────────────────────────────────
    def _chat_url(self) -> str:
        base = self.base_url
        if base.endswith("/chat/completions"):
            return base
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        # 예: https://api.friendli.ai/dedicated → …/dedicated/v1/chat/completions
        return f"{base}/v1/chat/completions"

    def chat(self, messages: list[dict], *, temperature: float = 0.3, max_tokens: int = 512) -> str:
        """messages=[{role, content}...] → assistant content 문자열."""
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

    # ── Phase 0 온보딩 엘리시테이션 ─────────────────────────────────
    def extract_answer(self, target_slot: SlotSpec, conversation: list[dict]) -> dict:
        """직전 답변에서 슬롯값 추출 + 충족 판정.

        반환: {"fields", "attraction_points", "behavior_notes", "slot_filled"}.
        스텁 모드에서는 빈 추출(slot_filled=True 로 진행만 시킴).
        """
        if self.is_stub:
            return {"fields": {}, "attraction_points": [], "behavior_notes": [], "slot_filled": True}
        raw = self.chat(
            [
                {"role": "system", "content": prompts.EXTRACT_SYSTEM},
                {"role": "user", "content": prompts.build_extract_input(target_slot, conversation)},
            ],
            temperature=0.1,
            max_tokens=400,
        )
        return prompts.parse_extract(raw)

    def phrase_question(
        self,
        ptype: PersonaType,
        target_slot: SlotSpec,
        is_followup: bool,
        conversation: list[dict],
        known: dict | None = None,
    ) -> str:
        """겨냥된 슬롯을 존댓말 질문 한 문장으로. 스텁이면 씨앗 질문.

        known: 이미 확보한 정보(이름·집 등) — 질문에서 반복하지 않게 프롬프트에 반영.
        """
        if self.is_stub:
            return target_slot.question
        raw = self.chat(
            [
                {"role": "system", "content": prompts.PHRASE_SYSTEM},
                {"role": "user", "content": prompts.build_phrase_input(ptype, target_slot, is_followup, conversation, known)},
            ],
            temperature=0.4,
            max_tokens=160,
        )
        return prompts.clean_question(raw)

    # ── Phase 3 시민 제보 챗봇 ──────────────────────────────────────
    def structure_tip(self, text: str) -> dict:
        """구어체 시민 제보 → 구조화 데이터.

        반환: {location_text, time_text, appearance_cues, direction,
               travel_mode("walk"/"transit"/None), specificity("상"/"중"/"하")}.
        specificity 는 신뢰도 p 의 구체성 항 입력 — LLM 에 숫자를 직접 받지 않고
        상/중/하 등급만 받아 trust 가 고정값으로 매핑한다 (가드레일 패턴).
        스텁: 키워드 휴리스틱으로 필드 채움 비율 → 등급.
        """
        if self.is_stub:
            return _stub_structure_tip(text)
        raw = self.chat(
            [
                {"role": "system", "content": _TIP_STRUCTURE_SYSTEM},
                {"role": "user", "content": text},
            ],
            temperature=0.1,
            max_tokens=400,
        )
        try:
            data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        except (ValueError, json.JSONDecodeError):
            return _stub_structure_tip(text)   # 파싱 실패 → 휴리스틱 폴백
        level = data.get("specificity")
        return {
            "location_text": data.get("location_text"),
            "time_text": data.get("time_text"),
            "appearance_cues": data.get("appearance_cues") or [],
            "direction": data.get("direction"),
            "travel_mode": data.get("travel_mode") if data.get("travel_mode") in ("walk", "transit") else None,
            "specificity": level if level in ("상", "중", "하") else "중",
        }

    def next_tip_question(self, structured: dict, ask_travel_mode: bool = False) -> str | None:
        """제보 챗봇 다음 질문 — 고정 4개(위치·시각·인상착의·행동/방향)를 순서대로,
        확보 안 된 것부터. 4개가 다 차면 조건부 이동수단 질문(ask_travel_mode=True,
        제보 위치가 걷기 상한을 넘을 때만). 더 물을 게 없으면 None.
        """
        if not structured.get("location_text"):
            return _TIP_Q_LOCATION
        if not structured.get("time_text"):
            return _TIP_Q_TIME
        if not structured.get("appearance_cues"):
            return _TIP_Q_APPEARANCE
        if not structured.get("direction"):
            return _TIP_Q_DIRECTION
        if ask_travel_mode and not structured.get("travel_mode"):
            return _TIP_Q_TRAVEL_MODE
        return None


# ── Phase 3 제보 챗봇 — 질문 뱅크 (고정 4 + 조건부 이동수단) ────────────
_TIP_Q_LOCATION = "어디서 보셨어요? 근처 건물이나 가게 이름을 알려주세요."
_TIP_Q_TIME = "몇 시쯤이었을까요? 방금 전인가요, 아까쯤인가요?"
_TIP_Q_APPEARANCE = "무엇을 입고 있었는지, 어떤 모습이었는지 기억나세요?"
_TIP_Q_DIRECTION = "그때 뭘 하고 계셨나요? 어느 쪽으로 가셨어요?"
_TIP_Q_TRAVEL_MODE = "그분이 걸어가시던가요, 아니면 버스나 택시 같은 걸 타시던가요?"

_TIP_STRUCTURE_SYSTEM = """\
너는 실종자 목격 제보를 정리하는 보조원이다. 시민의 구어체 제보에서 아래를 뽑아 \
JSON 객체 하나만 출력한다 (JSON 밖 문장 금지). 없는 정보는 지어내지 말고 null.

- location_text: 목격 장소 (건물·가게·교차로 등), 없으면 null
- time_text: 목격 시각 표현 ("방금", "30분 전", "3시쯤"), 없으면 null
- appearance_cues: 옷차림·외모 단서 문자열 배열, 없으면 []
- direction: 이동 방향·행동 ("골목 쪽", "북쪽으로"), 없으면 null
- travel_mode: "walk"(걸어서) / "transit"(버스·택시·지하철) / null(불명)
- specificity: 제보의 구체성·일관성 등급 "상"/"중"/"하" 중 하나. \
장소·시각·외모가 모두 구체적이고 앞뒤가 맞으면 "상", 하나만 있거나 모호하면 "하"."""


def _stub_structure_tip(text: str) -> dict:
    """스텁·폴백 — 키워드 휴리스틱. LLM 없이 필드 채움 정도로 등급 근사."""
    cues = [k for k in ("점퍼", "셔츠", "바지", "모자", "치마", "코트", "운동화") if k in text]
    behavior = [k for k in ("울", "뛰", "헤매", "앉아", "두리번") if k in text]
    transit = "transit" if any(k in text for k in ("버스", "택시", "지하철", "전철")) else None
    filled = sum([
        any(k in text for k in ("역", "앞", "동", "로", "길", "편의점", "시장", "공원")),  # 장소 흔적
        any(k in text for k in ("분", "시", "방금", "아까", "전")),                        # 시각 흔적
        bool(cues),                                                                        # 외모
    ])
    level = "상" if filled >= 3 else ("중" if filled == 2 else "하")
    return {
        "location_text": None, "time_text": None,
        "appearance_cues": cues, "direction": behavior[0] if behavior else None,
        "travel_mode": transit, "specificity": level,
    }

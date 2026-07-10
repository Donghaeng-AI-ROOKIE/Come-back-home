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

    # ── Phase 3 시민 제보 (기존 스텁 유지) ──────────────────────────
    def structure_tip(self, text: str) -> dict:
        """구어체 시민 제보 → 구조화 데이터. (Phase 3 — 별도 연동)"""
        return {
            "location_text": None,
            "time_text": None,
            "behavior_cues": [k for k in ("울", "뛰", "헤매", "앉아") if k in text],
            "specificity": 0.5,
        }

    def ask_followup(self, tip_text: str) -> str:
        """제보자에게 던질 확인 질문 생성 (신뢰 온도 측정). (Phase 3)"""
        return "목격하신 정확한 위치와 시각, 그리고 옷차림을 기억나는 대로 알려주시겠어요?"

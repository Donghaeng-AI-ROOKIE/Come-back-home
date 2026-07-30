"""KT Mi:dm — Phase 0 온보딩 인터뷰 챗봇.

역할(노트 설계): '다음에 어느 슬롯을 물을지'는 검색(phase0.retrieval)이 정하고,
Mi:dm 은 그 슬롯을 (1) 자연스러운 존댓말 질문으로 문장화, (2) 직전 답변에서 슬롯값
추출 — 두 가지만 한다. 프롬프트는 phase0.prompts 참고.

Phase 3 시민 제보 구조화는 app.llm.tip_llm 으로 분리됨(2026-07-21) — 다턴 대화가
아니라 1회성 추출+분류라 온보딩 대화 전용 모델과 무게가 다른 모델을 쓸 수 있게.

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
        # 호출 실패 누적 — 아래 폴백들은 침묵하므로(빈 추출·씨앗 질문·휴리스틱),
        # 호출자가 이 카운터 증가로 장애를 감지해 세션에 노출한다(phase0.interview).
        self.call_failures = 0

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

        반환: {"fields", "attraction_points", "preferred_targets", "behavior_notes", "slot_filled"}.
        스텁 모드에서는 빈 추출(slot_filled=True 로 진행만 시킴).
        """
        if self.is_stub:
            return {"fields": {}, "attraction_points": [], "preferred_targets": [],
                    "behavior_notes": [], "slot_filled": True}
        try:
            raw = self.chat(
                [
                    {"role": "system", "content": prompts.EXTRACT_SYSTEM},
                    {"role": "user", "content": prompts.build_extract_input(target_slot, conversation)},
                ],
                temperature=settings.midm_temp_extract,
                max_tokens=400,
            )
        except Exception:  # noqa: BLE001 — 호출 실패(엔드포인트 만료 등)가 인터뷰를 죽이면 안 됨.
            # 빈 추출 + 미충족으로 처리 — 같은 슬롯을 한 번 더 묻고(MAX_ASKS_PER_SLOT),
            # 계속 실패하면 소진 처리돼 인터뷰가 진행된다.
            self.call_failures += 1
            return prompts.parse_extract("")
        return prompts.parse_extract(raw)

    def extract_correction(self, place_labels: list[str], utterance: str) -> dict:
        """요약 확인 단계의 '수정 요청' → {fields, place_ops}.

        일반 추출과 분리한 이유는 prompts.CORRECTION_SYSTEM 주석 참고 — 정정은 새
        사실 진술이 아니라 등록된 항목에 대한 변경 지시라 동작(op)이 필요하다.
        스텁·호출 실패는 빈 결과 → 호출부가 기존 슬롯 재추출 경로로 폴백한다.
        """
        if self.is_stub:
            return {"fields": {}, "place_ops": []}
        try:
            raw = self.chat(
                [
                    {"role": "system", "content": prompts.CORRECTION_SYSTEM},
                    {"role": "user", "content": prompts.CORRECTION_FEWSHOT_USER},
                    {"role": "assistant", "content": prompts.CORRECTION_FEWSHOT_ASSISTANT},
                    {"role": "user", "content": prompts.build_correction_input(
                        place_labels, utterance)},
                ],
                temperature=settings.midm_temp_correction,
                max_tokens=400,
            )
        except Exception:  # noqa: BLE001 — 정정 실패가 등록 흐름을 죽이면 안 된다
            self.call_failures += 1
            return {"fields": {}, "place_ops": []}
        return prompts.parse_correction(raw, place_labels)

    def phrase_question(
        self,
        ptype: PersonaType,
        target_slot: SlotSpec,
        is_followup: bool,
        conversation: list[dict],
        known: dict | None = None,
        collected: list[str] | None = None,
    ) -> str:
        """겨냥된 슬롯을 존댓말 질문 한 문장으로. 스텁이면 씨앗 질문.

        known: 이미 확보한 정보(이름·집 등) — 질문에서 반복하지 않게 프롬프트에 반영.
        collected: 이 슬롯에서 이미 확보한 사실 — 갭 기반 꼬리질문의 재료.
        """
        if self.is_stub:
            return target_slot.question
        try:
            raw = self.chat(
                [
                    {"role": "system", "content": prompts.PHRASE_SYSTEM},
                    {"role": "user", "content": prompts.build_phrase_input(
                        ptype, target_slot, is_followup, conversation, known, collected)},
                ],
                temperature=settings.midm_temp_phrase,
                max_tokens=160,
            )
        except Exception:  # noqa: BLE001 — 호출 실패 시 씨앗 질문으로 폴백 (스텁과 동일)
            self.call_failures += 1
            return target_slot.question
        return prompts.clean_question(raw)

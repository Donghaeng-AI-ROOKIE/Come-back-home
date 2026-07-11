"""LG EXAONE — Phase 2 동선 예측의 두뇌.

역할 (아키텍처 결정사항):
- Top-down: 페르소나 맥락을 읽어 prior(전략확률·끌림점 가중치·반경 파라미터)만 출력.
  좌표를 직접 예측하지 않는다 (LLM calibration 한계).
- 마음 예측: 혼란도·목적지 변경 등 심리 상태 추론. 마음이 바뀔 때만 호출.

서빙: OpenAI 호환 chat completions (Mi:dm 과 같은 규약). settings 에
exaone_base_url(endpoint URL) / exaone_model(endpoint ID) / exaone_api_key 를
채우면 chat() 실호출 가능, 비어 있으면 스텁 모드.
generate_prior / predict_mind 의 실프롬프트 연동은 별도 작업 — 여기는 연결 배관만.
"""

from __future__ import annotations

import json
import urllib.request

from app.config import settings
from app.llm.base import LLMClient
from app.schemas.persona import Persona, PersonaType
from app.schemas.prediction import LognormalParams, MindState, PriorParams
from app.schemas.report import MissingReport

# Koester 프로파일별 이동 거리 lognormal 파라미터 (km) — placeholder, ISRID 기반 튜닝 대상
_KOESTER_PARAMS: dict[PersonaType, LognormalParams] = {
    PersonaType.dementia: LognormalParams(mu=0.0, sigma=0.9),                 # 중앙값 ~1.0km
    PersonaType.child: LognormalParams(mu=-0.2, sigma=0.8),                   # 중앙값 ~0.8km
    PersonaType.intellectual_disability: LognormalParams(mu=0.2, sigma=1.0),  # 중앙값 ~1.2km
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

    def generate_prior(self, persona: Persona | None, report: MissingReport) -> PriorParams:
        """Few-shot CoT 로 개인 맥락 → prior 생성.

        스텁: 프로파일 통계 기본값 + 끌림점 균등 가중.
        실제 구현 시 페르소나의 behavior_notes 를 프롬프트에 넣어
        전략확률·끌림점 가중치를 개인화한다.
        """
        # TODO: API 연동 시 Few-shot CoT 프롬프트로 교체
        mtype = report.missing_type
        strategy = dict(_STRATEGY_PRIORS[mtype])

        attraction: dict[str, float] = {}
        if persona and persona.attraction_points:
            total = sum(p.weight for p in persona.attraction_points)
            attraction = {p.label: p.weight / total for p in persona.attraction_points}

        return PriorParams(
            strategy_probs=strategy,
            attraction_weights=attraction,
            radius_lognormal=_KOESTER_PARAMS[mtype],
            reasoning="[스텁] 프로파일 통계 기본값 사용 — EXAONE 연동 후 개인 맥락 반영",
        )

    def predict_mind(self, current: MindState, observations: list[str]) -> MindState:
        """마음 예측 — 상태 변화가 의심될 때만 호출된다 (비용 원칙).

        스텁: observations 에 심리 단서가 있으면 혼란도를 올리고 상태 변경.
        """
        # TODO: API 연동 시 EXAONE 추론으로 교체
        cues = [o for o in observations if any(k in o for k in ("울", "뛰", "헤매", "불안"))]
        if cues:
            return MindState(status="혼란 심화", confusion=min(1.0, current.confusion + 0.2), changed=True)
        return current.model_copy(update={"changed": False})

    def summarize_case(self, case_summary: str) -> str:
        """보호자·경찰용 수색 리포트 생성 (Solar Pro 와 협업)."""
        # TODO: API 연동
        return f"[스텁 리포트] {case_summary}"

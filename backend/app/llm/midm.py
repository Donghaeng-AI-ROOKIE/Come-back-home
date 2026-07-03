"""KT Mi:dm — Phase 0 온보딩 인터뷰 챗봇 + Phase 3 시민 제보 구조화."""

from app.config import settings
from app.llm.base import LLMClient

# 온보딩 인터뷰 질문 시퀀스 (스텁 — 실제로는 Mi:dm이 답변 맥락 따라 후속 질문 생성)
_INTERVIEW_QUESTIONS = [
    "안녕하세요, 돌아오길입니다. 등록하실 분의 성함과 나이를 알려주세요.",
    "어떤 유형이신가요? (치매 노인 / 아동 / 지적장애인)",
    "집 주소(또는 주로 머무는 곳)를 알려주세요.",
    "평소 자주 가시던 곳이나 특별히 애착이 있는 장소가 있나요? (옛 직장, 공원, 옛집 등)",
    "길을 잃으셨을 때 보였던 행동이나 습관이 있다면 알려주세요.",
    "감사합니다. 입력하신 정보로 페르소나를 등록할게요.",
]


class MidmClient(LLMClient):
    name = "KT Mi:dm"

    def __init__(self) -> None:
        super().__init__(settings.midm_api_key)

    def interview_turn(self, turn_index: int) -> tuple[str, bool]:
        """다음 인터뷰 질문 반환. (질문, 인터뷰 종료 여부)"""
        # TODO: API 연동 시 대화 맥락 기반 동적 질문 생성으로 교체
        if turn_index >= len(_INTERVIEW_QUESTIONS) - 1:
            return _INTERVIEW_QUESTIONS[-1], True
        return _INTERVIEW_QUESTIONS[turn_index], False

    def structure_tip(self, text: str) -> dict:
        """구어체 시민 제보 → 구조화 데이터.

        스텁: 키워드 기반 추출. 실제로는 Mi:dm이 위치·시각·행동 묘사를 파싱.
        """
        # TODO: API 연동
        return {
            "location_text": None,
            "time_text": None,
            "behavior_cues": [k for k in ("울", "뛰", "헤매", "앉아") if k in text],
            "specificity": 0.5,   # 제보가 얼마나 구체적인지 (신뢰도 p 산출에 사용)
        }

    def ask_followup(self, tip_text: str) -> str:
        """제보자에게 던질 확인 질문 생성 (신뢰 온도 측정)."""
        # TODO: API 연동
        return "목격하신 정확한 위치와 시각, 그리고 옷차림을 기억나는 대로 알려주시겠어요?"

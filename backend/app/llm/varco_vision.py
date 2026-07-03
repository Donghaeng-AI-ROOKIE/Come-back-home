"""NC VARCO-Vision — VLM. 생성이 아니라 추출·대조에 사용 (아키텍처 결정사항).

- Phase 1: 실종자 사진 → 인상착의 텍스트 추출
- Phase 3: 제보 사진 ↔ 실종자 사진 대조 → 유사도 (신뢰도 p 입력)
"""

from app.config import settings
from app.llm.base import LLMClient
from app.schemas.report import Appearance


class VarcoVisionClient(LLMClient):
    name = "NC VARCO-Vision"

    def __init__(self) -> None:
        super().__init__(settings.varco_api_key)

    def extract_appearance(self, image_bytes: bytes | None) -> Appearance:
        """사진에서 인상착의 추출."""
        # TODO: API 연동
        return Appearance(
            top="[스텁] 파란색 점퍼",
            bottom="[스텁] 회색 바지",
            shoes="[스텁] 흰색 운동화",
            physical="[스텁] 160cm 마른 체형, 흰머리",
            summary="[스텁] 파란 점퍼에 회색 바지, 흰 운동화 차림의 마른 체형 어르신",
        )

    def compare_photo(self, tip_image: bytes | None, reference: Appearance | None) -> float:
        """제보 사진과 실종자 인상착의 유사도 (0~1)."""
        # TODO: API 연동
        if tip_image is None:
            return 0.0
        return 0.85  # 스텁: 사진이 있으면 높은 유사도로 가정

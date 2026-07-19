"""NC VARCO-Vision — VLM. 생성이 아니라 추출에 사용 (아키텍처 결정사항).

- Phase 1: 실종자 사진 → 인상착의 텍스트 추출

시민 제보 사진 대조(Phase 3)는 하지 않기로 확정되어 제거됨.
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

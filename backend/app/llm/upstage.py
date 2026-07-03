"""Upstage Solar Pro — Phase 1 비정형 문서(신고서·진단서) 파싱."""

from app.config import settings
from app.llm.base import LLMClient
from app.schemas.report import ReporterInfo


class UpstageClient(LLMClient):
    name = "Upstage Solar Pro"

    def __init__(self) -> None:
        super().__init__(settings.upstage_api_key)

    def parse_document(self, file_bytes: bytes | None) -> ReporterInfo:
        """신고서 PDF/이미지 → 신고자 정보 추출."""
        # TODO: API 연동 (Document Parse)
        return ReporterInfo(
            name="[스텁] 김보호",
            relation="[스텁] 자녀",
            phone="[스텁] 010-0000-0000",
            extra={"note": "Upstage 연동 전 스텁 응답"},
        )

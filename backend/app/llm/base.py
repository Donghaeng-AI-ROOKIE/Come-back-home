"""모델 클라이언트 공통 베이스.

API 키가 비어 있으면 스텁 모드: 결정적인 가짜 응답을 돌려줘서
파이프라인 전체를 키 없이 end-to-end 로 돌릴 수 있다.
키 발급 후 각 클라이언트의 `_call_api` 만 구현하면 된다.
"""


class LLMClient:
    name: str = "base"

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key

    @property
    def is_stub(self) -> bool:
        return not self.api_key

    def _call_api(self, prompt: str, **kwargs) -> str:
        # TODO: API 키 발급 후 모델별 실제 HTTP 호출 구현
        raise NotImplementedError(f"{self.name} 실제 API 연동 미구현 (스텁 모드로 사용하세요)")

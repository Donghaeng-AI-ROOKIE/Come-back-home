from app.llm.copy_llm import CopyLLMClient
from app.llm.exaone import ExaoneClient
from app.llm.midm import MidmClient
from app.llm.tip_llm import TipLLMClient
from app.llm.upstage import UpstageClient
from app.llm.varco_vision import VarcoVisionClient

# 전역 싱글턴 — API 키가 들어오면 각 클라이언트 내부에서 실제 호출로 전환
exaone = ExaoneClient()
midm = MidmClient()
tip_llm = TipLLMClient()
copy_llm = CopyLLMClient()
varco = VarcoVisionClient()
upstage = UpstageClient()

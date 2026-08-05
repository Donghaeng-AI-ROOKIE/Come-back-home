"""테스트는 항상 스텁 모드 — .env 의 실키가 테스트에 새어들지 않게 차단.

pydantic-settings 는 프로세스 환경변수를 .env 파일보다 우선하므로, app.config
가 임포트되기 전에(conftest 는 테스트 모듈보다 먼저 로드된다) 빈 값으로
덮어쓴다. USE_ROADNET 을 .env 에 넣지 않는 것과 같은 원칙 — 테스트는 로컬
크리덴셜 유무와 무관하게 결정론적이어야 하고, 네트워크로 LLM 을 부르면 안 된다.
"""

import os

for _key in (
    "EXAONE_API_KEY", "EXAONE_BASE_URL", "EXAONE_MODEL",
    "MIDM_API_KEY", "MIDM_BASE_URL", "MIDM_MODEL",
):
    os.environ[_key] = ""

# bool 필드라 pydantic-settings 가 "" 파싱에 실패한다 — 위 문자열 키들과 달리
# 반드시 "false" 로 강제한다. .env 에서 USE_ROADNET=true 를 켜도 테스트는 항상
# 오프라인(연속공간 폴백)이어야 한다 — Overpass/OSM 라이브 호출 금지.
os.environ["USE_ROADNET"] = "false"

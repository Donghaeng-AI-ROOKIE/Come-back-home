"""테스트는 항상 스텁 모드 — .env 의 실키가 테스트에 새어들지 않게 차단.

pydantic-settings 는 프로세스 환경변수를 .env 파일보다 우선하므로, app.config
가 임포트되기 전에(conftest 는 테스트 모듈보다 먼저 로드된다) 빈 값으로
덮어쓴다. USE_ROADNET 을 .env 에 넣지 않는 것과 같은 원칙 — 테스트는 로컬
크리덴셜 유무와 무관하게 결정론적이어야 하고, 네트워크로 LLM 을 부르면 안 된다.
"""

import os
from pathlib import Path

for _key in (
    "EXAONE_API_KEY", "EXAONE_BASE_URL", "EXAONE_MODEL",
    "MIDM_API_KEY", "MIDM_BASE_URL", "MIDM_MODEL",
):
    os.environ[_key] = ""

# bool 필드라 pydantic-settings 가 "" 파싱에 실패한다 — 위 문자열 키들과 달리
# 반드시 "false" 로 강제한다. .env 에서 USE_ROADNET=true 를 켜도 테스트는 항상
# 오프라인(연속공간 폴백)이어야 한다 — Overpass/OSM 라이브 호출 금지.
os.environ["USE_ROADNET"] = "false"

# 저장소 영속화도 항상 끈다. 켜 두면 테스트가 실제 SQLite 파일을 공유해 서로의
# 상태를 오염시키고, 실행 순서에 따라 결과가 바뀐다(디스크에 남은 페르소나가
# 다음 테스트에서 조회되는 식). 영속화 자체의 검증은 test_storage_persist.py 가
# 임시 경로로 직접 켜서 한다.
os.environ["PERSIST_STORAGE"] = "false"

# 감사로그 파일도 테스트 전용 경로로 돌린다.
#
# 이건 편의가 아니라 **증적의 무결성 문제**다. 파기 증적은 "언제 무엇을 지웠다"를
# 증명하는 기록인데, 테스트가 만든 가짜 파기 기록(persona_purged persist-1 …)이
# 같은 파일에 섞이면 증적으로서 신뢰할 수 없게 된다. 2026-08-05 실제로 운영
# 파일에서 테스트 유래 12행이 발견됐다.
#
# 파일 자체는 남지만 tests/ 아래라 커밋되지 않고(.gitignore), 운영 경로와 섞이지
# 않는다.
os.environ["PRIVACY_AUDIT_PATH"] = str(
    Path(__file__).resolve().parent / ".pytest_audit.jsonl")

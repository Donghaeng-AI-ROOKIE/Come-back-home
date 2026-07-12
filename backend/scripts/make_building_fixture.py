"""테스트용 건물 높이 레이어 fixture 생성 — 정릉동 반경 800m 건물 전체.

도로망·환경 레이어 fixture 와 동일 중심점/반경을 사용한다. 테스트는 이 파일만
읽으므로 외부 서버를 치지 않는다.

실행 (backend/ 에서):
  python scripts/make_building_fixture.py
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.geo import envlayer  # noqa: E402
from app.schemas.common import GeoPoint  # noqa: E402

FIXDIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
CENTER = GeoPoint(lat=37.6061, lng=127.0106)  # 도로망·환경 레이어 fixture 와 동일
RADIUS_M = 800

from app.config import settings  # noqa: E402

# 캐시를 지우고 재조회 — 파서 코드를 고친 뒤 재생성할 때 옛 캐시가 그대로
# fixture 로 복사되는 것을 방지 (buildings_with_height 는 캐시 우선이므로)
cache = Path(settings.roadnet_cache_dir) / f"buildings_{CENTER.lat:.4f}_{CENTER.lng:.4f}_{RADIUS_M}.json"
if cache.exists():
    cache.unlink()
    print(f"기존 캐시 삭제: {cache}")

t = time.time()
buildings = envlayer.buildings_with_height(CENTER, RADIUS_M)
print(f"건물 폴리곤 {len(buildings)}개 조회 완료 ({time.time() - t:.1f}s)")
if not buildings:
    sys.exit("조회 실패 또는 건물 0개 — fixture 를 덮어쓰지 않고 중단")

out = FIXDIR / "jeongneung_buildings_800m.json"
out.write_text(json.dumps(buildings, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"저장 완료: {out}")

with_height = sum(1 for b in buildings if b["height_m"] is not None)
with_levels = sum(1 for b in buildings if b["levels"] is not None)
print(f"높이 확보: {with_height}/{len(buildings)} (levels 태그 보유: {with_levels}개)")

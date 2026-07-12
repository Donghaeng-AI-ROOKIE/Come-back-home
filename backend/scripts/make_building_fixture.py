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

t = time.time()
buildings = envlayer.buildings_with_height(CENTER, RADIUS_M)
print(f"건물 {len(buildings)}개 조회 완료 ({time.time() - t:.1f}s)")

out = FIXDIR / "jeongneung_buildings_800m.json"
out.write_text(json.dumps(buildings, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"저장 완료: {out}")

with_height = sum(1 for b in buildings if b["height_m"] is not None)
from_tag = sum(1 for b in buildings if b["height_m"] is not None and b["levels"] is None)
print(f"높이 있는 건물: {with_height}/{len(buildings)} (height 태그 직접: {from_tag}개)")

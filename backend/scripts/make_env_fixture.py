"""테스트용 환경 레이어 fixture 생성 — 정릉동 도로망 fixture 노드들의 env dict.

도로망 fixture(jeongneung_walk_800m.graphml)의 668개 노드에 대해
OSM 태그 거리 + EGIS 토지피복 분류를 실제 API 로 계산하고 JSON 으로 저장한다.
테스트는 이 파일만 읽으므로 외부 서버를 치지 않는다.

실행 (backend/ 에서):
  python scripts/make_env_fixture.py
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.geo import envlayer  # noqa: E402
from app.geo.roadnet import OSMnxNetwork  # noqa: E402
from app.schemas.common import GeoPoint  # noqa: E402

FIXDIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
CENTER = GeoPoint(lat=37.6061, lng=127.0106)  # 도로망 fixture 와 동일
RADIUS_M = 800

net = OSMnxNetwork.from_graphml(FIXDIR / "jeongneung_walk_800m.graphml")
print(f"도로망 fixture 로드: {len(net.graph.nodes)}노드")

t = time.time()
env: dict[int, dict] = {n: {} for n in net.graph.nodes}
envlayer._attach_osm_distances(net, env, CENTER, RADIUS_M)
print(f"OSM 태그 거리 계산 완료 ({time.time() - t:.1f}s)")

t = time.time()
stats = envlayer._attach_landcover(net, env)
print(f"EGIS 토지피복 분류 완료 ({time.time() - t:.1f}s) — {stats}")

out = FIXDIR / "jeongneung_env_800m.json"
out.write_text(json.dumps(env, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"저장 완료: {out}")

# 요약 출력 — 사람이 훑어보고 상식 검증
from collections import Counter  # noqa: E402 — 픽스처 생성 후 요약 전용

lc = Counter(v.get("landcover_l3") for v in env.values())
print("피복 세분류 분포:", dict(lc.most_common(8)))
water_near = sum(1 for v in env.values() if v.get("water_m") is not None and v["water_m"] < 100)
print(f"물가 100m 이내 노드: {water_near}개")

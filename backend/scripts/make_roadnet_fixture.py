"""테스트용 도로망 fixture 생성 — 정릉동 데모 LKP 반경 800m 보행 그래프.

테스트가 매번 외부 서버(Overpass)를 치면 느리고 불안정하므로,
작은 그래프를 한 번 받아 GraphML 로 저장해두고 테스트는 이 파일만 읽는다.

실행 (backend/ 에서):
  python scripts/make_roadnet_fixture.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import osmnx as ox  # noqa: E402

# seed.py 데모 케이스(정릉동 김순자)의 LKP 와 동일 좌표
LAT, LNG = 37.6061, 127.0106
RADIUS_M = 800

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "jeongneung_walk_800m.graphml"

print(f"Overpass 에서 ({LAT}, {LNG}) 반경 {RADIUS_M}m 보행 그래프 다운로드 중...")
G = ox.graph_from_point((LAT, LNG), dist=RADIUS_M, network_type="walk")
OUT.parent.mkdir(parents=True, exist_ok=True)
ox.save_graphml(G, OUT)
print(f"저장 완료: {OUT}")
print(f"노드 {len(G.nodes)}개 / 엣지 {len(G.edges)}개")

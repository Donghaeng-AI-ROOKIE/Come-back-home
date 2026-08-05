"""도로망 캐시 예열 — 시연 전에 콜드 다운로드를 미리 끝내 둔다.

## 왜 필요한가

`use_roadnet` 기본값이 `True` 로 바뀌면서(PR #122) **캐시에 없는 좌표의 첫 예측이
Overpass 라이브 다운로드를 탄다 — 실측 15~110초.** 그동안 예측은 멈춰 있고, 시간이
초과되면 `pipeline._load_roadnet` 이 조용히 연속 공간 폴백으로 내려앉는다. 시연에서
이게 터지면 "느리다"가 아니라 "도로망을 안 쓴 예측"이 나간다.

캐시 키는 **좌표(소수 4자리) + 반경**이다(`roadnet.get_network`). 반경은 고정이
아니라 prior·경과시간으로 정해지고 1km 올림 양자화되므로, 같은 LKP 라도 경과시간에
따라 3·4·5·6km 중 다른 것을 요구한다. **3km 만 받아 두면 6h 예측에서 또 콜드가 난다.**
그래서 좌표당 네 반경을 전부 받는다.

## 사용

    cd backend
    # 시연 좌표(정릉) 예열
    python -m scripts.warm_roadnet 37.6061,127.0106

    # 여러 좌표 · 환경레이어까지
    python -m scripts.warm_roadnet 37.6061,127.0106 37.5665,126.9780 --env

    # 이미 받은 것만 확인 (다운로드 없음)
    python -m scripts.warm_roadnet 37.6061,127.0106 --check

환경레이어(`--env`)는 별도 캐시다. 게이지·트리거가 쓰는 환경 속성이라 예열해 두면
첫 예측이 더 빨라진다. 실패해도 도로망은 유효하므로 경고만 남긴다.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.schemas.common import GeoPoint


# 동적 반경이 실제로 낼 수 있는 값 전부 (radius.roadnet_radius_m 의 1km 양자화 결과).
# 하한·상한이 설정에서 오므로 여기서 다시 계산한다 — 설정을 바꾸면 같이 따라간다.
def radii() -> list[int]:
    lo = settings.roadnet_radius_m
    hi = settings.roadnet_radius_max_m
    step = 1000
    first = (lo + step - 1) // step * step
    return list(range(max(first, lo), hi + 1, step)) or [lo]


def cache_path(center: GeoPoint, r: int) -> Path:
    """`roadnet.OSMnxNetwork.load` 가 쓰는 파일명 규칙과 같아야 한다."""
    return (Path(settings.roadnet_cache_dir)
            / f"walk_{center.lat:.4f}_{center.lng:.4f}_{r}.graphml")


def parse_point(s: str) -> GeoPoint:
    lat, lng = (float(x) for x in s.split(","))
    return GeoPoint(lat=lat, lng=lng)


def main() -> int:
    ap = argparse.ArgumentParser(description="도로망 캐시 예열 (시연 전 콜드 다운로드 방지)")
    ap.add_argument("points", nargs="+", metavar="LAT,LNG",
                    help="예열할 좌표. 시연에서 쓸 LKP 를 넣는다.")
    ap.add_argument("--env", action="store_true", help="환경레이어(EGIS)도 함께 예열")
    ap.add_argument("--check", action="store_true", help="다운로드 없이 캐시 유무만 확인")
    args = ap.parse_args()

    pts = [parse_point(p) for p in args.points]
    rs = radii()
    print(f"좌표 {len(pts)}개 × 반경 {rs} = {len(pts) * len(rs)}건")

    if args.check:
        missing = 0
        for c in pts:
            for r in rs:
                p = cache_path(c, r)
                ok = p.exists()
                missing += 0 if ok else 1
                print(f"  {'✅' if ok else '❌'} {c.lat:.4f},{c.lng:.4f} r={r}")
        print(f"\n미보유 {missing}건" if missing else "\n전부 캐시됨 — 콜드 다운로드 없음")
        return 1 if missing else 0

    # 지연 임포트 — --check 는 osmnx 없이도 돌게 한다.
    from app.geo import roadnet

    failed = 0
    for c in pts:
        for r in rs:
            if cache_path(c, r).exists():
                print(f"  · {c.lat:.4f},{c.lng:.4f} r={r} 이미 있음")
                continue
            t = time.perf_counter()
            try:
                net = roadnet.get_network(c, radius_m=r)
                print(f"  ✅ {c.lat:.4f},{c.lng:.4f} r={r} "
                      f"nodes={len(net.graph.nodes)} ({time.perf_counter() - t:.1f}s)")
            except Exception as e:  # noqa: BLE001 — 한 건 실패가 나머지를 막지 않는다
                failed += 1
                print(f"  ❌ {c.lat:.4f},{c.lng:.4f} r={r} 실패 ({time.perf_counter() - t:.1f}s): {e}")
                continue
            if args.env:
                try:
                    from app.geo import envlayer

                    envlayer.attach(net, c, radius_m=r)
                    print("     환경레이어 부착됨")
                except Exception as e:  # noqa: BLE001 — 환경레이어는 도로망을 죽이지 않는다
                    print(f"     ⚠️ 환경레이어 실패(도로망은 유효): {e}")

    print(f"\n{'실패 ' + str(failed) + '건 — 다시 실행하면 성공분은 건너뛴다' if failed else '예열 완료'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

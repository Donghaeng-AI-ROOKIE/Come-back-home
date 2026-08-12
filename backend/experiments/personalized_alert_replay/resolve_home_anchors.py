"""Kakao 키 없이 합성 페르소나의 의도된 집 지역을 OSM으로 고정한다."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from app.geo.geocode import KakaoGeocoder, NominatimGeocoder
from experiments.personalized_alert_replay.build_persona_bank import load_profiles

HERE = Path(__file__).resolve().parent
QUERY_OVERRIDES = {
    "SP07": "보문동주민센터 서울",
    "SP08": "동선동주민센터 서울",
    "SP09": "삼선동주민센터 서울",
    "SP10": "종암동주민센터 서울",
}


def _query(home_area: str) -> str:
    return home_area.removesuffix(" 근처").strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("kakao", "osm"), default="kakao")
    parser.add_argument("--out", default="")
    parser.add_argument("--delay", type=float, default=1.1, help="Nominatim 요청 간격(초)")
    args = parser.parse_args()
    if args.provider == "kakao":
        key = os.environ.get("KAKAO_REST_KEY", "").strip()
        if not key:
            raise SystemExit(
                "KAKAO_REST_KEY가 없습니다. 터미널 환경에 설정한 후 다시 실행하세요."
            )
        geocoder = KakaoGeocoder(key, timeout=15)
    else:
        geocoder = NominatimGeocoder(timeout=15)
    profiles = load_profiles()
    rows = []
    for index, profile in enumerate(profiles):
        query = (_query(profile.home_area) if args.provider == "kakao"
                 else QUERY_OVERRIDES.get(profile.profile_id, _query(profile.home_area)))
        result = geocoder.locate(query)
        if result is None:
            raise RuntimeError(f"{profile.profile_id}: OSM 미탐 {query!r}")
        rows.append({
            "profile_id": profile.profile_id,
            "intended_home_area": profile.home_area,
            "query": query,
            "home": result.point.model_dump(),
            "precision": result.precision,
            "source": result.source,
            "matched": result.matched,
        })
        print(
            f"{profile.profile_id} {result.point.lat:.7f},{result.point.lng:.7f} "
            f"{result.matched}", flush=True,
        )
        if args.provider == "osm" and index + 1 < len(profiles):
            time.sleep(args.delay)
    filename = args.out or f"home_anchors_{args.provider}.json"
    out = HERE / filename
    out.write_text(json.dumps({
        "schema_version": 1,
        "provider": args.provider,
        "homes": rows,
    }, ensure_ascii=False, indent=2)
                   + "\n", encoding="utf-8")
    print(f"saved={out} n={len(rows)}")


if __name__ == "__main__":
    main()

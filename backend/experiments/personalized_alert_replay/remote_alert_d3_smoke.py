"""공식 배포에서 인앱 경보와 표준 제보 기반 D3 흐름을 1회 검증한다."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone

from app.geo.roadnet import OSMnxNetwork
from experiments.personalized_alert_replay.remote_live_replay import (
    Api,
    BASE_DEFAULT,
    GRAPHML,
    OUT_DIR,
    _cleanup,
    _persona_payload,
)
from experiments.personalized_alert_replay.truth_routes import build_scenarios


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--allow-public-alert",
        action="store_true",
        help="훈련 namespace가 격리된 경우에만 공개 경보 목록 시딩 허용",
    )
    args = parser.parse_args()
    if args.base.rstrip("/") == BASE_DEFAULT and not args.allow_public_alert:
        raise SystemExit(
            "공식 배포는 훈련 경보가 일반 /phase3/alerts에 노출될 수 있어 차단됨. "
            "training namespace/화이트리스트 격리 후에만 --allow-public-alert 사용."
        )
    api = Api(args.base)
    net = OSMnxNetwork.from_graphml(GRAPHML)
    scenario = next(
        s for s in build_scenarios(net.graph, per_stratum=2, fixed_start=True)
        if s.scenario_id == "neutral-00"
    )
    persona_id = case_id = None
    result: dict = {}
    try:
        persona = api.request("POST", "/phase0/personas", _persona_payload(scenario, True))
        persona_id = persona["id"]
        lkp_time = (
            datetime.now(timezone.utc) - timedelta(minutes=scenario.missing_before_report_min)
        ).replace(microsecond=0).isoformat()
        case = api.request("POST", "/phase1/reports", {
            "missing_type": "dementia",
            "lkp": {"lat": scenario.start.lat, "lng": scenario.start.lng},
            "lkp_time": lkp_time,
            "persona_id": persona_id,
            "situation": "[훈련] 인앱 경보·D3 실험. 실제 실종 사건 아님.",
        })
        case_id = case["id"]
        prediction = api.request("POST", f"/phase2/cases/{case_id}/predict?seed=42", timeout=300)

        issued = api.request("POST", f"/phase3/cases/{case_id}/alerts", timeout=30)
        seeded = api.request("GET", f"/phase1/cases/{case_id}", timeout=30)

        poll_started = time.perf_counter()
        active = api.request("GET", "/phase3/alerts", timeout=30)
        poll_ms = round((time.perf_counter() - poll_started) * 1000.0, 1)
        visible = next((alert for alert in active if alert["case_id"] == case_id), None)

        seen_at = (datetime.now(timezone.utc) - timedelta(minutes=5)) \
            .replace(microsecond=0).isoformat()
        tip = api.request("POST", f"/phase3/cases/{case_id}/tips", {
            "text": "[훈련] 5분 전 시장 입구에서 빨간 상의의 노인이 큰길 쪽으로 걷는 것을 봤습니다.",
            "location": {"lat": scenario.attraction.lat, "lng": scenario.attraction.lng},
            "seen_at": seen_at,
            "force": False,
        }, timeout=300)
        updated = api.request("GET", f"/phase1/cases/{case_id}", timeout=30)

        result = {
            "case_visible_in_app_poll": visible is not None,
            "poll_http_ms": poll_ms,
            "alert_issue_response": issued,
            "os_push_sent": bool(issued.get("sent")),
            "prior_source": prediction["prior"].get("source"),
            "roadnet_used": bool(updated.get("roadnet_used")),
            "tip_decision": tip.get("decision"),
            "tip_p": tip.get("p"),
            "lkp_moved_to_tip": (
                abs(updated["lkp"]["lat"] - scenario.attraction.lat) < 1e-7
                and abs(updated["lkp"]["lng"] - scenario.attraction.lng) < 1e-7
            ),
            "d3_last_alert_advanced": (
                bool(seeded.get("last_alert_at"))
                and bool(updated.get("last_alert_at"))
                and updated["last_alert_at"] != seeded["last_alert_at"]
            ),
            "seed_last_alert_at": seeded.get("last_alert_at"),
            "updated_last_alert_at": updated.get("last_alert_at"),
            "cleanup_errors": [],
        }
    finally:
        errors = _cleanup(api, persona_id, case_id)
        result["cleanup_errors"] = errors
        OUT_DIR.mkdir(exist_ok=True)
        out = OUT_DIR / "remote_alert_d3_smoke.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"saved={out}")


if __name__ == "__main__":
    main()

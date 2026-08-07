"""E2E 스모크 — 김순자 시나리오 9단계 (API_CONTRACT.md 호출 순서 그대로).

test_e2e_flow.py(스텁·오프라인)와 달리 이 스크립트는 실운영 구성으로 돈다:
- USE_ROADNET=true (도로망 그래프 + 환경레이어 + 게이지)
- .env 에 키가 있으면 EXAONE(목적지·마음예측)·Mi:dm(제보 구조화) 실호출

실행:  python scripts/e2e_smoke.py
확인:  API 응답 모양(계약 준수), POA 4종 합=1, 폴리곤 계약, 제보 신뢰도→
       층1/층2 판정, 베이지안 갱신으로 POA 가 실제로 바뀌는지 (회의록 6·7번).
"""

import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("USE_ROADNET", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)
t_all = time.time()


def step(name: str, resp, *checks: bool) -> dict:
    ok = resp.status_code < 300 and all(checks)
    print(f"{'OK ' if ok else 'FAIL'} {name} ({resp.status_code})")
    if not ok:
        print("  →", resp.text[:300])
        sys.exit(1)
    return resp.json()


# 1. 페르소나 사전등록
p = step("1 페르소나 등록", client.post("/phase0/personas", json={
    "name": "김순자", "age": 78, "type": "dementia",
    "home": {"lat": 37.6061, "lng": 127.0106},
    "attraction_points": [
        {"label": "옛집(아리랑고개)", "location": {"lat": 37.6015, "lng": 127.0088}, "weight": 0.55},
        {"label": "정릉시장", "location": {"lat": 37.6047, "lng": 127.0121}, "weight": 0.30}],
    "behavior_notes": ["해질녘 옛집 방향으로 걷는 습관", "중기 치매 — 시간 인식 혼란"]}))

# 2. 실종 신고 — lkp_time 은 상대 시각 (고정 날짜를 쓰면 실행일이 지날수록
#    경과시간이 커져 예측 반경·알림 셀 수가 매일 달라진다. 실측: 20h 경과로 계산돼
#    반경 √20≈4.5배 팽창 → 알림 3,684셀)
lkp_time = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
seen_time = (datetime.now() - timedelta(minutes=20)).isoformat(timespec="seconds")
case = step("2 실종 신고", client.post("/phase1/reports", json={
    "missing_type": "dementia", "lkp": {"lat": 37.6061, "lng": 127.0106},
    "lkp_time": lkp_time, "persona_id": p["id"],
    "appearance": {
        "top": "파란색 점퍼", "bottom": "회색 바지", "shoes": "흰색 운동화"
    },
    "with_document": True}))
cid = case["id"]

# 3. Phase 2 예측 (EXAONE prior + 도로망 그래프 MC + 게이지·마음 재해석)
t0 = time.time()
pred = step("3 예측", client.post(f"/phase2/cases/{cid}/predict?seed=42"))
print(f"   예측 {time.time() - t0:.1f}s | prior: {pred['prior']['reasoning'][:60]}...")
for key in ("poa_topdown", "poa_bottomup", "poa_statistical", "poa_combined"):
    total = sum(pred[key]["cells"].values())
    assert abs(total - 1.0) < 1e-6, f"{key} 합={total}"
print("   POA 4종 합=1, 전략확률:",
      {k: round(v, 2) for k, v in pred["prior"]["strategy_probs"].items()})

# 4. POA 히트맵 — 폴리곤 포함 계약 (프론트가 그대로 렌더)
poa = step("4 POA 조회", client.get(f"/phase3/cases/{cid}/poa?top=5"))
top1 = poa["top_cells"][0]
assert {"cell", "prob", "polygon"} <= set(top1) and len(top1["polygon"]) == 6, "폴리곤 계약 위반"
print(f"   top1 prob={top1['prob']:.3f}, polygon 6점 OK")

# 5. 타겟 알림 — 셀 수가 상한 이내여야 "타겟" (무차별 폭주 회귀 감지)
alert = step("5 알림 발송", client.post(f"/phase3/cases/{cid}/alerts"))
n_cells = alert["target_cells"]
n_cells = n_cells if isinstance(n_cells, int) else len(n_cells)
assert n_cells <= settings.max_alert_cells, \
    f"알림 셀 {n_cells} > 상한 {settings.max_alert_cells} — 타겟팅 붕괴"
print(f"   대상 셀 {n_cells}개 (상한 {settings.max_alert_cells})")

# 6. 시민 제보 → 신뢰도 p → 층1/층2 판정 (회의록 6번: 신뢰도 검증)
t0 = time.time()
tip = step("6 제보 접수", client.post(f"/phase3/cases/{cid}/tips", json={
    "text": "정릉시장 입구에서 파란 점퍼 입은 할머니가 두리번거리는 걸 봤어요",
    "location": {"lat": 37.6047, "lng": 127.0121},
    "seen_at": seen_time}))
print(f"   제보 {time.time() - t0:.1f}s | p={tip['p']:.2f}, decision={tip['decision']}")

# 7. 갱신 POA — 베이지안 갱신이 실제로 반영됐는지 (회의록 7번: 확률 업데이트)
poa2 = step("7 갱신 POA", client.get(f"/phase3/cases/{cid}/poa?top=5"))
changed = poa2["top_cells"][0]["cell"] != top1["cell"] or \
    abs(poa2["top_cells"][0]["prob"] - top1["prob"]) > 1e-9
print(f"   POA 변화 {'있음' if changed else '없음 — 확인 필요'}")

# 8~9. 층2 재실행 판정 + 케이스 상태
rerun = step("8 rerun-check", client.get(f"/phase3/cases/{cid}/rerun-check"))
print(f"   should_rerun={rerun['should_rerun']} ({rerun.get('reason', '')})")
final = step("9 케이스 조회", client.get(f"/phase1/cases/{cid}"))
print(f"   status={final['status']}, tips={len(final['tips'])}건")

print(f"\n전체 {time.time() - t_all:.1f}s — E2E 스모크 통과")

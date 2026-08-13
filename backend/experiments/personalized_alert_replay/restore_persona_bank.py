"""커밋된 Mi:dm 등록 스냅샷에서 Persona를 배포 백엔드로 복원한다.

배포 백엔드는 메모리 저장소라 재시작하면 Persona가 사라진다(2026-08-13에
v1 페르소나 10명 전원 404 확인). Mi:dm 을 다시 호출하면 v1과 다른 페르소나가
되므로, 인터뷰 결과 스냅샷을 그대로 다시 심어 조건 동일성을 지킨다.

복원 후 새 persona_id 매핑을 매니페스트로 저장한다.

    python -m experiments.personalized_alert_replay.restore_persona_bank \
        --base https://macmini.tail67859f.ts.net:8443 \
        --out persona_bank_manifest_v2.json
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SNAPSHOT = HERE / "results/persona_bank_midm-bank-v2-final-20260812.jsonl"
# Persona 생성 API가 받는 필드만 추린다. id·axis_scoring_report 등 서버가
# 다시 만드는 값은 보내지 않는다.
CREATE_FIELDS = (
    "type", "name", "age", "home", "attraction_points", "behavior_notes",
    "axis_evidence", "axis_scores", "route_familiarity", "env_responses",
)


def _post(base: str, path: str, body: dict, timeout: float = 60.0) -> dict:
    request = urllib.request.Request(
        base.rstrip("/") + path,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _get(base: str, path: str, timeout: float = 30.0) -> dict:
    with urllib.request.urlopen(base.rstrip("/") + path, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="https://macmini.tail67859f.ts.net:8443")
    parser.add_argument("--out", default="persona_bank_manifest_v2.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    rows = [json.loads(line) for line in
            SNAPSHOT.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"스냅샷 {len(rows)}명: {[r['profile_id'] for r in rows]}")

    restored = []
    for row in rows:
        persona = row["persona"]
        payload = {k: persona[k] for k in CREATE_FIELDS if k in persona}
        if args.dry_run:
            print(f"  [dry-run] {row['profile_id']} 필드={sorted(payload)}")
            continue
        try:
            created = _post(args.base, "/phase0/personas", payload)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:300]
            print(f"  {row['profile_id']} 실패 HTTP {exc.code}: {body}")
            return 1
        new_id = created["id"]
        # 저장된 내용이 스냅샷과 맞는지 즉시 검증 — 이름·끌림점 개수·축 점수 유무
        check = _get(args.base, f"/phase0/personas/{new_id}")
        ok = (
            check.get("name") == persona.get("name")
            and len(check.get("attraction_points") or []) == len(persona.get("attraction_points") or [])
        )
        print(f"  {row['profile_id']}: {row['persona_id']} → {new_id} "
              f"(끌림점 {len(check.get('attraction_points') or [])}, 검증 {'OK' if ok else '불일치'})")
        if not ok:
            print("    스냅샷과 저장 결과가 다르다 — 중단")
            return 1
        restored.append({
            "profile_id": row["profile_id"],
            "persona_id": new_id,
            "v1_persona_id": row["persona_id"],
        })

    if args.dry_run:
        return 0

    manifest = {
        "schema_version": 1,
        "run_id": "v2-restored-from-snapshot",
        "source": "restore_persona_bank.py (스냅샷 재이식, Mi:dm 재호출 없음)",
        "snapshot": SNAPSHOT.name,
        "personas": restored,
    }
    out = HERE / args.out
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"저장됨: {out} ({len(restored)}명)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

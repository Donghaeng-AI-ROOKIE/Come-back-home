"""이미 등록된 페르소나에 **주인(guardian_id)** 을 붙인다 — 1회성 마이그레이션.

## 왜 필요한가
가족 목록을 소유자별로 가르면서(`GET /phase0/personas?guardian_id=`),
소유자가 비어 있는 예전 페르소나는 **아무에게도 안 보이게** 됐다. "빈 소유자는
전원 공개" 같은 예외를 두면 필터를 넣으나 마나가 되므로, 예외 대신 이 스크립트로
주인을 붙인다.

## 쓰는 법 (맥미니, 백엔드 컨테이너 안에서)
    # 1) 먼저 무엇이 바뀌는지만 본다 — 기본이 미리보기다
    docker exec come-back-home-backend-1 python scripts/assign_persona_owner.py --owner u-XXXX

    # 2) 확인했으면 --apply 를 붙여 실제로 쓴다
    docker exec come-back-home-backend-1 python scripts/assign_persona_owner.py --owner u-XXXX --apply

    # 소유자가 비어 있는 것만 옮기고 싶으면
    ... --owner u-XXXX --only-empty --apply

**미리보기가 기본이다.** 남의 데이터를 조용히 옮기는 스크립트가 되면 안 된다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import storage


def main() -> int:
    ap = argparse.ArgumentParser(description="페르소나 소유자 일괄 지정")
    ap.add_argument("--owner", required=True, help="새 주인의 계정 id (예: u-d08ba6c18cd3)")
    ap.add_argument("--only-empty", action="store_true",
                    help="guardian_id 가 비어 있는 것만 옮긴다(다른 사람 것은 건드리지 않음)")
    ap.add_argument("--apply", action="store_true", help="실제로 저장한다(없으면 미리보기)")
    args = ap.parse_args()

    rows = storage.personas.list()
    targets = [p for p in rows
               if p.guardian_id != args.owner
               and (not args.only_empty or not p.guardian_id)]

    print(f"전체 {len(rows)}건 중 대상 {len(targets)}건 → 주인을 '{args.owner}' 로")
    for p in targets:
        print(f"  {p.id}  {p.name:8s} {p.age}세   {p.guardian_id or '(주인없음)'} → {args.owner}")
    if not targets:
        print("바꿀 것이 없습니다.")
        return 0

    if not args.apply:
        print("\n미리보기입니다. 실제로 쓰려면 --apply 를 붙이세요.")
        return 0

    for p in targets:
        # model_copy(update=) 는 검증을 건너뛴다 — 끌림점·집이 dict 로 박혀 예측이
        # 죽는다(PR #182). 필드를 직접 바꾸고 저장한다.
        p.guardian_id = args.owner
        storage.personas.save(p.id, p)
    print(f"\n{len(targets)}건 반영했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

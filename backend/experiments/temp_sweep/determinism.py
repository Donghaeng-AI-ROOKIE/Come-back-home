"""P1-3 — 추출 호출의 온도별 결정성 측정.

목적: "추출·구조화는 낮은 온도가 유리"라는 가설을 **가장 직접적으로** 재는 실험.
대화 전체를 돌리는 골드셋 채점은 턴마다 입력이 갈라져 결정성과 정확도가 섞이는데,
여기서는 **입력을 완전히 고정**하고 같은 호출을 N회 반복해 출력 일치율만 본다.

측정:
- 최빈 출력 비율(mode rate) = N회 중 가장 많이 나온 출력이 차지하는 비율.
  1.0 이면 완전 결정론. 온도 0 에서도 1.0 이 아니면 서빙 측 비결정성(배치·커널)이다.
- 서로 다른 출력 종류 수(variants).
정확도는 여기서 재지 않는다 — 정확도는 골드셋 채점(evaluate.py) 담당.

대상: midm.extract_answer(슬롯 추출) / midm.extract_correction(정정 지시 해석).
입력은 골드셋 D1(김순자) 대화에서 뽑았다 — 손라벨이 있는 실제 문장이라 대표성이 있고,
장소 2개·과거 발견이력이 겹친 고난도 발화라 흔들림이 드러나기 쉽다.

실행 (backend 에서):
    .venv/Scripts/python.exe -m experiments.temp_sweep.determinism --n 5
    .venv/Scripts/python.exe -m experiments.temp_sweep.determinism --n 5 --temps 0.0,0.2,0.4
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

RESULTS = Path(__file__).resolve().parent / "results"


# ── 고정 입력 ────────────────────────────────────────────────────────
# (슬롯 key, 이전 대화, 추출 대상 발화) — 대화는 prompts._convo 형식({role, text}).
EXTRACT_CASES: list[tuple[str, str, list[dict]]] = [
    (
        "autobiographical_destination_pull",
        "과거 일터 회귀 — 장소 1개 + 반복 행동",
        [
            {"role": "assistant", "text": "어머님이 혼자 나가시면 주로 어디로 가시나요?"},
            {"role": "user", "text": "혼자 나가시면 늘 정릉시장에 가세요. 반찬거리 사러요."},
            {"role": "assistant", "text": "예전에 자주 다니시던 곳이 있을까요?"},
            {"role": "user", "text": "예전에 면목동에서 방앗간을 오래 하셨는데, 아직도 새벽에 "
                                     "방앗간 문 열러 가야 한다고 자주 나가려 하세요."},
        ],
    ),
    (
        "dementia_wandering_pattern",
        "과거 실종 이력 — 새 장소(발견지)를 이전 턴 장소와 구분해야 함",
        [
            {"role": "assistant", "text": "예전에 자주 다니시던 곳이 있을까요?"},
            {"role": "user", "text": "예전에 면목동에서 방앗간을 오래 하셨어요."},
            {"role": "assistant", "text": "전에 길을 잃으신 적이 있으신가요?"},
            {"role": "user", "text": "작년에 한 번 못 돌아오신 적 있어요. 면목동 버스정류장 "
                                     "근처에서 발견됐고 계속 서성이고 계셨대요."},
        ],
    ),
    (
        "mobility_transport_capacity",
        "축 근거만 있고 장소는 없음 — 과다추출(환각) 검출용",
        [
            {"role": "assistant", "text": "얼마나 걸으실 수 있으세요?"},
            {"role": "user", "text": "쉬지 않고 30분은 걸으세요. 근데 버스나 지하철은 혼자 못 타세요."},
        ],
    ),
]

# (등록된 장소 라벨, 정정 발화)
CORRECTION_CASES: list[tuple[str, list[str], str]] = [
    ("이름 정정 — 삭제가 아니라 교체", ["정릉시장", "방앗간"], "방앗간이 아니라 떡집이에요."),
    ("장소 지역 지정", ["방앗간", "옛집"], "방앗간은 면목동에 있어요."),
    ("삭제 지시", ["정릉시장", "방앗간", "버스정류장"], "버스정류장은 빼주세요."),
]


def _canon(obj) -> str:
    """출력 비교용 정규화 — 키 순서·리스트 순서 차이는 같은 출력으로 본다.

    (추출 결과의 의미는 집합이지 순서가 아니다. 순서까지 세면 온도와 무관한
    나열 순서 흔들림이 비결정성으로 잡혀 지표가 과대평가된다.)
    """
    def norm(o):
        if isinstance(o, dict):
            return {k: norm(v) for k, v in sorted(o.items())}
        if isinstance(o, list):
            return sorted((json.dumps(norm(x), ensure_ascii=False, sort_keys=True) for x in o))
        return o
    return json.dumps(norm(obj), ensure_ascii=False, sort_keys=True)


def _mode_rate(outs: list[str]) -> tuple[float, int]:
    c = Counter(outs)
    return c.most_common(1)[0][1] / len(outs), len(c)


def main() -> int:
    ap = argparse.ArgumentParser(description="추출 호출 온도별 결정성")
    ap.add_argument("--n", type=int, default=5, help="같은 입력 반복 호출 수")
    ap.add_argument("--temps", default="0.0,0.2,0.4", help="쉼표 구분 온도")
    args = ap.parse_args()
    temps = [float(t) for t in args.temps.split(",")]

    from app.config import settings
    from app.llm.midm import MidmClient
    from app.phase0.slots import SLOTS

    client = MidmClient()
    if client.is_stub:
        print("Mi:dm 스텁 모드 — .env 의 MIDM_* 를 확인하세요. 실측 불가.")
        return 1

    slots = {s.key: s for s in (SLOTS if isinstance(SLOTS, list) else SLOTS.values())}

    print(f"═══ 추출 결정성 · 온도 {temps} × 같은 입력 {args.n}회 ═══")
    rows: list[dict] = []

    for temp in temps:
        settings.midm_temp_extract = temp
        settings.midm_temp_correction = temp
        for key, note, convo in EXTRACT_CASES:
            outs = [_canon(client.extract_answer(slots[key], convo)) for _ in range(args.n)]
            rate, variants = _mode_rate(outs)
            rows.append({"call": "extract", "case": key, "note": note, "temp": temp,
                         "mode_rate": rate, "variants": variants,
                         "sample": json.loads(outs[0])})
            print(f"  · extract    T={temp:<4} {key:38} 일치 {rate*100:3.0f}%  종류 {variants}")
        for note, labels, utt in CORRECTION_CASES:
            outs = [_canon(client.extract_correction(labels, utt)) for _ in range(args.n)]
            rate, variants = _mode_rate(outs)
            rows.append({"call": "correction", "case": utt, "note": note, "temp": temp,
                         "mode_rate": rate, "variants": variants,
                         "sample": json.loads(outs[0])})
            print(f"  · correction T={temp:<4} {utt:38} 일치 {rate*100:3.0f}%  종류 {variants}")

    # 요약
    print("\n" + "═" * 62)
    print(f"{'호출':12} {'온도':>6} {'평균 일치율':>12} {'평균 출력종류':>14}")
    print("─" * 62)
    for call in ("extract", "correction"):
        for temp in temps:
            sub = [r for r in rows if r["call"] == call and r["temp"] == temp]
            mr = sum(r["mode_rate"] for r in sub) / len(sub)
            vr = sum(r["variants"] for r in sub) / len(sub)
            print(f"{call:12} {temp:>6} {mr*100:>11.0f}% {vr:>14.1f}")
    print("═" * 62)
    print("일치율 = 같은 입력 N회 중 최빈 출력 비율(1.0=완전 결정론) · 종류 = 서로 다른 출력 수")
    print(f"호출 실패 누적: {client.call_failures}")

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"determinism_n{args.n}.json"
    out.write_text(json.dumps({"n": args.n, "temps": temps, "rows": rows},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"원본 저장: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

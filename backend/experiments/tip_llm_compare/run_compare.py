"""P1-4 부속 — tip_llm 후보 대조실험: Solar-mini(Upstage) vs Mi:dm 2.0 Mini(KT).

`app.llm.tip_llm.TipLLMClient`는 "모델 미정, tip_llm_api_key/base_url/model
세 값만 채우면 실동작"하도록 이미 설계돼 있다(2026-07-21). 그래서 새 클라이언트를
만들지 않고, 두 벤더의 실제 자격증명을 `settings.tip_llm_*`에 번갈아 주입해
**프로덕션과 완전히 동일한 코드 경로**(같은 시스템 프롬프트, 같은 JSON 파싱·검증
로직)로 두 모델을 비교한다 — 실험 코드가 실제 배포 판정과 최대한 가깝게.

채점 기준(scenarios.py 손라벨 대비):
- 구체성 등급 일치율
- 필드 추출 정확도(location/time/appearance/direction 각각 존재 유무가 정답과
  일치하는가) — 값 자체의 정확성이 아니라 "뽑아야 할 때 뽑았는가"만 봄(자유텍스트라
  값 자체의 완전 일치는 무의미, 존재 판정이 핵심)
- 호출 실패 수(TipLLMClient.call_failures — JSON 파싱 실패·API 에러 시 스텁 폴백)
- 평균 지연시간(참고용)

Upstage는 OpenAI 호환 hosted API를 실제 운영 중이라 base_url/model을 코드에서
직접 지정(https://api.upstage.ai/v1, "solar-mini") — KT처럼 발급받은 endpoint가
아니라 벤더가 공개한 공용 엔드포인트라 하드코딩. settings.upstage_api_key 재사용
(Phase1 문서파싱과 같은 계정 키, 모델 문자열만 다름).

실행: backend/ 에서
    python experiments/tip_llm_compare/run_compare.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")

from app.config import settings
from app.llm.tip_llm import TipLLMClient
from scenarios import SCENARIOS, category_breakdown

OUT_DIR = Path(__file__).resolve().parent

VENDORS: dict[str, dict[str, str]] = {
    "solar-mini(Upstage)": {
        "api_key": settings.upstage_api_key,
        "base_url": "https://api.upstage.ai/v1",
        "model": "solar-mini",
    },
    "midm-2.0-mini(KT)": {
        "api_key": settings.midm_api_key,
        "base_url": settings.midm_base_url,
        "model": settings.midm_model,
    },
}


def run_vendor(name: str, cred: dict[str, str]) -> list[dict] | None:
    settings.tip_llm_api_key = cred["api_key"]
    settings.tip_llm_base_url = cred["base_url"]
    settings.tip_llm_model = cred["model"]
    client = TipLLMClient()

    if client.is_stub:
        print(f"[{name}] 자격증명 미비(is_stub=True) — 건너뜀. .env 확인 필요.")
        return None

    rows = []
    for sc in SCENARIOS:
        t0 = time.perf_counter()
        result = client.structure_tip(sc.text)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

        rows.append({
            "id": sc.id,
            "category": sc.category,
            "note": sc.note,
            "gold_specificity": sc.gold_specificity,
            "pred_specificity": result["specificity"],
            "specificity_match": result["specificity"] == sc.gold_specificity,
            "location_match": (result["location_text"] is not None) == sc.expect_location,
            "time_match": (result["time_kind"] != "none") == sc.expect_time,
            "appearance_match": bool(result["appearance_cues"]) == sc.expect_appearance,
            "direction_match": (result["direction"] is not None) == sc.expect_direction,
            "elapsed_ms": elapsed_ms,
            "raw": result,
        })
    print(f"[{name}] 완료 — 호출실패 {client.call_failures}/{len(SCENARIOS)}")
    return rows, client.call_failures


def summarize(name: str, rows: list[dict], call_failures: int) -> dict:
    n = len(rows)
    field_keys = ["location_match", "time_match", "appearance_match", "direction_match"]
    field_score = sum(sum(r[k] for k in field_keys) for r in rows) / (n * len(field_keys))
    return {
        "vendor": name,
        "n": n,
        "call_failures": call_failures,
        "specificity_agreement": round(sum(r["specificity_match"] for r in rows) / n, 3),
        "field_extraction_accuracy": round(field_score, 3),
        "avg_latency_ms": round(sum(r["elapsed_ms"] for r in rows) / n, 1),
    }


def render_markdown(summaries: list[dict], detail: dict[str, list[dict]]) -> str:
    lines = ["# tip_llm 후보 대조실험 — Solar-mini vs Mi:dm 2.0 Mini", ""]
    lines.append(f"시나리오 {len(SCENARIOS)}개(자체 라벨링, 상/중/하 손라벨) x 2벤더. "
                "동일 프로덕션 코드(`TipLLMClient.structure_tip`) 경로로 실행.")
    lines.append("")
    lines.append("| 벤더 | 구체성일치율 | 필드추출정확도 | 호출실패 | 평균지연(ms) |")
    lines.append("|---|---|---|---|---|")
    for s in summaries:
        lines.append(f"| {s['vendor']} | {s['specificity_agreement']:.1%} | "
                     f"{s['field_extraction_accuracy']:.1%} | {s['call_failures']}/{s['n']} | "
                     f"{s['avg_latency_ms']} |")
    lines.append("")
    lines.append("## 유형별 구체성 일치율 (실전 잡음 내성 비교)")
    lines.append("장황·모순·과신·복수대상·구어체잡음은 실제 제보에 가까운 잡음을 넣은 유형. "
                 "기본(깔끔한 셋)과 유형별로 어디서 무너지는지 본다.")
    lines.append("")
    cats = ["기본", "장황", "모순", "과신", "복수대상", "구어체잡음"]
    header = "| 벤더 | " + " | ".join(cats) + " |"
    lines.append(header)
    lines.append("|---|" + "---|" * len(cats))
    for vendor, rows in detail.items():
        bd = category_breakdown(rows)
        cells = []
        for c in cats:
            if c in bd:
                cells.append(f"{bd[c]['specificity_agreement']:.0%}(n{bd[c]['n']})")
            else:
                cells.append("-")
        lines.append(f"| {vendor} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("## 시나리오별 구체성 판정 불일치")
    for vendor, rows in detail.items():
        mismatches = [r for r in rows if not r["specificity_match"]]
        if not mismatches:
            lines.append(f"- **{vendor}**: 불일치 없음")
            continue
        lines.append(f"- **{vendor}**: {len(mismatches)}건")
        for r in mismatches:
            lines.append(f"  - {r['id']}({r['category']}): 정답={r['gold_specificity']} → "
                         f"예측={r['pred_specificity']}")
    lines.append("")
    lines.append("## 모순·복수대상 시나리오 — 모델이 어느 값을 뽑았나 (두 값 대조, 채점 안 함)")
    lines.append("정정·충돌 케이스에서 '어느 값이 맞는지'는 채점하지 않는다(값 정확성 판정 안 함). "
                 "골드 note의 두 값과 모델 추출값을 나란히 놓아 사람이 검수한다.")
    lines.append("")
    for vendor, rows in detail.items():
        noted = [r for r in rows if r.get("note")]
        if not noted:
            continue
        lines.append(f"- **{vendor}**")
        for r in noted:
            raw = r["raw"]
            picked = (f"장소={raw.get('location_text')!r}, 시각kind={raw.get('time_kind')}"
                      f"(min={raw.get('time_minutes_ago')}, clock={raw.get('time_clock')}), "
                      f"외모={raw.get('appearance_cues')}, 방향={raw.get('direction')!r}")
            lines.append(f"  - {r['id']}: {r['note']}")
            lines.append(f"    → 모델 추출: {picked}")
    return "\n".join(lines)


def main() -> None:
    summaries = []
    detail: dict[str, list[dict]] = {}
    for name, cred in VENDORS.items():
        out = run_vendor(name, cred)
        if out is None:
            continue
        rows, call_failures = out
        detail[name] = rows
        summaries.append(summarize(name, rows, call_failures))

    if not summaries:
        print("두 벤더 모두 자격증명이 없어 비교 불가. .env 확인 필요.")
        return

    md = render_markdown(summaries, detail)
    by_category = {vendor: category_breakdown(rows) for vendor, rows in detail.items()}
    (OUT_DIR / "results" / "tip_llm_compare.md").write_text(md, encoding="utf-8")
    (OUT_DIR / "results" / "tip_llm_compare.json").write_text(
        json.dumps({"summaries": summaries, "by_category": by_category, "detail": detail},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")
    print()
    print(md)
    print(f"\n저장: {OUT_DIR / 'results' / 'tip_llm_compare.md'}")


if __name__ == "__main__":
    main()

"""P1-4 부속 — tip_llm 후보 대조실험 (3): 공식 원본 Mi:dm 2.0 Mini(로컬 transformers).

KT가 발급한 endpoint(TIP_LLM_* / MIDM_*)가 실제로 Mini(2.3B)인지 Base(11.5B)인지
API 응답만으로는 확인이 안 됐다(응답의 model 필드가 불투명한 deployment ID라
`dep0y7dit3r77da`처럼 나옴 — 2026-07-29 확인). 그래서 **공식 HF 레포에서 직접
받은 원본**(`K-intelligence/Midm-2.0-Mini-Instruct`, 비공식 GGUF 미러 아님)을
로컬에서 돌려 "진짜 Mini"와 비교한다.

run_compare.py 와 채점 기준을 동일하게 맞춘다(같은 시스템 프롬프트·같은 필드
존재유무 채점) — 다만 HTTP 대신 transformers 로 직접 추론하므로 TipLLMClient
는 안 거친다(JSON 파싱·검증 로직만 그대로 재사용).

GPU 없는 노트북에서 CPU로 돌리므로 20개 처리에 15~40분 걸릴 수 있다(모델
다운로드 ~4.6GB 별도).

실행: backend/ 에서
    python experiments/tip_llm_compare/run_compare_local.py midm-mini
    python experiments/tip_llm_compare/run_compare_local.py exaone-1.2b
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")

from app.llm.tip_llm import _CLOCK_RE, _TIME_KINDS, _TIP_STRUCTURE_SYSTEM  # noqa: E402
from scenarios import SCENARIOS, category_breakdown  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent

# 공식 계정에서 받은 원본만 후보로 둔다(비공식 미러 금지, 2026-07-29 확정 원칙).
CANDIDATES = {
    "midm-mini": ("K-intelligence/Midm-2.0-Mini-Instruct", "midm-2.0-mini-local(공식원본)"),
    "exaone-1.2b": ("LGAI-EXAONE/EXAONE-4.0-1.2B", "exaone-4.0-1.2b-local(공식원본)"),
    "ax-4.0-light": ("skt/A.X-4.0-Light", "ax-4.0-light-local(공식원본, 7B)"),
}


def _parse_structure(raw: str) -> dict:
    """tip_llm.TipLLMClient.structure_tip 의 파싱·검증 로직과 동일하게 맞춤."""
    try:
        data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    except Exception:
        return {"location_text": None, "time_text": None, "time_kind": "none",
                "time_minutes_ago": None, "time_clock": None,
                "appearance_cues": [], "direction": None, "specificity": "하",
                "parse_failed": True}
    level = data.get("specificity")
    time_kind = data.get("time_kind") if data.get("time_kind") in _TIME_KINDS else "none"
    minutes_ago = data.get("time_minutes_ago")
    if time_kind != "relative" or not isinstance(minutes_ago, int) or minutes_ago < 0:
        minutes_ago = None
    clock = data.get("time_clock")
    if time_kind != "absolute" or not _CLOCK_RE.match(str(clock or "")):
        clock = None
    return {
        "location_text": data.get("location_text"),
        "time_text": data.get("time_text"),
        "time_kind": time_kind,
        "time_minutes_ago": minutes_ago,
        "time_clock": clock,
        "appearance_cues": data.get("appearance_cues") or [],
        "direction": data.get("direction"),
        "specificity": level if level in ("상", "중", "하") else "중",
        "parse_failed": False,
    }


def main(candidate: str) -> None:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    model_id, vendor_label = CANDIDATES[candidate]
    print(f"모델 로딩: {model_id} (첫 실행이면 다운로드 발생)")
    t0 = time.time()
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    # bfloat16 — A.X-4.0-Light(7B)를 float32로 올리면 ~28GB라 노트북엔 위험.
    # bf16은 CPU에서도 안정적으로 도는 편이라 세 후보 전부 이걸로 통일.
    model = AutoModelForCausalLM.from_pretrained(model_id, dtype=torch.bfloat16)
    model.eval()
    print(f"로딩 완료 ({time.time() - t0:.0f}s)")

    rows = []
    parse_failures = 0
    for i, sc in enumerate(SCENARIOS):
        messages = [
            {"role": "system", "content": _TIP_STRUCTURE_SYSTEM},
            {"role": "user", "content": sc.text},
        ]
        # transformers 최신판은 apply_chat_template(..., return_tensors="pt")가
        # 텐서가 아니라 BatchEncoding(dict형)을 반환한다 — return_dict=True로 명시하고
        # model.generate(**inputs)로 풀어 넘겨야 한다(2026-07-29 실제 실행 중 발견,
        # 예전 버전 관례인 "텐서 하나 바로 반환"을 그대로 쓰면 AttributeError 남).
        inputs = tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, return_tensors="pt", return_dict=True)
        t0 = time.time()
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=400, do_sample=False,
                                 temperature=None, top_p=None,
                                 pad_token_id=tokenizer.eos_token_id)
        elapsed_ms = round((time.time() - t0) * 1000, 1)
        raw = tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        result = _parse_structure(raw)
        if result["parse_failed"]:
            parse_failures += 1

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
        print(f"  [{i + 1}/{len(SCENARIOS)}] {sc.id} 완료 ({elapsed_ms:.0f}ms, "
              f"pred={result['specificity']}, gold={sc.gold_specificity})")

    n = len(rows)
    field_keys = ["location_match", "time_match", "appearance_match", "direction_match"]
    field_score = sum(sum(r[k] for k in field_keys) for r in rows) / (n * len(field_keys))
    summary = {
        "vendor": vendor_label,
        "n": n,
        "call_failures": parse_failures,
        "specificity_agreement": round(sum(r["specificity_match"] for r in rows) / n, 3),
        "field_extraction_accuracy": round(field_score, 3),
        "avg_latency_ms": round(sum(r["elapsed_ms"] for r in rows) / n, 1),
    }
    for k in field_keys:
        rate = sum(r[k] for r in rows) / n
        print(f"  {k}: {rate:.1%}")

    breakdown = category_breakdown(rows)
    print("\n  유형별 구체성 일치율:")
    for cat in ["기본", "장황", "모순", "과신", "복수대상", "구어체잡음"]:
        if cat in breakdown:
            b = breakdown[cat]
            print(f"    {cat:6s} 구체성 {b['specificity_agreement']:.1%} / "
                  f"필드 {b['field_extraction_accuracy']:.1%} (n{b['n']})")

    out_path = OUT_DIR / "results" / f"tip_llm_compare_local_{candidate}.json"
    out_path.write_text(
        json.dumps({"summary": summary, "detail": rows, "category_breakdown": breakdown},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")

    print()
    print(f"구체성일치율: {summary['specificity_agreement']:.1%}")
    print(f"필드추출정확도: {summary['field_extraction_accuracy']:.1%}")
    print(f"파싱실패: {parse_failures}/{n}")
    print(f"평균지연: {summary['avg_latency_ms']}ms")
    print(f"\n저장: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", choices=list(CANDIDATES.keys()))
    args = parser.parse_args()
    main(args.candidate)

"""Join frozen truth only AFTER predictions, reuse original targeting calculations."""
import argparse
import json
from pathlib import Path

import h3

from app.config import settings
from experiments.personalized_alert_replay.analyze_targeting_resolution import (
    build_summary, evaluate_surface, load_pairs, fmt_metric,
)
from experiments.literature_targeting_20260924.run_predictions import HERE, sha, write


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--split", choices=["development", "evaluation"], required=True)
    p.add_argument("--predictions", type=Path, default=HERE / "predictions_v1")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise SystemExit("Do not overwrite analysis results")
    read = lambda path: json.loads(path.read_text(encoding="utf-8"))
    config = read(args.predictions / "config.json")
    for key in ("alert_coverage", "max_alert_cells", "push_prob_threshold"):
        if config["effective_settings"][key] != settings.model_dump(mode="json")[key]:
            raise ValueError(f"Targeting setting changed after prediction: {key}")
    inputs_path = HERE / "dataset_v1" / f"{args.split}_inputs.json"
    completion = read(args.predictions / f"{args.split}_complete.json")
    if completion["input_sha256"] != sha(inputs_path):
        raise ValueError("Inputs changed after prediction")
    manifest = read(HERE / "dataset_v1/manifest.json")
    truth_path = HERE / "dataset_v1" / f"{args.split}_truth.json"
    if sha(truth_path) != manifest["files"][truth_path.name]:
        raise ValueError("Frozen truth changed")
    truth = read(truth_path)
    joined, moving = [], {}
    for t in truth:
        row = {"scenario_id": t["scenario_id"], "profile_id": t["profile_id"],
               "stratum": t["condition"], "truth_behavior": t["condition"], "arms": {}}
        for arm in "BC":
            prediction = read(args.predictions / args.split / f"{t['scenario_id']}_{arm}.json")
            if (prediction["scenario_id"], prediction["profile_id"], prediction["arm"]) != (t["scenario_id"], t["profile_id"], arm):
                raise ValueError("Prediction identity mismatch")
            if prediction["prior"]["source"] != "exaone":
                raise ValueError("Non-EXAONE prediction")
            pm = {s["minute_after_report"]: s for s in prediction["snapshots"]}
            if len(pm) != len(prediction["snapshots"]) or len(pm) != len(t["points"]) or set(pm) != {x["minute_after_report"] for x in t["points"]}:
                raise ValueError("Missing or duplicate times")
            snapshots = []
            for point in t["points"]:
                minute = point["minute_after_report"]
                coord = {"lat": point["lat"], "lng": point["lng"]}
                snapshots.append({**pm[minute], "truth": coord,
                    "truth_cell": h3.latlng_to_cell(coord["lat"], coord["lng"], 9)})
                moving[t["scenario_id"], minute] = not point["arrived"]
            row["arms"][arm] = {"valid": True, "temporal": {"snapshots": snapshots}}
        joined.append(row)
    args.output.mkdir(parents=True)
    joined_path = args.output / "paired_predictions.jsonl"
    joined_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in joined), encoding="utf-8")
    pairs, audit = load_pairs(joined_path)
    records = []
    for pair in pairs:
        for arm in "BC":
            s = pair["snapshots"][arm]
            for res in (7, 8):
                for level, threshold in settings.push_prob_threshold.items():
                    records.append({k: pair[k] for k in ("profile_id", "scenario_id", "stratum", "behavior", "minute")} |
                        {"arm": arm, "resolution": res, "engagement": level,
                         "moving": moving[pair["scenario_id"], pair["minute"]]} |
                        evaluate_surface(s["surface_cells"], pair["truth"], s["truth_cell"], res,
                                         settings.alert_coverage, settings.max_alert_cells, threshold))
    summaries = {}
    for condition in ("all_equal_mixture", "routine_related", "route_departure", "unrelated_direction"):
        subset = [r for r in records if condition == "all_equal_mixture" or r["stratum"] == condition]
        for scope in ("all_times", "moving_only"):
            selected = [r for r in subset if scope == "all_times" or r["moving"]]
            profiles = sorted({r["profile_id"] for r in selected})
            if profiles:
                summaries[condition + "/" + scope] = build_summary(selected, profiles, 10000, 20260924)
    primary = summaries["routine_related/all_times"]["personalization"]["res8/normal"]
    area_ci = primary["area_reduction_pct"]["eligible"]["ci95"]
    hit_ci = primary["truth_inclusion_difference_pp"]["ci95"]
    joint = bool(area_ci and hit_ci and area_ci[0] > 0 and hit_ci[0] > 0)
    write(args.output / "summary.json", {"split": args.split, "audit": audit,
        "primary_joint_improvement": joint,
        "truth_sha256": sha(truth_path), "joined_sha256": sha(joined_path),
        "config": config, "summaries": summaries, "analysis_sha256": sha(__file__),
        "targeting_settings": {"coverage": settings.alert_coverage, "max_cells": settings.max_alert_cells,
                               "thresholds": settings.push_prob_threshold}})
    (args.output / "snapshots.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    lines = ["# 문헌 기반 타겟팅 결과", "", f"분할: {args.split}. 합성 조건별 탐색적 비교다.", "",
             "| 조건/시점 | res/참여도 | B 면적 km2 | C 면적 km2 | B 포함 | C 포함 |", "|---|---|---:|---:|---:|---:|"]
    for name, summary in summaries.items():
        for res in (8, 7):
            for level in settings.push_prob_threshold:
                b, c = [summary["groups"][f"res{res}/{level}/{arm}"] for arm in "BC"]
                lines.append(f"| {name} | {res}/{level} | {b['stages']['eligible']['mean_area_km2']:.3f} | {c['stages']['eligible']['mean_area_km2']:.3f} | {b['hits']}/{b['n']} | {c['hits']}/{c['n']} |")
    lines += ["", "## 사전 지정 주 비교", "",
              "평소 경로 일치 조건의 res8·normal, 전체 시점이 주 비교다.",
              f"- 발송면적 감소율: {fmt_metric(primary['area_reduction_pct']['eligible'])}%",
              f"- 포함률 차이: {fmt_metric(primary['truth_inclusion_difference_pp'])}%p",
              f"- 두 지표 95% 구간 하한이 모두 양수: {joint}",
              "이는 합성 조건 내 결과이며, 개발용 결과를 평가용 확인 결과로 취급하지 않는다.",
              "", "## 8개 지표: 조건별 res8 normal", ""]
    for condition in ("all_equal_mixture", "routine_related", "route_departure", "unrelated_direction"):
        summary = summaries[condition + "/all_times"]
        b, c = [summary["groups"][f"res8/normal/{arm}"] for arm in "BC"]
        comp = summary["personalization"]["res8/normal"]
        lines += [f"### {condition}", "", "| 지표 | B | C 또는 C-B 비교 |", "|---|---|---|"]
        for i, (stage, label) in enumerate((("raw", "전체 res9"), ("selected", "선택 res9"),
                                           ("parents", "문턱 전 부모"), ("eligible", "최종 발송")), 1):
            bs, cs = b["stages"][stage], c["stages"][stage]
            lines.append(f"| {i}. {label} 평균 수 / 면적 km2 | {bs['mean_count']:.2f} / {bs['mean_area_km2']:.3f} | {cs['mean_count']:.2f} / {cs['mean_area_km2']:.3f} |")
        lines += [f"| 5. 정답 포함 | {b['hits']}/{b['n']} ({100*b['truth_inclusion_rate']:.2f}%) | {c['hits']}/{c['n']} ({100*c['truth_inclusion_rate']:.2f}%) |",
                  "| 6. 단계별 면적 감소율, 95% 구간 | B 기준 | " + "; ".join(f"{s}: {fmt_metric(comp['area_reduction_pct'][s])}%" for s in ("raw", "selected", "parents", "eligible")) + " |",
                  f"| 7. 포함률 차이, 95% 구간 | C-B | {fmt_metric(comp['truth_inclusion_difference_pp'])}%p |",
                  f"| 8. 선택 res9는 다르고 최종 구역은 동일 | 전체 {comp['n']}시점 | {comp['different_res9_same_final_n']}시점 ({100*comp['different_res9_same_final_rate_all']:.2f}%) |", "",
                  "| 인물 | B 면적 km2 / 포함 | C 면적 km2 / 포함 |", "|---|---|---|"]
        for profile, bp in summary["by_profile"]["res8/normal/B"].items():
            cp = summary["by_profile"]["res8/normal/C"][profile]
            lines.append(f"| {profile} | {bp['stages']['eligible']['mean_area_km2']:.3f} / {bp['hits']}/{bp['n']} | {cp['stages']['eligible']['mean_area_km2']:.3f} / {cp['hits']}/{cp['n']} |")
    lines += ["", "## 해석 한계", "",
              "인물 6명을 묶어 재표집한 10,000회 구간이다. 보조 조건은 다중비교 보정하지 않았다.",
              "전체 균등 혼합은 실제 발생 비율을 뜻하지 않는다. 실제 수신자·푸시·발견 성공은 측정하지 않았다.",
              "현재 코드의 목적지와 보호자 설명을 사용했으며 전체 경로 좌표는 모델에 전달되지 않았다.",
              "환경 레이어를 양 군에서 제외했으므로 당시 V2의 완전한 재현이 아니다. 현재 동일 정책 내 B/C 비교로 해석한다."]
    (args.output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

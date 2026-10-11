"""Offline B/C targeting comparison with explicit historical/current policies.

Run from backend with python -B -m experiments.personalized_alert_replay.analyze_targeting_resolution.
Existing analysis scripts and production settings are never modified.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import time

import h3
import numpy as np

from app.config import settings
from app.geo import h3grid
from app.phase3 import alerts

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]
STAGES = ("raw", "selected", "parents", "eligible")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=None)
def area(cell: str) -> float:
    return h3.cell_area(cell, unit="km^2")


def region(cells) -> dict:
    ordered = sorted(set(cells))
    return {"cells": ordered, "count": len(ordered),
            "area_km2": math.fsum(area(c) for c in ordered)}


def load_pairs(path: Path) -> tuple[list[dict], dict]:
    """Fail closed rather than silently remove failed or misaligned cases."""
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    pairs, seen, masses = [], set(), []
    for row in rows:
        scenario = row["scenario_id"]
        if scenario in seen:
            raise ValueError(f"Duplicate scenario: {scenario}")
        seen.add(scenario)
        indexed = {}
        for arm in "BC":
            if not row["arms"][arm]["valid"]:
                raise ValueError(f"Invalid arm: {scenario}/{arm}")
            snapshots = row["arms"][arm]["temporal"]["snapshots"]
            indexed[arm] = {s["minute_after_report"]: s for s in snapshots}
            if not snapshots or len(indexed[arm]) != len(snapshots):
                raise ValueError(f"Empty/duplicate timepoints: {scenario}/{arm}")
        if indexed["B"].keys() != indexed["C"].keys():
            raise ValueError(f"Unpaired minutes: {scenario}")
        for minute in sorted(indexed["B"]):
            snapshots = {a: indexed[a][minute] for a in "BC"}
            b, c = snapshots["B"], snapshots["C"]
            if b["truth"] != c["truth"] or b["truth_cell"] != c["truth_cell"]:
                raise ValueError(f"Unpaired truth: {scenario}/{minute}")
            lat, lng = b["truth"]["lat"], b["truth"]["lng"]
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                raise ValueError("Invalid truth coordinates")
            if h3.latlng_to_cell(lat, lng, 9) != b["truth_cell"]:
                raise ValueError(f"Truth coordinate/res9 mismatch: {scenario}/{minute}")
            for arm, s in snapshots.items():
                poa = s["surface_cells"]
                if not poa or any(not h3.is_valid_cell(cell) or h3.get_resolution(cell) != 9
                                  for cell in poa):
                    raise ValueError(f"Invalid res9 surface: {scenario}/{minute}/{arm}")
                if any(not math.isfinite(p) or p < 0 for p in poa.values()):
                    raise ValueError(f"Invalid probability: {scenario}/{minute}/{arm}")
                mass = math.fsum(poa.values())
                if not math.isclose(mass, 1.0, abs_tol=1e-6):
                    raise ValueError(f"Unnormalized surface: {scenario}/{minute}/{arm}: {mass}")
                masses.append(mass)
            pairs.append({"profile_id": row["profile_id"], "scenario_id": scenario,
                          "stratum": row["stratum"], "behavior": row["truth_behavior"],
                          "minute": minute, "truth": b["truth"], "snapshots": snapshots})
    if not pairs:
        raise ValueError("No paired observations")
    return pairs, {"scenarios": len(rows), "profiles": sorted({p["profile_id"] for p in pairs}),
                   "paired_timepoints": len(pairs), "minutes": sorted({p["minute"] for p in pairs}),
                   "probability_mass_range": [min(masses), max(masses)], "excluded": [],
                   "policy": "fail on invalid/misaligned input; no automatic exclusions"}


def evaluate_surface(poa: dict, truth: dict, truth_res9: str, resolution: int,
                     coverage: float, max_cells: int, threshold: float, *,
                     targeting_policy: str = "legacy_peak_threshold") -> dict:
    selected = alerts.select_alert_cells(poa, coverage=coverage, max_cells=max_cells)
    # Archive reruns retain the original logical-parent + second-threshold policy.
    # Current dispatch parity must opt into geographic coverage without that filter.
    if targeting_policy == "selected_coverage_geographic_cover_v1":
        parents = alerts.target_parent_cells(selected, res=resolution)
    elif targeting_policy == "legacy_peak_threshold":
        parents = h3grid.parent_cells(selected, resolution)
    else:
        raise ValueError(f"Unknown targeting policy: {targeting_policy}")
    relative = alerts.relative_prob_by_parent(poa, res=resolution)
    eligible = (set(parents) if targeting_policy == "selected_coverage_geographic_cover_v1"
                else {p for p in parents if not relative or relative.get(p, 0.0) >= threshold})
    truth_target = h3.latlng_to_cell(truth["lat"], truth["lng"], resolution)
    proxy = h3.cell_to_parent(truth_res9, resolution)
    return {"targeting_policy": targeting_policy,
            "stages": {"raw": region(poa), "selected": region(selected),
                       "parents": region(parents), "eligible": region(eligible)},
            "selected_probability_mass": math.fsum(poa[c] for c in selected),
            "cap_reached": len(selected) == max_cells,
            "truth_cell": truth_target, "truth_parent_proxy": proxy,
            "truth_parent_proxy_differs": truth_target != proxy,
            "truth_selected_res9": truth_res9 in selected,
            "truth_prethreshold": truth_target in parents,
            "truth_included": truth_target in eligible,
            "truth_included_parent_proxy": proxy in eligible}


def reduce_percent(base: float, candidate: float):
    return None if base == 0 else 100 * (base - candidate) / base


def aggregate(records: list[dict]) -> dict:
    n = len(records)
    return {"n": n, "hits": sum(r["truth_included"] for r in records),
            "truth_inclusion_rate": sum(r["truth_included"] for r in records) / n,
            "proxy_hits": sum(r["truth_included_parent_proxy"] for r in records),
            "coordinate_parent_mismatch_n": sum(r["truth_parent_proxy_differs"] for r in records),
            "mean_selected_mass": sum(r["selected_probability_mass"] for r in records) / n,
            "cap_reached_n": sum(r["cap_reached"] for r in records),
            "stages": {s: {"total_count": sum(r["stages"][s]["count"] for r in records),
                            "mean_count": sum(r["stages"][s]["count"] for r in records) / n,
                            "total_area_km2": math.fsum(r["stages"][s]["area_km2"] for r in records),
                            "mean_area_km2": math.fsum(r["stages"][s]["area_km2"] for r in records) / n}
                       for s in STAGES}}


def comparison(base: list[dict], candidate: list[dict], profiles: list[str], draws: np.ndarray) -> dict:
    key = lambda r: (r["profile_id"], r["scenario_id"], r["minute"])
    bm, cm = {key(r): r for r in base}, {key(r): r for r in candidate}
    if bm.keys() != cm.keys() or len(bm) != len(base) or len(cm) != len(candidate):
        raise ValueError("Comparison records are not uniquely paired")
    # One vector per person: n, base hits, candidate hits, then stage areas in pairs.
    vectors = []
    for profile in profiles:
        keys = [k for k in bm if k[0] == profile]
        vectors.append([len(keys), sum(bm[k]["truth_included"] for k in keys),
                        sum(cm[k]["truth_included"] for k in keys)] +
                       [math.fsum(m[k]["stages"][s]["area_km2"] for k in keys)
                        for s in STAGES for m in (bm, cm)])
    v = np.asarray(vectors, dtype=float)
    total, boot = v.sum(axis=0), v[draws].sum(axis=1)

    def metric(point, samples):
        samples = samples[np.isfinite(samples)]
        return {"estimate": point, "ci95": np.quantile(samples, [.025, .975]).tolist() if len(samples) else None,
                "valid_bootstrap_replicates": len(samples)}

    out = {"n": len(base), "truth_inclusion_difference_pp": metric(
        100 * (total[2] - total[1]) / total[0], 100 * (boot[:, 2] - boot[:, 1]) / boot[:, 0]),
        "area_reduction_pct": {}}
    for i, stage in enumerate(STAGES):
        j = 3 + 2 * i
        with np.errstate(divide="ignore", invalid="ignore"):
            samples = 100 * (boot[:, j] - boot[:, j + 1]) / boot[:, j]
        out["area_reduction_pct"][stage] = metric(reduce_percent(total[j], total[j + 1]), samples)
    return out


def build_summary(records: list[dict], profiles: list[str], repeats: int, seed: int) -> dict:
    groups = defaultdict(list)
    for r in records:
        groups[(r["resolution"], r["engagement"], r["arm"])].append(r)
    draws = np.random.default_rng(seed).integers(0, len(profiles), size=(repeats, len(profiles)))
    summary = {"groups": {}, "personalization": {}, "resolution_change": {}, "by_profile": {}}
    for (res, level, arm), group in groups.items():
        name = f"res{res}/{level}/{arm}"
        summary["groups"][name] = aggregate(group)
        summary["by_profile"][name] = {p: aggregate([r for r in group if r["profile_id"] == p]) for p in profiles}
    for res in (7, 8):
        for level in settings.push_prob_threshold:
            b, c = groups[(res, level, "B")], groups[(res, level, "C")]
            item = comparison(b, c, profiles, draws)
            same_final = different_source = collapsed = 0
            for rb, rc in zip(b, c):
                if (rb["scenario_id"], rb["minute"]) != (rc["scenario_id"], rc["minute"]):
                    raise ValueError("Unpaired collapse comparison")
                diff = rb["stages"]["selected"]["cells"] != rc["stages"]["selected"]["cells"]
                same = rb["stages"]["eligible"]["cells"] == rc["stages"]["eligible"]["cells"]
                different_source += diff
                same_final += same
                collapsed += diff and same
            item["same_final_set_n"] = same_final
            item["different_selected_res9_n"] = different_source
            item["different_res9_same_final_n"] = collapsed
            item["different_res9_same_final_rate_all"] = collapsed / len(b)
            item["same_final_given_different_res9_rate"] = collapsed / different_source if different_source else None
            summary["personalization"][f"res{res}/{level}"] = item
    for level in settings.push_prob_threshold:
        for arm in "BC":
            summary["resolution_change"][f"{level}/{arm}"] = comparison(
                groups[(7, level, arm)], groups[(8, level, arm)], profiles, draws)
    return summary


def fmt_metric(m: dict) -> str:
    if m["estimate"] is None:
        return "미정의"
    ci = m["ci95"]
    return f"{m['estimate']:+.2f} [{ci[0]:+.2f}, {ci[1]:+.2f}]" if ci else f"{m['estimate']:+.2f}"


def render_report(result: dict) -> str:
    s, meta = result["summary"], result["metadata"]
    lines = ["# res7·res8 타겟팅 재분석", "",
             "저장된 예측에 당시 논리 부모·참여도 문턱 정책을 적용한 역사 재현이다. 현재 발송 정책과 구분하며 실제 푸시는 전송하지 않았다.", "",
             f"- 입력: `{meta['input']}` (SHA-256: `{meta['input_sha256']}`)",
             f"- 인물 {len(result['audit']['profiles'])}명, 시나리오 {result['audit']['scenarios']}개, 대응 시점 {result['audit']['paired_timepoints']}개.",
             "- B: 비개인화, C: 개인화. 주 비교: res8의 C 대 B. 보조 비교: res7 및 해상도 변경.",
             "- 구간은 인물 단위 대응 부트스트랩의 95% 백분위 구간이다. 9명 기반 탐색적 구간이며 다중비교 보정은 하지 않았다.",
             "- 포함률 허용 하락폭은 미설정이다. 비열등성/정확도 유지 성공을 판정하지 않는다.",
             "- 감소율은 평균 면적(동일 표본 수에서 총면적과 동등) 기준이다. 음수는 증가를 뜻한다.", "",
             "## 최종 발송구역과 정답 포함률", "",
             "| 해상도 | 참여도 | B 평균 면적 km² | C 평균 면적 km² | C 면적 감소율 % [95% 구간] | B 포함 | C 포함 | C−B %p [95% 구간] |",
             "|---|---|---:|---:|---|---|---|---|"]
    for res in (8, 7):
        for level in settings.push_prob_threshold:
            b, c = [s["groups"][f"res{res}/{level}/{a}"] for a in "BC"]
            comp = s["personalization"][f"res{res}/{level}"]
            lines.append(f"| {res} | {level} | {b['stages']['eligible']['mean_area_km2']:.3f} | {c['stages']['eligible']['mean_area_km2']:.3f} | {fmt_metric(comp['area_reduction_pct']['eligible'])} | {b['hits']}/{b['n']} ({100*b['truth_inclusion_rate']:.1f}%) | {c['hits']}/{c['n']} ({100*c['truth_inclusion_rate']:.1f}%) | {fmt_metric(comp['truth_inclusion_difference_pp'])} |")
    lines += ["", "## res7 → res8 변화: 동일 예측 기준", "",
              "| 참여도 | 예측 | 면적 감소율 % [95% 구간] | 포함률 변화 %p [95% 구간] |",
              "|---|---|---|---|"]
    for name, comp in s["resolution_change"].items():
        level, arm = name.split("/")
        lines.append(f"| {level} | {arm} | {fmt_metric(comp['area_reduction_pct']['eligible'])} | {fmt_metric(comp['truth_inclusion_difference_pp'])} |")
    lines += ["", "## 단계별 개인화 면적 감소율", "",
              "| 해상도/참여도 | 전체 res9 % | 선택 res9 % | 문턱 전 부모 % | 문턱 후 % | 다른 res9 → 같은 발송구역 |",
              "|---|---:|---:|---:|---:|---|"]
    for name, comp in s["personalization"].items():
        values = " | ".join(f"{comp['area_reduction_pct'][stage]['estimate']:+.2f}" for stage in STAGES)
        lines.append(f"| {name} | {values} | {comp['different_res9_same_final_n']}/{comp['different_selected_res9_n']} (선택 res9가 다른 시점 중) |")
    lines += ["", "## 단계별 셀 수·면적", "",
              "| 해상도/참여도/군 | 전체 res9 수/면적 | 선택 res9 수/면적 | 부모 수/면적 | 최종 수/면적 |",
              "|---|---|---|---|---|"]
    for name, group in s["groups"].items():
        values = " | ".join(f"{group['stages'][st]['mean_count']:.2f} / {group['stages'][st]['mean_area_km2']:.3f}" for st in STAGES)
        lines.append(f"| {name} | {values} |")
    lines += ["", "수/면적은 시점별 평균 셀 수 / 평균 km². 시점 간 합산 면적은 고유 지리적 면적이 아니다.",
              "", "## 인물별 결과", "",
              "| 해상도/참여도 | 인물 | C 면적 감소율 % | B 포함 | C 포함 |", "|---|---|---:|---|---|"]
    for res in (8, 7):
        for level in settings.push_prob_threshold:
            for p in result["audit"]["profiles"]:
                b, c = [s["by_profile"][f"res{res}/{level}/{a}"][p] for a in "BC"]
                reduction = reduce_percent(b["stages"]["eligible"]["total_area_km2"], c["stages"]["eligible"]["total_area_km2"])
                lines.append(f"| {res}/{level} | {p} | {reduction:+.2f} | {b['hits']}/{b['n']} | {c['hits']}/{c['n']} |")
    lines += ["", "## 검증·해석 한계", "",
              "- 전체 입력은 짝·유효성·정규화 검증을 통과해야 한다. 자동 제외나 재정규화는 하지 않는다.",
              "- 정답 좌표에서 대상 해상도를 직접 계산한다. H3의 계층 부모와 좌표 직접 변환은 경계에서 다를 수 있어 기존 부모 대리 방식 결과도 JSON에 남긴다.",
              "- 실제 등록 기기 분포·위치 최신성·수신·열람·발견 성과를 측정하지 않았다. 면적 감소는 수신자 감소가 아니다.",
              "- 같은 구역 집합으로 합쳐지는 빈도는 조건부 기술 통계다. 이것만으로 개인정보 정책의 타당성을 확정하지 않는다.",
              "- 설정을 바꿔 동일 포함률을 맞추는 탐색은 수행하지 않았다. 현재 설정에서의 대응 비교다.",
              "- 운영 전환은 별도 결정이다. 폰 res8 계산, 등록 API/저장 구조, 구버전 호환, 위치 재등록·최신성, 페이로드 검증이 필요하다.",
              "- 기존 res7 셀에서 정확한 res8 위치는 복원할 수 없다. 실제 전환 때 폰이 현재 GPS에서 계산한 셀 번호만 재등록해야 한다.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=HERE / "results/persona_abc_v2_r1.jsonl")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260924)
    args = parser.parse_args()
    if args.bootstrap < 100:
        parser.error("Use at least 100 bootstrap replicates")
    if args.output_dir.exists():
        parser.error("Output directory already exists; choose a new directory to preserve results")
    started = time.monotonic()
    pairs, audit = load_pairs(args.input)
    print(f"Validated {audit['scenarios']} scenarios, {len(audit['profiles'])} profiles, {len(pairs)} paired times", flush=True)
    coverage, cap = settings.alert_coverage, settings.max_alert_cells
    records = []
    for pair in pairs:
        for arm in "BC":
            snap = pair["snapshots"][arm]
            for res in (7, 8):
                for level, threshold in settings.push_prob_threshold.items():
                    records.append({k: pair[k] for k in ("profile_id", "scenario_id", "stratum", "behavior", "minute")} |
                                   {"arm": arm, "resolution": res, "engagement": level, "threshold": threshold} |
                                   evaluate_surface(snap["surface_cells"], pair["truth"], snap["truth_cell"], res, coverage, cap, threshold))
    print(f"Evaluated {len(records)} condition records in {time.monotonic()-started:.2f}s; bootstrap={args.bootstrap}", flush=True)
    summary = build_summary(records, audit["profiles"], args.bootstrap, args.seed)
    source_paths = [Path(__file__), BACKEND / "app/phase3/alerts.py", BACKEND / "app/geo/h3grid.py", BACKEND / "app/config.py"]
    result = {"metadata": {"created_utc": datetime.now(timezone.utc).isoformat(),
                           "targeting_policy": "legacy_peak_threshold",
                           "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=BACKEND, text=True).strip(),
                           "git_branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=BACKEND, text=True).strip(),
                           "input": str(args.input.resolve()), "input_sha256": sha256(args.input),
                           "source_sha256": {str(p.relative_to(BACKEND)): sha256(p) for p in source_paths},
                           "versions": {"python": platform.python_version(), "h3": h3.__version__, "numpy": np.__version__},
                           "settings": {"coverage": coverage, "max_cells": cap, "thresholds": dict(settings.push_prob_threshold),
                                        "production_resolution_unchanged": settings.push_target_res, "evaluated_resolutions": [7, 8]},
                           "bootstrap": {"unit": "profile_id", "paired": True, "replicates": args.bootstrap, "seed": args.seed,
                                         "interval": "percentile 95%; exploratory, no multiplicity adjustment"},
                           "inclusion_loss_margin": None, "success_verdict": "not_assessed", "elapsed_seconds": time.monotonic()-started},
              "audit": audit, "summary": summary}
    args.output_dir.mkdir(parents=True)
    (args.output_dir / "snapshots.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n" for r in records), encoding="utf-8")
    (args.output_dir / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (args.output_dir / "REPORT.md").write_text(render_report(result), encoding="utf-8")
    print(f"Saved {args.output_dir.resolve()} ({time.monotonic()-started:.2f}s)", flush=True)


if __name__ == "__main__":
    main()

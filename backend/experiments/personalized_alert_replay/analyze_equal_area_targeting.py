"""Exploratory res8 mass-ranked targeting at predeclared common area caps.

No production-policy change, push, model calls, or threshold tuning.
"""
from collections import defaultdict
from datetime import datetime, timezone
import argparse
import json
import math
from pathlib import Path
import subprocess
import time

import h3
import numpy as np

from experiments.personalized_alert_replay.analyze_targeting_resolution import (
    HERE, BACKEND, area, load_pairs, sha256,
)

BUDGETS = (.5, 1., 2., 3., 5., 7., 10., 15., 20.)
TARGETS = (.7, .8, .9)
SEED = 20260924
REPLICATES = 10000


def rank_parents(poa):
    masses = defaultdict(list)
    for cell, prob in poa.items():
        masses[h3.cell_to_parent(cell, 8)].append(prob)
    return sorted(((c, math.fsum(ps)) for c, ps in masses.items()), key=lambda x: (-x[1], x[0]))


def select_prefix(ranked, budget):
    selected, used = [], 0.
    for cell, _ in ranked:
        next_area = area(cell)
        if used + next_area > budget + 1e-12:
            break
        selected.append(cell)
        used += next_area
    return selected, used


def aggregate(rows):
    n = len(rows)
    return {"n": n, "hits": sum(r['hit'] for r in rows),
            "inclusion_rate": sum(r['hit'] for r in rows) / n,
            "mean_area_km2": math.fsum(r['area_km2'] for r in rows) / n,
            "mean_cells": sum(r['cell_count'] for r in rows) / n,
            "empty_n": sum(r['cell_count'] == 0 for r in rows),
            "exhausted_support_n": sum(r['support_exhausted'] for r in rows)}


def run(input_path, out):
    if out.exists():
        raise ValueError('Choose a new output directory; existing results are preserved')
    start = time.monotonic()
    pairs, audit = load_pairs(input_path)
    records = []
    for p in pairs:
        truth = h3.latlng_to_cell(p['truth']['lat'], p['truth']['lng'], 8)
        for arm in 'BC':
            ranked = rank_parents(p['snapshots'][arm]['surface_cells'])
            for budget in BUDGETS:
                selected, used = select_prefix(ranked, budget)
                records.append({k: p[k] for k in ('profile_id', 'scenario_id', 'minute', 'stratum', 'behavior')} |
                               {'arm': arm, 'budget_km2': budget, 'area_km2': used, 'cell_count': len(selected),
                                'cells': selected, 'truth_cell': truth, 'hit': truth in selected,
                                'support_exhausted': len(selected) == len(ranked),
                                'truth_in_full_support': truth in {c for c, _ in ranked}})
    profiles = audit['profiles']
    draws = np.random.default_rng(SEED).integers(0, len(profiles), (REPLICATES, len(profiles)))
    groups, diffs, by_profile = {}, {}, {}
    for budget in BUDGETS:
        k = str(budget)
        subsets = {a: [r for r in records if r['budget_km2'] == budget and r['arm'] == a] for a in 'BC'}
        groups[k] = {a: aggregate(rs) for a, rs in subsets.items()}
        by_profile[k] = {p: {a: aggregate([r for r in subsets[a] if r['profile_id'] == p]) for a in 'BC'} for p in profiles}
        vectors = np.array([[by_profile[k][p]['B']['n'], by_profile[k][p]['B']['hits'], by_profile[k][p]['C']['hits']] for p in profiles])
        boot = vectors[draws].sum(axis=1)
        samples = 100 * (boot[:, 2] - boot[:, 1]) / boot[:, 0]
        diffs[k] = {'C_minus_B_pp': 100 * (groups[k]['C']['inclusion_rate'] - groups[k]['B']['inclusion_rate']),
                    'ci95_pp': np.quantile(samples, [.025, .975]).tolist()}
    targets = {}
    for target in TARGETS:
        targets[str(target)] = {}
        for arm in 'BC':
            reached = [b for b in BUDGETS if groups[str(b)][arm]['inclusion_rate'] >= target]
            first = reached[0] if reached else None
            targets[str(target)][arm] = None if first is None else {
                'first_tested_budget_km2': first, **groups[str(first)][arm]}
    saturation = {a: sum(r['truth_in_full_support'] for r in records if r['arm'] == a and r['budget_km2'] == BUDGETS[0]) for a in 'BC'}
    result = {'metadata': {'created_utc': datetime.now(timezone.utc).isoformat(),
                           'input': str(input_path.resolve()), 'input_sha256': sha256(input_path),
                           'source_sha256': sha256(Path(__file__)),
                           'shared_helper_sha256': sha256(HERE / 'analyze_targeting_resolution.py'),
                           'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=BACKEND, text=True).strip(),
                           'resolution': 8, 'budgets_km2': BUDGETS, 'target_inclusion_rates': TARGETS,
                           'ranking': 'descending sum of res9 probabilities per logical res8 parent; ties by cell ID',
                           'selection': 'longest ranked prefix fitting cap; stop, do not skip cells or pad beyond support',
                           'truth': 'direct coordinate indexing at res8',
                           'bootstrap': {'unit': 'profile_id', 'paired': True, 'seed': SEED, 'replicates': REPLICATES,
                                         'interval': 'pointwise percentile 95%, exploratory, no multiplicity correction'},
                           'elapsed_seconds': time.monotonic() - start},
              'audit': audit, 'groups': groups, 'paired_differences': diffs, 'by_profile': by_profile,
              'target_crossings': targets, 'full_support_hits': saturation}
    lines = ['# 同一 면적 한도에서의 res8 타겟팅 비교'.replace('同一', '동일'), '',
             '## 결론을 읽는 기준', '',
             '같은 면적 한도에서 개인화 C와 비개인화 B의 정답 포함률을 비교한다. 운영 정책을 그대로 재현하는 실험이 아니라 위치 순위 선정의 실익을 보는 후속 탐색이다.', '',
             '## 고정 조건과 해석 범위', '',
             f"- 인물 {len(profiles)}명·시나리오 {audit['scenarios']}개·{len(pairs)}시점. 입력 파일과 SHA-256은 summary.json에 기록했다.",
             '- res9 확률을 res8 부모별로 합산해 내림차순 정렬했다. 동점은 셀 ID 순으로 처리했다.',
             '- 참여도 문턱과 누적 80% 절단을 적용하지 않았다. 두 요소와 구역 점수 방식이 함께 바뀌므로 이전 실험과의 차이를 문턱 효과 하나로 해석하지 않는다.',
             '- 면적 한도 0.5·1·2·3·5·7·10·15·20km²와 목표 포함률 70·80·90%를 실행 전에 정했다.',
             '- 셀을 쪼개지 않고 순위 접두부만 선택했다. 다음 셀이 한도를 넘으면 멈추며, 확률이 없는 구역으로 채우지 않았다. 따라서 동일한 것은 면적 한도이고 실제 사용 면적은 다르다.',
             '- 인물 단위 대응 부트스트랩 10,000회, seed=20260924, 점별 95% 구간. 9명 소표본·반복 비교에 대한 탐색적 결과이며 비열등 판정은 하지 않는다.',
             '- 과거 결과를 본 동일 데이터의 후속 분석이므로 독립 검증이 아니다. 새로운 설정 채택에는 별도 데이터 검증이 필요하다.', '',
             '## 면적 한도별 결과', '',
             '| 한도 km² | B 실제 평균 면적 | C 실제 평균 면적 | B 평균 셀 수 | C 평균 셀 수 | B 포함 | C 포함 | C−B %p [95% 구간] |',
             '|---:|---:|---:|---:|---:|---|---|---|']
    for budget in BUDGETS:
        k = str(budget); b, c = groups[k]['B'], groups[k]['C']; delta = diffs[k]
        lo, hi = delta['ci95_pp']
        lines.append(f"| {budget:g} | {b['mean_area_km2']:.3f} | {c['mean_area_km2']:.3f} | {b['mean_cells']:.2f} | {c['mean_cells']:.2f} | {b['hits']}/{b['n']} ({100*b['inclusion_rate']:.2f}%) | {c['hits']}/{c['n']} ({100*c['inclusion_rate']:.2f}%) | {delta['C_minus_B_pp']:+.2f} [{lo:+.2f}, {hi:+.2f}] |")
    lines += ['', '## 목표 포함률에 처음 도달한 시험 한도', '',
              '| 목표 포함률 | B 한도 / 실제 평균 면적 | C 한도 / 실제 평균 면적 |', '|---|---|---|']
    for target, arms in targets.items():
        vals = ['미도달' if arms[a] is None else f"{arms[a]['first_tested_budget_km2']:g} / {arms[a]['mean_area_km2']:.3f}km²" for a in 'BC']
        lines.append(f"| {100*float(target):g}% | {' | '.join(vals)} |")
    lines += ['', '이는 미리 정한 한도 중 처음 도달한 지점이다. 정확히 같은 포함률을 맞춘 최소 면적 추정이 아니며, 한도 사이를 보간하거나 목표에 맞춰 재조정하지 않았다.', '',
              f"전체 예측 부모 구역을 모두 선택했을 때 포함 가능한 정답은 B {saturation['B']}/{len(pairs)}, C {saturation['C']}/{len(pairs)}다. 확률이 없는 구역은 예산을 늘려도 추가하지 않으므로 포함률 상한이 다를 수 있다.", '',
              '## 인물별 결과', '', '| 한도 km² | 인물 | B 포함 | C 포함 |', '|---:|---|---|---|']
    for k, ps in by_profile.items():
        for p, arms in ps.items():
            lines.append(f"| {float(k):g} | {p} | {arms['B']['hits']}/{arms['B']['n']} | {arms['C']['hits']}/{arms['C']['n']} |")
    lines += ['', '## 재현', '',
              'backend에서 `python -B -X utf8 -m experiments.personalized_alert_replay.analyze_equal_area_targeting --output-dir <새 결과 경로>`를 실행한다. 기존 출력 경로는 덮어쓰지 않는다.',
              '실제 기기·푸시·모델 호출은 없으며 기존 분석 코드와 운영 설정은 변경하지 않았다.', '']
    out.mkdir(parents=True)
    (out / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    (out / 'snapshots.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False, allow_nan=False)+'\n' for r in records), encoding='utf-8')
    (out / 'REPORT.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'Saved {len(records)} records in {time.monotonic()-start:.2f}s: {out.resolve()}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=HERE / 'results/persona_abc_v2_r1.jsonl')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    run(args.input, args.output_dir)

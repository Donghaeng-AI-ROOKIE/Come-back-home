"""Isolate res8 parent MAX versus SUM ranking under identical area caps."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
import time

import h3
import numpy as np

from experiments.personalized_alert_replay.analyze_equal_area_targeting import (
    BUDGETS, SEED, REPLICATES, aggregate, select_prefix,
)
from experiments.personalized_alert_replay.analyze_targeting_resolution import (
    HERE, BACKEND, load_pairs, sha256,
)


def rank_parents(poa, mode):
    if mode not in ('max', 'sum'):
        raise ValueError(mode)
    groups = defaultdict(list)
    for cell, prob in poa.items():
        groups[h3.cell_to_parent(cell, 8)].append(prob)
    score = max if mode == 'max' else math.fsum
    return sorted(((cell, score(values)) for cell, values in groups.items()),
                  key=lambda x: (-x[1], x[0]))


def paired_effect(base, candidate, profiles, draws):
    key = lambda r: (r['profile_id'], r['scenario_id'], r['minute'])
    b, c = {key(r): r for r in base}, {key(r): r for r in candidate}
    if b.keys() != c.keys() or len(b) != len(base) or len(c) != len(candidate):
        raise ValueError('Unpaired records')
    vectors = []
    for profile in profiles:
        keys = [k for k in b if k[0] == profile]
        vectors.append([len(keys), sum(c[k]['hit'] - b[k]['hit'] for k in keys),
                        sum(c[k]['area_km2'] - b[k]['area_km2'] for k in keys)])
    arr = np.asarray(vectors, dtype=float)
    total, boot = arr.sum(axis=0), arr[draws].sum(axis=1)
    gained = sum(c[k]['hit'] and not b[k]['hit'] for k in b)
    lost = sum(b[k]['hit'] and not c[k]['hit'] for k in b)
    return {'inclusion_difference_pp': 100*total[1]/total[0],
            'ci95_pp': np.quantile(100*boot[:, 1]/boot[:, 0], [.025, .975]).tolist(),
            'mean_area_difference_km2': total[2]/total[0],
            'gained_n': gained, 'lost_n': lost,
            'same_selected_set_n': sum(set(b[k]['cells']) == set(c[k]['cells']) for k in b)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    out = args.output_dir
    if out.exists():
        parser.error('Output exists: choose a new directory')
    start = time.monotonic()
    source = HERE / 'results/persona_abc_v2_r1.jsonl'
    pairs, audit = load_pairs(source)
    records = []
    for p in pairs:
        truth = h3.latlng_to_cell(p['truth']['lat'], p['truth']['lng'], 8)
        for arm in 'BC':
            for mode in ('max', 'sum'):
                ranked = rank_parents(p['snapshots'][arm]['surface_cells'], mode)
                for budget in BUDGETS:
                    cells, used = select_prefix(ranked, budget)
                    records.append({k: p[k] for k in ('profile_id', 'scenario_id', 'minute', 'stratum', 'behavior')} |
                                   {'arm': arm, 'mode': mode, 'budget_km2': budget,
                                    'cells': cells, 'cell_count': len(cells), 'area_km2': used,
                                    'hit': truth in cells, 'truth_cell': truth,
                                    'support_exhausted': len(cells) == len(ranked)})
    profiles = audit['profiles']
    draws = np.random.default_rng(SEED).integers(0, len(profiles), (REPLICATES, len(profiles)))
    groups, subsets = {}, {}
    for budget in BUDGETS:
        for mode in ('max', 'sum'):
            for arm in 'BC':
                k = f'{budget}/{mode}/{arm}'
                subsets[k] = [r for r in records if r['budget_km2'] == budget and r['mode'] == mode and r['arm'] == arm]
                groups[k] = aggregate(subsets[k])
    scoring, personalization, by_profile = {}, {}, {}
    for budget in BUDGETS:
        for arm in 'BC':
            key = f'{budget}/{arm}'
            scoring[key] = paired_effect(subsets[f'{budget}/max/{arm}'], subsets[f'{budget}/sum/{arm}'], profiles, draws)
            by_profile[key] = {p: {mode: aggregate([r for r in subsets[f'{budget}/{mode}/{arm}'] if r['profile_id'] == p])
                                  for mode in ('max', 'sum')} for p in profiles}
        for mode in ('max', 'sum'):
            personalization[f'{budget}/{mode}'] = paired_effect(subsets[f'{budget}/{mode}/B'], subsets[f'{budget}/{mode}/C'], profiles, draws)
    result = {'metadata': {'created_utc': datetime.now(timezone.utc).isoformat(),
                           'input_sha256': sha256(source), 'input': str(source.resolve()),
                           'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=BACKEND, text=True).strip(),
                           'source_sha256': {p.name: sha256(p) for p in (Path(__file__), HERE/'analyze_equal_area_targeting.py', HERE/'analyze_targeting_resolution.py')},
                           'resolution': 8, 'budgets_km2': BUDGETS, 'threshold': None, 'coverage_cutoff': None,
                           'selection': 'descending score then cell ID; same longest prefix within cap, no padding',
                           'bootstrap': {'unit': 'profile_id', 'paired': True, 'replicates': REPLICATES, 'seed': SEED,
                                         'interval': 'pointwise percentile 95%; exploratory, no multiplicity correction'},
                           'elapsed_seconds': time.monotonic()-start},
              'audit': audit, 'groups': groups, 'sum_minus_max': scoring,
              'personalization_C_minus_B': personalization, 'by_profile': by_profile}
    lines = ['# res8 부모 구역 점수: 최고값 대 합산값', '',
             '## 목적과 고정 조건', '',
             '같은 예측·면적 한도에서 부모 구역 점수만 바꾸어 정답 포함률 변화를 비교한다. B는 비개인화, C는 개인화다.',
             '- 9명·27개 시나리오·108시점, res8, 면적 한도 0.5·1·2·3·5·7·10·15·20km².',
             '- 최고값은 부모 안 가장 높은 res9 확률, 합산값은 부모 안 res9 확률 합이다. 최고 상대확률은 양의 전역 상수로 환산되므로 동일 입력에서 최고 원확률과 순위가 같다.',
             '- 두 방식 모두 참여도 문턱·누적 80% 절단 없음. 후보 부모 집합·동점 처리(셀 ID순)·면적 제한·정답 좌표·재표집 조건은 같다.',
             '- 다음 순위 셀이 한도를 넘으면 중단한다. 같은 것은 면적 한도이며 실제 사용 면적 차이도 보고한다.',
             '- 인물 단위 대응 부트스트랩 10,000회, seed=20260924, 점별 95% 구간. 소표본·여러 한도 비교·동일 데이터 재분석이므로 탐색적 결과다.',
             '- 참여도 문턱 제거의 단독 효과나 실제 발송·수신자 수는 이번에 검증하지 않는다.', '',
             '## 주 비교: 같은 예측에서 합산 − 최고값', '',
             '| 한도 km² | 예측 | 최고값 포함 | 합산 포함 | 차이 %p [95% 구간] | 얻은/잃은 시점 | 같은 선택집합 | 실제 평균 면적 최고/합산 km² |',
             '|---:|---|---|---|---|---|---|---|']
    for budget in BUDGETS:
        for arm in 'BC':
            a, b = [groups[f'{budget}/{m}/{arm}'] for m in ('max', 'sum')]
            e = scoring[f'{budget}/{arm}']; lo, hi = e['ci95_pp']
            lines.append(f"| {budget:g} | {arm} | {a['hits']}/108 ({100*a['inclusion_rate']:.2f}%) | {b['hits']}/108 ({100*b['inclusion_rate']:.2f}%) | {e['inclusion_difference_pp']:+.2f} [{lo:+.2f}, {hi:+.2f}] | {e['gained_n']}/{e['lost_n']} | {e['same_selected_set_n']}/108 | {a['mean_area_km2']:.4f}/{b['mean_area_km2']:.4f} |")
    lines += ['', '## 보조 비교: 점수 방식별 개인화 C − 비개인화 B', '',
              '| 한도 km² | 점수 | C−B %p [95% 구간] |', '|---:|---|---|']
    for budget in BUDGETS:
        for mode in ('max', 'sum'):
            e = personalization[f'{budget}/{mode}']; lo, hi = e['ci95_pp']
            lines.append(f"| {budget:g} | {mode} | {e['inclusion_difference_pp']:+.2f} [{lo:+.2f}, {hi:+.2f}] |")
    lines += ['', '이 표는 개인화 효과이고 위 표는 점수 방식 변경 효과다. 합산이 좋아졌다는 것만으로 개인화 우위가 입증되는 것은 아니다.', '',
              '## 인물별 결과', '', '| 한도 km² | 예측 | 인물 | 최고값 포함 | 합산 포함 |', '|---:|---|---|---|---|']
    for key, values in by_profile.items():
        budget, arm = key.split('/')
        for p, g in values.items():
            lines.append(f"| {float(budget):g} | {arm} | {p} | {g['max']['hits']}/12 | {g['sum']['hits']}/12 |")
    lines += ['', '## 한계와 재현', '',
              '0.5km²의 빈 선택이나 넓은 한도에서 모든 정답을 포함하는 경우는 정책의 실효성 입증이 아니다. 같은 포함률 관측값이나 0을 포함하는 구간을 비열등성 입증으로 해석하지 않는다.',
              '이번 변경의 효과는 문턱 없는 고정 면적 정책에 한정된다. 운영에 참여도 문턱을 다시 붙였을 때도 유지되는지는 별도 검증해야 한다.',
              '`python -B -X utf8 -m experiments.personalized_alert_replay.compare_parent_scoring --output-dir <새 경로>` (backend에서 실행). 기존 출력 경로는 덮어쓰지 않는다.', '']
    out.mkdir(parents=True)
    (out/'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    (out/'snapshots.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False, allow_nan=False)+'\n' for r in records), encoding='utf-8')
    (out/'REPORT.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'Saved {len(records)} records in {time.monotonic()-start:.2f}s: {out.resolve()}')


if __name__ == '__main__':
    main()

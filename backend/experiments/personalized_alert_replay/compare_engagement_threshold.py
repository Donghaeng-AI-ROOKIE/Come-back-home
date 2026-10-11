"""Offline threshold ablation: preserve 80%-selected parents and max scores."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess

import h3
import numpy as np

from app.config import settings
from app.geo import h3grid
from app.phase3 import alerts
from experiments.personalized_alert_replay.analyze_targeting_resolution import HERE, BACKEND, load_pairs, area, sha256
from experiments.personalized_alert_replay.analyze_equal_area_targeting import SEED, REPLICATES, select_prefix, aggregate
from experiments.personalized_alert_replay.compare_parent_scoring import paired_effect


def select_conditions(poa, res):
    selected = alerts.select_alert_cells(poa, coverage=settings.alert_coverage, max_cells=settings.max_alert_cells)
    # Preserve this archived threshold ablation; current delivery uses geographic
    # coverage and no engagement-dependent second probability cutoff.
    parents = h3grid.parent_cells(selected, res)
    rel = alerts.relative_prob_by_parent(poa, res=res)
    ranked = sorted(((c, rel.get(c, 0.)) for c in parents), key=lambda x: (-x[1], x[0]))
    choices = {'off': sorted(parents)}
    for level, threshold in settings.push_prob_threshold.items():
        chosen = sorted(c for c in parents if not rel or rel.get(c, 0.) >= threshold)
        choices[f'on/{level}'] = chosen
        # Same snapshot's historical dispatch area, no tuning against truth.
        cap = math.fsum(area(c) for c in chosen)
        choices[f'matched/{level}'] = sorted(select_prefix(ranked, cap)[0])
    return selected, choices


def area_effect(base, candidate, profiles, draws):
    vectors = np.array([[math.fsum(r['area_km2'] for r in rows if r['profile_id'] == p)
                         for rows in (base, candidate)] for p in profiles])
    total, boot = vectors.sum(axis=0), vectors[draws].sum(axis=1)
    with np.errstate(divide='ignore', invalid='ignore'):
        samples = 100*(boot[:, 1]/boot[:, 0]-1)
    samples = samples[np.isfinite(samples)]
    return {'increase_pct': 100*(total[1]/total[0]-1) if total[0] else None,
            'ci95_pct': np.quantile(samples,[.025,.975]).tolist() if len(samples) else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    out = args.output_dir
    if out.exists():
        parser.error('Existing output is preserved; choose a new path')
    source = HERE/'results/persona_abc_v2_r1.jsonl'
    pairs, audit = load_pairs(source)
    records = []
    for p in pairs:
        for arm in 'BC':
            for res in (7, 8):
                selected, choices = select_conditions(p['snapshots'][arm]['surface_cells'], res)
                truth = h3.latlng_to_cell(p['truth']['lat'],p['truth']['lng'],res)
                for policy, cells in choices.items():
                    records.append({k:p[k] for k in ('profile_id','scenario_id','minute','stratum','behavior')} |
                                   {'arm':arm,'resolution':res,'policy':policy,'cells':cells,'cell_count':len(cells),
                                    'selected_res9':selected,'truth_cell':truth,'hit':truth in cells,
                                    'area_km2':math.fsum(area(c) for c in cells),
                                    'support_exhausted':policy=='off'})
    profiles = audit['profiles']
    draws = np.random.default_rng(SEED).integers(0,len(profiles),(REPLICATES,len(profiles)))
    subsets = {}
    for r in records:
        key=f"res{r['resolution']}/{r['arm']}/{r['policy']}"
        subsets.setdefault(key,[]).append(r)
    groups={k:aggregate(v) for k,v in subsets.items()}
    by_profile={k:{p:aggregate([r for r in rows if r['profile_id']==p]) for p in profiles} for k,rows in subsets.items()}
    changes, matched, personalization = {}, {}, {}
    for res in (7,8):
        for arm in 'BC':
            off=subsets[f'res{res}/{arm}/off']
            for level in settings.push_prob_threshold:
                key=f'res{res}/{arm}/{level}'
                on=subsets[f'res{res}/{arm}/on/{level}']
                changes[key]=paired_effect(on,off,profiles,draws) | {'area':area_effect(on,off,profiles,draws)}
                matched[key]=paired_effect(on,subsets[f'res{res}/{arm}/matched/{level}'],profiles,draws)
        for policy in ['off']+[f'on/{l}' for l in settings.push_prob_threshold]:
            b,c=[subsets[f'res{res}/{a}/{policy}'] for a in 'BC']
            personalization[f'res{res}/{policy}']=paired_effect(b,c,profiles,draws) | {'C_area_change_pct':area_effect(b,c,profiles,draws)}
    result={'metadata':{'created_utc':datetime.now(timezone.utc).isoformat(),'input_sha256':sha256(source),
                        'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=BACKEND,text=True).strip(),
                        'source_sha256':{p.name:sha256(p) for p in [Path(__file__),HERE/'analyze_targeting_resolution.py',HERE/'analyze_equal_area_targeting.py',HERE/'compare_parent_scoring.py']},
                        'settings':{'coverage':settings.alert_coverage,'max_cells':settings.max_alert_cells,'thresholds':dict(settings.push_prob_threshold),'production_res_unchanged':settings.push_target_res},
                        'bootstrap':{'unit':'profile_id','paired':True,'seed':SEED,'replicates':REPLICATES,'interval':'pointwise percentile 95%; exploratory, no multiplicity adjustment'},
                        'primary_resolution':8,'secondary_resolution':7,
                        'matched_area_policy':'remove threshold, rank same selected parents by max relative score, longest prefix capped by same snapshot on-policy area'},
            'audit':audit,'groups':groups,'off_minus_on':changes,'matched_minus_on':matched,
            'personalization_C_minus_B':personalization,'by_profile':by_profile}
    lines=['# 参加度 문턱 적용·미적용 비교'.replace('参加度','참여도'),'','## 실험 조건','',
           '목적은 같은 예측에서 참여도별 확률 문턱만 제거했을 때 정답 포함률과 발송면적의 변화를 확인하는 것이다. B는 비개인화, C는 개인화다.', '',
           '- 동일 9명·27개 시나리오·108시점. res8 주 비교, res7 보조 비교.',
           '- 운영 함수의 누적 80% res9 선택·최대 500셀·부모 최고 상대확률을 유지했다. 부모 확률 합산 방식은 이번에 사용하지 않았다.',
           '- on: high=.30/normal=.45/low=.60. off: 선택된 부모 구역을 모두 유지. off는 참여도와 무관한 동일 정책이며 세 번의 독립 실험이 아니다.',
           '- matched: 문턱은 제거하되 같은 시점의 on 발송면적을 상한으로 주고 최고 상대확률순으로 선택한다. 정답을 보고 한도를 조정하지 않는다.',
           '- 정답은 좌표에서 해상도로 직접 변환한다. 인물 단위 대응 부트스트랩 10,000회·seed=20260924·점별 95% 구간. 독립 데이터 검증이나 다중비교 보정은 하지 않았다.',
           '- 실제 푸시·재알림 빈도·알림 피로도는 측정하지 않았다. 참여도를 빈도에 적용하는 후속 운영 설계의 효과는 이 실험으로 판단하지 않는다.', '',
           '## 문턱 제거 효과','',
           '| 해상도 | 예측 | 기존 참여도 | 포함 on→off | 차이 %p [95% 구간] | 평균 면적 on→off km² | 면적 증가 % [95% 구간] |',
           '|---|---|---|---|---|---|---|']
    for res in (8,7):
        for arm in 'BC':
            for level in settings.push_prob_threshold:
                x,y=groups[f'res{res}/{arm}/on/{level}'],groups[f'res{res}/{arm}/off']
                e=changes[f'res{res}/{arm}/{level}']; lo,hi=e['ci95_pp']; al,ah=e['area']['ci95_pct']
                lines.append(f"| {res} | {arm} | {level} | {x['hits']}/108 ({100*x['inclusion_rate']:.2f}%) → {y['hits']}/108 ({100*y['inclusion_rate']:.2f}%) | {e['inclusion_difference_pp']:+.2f} [{lo:+.2f}, {hi:+.2f}] | {x['mean_area_km2']:.3f} → {y['mean_area_km2']:.3f} | {e['area']['increase_pct']:+.2f} [{al:+.2f}, {ah:+.2f}] |")
    lines+=['','## 同一 면적 상한으로 되돌렸을 때'.replace('同一','동일'),'','| 해상도/예측/참여도 | on과 같은 선택집합 | 포함률 변화 %p | 평균 면적 차이 km² |','|---|---|---:|---:|']
    for key,e in matched.items():
        lines.append(f"| {key} | {e['same_selected_set_n']}/108 | {e['inclusion_difference_pp']:+.2f} | {e['mean_area_difference_km2']:.8f} |")
    lines+=['','## 문턱 없는 정책에서 개인화 효과','','| 해상도 | B 포함 | C 포함 | C−B %p [95% 구간] | B 평균 면적 | C 평균 면적 | C 면적 감소율 |','|---|---|---|---|---:|---:|---:|']
    for res in (8,7):
        b,c=[groups[f'res{res}/{a}/off'] for a in 'BC']; e=personalization[f'res{res}/off']; lo,hi=e['ci95_pp']
        lines.append(f"| {res} | {b['hits']}/108 ({100*b['inclusion_rate']:.2f}%) | {c['hits']}/108 ({100*c['inclusion_rate']:.2f}%) | {e['inclusion_difference_pp']:+.2f} [{lo:+.2f}, {hi:+.2f}] | {b['mean_area_km2']:.3f} | {c['mean_area_km2']:.3f} | {-e['C_area_change_pct']['increase_pct']:.2f}% |")
    lines+=['','## 인물별 res8 normal 비교','','| 인물 | 예측 | 포함 on→off | 평균 면적 on→off km² |','|---|---|---|---|']
    for profile in profiles:
        for arm in 'BC':
            b,c=[by_profile[f'res8/{arm}/{policy}'][profile] for policy in ('on/normal','off')]
            lines.append(f"| {profile} | {arm} | {b['hits']}/12 → {c['hits']}/12 | {b['mean_area_km2']:.3f} → {c['mean_area_km2']:.3f} |")
    lines+=['','## 解釈の限界'.replace('解釈の限界','解釈の限界'),'',
           '문턱 제거는 대상 집합의 확대이므로 동일 예측의 정답 포함률이 낮아질 수 없다. 포함률 상승만을 선정 능력 개선으로 해석하지 않는다. 면적 확대 비용, 비개인화 대비 차이, 동일 면적 대조를 함께 본다.',
           '허용 손실폭을 정하지 않았으므로 정확도 유지·비열등 판정은 하지 않는다. 실제 수신자 감소나 시민 부담 개선은 별도 데이터가 필요하다.',
           '`python -B -X utf8 -m experiments.personalized_alert_replay.compare_engagement_threshold --output-dir <새 결과 경로>` (backend에서 실행). 기존 결과와 운영 설정은 변경하지 않는다.','']
    lines=[l.replace('## 解釈の限界','## 해석 한계와 재현') for l in lines]
    out.mkdir(parents=True)
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    (out/'snapshots.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n' for r in records),encoding='utf-8')
    (out/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    print(f'Saved {len(records)} conditions: {out.resolve()}')


if __name__=='__main__':
    main()

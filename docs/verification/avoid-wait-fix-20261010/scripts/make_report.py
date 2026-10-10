"""Build the Korean result report and monochrome SVG figures from saved outputs only."""
import json, sys
from pathlib import Path

X = Path(sys.argv[1]); A = X / 'analysis'
R = json.loads((A / 'final_summary.json').read_text())
T = {t['person_id']: t for t in json.loads((A / 'person_table.json').read_text())}
EV = R['evaluation']; SV = R['service_comparison_evaluation']; PRE = R['preliminary_map_evaluation']


def pct(x): return '—' if x is None else f'{x * 100:.1f}%'
def km(x): return '—' if x is None else f'{x:.2f}'
def ci(e, scale=100, unit='%p'):
    if not e: return '—'
    return f"{e['delta'] * scale:+.2f}{unit} [{e['ci95'][0] * scale:+.2f}, {e['ci95'][1] * scale:+.2f}]"


def rows(path):
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


# ---------- SVG: equal-area curve (monochrome)
budgets = [.25, .5, 1, 2, 4, 8, 12, 20, 30]
series = [('현재 배포본 D', EV['deployed_D']['equal_area_map_hit'], '#000', ''),
          ('수정본 D', EV['fixed_D']['equal_area_map_hit'], '#000', '6,4'),
          ('구성요소 C(초기 개인화, 행동 규칙 없음)', EV['component_fixed_engine']['C_initial_person']['equal_area_map_hit'], '#888', '2,3')]
W, H, L, B, TOP, RGT = 640, 360, 60, 50, 30, 20
def xs(b):  # log-ish spacing by index
    return L + (W - L - RGT) * budgets.index(b) / (len(budgets) - 1)
def ys(v): return TOP + (H - TOP - B) * (1 - v / .6)
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="Apple SD Gothic Neo, sans-serif" font-size="12">',
       f'<rect width="{W}" height="{H}" fill="#fff"/>',
       f'<text x="{L}" y="18" font-size="13">같은 면적 예산에서의 합성 위치 포함률 (평가 32명, 이미 본 자료의 개발 재평가)</text>']
for v in (0, .1, .2, .3, .4, .5, .6):
    svg.append(f'<line x1="{L}" x2="{W - RGT}" y1="{ys(v):.1f}" y2="{ys(v):.1f}" stroke="#ddd"/><text x="{L - 8}" y="{ys(v) + 4:.1f}" text-anchor="end">{int(v * 100)}%</text>')
for b in budgets:
    svg.append(f'<text x="{xs(b):.1f}" y="{H - B + 18}" text-anchor="middle">{b:g}</text>')
svg.append(f'<text x="{(L + W - RGT) / 2}" y="{H - 10}" text-anchor="middle">지도 상위 셀 면적 예산 (㎢)</text>')
for i, (name, d, color, dash) in enumerate(series):
    pts = ' '.join(f'{xs(b):.1f},{ys(d[str(b)]):.1f}' for b in budgets)
    svg.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2" stroke-dasharray="{dash}"/>')
    for b in budgets:
        svg.append(f'<circle cx="{xs(b):.1f}" cy="{ys(d[str(b)]):.1f}" r="2.5" fill="{color}"/>')
    y = TOP + 18 + i * 16
    svg.append(f'<line x1="{L + 12}" x2="{L + 40}" y1="{y}" y2="{y}" stroke="{color}" stroke-width="2" stroke-dasharray="{dash}"/><text x="{L + 46}" y="{y + 4}">{name}</text>')
svg.append('</svg>')
(A / 'equal_area_curve.svg').write_text('\n'.join(svg) + '\n')

# ---------- SVG: per-person map containment, deployed -> fixed (evaluation people)
ev_people = [p for p in sorted(T) if T[p]['split'] == 'evaluation']
W2, H2, L2 = 680, 40 + 16 * len(ev_people), 70
def xp(v): return L2 + (W2 - L2 - 20) * v
s2 = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W2} {H2 + 30}" font-family="Apple SD Gothic Neo, sans-serif" font-size="11">',
      f'<rect width="{W2}" height="{H2 + 30}" fill="#fff"/>',
      f'<text x="{L2}" y="16" font-size="13">사람별 지도 포함률: 배포본(○) → 수정본(●), 24회 판정</text>']
for v in (0, .25, .5, .75, 1):
    s2.append(f'<line x1="{xp(v):.1f}" x2="{xp(v):.1f}" y1="26" y2="{H2}" stroke="#eee"/><text x="{xp(v):.1f}" y="{H2 + 14}" text-anchor="middle">{int(v * 100)}%</text>')
for i, p in enumerate(ev_people):
    y = 36 + 16 * i; t = T[p]; a, b = t['deployed_map_hit'], t['fixed_map_hit']
    s2.append(f'<text x="{L2 - 8}" y="{y + 4}" text-anchor="end">{p} {t["family"]}</text>')
    s2.append(f'<line x1="{xp(a):.1f}" x2="{xp(b):.1f}" y1="{y}" y2="{y}" stroke="#000"/>')
    s2.append(f'<circle cx="{xp(a):.1f}" cy="{y}" r="4" fill="#fff" stroke="#000"/><circle cx="{xp(b):.1f}" cy="{y}" r="3" fill="#000"/>')
s2.append('</svg>')
(A / 'person_containment.svg').write_text('\n'.join(s2) + '\n')

# ---------- controlled checks
wd = {(r['person_id'], r['wait_rule_id']): r for r in json.loads((X / 'controlled/wait_deployed.json').read_text()) if r['recognition'] == 'false'}
wf = {(r['person_id'], r['wait_rule_id']): r for r in json.loads((X / 'controlled/wait_fixed3.json').read_text()) if r['recognition'] == 'false'}
att = {r['person_id']: r for r in json.loads((X / 'controlled/attribution_fixed3.json').read_text())}
cls = json.loads((X / 'controlled/early_departure_classification.json').read_text())
votes = {}
for c in cls:
    votes.setdefault(c['label'].split(':')[1], []).append(c['category'])
e27fix = json.loads((X / 'controlled/attribution_fixed3_E27fix.json').read_text())[0]
avd = json.loads((X / 'controlled/avoid_E20_deployed.json').read_text()); avf = json.loads((X / 'controlled/avoid_E20_fixed3.json').read_text())
e27 = {}
for lab, p in (('배포본', 'out_deployed'), ('수정본(저장 정책)', 'out_final'), ('수정본 + E27 해석 수정', 'out_final_E27fix')):
    z = [r for r in rows(X / p / 'metrics_rows_v2.jsonl') if r['person_id'] == 'E27' and r['arm'] == 'D_full_prepared']
    c = [r for r in z if r['complete']]
    e27[lab] = (sum(r['map_hit'] for r in z), sum(r['alert_hit'] for r in z), sum(r['map_area'] for r in c) / len(c), sum(r['alert_area'] for r in c) / len(c))
E27FIX_WAIT = sum(json.loads((X / 'out_fixed3_E27fix/people/E27' / f'walk_D_full_prepared_{seed}.json').read_text())['snapshots'][-1]['behaviour']['agent']['mean_wait_minutes'] for seed in (104729, 130363)) / 2
LABEL = {'wrong_early_departure': '잘못된 선행 이동', 'legitimate_end_or_movement': '정당한 종료·이동', 'undecidable': '판단 불가'}

# ---------- report
md = []
add = md.append
add('# 회피·대기 연결 오류 수정과 배포본 대비 효과 비교 — 2026-10-10\n')
add('> **표기:** 모든 수치는 이미 결과를 본 합성 40명(E01–E08 개발, E09–E40 평가)의 **개발 재평가**다. 새로운 독립 평가, 실제 환자 경로, 임상 정확도가 아니다. 새 모델 호출 0회.\n')
add('## 1. 무엇을 고쳤나\n')
add('| 오류 | 원인 | 수정 |\n|---|---|---|')
add('| E20 장소 회피가 시장 전체로 확대 | K 재출력이 첫 출력의 장소 한정(가상 E20 시장)을 지움 | 재출력이 장소 한정만 지운 규칙은 첫 출력 한정 복원. 고정 규칙 제외, 모호하면 복원 않고 기록 |')
add('| 위치 없는 회피로 보행자 정지·지도 미발행 | 배포 지도에 시장 레이어 없음 + 근처 여부 50% 가설 | 등록 장소·신고 관측·지도 레이어 근처에서만 판단. 없으면 "환경 정보 부족"으로 공개하고 지도 발행 |')
add('| 쉼터·시장 이동 편향 | 장소 한정 없는 시장 소음 조건을 도로 노드마다 50% 재추첨 | 알려진 장소 1곳 단위로만 판단(정보 없으면 발동하지 않고 공개) |')
add('| 대기 전 출발 | 같은 문답의 "대기"와 "그래도 가족이 없으면 출발"이 독립 규칙 | 같은 문답 쌍에만 "대기 중 우선" 추가(규칙 삭제 없음, 대기 뒤 이동은 원래 조건으로 계속 평가) |')
add('| 열린 사건에서 "가족 동행" 가설 | 관측 없는 family_present를 50% 가설로 둠 | 사건이 열려 있으면 거짓. 재회 관측 시 더 걷지 않음(종결은 앱 수명주기) |\n')
add('저장된 정책·`mind_policy.VERSION`은 바꾸지 않았다. 저장 K 응답으로 재준비하면 40명 중 E20만 바뀐다(장소 한정 복원).\n')
add('## 2. 배포본 대비 서비스 효율 (평가 32명)\n')
add('먼저 확인: 현재 배포본(PR #274, 도로 앵커 포함)으로 D를 다시 돌린 결과는 기존 실험과 **지도 320개(평가 256·개발 64) 모두 비트 단위로 같다.** 기존 수치가 곧 배포본 수치다.\n')
add('| 방식 | 지도 포함률 | 지도 면적 ㎢ | 알림 포함률 | 알림 면적 ㎢ | 미완료 판정 |\n|---|---:|---:|---:|---:|---:|')
add(f"| 기존 경보 근사: 관련 구 | — | — | {pct(SV['final']['alert_district_proxy']['alert_hit'])} | {km(SV['final']['alert_district_proxy']['alert_area_km2_complete'])} | 0 |")
add(f"| 기존 경보 근사: 고양시 | — | — | {pct(SV['final']['alert_city_proxy']['alert_hit'])} | {km(SV['final']['alert_city_proxy']['alert_area_km2_complete'])} | 0 |")
add(f"| 본선 코드 재현 | {pct(PRE['map_hit'])} | {km(PRE['map_area_km2'])} | {pct(SV['final']['preliminary']['alert_hit'])} | {km(SV['final']['preliminary']['alert_area_km2_complete'])} | 0 |")
d, f = EV['deployed_D'], EV['fixed_D']
add(f"| **현재 배포본** | {pct(d['map_hit'])} | {km(d['map_area_km2_complete'])}* | {pct(d['alert_hit'])} | {km(d['alert_area_km2_complete'])}* | {d['incomplete_checks']}/768 |")
add(f"| **수정본** | {pct(f['map_hit'])} | {km(f['map_area_km2_complete'])} | {pct(f['alert_hit'])} | {km(f['alert_area_km2_complete'])} | {f['incomplete_checks']}/768 |\n")
add('\\* 배포본 면적은 E20(미완료)을 뺀 31명 평균. 포함률은 실패를 포함한 32명. 경보 근사는 행정경계 가정이며 실제 송출 기록이 아니다.\n')
fd = EV['fixed_minus_deployed']
add('**사람 단위 쌍 비교(수정본 − 배포본, 부트스트랩 95% 구간):**\n')
add(f"- 지도 포함률 {ci(fd['map_hit'])} · 알림 포함률 {ci(fd['alert_hit'])}")
add(f"- 지도 면적 {ci(fd['map_area'], 1, '㎢')} · 알림 면적 {ci(fd['alert_area'], 1, '㎢')} (면적은 양쪽 완료 31명)")
add('- 해석: 포함률 변화는 구간이 0을 포함한다. 알림 면적은 줄었다. 가장 큰 변화는 E20의 지도 발행(0→24/24)이다.\n')
add('![같은 면적 곡선](equal_area_curve.svg)\n')
add('## 3. 구성요소 비교 (수정 엔진 기준, 배포본 성능 수치 아님)\n')
add('B/C는 같은 연속 엔진에 개인 행동 규칙을 비운 구성이다. 배포본에서 정책이 없는 사람은 기존 엔진(+dem5)을 쓰므로 이 표는 배포본 성능이 아니다.\n')
add('| 구성 | 지도 포함률 | 지도 면적 ㎢ | 알림 포함률 | 알림 면적 ㎢ |\n|---|---:|---:|---:|---:|')
names = {'B_population': 'B 공통 정보', 'C_initial_person': 'C + 초기 개인화', 'D_full_prepared': 'D + 행동 규칙(수정본)'}
for arm, s in EV['component_fixed_engine'].items():
    add(f"| {names[arm]} | {pct(s['map_hit'])} | {km(s['map_area_km2_complete'])} | {pct(s['alert_hit'])} | {km(s['alert_area_km2_complete'])} |")
add(f"\n- C−B: 지도 포함률 {ci(EV['component_C_minus_B']['map_hit'])}, 지도 면적 {ci(EV['component_C_minus_B']['map_area'], 1, '㎢')}")
add(f"- D−C: 지도 포함률 {ci(EV['component_D_minus_C']['map_hit'])}, 지도 면적 {ci(EV['component_D_minus_C']['map_area'], 1, '㎢')}, 알림 포함률 {ci(EV['component_D_minus_C']['alert_hit'])}\n")
add('## 4. 대기 순서 (통제 검사: 길 잃음·가족 없음 고정, 사람당 500명)\n')
add('| 사람 | 대기 | 대기 전 이동 배포본 → 수정본 | 원인 규칙(원문) | 원문 기준 분류(판정자 3명) |\n|---|---:|---:|---|---|')
for (pid, wid), r in sorted(wf.items()):
    a = att[pid]; cause = a['causes'][0] if a['causes'] else None
    who = f"{cause['rule_id']} {cause['action']}→{cause['goal']} ({','.join(cause['rule_note_ids'])})" if cause else '—'
    v = votes.get(pid)
    lab = f"{LABEL[v[0]]} {v.count(v[0])}/3" if v else ('해석 오류(같은 문답에서 길 잃음 조건 누락)' if pid == 'E27' else '—')
    add(f"| {pid} | {r['hold_minutes']:.0f}분 | {wd[(pid, wid)]['moved_before_wait_end']} → {r['moved_before_wait_end']} | {who} | {lab} |")
tot_d = sum(r['moved_before_wait_end'] for r in wd.values()); tot_f = sum(r['moved_before_wait_end'] for r in wf.values())
add(f"| **합계** | | **{tot_d} → {tot_f}** / 5,000 | | |\n")
add('- 남은 885건은 모두 원문 기준 **잘못된 선행 이동**이다. 원인은 다른 문답(N0)의 평소 외출 습관을 K가 조건 반응으로 바꾼 해석 오류다(E07·E23·E31: 관측 없는 "공원 알아봄" 가설, E35: "혼자 나가도 그곳으로"→"가족 없으면 공원"). 서로 다른 문답에 일괄 우선순위를 적용하지 않았다.')
add(f"- **E27 해석 수정:** 원문 N2의 \"길을 잃었다는 걸 알아차리면 … 그래도 가족이 없으면\"에서 빠진 길 잃음 조건만 복원(수동, K 재호출 아님). 통제 검사 대기 전 이동 264 → {e27fix['moved_before_wait_end']}. 결과는 수정 전후를 모두 보존.")
add('\n| E27 | 지도 포함 | 알림 포함 | 지도 면적 | 알림 면적 |\n|---|---:|---:|---:|---:|')
for lab, (mh, ah, ma, aa) in e27.items():
    add(f'| {lab} | {mh}/24 | {ah}/24 | {ma:.2f} | {aa:.2f} |')
add('\n- 대기 종료는 정해진 시간(완료 뒤 출발) 또는 대기 조건 해제로만 일어난다. 가족이 곁에 있다는 관측은 재회로 보고 더 걷지 않는다. 실험 입력에는 가족 관측이 없다.\n')
add('## 5. E20: 지도 발행과 장소 회피를 분리\n')
add('| 상황(500명, 15분) | 버전 | 지도 발행 | 회피 실행 | 쉼터 이동 | 15분 뒤 시장 60m 밖 | 판정 |\n|---|---|---|---:|---:|---:|---|')
for key, title in (('A_noisy_at_market', 'A 시끄러운 시장에서 출발'), ('B_quiet_at_market', 'B 조용한 시장에서 출발'), ('C_far_no_info', 'C 시장 2km 밖, 정보 없음')):
    for lab, src in (('배포본', avd), ('수정본', avf)):
        s = src['scenarios'][key]
        verdict = {'A_noisy_at_market': '회피 성공' if lab == '수정본' else '회피는 일어나나 지도 미발행',
                   'B_quiet_at_market': '회피 없음(원문대로)' if lab == '수정본' else '조용한데 쉼터 이동 편향',
                   'C_far_no_info': '검사 불가 — 성공으로 세지 않음' if lab == '수정본' else '지도 미발행'}[key]
        add(f"| {title} | {lab} | {'예' if s['map_published'] else '아니오'} | {s['executed_avoid']} | {s['executed_seek_shelter']} | {s['beyond_60m_from_market_at_15min']} | {verdict} |")
add('\n- "조용하면 시장에 들어가세요"는 K 정책에 표현되지 않았다(시장 이동 0). 계약 한계로 남긴다.')
add('- 6시간 재생에서 E20 보행자는 대부분 시장(약 2km)에 접근하지 않아 회피 규칙 실행 시간이 거의 0이고, 쉼터 이동 규칙은 평균 약 317분이 "환경 정보 부족"으로 공개된다. 이 시간은 회피 성공으로 세지 않는다.\n')
add('## 6. 사람별 보존 결과 (D, 6시간, 두 시드 평균)\n')
add('평균 개선이 개인 손실을 가리지 않도록 40명을 모두 적는다. 규칙 실행 시간은 보행자 1명당 분.\n')
DROPS = []
add('| 사람 | 군 | 지도 포함 배포→수정 | 알림 포함 | 지도 동일 | 휴식 분 | 대기 분 | 회피·이동 규칙 실행 분 | 정보 부족 분 | 변화 사유 |\n|---|---|---|---|---|---|---|---|---|---|')
for p in sorted(T):
    t = T[p]
    moves = []
    for rid in sorted(set(t['deployed_rule_minutes_6h']) | set(t['fixed_rule_minutes_6h'])):
        a = t['deployed_rule_minutes_6h'].get(rid, 0.); b = t['fixed_rule_minutes_6h'].get(rid, 0.)
        if abs(a - b) >= 1: moves.append(f'{rid} {a:.0f}→{b:.0f}')
    ins = ', '.join(f'{k} {v:.0f}' for k, v in t['fixed_env_insufficient_minutes_6h'].items() if v >= 1) or '—'
    reasons = []
    if t.get('policy_source') and t['policy_source'] != 'stored': reasons.append('장소 한정 복원')
    if t.get('ordered_pairs'): reasons.append('대기 우선')
    if t['rule_execution_drops']: reasons.append('근거 없는 발동 제거')
    if p in ('E03', 'E07', 'E09', 'E11', 'E15', 'E19', 'E23', 'E27', 'E31', 'E34', 'E35', 'E39'): reasons.append('가족 부재 기본값')
    dm = '—' if t['deployed_map_hit'] is None else f"{t['deployed_map_hit'] * 100:.0f}→{t['fixed_map_hit'] * 100:.0f}%"
    da = f"{t['deployed_alert_hit'] * 100:.0f}→{t['fixed_alert_hit'] * 100:.0f}%"
    rest = '—' if t['deployed_rest_minutes_6h'] is None else f"{t['deployed_rest_minutes_6h']:.0f}→{t['fixed_rest_minutes_6h']:.0f}"
    wait = '—' if t['deployed_wait_minutes_6h'] is None else f"{t['deployed_wait_minutes_6h']:.0f}→{t['fixed_wait_minutes_6h']:.0f}"
    if t['deployed_complete'] < t['checks']:
        rest = '미완료→' + f"{t['fixed_rest_minutes_6h']:.0f}"; wait = '미완료→' + f"{t['fixed_wait_minutes_6h']:.0f}"
    warn = []
    for name, a, b in (('대기', t['deployed_wait_minutes_6h'], t['fixed_wait_minutes_6h']), ('휴식', t['deployed_rest_minutes_6h'], t['fixed_rest_minutes_6h'])):
        if a is not None and b is not None and a - b >= 2 and (a - b) / max(a, 1e-9) >= .1:
            warn.append(f'{name} {a:.0f}→{b:.0f}')
            DROPS.append((p, name, a, b))
    if warn: reasons.append('⚠ ' + ', '.join(warn) + ' 감소')
    add(f"| {p} | {t['family']} | {dm} | {da} | {t['maps_identical']}/{t['maps']} | {rest} | {wait} | {'; '.join(moves) or '변화 없음'} | {ins} | {', '.join(reasons) or '—'} |")
add('\n![사람별 포함률](person_containment.svg)\n')
dec = R['people_hit_decreased']
add('**대기·휴식이 10% 이상 줄어든 사람:** ' + (', '.join(f'{p} {n} {a:.0f}→{b:.0f}분' for p, n, a, b in DROPS) or '없음') +
    '. E07은 공원 도착 뒤 기간 미상 대기(a_1, N0 "거기서 한동안 머무르세요")가 ' + f"{T['E07']['deployed_rule_minutes_6h'].get('a_1',0):.0f}→{T['E07']['fixed_rule_minutes_6h'].get('a_1',0):.0f}분" + '으로 늘어 걷는 시간이 줄고 휴식 발동도 줄었다(원문에 머무는 시간이 없어 길이를 지어내지 않음). E27은 K가 같은 문답의 이동 규칙에서 "길 잃음" 조건을 빠뜨린 해석 오류 때문이다. 가족 부재 기본값으로 "가족 없으면 공원으로"(a_2)가 늘 켜지면서 대기와 경쟁했다. 원문 근거 해석 수정(4절)을 적용한 재생에서는 대기가 ' + f'{E27FIX_WAIT:.1f}분으로 회복된다(배포본 {T["E27"]["deployed_wait_minutes_6h"]:.1f}분). 운영 정책의 수정은 K 재해석이 필요하다.\n')
add('**포함률이 떨어진 사람:** ' + ', '.join(f"{p} {a * 100:.0f}→{b * 100:.0f}%" for p, a, b in dec) +
    '. 휴식·대기 실행 시간은 유지됐다. 가족 부재 기본값으로 원문 "그래도 가족이 없으면 공원 쪽으로"가 더 많이 실행되면서 지도가 공원 경로에 모였고, 합성 정답이 2시간 이후 귀가·이탈한 시점(24회 중 1~3회)을 놓쳤다. 같은 사람들의 지도 면적은 줄었다. 특성 손실이 아니라 집중도와 포함률의 교환이며, 평균에 묻지 않고 그대로 적는다.\n')
add('**규칙 실행이 크게 준 사람:** ' + ', '.join(f"{p}({', '.join(x['rule_id'] for x in v)})" for p, v in R['rule_execution_drops'].items()) +
    '. 모두 장소 한정 없는 시장 소음 조건 규칙이며, 배포본은 시장에서 먼 곳에서도 가설만으로 발동했다(E08·E32·E40은 신고상 시장이 조용함). 수정본은 알려진 시장 근처에서만 발동하고 나머지는 정보 부족으로 공개한다. 근거 없는 발동 제거이며 이 사람들의 지도 포함률은 유지 또는 상승했다.\n')
add('## 7. 하지 않은 것과 한계\n')
add('- 실제 환자 경로·전문가 평가·새 독립 평가 없음. 수정에 E01–E40을 사용했으므로 다음 확인은 새 합성 평가가 필요하다.')
add('- E07·E23·E31·E35의 습관→조건 반응 해석 오류는 분류만 했고 정책은 고치지 않았다(K 재해석 필요). E27만 원문 근거로 해석 수정 결과를 별도로 남겼다.')
add('- 실제 KINTEX 시장·공원 위치 레이어는 기존 자료(도로 전용 OSM)에 없어 등록 장소만 사용한다. 유형 전체 회피의 실제 검증은 POI 레이어가 필요하다.')
add('- "조용하면 시장에 들어간다" 같은 진입 반응은 현재 계약으로 표현되지 않는다.')
add('- 운영 배포는 별도 단계다(GPU SSH 필요).\n')
add('## 8. 재현\n')
add('`scripts/`의 reprepare.py(저장 K 응답 재준비), batch_replay.py(배포본/수정본 재생), controlled_*.py(통제 검사), analyze_final.py, make_report.py. 모두 네트워크 차단·모델 호출 0회.')
(A / '결과_보고서.md').write_text('\n'.join(md) + '\n')
print('report written', len(md), 'lines')

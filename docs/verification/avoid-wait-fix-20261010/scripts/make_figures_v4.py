"""Monochrome SVG figures for the pre-merge check (same 31 people; E20 apart)."""
import json, sys
from pathlib import Path

X = Path(sys.argv[1]); A = X / 'analysis'
R = json.loads((A / 'summary_v4.json').read_text())['same_31_evaluation_people']
T = {t['person_id']: t for t in json.loads((A / 'person_table_v4.json').read_text())}
budgets = [.25, .5, 1, 2, 4, 8, 12, 20, 30]

W, H, L, B, TOP, RGT = 640, 360, 60, 50, 30, 20
def xs(b): return L + (W - L - RGT) * budgets.index(b) / (len(budgets) - 1)
def ys(v): return TOP + (H - TOP - B) * (1 - v / .6)
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="Apple SD Gothic Neo, sans-serif" font-size="12">',
       f'<rect width="{W}" height="{H}" fill="#fff"/>',
       f'<text x="{L}" y="18" font-size="13">같은 면적 예산의 합성 위치 포함률 (같은 평가 31명, E20 제외, 개발 재평가)</text>']
for v in (0, .1, .2, .3, .4, .5, .6):
    svg.append(f'<line x1="{L}" x2="{W - RGT}" y1="{ys(v):.1f}" y2="{ys(v):.1f}" stroke="#ddd"/><text x="{L - 8}" y="{ys(v) + 4:.1f}" text-anchor="end">{int(v * 100)}%</text>')
for b in budgets:
    svg.append(f'<text x="{xs(b):.1f}" y="{H - B + 18}" text-anchor="middle">{b:g}</text>')
svg.append(f'<text x="{(L + W - RGT) / 2}" y="{H - 10}" text-anchor="middle">지도 상위 셀 면적 예산 (㎢)</text>')
for i, (name, key, dash) in enumerate((('현재 배포본', 'deployed', ''), ('수정본', 'final', '6,4'))):
    d = R[key]['equal_area_map_hit']
    pts = ' '.join(f'{xs(b):.1f},{ys(d[str(b)]):.1f}' for b in budgets)
    svg.append(f'<polyline points="{pts}" fill="none" stroke="#000" stroke-width="2" stroke-dasharray="{dash}"/>')
    for b in budgets:
        svg.append(f'<circle cx="{xs(b):.1f}" cy="{ys(d[str(b)]):.1f}" r="2.5" fill="#000"/>')
    y = TOP + 18 + i * 16
    svg.append(f'<line x1="{L + 12}" x2="{L + 40}" y1="{y}" y2="{y}" stroke="#000" stroke-width="2" stroke-dasharray="{dash}"/><text x="{L + 46}" y="{y + 4}">{name}</text>')
svg.append('</svg>')
(A / 'equal_area_curve_v4.svg').write_text('\n'.join(svg) + '\n')

people = [p for p in sorted(T) if T[p]['split'] == 'evaluation' and p != 'E20']
W2, H2, L2 = 680, 40 + 16 * len(people), 60
def xp(v): return L2 + (W2 - L2 - 20) * v
s2 = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W2} {H2 + 30}" font-family="Apple SD Gothic Neo, sans-serif" font-size="11">',
      f'<rect width="{W2}" height="{H2 + 30}" fill="#fff"/>',
      f'<text x="{L2}" y="16" font-size="13">같은 31명의 지도 포함: 배포본(○) → 수정본(●), 사람당 24회 판정</text>']
for v in (0, .25, .5, .75, 1):
    s2.append(f'<line x1="{xp(v):.1f}" x2="{xp(v):.1f}" y1="26" y2="{H2}" stroke="#eee"/><text x="{xp(v):.1f}" y="{H2 + 14}" text-anchor="middle">{int(v * 100)}%</text>')
for i, p in enumerate(people):
    y = 36 + 16 * i; a, b = T[p]['deployed']['map_hits'] / 24, T[p]['final']['map_hits'] / 24
    s2.append(f'<text x="{L2 - 8}" y="{y + 4}" text-anchor="end">{p}</text>')
    s2.append(f'<line x1="{xp(a):.1f}" x2="{xp(b):.1f}" y1="{y}" y2="{y}" stroke="#000"/>')
    s2.append(f'<circle cx="{xp(a):.1f}" cy="{y}" r="4" fill="#fff" stroke="#000"/><circle cx="{xp(b):.1f}" cy="{y}" r="3" fill="#000"/>')
s2.append('</svg>')
(A / 'person_containment_v4.svg').write_text('\n'.join(s2) + '\n')
print('ok')

"""Rebuild the presentation figure from the preserved paired synthetic summary."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
root = Path(__file__).parent
for font in [Path('/System/Library/Fonts/AppleSDGothicNeo.ttc'), Path('/usr/share/fonts/truetype/nanum/NanumGothic.ttf')]:
    if font.exists():
        font_manager.fontManager.addfont(str(font))
        plt.rcParams['font.family'] = font_manager.FontProperties(fname=str(font)).get_name()
        break
plt.rcParams['axes.unicode_minus'] = False
v = json.loads((root / 'metrics.json').read_text())['profiles']
fig, axes = plt.subplots(1, 3, figsize=(16, 5.3), gridspec_kw={'width_ratios': [2.15, 1, 1]})
colors = ['#84939f', '#148675']
labels = ['본선', '최종 개인화30 + 문헌70']
for i, k in enumerate(['preliminary', 'current']):
    values = [v[k]['futures'][f]['hit_pct'] for f in ['habitual', 'departure', 'contradictory']]
    positions = [x + (i - .5) * .34 for x in range(3)]
    bars = axes[0].bar(positions, values, width=.32, color=colors[i], label=labels[i])
    axes[0].bar_label(bars, labels=[f'{x:.2f}%' for x in values], padding=4, fontsize=11)
axes[0].set_xticks(range(3), ['준수·습관', '중간 이탈', '처음부터 반대'])
axes[0].set_ylim(0, 115)
axes[0].set_title('정답 위치 포함률 (%)', fontsize=15)
axes[0].legend(frameon=False, loc='upper right', fontsize=10)
for ax, field, title, unit in [
    (axes[1], 'mean_area_km2', '평균 알림 면적 (㎢)', '㎢'),
    (axes[2], 'efficiency_pp_per_km2', '전체 면적당 효율 (%p/㎢)', '')]:
    values = [v[k]['overall'][field] for k in ['preliminary', 'current']]
    bars = ax.bar(range(2), values, color=colors, width=.58)
    ax.bar_label(bars, labels=[f'{x:.2f}{unit}' for x in values], padding=5, fontsize=12)
    ax.set_xticks(range(2), ['본선', '최종'])
    ax.set_ylim(0, max(values) * 1.26)
    ax.set_title(title, fontsize=14)
for ax in axes:
    ax.spines[['top', 'right']].set_visible(False)
    ax.grid(axis='y', alpha=.15)
    ax.set_axisbelow(True)
fig.suptitle('본선 대비 전체 면적당 효율 +28.18% · 반대 행동 포함률은 -2.88%p', fontsize=20, y=.98)
fig.text(.5, .015, 'KINTEX 합성39명 · 동일351경로(seed1251–1253) · 방식당2,808판정 · 실제 발견률/발송 비용 측정 아님', ha='center', fontsize=11, color='#56616d')
fig.tight_layout(rect=[0, .065, 1, .89])
(root / 'figures').mkdir(exist_ok=True)
fig.savefig(root / 'figures/preliminary-vs-final.png', dpi=180, facecolor='white')

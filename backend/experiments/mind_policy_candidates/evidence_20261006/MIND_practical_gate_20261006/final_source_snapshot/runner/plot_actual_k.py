"""Plot saved offline measurements; no model, map, or network access."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt, font_manager

D = Path(__file__).resolve().parent
font = Path('/System/Library/Fonts/AppleSDGothicNeo.ttc')
if font.exists():
    font_manager.fontManager.addfont(str(font))
    plt.rcParams['font.family'] = font_manager.FontProperties(fname=str(font)).get_name()
plt.rcParams['axes.unicode_minus'] = False
data = json.loads((D / 'actual_k_replay.json').read_text())
fig, axes = plt.subplots(1, 2, figsize=(12, 5.4), gridspec_kw={'width_ratios': [1.25, 1]})
colors = ['#34465b', '#d17a35']
for r, color in zip(data['results'], colors):
    rows = [x for x in r['snapshots'] if x['minute'] in (60, 120, 240, 360)]
    axes[0].plot([x['minute']/60 for x in rows], [x['mean_path_km'] for x in rows],
                 marker='o', lw=2.5, color=color, label=f"K 응답 {r['model_repeat']}")
    end = rows[-1]
    axes[0].annotate(f"{end['mean_path_km']:.2f} km", (6, end['mean_path_km']),
                     xytext=(-6, 9), textcoords='offset points', ha='right', color=color)
axes[0].set(xlabel='경과 시간', ylabel='평균 누적 이동 거리 (km)', xticks=[1, 2, 4, 6],
            title='같은 보호자 원문에서 생성한 두 정책의 보행 결과', ylim=(-.15, 7.4))
axes[0].legend(frameon=False, loc='upper left')
axes[0].grid(axis='y', color='#e5e5e5')
left = [0., 0.]
for key, label, color in [('mean_wait', '기다림', '#cfd5db'), ('mean_rest', '휴식', '#8e9bac'),
                          ('mean_walk', '걷기', '#34465b')]:
    values = [r['snapshots'][-1][key] for r in data['results']]
    axes[1].barh(['K 응답 1', 'K 응답 2'], values, left=left, label=label, color=color, height=.5)
    for i, (v, l) in enumerate(zip(values, left)):
        axes[1].text(l+v/2, i, f'{v:.0f}분', ha='center', va='center',
                     color='white' if key == 'mean_walk' else '#15212f', fontsize=10)
    left = [l+v for l, v in zip(left, values)]
axes[1].set(xlabel='6시간 동안의 평균 상태별 시간 (분)', xlim=(0, 360),
            title='조건 연결의 차이가 휴식·보행 시간에 반영')
axes[1].invert_yaxis()
axes[1].legend(frameon=False, loc='upper center', bbox_to_anchor=(.5, -.15), ncol=3)
for ax in axes:
    ax.spines[['top', 'right']].set_visible(False)
fig.suptitle('실제 K 출력 → KINTEX 보행엔진: 조건 해석의 차이가 경로를 바꿈', fontsize=17, y=.98)
fig.text(.5, .035,
         '합성 인물 1명 · 응답별 가상 보행자 100명 · 같은 시드 17 · 저장된 모델 규칙 수정 없음\n'
         '가족 도착 90분·목적지 좌표는 합성 설정 · 실제 환자 이동 정답과 비교한 정확도가 아님',
         ha='center', va='bottom', fontsize=10, color='#4b5563')
fig.subplots_adjust(top=.81, bottom=.25, wspace=.32, left=.07, right=.97)
fig.savefig(D / 'actual_k_replay.png', dpi=180, facecolor='white')
fig.savefig(D / 'actual_k_replay.svg', facecolor='white')

"""Render saved evidence only. Requires matplotlib; no models or simulations."""
import gzip
import json
import os
from pathlib import Path
import tempfile

os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'cbh-featurewise-mpl'))
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt, font_manager
from matplotlib.collections import LineCollection
from matplotlib.patches import Circle

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / 'assets'
font_override = os.environ.get('FIGURE_FONT_PATH')
if font_override:
    font_manager.fontManager.addfont(font_override)
    font_name = font_manager.FontProperties(fname=font_override).get_name()
else:
    installed = {f.name for f in font_manager.fontManager.ttflist}
    font_name = next((x for x in ['AppleGothic', 'NanumGothic', 'Noto Sans CJK KR', 'Arial Unicode MS'] if x in installed), None)
    if not font_name:
        raise RuntimeError('Set FIGURE_FONT_PATH to a Korean-capable font file.')
plt.rcParams.update({'font.family': font_name, 'font.size': 12, 'axes.unicode_minus': False,
                     'axes.spines.top': False, 'axes.spines.right': False,
                     'figure.facecolor': 'white', 'savefig.facecolor': 'white'})
TEAL, GRAY, DARK = '#176f7a', '#818a95', '#25313d'


def render_summary():
    data = json.loads((ROOT / 'matched_comparison.json').read_text())['rows']
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.2))
    configs = [('persistence_toward_park', 'near_origin', None,
                ['머무름 입력', '계속 걷기 입력'], '머무름 변화가 위치 분포에 반영되는가?',
                '출발지 200m 내 종료 (%)', 35, 'C02 ↔ C04 · 공통 K 반복 1개 × 시드 3개'),
               ('destination_when_continue', 'zone_entry', '공원',
                ['시장 지향 입력', '공원 지향 입력'], '목적지 변화가 해당 구역 진입에 반영되는가?',
                '공원 120m 구역 진입 (%)', 5, 'C03 ↔ C04 · 공통 K 반복 2개 × 시드 3개')]
    for ax, (pair, metric, place, labels, title, ylabel, top, note) in zip(axes, configs):
        for condition, offset, color, label in [('CONTROL', -.18, GRAY, '통합 출력'), ('FEATURES', .18, TEAL, '피처별 출력')]:
            row = next(x for x in data if x['id'] == pair and x['condition'] == condition)
            values = [row['values'][s][metric][place] if place else row['values'][s][metric] for s in ['a', 'b']]
            bars = ax.bar([x + offset for x in range(2)], [v*100 for v in values], .34, color=color, label=label, zorder=3)
            ax.bar_label(bars, labels=[f'{v*100:.2f}%' for v in values], padding=6, fontsize=12, color=DARK)
        ax.set_xticks([0,1],labels);ax.set_ylim(0,top);ax.set_ylabel(ylabel)
        ax.set_title(title,fontsize=13,pad=15);ax.grid(axis='y',alpha=.17,zorder=0)
        ax.text(.5,-.20,note,ha='center',transform=ax.transAxes,fontsize=10,color='#52606d')
    axes[0].legend(frameon=False,loc='upper right',fontsize=11)
    fig.suptitle('같은 사례·반복·시드가 모두 있는 결과끼리 비교',fontsize=18,y=.97)
    fig.subplots_adjust(top=.79,bottom=.26,left=.075,right=.98,wspace=.30)
    fig.text(.075,.055,'마음 재해석 OFF · 합성 사건 · 각 보행 500명. 종료 위치는 실제 정지 시간이 아니며, 구역 진입은 발견 정확도가 아님.',fontsize=10,color='#52606d')
    fig.savefig(ASSETS/'matched-results.png',dpi=180);plt.close(fig)


def render_maps():
    with gzip.open(ASSETS/'map_data.json.gz','rt') as f:data=json.load(f)
    fig,axes=plt.subplots(2,2,figsize=(11,11));extent=data['extent_km']
    for ax,panel in zip(axes.flat,data['panels']):
        ax.add_collection(LineCollection(data['roads'],colors='#dce1e5',linewidths=.45,zorder=1))
        ax.add_patch(Circle((0,0),.2,facecolor='none',edgecolor='#7d8790',linestyle='--',linewidth=1,zorder=2))
        ax.add_collection(LineCollection(panel['paths'],colors=TEAL,linewidths=.95,alpha=.5,zorder=3))
        endpoints=[p[-1] for p in panel['paths']]
        ax.scatter([p[0] for p in endpoints],[p[1] for p in endpoints],s=7,c=TEAL,zorder=4)
        ax.scatter([0],[0],marker='+',s=100,c=DARK,linewidths=2,zorder=6)
        for place in data['places']:
            x,y=place['xy'];ax.scatter([x],[y],s=32,c='white',edgecolors=DARK,zorder=5)
            ax.annotate(place['label'],(x,y),xytext=(5,6),textcoords='offset points',fontsize=10,
                        bbox={'facecolor':'white','edgecolor':'none','alpha':.8,'pad':.5},zorder=7)
        name='통합 출력' if panel['condition']=='CONTROL' else '피처별 출력'
        case='머무름 입력' if panel['case']=='C02' else '계속 걷기 입력'
        ax.set_title(f'{name} · {case}\n출발지 200m 내 종료 {panel["metrics"]["endpoint_within_200m"]*100:.1f}% (500명 기준)',fontsize=12,pad=10)
        ax.set_xlim(-extent,extent);ax.set_ylim(-extent,extent);ax.set_aspect('equal')
        ax.set_xlabel('출발지 기준 동서 거리 (km)',fontsize=10);ax.set_ylabel('남북 거리 (km)',fontsize=10)
        ax.tick_params(labelsize=9)
    fig.suptitle('저장된 OSM 도로망 위의 실제 실험 경로',fontsize=18,y=.98)
    fig.text(.5,.935,'동일 공원 지향 · C02/C04 · K 두 번째 반복 · 보행 시드 41 · 마음 재해석 OFF',ha='center',fontsize=11)
    fig.subplots_adjust(top=.85,bottom=.17,left=.085,right=.97,hspace=.37,wspace=.20)
    fig.text(.085,.035,'각 실행의 저장 순서 첫 40명 경로·종점만 표시. 점선 원: 200m. 네 패널은 같은 축척이며 표시 경로 전체를 포함.\n개별 시드 그림으로 우열을 판단하지 않음. 시설은 가상 배치. 실제 사람의 이동 기록이 아님.\n© OpenStreetMap contributors · ODbL',fontsize=10,color='#52606d',linespacing=1.5)
    fig.savefig(ASSETS/'osm-paths.png',dpi=180);plt.close(fig)


if __name__=='__main__':
    render_summary();render_maps()
    print('Rendered matched-results.png and osm-paths.png from saved evidence; 0 new model/walking runs.')

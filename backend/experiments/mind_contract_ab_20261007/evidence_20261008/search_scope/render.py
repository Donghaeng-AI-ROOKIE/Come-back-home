"""Render frozen offline diagnostics. No model/map calls."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root=Path(__file__).parent
data=json.loads((root/'unobserved_summary.json').read_text())
plt.rcParams.update({'font.family':'AppleGothic','axes.unicode_minus':False,'font.size':11})
fig,axes=plt.subplots(1,2,figsize=(12,5))
for key,label,color in [('empty_policy','개인 조건 없음 · 같은 초기 성향','#888888'),
                        ('d12_rep1','저장 D12 조건 적용','#15558f')]:
    rows=data['rows'][key]
    x=[r['minute']/60 for r in rows]
    axes[0].plot(x,[r['metrics']['mode'].get('wait',0) for r in rows],marker='o',color=color,label=label)
    axes[1].plot(x,[r['metrics']['mean_path_km'] for r in rows],marker='o',color=color,label=label)
axes[0].set(ylabel='대기 중인 가상 보행자 (명)',ylim=(0,550),title='2시간 이후 500명 모두 대기')
axes[1].set(ylabel='평균 누적 이동거리 (km)',ylim=(0,14),title='D12 이동거리 0.208km에서 고정')
for ax in axes:
    ax.set(xlabel='경과 시간',xticks=[1,2,4,6])
    ax.grid(axis='y',alpha=.18)
    ax.spines[['top','right']].set_visible(False)
axes[0].legend(loc='lower right',fontsize=10)
fig.suptitle('미래의 가족 귀환·자각·소음 관측 없이 다시 걸어 본 결과',fontsize=17,y=.98)
fig.text(.5,.025,'합성 보호자 1개 사례 · KINTEX 도로 · 구성별 500명 · seed 17 · 외부 모델 호출 0회\n'
         '대기 쏠림을 찾는 진단이며 실제 행동·거리의 정답 비교가 아님',ha='center',fontsize=10)
fig.subplots_adjust(top=.80,bottom=.22,wspace=.30,left=.08,right=.97)
fig.savefig(root/'미확인상태_대기쏠림.png',dpi=160)


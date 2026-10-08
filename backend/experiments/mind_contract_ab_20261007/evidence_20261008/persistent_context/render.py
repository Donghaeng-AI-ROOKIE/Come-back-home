"""Plot frozen diagnostic aggregates, not a clinical accuracy figure."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
p=Path(__file__).parent
data=json.loads((p/'summary.json').read_text())
plt.rcParams.update({'font.family':'AppleGothic','axes.unicode_minus':False,'font.size':11})
fig,axes=plt.subplots(1,2,figsize=(12,5))
x=[1,2,4,6]
for mode,label,color in [('legacy','기존 행동 재추첨','#777777'),
                        ('persistent','사실별 가정 유지 후보','#15558f')]:
 for ax,metric in zip(axes,['wait','distance']):
  values=[]
  for seed,rows in data['seeds'].items():
   rows=rows[mode]
   values.append([r['metrics']['mode'].get('wait',0) if metric=='wait' else r['metrics']['mean_path_km'] for r in rows])
  vals=np.asarray(values)
  ax.fill_between(x,vals.min(0),vals.max(0),color=color,alpha=.16)
  ax.plot(x,vals.mean(0),'-o',label=label,color=color)
axes[0].set(title='대기 인원이 계속 늘어나는 현상 해소',ylabel='대기 중인 가상 보행자 (명)',ylim=(0,550))
axes[1].set(title='나머지 보행자는 이동·휴식 지속',ylabel='평균 누적 이동거리 (km)',ylim=(0,6.5))
axes[0].legend(loc='lower right',fontsize=10)
for ax in axes:
 ax.set(xlabel='경과 시간',xticks=x)
 ax.spines[['top','right']].set_visible(False)
 ax.grid(axis='y',alpha=.2)
fig.suptitle('K 해석을 그대로 두고 미확인 상태 처리만 비교',fontsize=18,y=.98)
fig.text(.5,.025,'합성 온보딩 1개 · KINTEX · 3시드 × 구성별 500명 · 선: 시드 평균, 음영: 범위\n'
         '가족 귀환 등 미래 관측 없음 · 참/거짓 동일 가중은 연구 가정 · 실제 행동·위치 정확도 아님',ha='center',fontsize=10)
fig.subplots_adjust(top=.80,bottom=.22,left=.08,right=.97,wspace=.28)
fig.savefig(p/'대기쏠림_수정비교.png',dpi=160)

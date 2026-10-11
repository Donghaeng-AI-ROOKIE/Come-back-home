from pathlib import Path
import json,os
os.environ['MPLCONFIGDIR']='/tmp/cbh-mpl'
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt,font_manager
import numpy as np
O=Path.cwd()/'결선/실험/SAR_DISTANCE_ONLY_20261012';D=O/'results';p=json.loads((D/'area_budget_summary.json').read_text())['arms']['uniform_dev_current_mean_area_budget'];u=json.loads((D/'union_safety_summary.json').read_text())['arms']['preserve_current_union_uniform_dev_budget'];current=p['comparison']['current'];candidate=p['comparison']['distance_only'];union=u['comparison']['distance_only'];font='/System/Library/Fonts/AppleSDGothicNeo.ttc';font_manager.fontManager.addfont(font);plt.rcParams.update({'font.family':font_manager.FontProperties(fname=font).get_name(),'axes.unicode_minus':False});labels=['현재','문헌+면적 상한','기존 구역 보존'];colors=['#17846b','#397fb4','#b98a3e'];stats=[current,candidate,union]
fig,axs=plt.subplots(1,3,figsize=(15,6.5));fig.subplots_adjust(left=.055,right=.98,top=.77,bottom=.26,wspace=.35)
fig.text(.035,.94,'개인화 이탈을 평가에 포함: 효율과 기존 구역 보존의 교환',fontsize=21,weight='bold');fig.text(.035,.875,'이전에 본 합성31명 · 744조건 · res9 / 면적 상한5.281216㎢는 개발8명의 기존 평균에서 고정',fontsize=11)
for ax,key,title,ylabel in [(axs[0],'efficiency_pp_per_km2','면적당 적중률','정답 포함률(%) ÷ 평균 면적(㎢)'),(axs[1],'mean_area_km2','평균 발송 대상 면적','면적(㎢)')]:
 vals=[s[key] for s in stats];bars=ax.bar(labels,vals,color=colors,width=.6)
 for bar,v in zip(bars,vals):ax.text(bar.get_x()+bar.get_width()/2,v+.13,f'{v:.2f}',ha='center',fontsize=12)
 ax.set_title(title);ax.set_ylabel(ylabel);ax.set_ylim(0,max(vals)*1.25);ax.grid(axis='y',alpha=.2)
ax=axs[2];x=np.arange(3)
for offset,arm,label,color in [(-.26,'current','현재',colors[0]),(0,'budget','면적 상한',colors[1]),(.26,'union','구역 보존',colors[2])]:
 vals=[(p if arm!='union' else u)['future_slices'][f]['current' if arm=='current' else 'distance_only']['hit_pct'] for f in ['habitual','departure','contradictory']];bars=ax.bar(x+offset,vals,width=.26,label=label,color=color)
 for bar,v in zip(bars,vals):ax.text(bar.get_x()+bar.get_width()/2,v+1.3,f'{v:.1f}',ha='center',fontsize=8)
ax.set_xticks(x,['습관','이탈','반대']);ax.set_ylim(0,115);ax.set_title('정답 미래별 포함률');ax.set_ylabel('포함률 (%)');ax.legend(fontsize=8);ax.grid(axis='y',alpha=.2)
fig.text(.035,.19,'면적 상한: 효율 +14.50% (95% CI +5.77~+23.01%), 반대 행동 0.81%→8.47%. 습관 행동은 1.21%p 감소.',fontsize=11,weight='bold')
fig.text(.035,.125,'구역 보존: 기존 적중 손실0, 반대 행동8.87%. 평균 면적7.11㎢로 늘고 효율은11.89% 하락.',fontsize=11)
fig.text(.035,.06,'면적 상한 후보는 누적95% 정책이 아님. 새 홀드아웃·실푸시 미수행. 실험 후보이며 제품 기본값 변경 없음.',fontsize=10,color='#576d79')
fig.savefig(D/'safety_tradeoff.png',dpi=180);plt.close(fig)

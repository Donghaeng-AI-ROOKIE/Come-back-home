"""Show repeated outputs' movement consequences for prospectively selected P05."""
import json,statistics
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
D=Path(__file__).resolve().parent
font_manager.fontManager.addfont('/System/Library/Fonts/AppleSDGothicNeo.ttc')
plt.rcParams.update({'font.family':'Apple SD Gothic Neo','axes.unicode_minus':False})
rows=[json.loads(p.read_text()) for p in (D/'spatial').glob('P05_*.json')]
fig,axes=plt.subplots(1,3,figsize=(15,5.8));fig.subplots_adjust(left=.065,right=.98,bottom=.32,top=.69,wspace=.30)
notes=[]
for arm,color in [('on','#21618C'),('off','#777777')]:
 for rep,style,marker in [(1,'-','o'),(2,'--','s')]:
  group=[r for r in rows if r['arm']==arm and r['rep']==rep];valid=[r for r in group if r['status']=='executed']
  label=f"Thinking {'켬' if arm=='on' else '끔'} · {rep}차 응답"
  if len(valid)!=12:
   source=D/f'comparison/{arm}/P05/{rep}/result.json'
   failed=source.exists() and not json.loads(source.read_text())['valid']
   notes.append(label+(': 출력 실패로 보행 실행 불가' if failed else f': 실행 자료 {len(valid)}/12개 집단'));continue
  for ax,field,title,ylabel in zip(axes,['mean_walk_minutes','mean_rest_minutes','mean_path_km'],['누적 보행 시간','누적 휴식 시간','누적 보행 거리'],['분','분','km']):
   values=[statistics.mean(next(s[field] for s in r['snapshots'] if s['minute']==minute) for r in valid) for minute in (60,120,240,360)]
   ax.plot([1,2,4,6],values,style,color=color,marker=marker,label=label,lw=4 if arm=='on' else 2,ms=7 if arm=='on' else 4)
   ax.set_title(title,fontsize=14);ax.set_xlabel('경과 시간(h)');ax.set_ylabel(ylabel);ax.set_xticks([1,2,4,6]);ax.grid(axis='y',alpha=.2)
   ax.spines[['top','right']].set_visible(False)
for ax in axes:
 values=[float(v) for line in ax.lines for v in line.get_ydata()]
 ax.set_ylim(0,max(values)*1.08 if values else 1)
fig.suptitle('같은 보호자 원문, 반복 응답에 따라 달라지는 보행',fontsize=20,y=.965)
fig.text(.5,.87,'P05: “연속 8분 또는 450m를 걸으면 무릎 때문에 앉아 쉬어야 함”',ha='center',fontsize=13)
fig.text(.5,.80,'각 선: KINTEX 6개 출발 구역 × 보행 시드 2개 × 100보행자의 평균',ha='center',fontsize=11)
handles,labels=axes[0].get_legend_handles_labels();fig.legend(handles,labels,loc='lower center',bbox_to_anchor=(.5,.105),ncol=2,frameon=False,fontsize=10)
coincident=any(all(abs(a-b)<1e-8 for a,b in zip(x.get_ydata(),y.get_ydata())) for i,x in enumerate(axes[0].lines) for y in list(axes[0].lines)[i+1:])
foot=' / '.join(notes) if notes else '네 응답을 모두 포함. 좋은 응답을 골라 대체하지 않음.'
if coincident:foot+=' · 같은 값의 선은 겹쳐 표시'
fig.text(.5,.025,'거리 = 길을 따라 걸은 합계, 출발점 반경 아님 · 합성 사례·일반 초기 이동 prior · 실제 환자 정확도 아님\n'+foot,ha='center',fontsize=10)
fig.savefig(D/'같은원문_휴식과거리_반복차이.png',dpi=150)
print('P05 repetition artifact saved from completed local groups.')

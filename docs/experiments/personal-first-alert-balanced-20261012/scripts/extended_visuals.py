"""Postprocess fixed confirmation data only; no new experiment, model or network."""
from pathlib import Path
import os,json,sys,math,socket
os.environ.update(MPLCONFIGDIR='/tmp/cbh-mpl',PERSIST_STORAGE='false',PUSH_ENABLED='false')
def blocked(*a,**k):raise RuntimeError('network forbidden in visual postprocessing')
socket.socket.connect=blocked;socket.create_connection=blocked
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt,font_manager
from matplotlib.collections import PolyCollection,LineCollection
from shapely.geometry import Polygon
from shapely.ops import unary_union
import numpy as np,h3
O=Path(__file__).resolve().parents[1];R=O.parents[2]
D=O/'results/visualizations';D.mkdir(exist_ok=True)
E=R/'결선/실험/EFFICIENCY_KINTEX_v1_20261009'
X=R/'결선/실험/CHANNEL_ALERT_repair_20261011'
L=R/'결선/실험/SAR_DISTANCE_ONLY_20261012'
C=R/'결선/개발/cbh-independent-alert-core-20261011'
sys.path.insert(0,str(C/'backend'))
from app.phase2.combine import alpha_pool
font='/System/Library/Fonts/AppleSDGothicNeo.ttc'
font_manager.fontManager.addfont(font)
plt.rcParams.update({'font.family':font_manager.FontProperties(fname=font).get_name(),'axes.unicode_minus':False})
s=json.loads((O/'results/confirmation_summary.json').read_text())
rows=json.loads((O/'results/confirmation_rows.json').read_text())
sels=json.loads((O/'results/confirmation_selections.json').read_text())
truth=json.loads((O/'truth_private.json').read_text())
inputrows=json.loads((E/'inputs.json').read_text())
families={v['person_id']:v['family'] for v in inputrows}
arms=['preliminary','current','candidate'];names=['본선','기존 결선 개인90·SAR10','최종안 개인30·문헌70']
colors=['#d17746','#21846c','#337cb0'];future=['habitual','departure','contradictory']
future_names={'habitual':'개인화를 따름','departure':'중간 이탈','contradictory':'처음부터 반대'}
family_names={'avoid':'회피','goal':'목표 추구','rest':'휴식','wait':'대기'}
lookup={(z['person_id'],z['prediction_seed'],z['hour'],z['arm']):z for z in sels}
ts={(z['person_id'],z['truth_seed'],z['future']):z for z in truth}
people=sorted({r['person_id'] for r in rows})
picked={f:next(p for p in people if families[p]==f) for f in ['avoid','goal','rest','wait']}
comparisons={}
for f in ['overall']+future:
 v=lambda a:s['profiles'][a]['overall'] if f=='overall' else s['profiles'][a]['futures'][f]
 q=v('candidate');comparisons[f]={a:v(a) for a in arms}
 for baseline in ['preliminary','current']:
  comparisons[f]['vs_'+baseline]={'hit_delta_pp':q['hit_pct']-v(baseline)['hit_pct'],'efficiency_relative_pct':100*(q['efficiency_pp_per_km2']/v(baseline)['efficiency_pp_per_km2']-1),'efficiency_delta':q['efficiency_pp_per_km2']-v(baseline)['efficiency_pp_per_km2'],'hit_delta_ci95':s['comparisons'][baseline][f]['hit_pp']['ci95'],'efficiency_delta_ci95':s['comparisons'][baseline][f]['efficiency_pp_per_km2']['ci95']}
(D/'comparison_table.json').write_text(json.dumps(comparisons,ensure_ascii=False,indent=2)+'\n')
fig,axs=plt.subplots(1,3,figsize=(17,6.6))
fig.subplots_adjust(left=.06,right=.98,top=.76,bottom=.27,wspace=.32)
fig.text(.04,.94,'최종 비교: 개인화 준수와 이탈을 함께 평가',fontsize=22,weight='bold')
fig.text(.04,.87,'같은 새 정답351경로 · 설정별2,808판정 · 확률지도 개인화30%·문헌70% · 실제 면적 상한5.8㎢ / res9',fontsize=11)
x=np.arange(3)
for i,a in enumerate(arms):
 vals=[s['profiles'][a]['futures'][f]['hit_pct'] for f in future]
 bars=axs[0].bar(x+(i-1)*.25,vals,width=.25,color=colors[i],label=names[i])
 for bar,v in zip(bars,vals):axs[0].text(bar.get_x()+.125,v+1.5,f'{v:.1f}',ha='center',fontsize=8)
axs[0].set_xticks(x,[future_names[f] for f in future]);axs[0].set_ylim(0,121);axs[0].set_ylabel('正답 위치 포함률 (%)'.replace('正','정'));axs[0].legend(fontsize=7);axs[0].set_title('행동 조건별 포함률')
vals=[s['profiles'][a]['overall']['efficiency_pp_per_km2'] for a in arms]
bars=axs[1].bar(['본선','기존 결선','최종안'],vals,color=colors)
for bar,v in zip(bars,vals):axs[1].text(bar.get_x()+bar.get_width()/2,v+.2,f'{v:.2f}',ha='center')
axs[1].set_ylim(0,14);axs[1].set_ylabel('포함률(%) / 실제 평균 면적(㎢)');axs[1].set_title('전체 면적당 효율')
for i,base in enumerate(['preliminary','current']):
 vals=[s['comparisons'][base][f]['hit_pp']['point'] for f in future]
 cis=[s['comparisons'][base][f]['hit_pp']['ci95'] for f in future]
 y=np.arange(3)+(i-.5)*.17
 axs[2].errorbar(vals,y,xerr=np.array([[v-c[0] for v,c in zip(vals,cis)],[c[1]-v for v,c in zip(vals,cis)]]),fmt='o',color=colors[i],capsize=4,label=('본선 대비' if i==0 else '기존 결선 대비'))
axs[2].set_yticks(np.arange(3),[future_names[f] for f in future]);axs[2].invert_yaxis();axs[2].axvline(0,color='#596774',lw=1);axs[2].set_xlim(-10,35);axs[2].set_xlabel('포함률 개선 (%p), 95% CI');axs[2].set_title('개선 폭과 불확실성');axs[2].legend(fontsize=9)
for ax in axs:ax.grid(alpha=.16)
fig.text(.04,.17,'본선 대비: 준수 +20.30%p / 이탈 +11.22%p / 반대 +1.07%p / 전체 면적당 효율 +29.45%',fontsize=12,weight='bold')
fig.text(.04,.105,'반대30.24%는 여전히 낮음. 본선 대비 반대 차이 CI -5.77~+7.91%p → 개선 확증 아님.',fontsize=11,color='#983e34')
fig.text(.04,.045,'합성39명의 새 경로·동일 행동 비중 스트레스 평가 / 발견·수신률·실제 인구 빈도 검증 아님',fontsize=10,color='#536b78')
fig.savefig(D/'final_comparison.png',dpi=170);plt.close(fig)
# Every person in the confirmed sample, all truth seeds and prediction seeds.
mat=np.zeros((len(people),9))
for i,p in enumerate(people):
 for j,a in enumerate(arms):
  for k,f in enumerate(future):
   z=[r for r in rows if r['person_id']==p and r['arm']==a and r['future']==f]
   assert len(z)==24;mat[i,j*3+k]=100*sum(v['hit'] for v in z)/24
fig,ax=plt.subplots(figsize=(12.8,15.7))
fig.subplots_adjust(left=.18,right=.85,top=.89,bottom=.11)
im=ax.imshow(mat,aspect='auto',vmin=0,vmax=100,cmap='YlGnBu')
ax.set_yticks(range(len(people)),[f'{p} · {family_names[families[p]]}' for p in people],fontsize=9)
ax.set_xticks(range(9),[(('본선','기존 결선','최종안')[j]+'\n'+('준수','이탈','반대')[k]) for j in range(3) for k in range(3)],fontsize=9)
for i in range(len(people)):
 for j in range(9):ax.text(j,i,f'{mat[i,j]:.0f}',ha='center',va='center',fontsize=7,color='white' if mat[i,j]>65 else '#192c36')
for xline in (2.5,5.5):ax.axvline(xline,color='white',lw=3)
cb=fig.colorbar(im,ax=ax,fraction=.035,pad=.045);cb.set_label('정답 위치 포함률 (%)')
fig.text(.10,.955,'전체39명 테스트 결과: 성공도 실패도 모두 표시',fontsize=22,weight='bold')
fig.text(.10,.92,'각 칸24판정 = 정답3seed × 예측2seed × 4시간 / 새 정답351경로 전부 사용',fontsize=11)
fig.text(.10,.045,'개인별 표본24판정의 기술적 요약이며 독립24명이나 임상적 성공률이 아님. 본선·기존 결선·최종안 동일 정답.',fontsize=10,color='#536b78')
fig.savefig(D/'all_39_people.png',dpi=160);plt.close(fig)
background=json.loads((R/'결선/PR_설명보충_20261011/최종성능_그림/figure_data.json').read_text())['map_example']['roads']
loaded={};examples=[]
def poly(c):return Polygon([(lng,lat) for lat,lng in h3.cell_to_boundary(c)])
def outline(ax,g):
 if g.is_empty:return
 if g.geom_type=='Polygon':ax.plot(*g.exterior.xy,color='#162b37',lw=1.3,zorder=3)
 elif hasattr(g,'geoms'):
  for v in g.geoms:outline(ax,v)
def data(pid,hr,a):
 key=(pid,hr,a)
 if key in loaded:return loaded[key]
 pred=104729
 raw=next(z for z in json.loads((X/f'results_independent_sar/{pid}_{pred}.json').read_text())['snapshots'] if z['hour']==hr)
 q=next(z['cells'] for z in json.loads((L/f'results/distance_maps/{pid}.json').read_text())['snapshots'] if z['hour']==hr)
 if a=='preliminary':prob=next(z['cells'] for z in json.loads((E/f'service_comparison/output/people/{pid}/walk_preliminary_{pred}.json').read_text())['snapshots'] if z['hour']==hr)
 else:prob=alpha_pool([raw['personal'],raw['statistical'] if a=='current' else q],[.9,.1] if a=='current' else [.3,.7])
 selected=lookup[(pid,pred,hr,a)]
 loaded[key]=(prob,selected,unary_union([poly(c) for c in selected['cells']]))
 return loaded[key]
def bounds(pid,hours,ars):
 geoms=[data(pid,h,a)[2] for h in hours for a in ars];g=unary_union(geoms);box=g.bounds
 paths=[z for f in future for z in ts[(pid,2026101231,f)]['path'] if z['minute']<=max(hours)*60]
 return (min(box[0],min(z['lng'] for z in paths))-.002,max(box[2],max(z['lng'] for z in paths))+.002,min(box[1],min(z['lat'] for z in paths))-.002,max(box[3],max(z['lat'] for z in paths))+.002)
def panel(ax,pid,hr,f,a,bbox,title):
 prob,sel,g=data(pid,hr,a);path=[z for z in ts[(pid,2026101231,f)]['path'] if z['minute']<=hr*60]
 pos=next(z['position'] for z in ts[(pid,2026101231,f)]['snapshots'] if z['hour']==hr)
 cells=sel['cells'];i=arms.index(a);ps=list(prob) if a=='preliminary' else cells
 values=[prob.get(c,0) for c in ps];mx=max(values) or 1.
 ax.add_collection(LineCollection(background,colors='#b7c2c8',linewidths=.28,zorder=1))
 ax.add_collection(PolyCollection([list(poly(c).exterior.coords) for c in ps],array=[math.sqrt(v/mx) for v in values],cmap=['Oranges','Greens','Blues'][i],clim=(0,1),edgecolors='white',linewidths=.15,zorder=2))
 outline(ax,g);ax.plot([z['lng'] for z in path],[z['lat'] for z in path],color='#d93251',lw=1.8,zorder=4)
 ax.scatter(pos['lng'],pos['lat'],c='#ba27b3',marker='D',s=48,edgecolor='white',zorder=5)
 ax.scatter(path[0]['lng'],path[0]['lat'],c='#138bc4',s=33,edgecolor='white',zorder=6)
 hit=h3.latlng_to_cell(pos['lat'],pos['lng'],7 if a=='preliminary' else 9) in set(cells)
 expected=next(r for r in rows if r['person_id']==pid and r['prediction_seed']==104729 and r['truth_seed']==2026101231 and r['hour']==hr and r['future']==f and r['arm']==a)
 assert int(hit)==expected['hit']
 ax.set_xlim(bbox[:2]);ax.set_ylim(bbox[2:]);ax.set_aspect(1/math.cos(math.radians(pos['lat'])));ax.set_xticks([]);ax.set_yticks([])
 ax.set_title(title+f'\n{sel["area_km2"]:.2f}㎢ · '+('정답 포함' if hit else '정답 미포함'),fontsize=11,color='#182d37' if hit else '#983e34')
 examples.append(dict(person_id=pid,family=families[pid],hour=hr,future=f,arm=a,prediction_seed=104729,truth_seed=2026101231,hit=hit,area_km2=sel['area_km2']))
for fam,pid in picked.items():
 fig,axs=plt.subplots(3,3,figsize=(12.5,13.4));fig.subplots_adjust(left=.05,right=.96,top=.87,bottom=.12,wspace=.1,hspace=.28)
 fig.text(.05,.97,f'{family_names[fam]} 예시 {pid}: 준수·중간 이탈·반대 행동',fontsize=21,weight='bold')
 fig.text(.05,.925,'각 유형의 첫 유효 ID를 고정 · 새 첫 seed2026101231 · 4시간 · 예측104729 · 성공 여부로 교체하지 않음',fontsize=10)
 bbox=bounds(pid,[4],arms)
 for row,f in enumerate(future):
  for col,a in enumerate(arms):panel(axs[row,col],pid,4,f,a,bbox,future_names[f]+' · '+names[col])
 fig.text(.05,.07,'검정: 실제 발송 영역 / 빨강: 정답 경로 / 파랑: 시작 / 자주: 해당 시점 정답 위치',fontsize=11)
 fig.text(.05,.04,'9패널 동일 지리 범위. 농도는 각 지도 내 상대 확률(√)이며 모델 간 절대 확률 비교가 아님. © OSM contributors, ODbL',fontsize=9,color='#536b78')
 fig.savefig(D/f'example_{fam}.png',dpi=150);plt.close(fig)
 print('gallery',fam,pid,flush=True)
pid='E09'
fig,axs=plt.subplots(3,4,figsize=(16,12.3));fig.subplots_adjust(left=.04,right=.98,top=.86,bottom=.12,wspace=.1,hspace=.27)
fig.text(.04,.97,'최종안의 시간별 알림 영역: 같은 사람의 세 미래',fontsize=23,weight='bold')
fig.text(.04,.915,'고정 E09 · 첫 새 seed2026101231 · 개인화30%·문헌70% / res9 / 상한5.8㎢ · 체크포인트 이어서 계산',fontsize=11)
bbox=bounds(pid,[1,2,4,6],['candidate'])
for row,f in enumerate(future):
 for col,hr in enumerate([1,2,4,6]):panel(axs[row,col],pid,hr,f,'candidate',bbox,future_names[f]+f' · {hr}시간')
fig.text(.04,.068,'검정: 실제 발송 영역 / 빨강: 정답 경로 / 파랑: 시작 / 자주: 시간별 정답. 12패널 모두 동일 지리 범위.',fontsize=11)
fig.text(.04,.035,'발견·실제 푸시 수신 검증이 아님. 정답 경로는 표시·평가용이며 예측 입력에 넣지 않음. © OSM contributors, ODbL',fontsize=10,color='#536b78')
fig.savefig(D/'final_time_maps.png',dpi=160);plt.close(fig)
(D/'examples_manifest.json').write_text(json.dumps({'selection_rule':'first valid person ID per family, fixed first fresh truth seed and prediction seed; E09 final timeline retained from prior fixed example; no filtering by success','selected_people':picked,'truth_seed':2026101231,'prediction_seed':104729,'panels':examples,'new_model_calls':0,'external_calls':0,'actual_push':0},ensure_ascii=False,indent=2)+'\n')
print('figures complete',len(examples))


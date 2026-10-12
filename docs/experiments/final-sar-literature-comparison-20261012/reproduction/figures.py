"""Render the fixed two-arm study; never select examples based on outcomes."""
from pathlib import Path
import os,sys,json,math
os.environ['MPLCONFIGDIR']='/tmp/cbh-mpl'
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt,font_manager
from matplotlib.collections import LineCollection,PolyCollection
import h3,numpy as np,osmnx as ox
from shapely.geometry import Polygon
from shapely.ops import unary_union
O=Path(__file__).resolve().parents[1];R=O.parents[2];D=O/'results';F=O/'figures';F.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());s=read(D/'summary.json');v=s['datasets']['fresh_confirmation'];sels=read(D/'selections.json');truth=read(O/'truth_private.json')
font='/System/Library/Fonts/AppleSDGothicNeo.ttc';font_manager.fontManager.addfont(font);plt.rcParams.update({'font.family':font_manager.FontProperties(fname=font).get_name(),'axes.unicode_minus':False})
arms=['current_literature70','personalized_sar70'];names=['현행: 마음 개인화30 + 문헌70','비교: 마음 개인화30 + 개인별 SAR70'];colors=['#367FA3','#CD8B32'];futures=['habitual','departure','contradictory'];fn=['개인화 준수','중간 이탈','처음부터 반대']
fig,axs=plt.subplots(1,3,figsize=(15.5,6.3));fig.subplots_adjust(left=.065,right=.97,top=.75,bottom=.24,wspace=.32)
fig.text(.055,.94,'마지막 동일 조건 비교: 70% 채널만 바꾸면?',fontsize=22,weight='bold')
fig.text(.055,.875,'39명 · 새 합성351경로 · 안별2,808판정 / 개인화30%·res9·5.8㎢ 상한·동일 선택기·제보 없는 초기 예측',fontsize=11)
for i,a in enumerate(arms):
 vals=[v['profiles'][a]['futures'][f]['hit_pct'] for f in futures]
 bars=axs[0].bar(np.arange(3)+(i-.5)*.32,vals,width=.30,color=colors[i],label=names[i])
 for bar,z in zip(bars,vals):axs[0].text(bar.get_x()+bar.get_width()/2,z+1.8,f'{z:.2f}',ha='center',fontsize=10)
axs[0].set_xticks(range(3),fn);axs[0].set_ylim(0,116);axs[0].set_ylabel('정답 위치 포함률 (%)');axs[0].legend(fontsize=8,loc='upper right')
for ax,key,title in [(axs[1],'mean_area_km2','평균 실제 알림 대상 면적 (㎢)'),(axs[2],'efficiency_pp_per_km2','전체 포함률 / 평균 면적 (%p/㎢)')]:
 vals=[v['profiles'][a]['overall'][key] for a in arms];bars=ax.bar(range(2),vals,color=colors,width=.6)
 ax.set_xticks(range(2),['현행 문헌70','비교 SAR70']);ax.set_title(title,fontsize=12);ax.set_ylim(0,max(vals)*1.22)
 for b,z in zip(bars,vals):ax.text(b.get_x()+b.get_width()/2,z+.05,f'{z:.3f}',ha='center',fontsize=12)
for ax in axs:ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True);ax.spines[['top','right']].set_visible(False)
chosen='현행 문헌70 유지' if s['decision']['selection']=='current_literature70' else '기존 SAR70 모드 선택'
fig.text(.055,.13,f'사전 고정 기준의 선택: {chosen} / 엔진 변경0 · 모델 호출0 · 실제 알림0',fontsize=12,weight='bold')
fig.text(.055,.075,'새 경로를 만든 뒤 두 안을 조정하지 않았습니다. 같은 합성 사람의 스트레스 시험이며 실제 행동 발생률·발견률·푸시 도착률이 아닙니다.',fontsize=9,color='#52636E')
fig.savefig(F/'comparison.png',dpi=175);plt.close(fig)
fig,axs=plt.subplots(1,2,figsize=(13,5.6));fig.subplots_adjust(left=.17,right=.97,top=.78,bottom=.2,wspace=.40)
fig.text(.045,.94,'개인별 SAR70로 바꿀 때의 차이와 불확실성',fontsize=20,weight='bold')
keys=['habitual','departure','contradictory','overall'];labels=[*fn,'전체']
for ax,metric,title in [(axs[0],'hit_pp','위치 포함률 차이 (%p)'),(axs[1],'efficiency_pp_per_km2','면적당 효율 차이 (%p/㎢)')]:
 vals=[v['sar_minus_current'][f][metric] for f in keys];y=np.arange(4)
 point=np.array([z['point'] for z in vals]);lo=np.array([z['ci95'][0] for z in vals]);hi=np.array([z['ci95'][1] for z in vals])
 ax.errorbar(point,y,xerr=[point-lo,hi-point],fmt='o',color=colors[1],capsize=5,lw=2);ax.axvline(0,color='#6C7983',lw=1,ls='--');ax.set_yticks(y,labels);ax.set_ylim(3.8,-.35);ax.set_title(title,fontsize=12);ax.grid(axis='x',alpha=.15)
 for yy,z in zip(y,vals):ax.annotate(f'{z["point"]:+.2f} [{z["ci95"][0]:+.2f}, {z["ci95"][1]:+.2f}]',(z['point'],yy),xytext=(0,-20),textcoords='offset points',ha='center',fontsize=8)
fig.text(.045,.06,'양수: 비교 SAR70가 높음 / 음수: 현행 문헌70가 높음. 사람 단위 군집 부트스트랩10,000회·95% 구간.',fontsize=10)
fig.savefig(F/'paired_changes.png',dpi=175);plt.close(fig)
def poly(c):return Polygon([(lng,lat) for lat,lng in h3.cell_to_boundary(c)])
def outline(ax,g):
 if g.geom_type=='Polygon':
  ax.plot(*g.exterior.xy,color='#25363F',lw=.9,zorder=3)
  for ring in g.interiors:ax.plot(*ring.xy,color='#25363F',lw=.6,zorder=3)
 elif hasattr(g,'geoms'):
  for child in g.geoms:outline(ax,child)
g=ox.load_graphml(R/'결선/실험/MIND_completion_20261004/map_full_support/kintex_walk.graphml');examples=[]
for pid in ['E01','E04','E09']:
 selected={a:next(z for z in sels if z['person_id']==pid and z['prediction_seed']==104729 and z['hour']==4 and z['arm']==a) for a in arms}
 ts={f:next(z for z in truth if z['person_id']==pid and z['truth_seed']==2026101261 and z['future']==f) for f in futures}
 geom=unary_union([poly(c) for z in selected.values() for c in z['target_cells']]);bb=geom.bounds;positions=[z for t in ts.values() for z in t['path'] if z['minute']<=240]
 bounds=(min(bb[0],min(z['lng'] for z in positions))-.002,max(bb[2],max(z['lng'] for z in positions))+.002,min(bb[1],min(z['lat'] for z in positions))-.002,max(bb[3],max(z['lat'] for z in positions))+.002)
 lines=[]
 for u,w,data in g.edges(data=True):
  a,b=g.nodes[u],g.nodes[w]
  if not (bounds[0]<=a['x']<=bounds[1] and bounds[2]<=a['y']<=bounds[3]) and not (bounds[0]<=b['x']<=bounds[1] and bounds[2]<=b['y']<=bounds[3]):continue
  geometry=data.get('geometry');lines.append(list(geometry.coords) if geometry is not None else [(a['x'],a['y']),(b['x'],b['y'])])
 fig,axs=plt.subplots(3,2,figsize=(10,13));fig.subplots_adjust(left=.035,right=.97,top=.88,bottom=.085,wspace=.10,hspace=.24)
 fig.text(.035,.96,f'{pid} · 같은 4시간 정답에서 두 알림 구역 비교',fontsize=21,weight='bold')
 fig.text(.035,.918,'정답seed2026101261 · 예측seed104729 · res9 · 같은 지도 범위 / E01·E04·E09 사전 고정',fontsize=10)
 for row,f in enumerate(futures):
  t=ts[f];path=[z for z in t['path'] if z['minute']<=240];pos=next(z['position'] for z in t['snapshots'] if z['hour']==4)
  for col,arm in enumerate(arms):
   ax=axs[row,col];z=selected[arm];cells=z['target_cells'];hit=h3.latlng_to_cell(pos['lat'],pos['lng'],9) in cells
   ax.add_collection(LineCollection(lines,colors='#B4C0C7',linewidths=.24,zorder=1))
   ax.add_collection(PolyCollection([list(poly(c).exterior.coords) for c in cells],facecolors=colors[col],alpha=.38,edgecolors='white',linewidths=.24,zorder=2));outline(ax,unary_union([poly(c) for c in cells]))
   ax.plot([z['lng'] for z in path],[z['lat'] for z in path],color='#E13A61',lw=1.6,zorder=4)
   ax.scatter(path[0]['lng'],path[0]['lat'],s=32,color='#0B8EA8',edgecolors='white',zorder=5);ax.scatter(pos['lng'],pos['lat'],s=48,marker='D',color='#B32EB0',edgecolors='white',zorder=5)
   ax.set_xlim(bounds[:2]);ax.set_ylim(bounds[2:]);ax.set_aspect(1/math.cos(math.radians(pos['lat'])));ax.set_xticks([]);ax.set_yticks([])
   ax.set_title(fn[row]+' · '+('현행 문헌70' if col==0 else '비교 개인별 SAR70')+f'\n{z["area_km2"]:.2f}㎢ · '+('정답 포함' if hit else '정답 미포함'),fontsize=11,color='#214454' if hit else '#A13F39')
   examples.append({'person_id':pid,'future':f,'arm':arm,'hour':4,'prediction_seed':104729,'truth_seed':2026101261,'area_km2':z['area_km2'],'hit':hit})
 fig.text(.035,.044,'색칠: 실제 알림 대상 / 검정: 대상 경계 / 빨강: 평가용 경로 / 자주색◆: 4시간 정답 / 파랑●: 시작',fontsize=9)
 fig.text(.035,.02,'서로 다른 색은 비교안을 구분합니다. 색칠 비율이 개인화 가중치가 아닙니다. © OpenStreetMap contributors, ODbL.',fontsize=8)
 fig.savefig(F/f'{pid}_three_futures.png',dpi=170);plt.close(fig)
(D/'figure_examples.json').write_text(json.dumps(examples,ensure_ascii=False,indent=2)+'\n')
print('Rendered summary, paired confidence intervals and three fixed map examples',flush=True)

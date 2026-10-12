"""Render the frozen study from local artifacts; never optimize against truth."""
from pathlib import Path
import json, math, os, shutil, hashlib, sys
os.environ['MPLCONFIGDIR']='/tmp/cbh-mpl'
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt, font_manager
from matplotlib.collections import PolyCollection, LineCollection
import h3, numpy as np, osmnx as ox
from shapely.geometry import Polygon, shape
from shapely.ops import unary_union

O=Path(__file__).resolve().parents[1]; R=O.parents[2]; D=O/'results'
CORE=R/'결선/개발/cbh-independent-alert-core-20261011'
sys.path.insert(0,str(CORE/'backend'))
from app.geo.h3cover import cover
DOC=CORE/'docs/experiments/directional-alert-safety-20261012'
DOC.mkdir(parents=True,exist_ok=True); (DOC/'figures').mkdir(exist_ok=True)
def read(path): return json.loads(path.read_text())
s=read(D/'confirmation_summary.json'); rows=read(D/'confirmation_rows.json')
sels=read(D/'confirmation_selections.json'); truth=read(O/'truth_private.json')
p=read(O/'protocol.json'); e=read(D/'exploration_summary.json')
font='/System/Library/Fonts/AppleSDGothicNeo.ttc'
font_manager.fontManager.addfont(font)
plt.rcParams.update({'font.family':font_manager.FontProperties(fname=font).get_name(),'axes.unicode_minus':False})
names={'alert_district_proxy':'기존 방식·구 단위 대리지표','alert_city_proxy':'기존 방식·시 단위 대리지표',
 'preliminary':'본선','current':'현재 유지안·개인화30/res9',
 'directional_candidate':'원구역100% + 반대 방향5%',
 'personal50_res8':'개인화50/res8','personal70_res8':'개인화70/res8','personal90_res8':'개인화90/res8',
 'best_directional50_res8':'개인화50/res8·방향20% 예약','stat_only_matched_area':'통계만·동일 면적 상한'}
futures=['habitual','departure','contradictory']; fn=['개인화 준수','중간 이탈','처음부터 반대']
arms=['preliminary','current','directional_candidate','personal50_res8','best_directional50_res8']
colors=['#8995a0','#377da5','#d79733','#b394c8','#79629c']
fig,axs=plt.subplots(1,3,figsize=(18,6.5)); fig.subplots_adjust(left=.05,right=.98,top=.76,bottom=.24,wspace=.25)
fig.text(.04,.94,'반대 방향만 계산한 안전망과 개인화50%·res8',fontsize=22,weight='bold')
fig.text(.04,.88,'새 합성351경로 · 설정별2,808판정 · 39명 · 2예측seed · 1/2/4/6시간 / 채택 기준 미통과 → 기본값 유지',fontsize=11)
for i,a in enumerate(arms):
 vals=[s['profiles'][a]['futures'][f]['hit_pct'] for f in futures]
 bs=axs[0].bar(np.arange(3)+(i-2)*.16,vals,width=.16,color=colors[i],label=names[a])
 for b,v in zip(bs,vals): axs[0].text(b.get_x()+.08,v+1.3,f'{v:.1f}',ha='center',fontsize=7)
axs[0].set_xticks(range(3),fn); axs[0].set_ylim(0,118); axs[0].set_ylabel('定답 위치 포함률 (%)'.replace('定','정'))
axs[0].legend(fontsize=7,loc='upper right')
for ax,key,title in [(axs[1],'mean_area_km2','평균 알림 대상 면적 (㎢)'),(axs[2],'efficiency_pp_per_km2','전체 포함률 / 평균 면적 (%p/㎢)')]:
 vals=[s['profiles'][a]['overall'][key] for a in arms]
 bs=ax.bar(range(len(arms)),vals,color=colors)
 ax.set_xticks(range(len(arms)),['본선','현재','방향 추가','50/res8','50/res8\n방향 예약'])
 for b,v in zip(bs,vals):ax.text(b.get_x()+b.get_width()/2,v+.1,f'{v:.2f}',ha='center',fontsize=10)
 ax.set_ylim(0,max(vals)*1.25);ax.set_title(title,fontsize=12)
for ax in axs:ax.grid(axis='y',alpha=.15)
fig.text(.04,.14,'방향 추가: 현재 적중 손실0건 / 효율 +0.92%, 차이95% CI -0.078~+0.296 → 우월성 미확인',fontsize=12,weight='bold')
fig.text(.04,.085,'50/res8 방향 예약: 효율11.33, 반대33.87% / 준수89.74%로 현재96.69%보다 낮음 → 준수 보존 기준 실패',fontsize=11)
fig.text(.04,.03,'합성 경로 스트레스 평가. 실제 발견률·수신률·임상 정확도·원화 비용이 아님. 세 행동 비중은 동일하며 실제 발생률이 아님.',fontsize=9,color='#536b78')
fig.savefig(DOC/'figures/comparison.png',dpi=170);plt.close(fig)

# All published table values are generated directly from the new confirmation.
table='| 방식 | 준수 % | 이탈 % | 반대 % | 전체 % | 면적 ㎢ | 효율 %p/㎢ |\n|---|---:|---:|---:|---:|---:|---:|\n'
for a in names:
 v=s['profiles'][a]; ov=v['overall']
 table+='| '+names[a]+' | '+' | '.join(f'{v["futures"][f]["hit_pct"]:.2f}' for f in futures)+f' | {ov["hit_pct"]:.2f} | {ov["mean_area_km2"]:.2f} | {ov["efficiency_pp_per_km2"]:.2f} |\n'
(DOC/'comparison_table.md').write_text(table)

def poly(c):return Polygon([(lng,lat) for lat,lng in h3.cell_to_boundary(c)])
def outline(ax,g,color='#233b46'):
 if g.is_empty:return
 if g.geom_type=='Polygon':
  ax.plot(*g.exterior.xy,color=color,lw=1.,zorder=3)
  for ring in g.interiors:ax.plot(*ring.xy,color=color,lw=.7,zorder=3)
 elif hasattr(g,'geoms'):
  for child in g.geoms:outline(ax,child,color)
def drawcells(ax,cells,color,alpha=1):
 ax.add_collection(PolyCollection([list(poly(c).exterior.coords) for c in sorted(cells)],facecolors=color,edgecolors='white',linewidths=.22,alpha=alpha,zorder=2))
def selection(pid,arm):return next(z for z in sels if z['person_id']==pid and z['prediction_seed']==104729 and z['hour']==4 and z['arm']==arm)
def localtruth(pid,f):return next(z for z in truth if z['person_id']==pid and z['truth_seed']==2026101251 and z['future']==f)
g=ox.load_graphml(R/'결선/실험/MIND_completion_20261004/map_full_support/kintex_walk.graphml')
def roads(bounds):
 west,east,south,north=bounds
 lines=[]
 for u,v,data in g.edges(data=True):
  a=g.nodes[u];b=g.nodes[v]
  if not (west<=a['x']<=east and south<=a['y']<=north) and not (west<=b['x']<=east and south<=b['y']<=north):continue
  geom=data.get('geometry'); lines.append(list(geom.coords) if geom is not None else [(a['x'],a['y']),(b['x'],b['y'])])
 return lines
manifest=[]; exampledata=[]
def plotexamples(pid):
 localarms=['preliminary','current','directional_candidate','best_directional50_res8']
 selected={a:selection(pid,a) for a in localarms}
 core=set(selected['current']['target_cells']); extra=set(selected['directional_candidate']['target_cells'])-core
 assert core<=set(selected['directional_candidate']['target_cells'])
 ts={f:localtruth(pid,f) for f in futures}
 geom=unary_union([poly(c) for z in selected.values() for c in z['target_cells']])
 coords=[z for t in ts.values() for z in t['path'] if z['minute']<=240];b=geom.bounds
 bounds=(min(b[0],min(z['lng'] for z in coords))-.002,max(b[2],max(z['lng'] for z in coords))+.002,min(b[1],min(z['lat'] for z in coords))-.002,max(b[3],max(z['lat'] for z in coords))+.002)
 lines=roads(bounds)
 fig,axs=plt.subplots(3,4,figsize=(16,12.5),squeeze=False);fig.subplots_adjust(left=.025,right=.98,top=.875,bottom=.10,wspace=.07,hspace=.26)
 fig.text(.03,.96,f'{pid} · 같은 새 정답으로 준수·이탈·반대를 비교',fontsize=22,weight='bold')
 fig.text(.03,.915,'정답seed2026101251 · 예측seed104729 · 4시간 · E01/E04/E09 고정 제시 / 성공·실패에 따라 예제 교체하지 않음',fontsize=10)
 for row,f in enumerate(futures):
  t=ts[f];path=[z for z in t['path'] if z['minute']<=240];pos=next(z['position'] for z in t['snapshots'] if z['hour']==4)
  for col,a in enumerate(localarms):
   z=selected[a];ax=axs[row,col];cells=set(z['target_cells'])
   ax.add_collection(LineCollection(lines,colors='#b2bfc7',linewidths=.25,zorder=1))
   if a=='directional_candidate':drawcells(ax,core,'#a9cee3');drawcells(ax,extra,'#f2b84b')
   elif a=='best_directional50_res8':
    safety=set(z['safety_cells'] or []); targets=cover(safety,8)
    drawcells(ax,cells-targets,'#c4acd5');drawcells(ax,cells&targets,'#f2b84b')
   else:drawcells(ax,cells,'#c5ced4' if a=='preliminary' else '#a9cee3')
   outline(ax,unary_union([poly(c) for c in cells]))
   ax.plot([z['lng'] for z in path],[z['lat'] for z in path],c='#d93355',lw=1.5,zorder=4)
   ax.scatter(pos['lng'],pos['lat'],c='#af22b6',marker='D',s=40,edgecolor='white',zorder=5)
   ax.scatter(path[0]['lng'],path[0]['lat'],c='#078ebb',s=25,edgecolor='white',zorder=5)
   hit=h3.latlng_to_cell(pos['lat'],pos['lng'],z['target_res']) in cells
   ax.set_title(fn[row]+' · '+names[a].replace('·','\n')+f'\n{z["area_km2"]:.2f}㎢ · '+('정답 포함' if hit else '정답 미포함'),fontsize=10,color='#1f3a46' if hit else '#9a4337')
   ax.set_xlim(bounds[:2]);ax.set_ylim(bounds[2:]);ax.set_aspect(1/math.cos(math.radians(pos['lat'])));ax.set_xticks([]);ax.set_yticks([])
   manifest.append(dict(person_id=pid,future=f,truth_seed=2026101251,prediction_seed=104729,hour=4,arm=a,hit=hit,area_km2=z['area_km2']))
 fig.text(.03,.062,'파랑: 현재 알림 구역 / 주황: 계산한 방향 안전망 / 자주색 구역: 50%·res8의 기본 부분 / 검정: 대상 경계',fontsize=10)
 fig.text(.03,.025,'빨강: 평가용 정답 경로 / 자주색◆: 4시간 위치 / 파란●: 시작점. 같은 그림은 모든 패널 동일 범위. © OSM contributors, ODbL',fontsize=9)
 fig.savefig(DOC/f'figures/{pid}_three_futures.png',dpi=150);plt.close(fig)
 exampledata.append(dict(person_id=pid,bounds=bounds,selections=selected,truth=ts))
for pid in ['E01','E04','E09']:plotexamples(pid)

# Show near and far directional hypotheses, with the truth added only as overlay.
from pyproj import Geod
dm=read(D/'directional_maps/E09.json')
scores=[next(z for z in dm['snapshots'] if z['prediction_seed']==104729 and z['hour']==4 and z['progress']==p) for p in [.35,.65]]
local=next(z for z in exampledata if z['person_id']=='E09')
bounds=local['bounds']; lines=roads(bounds)
fig,axs=plt.subplots(1,3,figsize=(13,7.3));fig.subplots_adjust(left=.04,right=.98,top=.78,bottom=.14,wspace=.1)
fig.text(.04,.95,'E09 · 반대 방향은 같아도 거리와 면적 예산은 별도 문제',fontsize=20,weight='bold')
fig.text(.04,.885,'개인화 평균 방향을180° 반전 + 도로거리/보행시간 제약 / 정답 위치를 선택기에 넣지 않음',fontsize=10)
t=localtruth('E09','contradictory');path=[z for z in t['path'] if z['minute']<=240];origin=path[0]
for i,ax in enumerate(axs):
 ax.add_collection(LineCollection(lines,colors='#b7c5cc',linewidths=.25,zorder=1))
 core=selection('E09','current')['target_cells'];drawcells(ax,core,'#a9cee3',.65)
 if i<2:
  z=scores[i];ranked=sorted(z['scores'].items(),key=lambda x:-x[1]);cumulative=0;chosen=[]
  for c,value in ranked:
   chosen.append((c,value));cumulative+=value
   if cumulative>=.95:break
  peak=max(v for c,v in chosen)
  polys=[list(poly(c).exterior.coords) for c,v in chosen]
  shade=[plt.cm.YlOrRd(.18+.75*math.sqrt(v/peak)) for c,v in chosen]
  ax.add_collection(PolyCollection(polys,facecolors=shade,edgecolors='none',alpha=.65,zorder=3))
  title=f'距리 중심{int(z["progress"]*100)}%'.replace('距','거')+'\n반대 방향 상대 점수 상위95%'
 else:
  extra=set(selection('E09','directional_candidate')['target_cells'])-set(core)
  drawcells(ax,extra,'#f2b84b');outline(ax,unary_union([poly(c) for c in core|extra] if isinstance(core,set) else [poly(c) for c in set(core)|extra]))
  title='실제로 선택한 추가4구역\n평가 위치까지 모두 포함하지 못함'
 ax.plot([z['lng'] for z in path],[z['lat'] for z in path],c='#d93355',lw=1.5,zorder=4)
 ax.scatter(path[-1]['lng'],path[-1]['lat'],c='#af22b6',marker='D',s=45,edgecolor='white',zorder=5)
 bearing=scores[0]['metadata']['reverse_heading_deg'];lng,lat,_=Geod(ellps='WGS84').fwd(origin['lng'],origin['lat'],bearing,3000.)
 ax.annotate('',xy=(lng,lat),xytext=(origin['lng'],origin['lat']),arrowprops=dict(arrowstyle='->',color='#384b88',lw=2),zorder=6)
 ax.set_xlim(bounds[:2]);ax.set_ylim(bounds[2:]);ax.set_aspect(1/math.cos(math.radians(37.67)));ax.set_xticks([]);ax.set_yticks([]);ax.set_title(title,fontsize=11)
fig.text(.04,.08,'점수 색은 보정된 반대 행동 확률이 아님. 35/65% 거리 후보는 이전 경로에서 비교했고 새 정답에 맞춰 고르지 않음.',fontsize=10)
fig.text(.04,.035,'빨강·자주색은 평가용 정답; 파랑 화살표는 계산된 반대 방향. 추가 예산은 최대0.29㎢. © OSM contributors, ODbL',fontsize=9)
fig.savefig(DOC/'figures/direction_mechanism.png',dpi=160);plt.close(fig)

# Explicitly show administrative comparison with the same geographic extent.
E=R/'결선/실험/EFFICIENCY_KINTEX_v1_20261009/service_comparison'
admin=read(E/'baseline_selections.json'); ar=next(z for z in admin['rows'] if z['person_id']=='E09')
geoms={k:shape(read(E/f'boundaries/{k}_osm.geojson')['features'][0]['geometry']) for k in ['ilsanseo','ilsandong','goyang']}
district=unary_union([geoms[k] for k in ar['districts']]); b=district.bounds
bounds=(b[0]-.002,b[2]+.002,b[1]-.002,b[3]+.002); lines=roads(bounds)
fig,axs=plt.subplots(1,4,figsize=(16,6.2)); fig.subplots_adjust(top=.78,bottom=.13,wspace=.07)
fig.text(.03,.94,'기존 행정구역 대리지표와 선택 구역은 얼마나 다른가',fontsize=21,weight='bold')
fig.text(.03,.87,'E09 · 같은 지리 범위 · 구 단위 면적은 저장된 경계 기반 가정 / 실제 문자 발송 범위·통신사 수신 로그는 미확보',fontsize=10)
for i,a in enumerate(['alert_district_proxy','preliminary','current','directional_candidate']):
 ax=axs[i];ax.add_collection(LineCollection(lines,colors='#c2ccd1',linewidths=.18,zorder=1))
 if i==0:
  polys=list(district.geoms) if hasattr(district,'geoms') else [district]
  ax.add_collection(PolyCollection([list(x.exterior.coords) for x in polys],facecolors='#d9dfe2',alpha=.7,zorder=2));outline(ax,district);area=ar['district_area_km2']
 else:
  z=selection('E09',a);drawcells(ax,z['target_cells'],'#a9cee3');outline(ax,unary_union([poly(c) for c in z['target_cells']]));area=z['area_km2']
 for f in futures:
  path=[z for z in localtruth('E09',f)['path'] if z['minute']<=240]
  ax.plot([z['lng'] for z in path],[z['lat'] for z in path],lw=1,c='#d63354',zorder=4)
 ax.set_xlim(bounds[:2]);ax.set_ylim(bounds[2:]);ax.set_aspect(1/math.cos(math.radians(37.67)));ax.set_xticks([]);ax.set_yticks([]);ax.set_title(names[a]+f'\n{area:.2f}㎢',fontsize=10)
fig.text(.03,.035,'구역이 작거나 갈라져 보이는 것 자체는 성능 증거가 아님. 같은 정답 포함률과 실제 대상 면적의 비율로 판단. © OSM contributors, ODbL',fontsize=10)
fig.savefig(DOC/'figures/administrative_comparison.png',dpi=160);plt.close(fig)

# Person-level outcomes reveal heterogeneous behavior without selecting successes.
per=[]
for pid in p['people']:
 v={}
 for a in arms:
  rr=[z for z in rows if z['person_id']==pid and z['arm']==a]
  v[a]={'overall':100*np.mean([z['hit'] for z in rr]),'area':np.mean([z['area_km2'] for z in rr]),
        **{f:100*np.mean([z['hit'] for z in rr if z['future']==f]) for f in futures}}
 per.append({'person_id':pid,'profiles':v})
fig,axs=plt.subplots(1,2,figsize=(14,11));fig.subplots_adjust(left=.10,right=.97,top=.88,bottom=.09,wspace=.5)
fig.text(.06,.95,'39명 전원 · 준수와 반대의 차이를 함께 확인',fontsize=22,weight='bold')
for ax,arm in zip(axs,['directional_candidate','best_directional50_res8']):
 values=np.array([[z['profiles'][arm][f]-z['profiles']['current'][f] for f in futures] for z in per])
 ax.imshow(values,vmin=-30,vmax=30,cmap='RdBu',aspect='auto');ax.set_yticks(range(len(per)),[z['person_id'] for z in per],fontsize=8);ax.set_xticks(range(3),fn);ax.set_title(names[arm]+'\n현재 대비 포함률 변화 (%p)',fontsize=12)
 for y,line in enumerate(values):
  for x,v in enumerate(line):ax.text(x,y,f'{v:+.1f}',ha='center',va='center',fontsize=7,color='white' if abs(v)>18 else '#22333d')
fig.text(.06,.025,'사람별 각 행동24판정(3정답seed×2예측seed×4시점). 파랑 개선 / 빨강 저하. 합성 입력39명이며 새로운 사람 검증은 아님.',fontsize=10)
fig.savefig(DOC/'figures/all_people.png',dpi=150);plt.close(fig)

(DOC/'figure_examples.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
(DOC/'example_data.json').write_text(json.dumps(exampledata,ensure_ascii=False,separators=(',',':'))+'\n')
(DOC/'per_person.json').write_text(json.dumps(per,ensure_ascii=False,indent=2)+'\n')
for src in ['protocol.json','truth_manifest.json']:
 shutil.copy2(O/src,DOC/src)
for src in ['confirmation_summary.json','truth_physics_audit.json','exploration_summary.json','candidate_configs.json','adaptive_frozen_selection.json']:
 shutil.copy2(D/src,DOC/src)
decision={'status':'not_adopted','retained_default':{'personal_weight':.3,'literature_weight':.7,'target_res':9,'area_cap_km2':5.8},
 'requested_minimum50_res8':'experimented; not made default because following preservation failed',
 'directional_candidate':s['decision'],'live_directional_selector_enabled':False,
 'limits':['same synthetic people with fresh random road paths; no clinical truth','directional score is uncalibrated','generic stub fanout only; app/web integration unperformed','administrative alert comparison is a proxy, no actual dispatch logs']}
(DOC/'final_decision.json').write_text(json.dumps(decision,ensure_ascii=False,indent=2)+'\n')
print('published',DOC, 'example checks',len(manifest),flush=True)

from pathlib import Path
import json,os,sys,math
os.environ.update(MPLCONFIGDIR='/tmp/cbh-mpl',PERSIST_STORAGE='false',PUSH_TARGET_RES='9')
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt,font_manager
from matplotlib.collections import PolyCollection,LineCollection
from shapely.geometry import Polygon,Point,shape
from shapely.ops import unary_union
import h3,numpy as np
O=Path(__file__).resolve().parents[1];R=O.parents[2];E=R/'결선/실험/EFFICIENCY_KINTEX_v1_20261009';X=R/'결선/실험/CHANNEL_ALERT_repair_20261011';C=R/'결선/개발/cbh-independent-alert-core-20261011';sys.path.insert(0,str(C/'backend'))
from app.phase2.combine import alpha_pool
from app.phase3 import alerts
from app.phase3.area_budget import cell_area_km2
from app.config import settings
font='/System/Library/Fonts/AppleSDGothicNeo.ttc';font_manager.fontManager.addfont(font);plt.rcParams.update({'font.family':font_manager.FontProperties(fname=font).get_name(),'axes.unicode_minus':False})
D=O/'results';summary=json.loads((D/'validation_summary.json').read_text());stats=summary['profiles'];names=['기존 기본값','문헌10% + 6.37㎢'];arms=['current','area6'];colors=['#20856b','#387ab2'];fig,axs=plt.subplots(1,3,figsize=(15,6.8));fig.subplots_adjust(left=.055,right=.98,top=.76,bottom=.28,wspace=.35)
fig.text(.035,.94,'새 정답 경로 검증: 이탈 포함률 상승, 효율 기준은 미통과',fontsize=21,weight='bold');fig.text(.035,.872,'기존 합성39명 · 새 검증234경로 · 각 설정1,872판정 · 개인화90% / 통계10% · res9',fontsize=11)
for ax,k,title,ylabel in [(axs[0],'efficiency_pp_per_km2','면적당 정답 포함 효율','포함률(%) ÷ 평균 면적(㎢)'),(axs[1],'mean_delivery_area_km2','실제 발송 대상 평균 면적','면적(㎢)')]:
 vals=[stats[a]['overall'][k] for a in arms];bars=ax.bar(names,vals,color=colors,width=.6)
 for b,v in zip(bars,vals):ax.text(b.get_x()+b.get_width()/2,v+.13,f'{v:.2f}',ha='center',fontsize=12)
 ax.set_title(title);ax.set_ylabel(ylabel);ax.set_ylim(0,max(vals)*1.27);ax.grid(axis='y',alpha=.18)
ax=axs[2];x=np.arange(3)
for i,a in enumerate(arms):
 vals=[stats[a]['futures'][f]['hit_pct'] for f in ['habitual','departure','contradictory']];bars=ax.bar(x+(i-.5)*.36,vals,width=.36,color=colors[i],label=names[i])
 for b,v in zip(bars,vals):ax.text(b.get_x()+b.get_width()/2,v+1.5,f'{v:.2f}',ha='center',fontsize=8)
ax.set_xticks(x,['습관 행동','중간 이탈','반대 행동']);ax.set_ylim(0,113);ax.set_title('정답 미래별 포함률');ax.set_ylabel('포함률 (%)');ax.legend(fontsize=8);ax.grid(axis='y',alpha=.18)
ci=stats['area6']['comparisons']['overall']['delta']['efficiency_pp_per_km2']['ci95'];fig.text(.035,.205,f'효율 차이 95% CI {ci[0]:+.2f} ~ {ci[1]:+.2f}: 개선 확정 불가. 습관·중간 이탈 비열등성 CI 기준도 미통과.',fontsize=11,weight='bold');fig.text(.035,.13,'자동 적용 확정: 기존 기본값 유지. 문헌+면적 상한은 실제 알림 로직에 연결된 명시적 실험 설정으로 보존.',fontsize=11);fig.text(.035,.065,'새 인물·실제 실종 정답 검증 아님 / 습관·이탈·반대는 동일 비중 스트레스 조건 / 실푸시0 · 면적은 비용 대리값',fontsize=10,color='#536b78');fig.savefig(D/'fresh_validation_comparison.png',dpi=180);plt.close(fig)
# Fixed existing illustrative person E09, first validation route seed, contradictory future.
pid='E09';seed=104729;hour=4;truth=next(t for t in json.loads((O/'truth_private.json').read_text()) if t['person_id']==pid and t['truth_seed']==2026101202 and t['future']=='contradictory');pos=next(t['position'] for t in truth['snapshots'] if t['hour']==hour);path=[v for v in truth['path'] if v['minute']<=hour*60];d=json.loads((R/'결선/PR_설명보충_20261011/최종성능_그림/figure_data.json').read_text())['map_example'];selection=next(v for v in json.loads((E/'service_comparison/baseline_selections.json').read_text())['rows'] if v['person_id']==pid);district=unary_union([shape(json.loads((E/f'service_comparison/boundaries/{k}_osm.geojson').read_text())['features'][0]['geometry']) for k in selection['districts']]);s=next(v for v in json.loads((X/f'results_independent_sar/{pid}_{seed}.json').read_text())['snapshots'] if v['hour']==hour);lit=next(v['cells'] for v in json.loads((R/f'결선/실험/SAR_DISTANCE_ONLY_20261012/results/distance_maps/{pid}.json').read_text())['snapshots'] if v['hour']==hour)
def polygon(c):return Polygon([(lng,lat) for lat,lng in h3.cell_to_boundary(c)])
def draw(ax,g,**kw):
 if g.is_empty:return
 if g.geom_type=='Polygon':ax.fill(*g.exterior.xy,**kw)
 elif hasattr(g,'geoms'):
  for v in g.geoms:draw(ax,v,**kw)
fig,axs=plt.subplots(1,4,figsize=(18,7));fig.subplots_adjust(left=.035,right=.98,top=.78,bottom=.255,wspace=.10);fig.text(.035,.94,'동일한 새 정답 경로: 기존 알림 방식 / 본선 / 결선 / 면적 상한',fontsize=21,weight='bold');fig.text(.035,.875,'KINTEX · 합성 E09 · 새 반대 행동 경로 · 4시간 · prediction seed104729 / truth seed2026101202',fontsize=11);examples=[]
for i,ax in enumerate(axs):
 if i==0:
  prob={};selected=[];targets=[];size=d['panels'][3]['area'];hit=district.covers(Point(pos['lng'],pos['lat']));geom=district;label='기존 관련 행정구역 근사';draw(ax,district,facecolor='#d2dde3',edgecolor='#526f80',alpha=.65,zorder=2);mass=None
 elif i==1:
  pre=d['panels'][4];prob=pre['probability_cells'];selected=list(prob);targets=pre['alert_cells'];size=pre['area'];hit=h3.latlng_to_cell(pos['lat'],pos['lng'],7) in targets;geom=unary_union([polygon(c) for c in targets]);label='본선 · 당시 발송 정책';mass=None
 else:
  prob=alpha_pool([s['personal'],s['statistical'] if i==2 else lit],[.9,1-.9]);selected=alerts.select_alert_cells(prob,coverage=.95,max_cells=500,policy='coverage' if i==2 else 'area_budget',max_area_km2=6.368199998062131,target_res=9);targets=selected;size=sum(cell_area_km2(c) for c in targets);hit=h3.latlng_to_cell(pos['lat'],pos['lng'],9) in targets;geom=unary_union([polygon(c) for c in targets]);label='결선 · 기존 기본값' if i==2 else '문헌10% · 6.37㎢ 후보';mass=sum(prob[c] for c in selected)
 ax.add_collection(LineCollection(d['roads'],colors='#c1c9ce',linewidths=.3,zorder=1))
 if prob:ax.add_collection(PolyCollection([list(polygon(c).exterior.coords) for c in selected],array=[prob[c] for c in selected],cmap='Oranges' if i==1 else ('Greens' if i==2 else 'Blues'),clim=(0,.15),edgecolors='white',linewidths=.25,zorder=2))
 draw(ax,geom,facecolor='none',edgecolor='#172a35',linewidth=1.6,zorder=3);ax.plot([v['lng'] for v in path],[v['lat'] for v in path],color='#d93251',lw=2,zorder=4);ax.scatter(pos['lng'],pos['lat'],c='#a822bd',marker='D',s=60,edgecolor='white',zorder=5);ax.scatter(d['start']['lng'],d['start']['lat'],c='#1694d2',s=45,edgecolor='white',zorder=5);b=d['bounds'];ax.set_xlim(b[:2]);ax.set_ylim(b[2:]);ax.set_aspect(1/math.cos(math.radians(pos['lat'])));ax.set_xticks([]);ax.set_yticks([]);ax.set_title(label+f'\n{size:.2f}㎢ · 정답 {"포함" if hit else "미포함"}',fontsize=12,pad=12)
 examples.append({'arm':['district_proxy','preliminary_saved_policy','current','area6'][i],'person_id':pid,'prediction_seed':seed,'truth_seed':2026101202,'future':'contradictory','hour':hour,'area_km2':size,'hit':bool(hit),'selected_mass':mass})
fig.text(.035,.19,'색: 예측 확률 / 검정: 발송 대상 경계 / 빨강: 새 정답 경로 / 파랑: 시작 / 자주색: 정답 위치',fontsize=11);fig.text(.035,.125,'기존 방식은 행정구역 근사이며 실제 재난문자 실적이 아님. 본선은 보존된 동일 입력 결과. 화면 밖 구역도 면적에 포함.',fontsize=10);fig.text(.035,.065,'설명용 한 사례이며 전체 성능의 대표값이 아님. 자동 적용은 기존 기본값 유지 / © OpenStreetMap contributors, ODbL',fontsize=10,color='#536b78');fig.savefig(D/'fresh_same_case_comparison.png',dpi=180);plt.close(fig);(D/'figure_example.json').write_text(json.dumps(examples,indent=2)+'\n');print(examples)

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
from app.phase3.area_budget import cell_area_km2
font='/System/Library/Fonts/AppleSDGothicNeo.ttc';font_manager.fontManager.addfont(font);plt.rcParams.update({'font.family':font_manager.FontProperties(fname=font).get_name(),'axes.unicode_minus':False})
D=O/'results';summary=json.loads((D/'confirmation_summary.json').read_text());stats=summary['profiles'];names=['본선','이전 결선','선정 수정안'];arms=['preliminary','current','candidate'];colors=['#d37746','#20856b','#357db0'];fig,axs=plt.subplots(1,3,figsize=(16,7));fig.subplots_adjust(left=.055,right=.98,top=.76,bottom=.28,wspace=.32)
fig.text(.035,.94,'같은 새 정답 경로로 비교: 면적 효율과 세 행동 포함률 개선',fontsize=21,weight='bold');fig.text(.035,.87,'기존 합성39명 · 별도 새351경로 · 설정당2,808판정 · 수정안: 개인화10% + 문헌90%, res9, 상한6.37㎢',fontsize=11)
for ax,k,title,ylabel in [(axs[0],'efficiency_pp_per_km2','면적당 정답 포함 효율','포함률(%) ÷ 평균 면적(㎢)'),(axs[1],'mean_area_km2','실제 발송 대상 평균 면적','면적(㎢)')]:
 vals=[stats[a]['overall'][k] for a in arms];bars=ax.bar(names,vals,color=colors,width=.65)
 for b,v in zip(bars,vals):ax.text(b.get_x()+b.get_width()/2,v+.12,f'{v:.2f}',ha='center',fontsize=12)
 ax.set_title(title);ax.set_ylabel(ylabel);ax.set_ylim(0,max(vals)*1.27);ax.grid(axis='y',alpha=.18)
ax=axs[2];x=np.arange(3)
for i,a in enumerate(arms):
 vals=[stats[a]['futures'][f]['hit_pct'] for f in ['habitual','departure','contradictory']];bars=ax.bar(x+(i-1)*.25,vals,width=.25,color=colors[i],label=names[i])
 for b,v in zip(bars,vals):ax.text(b.get_x()+b.get_width()/2,v+1.3,f'{v:.1f}',ha='center',fontsize=8)
ax.set_xticks(x,['습관 행동','중간 이탈','반대 행동']);ax.set_ylim(0,119);ax.set_title('정답 미래별 포함률');ax.set_ylabel('포함률 (%)');ax.legend(fontsize=8,ncol=3,loc='upper center');ax.grid(axis='y',alpha=.18)
fig.text(.035,.2,'전체 효율 차이95% CI: 본선 대비 +0.69~+2.56 / 이전 결선 대비 +0.34~+1.95 (%p/㎢).',fontsize=11,weight='bold');fig.text(.035,.13,'반대 행동: 본선33.2% → 수정38.5%. 차이CI -2.56~+13.03%p로 본선 대비 개선은 아직 확증되지 않음.',fontsize=11);fig.text(.035,.065,'같은 합성 인물의 새 경로 / 세 미래 동일 비중 스트레스 조건 / 실푸시0 / 포함은 실제 발견·단말 수신이 아님',fontsize=10,color='#536b78');fig.savefig(D/'comparison.png',dpi=180);plt.close(fig)
# Fix E09 / new first seed / 4h before inspecting case hit. No successful-case search.
pid='E09';seed=104729;hour=int(sys.argv[1]) if len(sys.argv)>1 else 4;truth=next(t for t in json.loads((O/'truth_private.json').read_text()) if t['person_id']==pid and t['truth_seed']==2026101211 and t['future']=='contradictory');pos=next(z['position'] for z in truth['snapshots'] if z['hour']==hour);path=[v for v in truth['path'] if v['minute']<=hour*60];background=json.loads((R/'결선/PR_설명보충_20261011/최종성능_그림/figure_data.json').read_text())['map_example'];districts=next(v for v in json.loads((E/'service_comparison/baseline_selections.json').read_text())['rows'] if v['person_id']==pid)['districts'];district=unary_union([shape(json.loads((E/f'service_comparison/boundaries/{k}_osm.geojson').read_text())['features'][0]['geometry']) for k in districts]);s=next(z for z in json.loads((X/f'results_independent_sar/{pid}_{seed}.json').read_text())['snapshots'] if z['hour']==hour);q=next(z['cells'] for z in json.loads((R/f'결선/실험/SAR_DISTANCE_ONLY_20261012/results/distance_maps/{pid}.json').read_text())['snapshots'] if z['hour']==hour);pre=next(z for z in json.loads((E/f'service_comparison/output/people/{pid}/walk_preliminary_{seed}.json').read_text())['snapshots'] if z['hour']==hour);selected=json.loads((D/'confirmation_selections.json').read_text());maps={a:next(z['cells'] for z in selected if z['person_id']==pid and z['prediction_seed']==seed and z['hour']==hour and z['arm']==a) for a in arms}
def polygon(c):return Polygon([(lng,lat) for lat,lng in h3.cell_to_boundary(c)])
def draw(ax,g,**kw):
 if g.is_empty:return
 if g.geom_type=='Polygon':ax.fill(*g.exterior.xy,**kw)
 elif hasattr(g,'geoms'):
  for v in g.geoms:draw(ax,v,**kw)
allgeom=unary_union([polygon(c) for a in arms for c in maps[a]]);b=allgeom.bounds;x0=min(b[0],min(v['lng'] for v in path))-.003;x1=max(b[2],max(v['lng'] for v in path))+.003;y0=min(b[1],min(v['lat'] for v in path))-.003;y1=max(b[3],max(v['lat'] for v in path))+.003
fig,axs=plt.subplots(1,4,figsize=(18,7));fig.subplots_adjust(left=.03,right=.98,top=.77,bottom=.26,wspace=.10);fig.text(.03,.94,'동일한 새 반대 행동 경로: 기존 방식 / 본선 / 이전 결선 / 수정안',fontsize=20,weight='bold');fig.text(.03,.87,f'KINTEX · 합성 E09 · {hour}시간 · prediction seed104729 / truth seed2026101211 · 네 패널 같은 범위',fontsize=11);examples=[]
for i,ax in enumerate(axs):
 if i==0:prob={};cells=[];geom=district;area=abs(__import__('pyproj').Geod(ellps='WGS84').geometry_area_perimeter(district)[0])/1e6;hit=district.covers(Point(pos['lng'],pos['lat']));label='기존 행정구역 알림 근사';draw(ax,district,facecolor='#d6dfe5',edgecolor='#526f80',alpha=.65,zorder=2);arm='district_proxy'
 else:
  arm=arms[i-1];cells=maps[arm];prob=pre['cells'] if arm=='preliminary' else alpha_pool([s['personal'],s['statistical'] if arm=='current' else q],[.9,.1] if arm=='current' else [.1,.9]);geom=unary_union([polygon(c) for c in cells]);area=sum(cell_area_km2(c) for c in cells);hit=h3.latlng_to_cell(pos['lat'],pos['lng'],7 if arm=='preliminary' else 9) in set(cells);label=names[i-1]
 ax.add_collection(LineCollection(background['roads'],colors='#bbc5ca',linewidths=.35,zorder=1))
 if cells:
  # Render real source probability cells; outline true selected native delivery area.
  pcells=list(prob) if arm=='preliminary' else cells;vals=[prob.get(c,0.) for c in pcells];maximum=max(vals) or 1.;ax.add_collection(PolyCollection([list(polygon(c).exterior.coords) for c in pcells],array=[math.sqrt(v/maximum) for v in vals],cmap=['Greys','Oranges','Greens','Blues'][i],clim=(0,1),edgecolors='white',linewidths=.18,zorder=2))
 draw(ax,geom,facecolor='none',edgecolor='#172a35',linewidth=1.4,zorder=3);ax.plot([v['lng'] for v in path],[v['lat'] for v in path],color='#d93251',lw=2,zorder=4);ax.scatter(pos['lng'],pos['lat'],c='#b421b8',marker='D',s=65,edgecolor='white',zorder=5);start=truth['path'][0];ax.scatter(start['lng'],start['lat'],c='#1597d3',s=50,edgecolor='white',zorder=5);ax.set_xlim(x0,x1);ax.set_ylim(y0,y1);ax.set_aspect(1/math.cos(math.radians(pos['lat'])));ax.set_xticks([]);ax.set_yticks([]);ax.set_title(label+f'\n{area:.2f}㎢ · 정답 {"포함" if hit else "미포함"}',fontsize=12,pad=13);examples.append(dict(arm=arm,person_id=pid,hour=hour,truth_seed=2026101211,prediction_seed=seed,area_km2=area,hit=bool(hit)))
fig.text(.03,.19,'색: 예측 확률(최댓값 대비 √ 스케일) / 검정: 실제 발송 대상 경계 / 빨강: 새 정답 경로 / 파랑: 시작 / 자주: 정답',fontsize=11);fig.text(.03,.125,'기존 방식은 행정구역 근사이며 실제 재난문자 성능이 아님. 행정구역 화면 밖 면적도 비용에 포함. 본선은 보존된 당시 정책.',fontsize=10);fig.text(.03,.06,'고정한 한 사례이며 대표 성능은 전체 표 사용. 미포함도 표시 / © OpenStreetMap contributors, ODbL',fontsize=10,color='#536b78');fig.savefig(D/f'same_case_{hour}h.png',dpi=180);plt.close(fig);(D/f'figure_example_{hour}h.json').write_text(json.dumps(examples,indent=2)+'\n');print(examples)

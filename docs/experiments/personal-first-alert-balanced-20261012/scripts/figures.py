from pathlib import Path
import os,json,sys,math
os.environ.update(MPLCONFIGDIR='/tmp/cbh-mpl',PERSIST_STORAGE='false')
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt,font_manager
from matplotlib.collections import PolyCollection,LineCollection
from shapely.geometry import Polygon
from shapely.ops import unary_union
import numpy as np,h3
O=Path(__file__).resolve().parents[1];R=O.parents[2];E=R/'결선/실험/EFFICIENCY_KINTEX_v1_20261009';X=R/'결선/실험/CHANNEL_ALERT_repair_20261011';L=R/'결선/실험/SAR_DISTANCE_ONLY_20261012';C=R/'결선/개발/cbh-independent-alert-core-20261011';sys.path.insert(0,str(C/'backend'))
from app.phase2.combine import alpha_pool
font='/System/Library/Fonts/AppleSDGothicNeo.ttc';font_manager.fontManager.addfont(font);plt.rcParams.update({'font.family':font_manager.FontProperties(fname=font).get_name(),'axes.unicode_minus':False})
D=O/'results';s=json.loads((D/'confirmation_summary.json').read_text());arms=['preliminary','current','candidate','stat_only_control'];names=['본선','복구 결선90:10','개인화30·문헌70','통계만 대조군'];colors=['#d17746','#21846c','#337cb0','#8d9299'];fig,axs=plt.subplots(1,3,figsize=(17,7));fig.subplots_adjust(left=.055,right=.98,top=.76,bottom=.28,wspace=.32)
fig.text(.035,.94,'개인화 준수 성능을 지키면서 이탈도 보완하는지 함께 검증',fontsize=21,weight='bold');fig.text(.035,.87,'새 확인351경로 · 설정당2,808판정 · 개인화 최소30% · 면적 상한5.8㎢ · 통계만 대조군은 제품 후보가 아님',fontsize=11)
for ax,k,title,ylabel in [(axs[0],'efficiency_pp_per_km2','면적당 정답 포함 효율','포함률(%) ÷ 평균 면적(㎢)'),(axs[1],'mean_area_km2','실제 발송 대상 평균 면적','면적(㎢)')]:
 vals=[s['profiles'][a]['overall'][k] for a in arms];bars=ax.bar(names,vals,color=colors,width=.65)
 for b,v in zip(bars,vals):ax.text(b.get_x()+b.get_width()/2,v+.12,f'{v:.2f}',ha='center',fontsize=10)
 ax.set_title(title);ax.set_ylabel(ylabel);ax.set_ylim(0,max(vals)*1.3);ax.tick_params(axis='x',labelsize=9,rotation=15);ax.grid(axis='y',alpha=.18)
ax=axs[2];x=np.arange(3)
for i,a in enumerate(arms):
 vals=[s['profiles'][a]['futures'][f]['hit_pct'] for f in ['habitual','departure','contradictory']];bars=ax.bar(x+(i-1.5)*.21,vals,width=.21,color=colors[i],label=names[i])
 for b,v in zip(bars,vals):ax.text(b.get_x()+b.get_width()/2,v+1.3,f'{v:.1f}',ha='center',fontsize=7)
ax.set_xticks(x,['개인화 준수','중간 이탈','처음부터 반대']);ax.set_ylim(0,121);ax.set_title('준수와 이탈을 나눠 평가');ax.set_ylabel('정답 위치 포함률 (%)');ax.legend(fontsize=7,ncol=2,loc='upper center');ax.grid(axis='y',alpha=.18)
fig.text(.035,.20,'개인화 효과: 통계만75.0% → 개인화 결합96.0%. 준수 차이95% CI는 결과 JSON에 보존.',fontsize=11,weight='bold');fig.text(.035,.13,'반대 행동은30.2%로 여전히 낮음. 본선 대비 차이95% CI -5.77~+7.91%p: 개선 확증 아님.',fontsize=11);fig.text(.035,.065,'같은 합성39명의 새 경로 / 준수·이탈·반대 동일 비중 스트레스 조건 / 실제 발견·수신·인구 빈도 검증 아님',fontsize=10,color='#536b78');fig.savefig(D/'balanced_comparison.png',dpi=180);plt.close(fig)
pid='E09';pred=104729;hour=4;truthseed=2026101231;raw=next(z for z in json.loads((X/f'results_independent_sar/{pid}_{pred}.json').read_text())['snapshots'] if z['hour']==hour);q=next(z['cells'] for z in json.loads((L/f'results/distance_maps/{pid}.json').read_text())['snapshots'] if z['hour']==hour);pre=next(z for z in json.loads((E/f'service_comparison/output/people/{pid}/walk_preliminary_{pred}.json').read_text())['snapshots'] if z['hour']==hour);selections=json.loads((D/'confirmation_selections.json').read_text());maps={a:next(z['cells'] for z in selections if z['person_id']==pid and z['prediction_seed']==pred and z['hour']==hour and z['arm']==a) for a in arms};background=json.loads((R/'결선/PR_설명보충_20261011/최종성능_그림/figure_data.json').read_text())['map_example'];truth=json.loads((O/'truth_private.json').read_text())
def polygon(c):return Polygon([(lng,lat) for lat,lng in h3.cell_to_boundary(c)])
def outline(ax,g):
 if g.is_empty:return
 if g.geom_type=='Polygon':ax.plot(*g.exterior.xy,color='#1a2934',lw=1.3,zorder=3)
 elif hasattr(g,'geoms'):
  for v in g.geoms:outline(ax,v)
fig,axs=plt.subplots(2,4,figsize=(17,12));fig.subplots_adjust(left=.04,right=.98,top=.85,bottom=.13,wspace=.12,hspace=.27);fig.text(.04,.965,'같은 개인의 두 미래: 개인화를 따름 / 개인화와 반대 행동',fontsize=22,weight='bold');fig.text(.04,.91,'고정 E09 · 새 첫 확인 seed2026101231 · 4시간 · prediction seed104729 · 성공/실패 사례를 다시 고르지 않음',fontsize=11);examples=[];paths=[]
for future in ['habitual','contradictory']:
 t=next(z for z in truth if z['person_id']==pid and z['truth_seed']==truthseed and z['future']==future);paths.append([z for z in t['path'] if z['minute']<=hour*60])
g=unary_union([polygon(c) for a in arms for c in maps[a]]);b=g.bounds;coords=[z for path in paths for z in path];x0=min(b[0],min(z['lng'] for z in coords))-.003;x1=max(b[2],max(z['lng'] for z in coords))+.003;y0=min(b[1],min(z['lat'] for z in coords))-.003;y1=max(b[3],max(z['lat'] for z in coords))+.003
for row,(future,path) in enumerate(zip(['habitual','contradictory'],paths)):
 pos=path[-1]
 for i,arm in enumerate(arms):
  ax=axs[row,i];cells=maps[arm];prob=pre['cells'] if arm=='preliminary' else (q if arm=='stat_only_control' else alpha_pool([raw['personal'],raw['statistical'] if arm=='current' else q],[.9,.1] if arm=='current' else [.3,.7]));ps=list(prob) if arm=='preliminary' else cells;values=[prob.get(c,0) for c in ps];maximum=max(values) or 1.;geom=unary_union([polygon(c) for c in cells]);hit=h3.latlng_to_cell(pos['lat'],pos['lng'],7 if arm=='preliminary' else 9) in set(cells);area=next(z['area_km2'] for z in selections if z['person_id']==pid and z['prediction_seed']==pred and z['hour']==hour and z['arm']==arm)
  ax.add_collection(LineCollection(background['roads'],colors='#bbc5ca',linewidths=.3,zorder=1));ax.add_collection(PolyCollection([list(polygon(c).exterior.coords) for c in ps],array=[math.sqrt(v/maximum) for v in values],cmap=['Oranges','Greens','Blues','Greys'][i],clim=(0,1),edgecolors='white',linewidths=.15,zorder=2));outline(ax,geom);ax.plot([z['lng'] for z in path],[z['lat'] for z in path],color='#d93251',lw=2,zorder=4);ax.scatter(pos['lng'],pos['lat'],c='#b521b8',marker='D',s=50,edgecolor='white',zorder=5);ax.scatter(path[0]['lng'],path[0]['lat'],c='#1696d2',s=35,edgecolor='white',zorder=5);ax.set_xlim(x0,x1);ax.set_ylim(y0,y1);ax.set_aspect(1/math.cos(math.radians(pos['lat'])));ax.set_xticks([]);ax.set_yticks([]);ax.set_title(('준수' if row==0 else '반대')+' · '+names[i]+f'\n{area:.2f}㎢ · {"포함" if hit else "미포함"}',fontsize=10);examples.append(dict(person_id=pid,future=future,arm=arm,hour=hour,prediction_seed=pred,truth_seed=truthseed,hit=bool(hit),area_km2=area))
fig.text(.04,.075,'검정: 실제 발송 대상 / 빨강: 정답 경로 / 파랑: 시작 / 자주: 정답 / 색: 확률 √ 상대 스케일. 두 미래·모든 패널 같은 범위.',fontsize=10);fig.text(.04,.035,'한 사례이며 전체 성능을 대표하지 않음 / 같은 면적의 통계만 대조군으로 개인화 효과 확인 / © OpenStreetMap contributors, ODbL',fontsize=10,color='#536b78');fig.savefig(D/'following_and_departing.png',dpi=170);plt.close(fig);(D/'figure_examples.json').write_text(json.dumps(examples,indent=2)+'\n');print(examples)

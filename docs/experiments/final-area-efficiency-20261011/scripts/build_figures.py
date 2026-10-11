from pathlib import Path
import os,sys,json,math
os.environ['MPLCONFIGDIR']='/tmp/cbh-mpl';os.environ['PERSIST_STORAGE']='false'
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.collections import PolyCollection,LineCollection
import numpy as np,h3
from shapely.geometry import Polygon,shape
from shapely.ops import unary_union
from pyproj import Geod
R=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path.cwd();X=R/'결선/실험/CHANNEL_ALERT_repair_20261011';O=X/'results_area_efficiency_final';C=Path(__file__).resolve().parents[4];D=C/'docs/experiments/final-area-efficiency-20261011';sys.path.insert(0,str(C/'backend'))
from app.phase2.combine import alpha_pool
from app.phase3.alerts import select_alert_cells,target_parent_cells
font='/System/Library/Fonts/AppleSDGothicNeo.ttc';font_manager.fontManager.addfont(font);plt.rcParams.update({'font.family':font_manager.FontProperties(fname=font).get_name(),'axes.unicode_minus':False})
d=json.loads((R/'결선/PR_설명보충_20261011/최종성능_그림/figure_data.json').read_text())['map_example'];s=next(s for s in json.loads((X/'results_independent_sar/E09_104729.json').read_text())['snapshots'] if s['hour']==4);mixed=alpha_pool([s['personal'],s['statistical']],[.9,.1]);selected=select_alert_cells(mixed,coverage=.95)
pos=next(s['position'] for s in d['truth']['snapshots'] if s['hour']==4);path=[p for p in d['truth']['path'] if p['minute']<=240];g=Geod(ellps='WGS84')
def boundary(c):return [(lon,lat) for lat,lon in h3.cell_to_boundary(c)]
def area(cells):return sum(abs(g.geometry_area_perimeter(Polygon(boundary(c)))[0])/1e6 for c in cells)
def draw(ax,geom,**kw):
 if geom.geom_type=='Polygon':ax.fill(*geom.exterior.xy,**kw)
 elif hasattr(geom,'geoms'):
  for v in geom.geoms:draw(ax,v,**kw)
def panel(ax,prob,targets,cmap='Greens',district=False,keys=None):
 ax.add_collection(LineCollection(d['roads'],colors='#c3cbd0',linewidths=.3,zorder=1))
 if district:draw(ax,shape(d['district_clipped']),facecolor='#cbd4db',edgecolor='#6f8694',alpha=.7,zorder=0)
 else:
  keys=select_alert_cells(prob,coverage=.95) if keys is None else keys
  ax.add_collection(PolyCollection([boundary(c) for c in keys],array=[prob[c] for c in keys],cmap=cmap,clim=(0,.15),edgecolors='white',linewidths=.25,zorder=2))
  if targets:draw(ax,unary_union([Polygon(boundary(c)) for c in targets]),facecolor='none',edgecolor='#172a35',linewidth=1.8,zorder=3)
 ax.plot([p['lng'] for p in path],[p['lat'] for p in path],color='#d93251',lw=2,zorder=4);ax.scatter(pos['lng'],pos['lat'],marker='D',s=60,c='#a822bd',edgecolor='white',zorder=5);ax.scatter(d['start']['lng'],d['start']['lat'],s=45,c='#1694d2',edgecolor='white',zorder=5)
 b=d['bounds'];ax.set_xlim(b[:2]);ax.set_ylim(b[2:]);ax.set_aspect(1/math.cos(math.radians(pos['lat'])));ax.set_xticks([]);ax.set_yticks([])
fig,axs=plt.subplots(1,4,figsize=(16,6.6));fig.subplots_adjust(left=.03,right=.98,top=.76,bottom=.23,wspace=.07)
fig.text(.03,.94,'같은 사건의 비교: 기존 방식 / 본선 / 결선 res8·9',fontsize=22,weight='bold');fig.text(.03,.87,'KINTEX E09 · seed 104729 · 4시간 · 같은 합성 정답 경로 / 결선 두 그림 모두 개인:통계 90:10, 커버리지 95%',fontsize=11)
examples=[]
for i,ax in enumerate(axs):
 if i==0:
  p=d['panels'][3];panel(ax,{},[],district=True);size=p['area'];hit=p['hit'];title='기존 경보 · 관련 구 근사'
 elif i==1:
  p=d['panels'][4];panel(ax,p['probability_cells'],p['alert_cells'],'Oranges',keys=list(p['probability_cells']));size=p['area'];hit=p['hit'];title='본선 · 당시 발송 정책'
 else:
  res=8 if i==2 else 9;targets=target_parent_cells(selected,res=res);panel(ax,mixed,targets,keys=selected);size=area(targets);hit=h3.latlng_to_cell(pos['lat'],pos['lng'],res) in targets;title=f'결선 · res{res}'+(' (선택)' if res==9 else '')
  examples.append({'res':res,'area_km2':size,'hit':hit,'coverage':.95,'personal_weight':.9,'targets':sorted(targets)})
 ax.set_title(title+f'\n{size:.2f}㎢ · 정답 {"포함" if hit else "미포함"}',fontsize=12,pad=12)
fig.text(.03,.155,'색: 예측 확률 / 검정 경계: 발송 대상 셀 / 빨강: 합성 정답 경로 / 파랑: 시작 / 자주색: 4시간 정답',fontsize=11)
fig.text(.03,.105,'res8·9는 동일한 선택 셀을 지리적으로 덮음. res8은 더 넓은 면적 비용; 경계 밖 꼬리 확률까지 모두 보내는 정책은 아님.',fontsize=11)
fig.text(.03,.055,'지도는 설명용 한 사례. 종합 평가는 31명·744조건. 실제 푸시 수신·발견률 미측정. © OpenStreetMap contributors, ODbL',fontsize=10,color='#576d79')
fig.savefig(D/'same_case_comparison.png',dpi=180);plt.close(fig)
(D/'figure_example.json').write_text(json.dumps({'person':'E09','seed':104729,'hour':4,'channel_tv':s['total_variation'],'selected_mass':sum(mixed[c] for c in selected),'examples':examples},indent=2)+'\n')
summary=json.loads((O/'area_efficiency_summary.json').read_text());native=json.loads((O/'seen31_summary.json').read_text());e=summary['primary_efficiency'];b=summary['common_res9_same_area_budget']['budgets']
fig,axs=plt.subplots(1,3,figsize=(16,6.5));fig.subplots_adjust(left=.06,right=.98,top=.77,bottom=.27,wspace=.29)
fig.text(.04,.94,'면적을 비용으로: 정답을 얼마나 효율적으로 포함하는가',fontsize=22,weight='bold');fig.text(.04,.87,'이전에 본 31명 · 2개 seed × 4개 시점 × 3개 정답 미래 = 744조건 / 개인:통계 90:10 · res9 · 커버리지 95%',fontsize=11)
ax=axs[0];vals=[e[k] for k in ('preliminary','old_final','selected')];bars=ax.bar(['본선','기존 결선','선택 결선'],vals,color=['#d37935','#a86b85','#17846b'],width=.6)
for bar,v in zip(bars,vals):ax.text(bar.get_x()+bar.get_width()/2,v+.18,f'{v:.2f}',ha='center',fontsize=12)
ax.set_ylim(0,max(vals)*1.28);ax.set_ylabel('정답 포함률(%) ÷ 평균 면적(㎢)');ax.set_title('면적당 정답 포함률');ax.grid(axis='y',alpha=.2)
ax=axs[1]
for key,label,color in [('preliminary','본선','#d37935'),('selected','선택 결선','#17846b')]:ax.plot([r['area_km2'] for r in b],[100*r[key+'_inclusion'] for r in b],'o-',label=label,c=color)
ax.set_xlim(0,10.5);ax.set_ylim(0,65);ax.set_xlabel('동일 면적 예산 (㎢)');ax.set_ylabel('정답 포함률 (%)');ax.set_title('같은 res9 격자의 면적 예산 비교');ax.grid(alpha=.2);ax.legend()
ax=axs[2]
for res,color in [(8,'#4480ae'),(9,'#17846b')]:
 rows=[r for r in native['native_grid'] if r['weight']==.9 and r['res']==res];ax.plot([r['area_km2'] for r in rows],[100*r['hit'] for r in rows],'o-',c=color,label=f'90:10 · res{res}')
 for r in rows:ax.annotate(f'{r["coverage"]:.0%}',(r['area_km2'],100*r['hit']),xytext=(3,3),textcoords='offset points',fontsize=8)
p=native['preliminary_native'];ax.scatter(p['area_km2'],100*p['hit'],s=70,c='#d37935',marker='s',label='본선 · 기존 정책');p=native['candidate_native'];ax.scatter(p['area_km2'],100*p['hit'],s=150,c='#26333d',marker='*',label='선택 res9 · 95%');ax.set_xlabel('평균 발송 대상 면적 (㎢)');ax.set_ylabel('정답 포함률 (%)');ax.set_title('res8·9: 면적과 포함률의 교환');ax.grid(alpha=.2);ax.legend(fontsize=8,loc='lower right')
fig.text(.04,.185,f'본선 대비 면적당 포함률 +{e["relative_gain_pct"]:.1f}% (사람 단위 bootstrap 95% CI +{e["relative_gain_ci95"][0]:.1f}~+{e["relative_gain_ci95"][1]:.1f}%).',fontsize=12,weight='bold',color='#157b66')
fig.text(.04,.125,'통과: 전체 효율·포함률 CI / 미통과: 면적 감소 단독 CI·반대 행동(포함률0.81%) / 미수행: 새 독립 검증·실제 수신',fontsize=11,color='#895045')
fig.text(.04,.065,'면적은 비용의 대리값. 95%는 모델 확률의 누적 선택 기준이며 정답 포함률 95%가 아님. 가운데 곡선은 과거 실제 발송량이 아님.',fontsize=10,color='#576d79')
fig.savefig(D/'area_efficiency_comparison.png',dpi=180);plt.close(fig)
print(json.dumps(examples,ensure_ascii=False))

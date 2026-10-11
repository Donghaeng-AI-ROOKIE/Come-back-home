from pathlib import Path
import os,sys,json,math
os.environ['MPLCONFIGDIR']='/tmp/cbh-mpl';os.environ['PERSIST_STORAGE']='false'
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.collections import PolyCollection,LineCollection
import h3,numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union
from pyproj import Geod
O=Path(__file__).resolve().parents[1];R=O.parents[2];X=R/'결선/실험/CHANNEL_ALERT_repair_20261011';C=R/'결선/개발/cbh-independent-alert-core-20261011';sys.path.insert(0,str(C/'backend'))
from app.phase2.combine import alpha_pool
from app.phase3.alerts import select_alert_cells
font='/System/Library/Fonts/AppleSDGothicNeo.ttc';font_manager.fontManager.addfont(font);plt.rcParams.update({'font.family':font_manager.FontProperties(fname=font).get_name(),'axes.unicode_minus':False})
D=O/'results';d=json.loads((R/'결선/PR_설명보충_20261011/최종성능_그림/figure_data.json').read_text())['map_example'];s=next(s for s in json.loads((X/'results_independent_sar/E09_104729.json').read_text())['snapshots'] if s['hour']==4);new=next(s for s in json.loads((D/'distance_maps/E09.json').read_text())['snapshots'] if s['hour']==4)['cells'];pos=next(s['position'] for s in d['truth']['snapshots'] if s['hour']==4);path=[p for p in d['truth']['path'] if p['minute']<=240];g=Geod(ellps='WGS84')
def boundary(c):return [(lon,lat) for lat,lon in h3.cell_to_boundary(c)]
def area(cells):return sum(abs(g.geometry_area_perimeter(Polygon(boundary(c)))[0])/1e6 for c in cells)
def draw(ax,geom,**kw):
 if geom.geom_type=='Polygon':ax.fill(*geom.exterior.xy,**kw)
 elif hasattr(geom,'geoms'):
  for v in geom.geoms:draw(ax,v,**kw)
fig,axs=plt.subplots(1,4,figsize=(18,7));fig.subplots_adjust(left=.035,right=.98,top=.77,bottom=.26,wspace=.09)
fig.text(.035,.95,'개인화가 빗나가는 경우도: 본선 / 현재 / 문헌 통계 / 면적 예산',fontsize=21,weight='bold');fig.text(.035,.89,'KINTEX E09 · seed 104729 · 4시간 · 같은 합성 정답 경로 / 결선 개인화90%·res9 고정 / 현재·문헌안은95%, 마지막 후보는5.28㎢ 상한',fontsize=11)
examples=[]
for i,ax in enumerate(axs):
 if i==0:
  p=d['panels'][4];prob=p['probability_cells'];selected=list(prob);targets=p['alert_cells'];size=p['area'];hit=p['hit'];label='본선 · 당시 발송 정책';cmap='Oranges';mass=None
 else:
  stat=s['statistical'] if i==1 else new;prob=alpha_pool([s['personal'],stat],[.9,1-.9]);selected=select_alert_cells(prob,coverage=.95,max_cells=500) if i<3 else json.loads((D/'area_budget_example.json').read_text())['uniform_dev_current_mean_area_budget']['cells'];targets=selected;size=area(targets);hit=h3.latlng_to_cell(pos['lat'],pos['lng'],9) in targets;label='현재 · SAR 수치 보행10%' if i==1 else ('문헌 통계10% · 95% 선택' if i==2 else '문헌 통계10% · 면적5.28㎢');cmap='Greens' if i==1 else 'Blues';mass=sum(prob[c] for c in selected)
 ax.add_collection(LineCollection(d['roads'],colors='#c3cbd0',linewidths=.3,zorder=1));ax.add_collection(PolyCollection([boundary(c) for c in selected],array=[prob[c] for c in selected],cmap=cmap,clim=(0,.15),edgecolors='white',linewidths=.25,zorder=2));draw(ax,unary_union([Polygon(boundary(c)) for c in targets]),facecolor='none',edgecolor='#172a35',linewidth=1.7,zorder=3)
 ax.plot([p['lng'] for p in path],[p['lat'] for p in path],color='#d93251',lw=2,zorder=4);ax.scatter(pos['lng'],pos['lat'],marker='D',s=60,c='#a822bd',edgecolor='white',zorder=5);ax.scatter(d['start']['lng'],d['start']['lat'],s=45,c='#1694d2',edgecolor='white',zorder=5)
 b=d['bounds'];ax.set_xlim(b[:2]);ax.set_ylim(b[2:]);ax.set_aspect(1/math.cos(math.radians(pos['lat'])));ax.set_xticks([]);ax.set_yticks([]);ax.set_title(label+f'\n{size:.2f}㎢ · 정답 {"포함" if hit else "미포함"}',fontsize=12,pad=12)
 examples.append({'arm':['preliminary','current','distance_only','uniform_dev_area_budget'][i],'person':'E09','seed':104729,'hour':4,'area_km2':size,'hit':bool(hit),'selected_mass':mass})
fig.text(.035,.195,'색: 선택 구역의 예측 확률 / 검정 경계: 발송 대상 / 빨강: 정답 경로 / 파랑: 시작 / 자주색: 4시간 정답',fontsize=11)
fig.text(.035,.13,'문헌안은 개인 목적지·마음 규칙 없이 출발점으로부터 거리만 사용. 표시 범위는 같고 면적 수치는 화면 밖 대상 셀까지 포함.',fontsize=10)
fig.text(.035,.065,'설명용 한 사례. 실제 푸시·발견률 미측정. 문헌의 발견 거리 ≠ 시간별 위치 관측. © OpenStreetMap contributors, ODbL',fontsize=10,color='#576d79')
fig.savefig(D/'same_case_comparison.png',dpi=180);plt.close(fig);(D/'figure_example.json').write_text(json.dumps(examples,indent=2)+'\n')
su=json.loads((D/'summary.json').read_text());a=su['seen31']['current'];b=su['seen31']['distance_only'];labels=['현재 통계 보행10%','문헌 거리분포10%'];colors=['#17846b','#397fb4']
fig,axs=plt.subplots(1,3,figsize=(14,6.5));fig.subplots_adjust(left=.065,right=.98,top=.76,bottom=.25,wspace=.35)
fig.text(.04,.94,'문헌 10%: 포함률은 개선, 면적당 효율은 하락',fontsize=22,weight='bold');fig.text(.04,.87,'이전에 본 합성 31명 · 744조건 · 개인화90% / 통계10% · res9 · 누적 선택95% · 500셀 상한',fontsize=11)
for ax,key,title,ylabel in [(axs[0],'efficiency_pp_per_km2','면적당 적중률','정답 포함률(%) ÷ 평균 면적(㎢)'),(axs[1],'mean_area_km2','평균 발송 대상 면적','면적(㎢)')]:
 vals=[a[key],b[key]];bars=ax.bar(labels,vals,color=colors,width=.6)
 for bar,v in zip(bars,vals):ax.text(bar.get_x()+bar.get_width()/2,v+.1,f'{v:.2f}',ha='center',fontsize=12)
 ax.set_ylim(0,max(vals)*1.3);ax.set_title(title);ax.set_ylabel(ylabel);ax.grid(axis='y',alpha=.2)
ax=axs[2];x=np.arange(3)
for offset,key,label,color in [(-.19,'current','현재','#17846b'),(.19,'distance_only','문헌10%','#397fb4')]:
 vals=[su['future_slices'][f][key]['hit_pct'] for f in ['habitual','departure','contradictory']];bars=ax.bar(x+offset,vals,width=.38,label=label,color=color)
 for bar,v in zip(bars,vals):ax.text(bar.get_x()+bar.get_width()/2,v+1.3,f'{v:.2f}',ha='center',fontsize=9)
ax.set_xticks(x,['습관 행동','이탈 행동','반대 행동']);ax.set_ylim(0,112);ax.set_ylabel('정답 포함률 (%)');ax.set_title('세 가지 정답 미래');ax.legend();ax.grid(axis='y',alpha=.2)
delta=su['seen31']['candidate_minus_current']['relative_efficiency_gain_pct'];fig.text(.04,.18,f'포함률 {a["hit_pct"]:.2f}% → {b["hit_pct"]:.2f}% / 면적당 효율 {delta["point"]:.2f}% (사람 단위 95% CI {delta["ci95"][0]:.2f}~{delta["ci95"][1]:.2f}%).',fontsize=12,weight='bold')
fig.text(.04,.115,'통과: 전체 포함률 비열등·10㎢ AUC 개선 / 미통과: 면적당 효율 개선·면적 감소 / 반대 행동 4.44%로 여전히 낮음.',fontsize=11,color='#895045')
fig.text(.04,.06,'면적은 비용 대리값. 새 독립 검증·실제 수신 미수행. 문헌 거리분포로 제품 기본값을 교체하지 않음.',fontsize=10,color='#576d79')
fig.savefig(D/'area_efficiency_comparison.png',dpi=180);plt.close(fig);print(json.dumps(examples))

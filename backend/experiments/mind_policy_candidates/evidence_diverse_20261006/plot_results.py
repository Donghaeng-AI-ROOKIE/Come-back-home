"""Publication-style static artifacts from local recorded results only."""
import json,math,xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
import h3
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager,colors
from matplotlib.collections import LineCollection
D=Path(__file__).resolve().parent
font_manager.fontManager.addfont('/System/Library/Fonts/AppleSDGothicNeo.ttc')
plt.rcParams.update({'font.family':'Apple SD Gothic Neo','axes.unicode_minus':False})
r=json.loads((D/'replayed_results.json').read_text())
families=[('environment','환경 조건'),('physical_rest','보행 한계·휴식'),('waiting','대기와 해제'),('destination','목적지·출발'),('external_state','비·어둠 등'),('source_fidelity','정정·부정·타인'),('time_context','시각·지속시간'),('multiple_behaviors','복합 반응')]
if r['complete']:
 fig,ax=plt.subplots(figsize=(12,7));y=np.arange(len(families));width=.34
 for arm,offset,color,label in [('on',-width/2,'#21618C','Thinking 켬'),('off',width/2,'#A0A0A0','Thinking 끔')]:
  values=[r['arms'][arm]['families'][f]['passed'] for f,_ in families]
  ax.barh(y+offset,values,height=width,color=color,label=label)
  for yy,v in zip(y+offset,values):ax.text(v+.35,yy,f'{v}/32',va='center',fontsize=10)
 ax.axvline(26,color='#555555',ls='--',lw=1,label='행동군별 진행 기준 26/32')
 ax.set_yticks(y,[label for _,label in families]);ax.invert_yaxis();ax.set_xlim(0,36)
 ax.set_xticks([0,8,16,24,32]);ax.set_xlabel('합성 장면에서 기대 행동과 일치한 판정 수')
 ax.set_title('새 합성 32명으로 확대한 마음모델 비교',fontsize=20,pad=22)
 ax.spines[['top','right']].set_visible(False);ax.legend(loc='lower right',frameon=False)
 fig.subplots_adjust(left=.16,right=.96,top=.86,bottom=.23)
 fig.text(.5,.08,'8행동군 × 4명 × 4장면 × 2응답 · 설정별 256판정\n실패 출력 포함 | 독립 환자 512명·실제 동선 정확도·전문가 평가가 아님',ha='center',fontsize=11)
 fig.savefig(D/'행동군별_확대비교.png',dpi=150);plt.close(fig)
sites=json.loads((D/'sites.json').read_text())
spatial=[json.loads(p.read_text()) for p in (D/'spatial').glob('P29_*.json')]
spatial=[x for x in spatial if x.get('status')=='executed' and x['rep']==1]
if not spatial:raise SystemExit('P29 first-response spatial results not available yet')
points={};segments=[];keys={};ns='{http://graphml.graphdrawing.org/xmlns}'
for event,e in ET.iterparse(sites['source_map'],events=('end',)):
 if e.tag==ns+'key':keys[e.attrib['id']]=e.attrib.get('attr.name');e.clear()
 elif e.tag==ns+'node':
  attrs={keys.get(d.attrib['key']):d.text for d in e if d.tag==ns+'data'}
  points[e.attrib['id']]=(float(attrs['x']),float(attrs['y']));e.clear()
 elif e.tag==ns+'edge':
  a,b=points.get(e.attrib['source']),points.get(e.attrib['target'])
  if a and b:segments.append((a,b))
  e.clear()
arr=np.array(segments)
for arm in ('on','off'):
 fig,axes=plt.subplots(6,4,figsize=(14,19),sharex=False,sharey=False)
 fig.subplots_adjust(left=.065,right=.905,top=.905,bottom=.11,hspace=.43,wspace=.24)
 norm=colors.PowerNorm(gamma=.4,vmin=0,vmax=1);scatter=None
 for i,site in enumerate(sites['sites']):
  x,y=site['location']['lng'],site['location']['lat'];scale=np.array([111*math.cos(math.radians(y)),111])
  transform=lambda pts:(np.array(pts)-np.array([x,y]))*scale
  all_rows=[z for z in spatial if z['site_id']==site['site_id']]
  pts=[(p['lng'],p['lat']) for z in all_rows for s in z['snapshots'] for p in s['endpoints']]
  extent=max(.4,float(np.max(np.abs(transform(pts))))*1.08) if pts else 1.5
  local=transform(arr);mask=(np.min(local[:,:,0],axis=1)<extent)&(np.max(local[:,:,0],axis=1)>-extent)&(np.min(local[:,:,1],axis=1)<extent)&(np.max(local[:,:,1],axis=1)>-extent)
  for j,minute in enumerate((60,120,240,360)):
   ax=axes[i,j];rows=[z for z in all_rows if z['arm']==arm]
   ax.add_collection(LineCollection(local[mask],colors='#E1E4E7',linewidths=.45,zorder=1))
   if len(rows)==2:
    cells={}
    for z in rows:
     snap=next(s for s in z['snapshots'] if s['minute']==minute)
     for cell,p in snap['cells'].items():cells[cell]=cells.get(cell,0)+p/2
    ids=list(cells);xy=transform([(h3.cell_to_latlng(c)[1],h3.cell_to_latlng(c)[0]) for c in ids])
    if ids:scatter=ax.scatter(xy[:,0],xy[:,1],c=[cells[c] for c in ids],s=[10+130*math.sqrt(cells[c]) for c in ids],cmap='Blues',norm=norm,zorder=2,linewidths=0)
    ax.set_title(f"{site['label']} · {minute//60}시간",fontsize=11)
   else:ax.text(.5,.5,'첫 응답 실행 결과 없음',ha='center',transform=ax.transAxes,fontsize=10);ax.set_title(site['label']+f' · {minute//60}시간',fontsize=11)
   ax.scatter([0],[0],c='black',s=20,marker='x',linewidths=.8,zorder=3)
   ax.set_xlim(-extent,extent);ax.set_ylim(-extent,extent);ax.set_aspect('equal');ax.tick_params(labelsize=7)
   if i==5:ax.set_xlabel('출발점 기준 동서 거리(km)',fontsize=9)
   if j==0:ax.set_ylabel('남북 거리(km)',fontsize=9)
 if scatter is not None:
  cax=fig.add_axes([.93,.28,.012,.45]);cb=fig.colorbar(scatter,cax=cax);cb.set_label('모의 셀 확률 · 두 보행 시드 평균',fontsize=10)
 fig.suptitle('KINTEX 6개 구역에서 시간에 따른 위치 분포\nP29 첫 응답 · Thinking '+('켬' if arm=='on' else '끔'),fontsize=20,y=.972)
 fig.text(.5,.936,'보호자 원문: 길 잃음 인지·가족 부재 → 대기 / 6분 또는 280m 보행 → 휴식',ha='center',fontsize=12)
 fig.text(.5,.035,'가족이 90분에 도착하는 합성 관측 · 구역별 100보행자 × 시드 2개\n실제 KINTEX 도로 + 합성 시설·상황 · 일반 초기 이동 prior · 실제 환자 경로와 비교하지 않음\n색·크기 척도 동일, 행별 공간 범위 다름 | © OpenStreetMap contributors, ODbL',ha='center',fontsize=10)
 fig.savefig(D/f'KINTEX_시간별_P29_Thinking_{arm}.png',dpi=145);plt.close(fig)
print('Local figures saved; no network calls.')

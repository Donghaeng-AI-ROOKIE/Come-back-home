"""Render saved experimental evidence; no network or model/simulation calls."""
import json
import os
import math
import tempfile
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir())/'kexaone-review-mpl'))
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt, font_manager
from matplotlib.collections import LineCollection
from matplotlib.patches import Circle

ROOT=Path(__file__).resolve().parent
def read(p): return json.loads((ROOT/p).read_text())
font=os.environ.get('FIGURE_FONT_PATH')
if font:
    font_manager.fontManager.addfont(font)
    name=font_manager.FontProperties(fname=font).get_name()
else:
    available={f.name for f in font_manager.fontManager.ttflist}
    name=next((s for s in ['AppleGothic','NanumGothic','Noto Sans CJK KR','Arial Unicode MS'] if s in available),None)
    if not name: raise RuntimeError('Set FIGURE_FONT_PATH to a Korean font.')
plt.rcParams.update({'font.family':name,'font.size':12,'axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False})
TEAL='#147d83'; GRAY='#b4bbc1'; INK='#202b33'
def save(fig,name):
    fig.savefig(ROOT/'assets'/name,dpi=165,facecolor='white')
    plt.close(fig)

def walking():
    rows=[r for r in read('evidence/06_refinement/matched_comparison.json')['rows'] if r['family']=='F05']
    fig,ax=plt.subplots(figsize=(11,5.8)); fig.subplots_adjust(bottom=.27,top=.8)
    fig.suptitle('머무름 관찰을 바꾸면 보행도 달라지는가',fontsize=20,y=.96,weight='bold')
    fig.text(.5,.865,'SAR→K 결합 실험 · 동일 생성 반복과 보행 시드로 맞춘 비교',ha='center',color=INK)
    for i,r in enumerate(rows):
        a=r['variants']['A']['endpoint_within_200m']*100;b=r['variants']['B']['endpoint_within_200m']*100
        ax.bar(i-.18,a,.34,color=TEAL,label='근처에 머무름 관찰' if i==0 else None)
        ax.bar(i+.18,b,.34,color=GRAY,label='계속 걷기 관찰' if i==0 else None)
        for x,y in [(i-.18,a),(i+.18,b)]:ax.text(x,y+.5,f'{y:.2f}%',ha='center',fontsize=11)
        ax.text(i,31,f'차이 {a-b:.2f}%p',ha='center',weight='bold')
    ax.set_xticks(range(3),['기존 SAR + RAG','K + RAG','SAR → K + RAG']);ax.set_ylim(0,34)
    ax.set_ylabel('출발지 200m 이내 종료 비율 (%)');ax.legend(loc='upper left',bbox_to_anchor=(0,-.14),ncol=2,frameon=False)
    fig.text(.07,.045,'F05 · 두 번째 생성 × 시드 41/73/109 · 실행당 500명\nSAR는 저장 결과 재사용. 실제 휴식 확률·예측 정확도 아님. 차이의 크기에 정답은 없음.',fontsize=11)
    save(fig,'matched-walking.png')

def paths():
    d=read('assets/path_evidence.json');start=d['panels'][0]['paths'][0]['start']
    def xy(p):return ((p[1]-start[1])*111320*math.cos(math.radians(start[0])),(p[0]-start[0])*111320)
    coords={k:[xy(p) for p in v] for k,v in d['segments'].items()}
    points=[p for line in coords.values() for p in line]
    xbounds=(min(p[0] for p in points)-150,max(p[0] for p in points)+150)
    ybounds=(min(p[1] for p in points)-150,max(p[1] for p in points)+150)
    fig,axes=plt.subplots(2,2,figsize=(14,9));fig.subplots_adjust(top=.84,bottom=.18,hspace=.52,wspace=.24)
    fig.suptitle('실제로 저장된 OSMnx 진단 경로',fontsize=21,weight='bold',y=.97)
    fig.text(.5,.918,'동일 사례 F05 · 두 번째 생성 · 시드 41 · 1시간 · 마음 재해석 OFF',ha='center')
    for ax,p in zip(axes.flat,d['panels']):
        ax.add_collection(LineCollection(list(coords.values()),colors='#e1e5e7',linewidths=.6,zorder=0))
        for w in p['paths']:
            ax.add_collection(LineCollection([coords[k] for k in w['segments']],colors=TEAL,linewidths=.85,alpha=.35))
        ax.add_patch(Circle((0,0),200,fill=False,ls='--',ec=INK,lw=.9));ax.scatter([0],[0],s=35,c=INK,zorder=3)
        cond='K + RAG' if p['condition']=='K_DIRECT' else 'SAR → K + RAG'
        label='근처에 머무름' if p['variant']=='A' else '계속 걷기'
        ax.set_title(f'{cond} | {label}\n200m 이내 종료: {100*p["metrics"]["endpoint_within_200m"]:.1f}% (전체 500명)',fontsize=12)
        ax.set(xlim=xbounds,ylim=ybounds,aspect='equal',xlabel='출발지 기준 동서 거리 (m)',ylabel='남북 거리 (m)')
    fig.text(.065,.038,'각 실행의 저장 순서 첫 40명 표시 · 배경은 네 패널에서 사용한 도로 간선의 합집합\n실제 도로망·합성 사람/후보 장소. 오류가 포함된 진단 출력도 표시하며 도입 성공의 증거는 아님.\n동일 축척. 선은 OSM 간선 형상을 연결. © OpenStreetMap contributors (ODbL)',fontsize=10)
    save(fig,'osm-paths.png')

def contracts():
    raw=read('evidence/09_observation/saved_outputs.json'); post=read('evidence/09_observation/shape_diagnostic.json')
    fig,axes=plt.subplots(1,2,figsize=(12,5.7));fig.subplots_adjust(top=.75,bottom=.26,wspace=.28)
    fig.suptitle('답변을 읽을 수 있어도 필요한 규칙을 모두 지킨 것은 아니다',fontsize=19,weight='bold',y=.96)
    fig.text(.5,.875,'관찰 정리 실험 · 조건당 답변 16개 · 형식을 나중에 고쳐 읽은 결과는 별도 표시',ha='center',fontsize=11)
    for ax,arm,label in zip(axes,['NO_RAG','WITH_RAG'],['보호자 원문만','보호자 원문 + RAG']):
        items=[o for o in raw if o['arm']==arm];dec=0
        for o in items:
            try:json.loads(o['raw_content']);dec+=1
            except json.JSONDecodeError:pass
        vals=[dec,sum(o['checks']['valid'] for o in items),sum(post[o['id']]['valid'] for o in items)]
        ax.bar(range(3),vals,color=[GRAY,INK,TEAL],width=.6)
        for i,n in enumerate(vals):ax.text(i,n+.35,f'{n}/16',ha='center',weight='bold')
        ax.set_xticks(range(3),['JSON 해석\n가능','처음부터 모든\n출력 규칙 준수','항목 위치 보정 후\n출력 규칙 준수'])
        ax.set_ylim(0,17);ax.set_yticks([0,4,8,12,16]);ax.set_title(label,pad=14);ax.set_ylabel('응답 수')
    fig.text(.065,.065,'실험 후 항목 위치만 바로잡아 다시 검사. 빠진 내용을 만들거나 항목 이름을 추측해 고치지 않음.\n필수 항목·배치·출처 규칙의 검사이며, 내용이 정확하다는 뜻은 아님. 관찰 누락·잘못된 분류도 남음.',fontsize=11)
    save(fig,'output-contract.png')

def quotations():
    q=read('example_quotes.json')
    fig=plt.figure(figsize=(12,7.7));fig.patch.set_facecolor('white')
    fig.text(.06,.92,'같은 사람의 원문을 읽고도 달라진 해석',fontsize=22,weight='bold')
    fig.text(.06,.855,'사례별 SAR 참조 실험 · T02 · 아래 세 문장은 실제 저장 출력의 발췌',fontsize=12,color=INK)
    # Manual wrapping only; underlying exact quotes remain in example_quotes.json.
    labels=['SAR의 참고 해석','A · 원문 + RAG → K','B · 원문 + RAG + SAR → K']
    wraps=[
      '최근 길을 잃었을 때 멈추지 않고 계속 직진하는 모습이\n관찰되었기 때문이다.',
      '개인이 길을 잃었을 때의 방향 전환 여부나 경로 선택 방식은\n관찰되지 않아, 경로 형태에 대한 직접적 정보는 부족하다.',
      '개인은 길을 잃었을 때 멈추지 않고 직진하는 행동을 보였으나,\n방향 전환 여부나 익숙한 경로 사용 여부는 관찰되지 않았다.'
    ]
    for i,(label,text) in enumerate(zip(labels,wraps)):
        assert text.replace('\n',' ') == q[i]['quote']
        y=.72-i*.2
        fig.text(.06,y,label,fontsize=13,weight='bold',color=TEAL)
        fig.text(.06,y-.09,text,fontsize=15,linespacing=1.6)
    fig.text(.06,.075,'입력에는 계속 걷기가 있지만 방향 전환·익숙한 경로 이용은 미관찰.\nB는 SAR의 근거 없는 직진 설명을 반복했다. 한 사례의 진단이며 전체 우열 지표가 아님.',fontsize=11,color=INK)
    save(fig,'actual-interpretation.png')

if __name__=='__main__':
    walking();paths();contracts();quotations()
    print('Rendered four figures from saved evidence.')

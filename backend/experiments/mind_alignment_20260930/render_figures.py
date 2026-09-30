"""Render the archived metrics only. Requires matplotlib and a Korean font."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

D=Path(__file__).resolve().parent
font=Path('/System/Library/Fonts/AppleSDGothicNeo.ttc')
if font.exists():
    font_manager.fontManager.addfont(str(font))
    plt.rcParams['font.family']=font_manager.FontProperties(fname=str(font)).get_name()
else:
    plt.rcParams['font.family']=['Noto Sans CJK KR','NanumGothic','sans-serif']
plt.rcParams.update({'font.size':13,'axes.unicode_minus':False,'figure.facecolor':'white'})
assets=D/'assets';assets.mkdir(exist_ok=True)
E=D/'evidence';S=E/'MIND_state_alignment_20260930';R=E/'MIND_release_gate_20260930'
read=lambda p:json.loads(p.read_text())
p2=read(S/'contrast_pilot2/comparison.json')['results']
p3=read(S/'contrast_pilot3/comparison.json')['results']
p4=read(S/'contrast_pilot4/comparison.json')['results']
values=[p2['observation_v2']['command_correct'],p2['concise_person_scene']['command_correct'],p3['explicit_knowledge_state']['command_correct'],p4['separate_motion_and_goal']['command_correct']]
fig,ax=plt.subplots(figsize=(12,4.9))
fig.subplots_adjust(left=.23,right=.93,top=.73,bottom=.17)
labels=['현재 관측 정리','프롬프트 간결화','참·거짓·미확인 명시','현재 동작과 목표 기억 분리']
ax.barh(range(4),values,color=['#b9bec4']*3+['#256b9e'],height=.56)
ax.invert_yaxis();ax.set_yticks(range(4),labels);ax.set_xlim(0,44);ax.set_xticks([0,10,20,30,40]);ax.set_xlabel('기대한 명령과 일치한 상황 수 / 같은 개발 40개')
for i,v in enumerate(values):ax.text(v+.6,i,f'{v}/40',va='center',weight='bold')
for sp in ax.spines.values():sp.set_visible(False)
ax.tick_params(axis='y',length=0);ax.grid(axis='x',alpha=.13);ax.set_axisbelow(True)
fig.text(.06,.93,'개인 조건을 행동으로 연결하기 위한 후보 비교',fontsize=21,weight='bold')
fig.text(.06,.845,'최신 후보: 명령 37/40 · 설명과 근거까지 일치 30/40',fontsize=15,color='#256b9e')
fig.text(.06,.045,'개발 자료를 반복 사용한 비교 · 후보별 상황당 1회 · 실제 환자 정확도나 독립 일반화 성능이 아님',fontsize=11,color='#535961')
fig.savefig(assets/'development-comparison.png',dpi=160)
plt.close(fig)
v=read(R/'summary.json')['batches']
fig,axes=plt.subplots(1,3,figsize=(13,4.8))
fig.subplots_adjust(left=.045,right=.98,top=.68,bottom=.21,wspace=.38)
nums=[v['canary']['command_match'],v['natural']['command_match'],v['frontend']['command_match']]
den=[80,80,16];titles=['개인 특성 대비','자연어 스트레스','온보딩 해석 → 마음모델']
for ax,a,b,title in zip(axes,nums,den,titles):
    ax.barh([0],[b],color='#e8ebee',height=.45)
    ax.barh([0],[a],color='#256b9e',height=.45)
    ax.set_xlim(0,b);ax.set_ylim(-.65,.65);ax.axis('off')
    ax.set_title(title,loc='left',fontsize=15,pad=12)
    ax.text(0,-.46,f'{a}/{b}',fontsize=27,weight='bold')
    ax.text(b,-.46,f'{a/b:.1%}',ha='right',fontsize=16,color='#535961')
fig.text(.045,.925,'별도 평가 176회: 명령 일치와 의미 검토를 구분',fontsize=21,weight='bold')
fig.text(.045,.825,'저장된 온보딩 해석을 받은 16개 응답: 설명·근거 9통과 / 6오류 / 1문구 검토',fontsize=13)
fig.text(.045,.10,'합성 사례의 기대 명령 기준 · 설명 평가는 Codex 비맹검 검토 · 운영 모델 교체는 미수행',fontsize=12,color='#535961')
fig.text(.045,.045,'KINTEX 명령 전달 16/16은 별도 실행 검사이며, 위 명령 선택의 정확도에 합산하지 않음',fontsize=11,color='#535961')
fig.savefig(assets/'release-check.png',dpi=160)
plt.close(fig)
print('Rendered two figures from archived JSON metrics.')

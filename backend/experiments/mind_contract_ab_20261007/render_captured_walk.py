"""Matplotlib charts from frozen exported data; no simulation or external calls."""
import argparse,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import PowerNorm
from matplotlib.lines import Line2D


def main():
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);a=p.parse_args()
    data=json.loads(a.data.read_text()); out=a.data.parent
    plt.rcParams.update({'font.family':'AppleGothic','axes.unicode_minus':False,'font.size':11})
    scenes={'rest_cycle':'보행·휴식 반복','wait_release':'길 잃음·가족 귀환','place_noise':'한 장소의 소음 회피'}
    allpoints=[v for scene in scenes for t in data['plots'][scene]['d12_rep1']['timeline'] for v in t['points']]
    xmin=min(x['lng'] for x in allpoints)-.002;xmax=max(x['lng'] for x in allpoints)+.002
    ymin=min(x['lat'] for x in allpoints)-.002;ymax=max(x['lat'] for x in allpoints)+.002
    norm=PowerNorm(.5,vmin=0,vmax=max(x['p'] for x in allpoints))
    fig,axs=plt.subplots(3,4,figsize=(16,12),layout='constrained')
    for r,(scene,label) in enumerate(scenes.items()):
        for c,t in enumerate(data['plots'][scene]['d12_rep1']['timeline']):
            ax=axs[r,c];ax.add_collection(LineCollection(data['roads'],colors='#dfe3e7',linewidths=.25,rasterized=True))
            pts=t['points'];sc=ax.scatter([x['lng'] for x in pts],[x['lat'] for x in pts],c=[x['p'] for x in pts],
                s=20,cmap='Blues',norm=norm,linewidths=0,rasterized=True)
            ax.set(xlim=(xmin,xmax),ylim=(ymin,ymax),aspect=1.26)
            ax.tick_params(labelsize=8);ax.set_title(f"{label} · {t['minute']//60}시간\n누적 평균 {t['metrics']['mean_path_km']:.2f}km",fontsize=11)
            if c==0: ax.set_ylabel('위도')
            if r==2: ax.set_xlabel('경도')
    cb=fig.colorbar(sc,ax=axs,shrink=.65,pad=.02);cb.set_label('500명 중 셀에 있는 비율 · 제곱근 색눈금')
    fig.suptitle('같은 500명의 상태를 이어 계산한 시간별 위치 분포',fontsize=20)
    fig.supxlabel('가상 보호자 1명 · D12 첫 응답 · 실제 KINTEX 도로 + 합성 시설·관측\n초기 수치 기준선은 프로파일 기본값 · 실제 실종 동선 정확도 아님 · © OpenStreetMap contributors, ODbL',fontsize=10)
    fig.savefig(out/'시간별_보행지도.png',dpi=150);plt.close(fig)
    fig,axs=plt.subplots(2,3,figsize=(15,8),layout='constrained')
    for i,(scene,label) in enumerate(scenes.items()):
        d=data['plots'][scene]['d12_rep1']['trace0'];base=data['plots'][scene]['empty_policy']['trace0']
        ax=axs[0,i]
        ax.plot([0]+[v['minute'] for v in base],[0]+[v['distance_m']/1000 for v in base],color='#999',label='개인 행동 규칙 없음')
        ax.plot([0]+[v['minute'] for v in d],[0]+[v['distance_m']/1000 for v in d],color='#15558f',label='개인 행동 규칙 반영')
        ax.set(title=label,ylabel='누적 이동거리 (km)',xlim=(0,360),ylim=(0,18));ax.grid(alpha=.18);ax.legend(fontsize=10)
        ax=axs[1,i];colors={'walk':'#15558f','seek':'#15558f','avoid':'#15558f','rest':'#aaa','wait':'#222'}
        prior=0
        for v in d:
            ax.broken_barh([(prior,v['minute']-prior)],(0,1),facecolors=colors[v['mode']]);prior=v['minute']
        ax.set(xlim=(0,360),ylim=(-.15,1.3),xlabel='경과 시간 (분)',yticks=[])
        if scene=='wait_release':
            for x,txt in [(40,'인지·부재'),(90,'가족 귀환'),(210,'인지·부재'),(230,'가족 귀환')]:
                ax.axvline(x,color='#555',ls=':',lw=.8);ax.text(x,1.12,txt,rotation=35,fontsize=9)
        if scene=='place_noise':
            for x,y in [(0,20),(80,130)]:ax.plot([x,y],[1.15,1.15],lw=4,color='#15558f')
            ax.text(150,1.1,'위 파란 선: 소음 관측 시간',fontsize=9)
        ax.set_title('고정 보행자 0번의 행동',fontsize=12)
    axs[1,0].legend(handles=[Line2D([0],[0],color=c,lw=8,label=l) for l,c in
        [('보행·회피','#15558f'),('휴식','#aaa'),('대기','#222')]],loc='upper center',ncol=3,fontsize=10)
    fig.suptitle('규칙이 실제 보행·휴식·대기 시간으로 이어지는지 확인',fontsize=19)
    fig.supxlabel('선택 기준: 미리 저장한 0번 보행자 · 가상 사례와 합성 관측 · 전체 500명의 정확도를 뜻하지 않음',fontsize=10)
    fig.savefig(out/'개인조건_행동연결.png',dpi=160);plt.close(fig)


if __name__=='__main__':main()

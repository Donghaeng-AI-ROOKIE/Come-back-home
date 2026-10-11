"""Frozen independent synthetic trajectories; authored assumptions, not clinical labels.

Copied from EFFICIENCY_KINTEX_v1_20261009/build_dataset.py for the main (ad9597f)
final verification. Only the index range, IDs and split sizes change: new people
F01-F36 (indices 40-75, so every RNG seed differs from E01-E40), 4 development
+ 32 evaluation. Templates and families are unchanged (disclosed limitation).
"""
OFFSET,N,DEV=40,36,4
from pathlib import Path
import argparse, hashlib, json, math, random
import networkx as nx
import numpy as np
import osmnx as ox
from scipy.spatial import cKDTree
from app.phase0.slots import SLOTS
R=Path(__file__).resolve().parent
QUESTIONS={s.key:s.question for s in SLOTS}
def save(name,value):(R/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n")
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--map",required=True);args=ap.parse_args()
    path=Path(args.map);sha=hashlib.sha256(path.read_bytes()).hexdigest()
    assert sha=="953d2bca91fe7388011e9ca161dc576c3c79366c578ed314d7cc8deea677db92"
    g=ox.load_graphml(path);component=max(nx.strongly_connected_components(g),key=len)
    nodes=sorted(component);xy=np.array([[g.nodes[n]['x'],g.nodes[n]['y']] for n in nodes])
    scale=np.array([88000.,111000.]);tree=cKDTree(xy*scale)
    def nearest(lng,lat):return nodes[int(tree.query(np.array([lng,lat])*scale)[1])]
    def point(n):return dict(lat=g.nodes[n]['y'],lng=g.nodes[n]['x'])
    def road(a,b):
        ns=nx.shortest_path(g,a,b,weight="length");segments=[]
        for u,v in zip(ns,ns[1:]):
            edge=min(g[u][v].values(),key=lambda z:float(z["length"]));geom=edge.get("geometry")
            coords=list(geom.coords) if geom is not None else [(g.nodes[u]['x'],g.nodes[u]['y']),(g.nodes[v]['x'],g.nodes[v]['y'])]
            if math.dist(coords[-1],(g.nodes[u]['x'],g.nodes[u]['y']))<math.dist(coords[0],(g.nodes[u]['x'],g.nodes[u]['y'])):coords.reverse()
            lengths=[math.dist(np.array(x)*scale,np.array(y)*scale) for x,y in zip(coords,coords[1:])]
            total=sum(lengths)
            for (x,y),length in zip(zip(coords,coords[1:]),lengths):
                if length>0:segments.append((x,y,float(edge["length"])*length/total))
        assert segments
        return segments
    def at_distance(segments,d):
        for a,b,length in segments:
            if d<=length:return {"lat":a[1]+(b[1]-a[1])*max(0,d)/length,"lng":a[0]+(b[0]-a[0])*max(0,d)/length}
            d-=length
        b=segments[-1][1];return dict(lat=b[1],lng=b[0])
    def offset(center,d,angle,exclude=()):
        target=np.array([center[0]+math.cos(angle)*d/88000,center[1]+math.sin(angle)*d/111000])*scale
        for ix in np.atleast_1d(tree.query(target,k=32)[1]):
            if nodes[int(ix)] not in exclude:return nodes[int(ix)]
        raise ValueError('no distinct node')
    inputs=[];truth=[];manifest=[]
    for i in range(OFFSET,OFFSET+N):
        rng=random.Random(871000+i);pid=f"F{i-OFFSET+1:02d}";family=["goal","rest","wait","avoid"][i%4]
        split="development" if i-OFFSET<DEV else "evaluation";angle=rng.uniform(0,2*math.pi)
        start=offset((126.7483258,37.6652142),rng.uniform(100,950),angle)
        center=(g.nodes[start]["x"],g.nodes[start]["y"]);distance=rng.uniform(450,2400)
        goal=offset(center,distance,angle+rng.uniform(-.6,.6),[start])
        unrelated=offset(center,rng.uniform(2500,5200),angle+math.pi+rng.uniform(-.7,.7),[start,goal])
        home=offset(center,rng.uniform(200,600),angle+math.pi/2,[start,goal,unrelated])
        quiet=offset(center,distance+350,angle+.6,[start,goal,unrelated,home])
        assert len({start,goal,unrelated,home,quiet})==5
        goal_label=f"가상 {pid} {'공원' if i%2==0 else '시장'}";quiet_label=f"가상 {pid} 쉼터"
        speed=rng.choice([28,35,42,49]);bout=rng.choice([15,20,25,30]);rest=rng.choice([5,10,15])
        wait=rng.choice([10,20,30,40]);hour=rng.choice([8,10,14,16])
        goals=[
          f"매일 {goal_label}에 가십니다. 혼자 나가도 그곳으로 가는 모습을 여러 번 봤어요. 가는 길은 익숙해요.",
          f"평소 목적지는 {goal_label}이에요. 그 길은 스스로 찾아가시고, 거기서 한동안 머무르세요.",
          f"{goal_label} 쪽을 반복해서 찾으세요. 늘 다니는 길은 알아보시지만 처음 온 골목은 어려워하세요.",
          f"산책하러 나가면 보통 {goal_label}까지 가요. 그곳에 가야 한다고 평소 자주 말씀하세요."]
        answers={"routine_destinations":goals[(i//4)%4],
          "mobility_transport_capacity":f"평지에서 보통 {bout}분 정도 걸으세요. 그 다음에는 {rest}분 쉬면 다시 걸을 수 있어요.",
          "lost_behavior":"길을 잃었을 때 어떻게 하실지는 잘 모르겠어요."}
        if family=="rest":answers["mobility_transport_capacity"]=f"걸은 시간이 {bout}분쯤 되면 다리가 아프다고 멈춰 {rest}분 쉬세요. 쉬고 나서는 다시 목적지로 걸으세요. 매번 그런 편이에요."
        elif family=="wait":answers["lost_behavior"]=f"길을 잃었다는 걸 알아차리면 그 자리에 멈춰 {wait}분 기다려요. 그래도 가족이 없으면 다시 {goal_label} 쪽으로 걸으세요. 가족을 만나서 귀가한 뒤는 실종이 끝난 경우예요."
        elif family=="avoid":answers["hazard_awareness_vulnerability"]=f"{goal_label}이 시끄러울 때만 그곳을 피해서 {quiet_label} 쪽으로 가요. 조용하면 {goal_label}에 들어가세요. 모든 공원이나 시장을 피하는 것은 아니에요."
        if i%5==0:answers["autobiographical_destination_pull"]="예전 직장 이야기는 하시지만 요즘 찾아가겠다고 하신 적이나 실제 간 적은 없어요."
        if i%7==0:answers["communication_approach_vulnerability"]="낯선 사람에게 먼저 말을 거는지는 제가 본 적이 없어 잘 모르겠어요."
        points=[dict(label=goal_label,location=point(goal),place_type="park" if i%2==0 else "market",evidence="caregiver_report",origin_slot="routine_destinations",weight=.5,precision="poi")]
        if family=="avoid":points.append(dict(label=quiet_label,location=point(quiet),place_type="park",evidence="caregiver_report",origin_slot="hazard_awareness_vulnerability",weight=.5,precision="poi"))
        persona=dict(id=pid,type="dementia",name="합성 어르신 "+pid,age=rng.randint(68,89),home=point(home),created_at="2026-10-08T09:00:00",version=1,attraction_points=points,
          behavior_notes=list(answers.values()),onboarding_quotes={k:[v] for k,v in answers.items()},
          onboarding_turns=[dict(slot=k,question=QUESTIONS[k],answer=v,recorded_at="2026-10-08T09:00:00") for k,v in answers.items()])
        started=f"2026-10-10T{hour:02d}:00:00"
        report=dict(id="report-"+pid,persona_id=pid,missing_type="dementia",lkp=point(start),lkp_time=started,
          situation="혼자 걷는 모습을 마지막으로 봤습니다. 오늘 어디로 가려는지는 모릅니다.",environment_observations=[],behavior_observations=[])
        noisy=i%8==3
        if family=="avoid":report["environment_observations"]=[dict(feature=points[0]["place_type"],location=point(goal),radius_m=120,noisy=noisy,crowded=None,source="synthetic_scenario",valid_from=started,valid_until=f"2026-10-10T{hour+6:02d}:00:00")]
        inputs.append(dict(person_id=pid,split=split,family=family,persona=persona,report=report))
        usual=quiet if family=="avoid" and noisy else goal
        routes={v:road(start,v) for v in (usual,unrelated)}
        back=road(usual,home)+road(home,usual);dist=sum(s[2] for s in routes[usual])
        for future in ("habitual","departure","contradictory"):
            segs=routes[unrelated] if future=="contradictory" else routes[usual]
            snapshots=[];pathpoints=[];d=0.;arrived=False;target_length=sum(s[2] for s in segs)
            future_rng=random.Random(912000+i) # no prediction RNG, stable across future variants
            for minute in range(361):
                if minute:
                    elapsed=minute-1
                    if future=="departure" and elapsed==90:
                        here=at_distance(segs,min(d,target_length));n=nearest(here["lng"],here["lat"])
                        segs=road(n,unrelated);d=0.;target_length=sum(s[2] for s in segs)
                    waiting=family=="wait" and elapsed<wait and future!="contradictory"
                    resting=(elapsed%(bout+rest))>=bout
                    if not waiting and not resting:
                        if d<target_length:d=min(target_length,d+speed)
                        elif future=="habitual":
                            if not arrived:arrived=True;leave=elapsed+future_rng.choice([30,60,90])
                            if elapsed>=leave:segs=back;target_length=sum(s[2] for s in segs);d=0.;arrived=False
                pos=at_distance(segs,min(d,target_length))
                if minute%5==0:pathpoints.append(dict(minute=minute,**pos))
                if minute in (60,120,240,360):snapshots.append(dict(hour=minute//60,position=pos))
            truth.append(dict(person_id=pid,split=split,future=future,snapshots=snapshots,path=pathpoints,
              assumptions=dict(speed_m_min=speed,walk_bout_minutes=bout,rest_minutes=rest,initial_wait_minutes=wait if family=="wait" else 0,
                departure_minute=90,route="independent shortest paths with edge geometry",unrelated_destination=point(unrelated))))
        manifest.append(dict(person_id=pid,family=family,start_node=start,goal_node=goal,home_node=home,unrelated_node=unrelated,quiet_node=quiet,truth_path_km=dist/1000,split=split))
    save("inputs.json",inputs);save("truth_private.json",truth);save("dataset_manifest.json",manifest)
    save("dataset_notes.json",dict(people=N,development=DEV,evaluation=N-DEV,unique_future_paths=3*N,previous_set="E01-E40 (EFFICIENCY_KINTEX_v1) used for development of main; not reused",map_sha256=sha,map_metadata=json.loads(path.with_suffix(".json").read_text()),
      independence="Truth uses NetworkX shortest paths and authored timelines; no prediction engine, output or RNG.",
      limitation="Onboarding and truth share authored assumptions. Four families/repeated sentence patterns, not expert labels or representative dementia population.",
      split="Disjoint IDs/geometries/parameters; archetypes overlap, not out-of-template generalization.",
      facilities="Synthetic labels/coordinates on actual outdoor roads; no real POI/noise claim.",
      truth_weights="Equal stress-test weights, not empirical future probabilities.",
      snapshot_boundary="Completed onboarding snapshots with real seed questions; no adaptive chatbot test.",
      no_family_arrival="No hypothetical reunion. Observed return ends the incident."))
    print(json.dumps(dict(people=len(inputs),truths=len(truth),min_goal_km=min(x["truth_path_km"] for x in manifest),max_goal_km=max(x["truth_path_km"] for x in manifest))))
if __name__=="__main__":main()


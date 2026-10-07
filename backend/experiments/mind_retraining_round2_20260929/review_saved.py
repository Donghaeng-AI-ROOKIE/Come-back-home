"""Explicit input-to-output review annotations by Codex, not keyword scoring."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REVIEWS={
'original72_epoch2':{
'D01-1':('contradicted','휴식 행동은 맞지만 피로 우선 대신 소음 회피를 휴식 원인으로 바꿨다.'),
'D01-2':('contradicted','낮은 피로이면 소음을 피해 가야 하는데 낮은 피로를 지속 이동 이유로 삼았다.'),
'D01-3':('supported','확인된 조용함과 이동 유지 개인 조건을 연결한다.'),
'D01-4':('contradicted','소음 미확인을 언급하면서도 근거 없이 이동을 확정했다.'),
'D02-1':('unclear','일몰 뒤 B는 맞지만 낮의 낮은 목적이라는 표현은 원문의 낮 목적 미확인을 명료하게 보존하지 않는다.'),
'D02-2':('incomplete','B 도착은 보존했으나 도착 후 기다리는 개인 조건 대신 무관한 낮 정보로 대기 결정을 설명했다.'),
'D02-3':('supported','낮의 외출 목적이 미확인이라는 판단 보류의 핵심 근거가 있다.'),
'D02-4':('contradicted','일몰 관측은 미확인인데 해가 진 조건이 현재 사실과 맞는다고 확정했다.'),
'D03-1':('supported','보호자 요청만으로 실제 대기를 확정하지 않는다.'),
'D03-2':('incomplete','기억만이라는 일반론으로 수락 발언과 이후 미관찰의 구분을 설명하지 못했다.'),
'D03-3':('incomplete','미래를 확정할 수 없다는 일반론만 있고 방향 상실 때 반복 관찰한 대기와 현재 행동의 연결이 없다.'),
'D03-4':('supported','방향 상실 후 목적지 없는 최근 행동을 현재 이동에 연결한다. 과거 정정의 언급은 생략했다.'),
'D04-1':('contradicted','가족 부재가 관측됐는데 추정할 수 없다는 이유로 혼자인 경우의 회피를 누락했다.'),
'D04-2':('supported','가족 동행과 소음이 함께 있는 현재 조건에서 이동 유지 예외를 연결한다.'),
'D04-3':('supported','확인된 소음 부재를 조용할 때의 개인 이동 조건과 연결한다.'),
'D04-4':('supported','시각 언급은 불필요하지만 가족 동행을 알 수 없다는 정보 부족을 보존한다.')},
}

if (ROOT/'review_annotations.json').exists():
    REVIEWS.update(json.loads((ROOT/'review_annotations.json').read_text()))

def main():
    source=ROOT/'results/comparison.jsonl'
    rows=[json.loads(x) for x in source.read_text().splitlines()]
    reviewed=[];scores={}
    for r in rows:
        key=r['arm']+'_epoch'+str(r['epoch'])
        assessment=REVIEWS.get(key,{}).get(r['id'])
        if not assessment:continue
        outcome,note=assessment
        reviewed.append({'arm':r['arm'],'epoch':r['epoch'],'id':r['id'],'raw':r['raw'],'action_match':r['action_match'],
          'reason_assessment':outcome,'review_note':note,'joint_pass':r['raw_contract_pass'] and r['action_match'] and outcome=='supported'})
    for key in REVIEWS:
        group=[r for r in reviewed if r['arm']+'_epoch'+str(r['epoch'])==key]
        scores[key]={'reviewed':len(group),'supported_explanation':sum(r['reason_assessment']=='supported' for r in group),
            'joint_pass':sum(r['joint_pass'] for r in group),'contradicted':sum(r['reason_assessment']=='contradicted' for r in group),
            'incomplete_or_unclear':sum(r['reason_assessment'] in ('incomplete','unclear') for r in group)}
    report={'reviewer':'Codex, unblinded input/output comparison','independent_human_review':False,
       'clinical_validation':False,'scores':scores,'rows':reviewed}
    (ROOT/'results/explanation_review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(scores,ensure_ascii=False))
if __name__=='__main__':main()

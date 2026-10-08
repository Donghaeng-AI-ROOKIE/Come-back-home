"""Replay two saved Mi:dm outputs through the real extraction merge. No API calls."""
import argparse,json,hashlib,socket
from pathlib import Path
from app.phase0 import interview,prompts
from app.phase0.slots import slot_by_key
from app.schemas.persona import InterviewSession,PersonaType
from app.geo.geocode import GeoResult,to_attraction_points
from app.schemas.common import GeoPoint


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    def offline(*args,**kw):raise RuntimeError('network forbidden during saved-response replay')
    socket.socket.connect=offline
    paths=[a.capture/'calls'/f'midm_{i:03}.response.json' for i in (4,26)]
    transcript=json.loads((a.capture/'transcript.json').read_text())
    answers={row['answer'] for row in transcript if row.get('slot')=='routine_destinations'
             and row.get('answer_source')=='fixed_synthetic_guardian_answer_for_app_slot'}
    if len(answers)!=1:
        raise ValueError('This fixed replay requires one unchanged routine_destinations answer')
    utterance=answers.pop()
    session=InterviewSession(id='saved-synthetic-place-replay',guardian_name='합성',persona_type=PersonaType.dementia)
    snapshots=[]
    for path in paths:
        raw=json.loads(path.read_text())['choices'][0]['message']['content']
        parsed=prompts.parse_extract(raw)
        assert len(parsed['attraction_points'])==3
        interview._apply_extraction(session,slot_by_key('routine_destinations'),parsed,utterance=utterance)
        snapshots.append(json.loads(json.dumps(session.draft_attractions)))
    saved=json.loads((a.capture/'persona.json').read_text())
    points={x['label']:GeoPoint(**x['location']) for x in saved['attraction_points']}
    class Geo:
        def locate(self,query,anchor=None):
            for label,point in points.items():
                if label in query:return GeoResult(point,'poi','saved_synthetic_fixture')
    final,unresolved=to_attraction_points(session.draft_attractions,Geo())
    out={'scope':'saved synthetic Mi:dm outputs through real parser/merge/geocoder; no new model or network call',
         'source_sha256':{str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in paths},
         'interview_sha256':hashlib.sha256(Path(interview.__file__).read_bytes()).hexdigest(),
         'snapshots':snapshots,'persisted_types':{x.label:x.place_type for x in final},
         'unresolved':unresolved,'audit':session.extraction_audit,'new_api_calls':0}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'persisted_types':out['persisted_types'],'new_api_calls':0},ensure_ascii=False))


if __name__=='__main__':main()

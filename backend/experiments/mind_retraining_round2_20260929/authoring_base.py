"""Hand-authored contrast families; labels are NOT inferred by parsing guardian text.

Records are an authoring pilot, not independent real patients or trajectories.
No model/API calls. Output is immutable unless explicitly choosing a new directory.
"""
import argparse
import hashlib
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from contract import VERSION, messages, validate


def sha(b):
    return hashlib.sha256(b).hexdigest()


def families():
    # Each variant explicitly declares scenario state and author-labelled response.
    # Personal narratives below are newly authored synthetic observations, not quotes.
    return [
      ('T01','train','ENGINE_ONLY','휴식과 회복', '평소 피로가 심해지면 잠시 앉아요. 쉬는 시간을 마쳤더라도 아직 지쳐 있으면 더 쉬고, 괜찮아지면 가던 곳으로 걸어요.',[
        ({'f':.9},'rest','현재 피로가 높으며 이 사람은 지치면 쉬는 것으로 설정됐다.'),
        ({'f':.1},'continue','피로가 낮아 가던 이동을 유지하는 개인 조건에 해당한다.'),
        ({'f':.9,'rest':59},'rest','휴식은 끝났지만 피로가 남아 있어 개인 기록에 따라 더 쉰다.'),
        ({'f':.1,'rest':59},'continue','휴식 이력과 낮은 피로가 함께 주어져 원래 이동을 유지한다.')]),
      ('T02','train','DEM24','피로에도 지속 이동', '최근 함께 걸을 때는 지쳐 보여도 앉자고 하면 계속 걷겠다고 하며 실제로 걸었어요. 기운이 있을 때도 같은 목적지를 향해 걸어요.',[
        ({'f':.9},'continue','지쳐도 이동을 유지한 개인 행동 이력이 현재 상황과 맞는다.'),
        ({'f':.1},'continue','낮은 피로에서도 원래 목적지로 걷는 개인 이력을 유지한다.'),
        ({'f':.9,'rest':58},'continue','휴식 이력만으로 다시 쉬어야 한다고 추정하지 않고 주어진 개인 행동을 따른다.'),
        ({'f':.3,'hour':14},'continue','시각 변경만으로 이 사람의 이동 계획을 바꿀 근거가 없다.')]),
      ('T03','train','SYNTHETIC_ONLY','방향 상실 후 대기', '어디인지 모르겠다고 할 때는 서서 가족을 기다려요. 길을 알고 있을 때는 원래 가던 곳으로 가고요.',[
        ({'lost':True},'stay','최근 방향 상실이 발생해 가족을 기다리는 개인 조건이 활성화됐다.'),
        ({},'continue','방향 상실이 기록되지 않았고 원래 이동을 바꿀 조건이 없다.'),
        ({'lost':True,'f':.5},'stay','주어진 조건에서 필요한 것은 가족을 기다리는 대기이며 피로 휴식으로 바꾸지 않는다.'),
        ({'hour':15},'continue','오후라는 사실만으로 방향을 잃었다고 만들지 않는다.')]),
      ('T04','train','OUTDOOR','방향 상실과 익숙한 목적지', '낯설어서 길을 모르겠을 때에는 기다리지 않고 익숙한 등록 장소 B 쪽을 찾아가요. 헷갈리지 않을 때는 원래 이동을 계속해요.',[
        ({'lost':True},'seek:B','방향을 잃었을 때 익숙한 B를 찾는 개인 이력에 따라 목표를 정한다.'),
        ({},'continue','현재 방향 상실이 없으므로 기존 이동을 유지한다.'),
        ({'lost':True,'target':'B'},'seek:B','이미 기억한 목표가 B여도 현재 방향 상실 조건에 맞는 B 접근을 선택한다.'),
        ({'target':'B','hour':15},'continue','상태 변화 없이 목표 B를 향한 이동을 유지한다.')]),
      ('T05','train','ACOUSTIC','소음 관측 구분', '공원이 시끄러우면 다른 쪽으로 돌아가고, 조용한 게 확인되면 그냥 지나가요. 소리를 확인하지 못했을 때의 행동은 아직 몰라요.',[
        ({'feature':'park','noise':True},'avoid','공원의 소음이 확인되어 개인의 회피 조건과 일치한다.'),
        ({'feature':'park','noise':False},'continue','조용하다는 관측이 있으므로 원래 이동을 유지한다.'),
        ({'feature':'park'},'defer','현재 소음은 미확인이고 그 경우의 개인 반응도 없으므로 소음 확인이 필요하다.'),
        ({'feature':'park','noise':False,'crowd':True},'continue','혼잡만으로 소음이 있다고 바꾸지 않고 확인된 조용함과 개인 기록을 따른다.')]),
      ('T06','train','ACOUSTIC','복합 환경 조건', '시장에 사람이 많고 소리도 클 때만 길을 돌아가요. 둘 중 하나라도 아니라는 걸 알면 계속 가요. 확인 못한 경우는 지켜본 적 없어요.',[
        ({'noise':True,'crowd':True},'avoid','소음과 혼잡이 모두 확인되어 두 조건이 함께 성립한다.'),
        ({'noise':False,'crowd':True},'continue','소음이 없으므로 두 조건의 동시 성립이 아니다.'),
        ({'noise':True,'crowd':False},'continue','혼잡이 없다는 관측 때문에 회피 조건이 충족되지 않는다.'),
        ({'noise':True,'crowd':None},'defer','혼잡 관측이 없어 복합 조건을 확정할 수 없으며 확인이 필요하다.')]),
      ('T07','train','TIME','개인 일과', '오전에는 등록 장소 A, 저녁 여섯 시 이후에는 등록 장소 B를 찾는 일과가 반복돼요. 점심에는 어디를 찾는지 아직 잘 모르겠어요.',[
        ({'hour':8},'seek:A','오전 일과에 해당하는 등록 장소 A를 선택한다.'),
        ({'hour':19},'seek:B','현재 저녁이므로 이전 목표 A보다 저녁의 B 일과를 적용한다.'),
        ({'hour':13},'defer','오전과 저녁 사이의 개인 일과는 알려지지 않아 목적지를 추가 확인해야 한다.'),
        ({'hour':20,'target':'B'},'seek:B','저녁 일과에 맞는 B를 목표로 유지한다.')]),
      ('T08','train','SYNTHETIC_ONLY','도착 전후', '등록 장소 A에 닿기 전에는 계속 그쪽으로 가요. 도착하면 서서 저를 기다리는 모습을 여러 번 봤어요.',[
        ({'arrived':False},'continue','아직 A 도착 전이므로 접근 중인 이동을 유지한다.'),
        ({'arrived':True},'stay','A 도착이 확인되어 기다리는 개인 행동으로 전환한다.'),
        ({'arrived':True,'hour':16},'stay','시각이 달라도 A 도착 후 기다리는 조건은 동일하다.'),
        ({'arrived':False,'f':.35},'continue','A에 도착하지 않았고 별도의 휴식 조건이 없어 기존 접근을 유지한다.')]),
      ('T09','train','CAREGIVER','지시 약속 관찰 차이', '제가 여기서 기다리라고 했어요. 실제로 기다리는지는 보지 못했어요.',[
        ({'lost':True},'defer','보호자의 지시만 있으며 이 사람이 실제로 기다리는 행동을 보였는지 확인되지 않았다.'),
        ({'lost':True,'note':'어르신이 기다리겠다고 답했어요. 이후 행동은 보지 못했어요.'},'defer','기다리겠다는 발언은 실제 대기 행동의 관찰과 달라 선택을 확정할 수 없다.'),
        ({'lost':True,'note':'잘은 모르지만 아마 기다릴 것 같아요. 실제로 그런 상황을 본 적은 없어요.'},'defer','보호자의 추정만으로 방향 상실 후 행동을 정하지 않는다.'),
        ({'lost':True,'note':'지난 외출들에서 방향을 잃을 때마다 같은 자리에서 가족을 기다리는 모습을 반복해서 봤어요.'},'stay','방향 상실 후 기다리는 반복 관찰이 현재 조건을 뒷받침한다.')]),
      ('T10','train','SYNTHETIC_ONLY','원문과 요약 충돌', '최근에는 많이 지치면 앉아서 쉬어요. 피곤해도 계속 간다는 예전 기록은 지금과 달라요.',[
        ({'f':.9,'summary':'피곤해도 계속 걷는다'},'rest','최근 보호자 원문이 이전 요약을 정정하므로 휴식을 선택한다.'),
        ({'f':.9,'summary':'쉬지 않고 이동한다','hour':15},'rest','현재 원문에 명시된 피로 반응을 이전 요약보다 우선한다.'),
        ({'f':.9,'note':'최근에는 지쳐도 앉지 않고 계속 걸어요. 쉬는 사람으로 적힌 예전 요약은 틀렸어요.','summary':'피로가 높으면 쉰다'},'continue','보호자의 최신 정정은 지속 이동이며 과거 요약으로 덮지 않는다.'),
        ({'f':.9,'note':'쉴 거라고 제가 예상만 했어요. 실제 행동은 못 봤습니다.','summary':'항상 피곤하면 쉰다'},'defer','확정적 요약의 원문은 추정이므로 휴식 행동의 관찰을 더 확인해야 한다.')]),
      ('T11','train','SYNTHETIC_ONLY','질문 맥락과 짧은 답변', '아니요. 그럴 땐 앉아요.',[
        ({'f':.9,'question':'많이 지쳐도 계속 걷나요?'},'rest','계속 걷는지 묻는 질문에 대한 부정과 앉는다는 답변을 연결한다.'),
        ({'f':.9,'question':'많이 지치면 쉬나요?','note':'아니요. 계속 가세요.'},'continue','휴식 여부에 대한 부정 답변과 지속 이동 관찰을 함께 읽는다.'),
        ({'lost':True,'question':'방향을 잃으면 돌아다니시나요?','note':'아니요. 그 자리에 계셔요.'},'stay','방향 상실 상황에서 이동하지 않는다는 답변에 따라 대기한다.'),
        ({'lost':True,'question':'길을 잃으면 어디로 가나요?','note':'그건 본 적이 없어요.'},'defer','질문 자체를 개인의 행동 사실로 삼지 않고 미관찰로 남긴다.')]),
      ('T12','train','ACOUSTIC','소음에도 대기하는 개인', '공원이 시끄러우면 피해서 가는 게 아니라 그 자리에 서서 저를 기다려요. 조용하면 원래 길을 가요.',[
        ({'feature':'park','noise':True},'stay','이 사람은 소음에 회피 이동이 아니라 대기로 반응한다고 기록돼 있다.'),
        ({'feature':'park','noise':False},'continue','조용한 공원에서 원래 이동을 유지하는 개인 조건이다.'),
        ({'feature':'park','noise':True,'crowd':True},'stay','혼잡이 추가돼도 주어진 개인 소음 반응은 대기이다.'),
        ({'feature':'park'},'defer','소음 여부가 미확인이라 대기와 이동 중 무엇이 해당하는지 확인해야 한다.')]),
      ('T13','train','OUTDOOR','멈춰 살핀 뒤 재개', '길이 헷갈리면 먼저 멈춰 둘러봐요. 이후 길을 알아봤다는 확인이 있으면 원래 목표로 다시 가고, 아직 모르겠으면 계속 서 있어요.',[
        ({'lost':True},'stay','방향 상실 후 길을 알아봤다는 확인이 아직 없어 멈춰 살피는 상태를 선택한다.'),
        ({'lost':True,'resolved':True,'previous':'stay'},'seek:A','방향 회복이 더 최근 사건으로 확인되어 기억한 A를 향해 이동을 재개한다.'),
        ({'lost':True,'previous':'stay'},'stay','이미 대기 중이고 방향 회복이 없어 그 상태를 유지한다.'),
        ({'lost':True,'resolved':True,'previous':'stay','target':'B'},'seek:B','방향 회복 후 이전 목표 B를 잊지 않고 다시 접근한다.')]),
      ('T14','train','DEM24','친숙한 얼굴과 욕구', '가족 얼굴이 안 보인다고 확인되면 등록 장소 B에서 찾아봐요. 가족이 곁에 있다고 확인되면 원래 가던 곳으로 가요. 확인되지 않으면 반응을 모르겠어요.',[
        ({'companion':False},'seek:B','가족이 보이지 않는다는 현재 확인과 개인의 B 탐색 이력을 연결한다.'),
        ({'companion':True},'continue','가족이 곁에 있으므로 찾으러 B로 가는 조건이 아니다.'),
        ({'companion':None},'defer','가족이 곁에 있는지 확인되지 않아 해당 개인 조건을 확정할 수 없다.'),
        ({'companion':False,'target':'B'},'seek:B','가족이 없다는 확인에 따라 이미 기억한 B로 향한다.')]),
      ('T15','train','SYNTHETIC_ONLY','도착 후 목적지 없는 이동', 'A에 도착하기까지는 A로 가고, 닿은 뒤에는 거기 머무르지 않고 정해진 곳 없이 주변을 걸어요.',[
        ({'arrived':False},'continue','A에 도착하지 않아 기존 목표 접근을 유지한다.'),
        ({'arrived':True},'roam','도착 후 목적지 없이 걷는 개인 이력에 따라 기존 목표를 해제한다.'),
        ({'arrived':True,'hour':11},'roam','도착 후 행동은 시각 변화와 무관하게 목적지 없는 이동이다.'),
        ({'arrived':False,'f':.1},'continue','도착 전이며 피로도 낮아 A로의 기존 이동을 유지한다.')]),
      ('T16','train','ENGINE_ONLY','휴식 후 무목적 재개', '특별히 가는 곳 없이 걷다가 지치면 쉬어요. 기운이 돌아오면 다시 주변을 걷고, 쉬는 중에도 계속 피곤하면 더 앉아 있어요.',[
        ({'target':None,'f':.9,'previous':'roam'},'rest','높은 피로에 반응해 잠깐 쉬며 목적지를 새로 만들지 않는다.'),
        ({'target':None,'f':.1,'previous':'rest','rest':59},'roam','피로가 낮아져 휴식 뒤 목적지 없는 이동을 재개한다.'),
        ({'target':None,'f':.9,'previous':'rest','rest':59},'rest','휴식 종료 이력이 있어도 여전히 지쳐 있어 더 쉰다.'),
        ({'target':None,'f':.1,'previous':'roam'},'continue','이미 목적지 없이 걷고 있으며 현재 낮은 피로에서 그 이동을 유지한다.')]),
      ('T17','train','ACOUSTIC','혼잡과 소음 분리', '시장은 사람이 빽빽하면 소리가 작아도 돌아가요. 사람이 드문 것이 확인되면 소리가 커도 그대로 가고요.',[
        ({'crowd':True,'noise':False},'avoid','이 사람의 조건은 소음이 아니라 확인된 혼잡이므로 시장을 회피한다.'),
        ({'crowd':True,'noise':True},'avoid','혼잡이 확인되어 개인 회피 조건이 충족된다.'),
        ({'crowd':False,'noise':True},'continue','소음이 커도 혼잡하지 않다는 현재 관측과 개인 예외에 따라 이동한다.'),
        ({'crowd':None,'noise':False},'defer','조용함만으로 혼잡 여부를 알 수 없어 사람 밀집 상태를 확인해야 한다.')]),
      ('T18','train','DEM24','현재 거부 발언과 행동 이력', 'A로 가다가 지금은 거기 가기 싫다고 말한 때에는 목표 없이 주변을 돌아다니는 것을 반복해서 봤어요. 싫지 않다고 확인한 때는 A로 계속 갔어요.',[
        ({'rejection':True},'roam','A에 대한 현재 거부가 확인되어 목표 없이 이동하는 개인 행동 이력을 적용한다.'),
        ({'rejection':False},'continue','현재 거부하지 않는다는 확인에 따라 A로의 기존 이동을 유지한다.'),
        ({'rejection':True,'hour':14},'roam','시각과 무관하게 현재 확인된 거부에 따라 A 목표를 해제한다.'),
        ({'rejection':None},'defer','현재 거부 여부가 미확인이므로 과거의 거부 이력을 지금 사실로 만들지 않는다.')]),
      ('D01','development','ACOUSTIC','휴식 우선과 환경', '공원 소리를 꺼려 돌아가는 분이지만, 몸이 많이 지치면 우선 앉습니다. 덜 지쳤고 공원이 조용하면 그대로 걸어요.',[
        ({'feature':'park','noise':True,'f':.9},'rest','소음보다 먼저 쉬는 명시적 개인 우선순위를 적용한다.'),
        ({'feature':'park','noise':True,'f':.1},'avoid','피로가 낮고 소음이 확인되어 공원 회피 조건이다.'),
        ({'feature':'park','noise':False,'f':.1},'continue','피로와 소음 회피 조건 모두 성립하지 않아 기존 이동을 유지한다.'),
        ({'feature':'park','f':.1},'defer','피로는 낮지만 소음 관측이 없어 이동과 회피를 구분할 추가 정보가 필요하다.')]),
      ('D02','development','TIME','저녁 목표 도착', '해가 진 뒤에는 B에 갑니다. B에 다다르면 저를 기다리고요. 낮의 외출 목적은 잘 모르겠습니다.',[
        ({'hour':19,'sunset':True},'seek:B','해가 진 현재 상황에 맞는 B를 선택한다.'),
        ({'hour':19,'sunset':True,'target':'B','arrived':True},'stay','저녁 목표 B 도착이 확인되어 기다린다.'),
        ({'hour':11,'sunset':False},'defer','낮에는 목적지가 알려져 있지 않아 개인 일과를 확인해야 한다.'),
        ({'hour':19,'sunset':None},'defer','시각만으로 일몰을 단정하지 않고 주어진 개인 조건의 관측을 확인해야 한다.')]),
      ('D03','development','CAREGIVER','대기 지시와 반복 관찰', '잠깐 서 있으라고 부탁한 상황입니다. 그 뒤의 행동은 확인하지 않았어요.',[
        ({'lost':True},'defer','부탁한 내용은 실제로 기다리는 성향의 증거가 아니다.'),
        ({'lost':True,'note':'대답은 알겠다고 했지만 이후는 못 봤습니다.'},'defer','당시 수락만으로 그 이후 행동을 확정하지 않는다.'),
        ({'lost':True,'note':'제가 올 때까지 머무르는 모습을 길을 잃었던 지난 외출들에서 여러 번 확인했습니다.'},'stay','현재 방향 상실과 반복 관찰된 대기를 연결한다.'),
        ({'lost':True,'note':'예전에는 기다렸는데 최근에는 직접 찾아다녀요. 어제와 그제도 방향을 잃고 목적지 없이 걸었습니다.'},'roam','최근 관찰이 과거 대기를 정정하므로 목적지 없는 이동을 선택한다.')]),
      ('D04','development','ACOUSTIC','동행자에 따른 예외', '시장이 시끄러울 때 혼자면 돌아갑니다. 가족이 옆에 있으면 시끄러워도 같이 원래 길을 갑니다. 조용하면 혼자라도 계속 갑니다.',[
        ({'noise':True,'companion':False},'avoid','소음과 가족 부재가 확인되어 회피 조건에 해당한다.'),
        ({'noise':True,'companion':True},'continue','가족 동행이라는 개인의 예외 조건 때문에 기존 이동을 유지한다.'),
        ({'noise':False,'companion':False},'continue','조용한 경우에는 혼자여도 이동을 유지한다.'),
        ({'noise':True,'companion':None},'defer','가족 동행 여부가 미확인이라 예외 조건 적용을 결정할 수 없다.')]),
      ('E01','evaluation','ACOUSTIC','서로 다른 논리 조건', '시장 소리가 크거나 사람이 빽빽한 것 중 하나만 있어도 돌아서요. 둘 다 없다는 확인이 있으면 원래 길로 갑니다.',[
        ({'noise':True,'crowd':False},'avoid','두 조건 중 소음 하나가 성립하여 회피한다.'),
        ({'noise':False,'crowd':True},'avoid','두 조건 중 혼잡 하나가 성립하여 회피한다.'),
        ({'noise':False,'crowd':False},'continue','두 회피 조건이 모두 부정되어 기존 이동을 유지한다.'),
        ({'noise':False,'crowd':None},'defer','혼잡이 미확인이므로 어느 조건도 없다고 결론 내리지 않는다.')]),
      ('E02','evaluation','ENGINE_ONLY','방향 상실과 휴식 우선', '길을 모르겠으면 멈춰 가족을 기다리되, 몸까지 몹시 지치면 서서 기다리기보다 앉아 쉽니다. 길을 알고 덜 피곤하면 계속 갑니다.',[
        ({'lost':True,'f':.9,'rest':58},'rest','휴식 종료 뒤에도 피로가 높아 앉아 쉬는 개인 우선순위를 적용한다.'),
        ({'lost':True,'f':.1},'stay','길을 모르지만 피로는 낮아 가족을 기다리는 대기를 선택한다.'),
        ({'f':.1},'continue','방향 상실이 없고 덜 피곤하여 기존 이동을 유지한다.'),
        ({'lost':True,'f':.9,'previous':'stay'},'rest','이전 대기 상태보다 현재 높은 피로에 대한 휴식 조건을 우선한다.')]),
      ('E03','evaluation','OUTDOOR','목표 인식 확인', 'B를 찾는 중인데, 도착해도 본인이 그곳임을 알아보지 못하면 계속 주변을 걸어요. B라고 알아봤다는 확인이 있을 때에만 그 자리에 머뭅니다.',[
        ({'target':'B','arrived':True,'recognized':False},'roam','물리적 도착과 개인의 장소 인식은 다르며 인식하지 못한 경우의 주변 이동을 선택한다.'),
        ({'target':'B','arrived':True,'recognized':True},'stay','도착과 장소 인식이 모두 확인되어 머문다.'),
        ({'target':'B','arrived':True,'recognized':None},'defer','도착은 확인되지만 장소 인식은 미확인이어서 인식 확인이 필요하다.'),
        ({'target':'B','arrived':False,'recognized':False},'seek:B','도착 전이므로 찾고 있는 등록 장소 B로 향한다.')]),
      ('E04','evaluation','SYNTHETIC_ONLY','인용 대상과 정보 충분성', '옆집 어르신은 힘들면 쉬신대요. 우리 아버지가 그러는지는 본 적 없어요.',[
        ({'f':.9},'defer','다른 사람의 휴식 행동을 이 사람의 성향으로 전이하지 않는다.'),
        ({'f':.9,'note':'제가 힘들면 쉬자고 해요. 아버지가 실제로 멈추는지는 확인 못 했어요.'},'defer','보호자의 제안만으로 이 사람의 휴식을 정답으로 만들지 않는다.'),
        ({'f':.9,'note':'이번에는 아버지를 직접 본 기록이에요. 최근 외출에서 지칠 때마다 앉아 쉬셨습니다.'},'rest','이 사람에 대한 직접 관찰과 현재 높은 피로가 연결된다.'),
        ({'f':.9,'note':'제 아버지는 지쳐도 계속 걸으셨어요. 쉰다는 설명은 다른 분 이야기였습니다.'},'continue','다른 사람에 대한 정보를 제외하고 이 사람의 지속 이동 기록을 적용한다.')])
    ]


def build(base, sources):
    rows=[]
    for family_index,(fid,split,source,topic,note,variants) in enumerate(families()):
        for idx,(v,answer,reason) in enumerate(variants):
            c=deepcopy(base)
            c['contract_version']=VERSION
            c['case_id']=fid+'-'+str(idx+1)
            c['person_id']='synthetic-'+fid
            c['person_revision']='author-v1-'+fid
            c['person']['evidence_notes']=[{'id':'N1','text':'질문: '+v.get('question','평소 어떤 행동을 직접 보셨나요?')+'\n답변: '+v.get('note',note)}]
            c['person']['initial_interpretation']={'summary':v['summary']} if 'summary' in v else {}
            c['person']['prepared_person_interpretation']={}
            c['person']['compiled_environment_responses']=[]
            c['clock_time']=f"2026-09-28T{v.get('hour',9):02d}:00:00+09:00"
            c['trigger']='state_review'
            s=c['state']
            s.update(elapsed_minutes=60,distance_m=500,fatigue=v.get('f',.2),confusion=.2,
                     current_action=v.get('previous','seek'),target_label=('등록 장소 '+v.get('target','A')) if v.get('target','A') else None,
                     target_reached=v.get('arrived',False),last_rest_end_minutes=v.get('rest'),recent_events=[])
            for param,kind in [('lost','orientation_lost'),('resolved','orientation_recovered')]:
                if v.get(param):s['recent_events'].append({'kind':kind,'elapsed_minutes':58 if param=='lost' else 59})
            s['recent_events'].append({'kind':'orientation_status_observation','elapsed_minutes':60,
                    'value':'oriented' if not v.get('lost') or v.get('resolved') else 'lost',
                    'provenance':'synthetic condition, not a real sensor measurement'})
            for param in ('companion','sunset','recognized','rejection'):
                if param in v:s['recent_events'].append({'kind':param+'_observation','value':v[param],'elapsed_minutes':59})
            feature=v.get('feature','market')
            c['environment']={'map_proximity_m':{k:20 if k==feature else None for k in ('market','park','water','forest')},
                  'observed_signals':{feature:{'noisy':v.get('noise'),'crowded':v.get('crowd')}},
                  'observed_place_labels':[], 'visibility_of_other_places':'unknown',
                  'provenance':'synthetic scenario, not measured KINTEX sound/crowd'}
            research=sources.get(source)
            c['research']=[{'id':'R1','source_id':source,'excerpt':research['input_summary'],
                          'scope':research['limit']} ] if idx==family_index%4 and research and research.get('input_summary') else []
            c['limitations']=['Synthetic guardian narrative and state; not an actual patient trajectory.',
                 'Research is background, not individual ground truth.', 'Event observations are injected for this offline task; production adapters unverified.']
            action=answer.split(':')[0]
            target=answer.split(':')[1] if ':' in answer else None
            y={'status':'insufficient_information' if action=='defer' else 'decision',
               'action':None if action=='defer' else action,
               'goal_operation':None if action=='defer' else 'set' if action=='seek' else 'clear' if action=='roam' else 'keep',
               'goal_label':'등록 장소 '+target if target else None,
               'avoid_feature':feature if action=='avoid' else None,
               'evidence_ids':['N1','state','environment','history','clock'],
               'reason':reason,'confusion_level':'unknown'}
            validate(y,c)
            m=messages(c)+[{'role':'assistant','content':json.dumps(y,ensure_ascii=False)}]
            rows.append({'id':c['case_id'],'split':split,'person_family':fid,'case_family':fid,'template_family':fid,
                 'topic':topic,'context':c,'messages':m,'expected':y,
                 'rubric':{'required_status':y['status'],'allowed_action_goal_feature':[[y['action'],y['goal_label'],y['avoid_feature']]],
                    'basis':'AI-authored explicit synthetic personal condition; not clinical truth',
                    'source_role':'background motivation only, not per-patient label proof',
                    'source_ids':[] if source in ('SYNTHETIC_ONLY','ENGINE_ONLY') else [source]},
                 'review':{'author':'Codex','semantic_review':'author-reviewed','independent_human_review':False,
                    'clinical_review':False,'real_guardian_data':False,'real_frontend_output':False},
                 'release':'authoring_pilot_not_full_training_release'})
    return rows


def main():
    p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--sources',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();out=Path(a.out)
    if out.exists() and any(out.iterdir()):raise SystemExit('refusing overwrite; choose new output directory')
    out.mkdir(parents=True,exist_ok=True)
    base_blob=Path(a.base).read_bytes();base=json.loads(base_blob)[0]['context']
    sources_blob=Path(a.sources).read_bytes();sources=json.loads(sources_blob)
    rows=build(base,sources)
    manifest={'contract':VERSION,'records':len(rows),'families':len(families()),'files':{},
       'base_fixture_sha256':sha(base_blob),'sources_sha256':sha(sources_blob),
       'model_calls':0,'gpu_training':False,'human_review':False,'clinical_validation':False,
       'evaluation_role':'small authoring holdout; not the planned final 96-state evaluation',
       'source_split':'sources shared as background; source-held-out evaluation still required',
       'publication_status':'research preparation only'}
    for split in ('train','development','evaluation'):
        group=[r for r in rows if r['split']==split]
        blob=('\n'.join(json.dumps(r,ensure_ascii=False,sort_keys=True) for r in group)+'\n').encode()
        path=out/(split+'.jsonl');path.write_bytes(blob)
        manifest['files'][path.name]={'records':len(group),'families':len({r['case_family'] for r in group}),
             'sha256':sha(blob),'actions':dict(Counter(r['expected']['action'] or 'insufficient_information' for r in group))}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__=='__main__':main()

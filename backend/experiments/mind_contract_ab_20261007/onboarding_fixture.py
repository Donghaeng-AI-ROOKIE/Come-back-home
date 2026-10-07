"""One synthetic caregiver for testing the real app's onboarding entry points.

These are authored answers, not a patient record, clinician label, or a
held-out quality benchmark. The actual app chooses and phrases questions;
the fixture never supplies the research dev128 questions to the app.
"""

NAME = '검증가상어르신'
AGE = 78
HOME = '경기도 고양시 일산서구 대화동'
ANSWERS = {
    'identity': f'{NAME}님이고 만 {AGE}세예요. 치매가 있으세요.',
    'home': f'{HOME}에 살아요.',
    'routine_destinations': '혼자 가는 곳은 없고 저와 함께 다녀요. 경기도 고양시 일산서구 대화동의 느티공원과 해든상가, 솔빛쉼터를 함께 가요. 정해진 길이나 도는 방향은 없어요.',
    'autobiographical_destination_pull': '옛집이나 직장 같은 과거 장소에 가겠다는 말은 안 하세요. 반복해서 찾는 과거 장소는 없어요.',
    'dementia_wandering_pattern': '실종된 적은 없어요. 실종 때 어디로 갔는지는 경험이 없어 모르겠어요.',
    'mobility_transport_capacity': '저와 걸을 때 무릎 때문에 여섯 분을 계속 걷거나 이백팔십 미터 가면 먼저 도달한 쪽에서 앉아 쉬어야 해요. 쉬실 때는 오 분 앉아 있다가 다시 걸으세요. 천천히 걷고 혼자 외출하지는 않으세요.',
    'hazard_awareness_vulnerability': '차도 신호와 물가, 계단을 스스로 피할 수 있는지는 못 봐서 모르겠어요. 다만 해든상가 안에서 시끄러우면 밖으로 나오시는 것은 직접 봤어요. 다른 상가도 그러시는지는 모르겠어요.',
    'communication_approach_vulnerability': '이름을 부르면 저를 쳐다보세요. 낯선 사람이나 경찰이 다가올 때는 어떻게 반응하는지 보지 못했어요.',
    'medication': '약을 거른 뒤 증상은 관찰한 적이 없어 모르겠어요. 밤이나 추위, 더위에 혼자 이동하는 것도 못 봤어요.',
    'wayfinding_error_recovery_deficit': '함께 다닐 때 방향을 잘못 들어 제가 알려준 적이 있어요. 혼자 스스로 되돌아올 수 있는지는 모르겠어요.',
    'lost_behavior': '길을 잃었다고 본인이 알아차리고 제가 곁에 없을 때는 그 자리에 서서 기다리는 모습을 두 번 봤어요. 제가 오면 기다림은 끝났어요.',
    'distress_induced_movement_reactivity': '불안하거나 초조할 때 이동이 달라지는지는 직접 본 적이 없어 모르겠어요.',
}

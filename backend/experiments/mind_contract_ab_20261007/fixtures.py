"""Handwritten contract fixtures for candidates A/B (2026-10-07).

Written by hand to exercise the compiler, scorer and walking engine. They are
not model outputs, and passing them is not evidence of interpretation quality.
"""


def a_rule(action, condition, note='N1', goal='', scope=(), hold=0):
    return {'action': action, 'goal_place': goal, 'applies_only_at': list(scope),
            'condition': condition, 'hold_minutes': hold, 'note_ids': [note]}


def a_out(rules, non_action=('N0',)):
    return {'source_assessment': '수기 계약 fixture', 'rules': rules,
            'non_action_note_ids': list(non_action)}


def unit(note, quote, kind='other_information', subject='patient', action='none',
         start='', end='', goal='', scope=(), hold=0):
    return {'note_id': note, 'quote': quote, 'subject': subject, 'kind': kind, 'action': action,
            'goal_place': goal, 'applies_only_at': list(scope), 'start_condition': start,
            'end_condition': end, 'hold_minutes': hold}


N0 = unit('N0', '질문에 나온 후보 이름이에요')

A_CORRECT = {
    'P05': a_out([a_rule('rest', 'is_walking and (continuous_walk_minutes >= 8 or distance_since_rest_m >= 450)')]),
    'P14': a_out([a_rule('seek', 'target_recognized', goal='느티공원')]),
    'P21': a_out([a_rule('walk', 'lost_awareness')]),
    'P25': a_out([a_rule('wait', 'clock_hour >= 8 and clock_hour < 9 and not family_present')]),
    'P29': a_out([a_rule('rest', 'is_walking and (continuous_walk_minutes >= 6 or distance_since_rest_m >= 280)'),
                  a_rule('wait', 'lost_awareness and not family_present', note='N2')]),
    'P06': a_out([], non_action=('N0', 'N1')),
    'P13': a_out([], non_action=('N0', 'N1')),
    'P24': a_out([], non_action=('N0', 'N1')),
}

B_CORRECT = {
    'P05': {'units': [N0, unit('N1', '무릎 때문에 앉아 쉬어야 해요', 'functional_need', action='rest',
                               start='is_walking and (continuous_walk_minutes >= 8 or distance_since_rest_m >= 450)')]},
    'P14': {'units': [N0, unit('N1', '그쪽으로 걸어 출발했어요', 'observed_response', action='seek',
                               start='target_recognized', goal='느티공원'),
                      unit('N1', '알아보지 못했을 때의 행동은 아직 본 적 없어요', 'unobserved')]},
    'P21': {'units': [N0,
                      unit('N1', '어머니가 아니라 아버지 이야기였어요', 'corrected_away', subject='other_person'),
                      unit('N1', '실제로 멈추지 않고 계속 걸었어요', 'observed_response', action='walk',
                           start='lost_awareness'),
                      unit('N1', '기다리는지는 어머니에게서 본 적 없어요', 'unobserved')]},
    'P25': {'units': [N0, unit('N1', '현관에서 기다렸어요', 'observed_response', action='wait',
                               start='clock_hour >= 8 and not family_present', end='clock_hour >= 9')]},
    'P29': {'units': [N0,
                      unit('N1', '먼저 도달한 쪽에서 쉬어야 해요', 'functional_need', action='rest',
                           start='is_walking and (continuous_walk_minutes >= 6 or distance_since_rest_m >= 280)'),
                      unit('N2', '그 자리에서 기다렸어요', 'observed_response', action='wait',
                           start='lost_awareness and not family_present', end='family_present')]},
    'P06': {'units': [N0, unit('N1', '쉬지 않고 이십오 분은 걸을 수 있어요', 'capacity_only')]},
    'P13': {'units': [N0, unit('N1', '느티공원에 가야 한다는 말은 매일 하세요', 'stated_goal'),
                      unit('N1', '실제로 일어나 출발한 적은 확인하지 못했어요', 'unobserved')]},
    'P24': {'units': [N0, unit('N1', '기다리는 모습은 관찰하지 못했어요', 'unobserved'),
                      unit('N1', '다른 가족이 돌보는 분 이야기였어요', 'other_information', subject='other_person')]},
}

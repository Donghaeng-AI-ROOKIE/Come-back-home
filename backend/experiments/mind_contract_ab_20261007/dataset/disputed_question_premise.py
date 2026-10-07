"""Disputed cases: question-premise inheritance (separate from dev128; draft, unreviewed).

Short answers such as '네' carry the condition and the ending stated in the
question ('가족이 올 때까지 기다리시나요?' -> wait while family is absent, stop when
family arrives). Contrasting answers deny part of the premise. The authored
reference rules only make the scenes internally coherent; they are not proof
that the reading is right. A person must review these before they count as
evidence. dev128 answers are not changed by this file.

Scoring floor. note_policy_eval.score() also passes no_personal_reaction on
scenes whose expectation is [] or ['baseline'], so an empty output (no rules)
passes 23 of the 32 scenes. Only 9 scenes separate a personal trait from the
empty output: Q_question_premise_01_S1, 02_S1, 03_S1, 04_S1, 04_S3, 05_S1,
06_S1, 06_S2, 07_S1. Report per-person trait preservation on those 9 scenes as
the main metric and the overall scene pass rate only as a secondary figure.
(With the stricter scoring.scene_pass the empty output passes 16 of 32.)

Engine note. Facts such as lost_awareness, family_present, dark_observed and
pain_observed reach the engine only as observations. When they are missing,
person_walk picks among the possible branches with equal weight
(quality: unknown_branch_weighting = equal_distinct_supported_actions_not_calibrated)
and keeps that pick until its selection signature changes. Each summary (3)
states what this does to the walkers.

Overlap. 07 and 08 share the contrast axis 'observed continuation under
fatigue vs information gap' with disputed_fatigue_continuation (01-05 vs 06).
When disputed fragments are aggregated, count that axis once; both personas
carry an aggregation mark in their checks.
"""
from __future__ import annotations


def register(v):
    # 01. Short '네': the question's condition (lost) and ending (family arrives) are inherited.
    v.persona(
        'Q_question_premise_01', 'question_premise', ['webB:C48', 'corpusB:C09'],
        [{'label': '도담공원', 'place_type': 'park'}, {'label': '새솔상가', 'place_type': 'market'}],
        [(v.DEFAULT_INTRO, '도담공원이랑 새솔상가는 동네에 있는 곳이라 적었어요. 거기 꼭 가신다는 건 아니에요.'),
         ('밖에서 길을 잃으신 걸 알아차리시면, 가족이 올 때까지 그 자리에서 기다리시나요?', '네.'),
         ('평소에 혼자 걸으시는 건 어떠세요?', '동네 한 바퀴는 혼자서도 무리 없이 도세요.')],
        [v.spec('wait', 'lost_awareness and not family_present', ('N1',))],
        [v.case('trigger', v.scene(lost_awareness=True, family_present=False), ['wait'],
                '질문의 조건(길을 잃은 걸 앎)과 가족 부재가 모두 참이므로 대기한다.'),
         v.case('non_trigger', v.scene(lost_awareness=False), ['baseline'],
                '길을 잃었다는 질문 전제가 없으면 이 문답은 반응을 말하지 않는다.'),
         v.case('boundary_or_release', v.scene(lost_awareness=True, family_present=True), ['baseline'],
                '질문의 종료(가족이 옴)가 성립해 대기가 끝난다. 그 뒤 반응은 원문에 없다.'),
         v.case('unobserved_or_conflict', v.scene(lost_awareness=True, family_present=None), [],
                '가족이 곁에 있는지 모르므로 대기와 평소 이동을 모두 가능 분기로 남긴다.',
                status='unknown', possible=['baseline', 'wait'])],
        '(1) 논쟁 이유: 답이 "네." 한 마디라 조건(길을 잃은 걸 알아차림)과 종료(가족이 옴)가 질문에만 있다. '
        'D4에서 "가족이 없을 때 대기"를 "가족이 있을 때 대기"로 뒤집은 오류와 같은 유형이며, 답에 조건어가 없다는 이유로 '
        '조건 없는 대기나 규칙 없음으로 처리할 위험도 있다. '
        '(2) 기대 행동 근거: N1 질문 "가족이 올 때까지 그 자리에서 기다리시나요?" + 답 "네." -> 길을 잃은 걸 알고 가족이 '
        '곁에 없을 때 대기, 가족이 오면 종료. N2 "혼자서도 무리 없이 도세요"는 능력 서술이라 규칙 없음. '
        '(3) 엔진 지원: 지원(길 잃음 인지·가족 동석이 관찰 입력으로 주어질 때). 대기는 매 분 다시 판정되므로 가족 도착이 '
        '관찰 입력으로 들어오면 바로 끝난다. 관찰이 없으면 엔진은 [평소 이동, 대기] 두 분기를 같은 비중으로 고르고 '
        '선택 서명이 바뀌지 않는 한 유지하므로, 보행자의 약 절반이 시작 지점에서 끝까지 대기한다(분기 비중 미보정, '
        '기준선 쪽 제자리 전략 몫은 별도). '
        '근거 ID는 간접 근거(webB:C48 단일 사례의 홀로 서 있음, corpusB:C09는 대기 지시를 잊고 떠나는 반대 방향 사례).',
        ['S1 길 잃음 인지 + 가족 없음 -> wait (질문 조건 승계)',
         'S3 가족 도착 -> baseline (질문 종료 승계)',
         '조건을 family_present == True로 뒤집으면 S1·S3 모두 실패',
         'S4 가족 동석 미상 -> wait/baseline 가능 분기, 단정 금지'])

    # 02. The answer denies the 'lost' part of the premise: absence alone starts the wait.
    v.persona(
        'Q_question_premise_02', 'question_premise', ['corpusA:DM-05', 'corpusA:DM-03'],
        [{'label': '라온시장', 'place_type': 'market'}, {'label': '늘봄정류장', 'place_type': 'bus_stop'}],
        [(v.DEFAULT_INTRO, '라온시장은 장 보러 같이 가는 곳이고, 늘봄정류장은 집 앞 정류장이에요. 혼자 거기 가신 적은 없어요.'),
         ('길을 잃으셨다 싶으면 가족이 올 때까지 기다리시나요?',
          '기다리시긴 하는데, 길을 잃어서 그러시는 건 아니에요. 가족이 잠깐이라도 안 보이면 길을 알든 모르든 '
          '그 자리에 서서 저희 올 때까지 꼼짝 않으세요.')],
        [v.spec('wait', 'not family_present', ('N1',))],
        [v.case('trigger', v.scene(lost_awareness=False, family_present=False), ['wait'],
                '길을 알고 있어도 가족이 안 보이면 대기한다. 답이 질문의 길 잃음 전제를 부정했다.'),
         v.case('non_trigger', v.scene(lost_awareness=True, family_present=True), ['baseline'],
                '가족이 곁에 있으면 대기 반응의 시작 조건이 없다.'),
         v.case('boundary_or_release', v.scene(current_action='wait', family_present=True), ['baseline'],
                '가족이 오면 대기가 끝난다. 그 뒤 반응은 원문에 없다.'),
         v.case('unobserved_or_conflict', v.scene(family_present=None), [],
                '가족이 곁에 있는지 모르므로 대기와 평소 이동을 모두 가능 분기로 남긴다.',
                status='unknown', possible=['baseline', 'wait'])],
        '(1) 논쟁 이유: 질문은 "길을 잃으셨다 싶으면"을 전제했지만 답이 그 일부를 부정한다("길을 잃어서 그러시는 건 아니에요", '
        '"길을 알든 모르든"). 짧은 답처럼 질문 전제를 그대로 승계하면 조건이 지나치게 좁아진다. 또 시작 조건이 '
        '가족 부재(거짓 사실) 하나뿐이라, 부재 조건만으로 된 행동을 거절하는 검사가 있으면 이 특성이 사라진다. '
        '(2) 기대 행동 근거: N1.s2 "가족이 잠깐이라도 안 보이면 길을 알든 모르든 그 자리에 서서 저희 올 때까지 꼼짝 않으세요" '
        '-> 가족이 곁에 없을 때 대기, 가족이 오면 종료. 대기의 종료(가족이 옴)는 질문 전제와 답이 일치해 승계한다. '
        '(3) 엔진 지원: 지원(가족 부재가 관찰 입력으로 주어질 때). 엔진은 가족 동석을 관찰 입력으로만 채운다. 관찰이 없으면 '
        '[평소 이동, 대기] 두 분기를 같은 비중으로 골라 보행자의 약 절반이 시작 지점에서 끝까지 대기한다(분기 비중 미보정). '
        '실종 상황에서 가족 부재가 관찰 입력으로 들어오면 모든 보행자가 시작 지점에서 움직이지 않는다. 원문과는 맞지만 '
        '수색 범위 예측에 미치는 영향이 크므로, 실종 상황에서 가족 부재를 관찰로 넣을지는 별도 결정이 필요하다(검증 필요). '
        '근거 ID는 간접 근거(DM-05는 익숙한 얼굴이 없을 때의 반응이 시작된다는 점만 같고 방향은 반대, DM-03은 혼자 기다리던 상황).',
        ['S1 길을 알아도 가족 없음 -> wait (길 잃음 전제를 승계하지 않음)',
         'S2 가족 있음 -> baseline',
         '부재 조건만으로 된 대기를 거절하지 않는지',
         'S4 가족 동석 미상 -> wait/baseline 가능 분기'])

    # 03. '아니요' plus an alternative: absence starts movement to search for family.
    v.persona(
        'Q_question_premise_03', 'question_premise', ['corpusB:C09', 'corpusA:DM-05'],
        [{'label': '버들숲길', 'place_type': 'park'}, {'label': '해오름상가', 'place_type': 'market'}],
        [(v.DEFAULT_INTRO, '버들숲길은 예전에 같이 산책하던 길이고 해오름상가는 근처 상가예요. 요즘 거기 가자고 하신 적은 없어요.'),
         ('밖에서 길을 잃으시면 가족이 올 때까지 기다리시는 편인가요?',
          '아니요, 그럴 때 가만히 기다리시는 법이 없어요. 옆에 가족이 안 보이면 찾겠다고 바로 걸어 나서세요. '
          '걸으시면서 제 이름을 계속 부르세요.')],
        [v.spec('walk', 'lost_awareness and not family_present', ('N1',))],
        [v.case('trigger', v.scene(lost_awareness=True, family_present=False), ['walk'],
                '길을 잃었고 가족이 안 보이면 기다리지 않고 찾으러 걸어 나선다.'),
         v.case('non_trigger', v.scene(lost_awareness=False, family_present=True), ['baseline'],
                '길을 알고 가족도 곁에 있으면, "옆에 가족이 안 보이면"을 어느 쪽으로 읽어도 찾으러 나설 조건이 없다.'),
         v.case('boundary_or_release', v.scene(lost_awareness=True, family_present=True), ['baseline'],
                '가족이 곁에 있으면 찾으러 나설 조건이 없다. 그 뒤 반응은 원문에 없다.'),
         v.case('unobserved_or_conflict', v.scene(lost_awareness=True, family_present=None), [],
                '가족이 곁에 있는지 모르므로 걸어 나섬과 평소 이동을 모두 가능 분기로 남긴다.',
                status='unknown', possible=['baseline', 'walk'])],
        '(1) 논쟁 이유: "아니요"가 질문의 행동(대기)만 부정하고 상황(길을 잃음)은 유지한다. 대안 행동은 가족 부재로 시작되는 '
        '이동이다. "아니요"를 규칙 없음으로 처리하거나, 부재 조건으로 시작되는 행동을 거절하면 이 사람의 특성이 사라진다. '
        '"옆에 가족이 안 보이면"이 길 잃음과 무관한 일반 조건인지도 해석이 갈린다(참조는 "그럴 때"에 묶어 길 잃음 상황으로 한정). '
        '이 범위 논쟁은 장면 채점으로 확정하지 않는다. 길 잃음이 거짓인데 가족이 없는 장면, 길 잃음이 미상인데 가족이 없는 '
        '장면은 두 해석의 답이 갈리므로 넣지 않았고, 네 장면 모두 어느 해석에서도 같은 답이 나온다. 범위는 사람 검토 항목이다. '
        '(2) 기대 행동 근거: N1.s1 "그럴 때 가만히 기다리시는 법이 없어요" + N1.s2 "옆에 가족이 안 보이면 찾겠다고 바로 걸어 '
        '나서세요" -> 길을 잃었고 가족이 곁에 없을 때 걷기. '
        '(3) 엔진 지원: 의미 불완전. 걷기 규칙은 기록되지만 피로·통증 조건이 없어 일반 피로 휴식이 끼어들 수 있고(원문이 피로 '
        '무시를 말하지 않으므로 타당), 걸음은 기본 이동과 같아 "가족을 찾는" 방향은 표현되지 않는다. 관찰이 없으면 '
        '[평소 이동, 걷기]를 같은 비중으로 고르는데(분기 비중 미보정) 걷기 분기도 기본 이동이라, 위치 차이는 기준선 쪽 '
        '제자리 전략 몫에서만 생긴다. N1.s3 이름 부르기는 표현 불가(특성 손실 예상).',
        ['S1 길 잃음 + 가족 없음 -> walk (부재 조건 시작 행동을 거절하지 않음)',
         '"아니요"를 규칙 없음으로 처리하면 S1 실패',
         'S2 길을 앎 + 가족 있음 -> baseline (두 해석 모두 같음)',
         'S3 가족 있음 -> baseline',
         '"옆에 가족이 안 보이면"의 범위(길 잃음 한정 여부)는 채점하지 않고 사람 검토',
         'N1.s3 이름 부르기는 표현 불가로 보고되는지'],
        unsupported_sentences=('N1.s3',))

    # 04. '네' with an added ending: darkness ends the wait and starts walking.
    v.persona(
        'Q_question_premise_04', 'question_premise', ['webB:C56', 'webB:C26'],
        [{'label': '구름다리쉼터', 'place_type': 'park'}, {'label': '꽃담시장', 'place_type': 'market'}],
        [(v.DEFAULT_INTRO, '구름다리쉼터랑 꽃담시장은 제가 아는 곳이라 넣었어요. 어머니가 따로 찾으시는 데는 아니에요.'),
         ('길을 잃으신 걸 아시면 가족이 올 때까지 기다리시나요?',
          '네, 기다리세요. 그런데 날이 어두워지면 더는 못 기다리시고 일어나서 걸으세요.')],
        [v.spec('wait', 'lost_awareness and not family_present and not dark_observed', ('N1',)),
         v.spec('walk', 'lost_awareness and not family_present and dark_observed', ('N1',))],
        [v.case('trigger', v.scene(lost_awareness=True, family_present=False, dark_observed=False), ['wait'],
                '"네"로 질문의 조건과 종료를 승계한다. 아직 밝으면 가족을 기다린다.'),
         v.case('non_trigger', v.scene(lost_awareness=False, dark_observed=True), ['baseline'],
                '길을 잃지 않았다면 이 문답은 반응을 말하지 않는다. 어두워진 것만으로 걷기를 만들지 않는다.'),
         v.case('boundary_or_release', v.scene(lost_awareness=True, dark_observed=True), ['walk'],
                '답이 덧붙인 종료(어두워짐)로 대기가 끝나고, 가족이 없는 채로 일어나 걷는다.'),
         v.case('unobserved_or_conflict', v.scene(lost_awareness=True, dark_observed=None), [],
                '어두운지 모르므로 대기와 걷기를 모두 가능 분기로 남긴다.',
                status='unknown', possible=['wait', 'walk'])],
        '(1) 논쟁 이유: "네"는 질문 전제(길을 잃은 걸 앎, 가족이 올 때까지)를 받아들이지만, 답이 종료 조건을 하나 더 붙인다'
        '(어두워지면 더는 못 기다림). 질문의 종료만 승계하면 어두워진 뒤 반응을 잃고, 답의 종료만 쓰면 가족 부재 조건을 잃는다. '
        '어두워진 뒤 걷기도 가족 부재가 이어지는 상태에서 시작되는 행동이다. '
        '(2) 기대 행동 근거: N1.s1 "네, 기다리세요." -> 길 잃음 인지 + 가족 부재 + 밝을 때 대기. N1.s2 "날이 어두워지면 더는 못 '
        '기다리시고 일어나서 걸으세요" -> 같은 상황에서 어두우면 걷기. '
        '(3) 엔진 지원: 지원(어둠·길 잃음 인지·가족 동석이 관찰 입력으로 주어질 때). 대기는 매 분 다시 판정되어 어둠 관찰이 '
        '들어오면 걷기로 바뀐다. 걷기는 피로 조건이 없어 일반 피로 휴식이 끼어들 수 있다(원문이 피로 무시를 말하지 않으므로 '
        '타당). 관찰이 없으면 [평소 이동, 대기, 걷기] 세 분기를 같은 비중으로 골라, 어둠 관찰이 들어오기 전까지 보행자의 약 '
        '3분의 1이 시작 지점에서 대기한다. 밝음만 관찰되면 [평소 이동, 대기]로 다시 골라 약 절반이 대기한다(분기 비중 미보정). '
        '근거 ID는 간접 근거(해질녘·해 진 뒤 안절부절과 밖 방황).',
        ['S1 밝을 때 길 잃음 + 가족 없음 -> wait',
         'S3 어두워짐 -> walk (답이 덧붙인 종료와 이후 행동)',
         'S2 길 잃음 없이 어두움만 -> baseline',
         'S4 어둠 미상 -> wait/walk 가능 분기'])

    # 05. Place in the premise, '거기선 그러세요': the wait stays limited to that place.
    v.persona(
        'Q_question_premise_05', 'question_premise', ['webA:C08', 'corpusB:C11'],
        [{'label': '은행나무쉼터', 'place_type': 'park'}, {'label': '다솜시장', 'place_type': 'market'},
         {'label': '늘푸른정류장', 'place_type': 'bus_stop'}],
        [(v.DEFAULT_INTRO, '은행나무쉼터는 동네 쉼터고, 다솜시장이랑 늘푸른정류장은 근처에 있는 곳이라 적었어요. '
                           '셋 다 일부러 가자고 하시는 데는 아니에요.'),
         ('은행나무쉼터에서 길을 헷갈려하시면, 가족이 데리러 올 때까지 거기서 기다리시나요?', '네, 거기선 그러세요.'),
         ('다른 곳에서 길을 잃으셨을 때는요?', '다른 데서는 어떻게 하시는지 본 적이 없어요.')],
        [v.spec('wait', 'lost_awareness and not family_present', ('N1',), ('은행나무쉼터',))],
        [v.case('trigger', v.scene(lost_awareness=True, current_place_label='은행나무쉼터'), ['wait'],
                '질문의 장소·조건·종료를 "네, 거기선"으로 승계한다.'),
         v.case('non_trigger', v.scene(lost_awareness=True, current_place_label='다솜시장'), ['baseline'],
                '다른 장소의 반응은 본 적이 없다고 했으므로 대기를 넓히지 않는다.'),
         v.case('boundary_or_release',
                v.scene(lost_awareness=True, family_present=True, current_place_label='은행나무쉼터'), ['baseline'],
                '가족이 데리러 오면 대기가 끝난다. 그 뒤 반응은 원문에 없다.'),
         v.case('unobserved_or_conflict', v.scene(lost_awareness=True, current_place_label=None), [],
                '지금 그 쉼터에 있는지 모르므로 대기와 평소 이동을 모두 가능 분기로 남긴다.',
                status='unknown', possible=['baseline', 'wait'])],
        '(1) 논쟁 이유: 짧은 답 "네, 거기선 그러세요"가 질문의 장소(은행나무쉼터)·조건(길을 헷갈림)·종료(가족이 데리러 옴)를 '
        '함께 승계한다. 장소 한정을 빼고 모든 곳의 대기로 넓히거나, "거기선"을 무시하면 N2의 미관찰과 충돌한다. '
        '등록 장소 소개(N0)는 세 곳 모두 일부러 가는 곳이 아니라고 중립으로 두어, 장소 전제 승계와 무관한 상시 휴식·목적지 '
        '해석이 끼어들지 않게 했다. '
        '(2) 기대 행동 근거: N1 질문 + 답 "네, 거기선 그러세요." -> 은행나무쉼터에서 길을 잃은 걸 알고 가족이 없을 때 대기. '
        'N2 "다른 데서는 어떻게 하시는지 본 적이 없어요" -> 다른 장소는 정보 부족, 규칙 없음. '
        '(3) 엔진 지원: 지원(등록 장소 좌표 기준 60m 근접 판정, 길 잃음·가족 동석 관찰 입력 필요). 관찰이 없으면 은행나무쉼터 '
        '60m 안에 들어올 때마다 선택 서명이 바뀌어 [평소 이동, 대기]를 다시 고르므로, 들어온 보행자의 약 절반이 관찰이 바뀌지 '
        '않는 한 거기 머문다(분기 비중 미보정). 들어올 때마다 다시 고르기 때문에 머무는 보행자가 쌓여, 끌림 장소처럼 보행자가 '
        '모이는 효과가 생긴다. 원문은 그곳에 가려 한다는 뜻이 아니므로 이 모임 효과는 원문 이상의 의미다. '
        '근거 ID는 간접 근거(webA:C08 이동 정지 경향 일반, corpusB:C11 익숙한 환경에서도 길을 잃음; 장소 한정 대기 자체의 '
        '근거는 없음).',
        ['S1 쉼터에서 길 잃음 + 가족 없음 -> wait',
         'S2 다른 장소 -> baseline (장소 한정 유지)',
         'S3 가족 도착 -> baseline',
         'S4 현재 장소 미상 -> wait/baseline 가능 분기'])

    # 06. Rest while stopped: '기다리시다가 지쳐 보이시면 앉아서 쉬시나요?' -> '네'.
    v.persona(
        'Q_question_premise_06', 'question_premise', ['corpusA:DM-29', 'webA:C08', 'local:C17'],
        [{'label': '마루공원', 'place_type': 'park'}, {'label': '한올상가', 'place_type': 'market'}],
        [(v.DEFAULT_INTRO, '마루공원이랑 한올상가는 집에서 가까워서 적었어요. 특별한 의미는 없어요.'),
         ('길을 잃으신 걸 아시면 가족이 올 때까지 기다리시나요?', '네, 그 자리에 서서 기다리세요.'),
         ('그렇게 서서 기다리시다가 지쳐 보이시면 앉아서 쉬시나요?',
          '네, 근처 아무 데나 걸터앉으세요. 앉아서도 지나가는 사람한테 우리 딸 못 봤냐고 물어보세요.')],
        [v.spec('wait', 'lost_awareness and not family_present and (not fatigue_high or is_walking)', ('N1',)),
         v.spec('rest', 'lost_awareness and not family_present and fatigue_high and not is_walking', ('N2',))],
        [v.case('trigger', v.scene(current_action='wait', lost_awareness=True, fatigue_high=True), ['rest'],
                '서서 기다리는 중(걷지 않음)에 지치면 앉아 쉰다. 질문의 대기 맥락을 승계한다.'),
         v.case('non_trigger', v.scene(current_action='wait', lost_awareness=True, fatigue_high=False), ['wait'],
                '지치지 않았으면 계속 서서 기다린다.'),
         v.case('boundary_or_release',
                v.scene(current_action='wait', lost_awareness=True, family_present=True, fatigue_high=True),
                ['baseline'],
                '가족이 오면 대기 맥락이 끝나 대기도 대기 중 휴식도 적용되지 않는다. 그 뒤 반응은 원문에 없다.'),
         v.case('unobserved_or_conflict', v.scene(current_action='wait', lost_awareness=True, fatigue_high=None), [],
                '지쳤는지 모르므로 대기와 휴식을 모두 가능 분기로 남긴다.',
                status='unknown', possible=['rest', 'wait'])],
        '(1) 논쟁 이유: N2의 "네"는 질문의 맥락(서서 기다리는 중, 길을 잃음, 가족이 올 때까지)과 조건(지쳐 보임)을 승계한다. '
        '이 휴식은 걷다가 쉬는 반응이 아니라 정지·대기 중 휴식이므로, 모든 휴식에 보행 중 조건을 요구하는 검사가 있으면 이 '
        '특성이 사라진다. 대기와 휴식이 같은 상황에서 겹치므로 우선순위(지치면 휴식이 대기보다 앞섬)를 표현해야 한다. '
        '(2) 기대 행동 근거: N1 "네, 그 자리에 서서 기다리세요." -> 길 잃음 인지 + 가족 부재 시 대기. N2.s1 "근처 아무 데나 '
        '걸터앉으세요" -> 같은 대기 맥락에서 지쳤고 걷지 않을 때 휴식. 걷던 중 길을 잃은 걸 알면 먼저 멈춰 기다리는 것으로 '
        '참조를 짰다. '
        '(3) 엔진 지원: 의미 불완전. 정지 중 휴식은 멈춘 직후 이미 지쳐 있을 때(F 0.7 이상) 다음 재판정(1분 이내)에 '
        '한 번만 발동한다. 휴식이 끝나면 F에 회복 비율 0.4를 곱하므로, F가 1.75 이상이 아닌 한 피로 높음이 거짓이 되어 '
        '곧바로 대기로 돌아간다. 엔진은 대기 중 피로를 쌓지 않으므로 "기다리다 지침"은 표현 불가다. 대기와 휴식은 '
        '둘 다 정지라 위치 효과가 같고 차이는 피로 회복뿐이다. 길 잃음·가족 동석 관찰이 없으면 [평소 이동, 대기]를 같은 '
        '비중으로 골라 약 절반이 피로가 없는 상태에서 처음부터 대기하므로 휴식은 사실상 일어나지 않는다(분기 비중 미보정). '
        'N2.s2 지나가는 사람에게 묻기는 표현 불가(특성 손실 예상). '
        '근거 ID는 간접 근거(DM-29는 스스로 쉬지 않는 반대 사례, webA:C08 이동 정지, local:C17 길을 묻거나 가족에게 '
        '전화함(간접)).',
        ['S1 대기 중 + 지침 -> rest (정지 중 휴식을 거절하지 않음)',
         'S2 대기 중 + 지치지 않음 -> wait',
         '대기와 휴식이 동시에 참이 되면 우선순위 없이 unknown이 되어 실패',
         'S3 가족 도착 -> baseline (대기 맥락 종료)',
         'N2.s2 묻기는 표현 불가로 보고되는지'],
        unsupported_sentences=('N2.s2',))

    # 07. Short '네' inherits the question's fatigue-or-pain condition and the continued walking.
    v.persona(
        'Q_question_premise_07', 'question_premise', ['corpusA:DM-29', 'webB:C35'],
        [{'label': '갈대마을회관', 'place_type': 'community_center'}, {'label': '참나무길', 'place_type': 'park'}],
        [(v.DEFAULT_INTRO, '갈대마을회관은 노인정 다니시던 곳이고, 참나무길은 그 앞 산책길이에요. 요즘은 거기 안 다니세요.'),
         ('밖에서 오래 걸으시다가 다리 아프다고 하시거나 힘들어하셔도 그냥 계속 걸으시나요?',
          '네, 지난번에도 그러셨어요.')],
        [v.spec('walk', 'is_walking and (fatigue_high or pain_observed)', ('N1',))],
        [v.case('trigger', v.scene(fatigue_high=True), ['walk'],
                '"네"로 질문의 조건(걷다 힘들어함)과 행동(계속 걸음)을 승계한다. 지쳐도 계속 걷는다.'),
         v.case('non_trigger', v.scene(), ['baseline'],
                '지치지도 않고 통증 없음이 관찰된 평소 걸음은 이 문답의 개인 반응이 아니다.'),
         v.case('boundary_or_release', v.scene(current_action='rest', fatigue_high=True, pain_observed=True), ['baseline'],
                '이미 멈춰 앉아 있을 때 다시 일어난다는 근거는 없다. 질문과 답은 걷던 중의 이동 지속이다.'),
         v.case('unobserved_or_conflict', v.scene(fatigue_high=None), [],
                '지쳤는지 모르므로 이동 지속과 평소 이동을 모두 가능 분기로 남긴다.',
                status='unknown', possible=['baseline', 'walk'])],
        '(1) 논쟁 이유: 답이 "네, 지난번에도 그러셨어요." 뿐이라 조건(걷다 다리 아파하거나 힘들어함)과 행동(계속 걸음)이 '
        '질문에만 있다. "지난번에도"는 보호자가 그런 장면을 본 적이 있다는 뜻이므로 이동 지속의 관찰이다. 답에 행동어가 '
        '없다는 이유로 규칙 없음으로 처리하거나 "새 걷기 규칙을 만들지 않는다"로 처리하면, 이 사람을 일반 피로 휴식 가정으로 '
        '움직이게 되어 특성이 사라진다. 질문이 "아프다고 하시거나 힘들어하셔도"로 두 조건을 "거나"로 이었으므로 참조는 또는으로 '
        '둔다. 같은 대비 축(관찰된 이동 지속 대 정보 부족)을 disputed_fatigue_continuation 01~05가 다루므로, 묶음 집계 때 이 축은 '
        '한 번만 센다. 이 인물은 그 축을 짧은 답의 질문 전제 승계로 시험한다. '
        '(2) 기대 행동 근거: N1 질문 "다리 아프다고 하시거나 힘들어하셔도 그냥 계속 걸으시나요?" + 답 "네, 지난번에도 '
        '그러셨어요." -> 걷는 중 지치거나 아플 때 걷기. '
        '(3) 엔진 지원: 의미 불완전. 피로·통증 조건이 든 개인 걷기 규칙은 person_walk._explicit_physical_walk로 일반 피로 '
        '휴식보다 우선하지만, 실제 엔진에서는 세 가지가 원문과 어긋난다. 첫째, 통증은 관찰 입력으로만 들어오고 기본값이 '
        '미상이다. 그래서 관찰이 없으면 [평소 이동, 걷기] 두 분기가 생기고, 걷기 분기를 고른 보행자는 피로가 낮아도 통증 미상 '
        '조항 때문에 _explicit_physical_walk가 참이 되어 처음부터 일반 휴식을 전혀 하지 않는다. 휴식을 면제하는 것이 피로가 '
        '아니라 통증 미상이다. 둘째, 평소 이동 분기를 고른 보행자는 피로 높음 기준(F 0.7 이상)에 닿아야 보호가 켜지는데, 그 '
        '전에 일반 휴식이 끼어들 확률이 크다. 치매 피로 배수를 적용하고 분당 1회 추첨, 같은 지형 연속 보행을 가정해 계산하면 '
        '보도 약 75%, 기본 지형 약 40%, 계단 약 20%다(검토 계산과 몇 %p 차이는 추첨 시점 가정 차이). "힘들어도 안 쉰다"가 중간 '
        '피로 구간에서는 지켜지지 않는다. 셋째, F가 0.7을 넘으면 F는 휴식 때만 줄어들므로 그 뒤에는 끝까지 쉬지 않는 무한 '
        '지속이 된다. 원문은 언제까지 걷는지 말하지 않으므로 무한 지속은 원문 이상의 의미다. 또 S2는 통증 없음 관찰을 전제하지만 '
        '엔진 기본값은 미상이다. 보호가 시작되는 피로 구간을 어디에 둘지, 미상 통증 분기가 휴식을 면제하게 할지는 엔진 쪽 별도 '
        '결정 사항으로 남긴다.',
        ['S1 걷는 중 지침 -> walk (이동 지속을 표현 대상에서 빼지 않음)',
         '"네"에 행동어가 없다고 규칙 없음으로 처리하면 S1 실패',
         'S3 이미 멈춰 있음 -> baseline',
         'Q_question_premise_08(정보 부족)과 대비',
         '집계 표시: disputed_fatigue_continuation 01~05와 같은 대비 축(묶음 집계 때 중복 제외)'])

    # 08. Same fatigue premise, but '그런 모습은 못 봤어요': lack of information, not movement continuation.
    v.persona(
        'Q_question_premise_08', 'question_premise', ['corpusB:C20', 'corpusA:DM-42'],
        [{'label': '하늬공원', 'place_type': 'park'}, {'label': '미리내상가', 'place_type': 'market'}],
        [(v.DEFAULT_INTRO, '하늬공원이랑 미리내상가는 집 근처라서 적었어요. 아버지가 좋아하시는 곳인지는 잘 모르겠어요.'),
         ('밖에서 오래 걸으시다 힘들어하시면 좀 쉬었다 가시나요?',
          '글쎄요, 혼자 다니실 때라 그런 모습은 못 봤어요.'),
         ('요즘 걷는 건 어떠세요?', '동네는 아직 꽤 오래 걸으세요.')],
        [],
        [v.case('trigger', v.scene(fatigue_high=True), ['baseline'],
                '질문 전제 상황이지만 그때의 반응을 보지 못했다. 쉬기도 계속 걷기도 만들지 않는다.'),
         v.case('non_trigger', v.scene(), ['baseline'],
                '평소 걸음에는 개인 반응이 없다. "꽤 오래 걸으세요"는 능력 서술이다.'),
         v.case('boundary_or_release', v.scene(fatigue_high=True, pain_observed=True), ['baseline'],
                '통증까지 있어도 그때의 반응은 관찰되지 않았다.'),
         v.case('unobserved_or_conflict', v.scene(fatigue_high=None), ['baseline'],
                '개인 규칙이 없으므로 피로를 몰라도 평소 이동 가정이 그대로다.')],
        '(1) 논쟁 이유: 07과 같은 피로 전제의 질문에 "그런 모습은 못 봤어요"로 답했다. "그런 모습"은 질문의 전제(걷다 '
        '힘들어함)와 행동(쉬었다 감)을 가리키는 짧은 답이며, 혼자 다니실 때라 그 상황을 본 적이 없다는 정보 부족이다. 이동 '
        '지속의 관찰이 아니므로 걷기 규칙을 만들면 근거 없는 특성이 생기고, 쉰다고 단정해도 안 된다. 보호자가 앉혀 드린 '
        '경우는 DM-29와 같은 형태라 "스스로는 안 쉰다" 해석을 지지할 수 있어 신호가 섞이므로 이 인물에서 뺐다(별도 인물로 '
        '분리할 논쟁 장면, 이 파일에는 미포함). 같은 대비 축을 disputed_fatigue_continuation 06("그때 쉬는 모습은 못 '
        '봤어요")이 다루므로, 묶음 집계 때 이 축은 한 번만 센다. 이 인물은 그 축을 짧은 답의 질문 전제 지시로 시험한다. '
        '(2) 기대 행동 근거: N1 "글쎄요, 혼자 다니실 때라 그런 모습은 못 봤어요." -> 미관찰, 규칙 없음. '
        'N2 "꽤 오래 걸으세요"는 능력 서술이라 규칙 없음. '
        '(3) 엔진 지원: 지원(규칙 없음, 일반 휴식 가정 적용이 의도된 처리). '
        '근거 ID는 간접 근거(corpusB:C20 관찰하지 못한 시간대는 정보가 비어 있음, 원 응답자는 시설 직원; '
        'DM-42 보호자 평정의 신뢰도 한계).',
        ['S1 걷는 중 지침 -> baseline (못 봤다는 답으로 walk·rest를 만들지 않음)',
         'N2 능력 서술로 걷기 규칙을 만들지 않는지',
         'Q_question_premise_07(이동 지속 관찰)과 대비',
         '집계 표시: disputed_fatigue_continuation 06과 같은 대비 축(묶음 집계 때 중복 제외)'])

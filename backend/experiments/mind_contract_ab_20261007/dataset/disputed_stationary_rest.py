"""Disputed cases (draft, separate from dev128): stationary rest vs walking rest.

Topic: rest that starts while standing or waiting (current_action wait/rest),
contrasted with rest that starts while walking. dev128 answers are unchanged;
these personas are AI-authored drafts (draft_unreviewed) for human review
before any use as evidence. Each summary states (1) why the case is disputed,
(2) the source sentences behind the expected behavior, and (3) engine support:
지원 / 의미 불완전 (incl. partial support and cases that need an engine
decision) / 표현 불가, plus "엔진 도달 불가" when the contract can express a rule
that the engine's internal state can never trigger (an actual-behavior loss).

The authored reference is the contract-expressible reading. A scene must not
reward an output that drops a sourced trait: where the source means more than
the contract can say, the scene tests what the contract can carry (start,
release, scope) and the lost meaning is recorded instead of being scored.
unsupported_sentences lists sentences the contract cannot represent. Sentences
the contract represents but the engine cannot reach are written in the summary
and in an "엔진 메모" check line, not in unsupported_sentences.

Engine facts used in the summaries (app/phase2/person_walk.py): general fatigue
rest is drawn once per minute only in walking modes (can_rest) and is blocked by
a walk rule whose active branch names fatigue/pain/walking limits
(_explicit_physical_walk); fatigue accumulates only while walking and is
multiplied by 0.4 after a rest; fatigue_high cannot be set by an observation;
rest is held for its duration, wait is re-decided at least every minute.
These are read from the code; no engine run backs the summaries.
"""


def register(v):
    spec, scene, case = v.spec, v.scene, v.case

    # Q_01: sits on the spot when pain appears while waiting; stays seated
    # until the pain subsides. Walking pain response is unobserved.
    v.persona(
        'Q_stationary_rest_01', 'stationary_rest',
        ['webB:C42', 'corpusA:DM-29'],
        [{'label': '구름다리정류장', 'place_type': 'transit'},
         {'label': '은행골시장', 'place_type': 'market'}],
        [(v.DEFAULT_INTRO, '구름다리정류장은 병원 갈 때 버스 타던 곳이고, 은행골시장은 예전에 자주 장 보시던 데예요.'),
         ('몸이 불편해지시면 어떻게 하세요?',
          '버스를 기다리시거나 가게 앞에 서 계시다가 무릎이 아프다고 하시면 그 자리에 그냥 주저앉으세요. '
          '아픈 게 가라앉을 때까지는 일으켜 세워도 안 일어나세요.'),
         ('다른 때도 아프다고 하신 적이 있으세요?',
          '걸으실 때 아프다고 하신 건 못 들어 봤어요. 그래서 걷다가 아프시면 어떻게 하실지는 저도 모르겠어요.')],
        [spec('rest', 'not is_walking and pain_observed', ids=('N1',))],
        [case('trigger', scene(current_action='wait', pain_observed=True), ['rest'],
              '서서 기다리던 중 통증이 관찰되면 그 자리에 앉는다(N1.s1). 걷는 중 조건을 붙이지 않는다.'),
         case('non_trigger', scene(current_action='walk', pain_observed=True), ['baseline'],
              '걷는 중 통증 반응은 들어 본 적이 없다(N2). 정지 중 휴식을 보행 중으로 넓히지 않는다(장면 수준).'),
         case('boundary_or_release', scene(current_action='rest', pain_observed=True), ['rest'],
              '이미 앉아 있고 통증이 계속 관찰되면 앉은 채로 있다(N1.s2 가라앉을 때까지).'),
         case('unobserved_or_conflict', scene(current_action='wait', pain_observed=None), [],
              '서서 기다리는 중이지만 통증 여부가 관찰되지 않았다. 앉는다고 단정하지 않는다.',
              status='unknown', possible=['baseline', 'rest'])],
        '(1) 논쟁점: 서서 기다리던 중(걷는 중이 아님) 시작되는 휴식이다. D5 초안의 "모든 rest에 보행 중 조건" 검사라면 '
        '거절되거나 is_walking이 붙어 뜻이 바뀐다. 또 걷는 중 통증 반응은 미관찰(N2)이므로 이 휴식을 보행 중으로 넓히면 안 된다. '
        '(2) 근거 문장: N1.s1 "버스를 기다리시거나 가게 앞에 서 계시다가 무릎이 아프다고 하시면 그 자리에 그냥 주저앉으세요.", '
        'N1.s2 "아픈 게 가라앉을 때까지는 일으켜 세워도 안 일어나세요." N2는 보행 중 반응 정보 부족(규칙 없음). '
        '(3) 엔진(person_walk.py 코드 읽기 기준, 엔진 실행 미확인): 의미 불완전(반복이 원문 N1.s2와 일치). 정지 중 rest는 통증이 관찰되는 동안 기본 휴식 시간 단위로 반복되며, '
        '이 사람은 가라앉을 때까지 앉아 있으므로 반복 자체는 원문과 맞다. 통증은 외부 관찰로만 입력되고 없으면 분기로 남는다. '
        '단 이 정지 조건 휴식은 대기 중만이 아니라 걷다가 일반 피로 휴식에 들어간 상태(휴식 중, 걷는 중 아님)에서도 참이 된다. '
        '그래서 통증이 관찰된 채 걷던 경로는 첫 일반 휴식 뒤 통증 관찰이 끝날 때까지 계속 앉아 있게 된다. '
        'S2의 "보행으로 확대 금지"는 장면 수준에서만 성립하며, 엔진에서는 미관찰(N2)인 보행 중 통증 상황이 부분적으로 정지로 바뀐다(사람 검토 항목). '
        '연구 근거는 간접 근거(통증 등 신체 불편과 스스로 쉬지 않음에 관한 일반 서술이며 대기 중 앉음을 직접 다루지 않음).',
        ['S1 대기 중 통증 관찰 -> rest (보행 중 조건 없이)',
         'S2 보행 중 통증 -> baseline (정지 중 휴식을 보행 중으로 확대 금지, 장면 수준)',
         'S3 휴식 중 통증 지속 -> rest 유지',
         'S4 대기 중 통증 미관찰 -> unknown {baseline, rest}',
         '엔진 메모: 걷다가 일반 휴식에 들어간 뒤에도 통증이 관찰되면 이 규칙이 발동해 정지가 이어짐'])

    # Q_02: same contract rule as Q_01 but the source means a short sit, then
    # standing again even if pain persists. Place-limited observation.
    v.persona(
        'Q_stationary_rest_02', 'stationary_rest',
        ['corpusA:DM-03', 'webB:C42'],
        [{'label': '버들정류장', 'place_type': 'transit'},
         {'label': '개나리공원', 'place_type': 'park'}],
        [(v.DEFAULT_INTRO, '버들정류장은 복지관 가는 버스를 타시던 곳이에요. 개나리공원은 이름만 적은 거고 자주 가시진 않았어요.'),
         ('버들정류장에서 버스를 기다리실 때는 어떠세요?',
          '버들정류장에서 버스 기다리시다가 다리가 아프다고 하시면 의자에 한 오 분쯤 앉아 계세요. '
          '그러고는 아직 아프다고 하셔도 다시 일어나서 서서 기다리세요. 오래 앉아 계시는 걸 싫어하세요.'),
         ('다른 데서 기다리실 때도 그러세요?',
          '다른 데서 기다리시는 건 제가 본 적이 별로 없어서 잘 모르겠어요.')],
        [spec('rest', 'not is_walking and pain_observed', ids=('N1',), labels=('버들정류장',), hold=5)],
        [case('trigger', scene(current_action='wait', pain_observed=True, current_place_label='버들정류장'), ['rest'],
              '버들정류장에서 서서 기다리던 중 통증이 관찰되면 잠깐 앉는다(N1.s1).'),
         case('non_trigger', scene(current_action='wait', pain_observed=True), ['baseline'],
              '다른 곳에서 기다릴 때는 본 적이 없다(N2). 한 장소의 관찰을 다른 곳으로 넓히지 않는다.'),
         case('boundary_or_release',
              scene(current_action='rest', pain_observed=False, current_place_label='버들정류장'), ['baseline'],
              '버들정류장에서 앉아 있어도 통증이 관찰되지 않으면 이 사람의 개인 휴식 반응은 없다(해제). '
              '아파도 다시 일어나 서서 기다리는 특성(N1.s2, N1.s3)은 계약으로 표현할 수 없어 장면으로 채점하지 않고 특성 손실로 기록한다.'),
         case('unobserved_or_conflict',
              scene(current_action='wait', pain_observed=None, current_place_label='버들정류장'), [],
              '버들정류장에서 기다리는 중이지만 통증이 관찰되지 않았다.',
              status='unknown', possible=['baseline', 'rest'])],
        '(1) 논쟁점: Q_01과 같은 계약 규칙(정지 중, 통증, 휴식)으로 쓰이지만 원문 뜻은 "잠깐 앉았다가 아파도 다시 일어나 서서 기다림"이다. '
        '계약에는 이미 앉았던 적이 있는지, 지금 앉아 있는지 서서 기다리는지를 구분하는 사실이 없어 통증이 계속 관찰되면 휴식이 반복된다. '
        '그래서 장면은 원문이 뒷받침하고 계약이 담을 수 있는 것(대기 중 통증이면 앉음, 등록 장소 한정, 통증이 없으면 개인 휴식 없음)만 채점한다. '
        '"휴식 중 통증 지속 -> rest" 같은 장면은 원문 N1.s2가 부정하는 행동에 정답을 주므로 두지 않는다. '
        '원문에 맞추려고 rest와 wait를 같은 조건으로 함께 쓴 출력은 S1에서 unknown {rest, wait}, S4에서 unknown {baseline, rest, wait}가 된다. '
        '앉은 뒤에 서서 기다린다는 순서를 표현할 사실이 없기 때문이며, 이 출력을 S1·S4에서 어떻게 채점할지는 사람 검토 항목이다. '
        '장소는 버들정류장 관찰만 있고 다른 곳은 미관찰(N2). '
        '(2) 근거 문장: N1.s1 "버들정류장에서 버스 기다리시다가 다리가 아프다고 하시면 의자에 한 오 분쯤 앉아 계세요.", '
        'N1.s2 "그러고는 아직 아프다고 하셔도 다시 일어나서 서서 기다리세요.", N1.s3 "오래 앉아 계시는 걸 싫어하세요." '
        '(3) 엔진(person_walk.py 코드 읽기 기준, 엔진 실행 미확인): 의미 불완전. 휴식 지속시간은 실행되지만 끝난 뒤 통증이 계속 관찰되면 다시 rest가 선택된다. '
        'N1.s2와 N1.s3(아파도 다시 서서 기다림, 오래 앉지 않음)은 표현 불가로 특성 손실에 기록한다. 위치는 앉든 서든 정지라 같고, 피로 회복과 휴식/대기 기록이 달라진다. '
        '원문 지속시간(오 분)은 엔진 기본 휴식 시간과 같아 hold가 옮겨졌는지 엔진 행동으로도 구별되지 않으며, 장면 채점은 hold를 보지 않는다. '
        'Q_01과 같이 버들정류장 근처에서 걷다가 일반 휴식에 들어간 뒤에도 통증이 관찰되면 이 규칙이 발동한다. '
        '연구 근거는 간접 근거(혼자 기다리던 장소에서의 이탈, 통증 등 신체 불편에 관한 일반 서술).',
        ['S1 버들정류장 대기 중 통증 -> rest (hold는 장면에서 채점되지 않음; 원문 오 분은 엔진 기본 휴식 시간과 같아 엔진에서도 구별 불가)',
         'S2 등록 장소 밖 대기 중 통증 -> baseline (장소 한정 유지)',
         'S3 버들정류장 휴식 중 통증 없음 -> baseline (해제; 아파도 다시 일어남은 특성 손실로 기록, 채점 안 함)',
         'S4 버들정류장 대기 중 통증 미관찰 -> unknown {baseline, rest}',
         '사람 검토: rest와 wait를 함께 쓴 출력의 S1·S4 채점'],
        unsupported_sentences=('N1.s2', 'N1.s3'))

    # Q_03: walking rest (out of breath) and stationary rest (back pain) are
    # separate traits of one person; merging them changes the person.
    v.persona(
        'Q_stationary_rest_03', 'stationary_rest',
        ['corpusA:DM-29', 'webB:C42'],
        [{'label': '물푸레공원', 'place_type': 'park'},
         {'label': '새벽길상가', 'place_type': 'market'},
         {'label': '느릅나무정류장', 'place_type': 'transit'}],
        [(v.DEFAULT_INTRO, '물푸레공원은 운동 삼아 도시던 공원이고, 새벽길상가는 약국이 있는 상가예요. 느릅나무정류장은 그냥 집 앞 정류장이에요.'),
         ('밖에서 쉬시는 건 어떤 때예요?',
          '오래 걸으시면 숨이 차셔서 길가에 서서 잠깐 숨 돌리셨다가 다시 가세요.'),
         ('그 밖에 쉬시는 때가 또 있으세요?',
          '신호를 기다리거나 사람을 기다리느라 서 계실 때 허리가 아프다고 하시면 근처에 아무 데나 걸터앉으세요.')],
        [spec('rest', 'is_walking and fatigue_high', ids=('N1',)),
         spec('rest', 'not is_walking and pain_observed', ids=('N2',))],
        [case('trigger', scene(current_action='wait', pain_observed=True), ['rest'],
              '서서 기다리던 중 허리 통증이 관찰되면 걸터앉는다(N2.s1).'),
         case('non_trigger', scene(current_action='walk', pain_observed=True), ['baseline'],
              '걷는 중 통증 반응은 원문에 없다. 걷는 중 쉬는 것은 숨이 찰 때뿐이다(N1).'),
         case('boundary_or_release', scene(current_action='wait', fatigue_high=True), ['baseline'],
              '숨이 차서 쉬는 것은 걷던 중의 반응이다(N1). 이미 서 있는 상태에서 지친 것만으로 앉는다는 근거는 없다.'),
         case('unobserved_or_conflict', scene(current_action=None, pain_observed=True), [],
              '통증은 관찰됐지만 걷는 중인지 서 있는지 모른다. 서 있다면 앉고 걷는 중이면 개인 반응이 없다.',
              status='unknown', possible=['baseline', 'rest'])],
        '(1) 논쟁점: 한 사람 안에 걷다가 쉬는 휴식(N1, 숨이 참)과 서 있다가 앉는 휴식(N2, 허리 통증)이 따로 있다. '
        '하나의 "쉬는 사람" 특성으로 합치면 정지 중 피로(S3)나 보행 중 통증(S2)에도 쉬게 되어 사람이 바뀐다. '
        'N1의 "길가에 서서 숨 돌림"은 자세는 서 있지만 걷던 중에 시작되는 휴식이다. '
        '(2) 근거 문장: N1.s1 "오래 걸으시면 숨이 차셔서 길가에 서서 잠깐 숨 돌리셨다가 다시 가세요.", '
        'N2.s1 "신호를 기다리거나 사람을 기다리느라 서 계실 때 허리가 아프다고 하시면 근처에 아무 데나 걸터앉으세요." '
        '(3) 엔진(person_walk.py 코드 읽기 기준, 엔진 실행 미확인): N1은 지원(보행 중 rest, 지속시간 미기재라 엔진 기본값). 단 "오래 걸으시면 숨이 차셔서"를 피로 높음으로 옮긴 것은 해석이며 수치가 없다. '
        'N2는 의미 불완전(통증이 관찰되는 동안 rest 반복, 통증은 외부 관찰로만 입력). '
        '또 N2의 정지 조건 휴식은 걷다가 N1 휴식이나 일반 피로 휴식에 들어간 상태(걷는 중 아님)에서도 참이 된다. '
        '그래서 통증이 관찰된 채 걷던 경로는 첫 휴식 뒤 통증 관찰이 끝날 때까지 계속 앉아 있게 되며, S2의 "보행으로 확대 금지"는 장면 수준에서만 성립한다. '
        '연구 근거는 간접 근거(다리가 아파도 스스로 쉬지 않음, 통증 등 신체 불편에 관한 일반 서술).',
        ['S1 대기 중 통증 -> rest (정지 중 휴식)',
         'S2 보행 중 통증 -> baseline (정지 중 통증 휴식을 보행으로 확대 금지, 장면 수준)',
         'S3 대기 중 피로 -> baseline (보행 중 숨참 휴식을 정지로 확대 금지)',
         'S4 보행 여부 미상 + 통증 -> unknown {baseline, rest}',
         '엔진 메모: 걷다가 첫 휴식에 들어간 뒤 통증이 관찰되면 N2 규칙이 발동해 정지가 이어짐'])

    # Q_04: absence-triggered wait; while standing and waiting, sits when
    # tired. Seated posture continuation is not representable.
    v.persona(
        'Q_stationary_rest_04', 'stationary_rest',
        ['corpusA:DM-03', 'corpusB:C09'],
        [{'label': '해바라기시장', 'place_type': 'market'},
         {'label': '두레마을회관', 'place_type': 'other'}],
        [(v.DEFAULT_INTRO, '해바라기시장은 저랑 같이 장 보러 다니던 곳이고, 두레마을회관은 동네 어르신들 모이시는 곳이에요.'),
         ('같이 다니다가 가족이 안 보이면 어떻게 하세요?',
          '제가 곁에 없으면 어디 가지 않고 그 자리에 서서 저를 기다리세요.'),
         ('그렇게 기다리시다가 힘드시면요?',
          '서서 기다리시다가 힘드시면 계단이든 바닥이든 그 자리에 앉으세요. 앉아서도 계속 저를 기다리세요.')],
        [spec('wait', 'not family_present and (is_walking or not fatigue_high)', ids=('N1', 'N2')),
         spec('rest', 'not is_walking and not family_present and fatigue_high', ids=('N2',))],
        [case('trigger', scene(current_action='wait', family_present=False, fatigue_high=True), ['rest'],
              '가족이 곁에 없어 서서 기다리던 중 지치면 그 자리에 앉는다(N2.s1, 질문 전제 승계). '
              '이 정답은 조건을 나눈 우선순위에 기댄다(summary (c)).'),
         case('non_trigger', scene(current_action='wait', family_present=True, fatigue_high=True), ['baseline'],
              '가족이 곁에 있을 때의 반응은 원문에 없다. N2는 가족을 기다리는 상황을 전제로 한다.'),
         case('boundary_or_release', scene(current_action='wait', family_present=False, fatigue_high=False), ['wait'],
              '가족이 곁에 없어 서서 기다리는 중이고 지치지 않았으면 앉지 않고 그 자리에서 계속 서서 기다린다(N1.s1, N2.s1의 경계). '
              '대기 조건에 is_walking=참만 둔 출력은 대기를 시작하는 순간 꺼지므로 여기서 baseline이 되어 실패한다.'),
         case('unobserved_or_conflict', scene(current_action='walk', family_present=None, fatigue_high=True), [],
              '걷던 중이고 가족이 곁에 있는지 관찰되지 않았다. 가족이 없다면 지쳤더라도 먼저 그 자리에 서서 기다린다(N1.s1). '
              '가족이 있다면 개인 반응이 없다.',
              status='unknown', possible=['baseline', 'wait'])],
        '(1) 논쟁점: (a) 부재 조건으로 시작되는 대기(가족이 곁에 없을 때)이며 일괄 거절하면 안 된다. '
        '(b) N2는 질문 전제("그렇게 기다리시다가")를 승계해 가족을 기다리는 중에 앉는 반응이다. '
        '반면 N1의 질문 전제("같이 다니다가 가족이 안 보이면", 동행 중 분리)는 표현할 사실이 없어 규칙 "가족이 곁에 없음"이 혼자 집을 나선 경우를 포함한 가족 부재 전체로 넓어진다(의미 불완전, 사람 검토 항목). '
        '(c) 앉는 반응이 서서 기다리기를 대신한다는 우선순위를, 우선순위가 없는 현재 참조 형식(compile_note는 supersedes를 늘 비워 둠)에서는 '
        '대기 조건에 "걷는 중이거나 지치지 않음"을 넣는 조건 분할로 표현했다. 그래서 S1의 rest 정답은 이 조건 분할에 기댄다. '
        '우선순위 없이 두 규칙(대기: 가족 부재, 휴식: 정지 중이고 가족 부재이고 지침)으로 쓴 원문에 충실한 출력은 S1에서 unknown {rest, wait}가 된다(두 행동의 위치는 같음). '
        '근거 있는 우선순위(D5-08)가 생기기 전까지 S1을 어떻게 채점할지는 사람 검토 항목이다. '
        '참조 대기 규칙은 is_walking=참 분기를 가지므로 D4 검사(wait_cancels_itself_is_walking, 한 행이라도 is_walking=참을 요구하면 거절)에 걸린다. '
        '반대로 대기 조건을 "가족 부재이고 걷는 중"으로만 쓴 출력은 엔진에서 대기를 시작하는 순간 꺼져 매 분 걷기와 대기를 오가며 원문 N1.s1 "어디 가지 않고 그 자리에"와 반대가 된다. '
        'S3(지치지 않으면 계속 서서 기다림)가 이 출력을 가려낸다. S4는 걷던 중 가족이 없으면 지쳤어도 먼저 멈춰 서는지(N1)를 본다. '
        '(d) N2.s2의 앉은 자세 유지는 대기와 휴식 상태를 구분하는 사실이 없어 표현 불가다(피로가 줄면 서서 대기로 돌아감, 위치는 같음). '
        '(2) 근거 문장: N1.s1 "제가 곁에 없으면 어디 가지 않고 그 자리에 서서 저를 기다리세요.", '
        'N2.s1 "서서 기다리시다가 힘드시면 계단이든 바닥이든 그 자리에 앉으세요.", N2.s2 "앉아서도 계속 저를 기다리세요." '
        '(3) 엔진(person_walk.py 코드 읽기 기준, 엔진 실행 미확인): 대기는 의미 불완전. 동행 중 분리 전제가 빠져 가족 부재 전체로 넓어지고, 실종 상황에서는 출발 지점 정지로 이어진다. '
        '가족 관찰이 없으면 대기 규칙과 기본 행동의 분기가 생겨 약 절반의 걸음꾼이 출발 지점에서 대기를 시작하고, 대기 중에는 피로가 쌓이지 않아 끝나지 않는다. '
        'family_present=거짓이 관찰되면 전원이 출발 지점에서 대기한다(코드 추론, 엔진 실행으로 확인하지 않음). '
        '정지 중 휴식도 의미 불완전: 엔진은 정지 중 피로를 누적하지 않아 "서서 기다리다 지침"은 걷다가 지친 채 멈춘 경우에만 일어나고, '
        '휴식이 끝나 피로에 0.4를 곱해 줄면 서서 대기로 돌아간다. '
        '연구 근거는 간접 근거(기다리라던 장소에서의 이탈, 대기 지시를 잊고 보호자를 찾아 이동하는 대기 상황 일반 서술이며 이 사람과 반대 양상 포함).',
        ['S1 가족 부재 대기 중 피로 -> rest (조건 분할 우선순위에 기댐; 우선순위 없는 충실한 출력은 unknown {rest, wait}, 사람 검토 항목)',
         'S2 가족 동행 대기 중 피로 -> baseline (부재 조건 보존)',
         'S3 가족 부재 대기 중 피로 없음 -> wait (지치지 않으면 계속 서서 기다림; 걷는 중에만 참인 대기 규칙 판별)',
         'S4 가족 동행 미관찰 보행 중 피로 -> unknown {baseline, wait} (걷던 중이면 지쳤어도 먼저 멈춰 섬)',
         '사람 검토: N1 동행 중 분리 전제가 가족 부재 전체로 넓어짐(엔진에서 출발 지점 정지)'],
        unsupported_sentences=('N2.s2',))

    # Q_05: rest whose only condition is being stationary ("sits whenever
    # stopped"). Degenerate-branch checks reject it; in the engine it ends all
    # movement after the first stop. Needs an engine decision.
    v.persona(
        'Q_stationary_rest_05', 'stationary_rest',
        ['corpusA:DM-31', 'corpusA:DM-30'],
        [{'label': '도토리공원', 'place_type': 'park'},
         {'label': '장터골목', 'place_type': 'market'}],
        [(v.DEFAULT_INTRO, '도토리공원은 아파트 옆 작은 공원이고, 장터골목은 예전에 사시던 동네 골목이에요. 둘 다 요즘은 잘 안 가세요.'),
         ('밖에 계실 때 특별히 하시는 게 있어요?',
          '어디서든 걸음을 멈추시면 꼭 앉을 데부터 찾아서 앉으세요. 서서 계시는 모습은 거의 못 봤어요.'),
         ('쉬자고 하시는 편이에요?',
          '걷다가 쉬시는지는 제가 같이 오래 걸어 본 적이 없어서 잘 몰라요.')],
        [spec('rest', 'not is_walking', ids=('N1',))],
        [case('trigger', scene(current_action='wait'), ['rest'],
              '걸음을 멈춘 상태면 앉는다(N1.s1).'),
         case('non_trigger', scene(current_action='walk'), ['baseline'],
              '걷는 중 휴식은 관찰된 적이 없다(N2).'),
         case('boundary_or_release', scene(current_action='rest'), ['rest'],
              '장면 수준에서는 이미 앉아 있으면 앉은 채로 있다(원문 범위: 멈춘 상태면 앉아 있음). '
              '엔진에서 정지 상태가 조건을 계속 참으로 만들어 다시 걷지 않는 무한 반복은 원문 밖이다.'),
         case('unobserved_or_conflict', scene(current_action=None), [],
              '걷는 중인지 멈춘 상태인지 모른다.',
              status='unknown', possible=['baseline', 'rest'])],
        '(1) 논쟁점: 정지 상태 자체가 조건인 휴식(어디서든 멈추면 앉음)이다. 조건에 is_walking 말고 다른 사실이 없어 '
        '계약 D~D3의 degenerate_condition_only_is_walking, D4의 degenerate_branch_only_is_walking 검사에 걸린다. '
        'D4는 등록 장소 한정일 때만 허용하는데 원문은 "어디서든"이다. D5 수정 결정도 퇴화 분기는 계속 거절한다. '
        '원문 근거가 분명한 특성이므로 거절로 끝낼 것이 아니라 엔진 지원 여부를 따로 결정할 사례다. '
        '원문은 멈추면 앉는다는 뜻이며, 앉은 뒤 얼마 만에 일어나 다시 걷는지는 말하지 않는다(일어나는 조건 미기재). '
        '(2) 근거 문장: N1.s1 "어디서든 걸음을 멈추시면 꼭 앉을 데부터 찾아서 앉으세요.", N1.s2 "서서 계시는 모습은 거의 못 봤어요." '
        'N2는 보행 중 휴식 정보 부족(규칙 없음). '
        '(3) 엔진(person_walk.py 코드 읽기 기준, 엔진 실행 미확인): 엔진 결정 필요(의미 불완전보다 영향이 큼). 현재 엔진에 넣으면 첫 정지(일반 피로 휴식이나 staying_put 기본 대기) 이후 '
        '이 규칙이 매번 참이 되어 그 걸음꾼은 다시 걷지 않는다. 수색 분포가 "처음 멈춘 곳에서 영구 정지"로 바뀐다. '
        'D4·D5 거절과 특성 보존이 상충한다: 거절하면 "어디서든 멈추면 앉음"이 사라지고, 받아들이면 엔진에서 첫 정지 이후 이동이 끝난다. '
        '연구 근거는 간접 근거(스스로 멈춘 뒤 가만히 있음, 가까운 곳에서 멈춰 머묾에 관한 서술).',
        ['S1 대기(정지) -> rest',
         'S2 보행 -> baseline (보행 중 휴식 미관찰)',
         'S3 휴식 중 -> rest (장면 수준: 앉은 채로 있음; 엔진의 무한 반복은 원문 밖)',
         'S4 보행 여부 미상 -> unknown {baseline, rest}',
         '엔진 메모: 첫 정지 이후 이동이 끝남, D4·D5 퇴화 분기 거절과 특성 보존의 상충은 엔진 결정 항목'])

    # Q_06: walking rest on pain is observed; standing-pain response is not.
    # Do not generalize "rests when in pain" to the stationary state.
    v.persona(
        'Q_stationary_rest_06', 'stationary_rest',
        ['corpusA:DM-29', 'webB:C42'],
        [{'label': '갈대숲산책길', 'place_type': 'park'},
         {'label': '큰길시장', 'place_type': 'market'}],
        [(v.DEFAULT_INTRO, '갈대숲산책길은 저녁마다 걸으시던 길이고, 큰길시장은 가끔 들르시던 시장이에요.'),
         ('다리가 아프시면 어떻게 하세요?',
          '한참 걸으시다 다리가 아프다고 하시면 벤치든 턱이든 찾아서 앉아 쉬었다 가세요.'),
         ('다른 때는 어떠세요?',
          '가만히 서서 기다리실 때 앉으시는 건 본 적이 없어요. 그럴 때 아프다고 하신 적도 없어서 어떠실지는 모르겠어요.')],
        [spec('rest', 'is_walking and pain_observed', ids=('N1',))],
        [case('trigger', scene(current_action='walk', pain_observed=True), ['rest'],
              '걷던 중 다리 통증이 관찰되면 앉아 쉰다(N1.s1).'),
         case('non_trigger', scene(current_action='wait', pain_observed=True), ['baseline'],
              '서서 기다릴 때의 통증 반응은 관찰되지 않았다(N2). 보행 중 휴식을 정지 상태로 넓히지 않는다.'),
         case('boundary_or_release', scene(current_action='rest', pain_observed=True), ['baseline'],
              '걷다가 쉬는 반응은 걷던 중 시작된다. 이미 앉아 쉬는 상태에서 새로 시작되는 휴식이 아니며 쉬었다가 다시 간다(N1.s1).'),
         case('unobserved_or_conflict', scene(current_action='walk', pain_observed=None), [],
              '걷는 중이지만 통증이 관찰되지 않았다.',
              status='unknown', possible=['baseline', 'rest'])],
        '(1) 논쟁점: 걷다가 통증이 오면 앉아 쉬는 반응(N1)은 관찰됐지만 서서 기다릴 때의 통증 반응은 관찰되지 않았다(N2). '
        '"아프면 쉰다"를 정지 상태로 넓히면 관찰되지 않은 특성을 만든다. N2.s1 "앉으시는 건 본 적이 없어요"는 "앉지 않는다"는 관찰로도 읽힐 수 있으나, '
        'N2.s2가 그런 상황에서 통증 자체가 없었다고 하므로 정보 부족으로 본다. '
        '이 N2.s1 해석 논쟁은 어느 쪽으로 읽든 S2 정답이 baseline이라 현재 장면으로 판별되지 않으며 사람 검토 항목이다. '
        '(2) 근거 문장: N1.s1 "한참 걸으시다 다리가 아프다고 하시면 벤치든 턱이든 찾아서 앉아 쉬었다 가세요.", '
        'N2.s1 "가만히 서서 기다리실 때 앉으시는 건 본 적이 없어요.", N2.s2 "그럴 때 아프다고 하신 적도 없어서 어떠실지는 모르겠어요." '
        '(3) 엔진(person_walk.py 코드 읽기 기준, 엔진 실행 미확인): 의미 불완전. 엔진에서 통증 관찰은 휴식으로 끝나지 않는다. 휴식(지속시간 미기재라 엔진 기본값)이 끝나면 걷는 중이 아닌 상태라 기본 행동으로 걷고, '
        '다음 판단(1분 이내 또는 도로 구간 끝)에서 다시 rest가 선택된다. 그래서 통증이 관찰되는 동안 짧은 보행과 휴식이 반복되며 원문의 "쉬었다 가세요"와 다르다. '
        '"한참 걸으시다"라는 선행 조건은 수치가 없어 표현하지 않았다. 통증은 외부 관찰로만 입력된다. '
        '연구 근거는 간접 근거(다리가 아파도 스스로 쉬지 않음, 통증 등 신체 불편에 관한 일반 서술).',
        ['S1 보행 중 통증 -> rest',
         'S2 대기 중 통증 -> baseline (미관찰 정지 상태로 확대 금지; N2.s1 해석 논쟁은 이 장면으로 판별 안 됨)',
         'S3 휴식 중 통증 -> baseline (보행 중 휴식은 휴식 상태에서 새로 시작하지 않음)',
         'S4 보행 중 통증 미관찰 -> unknown {baseline, rest}',
         '엔진 메모: 통증 관찰 동안 짧은 보행과 기본 휴식이 반복됨, "한참 걸은 뒤" 조건 미표현'])

    # Q_07: stops and waits standing at dusk until picked up; sits only after
    # a long wait. The wait-duration trigger is not representable.
    v.persona(
        'Q_stationary_rest_07', 'stationary_rest',
        ['webA:C08', 'corpusA:DM-31'],
        [{'label': '달맞이공원', 'place_type': 'park'},
         {'label': '샘터마을슈퍼', 'place_type': 'market'}],
        [(v.DEFAULT_INTRO, '달맞이공원은 집 뒤 공원이고, 샘터마을슈퍼는 담배 사러 다니시던 가게예요.'),
         ('날이 어두워지면 어떻게 하세요?',
          '밖에 계시다 해가 지면 걷던 걸 멈추고 그 자리에 서서 제가 데리러 올 때까지 기다리세요.'),
         ('그렇게 기다리시다 보면요?',
          '서서 한참을 기다리시다 보면 그제야 길가 아무 데나 앉으세요. 처음부터 앉지는 않으세요.')],
        [spec('wait', 'dark_observed and not family_present', ids=('N1',))],
        [case('trigger', scene(current_action='walk', dark_observed=True), ['wait'],
              '밖에서 걷다가 어두워진 것이 관찰되면 멈춰 서서 기다린다(N1.s1).'),
         case('non_trigger', scene(current_action='walk', dark_observed=False), ['baseline'],
              '어둡지 않으면 개인 반응이 없다.'),
         case('boundary_or_release', scene(current_action='wait', dark_observed=True, family_present=True), ['baseline'],
              '어두워서 기다리던 중 가족이 데리러 온 것이 관찰되면 대기가 끝난다(N1.s1 "제가 데리러 올 때까지").'),
         case('unobserved_or_conflict', scene(current_action='walk', dark_observed=None), [],
              '걷는 중이지만 어두워졌는지 관찰되지 않았다. 시각으로 어두움을 추론하지 않는다.',
              status='unknown', possible=['baseline', 'wait'])],
        '(1) 논쟁점: 해가 지면 멈춰 서서 데리러 올 때까지 기다리는 반응(N1)은 표현되지만, 서서 한참 기다린 뒤에야 앉는 반응(N2.s1)은 대기 경과 시간 사실이 없고 '
        '엔진이 정지 중 피로를 누적하지 않아 표현할 수 없다. 기존 시험에 맞추려고 N2.s1을 "행동 아님"으로 지우지 않고 특성 손실로 기록한다 '
        '(위치는 정지로 같고 휴식에 따른 피로 회복과 기록만 달라짐). 이 손실은 장면으로 채점하지 않는다. '
        'N1의 "제가 데리러 올 때까지"는 끝나는 조건으로 가족 부재를 함께 넣었고 S3가 그 해제를 시험한다(끝나는 조건을 뺀 대기 규칙은 S3에서 실패). '
        'N2.s2 "처음부터 앉지는 않으세요"는 엔진에서 이미 보존된다: 대기 중에는 일반 피로 휴식이 일어나지 않고(보행 계열에서만 허용) 대기 규칙이 서 있기를 유지한다. '
        '(2) 근거 문장: N1.s1 "밖에 계시다 해가 지면 걷던 걸 멈추고 그 자리에 서서 제가 데리러 올 때까지 기다리세요.", '
        'N2.s1 "서서 한참을 기다리시다 보면 그제야 길가 아무 데나 앉으세요.", N2.s2 "처음부터 앉지는 않으세요." '
        '(3) 엔진(person_walk.py 코드 읽기 기준, 엔진 실행 미확인): N1은 지원(대기는 적어도 매 분 다시 판단되어 가족이 데리러 온 것이 관찰되면 다음 판단에서 끝난다. '
        '어두움과 가족 동행은 외부 관찰로만 입력되고 시각으로 추론하지 않으며, 가족 관찰이 없으면 대기와 기본 행동의 분기가 생긴다). '
        'N2.s1은 표현 불가. N2.s2는 엔진 대기 상태로 보존됨. '
        '연구 근거는 간접 근거(몇 시간 안에 이동을 멈춤, 스스로 멈춘 뒤 가만히 있음에 관한 서술).',
        ['S1 보행 중 어두움 관찰 -> wait',
         'S2 보행 중 어둡지 않음 -> baseline',
         'S3 어두움 대기 중 가족 도착 관찰 -> baseline (데리러 오면 대기 종료)',
         'S4 보행 중 어두움 미관찰 -> unknown {baseline, wait}',
         '엔진 메모: N2.s1(오래 기다린 뒤 앉음) 표현 불가, N2.s2(처음부터 앉지 않음)는 엔진 대기 상태로 보존'],
        unsupported_sentences=('N2.s1',))

    # Q_08: correction. Walking: keeps walking even when tired (observed
    # continuation). Sitting happens only when tired while standing/waiting;
    # that stationary rest is contract-expressible but engine-unreachable.
    v.persona(
        'Q_stationary_rest_08', 'stationary_rest',
        ['corpusA:DM-29', 'webB:C35'],
        [{'label': '민들레공원', 'place_type': 'park'},
         {'label': '오솔길시장', 'place_type': 'market'}],
        [(v.DEFAULT_INTRO, '민들레공원은 손주랑 가시던 공원이고, 오솔길시장은 예전 집 근처 시장이에요.'),
         ('앉아서 쉬시는 건 언제예요?',
          '걷다가 지치시면 앉아서 쉬세요.'),
         ('걸으실 때 얘기를 좀 더 해 주시겠어요?',
          '아까 말씀드린 건 제가 잘못 말했어요. 걸으실 때는 지치셔도 멈추지 않고 계속 걸으세요. '
          '앉으시는 건 신호나 차를 기다리느라 서 계시다가 지치셨을 때예요.')],
        [spec('walk', 'is_walking and fatigue_high', ids=('N2',)),
         spec('rest', 'not is_walking and fatigue_high', ids=('N2',))],
        [case('trigger', scene(current_action='wait', fatigue_high=True), ['rest'],
              '서서 기다리다 지치면 앉는다(N2.s3). 계약 수준 기대이며 엔진에서는 이 상태에 도달하지 않는다(summary (3)).'),
         case('non_trigger', scene(current_action='wait', fatigue_high=False), ['baseline'],
              '서서 기다려도 지치지 않았으면 개인 반응이 없다.'),
         case('boundary_or_release', scene(current_action='walk', fatigue_high=True), ['walk'],
              '정정된 원문(N2.s2): 걷는 중에는 지쳐도 멈추지 않고 계속 걷는다. 정정 전 문장(N1)의 걷다 쉬기를 따르지 않는다.'),
         case('unobserved_or_conflict', scene(current_action=None, fatigue_high=True), [],
              '지친 상태지만 걷는 중인지 서 있는지 모른다. 걷는 중이면 계속 걷고 서 있으면 앉는다.',
              status='unknown', possible=['rest', 'walk'])],
        '(1) 논쟁점: 정정 관계다. N1(걷다 지치면 앉아 쉼)은 N2.s1에서 잘못 말했다고 정정됐다. 정정 후 원문은 걷는 중에는 지쳐도 멈추지 않고 '
        '계속 걷고(관찰된 이동 지속), 앉는 것은 서서 기다리다 지쳤을 때다. "피곤해도 계속 걸음"을 규칙 없음으로 처리하거나 '
        '"모든 rest에 보행 중 조건"을 요구하면 정정 전 의미(걷다 쉼)나 일반 피로 휴식으로 되돌아간다. '
        '(2) 근거 문장: N2.s1 "아까 말씀드린 건 제가 잘못 말했어요.", N2.s2 "걸으실 때는 지치셔도 멈추지 않고 계속 걸으세요.", '
        'N2.s3 "앉으시는 건 신호나 차를 기다리느라 서 계시다가 지치셨을 때예요." N1은 정정된 문장(규칙 없음). '
        '(3) 엔진(person_walk.py 코드 읽기 기준, 엔진 실행 미확인): 걷기 규칙(N2.s2)은 부분 지원. 피로 조건이 든 개인 walk 규칙은 person_walk._explicit_physical_walk로 '
        'fatigue_high 구간(피로 0.7 이상)에서만 일반 피로 휴식보다 우선하고, 그 아래에서는 일반 휴식이 남는다. '
        '일반 휴식 확률은 피로 0에서 0.7 사이 분당 약 0.07~4.7%이며, 지형 계수 1과 0.5, 피로 배수 1을 가정하면 '
        '피로 0.7에 이르기 전 한 번 이상 쉬는 비율이 약 24~41%다(해석적 추정, 엔진 실행으로 검증하지 않음). '
        '원문 "지치셔도 멈추지 않고"가 피로 높음 이전의 일반 휴식까지 막는 뜻인지는 사람 검토 항목이다. '
        '정지 중 휴식(N2.s3)은 계약으로는 표현되지만 엔진에서 도달할 수 없다(실제 행동에서 특성 손실). '
        '이유: fatigue_high는 외부 관찰로 넣을 수 있는 사실이 아니다. 피로는 걷는 중에만 쌓인다. '
        '걷는 중 피로 0.7 이상이면 walk 규칙이 선택되어 일반 휴식이 막히고 기본 행동도 쓰이지 않아 멈출 계기가 없다. '
        '피로 0.7 미만에서 일반 휴식으로 멈추면 정지 상태여도 fatigue_high가 거짓이고, 휴식 뒤에는 피로에 0.4를 곱해 더 줄어든다. '
        '따라서 S1·S4의 rest는 계약 수준 기대이며 엔진 행동으로는 확인되지 않는다. '
        '계약으로 표현할 수 있는 문장이라 unsupported_sentences에는 넣지 않고 엔진 메모로 남긴다. '
        'S4는 보행 여부를 모를 때 rest와 walk 두 가능성이 상관된 채 남는지(기본 행동 없이) 본다. '
        '연구 근거는 간접 근거(다리가 아파도 스스로 쉬지 않음, 막힐 때까지 계속 이동).',
        ['S1 대기 중 피로 -> rest (계약 수준 기대)',
         'S2 대기 중 피로 없음 -> baseline',
         'S3 보행 중 피로 -> walk (정정 후 원문, fatigue_high 구간에서만 일반 피로 휴식보다 우선)',
         'S4 보행 여부 미상 + 피로 -> unknown {rest, walk}',
         '엔진 메모: N2.s3 정지 중 rest는 엔진에서 발동 불가(fatigue_high는 보행 중에만 쌓이고 외부 관찰 불가, 실제 행동에서 특성 손실)'])

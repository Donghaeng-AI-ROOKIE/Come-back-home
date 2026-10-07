"""Disputed cases (fatigue_continuation): observed continuation under fatigue/pain vs. information gap.

dev128과 분리된 별도 자료이다. 기존 시험의 정답(참조 정책·장면)은 바꾸지 않는다.
주제: 피로·통증 상황에서 관찰된 이동 지속("힘들어하시는데도 멈추지 않고 계속 걸으셨어요" ->
조건이 있는 walk 규칙)과 정보 부족("그때 쉬는 모습은 못 봤어요" -> 규칙 없음)의 대비, 일반 휴식 관찰.
01~05는 관찰된 이동 지속이 있고, 06~08은 대비군(정보 부족, 일반 휴식, 추측)이다.

AI 초안(draft_unreviewed)이며 사람 검토 전에는 근거로 쓰지 않는다. 장면 기대값은 참조 규칙이 같은
typed evaluator로 재현된다는 내부 일관성만 확인한 것이다. 한국어 원문 해석이나 연구 근거 대응이 맞다는
증거가 아니다. 각 summary에 (1) 논쟁 이유, (2) 기대 행동의 근거 문장, (3) 엔진 지원 여부(지원 / 의미
불완전 / 표현 불가)를 적는다.

원형 예시 문항과 변형 문항: 01(관찰된 이동 지속)과 06(정보 부족)은 사용자가 든 예시 문장을 거의 그대로
쓴 원형 예시 문항이다. 두 문장과 01의 "몰래 뒤따라가 본 적이 있는데"는 D5 조건 원칙 5(contract_d5.py
CONDITION_PRINCIPLES 5)의 "보호자가 직접 보았다면 / 쉬는 모습을 보지 못했다는 말뿐이면"에 1:1로 대응하므로,
이 두 문항 통과는 예시 재현 확인일 뿐 일반화 증거가 아니다. 같은 의미를 다른 표현으로 쓴 변형은 다음과 같다.
02(관찰 표지 없이 습관으로 말함), 03·04(다른 표현의 이동 지속), 05(녹화 영상, 간접 관찰), 07 N2(이동 능력
진술, "체력"이라는 말 없음), 08 N1.s1(표지가 약한 정보 부족).

엔진 소비 방식(2026-10-07 코드 확인, app/phase2/person_walk.py·gauges.py·schemas/environment.py):
- fatigue_high는 내부 피로 0.7 이상이다. 피로는 걷는 동안 늘기만 하고, 쉬기(개인 rest든 모집단 휴식이든)를
  마칠 때만 0.4배가 된다(BaselineRestPolicy.recovery_fraction). 피로 누적 배수는 유형 단위
  (gauges.fatigue_mult)이고 k_f 개인화는 금지 목록(gauges.DENIED_OVERRIDES)에 있다.
- anxiety_high는 관찰이 아니라 누적 잠재값이다(불안 = k_a1 x 혼란 + k_a2 x 혐오노출). 혼란·혐오노출은 걷는
  동안 늘기만 하고 쉬는 동안에도 줄지 않으므로 불안은 한 번 0.7을 넘으면 내려오지 않는다. 축 점수는 k_a1
  (누적 속도)만 바꾼다. 관찰(BehaviorObservation)로 넣을 수 있는 사실이 아니다.
- family_present, pain_observed는 관찰로만 채워지고, 관찰이 없으면 None(미정)이다. 미정이면 가능한 분기를
  나열해 하나를 무작위로 고르며, 선택은 선택 서명이 바뀔 때까지 유지된다. 실종 중이라고 가족 부재를 자동
  가정하지 않는다.
- 피로·통증(pain_observed 참)·보행 한계가 들어간 walk 규칙은 그 조건절이 거짓이 아닐 때 모집단 휴식보다
  우선한다(_explicit_physical_walk). 이런 walk가 피로 조건만으로 켜지면 피로가 줄 길이 없어 끝나지 않는다.
  그래서 "특성이 실제 행동에 보존되는가"를 볼 때 과잉 보존(무기한 이동 지속)도 점검 항목으로 둔다.
- 개인 rest의 hold가 원문에 없으면 엔진 기본 5분이다. 정지 중 rest는 조건이 참이거나 미정인 동안 hold가
  끝날 때마다 다시 선택될 수 있다.
- 엔진에는 신호등 같은 정지 계기가 없다. 보행자가 멈추는 길은 모집단 휴식, 개인 rest·wait, 제자리 대기 전략의
  기준선 대기뿐이다.
엔진 동작 수치는 Population._decide를 직접 부르고 사실·주변만 대체한 근사 탐침 결과다(평지 피로 0.03/분,
혼란 0.009/분, 보행자 400명, 240~300분). 실제 지도·게이지 실행 결과는 검증 필요다.

채점 장면은 단일 정답이다. 해석이 갈려 한쪽을 정답으로 고정하면 다른 해석이 무조건 실패하는 장면은 채점
장면에서 빼고 summary에 '채점 밖 검토 장면'으로 적는다(08). hold_minutes와 엔진 동작은 scene_pass가 비교하지
않으므로 checks의 해당 항목은 '장면 채점 밖 수동 확인'이다.
"""

FAMILY = 'fatigue_continuation'


def _intro(names):
    # Korean topic particle follows the final syllable (consonant -> 은, vowel -> 는).
    particle = '은' if (ord(names[-1]) - 0xAC00) % 28 else '는'
    return names + particle + ' 동네에 있어서 적어 둔 이름일 뿐이에요. 자주 가신다거나 좋아하신다는 뜻은 아니에요.'


def register(v):
    spec, scene, case = v.spec, v.scene, v.case

    # 01: observed continuation seen while the person believed they were alone (prototype item).
    v.persona(
        'Q_fatigue_continuation_01', FAMILY, ['corpusA:DM-29', 'corpusA:DM-14'],
        [{'label': '버들못공원', 'place_type': 'park'}, {'label': '도담골시장', 'place_type': 'market'}],
        [(v.DEFAULT_INTRO, _intro('버들못공원과 도담골시장')),
         ('밖에서 걷다가 지치시면 어떻게 하세요?',
          '몰래 뒤따라가 본 적이 있는데, 숨을 몰아쉬시고 힘들어하시는데도 멈추지 않고 계속 걸으셨어요. '
          '걸음만 많이 느려지셨고요.'),
         ('비 오는 날 밖에서는 어떠세요?', '비 오는 날 밖에 계신 걸 본 적은 없어요.')],
        [spec('walk', 'is_walking and fatigue_high', ids=('N1',))],
        [case('trigger', scene(fatigue_high=True), ['walk'],
              '보행 중 피로가 높으면 멈추지 않고 계속 걷는다(N1.s1, 직접 관찰).'),
         case('non_trigger', scene(fatigue_high=False), ['baseline'],
              '피로가 높지 않으면 이 사람 고유 반응이 기술되지 않았다.'),
         case('boundary_or_release', scene(fatigue_high=True, current_action='rest'), ['baseline'],
              '원문은 걷던 중의 지속만 말한다. 이미 멈춰 있을 때 다시 일어나 걷는지는 관찰되지 않았다.'),
         case('unobserved_or_conflict', scene(fatigue_high=None), [],
              '피로 여부를 모르면 계속 걷기와 기준선이 모두 가능하다.', status='unknown',
              possible=['baseline', 'walk'])],
        '(1) 논쟁점: "힘들어하시는데도 멈추지 않고 계속 걸으셨어요"를 휴식 정보 부족으로 읽으면 규칙이 없어지고, '
        '관찰된 이동 지속으로 읽으면 피로 조건 walk가 된다. 보호자가 뒤따라가며 직접 본 장면이고 동행이 쉬자고 '
        '권한 맥락이 아니므로 관찰된 이동 지속으로 둔다. 기존 정답이 이런 문장을 규칙 없음으로 둔 경우와 해석이 갈린다. '
        '원형 예시 문항: N1.s1은 사용자가 든 예시 문장을 거의 그대로 쓰고, "몰래 뒤따라가 본 적이 있는데"는 D5 조건 원칙 5의 '
        '"보호자가 직접 보았다면"에 1:1로 대응한다. 이 문항을 맞혀도 예시 재현 확인일 뿐 일반화 증거가 아니다. 같은 의미의 '
        '변형은 02(관찰 표지 없음)·03·04·05(녹화 영상)이다. '
        '(2) 근거 문장: N1.s1 "몰래 뒤따라가 본 적이 있는데, 숨을 몰아쉬시고 힘들어하시는데도 멈추지 않고 계속 걸으셨어요." '
        '→ walk, 조건 is_walking and fatigue_high. N1.s2 "걸음만 많이 느려지셨고요."는 속도 명령이 없어 특성 손실로 보존한다. '
        'N2는 미관찰. '
        '(3) 엔진 지원: walk = 지원(fatigue_high는 내부 게이지 사실이고, 피로 원자가 든 walk 규칙은 '
        'person_walk._explicit_physical_walk로 모집단 휴식보다 우선한다). 다만 종료 조건 없음: 피로는 걷는 동안 늘기만 하고 '
        '쉬어야 0.4배로 줄어드는데, 내부 피로가 0.7 이상이 된 뒤에는 이 walk가 모집단 휴식을 막으므로 시뮬레이션 끝까지 '
        '휴식이 없다. 원문은 관찰된 한 장면이고 언제 멈췄는지 말하지 않으므로, 무기한 지속이 원문 범위를 넘는지 사람 검토가 '
        '필요하다(과잉 보존 점검 대상). 피로 0.7 미만 구간에서는 모집단 휴식이 그대로 적용된다. 근사 탐침(검증 필요): '
        '피로가 높아진 뒤 쉰 보행자 0/400. 감속 = 표현 불가. '
        '연구 근거: DM-29(다리가 아파도 스스로 쉬지 않음)는 직접에 가깝고, DM-14(쉬지 않고 직진)는 속도 방향이 반대라 부분 근거.',
        ['S1 피로·보행 중 → walk 단독(쉬기 규칙을 만들면 실패)',
         'S2 피로 아님 → 개인 반응 없음',
         'S3 이미 멈춤 → walk 미발동(계속 걷기는 보행 중에만)',
         'S4 피로 미상 → 기준선/walk 분기 보존',
         'N1.s2 감속은 규칙으로 만들지 않고 특성 손실로 보존',
         '엔진 점검(장면 채점 밖 수동 확인): 과잉 보존 여부. 피로가 높아진 뒤 시뮬레이션 끝까지 휴식이 없는 것이 원문 범위를 '
         '넘는지 특성 보존 확인 항목으로 둔다'],
        unsupported_sentences=('N1.s2',))

    # 02: pain continuation while walking, but sits down once stopped.
    v.persona(
        'Q_fatigue_continuation_02', FAMILY, ['corpusA:DM-29', 'webB:C42', 'corpusA:DM-31'],
        [{'label': '물푸레쉼터', 'place_type': 'park'}, {'label': '가람골상가', 'place_type': 'market'}],
        [(v.DEFAULT_INTRO, _intro('물푸레쉼터와 가람골상가')),
         ('걷다가 몸이 아프시면 어떻게 하세요?',
          '무릎이 아프다고 하시면서도 쉬지 않고 계속 걸으세요. '
          '그런데 신호등 앞처럼 한번 멈춰 서시면 그 자리에 주저앉아 버리세요.')],
        [spec('walk', 'is_walking and pain_observed', ids=('N1',)),
         spec('rest', 'pain_observed and not is_walking', ids=('N1',))],
        [case('trigger', scene(pain_observed=True), ['walk'],
              '걷는 중 통증이 있어도 쉬지 않고 계속 걷는다(N1.s1).'),
         case('non_trigger', scene(pain_observed=False), ['baseline'],
              '통증이 없으면 기술된 반응이 없다.'),
         case('boundary_or_release', scene(pain_observed=True, current_action='wait'), ['rest'],
              '멈춰 선 상태에서 통증이 있으면 그 자리에 주저앉는다(N1.s2). 정지 중 휴식이다.'),
         case('unobserved_or_conflict', scene(pain_observed=None), [],
              '통증 관찰이 없으면 걷는 중 계속 걷기와 기준선이 모두 가능하다.', status='unknown',
              possible=['baseline', 'walk'])],
        '(1) 논쟁점: 같은 통증 상황에서 걷는 중에는 이동 지속, 멈춰 선 뒤에는 주저앉음이다. 모든 rest에 보행 중 조건을 '
        '요구하는 검사는 N1.s2를 거절하게 되고, 피로·통증 이동 지속을 버리는 처리는 N1.s1을 일반 휴식 가정으로 덮는다. '
        '두 반응을 보행 여부로 나눠 함께 보존해야 한다. 멈추게 된 원인(신호등)은 사실 목록에 없어 정지 상태로만 근사한다. '
        '관찰 표지 없는 변형 문항: "보았다"는 말 없이 습관으로 말한다(01 원형 대비). '
        '(2) 근거 문장: N1.s1 "무릎이 아프다고 하시면서도 쉬지 않고 계속 걸으세요." → walk, is_walking and pain_observed. '
        'N1.s2 "그런데 신호등 앞처럼 한번 멈춰 서시면 그 자리에 주저앉아 버리세요." → rest, pain_observed and not is_walking. '
        '(3) 엔진 지원: N1.s1 = 의미 불완전. 원문대로 walk 조건에 피로가 없어서, 통증이 관측되면 0분부터 '
        '_explicit_physical_walk가 참이 되어 관측이 유효한 동안 피로와 무관하게 모든 모집단 휴식이 막힌다(종료 없음). '
        '통증이 미관측(기본값)이면 pain_observed가 미정이라 walk와 기준선이 절반씩 분기한다. walk 분기도 조건이 거짓이 아니어서 '
        '모집단 휴식이 막힌다. '
        'N1.s2 = 통증 관측 시 표현 불가. 엔진에는 신호등 같은 정지 계기가 없고 walk가 휴식을 막아 보행자가 멈추지 않으므로 '
        'not is_walking에 도달하는 경로가 없다. 미관측 시에는 영구 정지 위험이 있다. 기준선 분기에서 한 번 멈추면(모집단 휴식, '
        '또는 제자리 대기 전략의 대기) rest와 기준선이 다시 분기한다. rest가 뽑히면 통증이 계속 미정이라 선택 서명이 바뀌지 '
        '않아, hold가 끝날 때마다 rest가 다시 선택되어 끝나지 않는다(정지 중 rest 반복의 극단형). '
        '근사 탐침(검증 필요, 300분): 통증 관측 시 400명 모두 한 번도 쉬지 않고 N1.s2 휴식 0회, 미관측 시 마지막 100분 내내 '
        '쉬는 보행자 121/400. '
        '연구 근거: DM-29(다리가 아파도 스스로 쉬지 않음) 직접, C42(통증과 배회) 보조, DM-31(스스로 멈춘 뒤 가만히 있음)은 '
        '정지 후 주저앉음에 대한 간접 근거.',
        ['S1 통증·보행 중 → walk 단독(rest 금지)',
         'S2 통증 없음 → 개인 반응 없음',
         'S3 통증·멈춰 섬 → rest(보행 중 조건이 없다는 이유로 거절하면 특성 손실)',
         'S4 통증 미상·보행 중 → 기준선/walk 분기 보존',
         '엔진 점검(장면 채점 밖 수동 확인): 통증 관측 시 엔진에서 N1.s2 도달 경로 없음(표현 불가). 미관측 시 rest 분기가 '
         '영구 정지로 이어지는지 확인'])

    # 03: earlier "rests when tired" corrected; continuation until a walking limit.
    v.persona(
        'Q_fatigue_continuation_03', FAMILY, ['corpusA:DM-29', 'corpusA:DM-27'],
        [{'label': '느루공원', 'place_type': 'park'}, {'label': '다솜상가', 'place_type': 'market'},
         {'label': '옛 우물터', 'place_type': 'other'}],
        [(v.DEFAULT_INTRO, _intro('느루공원, 다솜상가, 옛 우물터')),
         ('걷다가 지치시면 쉬시나요?', '네, 지치시면 알아서 쉬세요.'),
         ('앞에서 지치시면 쉬신다고 하셨는데, 요즘도 그러세요?',
          '아, 그건 예전 얘기예요. 요즘은 기운이 빠져 보이셔도 발걸음을 안 멈추세요. '
          '그러다 사십 분쯤 쉬지 않고 걸으시면 다리가 풀려서 결국 주저앉으세요.')],
        [spec('walk', 'is_walking and fatigue_high and continuous_walk_minutes < 40', ids=('N2',)),
         spec('rest', 'is_walking and continuous_walk_minutes >= 40', ids=('N2',))],
        [case('trigger', scene(fatigue_high=True, continuous_walk_minutes=15), ['walk'],
              '정정 후 현재 행동: 기운이 빠져 보여도 계속 걷는다(N2.s2). 정정 전 N1의 휴식은 쓰지 않는다.'),
         case('non_trigger', scene(fatigue_high=False, continuous_walk_minutes=15), ['baseline'],
              '피로가 높지 않고 걷기 한계 전이면 기술된 반응이 없다.'),
         case('boundary_or_release', scene(fatigue_high=True, continuous_walk_minutes=40), ['rest'],
              '사십 분쯤 쉬지 않고 걸으면 피로 여부와 무관하게 주저앉는다(N2.s3). 이동 지속이 끝나는 경계다.'),
         case('unobserved_or_conflict', scene(fatigue_high=None, continuous_walk_minutes=15), [],
              '피로 여부를 모르면 계속 걷기와 기준선이 모두 가능하다.', status='unknown',
              possible=['baseline', 'walk'])],
        '(1) 논쟁점: N1 "지치시면 알아서 쉬세요"가 N2에서 "예전 얘기"로 정정된다. 정정 관계를 놓치면 피로 휴식과 피로 이동 지속이 '
        '충돌하거나, 휴식만 남아 이 사람을 일반 피로 휴식으로 움직이게 된다. 또 한 문답 안에 이동 지속(피로)과 보행 한계 휴식'
        '(연속 보행 한계)이 함께 있어 두 조건을 나눠야 한다. N2 질문의 전제("앞에서 지치시면 쉬신다고 하셨는데")를 답이 부정하는 형태다. '
        '변형 문항: 이동 지속을 01 원형과 다른 표현("기운이 빠져 보이셔도 발걸음을 안 멈추세요")으로 쓴다. N2.s3는 처음 초안의 '
        '"꼭 앉으셔야 해요"가 본인이 실제로 앉는다는 뜻인지 보호자가 판단한 필요인지 모호해서, 행동이 드러나는 '
        '"결국 주저앉으세요"로 고쳤다. '
        '(2) 근거 문장: N2.s2 "요즘은 기운이 빠져 보이셔도 발걸음을 안 멈추세요." → walk, is_walking and fatigue_high and '
        'continuous_walk_minutes < 40. N2.s3 "그러다 사십 분쯤 쉬지 않고 걸으시면 다리가 풀려서 결국 주저앉으세요." → rest, '
        'is_walking and continuous_walk_minutes >= 40. N1은 정정된 정보로 실행하지 않는다. "사십 분쯤"을 40 경계로 두는 것은 실행 가정이다. '
        '(3) 엔진 지원: 지원. fatigue_high·continuous_walk_minutes는 내부 사실이다. 40분 전 구간에서 피로가 높으면 walk가 모집단 '
        '휴식을 막고, 이 이동 지속의 종료는 사십 분 rest가 맡는다(원문이 말한 한계 안이라 01과 달리 무기한 지속이 아니다). '
        '40분부터 개인 rest가 발동하고, rest가 끝나면 연속 보행 카운터가 0, 피로가 0.4배로 돌아가 주기가 재현된다. '
        'hold는 원문에 없어 엔진 기본 5분(의미 불완전 소지). '
        '연구 근거: DM-29 직접, DM-27(하지 근력 저하)은 보행 한계 휴식에 대한 간접 근거.',
        ['S1 피로·사십 분 전 → walk 단독(정정 전 N1로 rest를 만들면 실패)',
         'S2 피로 아님·한계 전 → 개인 반응 없음',
         'S3 사십 분 도달 → rest 단독(walk와 겹치면 실패)',
         'S4 피로 미상 → 기준선/walk 분기 보존',
         'N1은 정정 관계로 비실행'])

    # 04: ordinary rest vs. continuation when anxious, in the same person.
    v.persona(
        'Q_fatigue_continuation_04', FAMILY, ['corpusA:DM-29', 'corpusA:DM-41', 'webB:C41'],
        [{'label': '가온쉼터', 'place_type': 'park'}, {'label': '솔바람마당', 'place_type': 'park'}],
        [(v.DEFAULT_INTRO, _intro('가온쉼터와 솔바람마당')),
         ('밖에서 지치시면 어떻게 하세요?',
          '보통 산책할 때는 힘드시면 벤치에 앉아 쉬었다 가세요. '
          '그런데 안절부절못하고 불안해하실 때는 지쳐 보여도 앉지를 않으시고 이리저리 걸어 다니세요.')],
        [spec('rest', 'is_walking and fatigue_high and not anxiety_high', ids=('N1',)),
         spec('walk', 'is_walking and fatigue_high and anxiety_high', ids=('N1',))],
        [case('trigger', scene(fatigue_high=True, anxiety_high=True), ['walk'],
              '불안이 높을 때는 지쳐도 계속 걷는다(N1.s2).'),
         case('non_trigger', scene(fatigue_high=False, anxiety_high=True), ['baseline'],
              '피로가 높지 않으면 불안만으로 기술된 반응이 없다.'),
         case('boundary_or_release', scene(fatigue_high=True, anxiety_high=False), ['rest'],
              '불안하지 않은 평소에는 지치면 앉아 쉰다(N1.s1). "불안이 풀리면 이동 지속이 끝난다"는 규칙 수준의 설명이고, '
              '엔진에서는 불안이 누적 잠재값이라 풀림이 재현되지 않는다.'),
         case('unobserved_or_conflict', scene(fatigue_high=True, anxiety_high=None), [],
              '불안 여부를 모르면 쉬기와 계속 걷기가 모두 가능하다.', status='unknown',
              possible=['rest', 'walk'])],
        '(1) 논쟁점: 한 사람 안에 일반 휴식 관찰과 이동 지속 관찰이 같이 있다. 휴식 문장만 규칙화하면 불안할 때의 이동 지속을 잃고, '
        '두 문장을 조건 없이 나란히 두면 피로 때마다 충돌한다. "보통 산책할 때"를 불안이 높지 않은 상태로 읽는 것은 해석이며 검토가 필요하다. '
        '변형 문항: 이동 지속을 "앉지를 않으시고 이리저리 걸어 다니세요"로 쓴다. '
        '(2) 근거 문장: N1.s1 "보통 산책할 때는 힘드시면 벤치에 앉아 쉬었다 가세요." → rest, is_walking and fatigue_high and not anxiety_high. '
        'N1.s2 "그런데 안절부절못하고 불안해하실 때는 지쳐 보여도 앉지를 않으시고 이리저리 걸어 다니세요." → walk, '
        'is_walking and fatigue_high and anxiety_high. 벤치를 찾는 부분은 장소 유형이 없어 휴식으로만 남는다. '
        '(3) 엔진 지원: 의미 불완전. 지원하는 부분: 불안 임계 전에는 피로 시 개인 rest, 임계 후에는 walk가 '
        '_explicit_physical_walk로 모집단 휴식보다 우선한다. 불완전한 이유: 엔진의 anxiety_high는 관찰이 아니라 시간과 함께 '
        '누적되는 잠재값이다(불안 = k_a1 x 혼란 + k_a2 x 혐오노출, person_walk.facts). 혼란·혐오노출은 걷는 동안 늘기만 하고 '
        '쉬는 동안에도 줄지 않으므로(gauges.step, _advance) 한 번 임계 0.7을 넘으면 풀리지 않고, 그 뒤로는 지쳐도 계속 걷는 '
        '쪽으로 고정된다. 이 경우 N1.s1의 일반 휴식은 돌아오지 않고, 피로 0.7 이상 구간의 휴식이 사라진다. 또 보호자가 본 '
        '"안절부절못함"(관찰)을 시간 누적값으로 근사하는 것이며, anxiety_high는 관찰로 넣을 수 있는 사실이 아니다. 축 점수는 '
        'k_a1 누적 속도만 바꾼다. 근사 탐침(검증 필요, 300분): 400명의 휴식 분 합계가 불안 임계(약 130분) 전 16750분, '
        '이후 365분. 휴식 hold는 원문에 없어 기본 5분. '
        '연구 근거: DM-29(쉬지 않음) 직접, DM-41·C41(불안해서 여기저기 걸어 다님)은 불안 조건에 대한 근거.',
        ['S1 피로·불안 → walk 단독',
         'S2 피로 아님 → 개인 반응 없음(불안만으로 walk 금지)',
         'S3 피로·불안 아님 → rest 단독',
         'S4 불안 미상 → rest/walk 분기 보존',
         '엔진 점검(장면 채점 밖 수동 확인): 불안 임계 이후 피로 휴식이 돌아오지 않는 것(풀림 미재현)이 이 사람의 특성을 '
         '왜곡하는지 확인'])

    # 05: continuation that starts with an absence condition; rest once family arrives.
    v.persona(
        'Q_fatigue_continuation_05', FAMILY, ['corpusA:DM-29', 'corpusA:DM-05'],
        [{'label': '윗말공원', 'place_type': 'park'}, {'label': '한울상가', 'place_type': 'market'}],
        [(v.DEFAULT_INTRO, _intro('윗말공원과 한울상가')),
         ('혼자 계실 때 지치시면 어떻게 하시던가요?',
          '가게 방범 카메라에 찍힌 걸 봤는데, 저희가 옆에 없으니까 지친 얼굴로도 걸음을 멈추질 않으셨어요.'),
         ('찾으러 가셨을 때는 어떠셨어요?', '제가 가서 팔을 잡아 드리니까 그제야 그 자리에 주저앉아 쉬셨어요.')],
        [spec('walk', 'is_walking and fatigue_high and not family_present', ids=('N1',)),
         spec('rest', 'fatigue_high and family_present', ids=('N2',))],
        [case('trigger', scene(fatigue_high=True, family_present=False), ['walk'],
              '가족이 곁에 없을 때 지쳐도 계속 걷는다(N1).'),
         case('non_trigger', scene(fatigue_high=False, family_present=False), ['baseline'],
              '피로가 높지 않으면 기술된 반응이 없다.'),
         case('boundary_or_release', scene(fatigue_high=True, family_present=True), ['rest'],
              '가족이 오면 이동 지속이 끝나고 그 자리에 주저앉아 쉰다(N2).'),
         case('unobserved_or_conflict', scene(fatigue_high=True, family_present=None), [],
              '가족이 곁에 있는지 모르면 계속 걷기와 쉬기가 모두 가능하다.', status='unknown',
              possible=['rest', 'walk'])],
        '(1) 논쟁점: 이동 지속이 "저희가 옆에 없으니까"라는 부재 조건으로 시작된다. 부재 조건을 거절하거나 '
        '"가족이 있을 때"로 뒤집으면(D4 실패 유형) 반응이 사라지거나 반대가 된다. 또 녹화 영상으로 본 장면이라 관찰 맥락이 '
        '단독이다(변형 문항: 간접 관찰 표지). 원인 절 "저희가 옆에 없으니까"는 영상에서 본 것이 아니라 보호자의 추론이다. 영상으로 '
        '본 것은 혼자 지친 얼굴로 걸음을 멈추지 않은 모습뿐이다. 이를 조건으로 볼지 단순 맥락으로 볼지는 검토가 필요하다(여기서는 '
        '원문이 이유로 말했으므로 조건). N2는 발견 시점의 반응이다. 06의 "찾았을 때는 의자에 앉아 계셨다"는 계기가 관찰되지 않은 '
        '발견 상태라 규칙을 만들지 않지만, N2는 관찰된 계기(팔을 잡아 드림)와 그에 이어진 반응(그제야 주저앉음)이 있어 규칙화했다. '
        '(2) 근거 문장: N1 "가게 방범 카메라에 찍힌 걸 봤는데, 저희가 옆에 없으니까 지친 얼굴로도 걸음을 멈추질 않으셨어요." '
        '→ walk, is_walking and fatigue_high and not family_present. N2 "제가 가서 팔을 잡아 드리니까 그제야 그 자리에 주저앉아 쉬셨어요." '
        '→ rest, fatigue_high and family_present. '
        '(3) 엔진 지원: 의미 불완전. 실종 상황에서는 가족 부재가 사실상 기본값인데, 엔진은 family_present를 관찰 주입 전용으로 '
        '두어 기본이 미상이다. 그래서 피로가 높아지면 부재 walk와 발견 시 rest가 절반씩 분기한다. 즉 부재 walk는 절반만 발동하고, '
        '발견 시점 반응인 N2 휴식이 수색 중 절반에 섞여 들어온다. rest 분기는 가족이 곁에 있고 피로가 높은 동안 반복되는 것이 '
        '아니다. 5분 휴식 뒤 피로가 0.4배가 되어 조건이 풀리므로 피로 회복 뒤 보통 1회로 끝나고, 휴식 직전 피로가 1.75 이상일 '
        '때만 이어서 반복된다. walk 분기가 뽑히거나 가족 없음이 관찰로 주입되면 종료 조건이 없다. 피로가 높아진 뒤 시뮬레이션 끝까지 '
        '휴식이 없으며(01과 같음), 원문 범위를 넘는지 검토가 필요하다. 근사 탐침(검증 필요): 피로가 높아진 뒤 끝까지 쉬지 않은 '
        '보행자가 미관측 시 189/400, 가족 없음 주입 시 400/400. '
        '연구 근거: DM-29(스스로 쉬지 않아 보호자가 앉혀 쉬게 함) 직접, DM-05(익숙한 사람이 안 보이면 찾으러 나섬)는 부재 조건에 대한 간접 근거.',
        ['S1 피로·가족 없음 → walk 단독(부재 조건 뒤집기 금지)',
         'S2 피로 아님 → 개인 반응 없음',
         'S3 피로·가족 옴 → rest 단독',
         'S4 가족 여부 미상 → rest/walk 분기 보존',
         '엔진 점검(장면 채점 밖 수동 확인): 가족 여부 미관측 시 발견 시 휴식(N2)이 수색 중에 섞이는지, 가족 없음 관찰 시 '
         '무기한 이동 지속(과잉 보존)이 원문 범위를 넘는지 확인'])

    # 06: information gap (rest not seen) + found seated is not a rest rule (prototype item).
    v.persona(
        'Q_fatigue_continuation_06', FAMILY, ['corpusB:C20', 'webB:C39'],
        [{'label': '새터공원', 'place_type': 'park'}, {'label': '여울쉼터', 'place_type': 'park'}],
        [(v.DEFAULT_INTRO, _intro('새터공원과 여울쉼터')),
         ('밖에서 오래 걸으시면 지쳐서 쉬시나요?',
          '혼자 나가셨던 날이라 그때 쉬는 모습은 못 봤어요. '
          '찾았을 때는 정류장 의자에 앉아 계셨는데, 언제부터 앉아 계셨는지는 몰라요.'),
         ('사람 많은 곳에서는 어떠세요?', '시장 골목에 사람이 북적이면 들어가시다가도 돌아 나오세요.')],
        [spec('avoid_market', 'market.crowded', ids=('N2',))],
        [case('trigger', v.nearby('market', crowded=True), ['avoid_market'],
              '붐비는 시장 근처에서는 돌아 나온다(N2).'),
         case('non_trigger', scene(fatigue_high=True, continuous_walk_minutes=50), ['baseline'],
              '피로 상황의 반응은 관찰되지 않았다(N1.s1). 계속 걷기도 쉬기도 개인 규칙으로 만들지 않는다.'),
         case('boundary_or_release', v.nearby('market', crowded=False), ['baseline'],
              '시장이 붐비지 않으면 회피 조건이 풀린다.'),
         case('unobserved_or_conflict', scene(fatigue_high=None), ['baseline'],
              '피로를 몰라도 피로와 관련된 개인 규칙이 없으므로 분기가 생기지 않는다.')],
        '(1) 논쟁점: "그때 쉬는 모습은 못 봤어요"는 휴식 여부에 대한 정보 부족이다. 이를 "쉬지 않고 계속 걸었다"로 읽어 walk를 만들거나, '
        '발견 당시 의자에 앉아 있던 상태를 피로 휴식 규칙으로 만들면 둘 다 근거 없는 행동이 된다. 01~05의 관찰된 이동 지속과 대비된다. '
        '원형 예시 문항: N1.s1은 사용자가 든 정보 부족 예시 문장을 그대로 쓰고, D5 조건 원칙 5의 "쉬는 모습을 보지 못했다는 말뿐이면"에 '
        '1:1로 대응한다. 이 문항을 맞혀도 예시 재현 확인일 뿐이다. 표지가 약한 정보 부족 변형은 08 N1.s1이다. N1.s2의 발견 상태는 '
        '05 N2와 달리 관찰된 계기가 없어 규칙을 만들지 않는다. '
        '(2) 근거 문장: N1.s1 "혼자 나가셨던 날이라 그때 쉬는 모습은 못 봤어요." → 규칙 없음(미관찰). '
        'N1.s2 "찾았을 때는 정류장 의자에 앉아 계셨는데, 언제부터 앉아 계셨는지는 몰라요." → 발견 상태이며 반응 조건이 없어 규칙 없음. '
        'N2 "시장 골목에 사람이 북적이면 들어가시다가도 돌아 나오세요." → avoid_market, market.crowded. '
        '(3) 엔진 지원: 피로 상황은 개인 규칙이 없으므로 모집단 휴식 가정이 적용된다(정보 부족의 올바른 처리). '
        'avoid_market = 지원(장면 신호 market.crowded가 있을 때). '
        '연구 근거: 간접 근거. C20(보호자가 보지 못한 시간대는 비어 있음)은 정보 부족 구분, C39(혼잡한 시장에서 불안)는 회피에 대한 근거.',
        ['S1 붐비는 시장 근처 → avoid_market',
         'S2 피로·오래 걸음 → 개인 반응 없음(walk·rest 생성 금지)',
         'S3 시장 안 붐빔 → 개인 반응 없음',
         'S4 피로 미상 → 개인 반응 없음(피로 분기 생성 금지)'])

    # 07: ordinary observed rest; walking capacity is not continuation.
    v.persona(
        'Q_fatigue_continuation_07', FAMILY, ['corpusA:DM-31', 'local:C07'],
        [{'label': '모래내공원', 'place_type': 'park'}, {'label': '고운상가', 'place_type': 'market'}],
        [(v.DEFAULT_INTRO, _intro('모래내공원과 고운상가')),
         ('걷다가 지치시면 어떻게 하세요?',
          '힘들어하시면 근처 의자를 찾아 꼭 앉으세요. 한번 앉으시면 한참 계시다가 다시 일어나세요.'),
         ('평소에는 얼마나 걸으세요?', '요즘도 동네 한 바퀴는 숨도 안 차고 금방 도세요.')],
        [spec('rest', 'is_walking and fatigue_high', ids=('N1',))],
        [case('trigger', scene(fatigue_high=True), ['rest'],
              '걷다가 힘들어하면 앉아 쉰다(N1.s1).'),
         case('non_trigger', scene(fatigue_high=False, continuous_walk_minutes=50), ['baseline'],
              '숨도 안 차고 동네를 돈다는 이동 능력(N2)은 계속 걷기 규칙이 아니다. 피로가 없으면 기술된 반응이 없다.'),
         case('boundary_or_release', scene(fatigue_high=True, current_action='rest'), ['baseline'],
              '이미 앉아 있으면 쉬기를 새로 시작하지 않는다. 다시 일어난 뒤의 행동은 기술되지 않았다.'),
         case('unobserved_or_conflict', scene(fatigue_high=None), [],
              '피로 여부를 모르면 쉬기와 기준선이 모두 가능하다.', status='unknown',
              possible=['baseline', 'rest'])],
        '(1) 논쟁점: 피로 상황에서 실제로 쉬는 일반 휴식 관찰이다. 이동 지속 사례(01~05)와 같은 피로 조건이지만 행동이 반대다. '
        '또 이동 능력 진술을 피로 이동 지속으로 오해하면 walk가 생긴다. 능력과 관찰된 이동 지속을 구분하는지 본다. '
        '변형 문항: 처음 초안의 "체력은 좋으셔서"는 D5 조건 원칙 5의 "보행 능력 진술"에 1:1로 대응해서, "체력"이라는 말 없이 '
        '걷는 모습("숨도 안 차고")으로 능력을 말하게 고쳤다. "숨도 안 차고"는 피로가 없는 상태라 "숨이 차도 계속 걸음"과 대비된다. '
        '(2) 근거 문장: N1.s1 "힘들어하시면 근처 의자를 찾아 꼭 앉으세요." → rest, is_walking and fatigue_high. '
        'N1.s2 "한번 앉으시면 한참 계시다가 다시 일어나세요."의 "한참"은 수치가 아니어서 hold를 만들지 않는다(특성 손실로 보존). '
        'N2 "요즘도 동네 한 바퀴는 숨도 안 차고 금방 도세요." → 이동 능력, 규칙 없음(capacity_only). '
        '(3) 엔진 지원: rest = 지원(fatigue_high 내부 사실, 보행 중 조건). 오래 쉬는 특성 = 의미 불완전(hold 미상이라 엔진 기본 5분). '
        '의자를 찾아가는 부분 = 표현 불가. 체력(피로 누적 속도) = 표현 불가, 개인화 채널 없음: 엔진의 피로 누적 배수는 유형 단위'
        '(gauges.fatigue_mult)이고 k_f 개인화는 금지 목록(gauges.DENIED_OVERRIDES)에 있다. 이동 능력 축은 반경·최대 속도에 쓰인다고 '
        '금지 사유에 적혀 있으나, 이 문장이 그 축으로 소비되는지는 검증 필요. N2의 capacity_only 역할(규칙 없음)은 그대로 두고, '
        '엔진 특성 손실은 checks의 특성 보존 점검 항목으로 따로 남긴다(모델 역할 기대와 엔진 한계를 섞지 않으려고 '
        'unsupported_sentences에는 넣지 않았다). '
        '연구 근거: 간접 근거. DM-31(한참 왔다 갔다 하다 스스로 멈춤)·C07(보행 어려움 비중)은 피로 휴식을 직접 말하지 않는다.',
        ['S1 피로·보행 중 → rest 단독(walk 금지)',
         'S2 피로 아님·오래 걸음 → 개인 반응 없음(능력으로 walk 생성 금지)',
         'S3 이미 앉아 있음 → 개인 반응 없음',
         'S4 피로 미상 → 기준선/rest 분기 보존',
         'N1.s2 "한참"으로 수치 hold를 만들지 않음',
         '특성 보존 점검(장면 채점 밖 수동 확인): N2 이동 능력은 규칙 없음(capacity_only)이 맞지만, 엔진에 개인 체력(피로 누적 '
         '속도) 채널이 없어 이 사람의 특성이 표현되지 않고 사라진다'],
        unsupported_sentences=('N1.s2',))

    # 08: speculation about an unobserved day vs. observed rest (alone-scene kept out of scoring).
    v.persona(
        'Q_fatigue_continuation_08', FAMILY, ['corpusB:C19', 'corpusB:C20', 'local:C07'],
        [{'label': '살구나무쉼터', 'place_type': 'park'}, {'label': '한마음상가', 'place_type': 'market'}],
        [(v.DEFAULT_INTRO, _intro('살구나무쉼터와 한마음상가')),
         ('혼자 나가셨던 날 지치셨을 때는 어떠셨어요?',
          '그날 중간에 앉으셨는지는 저도 몰라요. 아마 힘들어도 계속 걸으셨을 거예요, 워낙 고집이 세셔서요.'),
         ('같이 걸을 때는 어떠세요?',
          '같이 산책하다 힘드시면 먼저 멈춰 서서 좀 쉬었다 가자고 하시고, 실제로 앉아서 쉬세요.')],
        [spec('rest', 'is_walking and fatigue_high', ids=('N2',))],
        [case('trigger', scene(fatigue_high=True, family_present=True), ['rest'],
              '같이 걷다 힘들면 실제로 앉아 쉰다(N2).'),
         case('non_trigger', scene(fatigue_high=False, family_present=True), ['baseline'],
              '피로가 없으면 기술된 반응이 없다.'),
         case('boundary_or_release', scene(fatigue_high=True, family_present=True, current_action='rest'), ['baseline'],
              '이미 앉아 쉬는 중이면 쉬기를 새로 시작하지 않는다. 휴식을 동행 중으로 한정하든 않든 같은 답이 나오는 경계다.'),
         case('unobserved_or_conflict', scene(fatigue_high=None, family_present=True), [],
              '동행 중 피로 여부를 모르면 쉬기와 기준선이 모두 가능하다.', status='unknown',
              possible=['baseline', 'rest'])],
        '(1) 논쟁점: "아마 힘들어도 계속 걸으셨을 거예요"는 문장 모양이 01의 관찰된 이동 지속과 비슷하지만, 보지 못한 날에 대한 성격 기반 '
        '추측이다. 이를 walk로 만들면 관찰된 휴식과 충돌한다. 반대로 관찰된 휴식이 동행 중이었으므로 혼자일 때까지 넓혀도 되는지도 논쟁이다. '
        '참조는 동행 한정 표현이 원문에 없으므로 일반 휴식으로 두었고, 대안 해석은 rest 조건에 family_present를 붙여 혼자일 때는 모집단 '
        '휴식으로 둔다. 변형 문항: N1.s1은 06 원형("그때 쉬는 모습은 못 봤어요")과 달리 "못 봤다"는 말 없이 정보 부족을 말한다. '
        '채점 밖 검토 장면: 걷는 중·피로 높음·혼자(family_present 거짓). 참조는 rest, 대안 해석은 기준선이다. 단일 정답 채점에 넣으면 '
        '대안 해석이 무조건 실패하므로 사람 검토 전까지 채점 장면에서 뺐다. 그래서 채점 장면 S1~S4는 모두 동행(family_present 참) 또는 '
        '이미 쉬는 상태로 두어 두 해석이 같은 답을 내게 했다. 이 때문에 "혼자일 때만 계속 걷는다"로 묶은 추측 walk는 채점 장면으로 '
        '잡히지 않으므로, N1(미관찰·추측)을 근거로 한 규칙이 있는지 근거 문장으로 따로 확인한다. '
        '(2) 근거 문장: N2 "같이 산책하다 힘드시면 먼저 멈춰 서서 좀 쉬었다 가자고 하시고, 실제로 앉아서 쉬세요." → rest, is_walking and fatigue_high. '
        'N1.s1 "그날 중간에 앉으셨는지는 저도 몰라요."와 N1.s2 "아마 힘들어도 계속 걸으셨을 거예요, 워낙 고집이 세셔서요." → 미관찰·추측, 규칙 없음. '
        '(3) 엔진 지원: rest = 지원. 추측은 규칙이 없으므로 엔진 영향 없음. 대안 해석을 택하면 family_present가 관찰 주입 전용이라 기본이 '
        '미상이어서 수색 중에는 rest와 모집단 기준선이 분기한다(의미 불완전). '
        '연구 근거: 간접 근거. C19는 배회 판정에 목적 지향성 추론을 섞는 문제를 지적한 문헌이고, 보호자 진술을 관찰과 추론으로 구분하자는 '
        '"해석:" 부분은 원문에 없는 주장자의 추론이다. C20(관찰 공백) 보조, C07은 휴식에 대한 간접 근거.',
        ['S1 피로·동행 → rest 단독(추측을 조건 없이 walk로 만들면 rest와 분기 충돌로 실패)',
         'S2 피로 아님·동행 → 개인 반응 없음',
         'S3 동행 중 이미 앉아 쉼 → 개인 반응 없음(두 해석 모두 같은 답)',
         'S4 동행 중 피로 미상 → 기준선/rest 분기 보존',
         '채점 밖 검토 장면(사람 검토 전 채점 제외): 피로·혼자 걷는 중 → 참조 rest / 대안 해석(동행 한정) 기준선',
         '근거 문장 수동 확인: N1(미관찰·추측)을 근거로 한 규칙이 있으면 실패. "혼자일 때만 walk"형 추측 규칙은 채점 장면으로 잡히지 않음'])

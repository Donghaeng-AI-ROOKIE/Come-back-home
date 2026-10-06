"""Research personas: past_destination family (AI draft, unreviewed).

Behavior type: heading for a place that mattered in the past (old home, old
workplace, hometown, a relative's home, a family grave, an old school). Axes
covered: an observed departure versus talk only, coordinate arrival versus
recognizing the place, and departure gated by an observable fact (clock time,
observed darkness, observed rain, being alone, being lost). Pre-departure
emotion, route shape, transport, endurance and terrain are kept as
unrepresentable traits instead of being mapped onto latent engine facts.
Every persona is synthetic. Guardian wording describes what this one person
was seen doing; population rates in the brief are not turned into rules.
"""
from __future__ import annotations

FAMILY = 'past_destination'


def register(v):
    spec, scene, nearby, case = v.spec, v.scene, v.nearby, v.case

    # 01. Old workplace, early-morning "commute"; waits at the coordinates while
    # the guardian does not know whether the changed building was recognized.
    # Endurance ("does not ask to rest") is an ability trait, not a rest rule.
    v.persona(
        'R_past_destination_01', FAMILY,
        ['webB:C38', 'webB:C40', 'webA:C09', 'corpusA:DM-20', 'webB:C05'],
        [{'label': '물레방직 옛 공장', 'place_type': 'workplace'},
         {'label': '버들내역', 'place_type': 'station'}],
        [('적어 주신 두 곳부터 여쭤볼게요. 아버님께 어떤 곳이에요?',
          '물레방직 옛 공장은 아버지가 스물여덟 해를 다니신 직장이에요. 문 닫은 지 오래돼서 지금은 택배 창고로 쓰여요. '
          '버들내역은 제가 출퇴근하는 역이라 혹시 몰라 같이 적었어요.'),
         ('올해 아버님이 혼자 나가셨던 날을 떠올려 보시면 어떤 모습이셨어요?',
          '올해 들어 그런 일이 두 번 있었는데 둘 다 새벽 5시 반부터 7시 사이였어요. '
          '작업복 점퍼를 챙겨 입고 늦으면 반장한테 혼난다면서 공장 쪽으로 걸어가셨어요.'),
         ('가장 최근에는 어디서 어떤 모습으로 찾으셨어요?',
          '제가 공장 정문 자리로 바로 가 봤더니 거기 계셨어요. 간판도 다르고 건물도 바뀌었는데 경비실 옆에 가만히 서서 '
          '사람들 출근하기를 기다리고 계시더라고요. 그게 옛 공장인 줄 알아보셨는지는 저도 모르겠어요.'),
         ('요즘 아버님 다리 힘은 어떠세요?',
          '다리는 아직 정정하셔서 한 시간 넘게 걸으셔도 쉬자는 말씀을 안 하세요.')],
        [spec('seek_0', 'clock_hour >= 5.5 and clock_hour <= 7 and not physical_arrival', ids=('N1', 'N2')),
         spec('wait', 'physical_arrival', ids=('N2',))],
        [case('trigger', scene(clock_hour=6.1), ['seek_0'],
              '새벽 5시 반~7시 사이에는 옛 공장으로 출근하듯 향한다.'),
         case('non_trigger', scene(clock_hour=15.5, continuous_walk_minutes=70, distance_since_rest_m=3360),
              ['baseline'],
              '새벽 시간대가 아니면 공장으로 향하지 않는다. 한 시간 넘게 걸어도 쉬자고 하지 않는다는 말은 '
              '지구력에 관한 진술이라 휴식 규칙의 근거가 아니다.'),
         case('boundary_or_release',
              scene(clock_hour=6.6, physical_arrival=True, target_recognized=None,
                    current_place_label='물레방직 옛 공장'), ['wait'],
              '공장 좌표에 닿으면 정문 옆에서 기다린 관찰. 알아봤는지는 보호자도 모르므로 대기의 조건이 아니다.'),
         case('unobserved_or_conflict', scene(clock_hour=None), [],
              '시각을 모르면 새벽 출발 여부를 단정할 수 없다.', status='unknown',
              possible=['baseline', 'seek_0'])],
        '퇴직한 아버지가 새벽 시간대에만 옛 공장으로 출근하듯 나섰고, 바뀐 건물 앞에서 기다린 사람(알아봤는지는 모름).',
        ['새벽 5시 반~7시이면 옛 공장으로 출발', '새벽 밖 시간대는 출발 없음(70분 연속 보행이어도 휴식 규칙 없음)',
         '좌표 도착만으로 대기하며 알아봄 여부는 조건이 아님(장면도 알아봄 미관측)', '시각 미관측이면 출발과 기본 이동이 갈림',
         '보호자 자신의 출퇴근 역은 본인 목적지 근거가 아님',
         '지구력 개인차(N3.s1)는 표현 불가: 쉬지 않는다는 능력 진술을 휴식 규칙이나 계속 걷기로 옮기지 않음'],
        unsupported_sentences=('N3.s1',))

    # 02. Old home when darkness is observed (not a clock time); at the house,
    # recognition shown by her own words decides waiting vs. walking on.
    v.persona(
        'R_past_destination_02', FAMILY,
        ['webA:C05', 'webB:C05', 'webB:C40', 'corpusB:C13'],
        [{'label': '오동나무골 옛집', 'place_type': 'past_home'},
         {'label': '새말 정형외과', 'place_type': 'hospital'}],
        [('두 곳을 고르신 이유가 궁금해요.',
          '오동나무골 옛집은 어머니가 시집와서 마흔 해 넘게 사신 집이에요. 몇 해 전에 헐리고 그 자리에 빌라가 섰어요. '
          '새말 정형외과는 어머니 무릎 때문에 한 달에 한 번 다니는 병원이에요.'),
         ('어머님이 현관을 나서시는 건 주로 어떤 때예요?',
          '창밖이 어둑어둑해지면 이제 집에 가야 한다면서 신을 신으세요. 그때 말하는 집은 오동나무골 옛집이에요. '
          '해가 짧은 겨울에는 저녁 먹기 한참 전부터 그러시고요. 지난가을에 그렇게 나가셨다가 옛집 골목에서 찾았어요.'),
         ('옛집 골목에서 찾으셨을 때 어머님은 어떤 모습이셨어요?',
          '지난가을에는 대문 있던 자리 앞 계단에 앉아서, 우리 집 문이 왜 잠겼냐고 하시면서 꼼짝 않고 계셨어요. '
          '올봄에 또 나가셨을 때는 빌라 앞에서 여기가 어디냐고 두리번거리시더니 그냥 지나쳐서 골목 끝까지 걸어가셨고요. '
          '그날은 거기가 옛집인 줄 모르셨던 것 같아요.')],
        [spec('seek_0', 'dark_observed and not physical_arrival', ids=('N1',)),
         spec('wait', 'physical_arrival and target_recognized', ids=('N2',)),
         spec('walk', 'physical_arrival and not target_recognized', ids=('N2',))],
        [case('trigger', scene(dark_observed=True, clock_hour=17.2), ['seek_0'],
              '겨울 해질녘처럼 이른 시각이라도 어둑해지면 옛집으로 향한다.'),
         case('non_trigger', scene(dark_observed=False, clock_hour=19.3), ['baseline'],
              '여름 저녁처럼 늦은 시각이라도 밖이 밝으면 나서지 않는다. 기준은 시각이 아니라 어둠이다.'),
         case('boundary_or_release',
              scene(dark_observed=True, clock_hour=19, physical_arrival=True, target_recognized=False,
                    current_place_label='오동나무골 옛집'), ['walk'],
              '좌표에 닿았어도 못 알아보면 지나쳐 계속 걷는다.'),
         case('unobserved_or_conflict',
              scene(dark_observed=True, clock_hour=18.4, physical_arrival=True, target_recognized=None,
                    current_place_label='오동나무골 옛집'), [],
              '도착했지만 알아봤는지 모르면 대기와 계속 걷기가 갈린다.', status='unknown',
              possible=['wait', 'walk'])],
        '어두워지면 헐린 옛집을 찾아 나서고, 도착 후 알아보면 앉아 기다리고 못 알아보면 지나치는 어머니.',
        ['어둠 관측 시 옛집으로 출발(17.2시 어둠에서도 출발)', '밝으면 늦은 시각(19.3시)이어도 출발하지 않음',
         '도착+알아봄=대기, 도착+못 알아봄=계속 걷기', '알아봄 미관측이면 대기/걷기 분기',
         '알아봄 여부는 본인 말(우리 집/여기가 어디냐)로 드러난 관찰이며 보호자의 추론이 섞임'])

    # 03. Relative's home only when left alone; hometown is talk only; stops when lost.
    v.persona(
        'R_past_destination_03', FAMILY,
        ['corpusA:DM-20', 'webA:C20', 'webB:C09', 'webA:C17', 'webB:C38'],
        [{'label': '갈뫼골 고향 마을', 'place_type': 'hometown'},
         {'label': '버드실 큰이모 댁', 'place_type': 'relative_home'},
         {'label': '한빛 주간보호센터', 'place_type': 'day_care'}],
        [('세 곳이 어머님과 어떤 인연이 있는지 차례로 알려 주세요.',
          '갈뫼골은 어머니가 나고 자란 고향이에요. 버드실은 큰이모가 사시던 동네고, '
          '한빛 주간보호센터는 평일에 제가 차로 모셔다 드리는 곳이에요.'),
         ('어머님이 요즘 입버릇처럼 하시는 말씀이 있나요?',
          '하루에도 몇 번씩 갈뫼골에 가 봐야 한다고 하세요. 그런데 고향 쪽으로 실제로 나서신 적은 한 번도 없어요. '
          '버스를 몇 번이나 갈아타야 하는 먼 곳이라 말씀으로만 그러세요.'),
         ('혼자 집을 나가셨던 날들을 떠올려 보시면 공통점이 있었나요?',
          '제가 장 보러 나가서 어머니 혼자 집에 계실 때만 그랬어요. 세 번 다 큰이모 댁에 간다며 버드실 쪽으로 '
          '걸어가셨어요. 이모가 돌아가신 지 열다섯 해가 넘었는데도요. 제가 옆에 있으면 그쪽으로 가자는 말도 안 하세요.'),
         ('혼자 가시던 중에 있었던 일 가운데 기억에 남는 게 있으세요?',
          '작년 가을에 동네 약국 앞에 우두커니 서 계신 걸 약사님이 알려 주셨어요. 길을 잃으셨다는 걸 아시면 '
          '그렇게 이모 댁 가던 것도 잊으시고, 그 자리에 멈춰서 누가 데리러 오기만 기다리세요.')],
        [spec('seek_1', 'not family_present and not lost_awareness', ids=('N2', 'N3')),
         spec('wait', 'lost_awareness', ids=('N3',))],
        [case('trigger', scene(family_present=False), ['seek_1'],
              '혼자 있을 때 큰이모 댁 쪽으로 나선다.'),
         case('non_trigger', scene(family_present=True), ['baseline'],
              '보호자가 곁에 있으면 이모 댁으로 가지 않고, 고향은 말뿐이라 출발하지 않는다.'),
         case('boundary_or_release', scene(family_present=False, lost_awareness=True), ['wait'],
              '가던 중 길을 잃은 걸 알면 이모 댁 가던 것을 멈추고 기다린다.'),
         case('unobserved_or_conflict', scene(family_present=None), [],
              '보호자가 곁에 있는지 모르면 이모 댁 출발 여부가 갈린다.', status='unknown',
              possible=['baseline', 'seek_1'])],
        '고향은 말로만 찾고, 실제로는 혼자 남았을 때만 돌아가신 큰이모 댁으로 걸어 나서며, 길을 잃으면 멈춰 기다리는 어머니.',
        ['혼자일 때만 큰이모 댁으로 출발', '고향은 반복 발언뿐이라 출발 근거 아님',
         '길 잃음 인지 시 출발을 멈추고 대기(우선)', '보호자 동석 미관측이면 출발 분기',
         '근사 표기: 원문의 혼자 남음은 출발 맥락인데 참조 규칙은 이를 실종 중 유지 조건(보호자 부재)으로 근사함. '
         '엔진에서는 보호자 동석이 대개 거짓이거나 미관측이라 늘 분기로 작동함'])

    # 04. Family grave; the pre-departure agitation is not an engine fact, so the
    # stated observable gate is rain. Rest by walking time applies on any path;
    # the uphill terrain itself cannot be represented.
    v.persona(
        'R_past_destination_04', FAMILY,
        ['local:C12', 'webB:C40'],
        [{'label': '갈참나무골 선산', 'place_type': 'cemetery'},
         {'label': '윗말 약수터', 'place_type': 'park'}],
        [('선산하고 약수터를 적어 주셨는데, 아버님께 각각 어떤 자리예요?',
          '갈참나무골 선산에는 할아버지 할머니 산소가 있어요. 윗말 약수터는 아버지가 예전에 새벽마다 물 뜨러 다니시던 '
          '곳인데, 무릎이 나빠지고 나서는 발길을 끊으셨어요.'),
         ('지금까지 아버님이 혼자 나가셨던 날 이야기를 처음부터 들려주시겠어요?',
          '지난봄하고 초여름에 한 번씩 있었어요. 그날들은 아침부터 안절부절못하시면서 방을 들락날락하셨어요. '
          '그러다 할아버지 산소에 가 봐야 한다며 모자를 쓰고 나가셨고, 매번 선산 들머리에서 찾았어요. '
          '비가 오면 산길 미끄럽다고 산소 쪽으로는 아예 안 가세요.'),
         ('선산까지 가는 길이랑 아버님 걸음은 어떤지 궁금해요.',
          '선산 가는 길은 처음부터 끝까지 오르막이에요. 시장에 다녀오실 때나 산소 가실 때나 15분쯤 걸으시면 꼭 '
          '길가 돌이든 남의 집 계단이든 걸터앉아서 7분 정도 숨을 고르세요. 그러고 나서 다시 일어나 가던 길을 가세요.')],
        [spec('seek_0', 'not rain_observed and continuous_walk_minutes < 15', ids=('N1',)),
         spec('rest', 'is_walking and continuous_walk_minutes >= 15', ids=('N2',), hold=7)],
        [case('trigger',
              scene(rain_observed=False, anxiety_high=False, continuous_walk_minutes=7, distance_since_rest_m=340),
              ['seek_0'],
              '비가 오지 않으면 선산 쪽으로 향한다. 출발 전 초조함은 엔진의 불안 사실과 다르므로 조건이 아니다.'),
         case('non_trigger',
              scene(rain_observed=True, anxiety_high=True, continuous_walk_minutes=7, distance_since_rest_m=340),
              ['baseline'],
              '비가 오면 산소 쪽으로 가지 않는다. 불안 사실이 켜져 있어도 출발 근거가 아니다.'),
         case('boundary_or_release',
              scene(rain_observed=False, continuous_walk_minutes=15, distance_since_rest_m=720), ['rest'],
              '15분 연속 보행에 이르면 산소로 가던 길이어도 먼저 앉아 쉰다.'),
         case('unobserved_or_conflict',
              scene(rain_observed=None, continuous_walk_minutes=4, distance_since_rest_m=190), [],
              '비 여부를 모르면 선산 출발 여부가 갈린다.', status='unknown',
              possible=['baseline', 'seek_0'])],
        '초조한 날 조부모 산소가 있는 선산으로 나서지만 비 오면 가지 않고, 어느 길이든 15분쯤 걸으면 7분 쉬는 아버지.',
        ['비가 오지 않으면 선산으로 출발', '비가 오면 출발 없음(불안 사실이 참이어도)',
         '연속 보행 15분 이상이면 출발보다 휴식(7분) 우선', '비 미관측이면 출발 분기',
         '출발 전 초조함(N1.s2)은 표현 불가: 이동 중 누적되는 불안 사실로 옮기지 않음',
         '오르막 지형(N2.s1)은 표현 불가: 휴식은 시장 길도 같다는 진술로 일반화되며 오르막 한정이 아님'],
        unsupported_sentences=('N1.s2', 'N2.s1'))

    # 05. Old shop in a market when it rains; waits under the eaves; avoids crowded markets.
    # Reminiscence on clear days is talk, not a departure basis.
    v.persona(
        'R_past_destination_05', FAMILY,
        ['webA:C09', 'webB:C38', 'webB:C40'],
        [{'label': '반달시장 옛 철물점 자리', 'place_type': 'workplace'},
         {'label': '반달 목욕탕', 'place_type': 'bathhouse'}],
        [('철물점 자리하고 목욕탕은 아버님께 어떤 곳이에요?',
          '반달시장 철물점 자리는 아버지가 서른다섯 해 동안 장사하시던 가게예요. 지금은 다른 분이 떡집을 하고 있어요. '
          '반달 목욕탕은 가게 하실 때 단골이던 곳인데 문 닫은 지 꽤 됐어요.'),
         ('아버님 일로 가장 놀라셨던 때가 언제였어요?',
          '올여름 장마 때요. 비가 오기 시작하면 가게 차양을 내리고 물건을 들여놔야 한다면서 우산도 없이 시장 쪽으로 '
          '나가세요. 장마 동안에만 세 번이나 그러셨어요. 날이 맑으면 종일 철물점 시절 손님 얘기를 하시는데, '
          '그건 그냥 옛날이야기예요.'),
         ('그다음에는 어떻게 되셨어요?',
          '한 번은 제가 시장까지 쫓아가 봤는데 떡집 처마 밑에 서서 비가 그칠 때까지 가만히 계셨어요. 비가 그치자 '
          '거기서 나오셨는데, 제가 잠깐 한눈판 사이라 그다음엔 어디로 가셨는지 못 봤어요.'),
         ('장날에 시장에 모시고 가 보신 적이 있으세요?',
          '장날처럼 시장 바닥이 사람으로 꽉 차 있으면 질색을 하시고 시장 밖으로 빠져나오세요. '
          '한산할 때는 시장 안도 잘 다니세요.')],
        [spec('seek_0', 'rain_observed and not physical_arrival', ids=('N1', 'N2')),
         spec('wait', 'physical_arrival and rain_observed', ids=('N2',)),
         spec('avoid_market', 'market.crowded', ids=('N3',))],
        [case('trigger', scene(rain_observed=True), ['seek_0'],
              '비가 오기 시작하면 옛 가게 자리로 향한다.'),
         case('non_trigger', scene(rain_observed=False, clock_hour=16), ['baseline'],
              '맑은 날에는 장사 이야기만 하고 나서지 않는다.'),
         case('boundary_or_release',
              nearby('market', crowded=False, rain_observed=True, physical_arrival=True,
                     current_place_label='반달시장 옛 철물점 자리'), ['wait'],
              '가게 자리에 닿으면 비가 그칠 때까지 처마 밑에서 기다린다(시장은 한산함).'),
         case('unobserved_or_conflict', nearby('market', crowded=True, rain_observed=True), [],
              '비 오는 중 붐비는 시장 근처라면 가게로 가기와 시장 피하기 중 무엇이 먼저인지 원문에 없다.',
              status='unknown', possible=['avoid_market', 'seek_0'])],
        '비가 오면 옛 철물점 차양을 내리러 시장으로 나서고 처마 밑에서 비를 기다리지만, 붐비는 시장은 피하는 아버지.',
        ['비 관측 시 옛 가게 자리로 출발', '맑은 날 회상 이야기는 출발 근거 아님', '도착 후 비가 계속되면 대기',
         '붐비는 시장 근처에서 출발과 회피의 우선순위 미진술이면 미확정',
         '문 닫은 단골 목욕탕은 과거 장소일 뿐 출발 관찰이 없음'])

    # 06. Old neighborhood only once lost; stops after dark.
    # A past found location was a police handover, not a destination.
    v.persona(
        'R_past_destination_06', FAMILY,
        ['webA:C46', 'local:C24', 'corpusB:C11', 'webA:C09'],
        [{'label': '미루나무골 옛 동네', 'place_type': 'past_residence'},
         {'label': '가람역 지구대', 'place_type': 'police'},
         {'label': '솔밭 체육공원', 'place_type': 'park'}],
        [('남편분과 관련해 적어 주신 세 곳을 하나씩 설명해 주시겠어요?',
          '미루나무골은 저희가 신혼 때부터 스무 해 가까이 살던 동네예요. 가람역 지구대는 지난번 실종 때 남편을 찾은 곳이고, '
          '솔밭 체육공원은 남편이 혼자 운동하러 다니는 곳이에요.'),
         ('가람역 지구대는 어떤 일로 적으셨어요?',
          '역 앞에서 헤매는 걸 순찰하던 경찰관이 보고 지구대로 모셔 간 거예요. 남편이 지구대로 찾아간 건 아니에요.'),
         ('혼자 나갔다가 늦게 들어오신 날은 대개 어디서 찾으셨어요?',
          '작년에만 세 번을 미루나무골 어귀에서 예전 이웃 눈에 띄어서 연락을 받았어요. '
          '길을 잃었다 싶으면 옛날 살던 그 동네 쪽으로 가요. 갈 때는 꼭 큰길만 따라가요.'),
         ('해 진 뒤에 찾으신 적도 있으세요?',
          '길을 잃은 채로 날이 어두워지면 더는 안 가고 멈춰 서서 꼼짝 않고 있어요. '
          '밤에 찾았을 때는 늘 가로등 밑에 서 있었어요.')],
        [spec('seek_0', 'lost_awareness and not dark_observed', ids=('N2', 'N3')),
         spec('wait', 'lost_awareness and dark_observed', ids=('N3',))],
        [case('trigger', scene(lost_awareness=True, dark_observed=False), ['seek_0'],
              '길을 잃은 걸 알면 옛 동네 쪽으로 향한다.'),
         case('non_trigger', scene(lost_awareness=False, current_place_label='가람역 지구대'), ['baseline'],
              '길을 잃지 않았으면 옛 동네로 가지 않고, 지구대는 인계 장소라 목적지가 아니다.'),
         case('boundary_or_release', scene(lost_awareness=True, dark_observed=True, clock_hour=20), ['wait'],
              '길 잃은 채 어두워지면 멈춰 기다린다.'),
         case('unobserved_or_conflict', scene(lost_awareness=True, dark_observed=None, clock_hour=19), [],
              '어둠 여부를 모르면 옛 동네로 가기와 멈춰 기다리기가 갈린다.', status='unknown',
              possible=['seek_0', 'wait'])],
        '길을 잃었다고 느낄 때만 큰길 따라 옛 동네로 향하고, 어두워지면 멈춰 서는 남편. 과거 발견지는 경찰 인계 장소.',
        ['길 잃음 인지 + 밝음이면 옛 동네로 출발', '길을 잃지 않았으면 출발 없음, 인계 장소는 목적지 아님',
         '길 잃음 + 어둠이면 대기', '어둠 미관측이면 출발/대기 분기',
         '큰길만 따라가는 경로 특성(N2.s3)은 표현 불가', '가로등 밑처럼 밝은 자리를 골라 서는 특성(N3.s2)은 표현 불가'],
        unsupported_sentences=('N2.s3', 'N3.s2'))

    # 07. "Going home" at a stated clock window means the old house; the
    # distance-limited rest takes precedence; a bus attempt is unrepresentable.
    v.persona(
        'R_past_destination_07', FAMILY,
        ['webB:C38', 'webB:C40', 'webA:C05'],
        [{'label': '은행나무골 옛집', 'place_type': 'past_home'},
         {'label': '샘골 어린이공원', 'place_type': 'park'}],
        [('어머님과 관련해 두 곳을 적어 주셨네요. 어떤 곳인지 들려주세요.',
          '은행나무골 옛집은 어머님이 자식 넷을 키우신 집이에요. 지금 사시는 아파트에서 1.5킬로쯤 떨어져 있어요. '
          '샘골 어린이공원은 아파트 바로 뒤에 있는 작은 공원이에요.'),
         ('하루 중에 유독 신경 쓰이는 시간대가 있으세요?',
          '오후 4시 반부터 6시 반 사이가 되면 애들 저녁 해 먹여야 한다면서 집에 가야 한다고 하세요. '
          '그때 말하는 집은 이 아파트가 아니라 은행나무골 옛집이에요. 지난달에는 그 시간에 실제로 옛집 쪽으로 '
          '걸어 나가셔서, 큰길 건너기 전에 제가 따라가 모셔 왔어요. 지난겨울에는 옛집 가는 버스를 타겠다며 '
          '정류장에 서 계신 걸 이웃분이 보고 데려다주셨어요.'),
         ('산책하실 때 옆에서 보시면 어떠세요?',
          '무릎이 안 좋으셔서 한 900미터쯤 걸으시면 꼭 주저앉아서 쉬세요. 쉬고 나면 다시 가던 쪽으로 걸으세요.')],
        [spec('seek_0', 'clock_hour >= 16.5 and clock_hour <= 18.5 and distance_since_rest_m < 900', ids=('N1',)),
         spec('rest', 'is_walking and distance_since_rest_m >= 900', ids=('N2',))],
        [case('trigger',
              scene(clock_hour=17, dark_observed=False, home_pull_high=False,
                    distance_since_rest_m=350, continuous_walk_minutes=7), ['seek_0'],
              '오후 4시 반~6시 반에는 집에 간다며 옛집 쪽으로 나선다. 밝은지, 귀소 사실이 켜졌는지는 조건이 아니다.'),
         case('non_trigger',
              scene(clock_hour=14, home_pull_high=True, distance_since_rest_m=350, continuous_walk_minutes=7),
              ['baseline'], '그 시간대가 아니면 옛집으로 가지 않는다. 경과 시간으로 켜지는 귀소 사실은 근거가 아니다.'),
         case('boundary_or_release',
              scene(clock_hour=17.6, distance_since_rest_m=900, continuous_walk_minutes=19), ['rest'],
              '쉬지 않고 900미터에 이르면 옛집으로 가던 중이어도 주저앉아 쉰다.'),
         case('unobserved_or_conflict',
              scene(clock_hour=None, distance_since_rest_m=350, continuous_walk_minutes=7), [],
              '시각을 모르면 옛집으로 가기와 기본 이동이 갈린다.', status='unknown',
              possible=['baseline', 'seek_0'])],
        '저녁 무렵 집에 가겠다는 그 집이 옛집이고 실제로 그쪽으로 걸어 나섰으며, 900미터쯤마다 반드시 쉬는 시어머니.',
        ['오후 4시 반~6시 반이면 옛집으로 출발', '시간대 밖이면 출발 없음(귀소 사실이 참이어도)',
         '휴식 후 거리 900m 이상이면 휴식 우선', '시각 미관측이면 출발/기본 이동 분기',
         '말하는 집이 현재 집이 아니라 옛집이라는 목표 식별이 핵심',
         '옛집 가는 버스를 타려 한 시도(N1.s4)는 표현 불가(도보 도로망만 있음)'],
        unsupported_sentences=('N1.s4',))

    # 08. Old school in the late afternoon (former teacher); pain stops her first;
    # the church is talk only. The non-trigger sits just past the stated window.
    v.persona(
        'R_past_destination_08', FAMILY,
        ['local:C12', 'webA:C09', 'webB:C38'],
        [{'label': '다솜초등학교', 'place_type': 'workplace'},
         {'label': '성모 언덕 성당', 'place_type': 'religious'},
         {'label': '개울가 쉼터 정자', 'place_type': 'park'}],
        [('세 곳 모두 어머님과 어떤 사연이 있는지 궁금해요.',
          '다솜초등학교는 어머니가 마지막으로 근무하고 정년퇴임하신 학교예요. 성모 언덕 성당은 젊을 때 다니시던 성당이고, '
          '개울가 쉼터 정자는 동네 어르신들이 모이는 곳이에요.'),
         ('선생님으로 오래 계셨다고 들었어요. 요즘도 그 시절 습관이 나올 때가 있나요?',
          '오후 3시 반부터 5시 사이에 아이들 하교시켜야 한다면서 가방을 들고 나서세요. '
          '올해만 여러 번 그러셨고, 실제로 다솜초등학교 정문까지 걸어가신 적도 한 번 있어요.'),
         ('성당은 요즘도 다니세요?',
          '성당 얘기는 가끔 하시는데 성당 쪽으로 나서신 적은 없어요. 옛날 미사 드리던 얘기를 하시는 정도예요.'),
         ('같이 걸으실 때 따로 챙기시는 게 있으세요?',
          '허리가 아프다고 하시면 아무리 급하게 가시던 길이라도 그 자리에서 앉을 데를 찾아 쉬세요. 5분쯤 앉아 계세요. '
          '그러고는 허리가 다 낫지 않았어도 다시 일어나서 가던 길을 가세요.')],
        [spec('seek_0', 'clock_hour >= 15.5 and clock_hour <= 17 and not pain_observed', ids=('N1', 'N3')),
         spec('rest', 'pain_observed', ids=('N3',), hold=5)],
        [case('trigger', scene(clock_hour=16.2), ['seek_0'],
              '오후 3시 반~5시에는 하교 지도하러 학교로 향한다.'),
         case('non_trigger', scene(clock_hour=17.4), ['baseline'],
              '5시를 넘기면 하교 시간대가 지나 학교로 향하지 않는다. 성당은 말뿐이라 출발하지 않는다.'),
         case('boundary_or_release', scene(clock_hour=16.5, pain_observed=True), ['rest'],
              '학교로 가던 시간대라도 허리 통증을 말하면 먼저 앉아 쉰다.'),
         case('unobserved_or_conflict', scene(clock_hour=15.8, pain_observed=None), [],
              '통증 여부를 모르면 학교로 가기와 쉬기가 갈린다.', status='unknown',
              possible=['rest', 'seek_0'])],
        '퇴직 교사인 어머니가 늦은 오후에만 옛 학교로 하교 지도하러 나서며, 통증을 말하면 먼저 쉬고, 성당은 이야기뿐인 사람.',
        ['오후 3시 반~5시 학교로 출발', '5시 직후(17.4시)는 시간대 밖이라 출발 없음, 성당 이야기는 출발 근거 아님',
         '통증 관측 시 휴식(5분) 우선', '통증 미관측이면 출발/휴식 분기',
         '통증이 남아도 쉬고 나서 다시 가는 특성(N3.s3)은 표현 불가: 통증 관측이 이어지면 휴식이 반복됨'],
        unsupported_sentences=('N3.s3',))

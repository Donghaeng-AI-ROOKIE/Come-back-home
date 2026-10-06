"""Research prototypes, family rest_endurance (AI draft, unreviewed).

Walking limit, rest cycle and endurance: a sourced need to sit after a walking
limit (time only, distance only, time AND distance, evening time, fatigue, one
named place), a corrected past capacity, capacity-only statements, guardian-led
rest, and people who keep walking when tired or in pain. Every persona is
synthetic; the guardian speaks about what this one person was actually seen
doing. Group statistics in research_basis are background, never an individual
rule; the only direct basis for each personal rule is the guardian's own
observation (local:C25).
"""


def register(v):
    v.persona(
        'R_rest_endurance_01', 'rest_endurance',
        ['local:C25', 'corpusA:DM-44'],
        [{'label': '은행나무공원', 'place_type': 'park'},
         {'label': '새벽시장', 'place_type': 'market'},
         {'label': '첫 신혼집 골목', 'place_type': 'past_home'}],
        [('요즘 어머니 걸음은 어떠세요?',
          '작년까지만 해도 두 시간을 걸으셔도 앉는 법이 없으셨어요. 올봄에 독감을 크게 앓고 나서 많이 약해지셨어요. '
          '요즘은 35분쯤 걸으시면 앉을 데부터 찾으세요.'),
         ('그건 어떻게 알게 되셨어요?',
          '목에 걸어 드린 위치 단말기에 움직인 기록이 남아요. 보면 35분쯤 움직이다가 7분 남짓 한자리에 멈춰 있고, 다시 움직이세요. '
          '일주일 치 기록이 다 그랬어요.'),
         ('등록하신 세 곳은 어떤 곳인가요?',
          '은행나무공원은 집에서 제일 가까운 공원이고, 새벽시장은 예전에 채소 장사를 하시던 데예요. '
          '첫 신혼집 골목은 결혼하고 처음 사셨던 동네고요.')],
        [v.spec('rest', 'is_walking and continuous_walk_minutes >= 35', ids=('N0', 'N1'), hold=7)],
        [v.case('trigger', v.scene(continuous_walk_minutes=38, distance_since_rest_m=1820),
                ['rest'], '요즘 모습대로 35분쯤을 넘겨 걷는 중이므로 앉아 쉰다.'),
         v.case('non_trigger', v.scene(continuous_walk_minutes=22, distance_since_rest_m=1060, clock_hour=6.5),
                ['baseline'], '아직 35분에 못 미쳐 쉬지 않는다. 작년의 "두 시간도 안 앉음"은 정정된 과거라 다른 행동이 생기지 않는다.'),
         v.case('boundary_or_release', v.scene(continuous_walk_minutes=34, distance_since_rest_m=1630),
                ['baseline'], '35분 바로 아래라 아직 쉬지 않는다.'),
         v.case('unobserved_or_conflict', v.scene(continuous_walk_minutes=41, distance_since_rest_m=1970,
                                                  pain_observed=None, family_present=None, lost_awareness=None),
                ['rest'], '통증·가족 동행·길 잃음 인식이 모두 미관측인 실제 실종 상황이어도 '
                          '휴식은 걸은 시간만으로 정해진다. 원문에 없는 조건으로 휴식을 막지 않는다.')],
        '올봄 이후 약 35분 연속 보행하면 7분 남짓 앉아 쉬는 현재 휴식 주기다(위치 단말기 기록). '
        '작년의 "두 시간을 걸어도 안 앉음"은 정정된 과거 모습이라 규칙이 아니다. '
        '직접 근거는 보호자 관찰(local:C25)뿐이고, DM-44는 병이 진행하며 보행이 나빠질 수 있다는 간접 배경이다.',
        ['과거(두 시간 무휴식) 대신 현재(35분) 진술을 따르는지',
         '35분 바로 아래(34분)에서 쉬지 않는지',
         '7분 남짓 멈춤이 hold로 옮겨지고 쉬기 전 보행 시간과 혼동되지 않는지',
         '관측 주입 사실이 모두 미관측이어도 원문에 없는 조건을 붙여 휴식을 막지 않는지'])

    v.persona(
        'R_rest_endurance_02', 'rest_endurance',
        ['local:C25', 'corpusA:DM-25', 'local:C07'],
        [{'label': '뒷산 둘레길', 'place_type': 'park'},
         {'label': '읍내 오일장', 'place_type': 'market'},
         {'label': '옛 철도관사', 'place_type': 'past_home'}],
        [('아버님이 바깥에서 걸으시는 모습을 보신 적이 있으세요?',
          '베란다에서 내려다보면 단지 바깥 길을 한 바퀴 도세요. 휴대폰 지도로 재 보니 그 한 바퀴가 900미터쯤 되더라고요. '
          '그만큼 걸으시면 아무 데나 걸터앉으세요. 한번 앉으시면 15분은 그대로 계세요.'),
         ('다른 길로 다니실 때도 그러세요?',
          '보건소 가시는 길에도 중간 다리께에서 꼭 한 번 앉으시는데, 재 보니 거기도 집에서 900미터 남짓이었어요.'),
         ('걸음걸이는 어떠세요?',
          '지팡이를 짚으셔서 걸음이 아주 느려요. 그 한 바퀴를 빨리 도는 날은 36분, 늦는 날은 한 시간 가까이 걸려요.'),
         ('같이 나가실 때는 어떠세요?',
          '제가 같이 나가면 제가 먼저 쉬었다 가자고 해요. 그러면 그때 앉으세요.'),
         ('등록하신 둘레길, 오일장, 철도관사는 어떤 곳인가요?',
          '둘레길은 아파트 뒤편 산책길이고, 오일장은 장날마다 구경 다니시던 곳이에요. '
          '철도관사는 기관사로 일하실 때 식구들이랑 살던 집이고요.')],
        [v.spec('rest', 'is_walking and distance_since_rest_m >= 900', ids=('N0', 'N1'), hold=15)],
        [v.case('trigger', v.scene(distance_since_rest_m=940, continuous_walk_minutes=39),
                ['rest'], '쉬고 난 뒤 900미터를 넘겨 걸었으므로 앉는다.'),
         v.case('non_trigger', v.scene(distance_since_rest_m=700, continuous_walk_minutes=47),
                ['baseline'], '빨리 도는 날의 한 바퀴 시간(36분)보다 오래 걸었어도 거리가 900미터에 못 미친다. '
                              '앉는 기준은 한 바퀴 거리이고, 한 바퀴 시간은 날마다 다르다.'),
         v.case('boundary_or_release', v.scene(distance_since_rest_m=900, continuous_walk_minutes=44),
                ['rest'], '900미터에 막 도달한 경계. "900미터쯤 걸으시면"은 도달 시점부터 앉는다.'),
         v.case('unobserved_or_conflict', v.scene(distance_since_rest_m=520, continuous_walk_minutes=31,
                                                  family_present=None),
                ['baseline'], '가족 동행 여부를 몰라도 보호자가 권해서 앉는 휴식은 본인 규칙이 아니므로 '
                              '거리가 덜 찬 지금은 개인 반응이 없다.')],
        '단지 한 바퀴(약 900미터)를 걸으면 15분 앉아 쉬는 거리 기준 휴식이다. 보건소 가는 길에서도 900미터 남짓에서 앉아 '
        '특정 길에 한정되지 않는다. 지팡이·느린 걸음(속도 개인차)과 단지 바깥을 한 바퀴 도는 순환 경로는 현재 계약으로 '
        '표현할 수 없어 부분 손실로 남는다. 동행 중 휴식은 보호자가 먼저 권한 것이라 본인 규칙의 근거가 아니다. '
        '엔진 속도는 분당 48미터로 고정이라 엔진 안에서는 거리와 시간이 함께 움직인다. 시간과 거리를 가르는 장면은 '
        '규칙 구조 시험일 뿐이며, 장면 속 걸음(분당 15~24미터)은 이 사람의 느린 걸음에 맞췄다. '
        '직접 근거는 보호자 관찰(local:C25)이고 DM-25·local:C07은 느린 걸음과 보행 보조기구의 배경이다.',
        ['거리 기준(900미터)을 한 바퀴 소요 시간(36분~한 시간)으로 바꾸지 않는지',
         '900미터 경계에서 휴식이 포함되는지(이상 비교)',
         '보호자가 먼저 권해서 앉는 동행 중 휴식을 규칙으로 만들지 않는지(가족 동행 미관측에서도 기본 이동)',
         '느린 걸음과 순환 경로를 임의 수치나 조건으로 바꾸지 않는지'],
        unsupported_sentences=('N0.s1', 'N2.s1'))

    v.persona(
        'R_rest_endurance_03', 'rest_endurance',
        ['local:C25', 'corpusA:DM-29', 'corpusA:DM-14'],
        [{'label': '갈대천 둑길', 'place_type': 'park'},
         {'label': '삼거리 철물점', 'place_type': 'workplace'},
         {'label': '면 보건지소', 'place_type': 'hospital'}],
        [('갈대천 둑길은 남편분께 어떤 길인가요?',
          '아침마다 걷던 길이에요. 삼거리 철물점은 삼십 년 넘게 운영하던 가게고, 보건지소는 혈압약 타러 다니는 곳이에요.'),
         ('혼자 걷다가 힘에 부치시면 어떻게 하세요?',
          '지쳐도 안 앉아요. 지난봄에 없어졌을 때 경찰서에서 길가 방범 카메라 영상을 같이 봤는데, '
          '숨을 몰아쉬고 셔츠가 땀에 다 젖었는데도 한 시간 반 넘게 한 번을 안 쉬고 걸어가더라고요.'),
         ('보호자분이 같이 걸으실 때는 어떠세요?',
          '같이 걸을 때 제가 좀 쉬었다 가자고 해도 싫다고 손을 뿌리쳐요.')],
        [v.spec('walk', 'is_walking and fatigue_high', ids=('N1',))],
        [v.case('trigger', v.scene(fatigue_high=True, continuous_walk_minutes=84, distance_since_rest_m=4030),
                ['walk'], '걷는 중 몹시 지쳐도 앉지 않고 계속 걷는다.'),
         v.case('non_trigger', v.nearby('park', continuous_walk_minutes=52, distance_since_rest_m=2500),
                ['baseline'], '벤치가 있는 공원 옆에서 오래 걸었어도 지치지 않았으면 개인 반응이 없다.'),
         v.case('boundary_or_release', v.scene(current_action='wait', fatigue_high=True,
                                               continuous_walk_minutes=0, distance_since_rest_m=0),
                ['baseline'], '멈춰 서 있는 중이면 걷다가 지쳐도 안 앉는다는 모습이 적용되지 않는다.'),
         v.case('unobserved_or_conflict', v.scene(fatigue_high=True, lost_awareness=None, pain_observed=None,
                                                  continuous_walk_minutes=78, distance_since_rest_m=3740),
                ['walk'], '길 잃음 인식과 통증이 미관측이어도 지친 채 걷는 중이면 계속 걷는다. '
                          '방범 카메라 장면이 실종 중이었다고 해서 길 잃음 조건을 붙이지 않는다.')],
        '지쳐도 앉지 않고 계속 걷는다(실종 당시 방범 카메라 영상과 보호자 진술). 동행 중 쉬자는 권유를 뿌리치는 모습은 '
        '혼자일 때와 같은 방향이라 별도 규칙이 아니고, 장면은 가족 동행 여부에 기대지 않는다. 통증은 이 사람의 진술에 '
        '없으므로 조건에 넣지 않는다. 피로 높음은 엔진 내부 상태라 실종 상황에서도 값이 정해진다. '
        '직접 근거는 보호자 관찰(local:C25)이고 DM-29·DM-14는 쉬지 않고 걷는 집단 경향의 배경이다.',
        ['피로만으로 계속 걷기가 되는지(통증 조건을 지어내지 않는지)',
         '오래 걸었지만 지치지 않은 장면에서 반응이 없는지',
         '멈춰 서 있을 때는 계속 걷기가 적용되지 않는지(걷는 중 가드)',
         '실종 당시 영상이라는 이유로 길 잃음 조건을 붙이지 않는지',
         '동행 중 권유 거절을 별도 규칙으로 만들지 않는지'])

    v.persona(
        'R_rest_endurance_04', 'rest_endurance',
        ['local:C25', 'corpusA:DM-29'],
        [{'label': '벚꽃길 체육공원', 'place_type': 'park'},
         {'label': '성당 앞 꽃집', 'place_type': 'workplace'},
         {'label': '친정 동네 우물터', 'place_type': 'past_home'}],
        [('어머님은 예전에 어떤 일을 하셨어요?',
          '성당 앞 꽃집에서 이십 년 넘게 일하셨어요. 퇴근하시면 벚꽃길 체육공원을 한 바퀴 걸으셨고요. '
          '친정 동네 우물터 얘기도 자주 하세요.'),
         ('밖에서 걸으시다가 쉬시는 모습은 어떠세요?',
          '기운이 빠져 보이시면 벤치든 계단이든 아무 데나 찾아서 앉으세요. 5분쯤 쉬시고 다시 일어나세요. '
          '공원에서도 그렇고 시장 골목에서도 그러시는 걸 제 눈으로 봤어요.'),
         ('다리가 아프실 때도 그렇게 쉬시나요?',
          '그게 이상해요. 무릎이 아프다고 하시기 시작하면 오히려 안 앉으세요. '
          '아프다고 다리를 주무르시면서도 앉지 않고 계속 걸으셨어요.'),
         ('집에서는 어떻게 지내세요?',
          '집 안에서는 가만히 못 계시고 방이랑 거실을 왔다 갔다 하세요.')],
        [v.spec('rest', 'is_walking and fatigue_high and not pain_observed', ids=('N1', 'N2'), hold=5),
         v.spec('walk', 'is_walking and pain_observed', ids=('N2',))],
        [v.case('trigger', v.scene(fatigue_high=True, continuous_walk_minutes=76, distance_since_rest_m=3650),
                ['rest'], '통증 없이 기운이 빠졌으므로 앉아 쉰다.'),
         v.case('non_trigger', v.nearby('park', continuous_walk_minutes=15, distance_since_rest_m=720),
                ['baseline'], '공원 벤치가 가까워도 기운이 빠지지 않았고 통증도 없다.'),
         v.case('boundary_or_release', v.scene(fatigue_high=True, pain_observed=True,
                                               continuous_walk_minutes=80, distance_since_rest_m=3840),
                ['walk'], '지쳤어도 무릎 통증이 시작되면 쉬지 않고 계속 걷는다.'),
         v.case('unobserved_or_conflict', v.scene(fatigue_high=True, pain_observed=None,
                                                  continuous_walk_minutes=78, distance_since_rest_m=3740),
                [], '기운이 빠졌지만 통증 여부를 모르면 쉴지 계속 걸을지 갈린다.', status='unknown',
                possible=['rest', 'walk'])],
        '평소에는 기운이 빠지면 아무 데나 앉아 5분쯤 쉬지만, 무릎 통증이 시작되면 오히려 앉지 않고 계속 걷는다. '
        '공원과 시장 골목 모두에서 본 모습이라 장소 한정이 아니다. 집 안에서 왔다 갔다 하는 것은 실내 모습이라 '
        '바깥 보행 규칙이 아니다. 통증은 관측 주입 사실이라 실종 상황에서 관측이 없으면 지친 뒤 쉬기와 계속 걷기로 갈린다. '
        '직접 근거는 보호자 관찰(local:C25)이고 DM-29는 아파도 쉬지 않는 집단 경향의 배경이다.',
        ['피로 휴식에 통증 없음 조건이 붙는지',
         '통증이 있으면 쉬기 대신 계속 걷기인지(두 규칙이 동시에 참이 되지 않는지)',
         '통증 미관측 시 쉬기와 계속 걷기를 함께 가능성으로 남기는지',
         '벤치가 가까워도 기운이 빠지지 않았으면 쉬지 않는지',
         '실내 서성임을 바깥 계속 걷기로 옮기지 않는지'])

    v.persona(
        'R_rest_endurance_05', 'rest_endurance',
        ['local:C25', 'local:C07'],
        [{'label': '물레방아 정자', 'place_type': 'park'},
         {'label': '물푸레 반찬골목', 'place_type': 'market'},
         {'label': '외가 옛집', 'place_type': 'past_home'}],
        [('할머님이 사시는 동네를 간단히 소개해 주시겠어요?',
          '집 앞에 작은 공원이 있고 그 안에 물레방아 정자가 있어요. 물푸레 반찬골목은 반찬거리 사러 다니시던 데고, '
          '외가 옛집은 할머니가 오래 사시다 이사 나온 집이에요.'),
         ('걷다가 어디서 쉬시는지 아세요?',
          '제 가게가 공원 바로 맞은편이라 창으로 정자가 보여요. '
          '기운 없이 터덜터덜 오시는 날은 정자에 들어가서 앉으시고, 기운 있게 오시는 날은 그냥 지나가세요. '
          '한번 앉으시면 한 시간은 꼼짝 안 하세요.'),
         ('걸음은 어떠세요?',
          '보행기를 밀고 다니셔서 걸음이 느려요.')],
        [v.spec('rest', 'is_walking and fatigue_high', ids=('N1',), labels=('물레방아 정자',), hold=60)],
        [v.case('trigger', v.scene(current_place_label='물레방아 정자', fatigue_high=True,
                                   continuous_walk_minutes=74, distance_since_rest_m=1850),
                ['rest'], '기운이 빠진 채 그 정자를 지나므로 들어가 앉는다.'),
         v.case('non_trigger', v.scene(current_place_label='물레방아 정자',
                                       continuous_walk_minutes=28, distance_since_rest_m=700),
                ['baseline'], '기운 있게 지나가는 날은 정자에 앉지 않는다.'),
         v.case('boundary_or_release', v.nearby('park', fatigue_high=True,
                                               continuous_walk_minutes=80, distance_since_rest_m=2000),
                ['baseline'], '지쳤어도 그 정자가 아닌 다른 공원 근처에서는 앉는 모습이 관찰되지 않았다.'),
         v.case('unobserved_or_conflict', v.scene(current_place_label=None, fatigue_high=True,
                                                  continuous_walk_minutes=76, distance_since_rest_m=1900),
                [], '지쳤지만 지금 그 정자에 있는지 모르면(등록 장소 위치 미확인) 앉을지 단정할 수 없다.',
                status='unknown', possible=['baseline', 'rest'])],
        '기운이 빠진 날 공원 안 물레방아 정자를 지나면 들어가 한 시간가량 앉는 장소 한정 휴식이다. 보호자는 가게 창으로 '
        '정자 쪽만 볼 수 있어 다른 곳의 휴식은 관찰되지 않았고, 규칙을 다른 공원이나 공원 유형 전체로 넓히지 않는다. '
        '조건에 피로가 있어 걷는 중 하나뿐인 퇴화 조건이 아니다. 브리프의 엔진 설명상 휴식이 끝나면 피로가 줄어 '
        '정자 근처에서 곧바로 다시 앉는 흡수 지점이 되지 않는다(실행 확인 안 함). 보행기 사용은 속도 개인차라 표현할 수 없다. '
        '직접 근거는 보호자 관찰(local:C25)이고 local:C07은 보행 보조기구 사용의 배경이다.',
        ['휴식이 그 정자 라벨에 한정되고 다른 공원이나 공원 유형 전체로 넓어지지 않는지',
         '기운 있는 날 정자를 지나칠 때는 앉지 않는지(피로 조건)',
         '한 시간 지속이 hold로 옮겨지는지',
         '정자에 있는지 모르면 단정하지 않는지',
         '보행기 사용에 임의 수치를 붙이지 않는지'],
        unsupported_sentences=('N2.s1',))

    v.persona(
        'R_rest_endurance_06', 'rest_endurance',
        ['local:C25'],
        [{'label': '호숫가 산책로', 'place_type': 'park'},
         {'label': '옛 양조장', 'place_type': 'workplace'},
         {'label': '중앙 버스터미널', 'place_type': 'station'}],
        [('장인어른께서는 하루를 보통 어떻게 보내세요?',
          '아침 드시고 나면 호숫가 산책로를 걸으시거나 동네를 다니세요. 옛 양조장은 젊어서 일하시던 곳이고, '
          '버스터미널은 고향 내려가실 때 늘 이용하시던 데예요.'),
         ('낮에 걸으실 때 체력은 어떠세요?',
          '낮에는 두 시간을 걸으셔도 끄떡없으세요.'),
         ('저녁에는 달라지시나요?',
          '네, 저녁 다섯 시가 넘으면 기운이 확 떨어지세요. '
          '휴대폰 걸음 기록을 같이 보니까 그 시간 이후에는 22분쯤만 걸으셔도 길가 아무 데나 주저앉으시더라고요. '
          '앉으시면 한참을 그대로 계세요.')],
        [v.spec('rest', 'is_walking and clock_hour >= 17 and continuous_walk_minutes >= 22', ids=('N2',))],
        [v.case('trigger', v.nearby('water', clock_hour=18.5, continuous_walk_minutes=24, distance_since_rest_m=1150),
                ['rest'], '저녁 다섯 시 이후 22분쯤을 넘겨 걸었으므로 주저앉아 쉰다.'),
         v.case('non_trigger', v.scene(clock_hour=13.5, continuous_walk_minutes=70, distance_since_rest_m=3360),
                ['baseline'], '낮에는 오래 걸어도 거뜬하다는 능력 진술뿐이라 휴식 반응이 없다.'),
         v.case('boundary_or_release', v.scene(clock_hour=16.75, continuous_walk_minutes=40, distance_since_rest_m=1920),
                ['baseline'], '다섯 시 직전이라 저녁 휴식이 아직 적용되지 않는다.'),
         v.case('unobserved_or_conflict', v.scene(clock_hour=18.25, continuous_walk_minutes=26,
                                                  distance_since_rest_m=1250, dark_observed=None),
                ['rest'], '어둠 관측이 없어도 보호자가 말한 기준은 시계 시각이다. '
                          '저녁을 어둠 관측으로 바꾸면 실종 상황에서 휴식이 늘 미확정이 된다.')],
        '낮에는 두 시간도 거뜬하다는 능력 진술뿐이고, 저녁 다섯 시 이후에는 22분쯤 걸으면 주저앉아 쉰다. '
        '휴식 지속은 "한참"이라 수치가 없다(hold 없음, 부분 손실). 시각 조건이 17시 이상뿐이라 자정을 넘기면(0시 이후) '
        '저녁 휴식이 꺼진다. 원문이 심야를 말하지 않아 정답은 바꾸지 않지만, 밤을 넘기는 시뮬레이션에서는 개인 휴식이 '
        '사라진다. 직접 근거는 보호자 관찰(local:C25)뿐이며 저녁 피로를 받치는 문헌은 브리프에 없다.',
        ['낮 체력(두 시간) 진술이 휴식·걷기 규칙이 되지 않는지',
         '저녁 시각과 보행 시간이 함께 필요한지(AND)',
         '"한참"에 임의 지속시간을 붙이지 않는지(hold 없음)',
         '저녁을 어둠 관측으로 바꾸지 않는지(어둠 미관측에서도 휴식)'],
        unsupported_sentences=('N2.s3',))

    v.persona(
        'R_rest_endurance_07', 'rest_endurance',
        ['local:C25', 'corpusA:DM-14'],
        [{'label': '시외버스 정류장', 'place_type': 'station'},
         {'label': '대장간 골목', 'place_type': 'workplace'},
         {'label': '옛 하숙집', 'place_type': 'past_home'}],
        [('할아버님 소개를 간단히 부탁드려요.',
          '대장간 골목에서 평생 쇠 다루는 일을 하셨어요. 옛 하숙집은 젊을 때 도시로 올라와 머무셨던 집이고, '
          '시외버스 정류장은 동네 어귀에 있는 정류장이에요.'),
         ('걸으시다가 언제쯤 앉으시는지 짐작 가는 게 있으세요?',
          '할아버지 손목에 채워 드린 만보기 시계에 걸은 시간이랑 거리가 다 찍혀요. '
          '앉으신 때를 보면 늘 40분은 넘게 걸으셨고 거리도 1.6킬로는 넘었더라고요. '
          '동네 골목을 천천히 빙빙 도신 날은 한 시간 가까이 걸으셔도 안 앉으셨어요. '
          '기분 좋게 성큼성큼 1.8킬로를 금방 가신 날도 안 앉으셨고요. '
          '앉으시면 4분 정도 숨 고르시고 바로 일어나세요.'),
         ('쉬고 나서는 어디로 가세요?',
          '쉬고 나면 꼭 왔던 길로 되돌아가세요. 지난번에 없어지셨을 때는 시외버스 정류장 의자에 앉아 계신 걸 찾았어요.'),
         ('걸음은 빠른 편이세요?',
          '연세에 비해 걸음이 빨라서 제가 따라가려면 숨이 차요.')],
        [v.spec('rest', 'is_walking and continuous_walk_minutes >= 40 and distance_since_rest_m >= 1600',
                ids=('N1',), hold=4)],
        [v.case('trigger', v.scene(continuous_walk_minutes=46, distance_since_rest_m=2100),
                ['rest'], '걸은 시간 40분과 거리 1.6킬로를 모두 넘겨 앉는다.'),
         v.case('non_trigger', v.scene(continuous_walk_minutes=58, distance_since_rest_m=1250),
                ['baseline'], '천천히 돈 날처럼 시간은 길어도 거리가 1.6킬로에 못 미쳐 앉지 않는다.'),
         v.case('boundary_or_release', v.scene(continuous_walk_minutes=37, distance_since_rest_m=1800),
                ['baseline'], '성큼성큼 간 날처럼 거리는 넘었어도 시간이 40분에 못 미쳐 앉지 않는다.'),
         v.case('unobserved_or_conflict', v.scene(current_place_label='시외버스 정류장', lost_awareness=None,
                                                  continuous_walk_minutes=30, distance_since_rest_m=1400),
                ['baseline'], '정류장에서 한 번 발견된 일은 습관이 아니라서, 길 잃음 인식이 미관측이어도 '
                              '정류장 휴식이나 목적지가 생기지 않는다. 시간·거리도 아직 덜 찼다.')],
        '걸은 시간 40분과 거리 1.6킬로를 모두 넘겼을 때 4분 정도 쉬는 휴식이다(만보기 시계 기록). 시간만 길었던 날과 '
        '거리만 길었던 날 모두 앉지 않아 한쪽만으로는 쉬지 않는다. 엔진은 속도가 분당 48미터로 고정이라 1.6킬로에 약 '
        '33분 만에 닿고, 엔진 안에서는 사실상 40분 조건이 휴식 시점을 정한다. 시간과 거리를 가르는 장면은 규칙 구조 '
        '시험일 뿐이며, 장면 속 걸음(분당 약 22~49미터)은 빠른 날과 느린 날 관찰에 맞췄다. 쉰 뒤 왔던 길로 돌아가는 '
        '순서와 빠른 걸음은 표현할 수 없고, 정류장에서 발견된 일은 단발 장면이다. '
        '직접 근거는 보호자 관찰(local:C25)이고 DM-14는 빠른 걸음의 배경이다.',
        ['시간과 거리가 모두 차야 쉬는지(AND)',
         '시간만 긴 장면과 거리만 긴 장면에서 쉬지 않는지',
         '4분 휴식이 hold로 옮겨지는지',
         '정류장 발견 장면을 정류장 휴식이나 목적지로 만들지 않는지(길 잃음 미관측 포함)',
         '"쉬고 나면 왔던 길로"와 빠른 걸음을 다른 행동이나 수치로 바꾸지 않는지'],
        unsupported_sentences=('N2.s1', 'N3.s1'))

    v.persona(
        'R_rest_endurance_08', 'rest_endurance',
        ['local:C25', 'corpusA:DM-29', 'webB:C42'],
        [{'label': '버들천 산책로', 'place_type': 'park'},
         {'label': '달개비 정형외과', 'place_type': 'hospital'},
         {'label': '옛 정미소', 'place_type': 'workplace'}],
        [('버들천 산책로는 집에서 가까운가요?',
          '네, 집 앞 하천 길이에요. 달개비 정형외과는 무릎 때문에 몇 년째 물리치료 받으러 다니시는 병원이고, '
          '옛 정미소는 아버님이 하시던 방앗간 자리예요.'),
         ('평소에 걸으시다가 쉬시나요?',
          '600미터쯤 걸으시면 앉으세요. 산책로에 거리 표시가 있어서 보면 늘 그 언저리에서 앉으시더라고요. '
          '같이 장 보러 갈 때도 집에서 그쯤 가면 한 번 앉으세요. 앉으시면 40분은 계세요.'),
         ('다리가 아프실 때는요?',
          '무릎이 쑤신다고 하시면 쉬지도 않고 곧장 달개비 정형외과 쪽으로 걸어가세요. '
          '혼자서 병원 앞까지 가 계신 걸 몇 번 봤어요.'),
         ('길을 잃으시면 어떻게 하실 것 같으세요?',
          '글쎄요, 아마 어디 앉아서 쉬고 계시지 않을까 싶어요.')],
        [v.spec('rest', 'is_walking and distance_since_rest_m >= 600 and not pain_observed',
                ids=('N1', 'N2'), hold=40),
         v.spec('seek_1', 'is_walking and pain_observed', ids=('N2',))],
        [v.case('trigger', v.scene(distance_since_rest_m=650, continuous_walk_minutes=14),
                ['rest'], '산책로가 아닌 곳에서도 통증 없이 600미터를 넘기면 앉아 쉰다.'),
         v.case('non_trigger', v.scene(lost_awareness=True, distance_since_rest_m=240, continuous_walk_minutes=5),
                ['baseline'], '길을 잃으면 앉아 있을 거라는 말은 추측일 뿐이고, 거리도 600미터 전이다.'),
         v.case('boundary_or_release', v.scene(pain_observed=True, distance_since_rest_m=660, continuous_walk_minutes=14),
                ['seek_1'], '600미터를 넘겼어도 무릎 통증이 보이면 쉬지 않고 다니던 정형외과로 향한다.'),
         v.case('unobserved_or_conflict', v.scene(pain_observed=None, distance_since_rest_m=700, continuous_walk_minutes=15),
                [], '600미터는 넘겼지만 통증 여부를 모르면 앉아 쉴지 병원으로 향할지 갈린다.', status='unknown',
                possible=['rest', 'seek_1'])],
        '통증이 없으면 600미터쯤마다 40분 앉아 쉬고(산책로 거리 표시와 장 보러 가는 길 모두에서 관찰돼 산책로 한정이 아니다), '
        '무릎 통증이 있으면 쉬지 않고 다니던 정형외과로 걸어간다. "쉬지도 않고"는 목적지 출발로만 옮겨지고, 출발 중에는 '
        '모집단 휴식이 끼어들 수 있어 부분 손실이다. 통증은 관측 주입 사실이라 실종 상황에서 관측이 없으면 600미터 전에는 '
        '기본 이동과 병원 출발, 그 뒤에는 휴식과 병원 출발로 늘 갈린다. 길을 잃었을 때의 모습은 보호자 추측이다. '
        '직접 근거는 보호자 관찰(local:C25)이고 DM-29·webB:C42는 통증 시 휴식 거부와 이동의 배경이다.',
        ['통증 시 휴식 대신 병원 출발(seek_1)인지',
         '휴식을 산책로나 공원에 한정하지 않는지',
         '목적지 출발에 장소 한정을 붙이지 않는지',
         '길 잃음 추측을 휴식 규칙으로 만들지 않는지',
         '통증 미관측 시 휴식과 병원 출발을 함께 가능성으로 남기는지'])

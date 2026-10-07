"""Evaluation personas, family multiple_behaviors (AI draft, unreviewed).

Two or three behaviors in one person: rest + waiting, avoidance + destination,
representable behavior + unrepresentable trait, explicit or unstated priority,
and a person for whom only one behavior was actually observed. Written from the
family brief (multiple_behaviors.json) and the DSL only; no development data
was read. Priority is encoded only where the guardian states it; an overlap the
guardian never saw stays unknown. Two moving behaviors (seek + avoid) are not
used as a conflict scene, because they can co-occur. Revised 2026-10-07 after an
independent review (type-level wording, evening-but-not-dark scenes, single rest
limit for 05). Hold minutes are not scored by scene_pass; those checks are for
human review. Draft for human review, not clinical evidence.
"""

FAMILY = 'multiple_behaviors'


def register(v):
    # 01: 휴식(연속 보행 시간, 유지 시간 명시) + 길 잃음 인지 시 그 자리에 서 있기. 겹침은 보호자가 본 적 없음.
    v.persona(
        pid='R_multiple_behaviors_01', family=FAMILY,
        research_basis=('local:C25', 'corpusA:DM-27', 'local:C07', 'webB:C31', 'local:C17'),
        places=[{'label': '두꺼비 어린이공원', 'place_type': 'park'},
                {'label': '옛 양복점 자리', 'place_type': 'workplace'},
                {'label': '큰누나네 오피스텔', 'place_type': 'relative_home'}],
        qa=[('목록에 넣어 두신 곳들은 아버님께 어떤 곳이에요?',
             '두꺼비 공원은 집 앞이라 넣었고, 양복점 자리는 아버지가 젊을 때 일하시던 데예요. '
             '큰누나네는 혹시 몰라서 적었어요. 요즘 그쪽으로 가신다는 말씀은 없으세요.'),
            ('혼자 걸으실 때 중간에 쉬시는 편인가요?',
             '쉬지 않고 사십 분을 넘게 걸으시면 허리를 짚으면서 아무 데나 걸터앉으세요. '
             '한번 앉으시면 십오 분은 일어나질 않으세요.'),
            ('혼자 계시다가 길이 헷갈리시면 어떤 모습이세요?',
             '어디가 어딘지 모르겠다 싶으시면 전봇대든 가로수든 붙잡고 그 자리에 붙박인 듯 서 계세요. '
             '작년 겨울에 시장 뒷길에서 그러고 계신 걸 이웃 분이 보고 연락을 주셨어요.'),
            ('반대로 잘 모르시는 부분도 있을까요?',
             '오래 걸어서 지치신 데다 길까지 헷갈리시는 때는 본 적이 없어서, 그땐 어떻게 하실지 모르겠어요.')],
        rules=[v.spec('rest', 'is_walking and continuous_walk_minutes > 40', ids=('N1',), hold=15),
               v.spec('wait', 'lost_awareness', ids=('N2',))],
        cases=[
            v.case('trigger', v.scene(continuous_walk_minutes=44, distance_since_rest_m=2110), ['rest'],
                   '40분 넘게 이어 걸음, 길 잃음 인지 없음 → 휴식'),
            v.case('non_trigger', v.scene(continuous_walk_minutes=33, distance_since_rest_m=1580), ['baseline'],
                   '40분 전, 길 잃음 인지 없음 → 개인 반응 없음'),
            v.case('boundary_or_release', v.scene(lost_awareness=True, continuous_walk_minutes=38,
                                                  distance_since_rest_m=1820),
                   ['wait'], '40분 전에 길 잃음을 알아차림 → 휴식 한계 전이라 겹치지 않고 그 자리에 서 있기만'),
            v.case('unobserved_or_conflict', v.scene(lost_awareness=True, continuous_walk_minutes=46,
                                                     distance_since_rest_m=2210), [],
                   '휴식 한계와 길 잃음 인지가 겹침(멈춰 앉기와 서 있기). 보호자가 이 겹침을 본 적 없다고 함(N3)',
                   status='unknown', possible=['rest', 'wait']),
        ],
        summary='연속 보행 40분을 넘기면 15분 휴식, 길을 모르겠다 싶으면 무언가를 붙잡고 그 자리에 서 있는 대기가 공존. '
                '둘이 겹칠 때의 순서는 보호자가 관찰하지 못했다고 명시. 가족이 오면 풀린다는 진술은 없음.',
        checks=['보행 40분 초과면 rest(hold 15는 장면 채점 밖, 사람 검토)', '40분 전 길 잃음 인지는 wait 하나',
                '가족 유무 조건은 원문에 없음(어느 쪽으로 써도 장면 채점 밖)',
                '휴식·대기 동시 성립 시 우선순위를 지어내지 않고 unknown(rest, wait)',
                '등록 장소(옛 직장·친척 집)로 출발하는 규칙을 만들지 않음'],
    )

    # 02: 불안할 때 옛 직장 쪽으로 출발 + 어느 공원이든 붐비면 회피. 시장은 소음·붐빔 모두 반응 없음.
    #     출발과 회피는 함께 성립할 수 있는 이동이라 충돌 장면으로 쓰지 않음.
    v.persona(
        pid='R_multiple_behaviors_02', family=FAMILY,
        research_basis=('webA:C09', 'webB:C38', 'webB:C40', 'corpusA:DM-20', 'local:C25'),
        places=[{'label': '제일제면소 터', 'place_type': 'workplace'},
                {'label': '배나무골 근린공원', 'place_type': 'park'},
                {'label': '윗동네 골목시장', 'place_type': 'market'}],
        qa=[('등록하신 세 곳을 간단히 설명해 주시겠어요?',
             '제면소 터는 어머니가 한평생 국수 뽑던 공장 자리예요. 지금은 주차장이 됐어요. '
             '공원하고 시장은 그냥 동네에 있는 데라 같이 적었어요.'),
            ('밖에서 마음이 불안해 보이실 때 특별히 하시는 행동이 있나요?',
             '마음이 불안해지시면 꼭 제면소에 가 봐야 한다고 그쪽으로 발길을 돌리세요. '
             '지난봄에도 두 번이나 그렇게 가시다가 이웃 분이 모시고 오셨어요.'),
            ('사람 많은 곳은 어떠세요?',
             '공원이 어디든 사람이 바글바글하면 질색을 하시고 그 옆으로는 아예 안 지나가려고 하세요. '
             '동네 공원이든 큰 공원이든 똑같아요. 한산할 때는 공원 안으로도 잘 들어가세요.'),
            ('시장 쪽은 어떠세요?', '시장은 시끄럽든 사람이 붐비든 별 상관 안 하고 다니세요.')],
        rules=[v.spec('seek_0', 'anxiety_high', ids=('N1',)),
               v.spec('avoid_park', 'park.crowded', ids=('N2',))],
        cases=[
            v.case('trigger', v.scene(anxiety_high=True), ['seek_0'],
                   '불안이 높고 공원 근처가 아님 → 옛 제면소 쪽으로 출발'),
            v.case('non_trigger', v.nearby('market', noisy=True, crowded=True), ['baseline'],
                   '시끄럽고 붐비는 시장 근처. 시장은 소음·붐빔 모두 상관없다고 함(N3), 불안 없음'),
            v.case('boundary_or_release', v.nearby('park', noisy=True, crowded=False), ['baseline'],
                   '공원 근처가 시끄럽기만 하고 붐비지는 않음 → 회피하지 않음'),
            v.case('unobserved_or_conflict', v.nearby('park', crowded=None), [],
                   '공원 근처인데 붐비는지 관측되지 않음 → 회피 여부 미정',
                   status='unknown', possible=['avoid_park', 'baseline']),
        ],
        summary='불안해지면 옛 직장(제면소 터)으로 향하는 목적지 행동과, 어느 공원이든 붐비면 피하는 유형 회피가 공존. '
                '둘이 겹칠 때의 순서는 진술이 없고, 함께 성립할 수 있는 이동이라 장면으로 채점하지 않음. '
                '시장은 소음·붐빔 모두 반응 없음(피하지 않는다는 말을 행동으로 바꾸지 않음). '
                'webB:C38·C40은 출발 동기 근거라 실종 중 방향 전환에는 간접 근거.',
        checks=['불안 시 seek_0, 목표를 장소 범위로 바꾸지 않음',
                '공원 회피는 유형 전체(등록 공원 한정 아님), 붐빌 때만이고 소음만으로는 아님',
                '시장에 대한 규칙 없음(붐벼도 회피 아님)', '붐빔 미관측 시 unknown(avoid_park, baseline)'],
    )

    # 03: 지치거나 아파도 쉬지 않고 계속 걷기 + 표현 불가 특성 두 개(마을버스 무작정 탑승, 처음 방향 고수).
    v.persona(
        pid='R_multiple_behaviors_03', family=FAMILY,
        research_basis=('corpusA:DM-29', 'corpusA:DM-14', 'webA:C10', 'webB:C47', 'webA:C01', 'local:C25'),
        places=[{'label': '세탁소 앞 버스정류장', 'place_type': 'station'},
                {'label': '푸른 내과의원', 'place_type': 'hospital'}],
        qa=[('이 두 곳은 왜 넣으셨어요?',
             '정류장은 아버님이 예전에 버스 타시던 곳이고, 내과는 한 달에 한 번 약 타러 가는 데예요.'),
            ('혼자 걸으시다 힘에 부치실 때는 어떻게 하세요?',
             '단지 산책로를 혼자 도시는 걸 베란다에서 내려다보면, 숨이 턱에 차셔도 앉을 생각을 안 하세요. '
             '무릎이 아프다고 혼잣말을 하시면서도 그냥 걸음을 옮기세요.'),
            ('밖에서 버스나 지하철을 타신 적이 있나요?',
             '마을버스가 정류장에 서 있으면 어디 가는 차인지 보지도 않고 일단 오르세요. '
             '작년에 그렇게 타셨다가 종점에서 기사님이 연락을 주셨어요.'),
            ('걸으실 때 방향은 어떻게 잡으세요?',
             '현관을 나서서 처음 잡은 방향에서 좀처럼 벗어나질 않으세요.')],
        rules=[v.spec('walk', 'is_walking and (fatigue_high or pain_observed)', ids=('N1',))],
        cases=[
            v.case('trigger', v.scene(fatigue_high=True, continuous_walk_minutes=52, distance_since_rest_m=2490),
                   ['walk'], '혼자 걷다가 지침 → 앉지 않고 계속 걷기'),
            v.case('non_trigger', v.scene(continuous_walk_minutes=46, distance_since_rest_m=2200), ['baseline'],
                   '오래 걸었지만 지침·통증 없음 → 개인 반응 없음. 휴식 규칙도, 버스·방향 특성 규칙도 없음'),
            v.case('boundary_or_release', v.scene(pain_observed=True, continuous_walk_minutes=14,
                                                  distance_since_rest_m=670),
                   ['walk'], '지친 상태는 아니지만 무릎 통증이 관찰됨 → 통증 쪽으로도 계속 걷기'),
            v.case('unobserved_or_conflict', v.scene(pain_observed=None, continuous_walk_minutes=27,
                                                     distance_since_rest_m=1300), [],
                   '지침은 없고 통증 여부는 관측되지 않음 → 계속 걷기 여부 미정',
                   status='unknown', possible=['baseline', 'walk']),
        ],
        summary='혼자 걸을 때 지치거나 무릎이 아파도 쉬지 않고 계속 걷기(베란다에서 관찰). 마을버스 무작정 탑승과 '
                '처음 방향 고수는 현행 계약으로 표현할 수 없는 특성이라 원문으로만 보존.',
        checks=['지침 또는 통증이면 walk(보행 중)', '지침·통증 없는 장시간 보행에 rest나 walk를 만들지 않음',
                '버스 탑승을 정류장 seek로 바꾸지 않음', '처음 방향 고수를 walk 규칙으로 만들지 않음',
                '통증 미관측 시 unknown(baseline, walk)'],
        unsupported_sentences=('N2.s1', 'N3.s1'),
    )

    # 04: 세 행동 — 휴식(시간) + 어두우면 쉬지 않고 계속 걷기 + 비 오면 처마 밑 대기.
    #     어둠 > 휴식은 명시, 비와 어둠이 겹칠 때는 미관찰. 저녁 시각이지만 어둡지 않은 장면으로 시각 추정을 거름.
    v.persona(
        pid='R_multiple_behaviors_04', family=FAMILY,
        research_basis=('local:C25', 'corpusA:DM-44', 'webB:C36', 'webB:C26', 'webB:C27',
                        'webB:C56', 'corpusA:DM-29'),
        places=[{'label': '참샘 약수터', 'place_type': 'park'},
                {'label': '복개천 먹자골목', 'place_type': 'market'},
                {'label': '어릴 적 살던 장터마을', 'place_type': 'past_home'}],
        qa=[('적어 두신 장소들이 어머님께 어떤 의미인지 알려 주세요.',
             '약수터는 아침마다 물 뜨러 다니시던 데고, 먹자골목은 장 보러 가시는 길이에요. '
             '장터마을은 어머니가 어릴 때 사신 동네인데, 거기 가겠다고 하신 적은 없어요.'),
            ('보통 얼마나 걸으시면 쉬세요?',
             '35분을 넘게 걸으시면 다리가 무겁다고 길가 의자나 계단에 앉으세요. '
             '그렇게 7분쯤 앉아 계시다가 다시 일어나 걸으세요.'),
            ('날이 어두워지면 달라지는 점이 있나요?',
             '해가 지고 깜깜해지면 그때부턴 다리가 아프다고 하셔도 앉질 않으시고 계속 걸으세요. '
             '집에 가야 한다면서 걸음을 더 서두르세요.'),
            ('비가 오는 날에는 어떠세요?',
             '비가 떨어지면 가게 차양 밑 같은 데 들어가서 그칠 때까지 서 계세요. '
             '비 오는 밤에는 어떻게 하시는지 본 적이 없어요.')],
        rules=[v.spec('rest', 'is_walking and continuous_walk_minutes > 35 and not dark_observed',
                      ids=('N1', 'N2'), hold=7),
               v.spec('walk', 'dark_observed', ids=('N2',)),
               v.spec('wait', 'rain_observed', ids=('N3',))],
        cases=[
            v.case('trigger', v.scene(dark_observed=True, pain_observed=True, fatigue_high=True, clock_hour=18.9,
                                      continuous_walk_minutes=48, distance_since_rest_m=2300), ['walk'],
                   '어두움 + 35분 초과 보행 + 다리 통증·피로 → 휴식 대신 계속 걷기(보호자 명시 우선)'),
            v.case('non_trigger', v.scene(clock_hour=19.4, dark_observed=False, continuous_walk_minutes=21,
                                          distance_since_rest_m=1010), ['baseline'],
                   '저녁 일곱 시가 넘었지만 아직 어둡지 않다고 관측됨, 35분 전, 비 없음 → 개인 반응 없음'),
            v.case('boundary_or_release', v.scene(clock_hour=18.4, dark_observed=False, continuous_walk_minutes=38,
                                                  distance_since_rest_m=1820), ['rest'],
                   '저녁 시각이지만 어둡지 않다고 관측됨 + 35분 넘김 → 계속 걷기가 아니라 7분 휴식'),
            v.case('unobserved_or_conflict', v.scene(dark_observed=True, rain_observed=True, pain_observed=True,
                                                     fatigue_high=True, clock_hour=20.1,
                                                     continuous_walk_minutes=16, distance_since_rest_m=770),
                   [], '비 오는 밤은 본 적 없음 → 계속 걷기와 비 피해 대기 중 미정',
                   status='unknown', possible=['wait', 'walk']),
        ],
        summary='35분 넘게 걸으면 7분 휴식, 어두워지면 쉬지 않고 계속 걷기(휴식보다 우선이라고 명시), 비 오면 '
                '그칠 때까지 대기. 비 오는 밤은 관찰 공백. 서두르는 걸음·귀가 의도는 표현 불가.',
        checks=['어두울 때 휴식 규칙이 꺼지고 walk만 남음(통증·피로 조건을 붙인 walk도 같은 판정이 되도록 장면에 통증·피로를 넣음)',
                '저녁 시각이라도 어둠이 관측되지 않으면 35분 초과 시 rest(hold 7은 장면 채점 밖, 사람 검토)',
                '시각만으로 어둠을 추정하지 않음(non_trigger·boundary가 저녁 시각·어둠 없음)',
                '비 오면 wait, 해제 시간 없음', '비+어둠은 unknown(wait, walk)', '어릴 적 동네로 가는 규칙 없음'],
        unsupported_sentences=('N2.s2',),
    )

    # 05: 한 행동만 관찰 — 휴식(걷기 시작 후 26분, 세 번 관찰). 나머지는 추측·본인 말·앞에서 했다가 정정한 진술.
    v.persona(
        pid='R_multiple_behaviors_05', family=FAMILY,
        research_basis=('local:C25', 'local:C07', 'corpusB:C19', 'corpusB:C20', 'corpusB:C39', 'corpusB:C45',
                        'local:C17'),
        places=[{'label': '까치울 체육공원', 'place_type': 'park'},
                {'label': '시립 보건소', 'place_type': 'hospital'}],
        qa=[('등록하신 곳은 각각 어떤 곳인가요?',
             '체육공원은 남편이 매일 운동하러 가는 데고, 보건소는 혈압약 때문에 다녀요.'),
            ('혼자 다니실 때 쉬는 모습을 보신 적 있나요?',
             '운동 나갈 때 몇 번 몰래 뒤를 밟으면서 시계를 봤어요. '
             '세 번 다 걷기 시작하고 스물여섯 분이 지나니까 아무 데나 걸터앉더라고요.'),
            ('해가 지면 어떤가요?', '해가 지면 길가에 그냥 주저앉아 계세요.'),
            ('길을 잃으시면 어떻게 하실 것 같으세요?',
             '아마 지나가는 사람한테 물어보지 않을까 싶어요. 실제로 그런 걸 본 적은 없어요.'),
            ('비 오는 날은 어떠세요?',
             '본인 말로는 비 오면 버스 정류장 지붕 밑에서 비를 긋는다고 하는데, 제가 본 건 아니에요.'),
            ('앞에서 하신 말씀 중에 바로잡을 게 있을까요?',
             '아까 해 지면 길가에 주저앉는다고 한 건 제가 시어머니랑 헷갈린 거예요. '
             '남편이 어두울 때 어떤지는 저도 몰라요.')],
        rules=[v.spec('rest', 'is_walking and continuous_walk_minutes >= 26', ids=('N1',))],
        cases=[
            v.case('trigger', v.scene(continuous_walk_minutes=29, distance_since_rest_m=1390), ['rest'],
                   '걷기 시작하고 26분을 넘김 → 휴식'),
            v.case('non_trigger', v.scene(lost_awareness=True, rain_observed=True, dark_observed=True,
                                          continuous_walk_minutes=9, distance_since_rest_m=430),
                   ['baseline'], '길 잃음·비·어둠이 모두 있어도 추측·본인 말·정정된 진술이라 반응 없음'),
            v.case('boundary_or_release', v.scene(continuous_walk_minutes=24, distance_since_rest_m=1150),
                   ['baseline'], '26분 직전 → 아직 휴식 없음'),
            v.case('unobserved_or_conflict', v.scene(current_action=None, continuous_walk_minutes=31,
                                                     distance_since_rest_m=1490),
                   [], '지금 걷는 중인지 모름 → 휴식 여부 미정', status='unknown', possible=['baseline', 'rest']),
        ],
        summary='실제 관찰은 휴식 하나(걷기 시작 후 26분, 세 번 관찰, 유지 시간 미상). 길 잃었을 때 묻기는 보호자 추측, '
                '비 피하기는 본인 말 전달, 해 지면 주저앉기는 앞에서 말했다가 시어머니와 혼동이었다고 정정. '
                '어두울 때 모습은 관찰 공백.',
        checks=['보행 26분 이상이면 rest, 보행 중 조건 포함, hold 없음(0)', '원문에 없는 거리 한계를 지어내지 않음',
                '정정 전 진술(N2)로 wait·rest 규칙을 만들지 않음', '길 잃음·비에 규칙을 만들지 않음',
                '본인 말·추측을 관찰로 승격하지 않음', '보행 여부 미관측 시 unknown(baseline, rest)'],
    )

    # 06: 목적지(어두워지면 옛집 쪽) + 비 오면 대기(비가 우선이라고 명시) + 표현 불가(큰길만 따라감).
    v.persona(
        pid='R_multiple_behaviors_06', family=FAMILY,
        research_basis=('corpusA:DM-20', 'webA:C05', 'webB:C05', 'webA:C46', 'webB:C36', 'local:C24'),
        places=[{'label': '감나무 옛집', 'place_type': 'past_home'},
                {'label': '둑방 산책로', 'place_type': 'park'},
                {'label': '사거리 약국', 'place_type': 'hospital'}],
        qa=[('여기 적힌 곳들을 하나씩 설명해 주시겠어요?',
             '감나무 옛집은 아버지가 결혼하고 서른 해 가까이 사신 집인데 지금은 남이 살아요. '
             '둑방 산책로는 늘 걷던 코스고, 약국은 단골이라 넣었어요.'),
            ('밖에 계시다가 날이 저물면 어떻게 하세요?',
             '어둑해지면 꼭 감나무 집에 가야 한다고 그쪽으로 방향을 트세요. '
             '지난가을에 두 번 나가셨을 때 두 번 다 그 집 대문 앞에서 찾았어요.'),
            ('비가 오면 달라지나요?',
             '비가 오면 옛집 가시던 것도 잊어버리시고 아파트 현관이든 지하도 입구든 비 안 맞는 데로 들어가 서 계세요. '
             '비가 그치면 다시 걸으세요.'),
            ('그 집까지는 어떤 길로 가세요?', '큰길만 따라가세요. 골목으로는 절대 안 들어가세요.')],
        rules=[v.spec('seek_0', 'dark_observed and not rain_observed', ids=('N1', 'N2')),
               v.spec('wait', 'rain_observed', ids=('N2',))],
        cases=[
            v.case('trigger', v.scene(dark_observed=True, clock_hour=18.5), ['seek_0'],
                   '어두워짐, 비 없음 → 감나무 옛집 쪽으로 출발'),
            v.case('non_trigger', v.scene(clock_hour=17.8), ['baseline'],
                   '저녁 시각이지만 아직 어둡지 않다고 관측됨(미관측이 아님) → 시각으로 어둠을 추정하지 않음'),
            v.case('boundary_or_release', v.scene(dark_observed=True, rain_observed=True, clock_hour=19), ['wait'],
                   '어둡지만 비가 옴 → 옛집 가기를 멈추고 비 피해 대기(보호자 명시 우선)'),
            v.case('unobserved_or_conflict', v.scene(dark_observed=None, clock_hour=19.5), [],
                   '어둠 여부 미관측 → 옛집 출발 여부 미정', status='unknown', possible=['baseline', 'seek_0']),
        ],
        summary='어두워지면 옛집으로 향하고, 비가 오면 그 출발도 멈추고 그칠 때까지 대기(비 우선 명시). '
                '큰길만 따라가는 경로 습관은 표현 불가. 과거 발견지(대문 앞)는 관찰된 출발을 보강하는 맥락.',
        checks=['seek_0 목표를 장소 범위로 넣지 않음', '비가 오면 seek 대신 wait만',
                '시각만으로 어둠 추정 금지', '어둠 미관측 시 unknown(baseline, seek_0)'],
        unsupported_sentences=('N3.s1', 'N3.s2'),
    )

    # 07: 오후 네 시 반이 넘으면 옛 직장(떡집) 쪽으로 출발 + 쉰 뒤 1.5킬로를 넘기면 휴식.
    #     가는 길에도 휴식이 먼저라고 명시(이동과 멈춤의 실제 충돌). 예전 역할 의도 문장은 표현 불가.
    v.persona(
        pid='R_multiple_behaviors_07', family=FAMILY,
        research_basis=('webB:C38', 'webA:C09', 'webB:C26', 'webB:C27', 'local:C24', 'local:C25',
                        'corpusA:DM-25'),
        places=[{'label': '풍년 떡집', 'place_type': 'workplace'},
                {'label': '아랫장터', 'place_type': 'market'},
                {'label': '시냇가 놀이터', 'place_type': 'park'}],
        qa=[('이 장소들은 어머님께 어떤 곳이에요?',
             '떡집은 어머니가 스무 해 넘게 일하시던 곳이고, 아랫장터랑 놀이터는 집 근처라 적었어요.'),
            ('시간대에 따라 다니시는 곳이 달라지나요?',
             '오후 네 시 반이 넘으면 떡집 쪽으로 걸음을 돌리세요. '
             '반죽 올려놔야 한다고 혼잣말을 하시고요. '
             '지난달 두 번 혼자 나가셨을 때도 두 번 다 그 시간 지나서 떡집 가는 길목에서 찾았어요.'),
            ('걷다가 쉬어 가시는 건 어떠세요?',
             '휴대폰 만보기로 보면 쉬고 나서 1.5킬로를 넘기시면 꼭 한 번 앉으세요. '
             '떡집 쪽으로 가시는 길에도 그만큼 걸으셨으면 일단 앉았다 가세요. '
             '앉으시면 4분 정도 숨 고르고 일어나세요.')],
        rules=[v.spec('rest', 'is_walking and distance_since_rest_m > 1500', ids=('N2',), hold=4),
               v.spec('seek_0', 'clock_hour > 16.5 and distance_since_rest_m <= 1500', ids=('N1', 'N2'))],
        cases=[
            v.case('trigger', v.scene(clock_hour=17.1, continuous_walk_minutes=14, distance_since_rest_m=670),
                   ['seek_0'], '오후 네 시 반 이후, 쉰 뒤 아직 많이 걷지 않음 → 떡집 쪽으로 출발'),
            v.case('non_trigger', v.scene(clock_hour=16.2, continuous_walk_minutes=18, distance_since_rest_m=860),
                   ['baseline'], '네 시 반 전, 1.5킬로 전 → 개인 반응 없음'),
            v.case('boundary_or_release', v.scene(clock_hour=17.4, continuous_walk_minutes=34,
                                                  distance_since_rest_m=1630),
                   ['rest'], '네 시 반 이후라도 쉰 뒤 1.5킬로를 넘김 → 떡집 쪽 출발보다 휴식이 먼저(보호자 명시 우선)'),
            v.case('unobserved_or_conflict', v.scene(clock_hour=17.8, continuous_walk_minutes=None,
                                                     distance_since_rest_m=None),
                   [], '네 시 반 이후인데 쉰 뒤 얼마나 걸었는지 모름 → 휴식과 출발 중 미정',
                   status='unknown', possible=['rest', 'seek_0']),
        ],
        summary='오후 네 시 반이 넘으면 옛 직장(떡집) 쪽으로 출발(혼자 나간 두 번 모두 가는 길목에서 발견), 쉰 뒤 '
                '1.5킬로를 넘기면 4분 휴식이며 떡집으로 가는 길에도 휴식이 먼저(보호자 명시). '
                '반죽하러 가야 한다는 말은 예전 역할 이행 의도라 표현 불가(webB:C38).',
        checks=['네 시 반 이후 seek_0, 목표를 장소 범위로 넣지 않음',
                '1.5킬로 초과 시 rest가 seek_0보다 우선(hold 4는 장면 채점 밖, 사람 검토)',
                '예전 역할 의도 문장(N1.s2)으로 별도 규칙을 만들지 않음', '장터·놀이터 규칙 없음',
                '거리 미관측 시 unknown(rest, seek_0)'],
        unsupported_sentences=('N1.s2',),
    )

    # 08: 길 잃음 인지 시 담벼락에 붙어 서 있기 + 해 진 뒤 숲 유형 회피 + 표현 불가(동네 묻기, 데려다주는 사람 따라가기).
    v.persona(
        pid='R_multiple_behaviors_08', family=FAMILY,
        research_basis=('local:C25', 'webB:C31', 'local:C17', 'corpusB:C45'),
        places=[{'label': '반달 전철역', 'place_type': 'station'},
                {'label': '막내삼촌네 빌라', 'place_type': 'relative_home'},
                {'label': '물레방아 공원', 'place_type': 'park'}],
        qa=[('등록된 장소마다 어떤 사연이 있나요?',
             '전철역은 할머니가 장 보러 가실 때 타시던 데고, 막내삼촌네는 걸어서 갈 만한 거리라 넣었어요. '
             '물레방아 공원은 집 바로 뒤라 같이 적었어요.'),
            ('밖에서 길을 잃으신 걸 본인도 아시는 것 같을 때가 있었나요?',
             '네, 길을 모르겠다 싶으시면 얼굴이 하얘지시면서 가까운 담벼락에 등을 딱 붙이고 꼼짝을 안 하세요. '
             '그러다 누가 말을 걸면 여기가 무슨 동네냐고 물어보세요. '
             '모셔다 드린다는 사람이 있으면 군말 없이 따라가세요.'),
            ('산이나 숲 쪽은 어떠세요?',
             '해가 떨어지고 나면 산이든 숲이든 나무 우거진 데는 무섭다고 근처에도 안 가세요. '
             '낮에는 뒷산에도 곧잘 오르세요.')],
        rules=[v.spec('wait', 'lost_awareness', ids=('N1',)),
               v.spec('avoid_forest', 'dark_observed', ids=('N2',))],
        cases=[
            v.case('trigger', v.nearby('forest', dark_observed=True, clock_hour=19.6), ['avoid_forest'],
                   '어두울 때 숲 가까이 → 숲 회피'),
            v.case('non_trigger', v.nearby('forest', clock_hour=13), ['baseline'],
                   '낮에 숲 가까이, 길 잃음 인지 없음 → 개인 반응 없음'),
            v.case('boundary_or_release', v.nearby('forest', clock_hour=19.2, dark_observed=False), ['baseline'],
                   '저녁 시각이지만 아직 어둡지 않다고 관측됨, 숲 가까이 → 회피 없음(시각으로 어둠을 추정하지 않음)'),
            v.case('unobserved_or_conflict', v.scene(lost_awareness=None), [],
                   '길 잃음을 알아차렸는지 모름 → 서 있기 여부 미정', status='unknown', possible=['baseline', 'wait']),
        ],
        summary='길을 잃은 걸 알면 담벼락에 등을 붙이고 그 자리에 서 있음, 해가 진 뒤에는 숲 유형 전체를 피함'
                '(등록 장소와 무관). 해 진 뒤 숲 회피 자체를 뒷받침하는 문헌 근거는 없어 개인 진술로만 둠. '
                '말을 거는 사람에게 동네 묻기와 데려다주는 사람 따라가기는 현행 계약에 사실·행동이 없어 원문 보존.',
        checks=['길 잃음 인지 시 wait(가족 해제 조건 없음)', '해가 진 뒤 숲 유형 회피(장소 한정 아님), 낮에는 없음',
                '저녁 시각만으로 어둠을 추정하지 않음', '동네 묻기·따라가기를 규칙으로 만들지 않음',
                '등록 장소(전철역·친척 집·공원) seek 규칙 없음', '길 잃음 미관측 시 unknown(baseline, wait)'],
        unsupported_sentences=('N1.s2', 'N1.s3'),
    )

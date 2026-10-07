"""Evaluation personas: avoidance family (AI draft, unreviewed).

Author did not read dev128, variants_*, evidence_diverse_20261006 profiles/scenes,
or the contract A/B tests. Coverage: type-wide vs one registered place, single /
AND / OR conditions, unconditional type avoidance, releases (fatigue, companion,
time of day), darkness vs clock time, unobserved signal / distance / place /
numeric fact, two simultaneous reactions, and caregiver statements that are not
avoidance (other person's preference, past preference, outcome, departure
motive, refusal talk, past habit). Every persona stays draft_unreviewed.

research_basis cites only evidence for behavior this person actually shows in
the guardian's words (brief F21: webB:C39, corpusA:DM-09; F30/F32: corpusA:DM-04).
Where the core avoidance rule itself has no direct evidence, the summary says so.

Trait-loss rule (expected_trait_loss_sentences): a sentence is listed when it
describes this person's own recurring behavior or departure motive that the
current action vocabulary cannot carry. Not listed: habits the guardian says
have stopped, other people's preferences, outcomes (getting lost), refusal talk,
one-off found locations, and place descriptions.
"""

FAR = {'market': 1000, 'park': 1000, 'forest': 1000, 'water': 1000}


def register(v):
    # 01: crowded market, released when worn out; the guardian's own dislike is not his reaction.
    v.persona(
        'R_avoidance_01', 'avoidance', ['webB:C39'],
        [{'label': '새말장터', 'place_type': 'market'},
         {'label': '버들못공원', 'place_type': 'park'},
         {'label': '옛 철공소', 'place_type': 'workplace'}],
        [('등록하신 장소들은 아버님께 어떤 곳이에요?',
          '새말장터는 집에서 제일 가까운 시장이고, 버들못공원은 아파트 단지 옆 공원이에요. '
          '옛 철공소는 젊을 때 일하시던 데라 적어 둔 거지, 요즘 가시는 데는 아니에요.'),
         ('사람이 북적이는 곳에 가시면 어떠세요?',
          '시장 안이 사람으로 바글바글하면 몇 걸음 들어가시다가 얼굴이 굳으면서 바로 돌아 나오세요. '
          '한산할 땐 시장 골목을 끝까지 쭉 걸어서 지나가시고요.'),
         ('붐빌 때는 늘 그렇게 돌아 나오세요?',
          '한참 걸어서 기운이 쭉 빠지신 날엔 붐벼도 그냥 사람들 사이로 지나가세요. '
          '돌아 나올 힘도 없으신 것 같아요.'),
         ('주말에는 주로 어떻게 지내세요?',
          '사실 사람 많은 데를 질색하는 건 저라서, 주말엔 아버지를 잘 안 모시고 나가요.')],
        [v.spec('avoid_market', 'market.crowded and not fatigue_high', ids=('N1', 'N2'))],
        [v.case('trigger', v.nearby('market', crowded=True), ['avoid_market'],
                '시장 60m 안에서 혼잡이 관측되고 지친 상태가 아님. 붐비는 시장에서 돌아 나온 관찰과 일치.'),
         v.case('non_trigger', v.nearby('market'), ['baseline'],
                '한산한 시장. 골목을 끝까지 걸어서 지나간다고 함. 회피 반응 없음.'),
         v.case('boundary_or_release',
                v.nearby('market', crowded=True, noisy=True, fatigue_high=True, continuous_walk_minutes=70),
                ['baseline'],
                '붐비지만 오래 걸어 기운이 빠진 상태. 그럴 땐 붐벼도 사람들 사이로 지나간다고 진술함(해제).'),
         v.case('unobserved_or_conflict',
                v.nearby('market', crowded=True, fatigue_high=None, continuous_walk_minutes=None), [],
                '시장이 붐비지만 지친 상태인지, 얼마나 걸었는지 관측이 없음. 회피와 해제가 모두 가능.',
                status='unknown', possible=['avoid_market', 'baseline'])],
        '시장이 붐빌 때 돌아 나오지만, 오래 걸어 기운이 빠진 날에는 그러지 않는 아버지(유형 단위, 혼잡 그리고 '
        '피로하지 않음). webB:C39(시장 같은 혼잡한 곳에서의 긴장)를 이 사람이 실제로 보인 모습으로 옮겼다. '
        '피로 해제는 이 사람의 보호자 진술이다. 보호자 본인의 혼잡 기피(타인 선호)는 반례로 들어 있다.',
        ['N1·N2가 혼잡 그리고 지치지 않았을 때로 읽히고, 피로 해제가 보존되는지',
         'N2의 "한참 걸어서"가 지어낸 보행 시간 임계값으로 바뀌지 않는지',
         'N3의 "제가 질색해서"가 이 사람의 회피로 바뀌지 않는지',
         '한산한 시장 장면이 기본 이동인지, 피로 미관측 장면이 미확인으로 남는지'])

    # 02: whole market type, unconditional; past preference for the market is not a current destination.
    v.persona(
        'R_avoidance_02', 'avoidance', ['webB:C39'],
        [{'label': '솔밭시장', 'place_type': 'market'},
         {'label': '외가 동네', 'place_type': 'relative_home'},
         {'label': '갈대내 산책로', 'place_type': 'park'}],
        [('어머님께 이 세 곳은 어떤 의미가 있는 데예요?',
          '솔밭시장은 삼십 년 넘게 다니시던 단골 시장이에요. 외가 동네는 명절마다 가는 데고, '
          '갈대내 산책로는 몇 해 전까지 저랑 같이 걷던 길이에요.'),
         ('요즘 장 보러 가시는 건 어떠세요?',
          '재작년부터 시장 골목에만 들어서면 손을 떨면서 안절부절못하셨어요. '
          '그 뒤로는 사람이 많든 적든 시장 쪽으로는 아예 발을 안 들이시고 길을 돌아가세요.'),
         ('예전에도 그러셨어요?',
          '아니요, 예전엔 장 구경을 그렇게 좋아하셔서 솔밭시장에 하루 두 번도 가셨어요. '
          '요즘은 장 볼 게 있으면 제가 혼자 다녀와요.')],
        [v.spec('avoid_market', 'True', ids=('N1',))],
        [v.case('trigger', v.nearby('market', crowded=True, noisy=True), ['avoid_market'],
                '붐비는 시장 60m 안. 시장 쪽으로는 발을 안 들임.'),
         v.case('non_trigger',
                v.scene(map_distance_m={**FAR, 'market': 85, 'park': 25}, crowded=True), ['baseline'],
                '시장은 회피 범위(60m) 밖이고 붐비는 공원 근처. 공원 반응은 진술되지 않음.'),
         v.case('boundary_or_release',
                v.nearby('market', current_place_label='솔밭시장', family_present=True, clock_hour=7.5),
                ['avoid_market'],
                '이른 아침 한산한 옛 단골 시장, 딸이 곁에 있음. "많든 적든" 피한다고 했고 해제 진술이 없음. '
                '예전 단골이라는 과거 선호가 출발로 바뀌지 않아야 함.'),
         v.case('unobserved_or_conflict',
                v.scene(map_distance_m={'park': 1000, 'forest': 1000, 'water': 1000}), [],
                '지도에 시장까지의 거리값이 없음. 시장 근처인지 모르므로 회피와 기본 이동이 모두 가능.',
                status='unknown', possible=['avoid_market', 'baseline'])],
        '시장에서 불안해하던 모습(webB:C39와 같은 유형)이 굳어져, 지금은 혼잡과 상관없이 시장 유형 전체를 '
        '피하는 어머니(조건 없는 유형 회피). 예전엔 시장 구경을 좋아했다는 과거 선호는 현재 목적지가 아니다. '
        '조건 없는 유형 회피는 앞단 저장 형식에서 고정 규칙이 되지 않을 수 있다는 엔진 결함 의심(E2, 검증 필요)과 '
        '맞닿아 있다.',
        ['N1이 조건 없는 시장 회피로 읽히고 혼잡·동행 같은 조건이 붙지 않는지',
         'N2의 과거 선호(솔밭시장 단골)가 솔밭시장 출발로 바뀌지 않는지',
         '시장 거리값이 없는 장면이 미확인으로 남는지(지도 결측 시 엔진은 unmapped_avoidance 위험)'])

    # 03: one registered market only, unconditional; other markets fine; departure motive is not avoidance.
    v.persona(
        'R_avoidance_03', 'avoidance', ['corpusA:DM-04'],
        [{'label': '가람시장', 'place_type': 'market'},
         {'label': '큰딸네 아파트', 'place_type': 'relative_home'},
         {'label': '은행나무공원', 'place_type': 'park'}],
        [(v.DEFAULT_INTRO,
          '가람시장은 어머님이 서른 해 가까이 좌판을 하시던 시장이에요. 큰딸네 아파트는 시누이 집인데 '
          '명절이면 식구들이 다 모이는 데고, 은행나무공원은 그 아파트 바로 앞 공원이에요.'),
         ('시장 같은 데 가시면 어떠세요?',
          '가람시장 쪽으로는 안 가려고 하세요. 같이 장사하던 분들 얼굴을 못 알아보시게 된 뒤로, '
          '그 시장 입구가 한 50미터 앞에 보이면 다른 골목으로 돌아가세요. '
          '동네 다른 시장은 예전처럼 잘 다니시고요.'),
         ('최근에 혼자 나가신 적이 있으세요?',
          '지난달에 주간보호센터 한번 다녀 보시자고 했더니 다음 날 새벽에 혼자 나가셨어요. '
          '그때는 은행나무공원 벤치에 앉아 계신 걸 찾았어요.')],
        [v.spec('avoid_market', 'True', ids=('N1',), labels=('가람시장',))],
        [v.case('trigger', v.nearby('market', current_place_label='가람시장'), ['avoid_market'],
                '등록된 가람시장 범위 안. 그 시장에서만 돌아감.'),
         v.case('non_trigger', v.nearby('market', crowded=True, noisy=True), ['baseline'],
                '등록되지 않은 다른 시장은 붐벼도 예전처럼 다님. 특정 장소 회피를 유형 전체로 넓히지 않음.'),
         v.case('boundary_or_release',
                v.nearby('market', current_place_label='가람시장', family_present=True, clock_hour=18),
                ['avoid_market'],
                '장이 파한 저녁, 며느리가 곁에 있고 한산해도 그 시장은 피함. 진술에 해제 조건이 없음. '
                '50미터는 보이는 거리 묘사이지 걸은 거리 조건이 아님.'),
         v.case('unobserved_or_conflict', v.nearby('market', current_place_label=None), [],
                '시장 근처지만 어느 시장인지 모름. 가람시장이면 회피, 다른 시장이면 기본 이동.',
                status='unknown', possible=['avoid_market', 'baseline'])],
        '예전에 장사하던 특정 등록 시장만 조건 없이 피하는 시어머니(특정 등록 장소 회피, 유형 전체 아님). '
        'research_basis는 이 사람이 실제로 보인 출발 동기(센터 권유 뒤 새벽 이탈, corpusA:DM-04)만 인용한다. '
        '실종 중 특정 장소 회피 자체의 직접 근거는 브리프에 없다(F32). 그 출발 동기는 회피 규칙을 만들지 않고 '
        '현행 행동 어휘로 표현되지 않으므로 손실 문장으로 표시한다(F30). 발견 장소(은행나무공원) 진술은 출발 '
        '규칙이 아니다. 브리프 F32는 특정 장소 회피를 no_place_avoid_action으로 두지만, 이 시장은 장소 유형이 '
        '시장과 일치해 avoid_market과 place_labels로 표현했다. "feature가 장소 유형과 일치할 때만 허용"한다는 '
        '관례는 사람 검토에서 확정해야 한다.',
        ['N1이 가람시장 한정 회피로 읽히고 다른 시장으로 확대되지 않는지',
         '"50미터"가 휴식 후 이동 거리 같은 숫자 조건으로 바뀌지 않는지',
         'N2의 새벽 이탈(출발 동기)과 발견 장소가 회피·출발 규칙으로 바뀌지 않는지'],
        unsupported_sentences=('N2.s1',))

    # 04: park AND (crowded, noisy), released when a family member is beside her; refusal talk is not avoidance.
    v.persona(
        'R_avoidance_04', 'avoidance', ['webB:C39'],
        [{'label': '물푸레공원', 'place_type': 'park'},
         {'label': '옛 우체국 관사', 'place_type': 'past_home'},
         {'label': '한빛정형외과', 'place_type': 'hospital'}],
        [('어머님이 혼자 걸으실 때 자주 지나는 곳이 있나요?',
          '시장 가실 때 물푸레공원을 가로질러 다니세요. 옛 우체국 관사는 신혼 때 사시던 집이고, '
          '한빛정형외과는 무릎 때문에 다니시는 병원이에요.'),
         ('공원에 사람이 많거나 행사가 있을 때는 어떠세요?',
          '사람만 많은 건 괜찮으세요. 사람은 별로 없는데 음악만 크게 틀어 놓은 것도 그냥 지나가시고요. '
          '그런데 공원에서 공연이나 축제를 해서 사람도 꽉 차고 스피커 소리까지 쾅쾅 울리면, '
          '귀를 막으시면서 공원 밖으로 빠져나가세요. '
          '그럴 때도 제가 팔짱 끼고 옆에 있으면 공원 안을 그냥 같이 걸어 다니세요.'),
         ('병원은 잘 다니세요?',
          '병원 가자고 하면 늘 싫다고 하세요. 그래도 막상 모시고 가면 진료는 얌전히 받으세요.')],
        [v.spec('avoid_park', 'park.crowded and park.noisy and not family_present', ids=('N1',))],
        [v.case('trigger', v.nearby('park', crowded=True, noisy=True), ['avoid_park'],
                '공원이 붐비고 시끄러우며 딸이 곁에 없음. 공원 밖으로 빠져나감.'),
         v.case('non_trigger', v.nearby('park', crowded=True), ['baseline'],
                '사람만 많고 소리는 크지 않음. 사람만 많은 건 괜찮다고 함(두 조건 모두 필요).'),
         v.case('boundary_or_release', v.nearby('park', crowded=True, noisy=True, family_present=True),
                ['baseline'], '붐비고 시끄러워도 딸이 팔짱 끼고 곁에 있으면 공원 안을 같이 걸어 다님.'),
         v.case('unobserved_or_conflict', v.nearby('park', noisy=True, crowded=None), [],
                '소리가 큰 것은 관측됐지만 붐비는지 관측이 없음. 소리만으로는 빠져나가지 않는다고 했으므로 '
                '혼잡 여부에 따라 회피와 기본 이동이 갈림.',
                status='unknown', possible=['avoid_park', 'baseline'])],
        '공원이 붐비면서 시끄러울 때(AND)만 빠져나가고, 딸이 곁에 있으면 그러지 않는 어머니. '
        'webB:C39는 혼잡한 곳의 긴장을 들고, 소음과의 결합·동행 해제는 이 사람의 보호자 진술이다. '
        '병원 거부 발언은 회피 이동 관찰이 아니므로 규칙을 만들지 않는다.',
        ['N1이 혼잡 그리고 소음(둘 다)으로 읽히고, 혼잡만으로도 소음만으로도 발동하지 않는지',
         '딸이 곁에 있을 때 해제가 보존되는지',
         'N2의 "병원 가기 싫다"가 병원 쪽 회피로 바뀌지 않는지'])

    # 05: forest when dark AND alone; a companion releases it; clock time is not darkness; "somewhere I know" is lost.
    v.persona(
        'R_avoidance_05', 'avoidance', ['corpusA:DM-09'],
        [{'label': '솔고개 약수터', 'place_type': 'park'},
         {'label': '삼거리 방앗간', 'place_type': 'workplace'}],
        [('등록하신 두 곳은 어떤 데예요?',
          '솔고개 약수터는 예전에 물 뜨러 다니시던 뒷산 약수터예요. 요즘은 무릎 때문에 거기까지는 안 가세요. '
          '삼거리 방앗간은 마흔 해 가까이 하시던 가게고요.'),
         ('뒷산 근처에서 눈에 띄는 모습이 있나요?',
          '날이 저물어 컴컴해지면 혼자서는 뒷산 숲 쪽에 얼씬도 안 하세요. '
          '산 밑 길을 걷다가도 나무가 빽빽한 데가 나오면 빙 둘러서 가세요. '
          '제가 손전등 들고 같이 있으면 깜깜해도 숲길로 같이 걸어 내려오시고요. '
          '환한 낮에는 혼자서도 숲길을 잘 다니세요.'),
         ('처음 가 보는 곳에서는 어떠세요?',
          '낯선 동네에 가면 안절부절못하시고 자꾸 아는 데로 가자고 하세요. '
          '작년 가을 친척 결혼식 때도 식장에 오래 못 계셨어요.')],
        [v.spec('avoid_forest', 'dark_observed and not family_present', ids=('N1',))],
        [v.case('trigger', v.nearby('forest', dark_observed=True, clock_hour=17.5), ['avoid_forest'],
                '숲 60m 안, 혼자이고 겨울 이른 저녁이라 이미 어둠이 관측됨. 시각이 아니라 어둠 관측이 조건임.'),
         v.case('non_trigger', v.nearby('forest', clock_hour=12.5), ['baseline'],
                '밝은 낮의 숲길. 낮에는 혼자서도 숲길을 다닌다고 함.'),
         v.case('boundary_or_release',
                v.nearby('forest', dark_observed=True, family_present=True, clock_hour=19.5), ['baseline'],
                '어둡지만 보호자(자녀)가 곁에 있음. 같이 있으면 깜깜해도 숲길로 걸어 내려온다고 진술함(해제).'),
         v.case('unobserved_or_conflict', v.nearby('forest', dark_observed=None, clock_hour=21), [],
                '혼자이고 밤 9시지만 어둠 관측이 없음. 시각만으로 어둡다고 추정하지 않음.',
                status='unknown', possible=['avoid_forest', 'baseline'])],
        '어둠이 관측되고 혼자일 때 숲 쪽을 피하고, 자녀가 곁에 있으면 그러지 않는 아버지. 숲·어둠 회피 자체의 '
        '직접 연구 근거는 브리프에 없다(F21 보호자 표현 수준). research_basis는 이 사람이 실제로 보인 낯선 곳 '
        '불안(corpusA:DM-09)만 인용한다. 그 모습(아는 데로 가자고 함, 낯선 곳에 오래 못 머묾)은 현행 행동 어휘에 '
        '"아는 곳으로 가기"가 없어 규칙을 만들지 않고 손실 문장으로 표시한다. 약수터는 그만둔 과거 습관이다.',
        ['N1이 어둠 관측 그리고 혼자일 때로 읽히고 시각 임계값으로 바뀌지 않는지(이른 어둠 장면, 밤 시각만 있는 장면)',
         '자녀가 곁에 있을 때 해제가 보존되는지',
         'N0의 약수터(그만둔 과거 습관)와 N2의 "아는 데로 가자고"가 출발 규칙으로 바뀌지 않는지'],
        unsupported_sentences=('N2.s1', 'N2.s2'))

    # 06: crowded waterside path + distance-limited rest; getting lost in crowds is an outcome, not avoidance.
    v.persona(
        'R_avoidance_06', 'avoidance', ['webB:C39'],
        [{'label': '두레시장', 'place_type': 'market'},
         {'label': '구 시청 앞 정류장', 'place_type': 'station'},
         {'label': '작은아들 집', 'place_type': 'relative_home'}],
        [('남편분이 다니시는 곳을 알려 주세요.',
          '두레시장은 제가 장 보러 갈 때 같이 가는 시장이에요. 구 시청 앞 정류장은 퇴직 전에 출퇴근하던 데고, '
          '작은아들 집은 명절에나 모이는 데라 혼자 가실 일은 없어요.'),
         ('호숫가나 물가 산책로에서는 어떠세요?',
          '호숫가 둘레길이 좁아서 그런지, 사람이 바글거리면 부딪힐까 봐 겁을 내면서 물가 길을 버리고 '
          '안쪽 길로 빠져나와요. 한산할 땐 물가 길로 끝까지 걸어요.'),
         ('시장처럼 사람 많은 데서는요?',
          '사람 많은 데서 제가 손을 놓치면 금방 잃어버려요. 작년에 두레시장에서 한 번 놓쳐서 한참 찾았어요.'),
         ('한 번에 얼마나 걸으세요?',
          '만보기로 재 보니까 쉬지 않고 1.5킬로쯤 걸으면 꼭 아무 데나 걸터앉아 한숨 돌리고 다시 가요.')],
        [v.spec('avoid_water', 'water.crowded', ids=('N1',)),
         v.spec('rest', 'is_walking and distance_since_rest_m >= 1500', ids=('N3',))],
        [v.case('trigger', v.nearby('water', crowded=True, distance_since_rest_m=400), ['avoid_water'],
                '물가 100m 안에서 혼잡이 관측되고, 쉰 뒤로 걸은 거리는 짧음. 물가 길을 버리고 빠져나옴.'),
         v.case('non_trigger', v.nearby('market', crowded=True, noisy=True, distance_since_rest_m=650),
                ['baseline'],
                '붐비는 시장이고 물가는 멂. 사람 많은 데서 잃어버린다는 말은 결과 진술이고, 시장 혼잡에 대한 '
                '회피는 진술되지 않음.'),
         v.case('boundary_or_release', v.scene(distance_since_rest_m=1560), ['rest'],
                '보행 중, 쉰 뒤로 1.5킬로를 막 넘김. 주변에 반응할 지형 없음. 걸터앉아 쉼.'),
         v.case('unobserved_or_conflict', v.scene(distance_since_rest_m=None), [],
                '보행 중이지만 쉰 뒤로 얼마나 걸었는지 관측이 없음. 휴식과 기본 이동이 모두 가능.',
                status='unknown', possible=['baseline', 'rest'])],
        '좁은 호숫가 길이 붐비면 겁을 내며 물가를 벗어나고, 쉬지 않고 1.5킬로쯤 걸으면 앉아 쉬는 남편. '
        'webB:C39(혼잡한 곳에서의 긴장)를 이 사람이 물가 길에서 실제로 보인 모습으로 옮겼다. 휴식 거리는 '
        '보호자 진술이다. "사람 많은 데서 잃어버린다"는 F21 반례(결과 진술)로 시장 혼잡 회피가 아니다.',
        ['N1이 물가 혼잡 조건부 회피로 읽히고 시장 등 다른 유형으로 확대되지 않는지',
         'N2(잃어버림, 결과 진술)가 시장 혼잡 회피로 바뀌지 않는지',
         'N3이 보행 중 휴식 후 거리 1.5킬로 이상의 휴식으로 읽히는지, 거리 미관측 장면이 미확인으로 남는지'])

    # 07: one registered park, crowded mornings only; afternoons and other parks fine; past habit at the same park.
    v.persona(
        'R_avoidance_07', 'avoidance', ['webB:C39'],
        [{'label': '개나리공원', 'place_type': 'park'},
         {'label': '살구나무집', 'place_type': 'past_home'}],
        [('개나리공원은 아내분께 어떤 곳이에요?',
          '집 바로 뒤 공원이에요. 예전엔 아침마다 거기 체조 모임에 나갔는데, '
          '작년 봄에 체조하다 넘어진 뒤로는 모임에 발을 끊었어요.'),
         ('요즘 개나리공원 앞을 지날 때는 어떤 모습이세요?',
          '오전에 체조하는 사람들로 공원이 북적이면 입구에서 멈칫하다가 그냥 돌아서요. '
          '오후에 동네 아이들로 시끌벅적할 때는 아무렇지 않게 공원을 가로질러 가고요.'),
         ('다른 공원도 그러세요?',
          '다른 공원은 아침에 사람이 몰려 있어도 상관 안 해요. 그러는 건 개나리공원뿐이에요.'),
         ('살구나무집 쪽으로 가신 적은 있나요?',
          '살구나무집은 결혼하고 처음 살던 집인데, 요즘 거기 얘기는 통 안 해요.')],
        [v.spec('avoid_park', 'park.crowded and clock_hour < 12', ids=('N1', 'N2'), labels=('개나리공원',))],
        [v.case('trigger',
                v.nearby('park', crowded=True, current_place_label='개나리공원', clock_hour=7.5), ['avoid_park'],
                '오전에 개나리공원이 북적임. 입구에서 돌아섬.'),
         v.case('non_trigger',
                v.nearby('park', crowded=True, noisy=True, current_place_label='개나리공원', clock_hour=16),
                ['baseline'],
                '같은 개나리공원이 붐비지만 오후. 오후에는 아이들로 시끌벅적해도 가로질러 간다고 함(시간 조건).'),
         v.case('boundary_or_release', v.nearby('park', crowded=True, clock_hour=7), ['baseline'],
                '등록되지 않은 다른 공원이 아침에 붐빔. 개나리공원뿐이라고 했으므로 반응 없음(장소 범위).'),
         v.case('unobserved_or_conflict',
                v.nearby('park', crowded=None, current_place_label='개나리공원', clock_hour=6.5), [],
                '오전의 개나리공원 근처지만 붐비는지 관측이 없음.',
                status='unknown', possible=['avoid_park', 'baseline'])],
        '집 뒤 특정 등록 공원이 오전에 붐빌 때만 돌아서는 아내(특정 장소, 혼잡 그리고 오전). 오후의 혼잡이나 '
        '다른 공원의 혼잡에는 반응하지 않는다. webB:C39의 혼잡 긴장을 한 장소·시간대에 한정된 모습으로 옮겼다. '
        '같은 공원의 체조 모임은 그만둔 과거 습관이라 출발 근거가 아니다. 브리프 F32는 특정 장소 회피를 '
        'no_place_avoid_action으로 두지만, 이 공원은 장소 유형이 공원과 일치해 avoid_park와 place_labels로 '
        '표현했다(관례는 사람 검토에서 확정).',
        ['N1·N2가 개나리공원 한정, 혼잡 그리고 오전 조건으로 읽히는지(공원 유형 전체나 하루 종일로 확대 금지)',
         'N0의 과거 체조 모임이 개나리공원으로 가는 아침 출발로 바뀌지 않는지',
         '오후의 붐비는 개나리공원 장면이 기본 이동인지'])

    # 08: market OR (crowded, noisy) + park crowded; both near -> conflict; day-care center avoidance is lost.
    v.persona(
        'R_avoidance_08', 'avoidance', ['webB:C39'],
        [{'label': '장미골목시장', 'place_type': 'market'},
         {'label': '햇살주간보호센터', 'place_type': 'care_center'},
         {'label': '미루나무공원', 'place_type': 'park'}],
        [('할머님이 가실 만한 곳으로 이 세 곳을 적으셨는데, 각각 어떤 곳이에요?',
          '장미골목시장은 할머니가 반찬거리 사러 다니시는 시장이고, 미루나무공원은 집 앞 공원이에요. '
          '햇살주간보호센터는 지난봄부터 평일에 다니시는 센터예요.'),
         ('시장 골목에서는 어떠세요?',
          '시장 골목에 사람이 북적이거나, 사람이 없어도 확성기 소리나 음악이 크게 울리면 바로 시장 밖으로 '
          '빠져나오세요. 조용하고 한산할 땐 시장 안을 아무렇지 않게 오가세요.'),
         ('공원은요?',
          '공원도 사람이 꽉 차 있으면 들어가시다 말고 나오세요. 시끄러운 건 공원에선 별로 상관없어 하시고요.'),
         ('혹시 일부러 피해 다니시는 데가 있나요?',
          '센터 차 타는 날 아침마다 안 가겠다고 실랑이를 하세요. '
          '산책하시다가도 햇살주간보호센터 건물이 보이면 반대쪽 길로 돌아서 가세요.')],
        [v.spec('avoid_market', 'market.crowded or market.noisy', ids=('N1',)),
         v.spec('avoid_park', 'park.crowded', ids=('N2',))],
        [v.case('trigger', v.nearby('market', crowded=True), ['avoid_market'],
                '시장 골목이 붐빔. 시장 밖으로 빠져나옴.'),
         v.case('non_trigger', v.nearby('market'), ['baseline'],
                '센터와 무관한 곳의 조용하고 한산한 시장. 아무렇지 않게 오간다고 함.'),
         v.case('boundary_or_release', v.nearby('market', noisy=True), ['avoid_market'],
                '사람은 없지만 확성기 소리가 큼. 혼잡 또는 소음 하나면 충분(OR).'),
         v.case('unobserved_or_conflict',
                v.scene(map_distance_m={**FAR, 'market': 30, 'park': 45}, crowded=True), [],
                '관측 공백이 아니라 충돌: 시장과 공원이 모두 가깝고 둘 다 붐벼 두 회피가 동시에 성립함. '
                '어느 쪽을 먼저 하는지 진술이 없어 하나를 고르지 않음.',
                status='unknown', possible=['avoid_market', 'avoid_park'])],
        '시장은 혼잡 또는 소음(OR), 공원은 혼잡만으로 피하는 할머니(유형별로 조건이 다름). webB:C39의 혼잡 '
        '긴장을 이 사람이 실제로 보인 모습으로 옮겼다. 주간보호센터 건물을 보고 돌아가는 모습(N3.s2)은 특정 등록 '
        '장소 회피(F32)다. 센터는 시장·공원·숲·물 유형이 아니어서 계약 관례상 표현할 수 없고, 손실 문장으로 '
        '표시한다. 다만 avoid에 임의 feature와 place_labels를 붙이면 엔진은 기계적으로 동작한다(mind_policy.'
        'spatial_scope가 place_labels를 우선함). 따라서 이 판정은 엔진상 불가가 아니라 관례상 불가이며, 사람 '
        '검토에서 확정해야 한다. 센터 차를 두고 하는 실랑이(N3.s1)는 거부 발언이지 회피 이동 관찰이 아니다.',
        ['N1이 혼잡 또는 소음(OR)으로, N2가 공원 혼잡만으로 읽히는지(공원 소음으로 확대 금지)',
         'N3.s2 센터 회피가 시장·공원 회피 등 다른 유형 규칙으로 둔갑하지 않는지, N3.s1 실랑이가 회피로 '
         '읽히지 않는지',
         '시장·공원이 동시에 붐비는 충돌 장면에서 우선순위를 지어내지 않는지'],
        unsupported_sentences=('N3.s2',))

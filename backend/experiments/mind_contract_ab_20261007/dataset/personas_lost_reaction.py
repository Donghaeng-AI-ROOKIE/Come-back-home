"""Research-grounded evaluation personas: lost_reaction (AI draft, unreviewed).

Family: what the person does once they notice they are lost (stand still,
keep walking, head somewhere, difference with or without family, what ends
the reaction).
Brief: 결선/실험/MIND_research_personas_20261007/family_briefs/lost_reaction.json.
Written without reading the development set. Every guardian answer is a
synthetic, individual observation; group statistics are not turned into rules.
Revised 2026-10-07 after an independent review (release facts, time bounds,
habit vs single episode, trait-loss sentences, wording variety, basis notes).
"""

FAMILY = 'lost_reaction'


def register(v):
    # 01. Evening freeze vs daytime roaming (explicit morning start); released when family arrives.
    v.persona(
        'R_lost_reaction_01', FAMILY, ['local:C25'],
        [{'label': '버들내공원', 'place_type': 'park'},
         {'label': '옛 운수회사 차고지', 'place_type': 'workplace'},
         {'label': '한마음의원', 'place_type': 'hospital'}],
        [(v.DEFAULT_INTRO, '버들내공원은 아버지가 아침마다 걷던 곳이고, 옛 운수회사 차고지는 버스 운전하시던 시절 일터예요. '
                           '한마음의원은 혈압약 타러 한 달에 한 번 가시는 곳이에요.'),
         ('아버님이 길을 잃으셨다는 걸 스스로 아실 때 어떻게 하시나요?',
          '아침 일곱 시쯤 나가셔서 오후 다섯 시 전까지는 길이 헷갈리셔도 이 골목 저 골목 계속 다니세요. '
          '그런데 오후 다섯 시가 넘어서 길 잃은 걸 아시면 발이 땅에 붙은 것처럼 안 움직이세요. '
          '지난달에도 저녁 여섯 시쯤 버스정류장 옆에 한 시간 넘게 서 계신 걸 동네 분이 보셨대요.'),
         ('그렇게 꼼짝 않고 계시다가 언제 다시 움직이시던가요?',
          '제가 가서 팔을 잡아 드릴 때까지는 그대로 계세요. 혼자 힘으로 다시 걸어 나오신 적은 아직 없어요.')],
        [v.spec('wait', 'lost_awareness and not family_present and clock_hour >= 17', ids=('N1', 'N2')),
         v.spec('walk', 'lost_awareness and clock_hour >= 7 and clock_hour < 17', ids=('N1',))],
        [v.case('trigger', v.scene(lost_awareness=True, clock_hour=18.5), ['wait'],
                '저녁 여섯 시 반, 혼자 길 잃음을 알아차림 → 꼼짝 않고 서 있음'),
         v.case('non_trigger', v.scene(lost_awareness=False, clock_hour=19), ['baseline'],
                '길 잃음을 알아차리지 않은 저녁 외출 → 개인 반응 없음'),
         v.case('boundary_or_release', v.scene(lost_awareness=True, clock_hour=16.5), ['walk'],
                '오후 네 시 반(다섯 시 전) 길 잃음 인지 → 멈춤이 아니라 계속 돌아다님'),
         v.case('unobserved_or_conflict', v.scene(lost_awareness=True, family_present=None, clock_hour=18.5), [],
                '저녁에 길 잃음을 알았지만 가족이 곁에 왔는지 모르면 멈춤과 평소 이동이 모두 가능', status='unknown',
                possible=['baseline', 'wait'])],
        '오후 5시 이후 길 잃음을 알면 혼자일 때 꼼짝 않고 서 있고, 아침 7시쯤부터 5시 전까지는 계속 돌아다님. '
        '가족이 와야 멈춤이 풀림(해제 뒤 보행은 진술하지 않음). '
        '근거: local:C25=방법론(개인 관찰 우선 권고). 직접 근거 없음(브리프 F20의 직접 근거가 비어 있음).',
        ['17시 이후 혼자 길 잃음 인지 → 대기', '17시 전(7시 이후) 길 잃음 인지 → 계속 걷기',
         '저녁 + 가족 동행 미확인 → 대기·평소 분기'])

    # 02. Keeps walking when lost; in the rain heads for the covered market instead.
    v.persona(
        'R_lost_reaction_02', FAMILY, ['corpusA:DM-30', 'local:C25'],
        [{'label': '물푸레시장', 'place_type': 'market'},
         {'label': '은행나무쉼터', 'place_type': 'park'},
         {'label': '옛 방앗간 집', 'place_type': 'past_home'}],
        [(v.DEFAULT_INTRO, '물푸레시장은 어머니가 사십 년 장사하시던 곳이고, 은행나무쉼터는 동네 어르신들 모이는 쉼터예요. '
                           '옛 방앗간 집은 제가 어릴 때 살던 집인데 지금은 다른 분이 사세요.'),
         ('길을 잃었다고 느끼시면 보통 어떤 모습을 보이세요?',
          '어머니는 길 잃은 걸 아셔도 걸음을 멈추시는 법이 없어요. '
          '동네 분들 말로는 그럴 땐 걸음도 평소보다 훨씬 빨라지신대요. '
          '지난봄 시장 뒷골목에서 놓쳤을 때도 한 시간 반 뒤에 집에서 2킬로 가까이 떨어진 둑길에서 찾았어요.'),
         ('날씨 궂은 날은 어떠셨어요?',
          '비 오는 날은 달라요. 그럴 때 비까지 오면 아무 데로나 걷지 않고 지붕 있는 물푸레시장 쪽으로 곧장 가세요. '
          '작년 장마 때도 시장 통로 안에서 찾았어요.')],
        [v.spec('walk', 'lost_awareness and not rain_observed', ids=('N1',)),
         v.spec('seek_0', 'lost_awareness and rain_observed', ids=('N2',))],
        [v.case('trigger', v.scene(lost_awareness=True, rain_observed=False), ['walk'],
                '비 없는 날 길 잃음을 알아차림 → 멈추지 않고 계속 걸음'),
         v.case('non_trigger', v.scene(lost_awareness=False), ['baseline'],
                '길 잃음 인지가 없는 평소 외출 → 개인 반응 없음'),
         v.case('boundary_or_release', v.scene(lost_awareness=True, rain_observed=True), ['seek_0'],
                '비가 오는 중 길 잃음 인지 → 아무 데로나 걷지 않고 물푸레시장으로 향함'),
         v.case('unobserved_or_conflict', v.scene(lost_awareness=True, rain_observed=None), [],
                '비 관측이 없으면 계속 걷기와 시장으로 향함이 모두 가능', status='unknown',
                possible=['seek_0', 'walk'])],
        '길 잃음을 알면 멈추지 않고 계속 걸음(걸음이 빨라지는 점은 속도라 표현 불가). '
        '비가 오면 아무 데로나 걷지 않고 지붕 있는 물푸레시장으로 향함. '
        '근거: corpusA:DM-30=간접(집단 수준에서 멀리 걸어간 사례가 있다는 보고, 개인 규칙 근거 아님), '
        'local:C25=방법론. 비·시장 규칙의 직접 근거 없음.',
        ['비 없음 + 길 잃음 인지 → 계속 걷기', '비 관측 + 길 잃음 인지 → 시장으로 출발', '비 미관측 → 걷기·출발 분기'],
        unsupported_sentences=('N1.s2',))

    # 03. Heads to a long-familiar station when lost, then waits there until someone comes.
    v.persona(
        'R_lost_reaction_03', FAMILY, ['local:C17', 'local:C25'],
        [{'label': '가람역', 'place_type': 'station'},
         {'label': '느릅골 옛집', 'place_type': 'past_home'},
         {'label': '새솔병원', 'place_type': 'hospital'}],
        [(v.DEFAULT_INTRO, '가람역은 남편이 삼십오 년 동안 출퇴근하던 역이에요. '
                           '느릅골 옛집은 결혼하고 처음 살던 동네고, 새솔병원은 무릎 치료받는 병원이에요.'),
         ('길을 잃은 걸 아시면 어디로 가시는지 짐작 가는 데가 있나요?',
          '길을 모르겠다 싶으면 곧장 가람역 쪽으로 걸어가요. 지난번 두 번 모두 역 방향으로 가는 걸 이웃이 봤고, 결국 역에서 찾았어요.'),
         ('역에 도착하신 다음에는 어떻게 지내셨어요?',
          '역에 닿으면 개찰구 옆 의자에 앉아서 누가 데리러 올 때까지 기다려요. 역무원한테 집에 전화 좀 해 달라고 부탁한 적도 있어요.')],
        [v.spec('seek_0', 'lost_awareness and not physical_arrival', ids=('N1',)),
         v.spec('wait', 'lost_awareness and not family_present', ids=('N2',), labels=('가람역',))],
        [v.case('trigger', v.scene(lost_awareness=True), ['seek_0'],
                '역 밖에서 길 잃음을 알아차림 → 익숙한 역으로 향함'),
         v.case('non_trigger', v.scene(lost_awareness=False), ['baseline'],
                '길 잃음 인지가 없으면 역으로 향하는 반응도 없음'),
         v.case('boundary_or_release',
                v.scene(lost_awareness=True, physical_arrival=True, current_place_label='가람역'), ['wait'],
                '역에 도착하면 출발 반응이 끝나고 그 자리에서 누군가를 기다림'),
         v.case('unobserved_or_conflict', v.scene(lost_awareness=None), [],
                '길 잃음 인지 여부를 모르면 평소 이동과 역으로 향함이 모두 가능', status='unknown',
                possible=['baseline', 'seek_0'])],
        '길 잃음을 알면 오래 다닌 역으로 향하고, 역에 닿으면 가족이 올 때까지 기다림. 역무원에게 연락을 부탁하는 점은 표현 불가. '
        '근거: local:C17=간접(길을 묻거나 전화로 도움을 구한다는 보고, 표현 불가 문장 N2.s2만 뒷받침), '
        'local:C25=방법론. 역 출발·대기 규칙의 직접 근거 없음.',
        ['역 밖 길 잃음 인지 → 역으로 출발', '역 도착 → 대기로 전환', '인지 미확인 → 평소 이동·출발 분기'],
        unsupported_sentences=('N2.s2',))

    # 04. Observed only while accompanied: stops and looks to the guardian. Alone: never seen.
    v.persona(
        'R_lost_reaction_04', FAMILY, ['local:C17', 'local:C25'],
        [{'label': '청보리공원', 'place_type': 'park'},
         {'label': '아랫마을 옛집', 'place_type': 'past_home'}],
        [(v.DEFAULT_INTRO, '청보리공원은 저랑 저녁마다 한 바퀴 도는 공원이고, 아랫마을 옛집은 어머님이 시집와서 오래 사신 집이에요.'),
         ('어머님이 길이 헷갈린다고 느끼실 때 어떻게 하시던가요?',
          '저랑 같이 걷다가 길이 헷갈리시면 걸음을 뚝 멈추고 제 얼굴만 쳐다보세요. 제가 앞장서야 다시 따라오세요.'),
         ('혼자 나가셨을 때도 그러시나요?',
          '혼자 계실 때 어떠신지는 제가 직접 본 적이 없어요. 작년에 한 번 혼자 나가셨다가 경찰분이 모시고 오셨는데, 어디서 어떻게 계셨는지는 못 들었어요.')],
        [v.spec('wait', 'lost_awareness and family_present', ids=('N1',))],
        [v.case('trigger', v.scene(lost_awareness=True, family_present=True), ['wait'],
                '보호자와 함께 있다가 길이 헷갈림 → 멈춰 서서 보호자를 봄'),
         v.case('non_trigger', v.scene(lost_awareness=False, family_present=True), ['baseline'],
                '함께 걷는 중 길 헷갈림이 없으면 개인 반응 없음'),
         v.case('boundary_or_release', v.scene(lost_awareness=True, family_present=False), ['baseline'],
                '혼자일 때의 반응은 관찰된 적이 없으므로 동행 중 멈춤을 확대하지 않음'),
         v.case('unobserved_or_conflict', v.scene(lost_awareness=True, family_present=None), [],
                '곁에 가족이 있는지 모르면 멈춤과 평소 이동이 모두 가능', status='unknown',
                possible=['baseline', 'wait'])],
        '동행 중 길이 헷갈리면 멈춰 서서 보호자를 바라봄. 혼자일 때는 관찰 없음. 보호자를 따라가는 해제는 표현 불가. '
        '형식 충실도 시험(동행 중 관찰을 혼자일 때로 확대하지 않는지)이며, 실종 수색 중에는 가족 동행이 참일 수 없어 '
        '지도 효과는 없음. 동행 맥락 진술을 길 잃음 반응의 반례로 보는 브리프 분류와 판단이 갈릴 수 있음. '
        '근거: local:C17=간접(가족 뒤를 따라다닌다는 보고), local:C25=방법론.',
        ['동행 중 길 잃음 인지 → 대기', '혼자일 때는 개인 반응 없음', '가족 동행 미확인 → 대기·평소 분기'],
        unsupported_sentences=('N1.s2',))

    # 05. Looks ordinary at first; once agitated while moving about, freezes. Not when merely agitated.
    v.persona(
        'R_lost_reaction_05', FAMILY, ['local:C25'],
        [{'label': '해솔공원', 'place_type': 'park'},
         {'label': '동그라미시장', 'place_type': 'market'},
         {'label': '옛 봉제공장', 'place_type': 'workplace'}],
        [(v.DEFAULT_INTRO, '해솔공원은 아내가 친구들이랑 체조하던 곳이고, 동그라미시장은 반찬거리 사러 가는 시장이에요. '
                           '옛 봉제공장은 젊을 때 열다섯 해 가까이 다닌 일터예요.'),
         ('길을 잃었다는 걸 알아차리시면 처음에 어떠세요?',
          '처음엔 겉으로 봐서는 길 잃은 사람인지 모를 정도로 여느 때랑 똑같아요.'),
         ('그 뒤로 시간이 지나면 달라지나요?',
          '그렇게 다니다가 점점 초조해지면 손을 비비면서 꼼짝을 안 해요. 그때는 불러도 대답을 잘 안 해요. '
          '길을 잃은 게 아니면 초조해해도 이렇게 굳지는 않아요.')],
        [v.spec('wait', 'lost_awareness and anxiety_high', ids=('N2',))],
        [v.case('trigger', v.scene(lost_awareness=True, anxiety_high=True), ['wait'],
                '길 잃음을 알고 초조해짐 → 손을 비비며 꼼짝 않음'),
         v.case('non_trigger', v.scene(lost_awareness=False, anxiety_high=True), ['baseline'],
                '길을 잃은 게 아닌데 초조함 → 굳지 않음(보호자가 명시)'),
         v.case('boundary_or_release', v.scene(lost_awareness=True, anxiety_high=False), ['baseline'],
                '길 잃음을 알았지만 아직 초조하지 않음 → 여느 때와 같음'),
         v.case('unobserved_or_conflict', v.scene(lost_awareness=True, anxiety_high=None), [],
                '길 잃음은 알지만 초조한지 모르면 굳음과 평소 이동이 모두 가능', status='unknown',
                possible=['baseline', 'wait'])],
        '길 잃음을 알아도 처음엔 여느 때와 같다가, 초조해지면 손을 비비며 꼼짝 않음. 길을 잃은 게 아니면 초조해도 굳지 않음. '
        '불러도 대답하지 않는 점은 표현 불가. 초조함은 엔진의 불안 상태(게이지에서 유도한 잠재 상태, 감정 관측 아님)로 옮김. '
        '보행 중 혼란이 쌓여 불안이 높아진 뒤 대기로 들어가는 순서라 엔진에서 도달 가능하고, 대기 중 게이지가 멈추므로 '
        '스스로 풀리지 않음(진술에도 해제 언급 없음). 근거: local:C25=방법론. 직접 근거 없음.',
        ['길 잃음 인지 + 초조함 → 대기', '길 잃음 없이 초조함 → 개인 반응 없음', '초조함 미관측 → 대기·평소 분기'],
        unsupported_sentences=('N2.s2',))

    # 06. Crowded market: pushes out of it; quiet market: habitually stands in front of a shop.
    v.persona(
        'R_lost_reaction_06', FAMILY, ['local:C25'],
        [{'label': '한빛재래시장', 'place_type': 'market'},
         {'label': '솔밭어린이공원', 'place_type': 'park'},
         {'label': '샘골 옛집', 'place_type': 'past_home'}],
        [(v.DEFAULT_INTRO, '한빛재래시장은 어머니가 일주일에 서너 번 장 보러 가시는 시장이에요. '
                           '솔밭어린이공원은 손주들 데리고 자주 가던 공원이고, 샘골 옛집은 예전에 살던 동네예요.'),
         ('시장에서 놓치신 적이 있나요?',
          '네, 몇 번 있어요. 장날처럼 사람이 북적일 때 길 잃은 걸 아시면 숨이 막힌다면서 사람 없는 쪽으로 막 빠져나오세요. '
          '시장을 벗어나시면 그다음부터는 그냥 평소처럼 걸으세요.'),
         ('사람이 별로 없을 때는요?',
          '한산한 날은 달라요. 그럴 땐 길 잃은 걸 아셔도 빠져나오지 않고 늘 시장 안 단골 떡집 앞에 우두커니 서 계세요. '
          '지난달 평일 오후에 놓쳤을 때도 거기서 한참을 그러고 계셨어요.')],
        [v.spec('avoid_market', 'lost_awareness and market.crowded', ids=('N1',)),
         v.spec('wait', 'lost_awareness and not market.crowded', ids=('N2',), labels=('한빛재래시장',))],
        [v.case('trigger',
                v.nearby('market', lost_awareness=True, crowded=True, current_place_label='한빛재래시장'),
                ['avoid_market'], '붐비는 시장 안에서 길 잃음을 알아차림 → 시장 밖으로 빠져나옴'),
         v.case('non_trigger',
                v.nearby('market', lost_awareness=False, crowded=True, current_place_label='한빛재래시장'),
                ['baseline'], '붐비더라도 길 잃음 인지가 없으면 개인 반응 없음'),
         v.case('boundary_or_release',
                v.nearby('market', lost_awareness=True, crowded=False, current_place_label='한빛재래시장'),
                ['wait'], '한산한 시장에서 길 잃음 인지 → 빠져나오지 않고 가게 앞에 서 있음'),
         v.case('unobserved_or_conflict',
                v.nearby('market', lost_awareness=True, crowded=None, current_place_label='한빛재래시장'),
                [], '시장 혼잡 관측이 없으면 빠져나옴과 서 있음이 모두 가능', status='unknown',
                possible=['avoid_market', 'wait'])],
        '시장에서 길 잃음을 알면 붐빌 때는 시장 밖으로 빠져나오고, 한산할 때는 늘 단골 가게 앞에 서 있음'
        '(습관 진술 N2.s2가 있고 N2.s3 일화는 그 예시). 근거: local:C25=방법론. 직접 근거 없음.',
        ['혼잡한 시장 + 길 잃음 인지 → 시장 회피', '한산한 등록 시장 → 대기', '혼잡 미관측 → 회피·대기 분기'])

    # 07. Keeps walking up to a stated distance, rests, repeats; after many hours settles for good.
    v.persona(
        'R_lost_reaction_07', FAMILY, ['webA:C08', 'webB:C11'],
        [{'label': '갈매천 산책로', 'place_type': 'park'},
         {'label': '옛 철공소', 'place_type': 'workplace'},
         {'label': '두루미역', 'place_type': 'station'}],
        [(v.DEFAULT_INTRO, '갈매천 산책로는 아버지가 매일 두 시간씩 걷던 길이고, 옛 철공소는 은퇴 전까지 일하시던 곳이에요. '
                           '두루미역은 예전에 장 보러 다니실 때 타던 역이에요.'),
         ('길을 잃으셨다는 걸 아셨을 때 아버님 모습이 어떠셨어요?',
          '아버지는 길을 잃은 걸 아셔도 걸음을 늦추질 않으세요. 한 1.3킬로쯤 갈 때까지는 쉬지 않고 내리 걸으세요.'),
         ('그렇게 걸으시다가 쉬기는 하세요?',
          '그쯤 가시면 길가 아무 데나 앉아서 한 십오 분 쉬세요. 그러고는 다시 일어나서 또 걸으세요.'),
         ('오래 못 찾으셨을 때는 어떤 모습이셨어요?',
          '재작년에 다섯 시간 만에 찾았을 때는 둑방 풀숲 가장자리에 앉아 계셨는데, 일으켜 드려도 안 일어나시려고 했어요. '
          '한나절쯤 헤매고 나면 그렇게 아예 눌러앉아 버리시는 것 같아요.')],
        [v.spec('walk', 'lost_awareness and distance_since_rest_m < 1300', ids=('N1',)),
         v.spec('rest', 'is_walking and distance_since_rest_m >= 1300', ids=('N1', 'N2'), hold=15)],
        [v.case('trigger', v.scene(lost_awareness=True, distance_since_rest_m=500), ['walk'],
                '길 잃음 인지 후 쉰 뒤 500m → 멈추지 않고 계속 걸음'),
         v.case('non_trigger', v.scene(lost_awareness=False, distance_since_rest_m=500), ['baseline'],
                '길 잃음 인지가 없고 쉴 거리 전 → 개인 반응 없음'),
         v.case('boundary_or_release', v.scene(lost_awareness=True, distance_since_rest_m=1300), ['rest'],
                '쉬지 않고 1.3km에 도달 → 계속 걷기가 끝나고 앉아 쉼'),
         v.case('unobserved_or_conflict', v.scene(lost_awareness=True, distance_since_rest_m=None), [],
                '쉰 뒤 걸은 거리를 모르면 계속 걷기와 휴식이 모두 가능', status='unknown',
                possible=['rest', 'walk'])],
        '길 잃음을 알아도 1.3km쯤까지 쉬지 않고 걷고, 앉아 15분 쉰 뒤 다시 걸음. '
        '한나절 헤맨 뒤 아예 주저앉는 점은 경과 시간 사실이 없어 표현 불가. '
        '근거: webA:C08=간접(몇 시간 안에 이동을 멈춘다는 교육자료 요약, 표현 불가 문장 N3만 뒷받침), '
        'webB:C11=간접(Rowe 2011, 자연지대에 머문 사례, N3만 뒷받침). 걷기·휴식 규칙의 직접 근거 없음.',
        ['길 잃음 인지 + 1.3km 전 → 계속 걷기', '보행 중 1.3km 도달 → 휴식', '거리 미확인 → 걷기·휴식 분기'],
        unsupported_sentences=('N3.s1', 'N3.s2'))

    # 08. Usually unaware of being lost; once made aware, freezes until a family member arrives.
    v.persona(
        'R_lost_reaction_08', FAMILY, ['webB:C31', 'corpusB:C45'],
        [{'label': '마루공원', 'place_type': 'park'},
         {'label': '가온시장', 'place_type': 'market'},
         {'label': '버드내 옛집', 'place_type': 'past_home'}],
        [(v.DEFAULT_INTRO, '마루공원은 장인어른이 아침마다 바둑 두러 가시는 공원이고, 가온시장은 장모님 살아 계실 때 같이 다니던 시장이에요. '
                           '버드내 옛집은 고향 집인데 지금은 헐렸어요.'),
         ('길을 잃으셨을 때 본인이 그걸 아시는 편인가요?',
          '정작 본인은 헤매고 계신 줄을 거의 모르시고, 그냥 바람 쐬러 나온 줄 아세요.'),
         ('누가 알려 드리거나 스스로 깨달으시면 어떻게 하시던가요?',
          '한번은 지나가던 학생이 할아버지 길 잃으셨냐고 묻자 그제야 당황하셔서 길모퉁이에 그대로 굳어 버리셨대요. '
          '그 뒤로도 길 잃은 걸 알아채신 날은 매번 그러세요. 식구 얼굴을 보기 전까지는 한 발짝도 안 떼세요.')],
        [v.spec('wait', 'lost_awareness and not family_present', ids=('N2',))],
        [v.case('trigger', v.scene(lost_awareness=True, family_present=False), ['wait'],
                '길 잃음을 알게 되었고 곁에 가족이 없음 → 그대로 굳음'),
         v.case('non_trigger', v.scene(lost_awareness=False), ['baseline'],
                '길 잃은 줄 모르고 바람 쐬러 나온 줄 앎 → 개인 반응 없음'),
         v.case('boundary_or_release', v.scene(lost_awareness=True, family_present=True), ['baseline'],
                '식구가 곁에 오면 굳어 있던 반응이 풀림'),
         v.case('unobserved_or_conflict', v.scene(lost_awareness=None), [],
                '본인이 길 잃음을 알아챘는지 모르면 굳음과 평소 이동이 모두 가능', status='unknown',
                possible=['baseline', 'wait'])],
        '대개 길 잃은 줄 모름(병식 부족, 규칙 없음·표현 불가). 알게 되면 그대로 굳고, 식구가 와야 풀림. '
        '보호자가 오는 중이라는 동행 맥락이 아니라 알아챈 직후 스스로 굳는 모습이며 가족 도착은 해제 조건임. '
        '근거: webB:C31·corpusB:C45=간접(길 잃음·결손을 자각하지 못하는 집단 경향, N1만 뒷받침). '
        '굳음·해제 규칙의 직접 근거 없음.',
        ['길 잃음 인지 + 혼자 → 대기', '가족이 곁에 오면 대기 해제', '길 잃음 인지 미확인 → 대기·평소 분기'],
        unsupported_sentences=('N1.s1',))

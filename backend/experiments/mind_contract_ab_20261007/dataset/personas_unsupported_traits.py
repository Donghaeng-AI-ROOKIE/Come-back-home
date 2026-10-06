"""Research personas: unsupported_traits family (AI draft, unreviewed).

Each persona carries guardian sentences describing a trait the current engine
cannot express (keeping the first heading and walking fast, hiding in cover,
returning to the current home, riding any train or bus, frequent heading
changes, stopping where the path ends, looping around unregistered shops,
crossing roads without looking and trying to drive). Those sentence IDs go to
unsupported_sentences and have no reference rule. They sit at different note
positions on purpose. Representable behavior in the same persona is written as
a rule; the family mixes avoid, wait, seek and one rest rule so that most
scenes do not reduce to a walking-limit check.
Brief: MIND_research_personas_20261007/family_briefs/unsupported_traits.json.
"""

FAMILY = 'unsupported_traits'


def register(v):
    # 01. Keeping the first heading and walking fast (unsupported, N2-N3);
    #     avoiding the stream side only when it is crowded (supported, N1).
    v.persona(
        'R_unsupported_traits_01', FAMILY,
        ['corpusA:DM-14', 'webA:C12', 'webA:C01', 'webB:C03'],
        [{'label': '오얏골 우체국', 'place_type': 'workplace'},
         {'label': '참빗골 경로당', 'place_type': 'senior_center'}],
        [('등록해 두신 우체국이랑 경로당 얘기를 좀 해 주세요.',
          '오얏골 우체국은 아버지가 집배원으로 삼십 년 넘게 일하신 곳이에요. '
          '참빗골 경로당은 몇 년 다니시다가 작년부터는 안 나가세요.'),
         ('산책하실 때 가리시는 길이 있나요?',
          '개천 산책로에 사람이 바글바글하면 물가 쪽으로는 안 내려가세요. '
          '한산할 때는 물가 길로도 잘 다니시고요.'),
         ('혼자 나가셨다가 찾으셨던 때 얘기를 들려주세요.',
          '대문을 나서서 처음 잡은 방향에서 벗어나질 않으세요. '
          '갈림길이 나와도 고개를 안 돌리시고, 찾고 보면 늘 집에서 나간 쪽으로 곧게 그은 선 위 어디쯤에 계셨어요.'),
         ('혼자 걸으실 때 빠르기는 어느 정도예요?',
          '워낙 빠르세요. 제가 신발 신고 따라 나가 보면 그새 골목 두 개는 지나가 계세요.')],
        [v.spec('avoid_water', 'water.crowded', ids=('N1',))],
        [v.case('trigger', v.nearby('water', crowded=True),
                ['avoid_water'], '개천 근처가 붐비므로 물가를 피한다.'),
         v.case('non_trigger', v.nearby('water', crowded=False, continuous_walk_minutes=46, distance_since_rest_m=3100),
                ['baseline'], '물가가 한산하다. 다닌다는 말은 걷기 명령이 아니고, 한 방향 고집과 빠른 걸음도 명령으로 만들지 않는다.'),
         v.case('boundary_or_release', v.nearby('water', noisy=True, crowded=False),
                ['baseline'], '시끄럽기만 하고 붐비지 않으면 물가를 피하지 않는다.'),
         v.case('unobserved_or_conflict', v.nearby('water', crowded=None),
                [], '개천 근처지만 붐비는지 관측되지 않았다.', status='unknown',
                possible=['avoid_water', 'baseline'])],
        '처음 나간 방향에서 벗어나지 않고 걸음이 빠른 아버지. 방위 유지와 보행 속도 개인차는 현재 엔진이 표현하지 못한다. '
        '실행 가능한 것은 개천가가 붐빌 때 물가 회피뿐이다. 우체국·경로당은 행동 근거가 아니다.',
        ['붐비는 개천 근처에서 물가 회피', '한산한 물가·오래 걷기에서 반응 없음(한 방향 고집·빠른 걸음은 명령 아님)',
         '소음만 있고 붐비지 않으면 회피 없음', '붐빔 미관측이면 미확인'],
        unsupported_sentences=('N2.s1', 'N2.s2', 'N3.s1', 'N3.s2'))

    # 02. Found twice hiding behind a hedge or between outdoor units, not
    #     answering (unsupported, N3; stated without a trigger); avoiding the
    #     wooded hill path on rainy days (supported, N1).
    v.persona(
        'R_unsupported_traits_02', FAMILY,
        ['corpusA:DM-30', 'webA:C19', 'webA:C14', 'corpusA:DM-33', 'webB:C11', 'corpusB:C16'],
        [{'label': '방울샘 시장', 'place_type': 'market'},
         {'label': '능소화 연립', 'place_type': 'past_home'}],
        [('어머님께 두 장소가 어떤 데인지 여쭤봐도 될까요?',
          '방울샘 시장은 장 보러 자주 다니시던 곳이고, 능소화 연립은 아홉 해 전에 이사 나온 집이에요. '
          '이사 온 뒤로는 그 동네에 가신 적이 없어요.'),
         ('밖에서 꺼리시는 데가 있을까요?',
          '비 오는 날엔 뒷산 숲길 쪽으로는 발을 안 들이세요. '
          '몇 해 전에 젖은 나무 계단에서 미끄러지신 뒤로 그러세요. '
          '날이 맑으면 숲길도 상관없이 다니세요.'),
         ('요즘 다리 힘은 어떠세요?',
          '다리는 아직 튼튼하세요. 지팡이 없이도 동네 한 바퀴는 거뜬하세요.'),
         ('밖에서 어머님을 찾아냈던 자리가 기억나세요?',
          '두 번 다 사람 눈에 잘 안 띄는 데 계셨어요. '
          '한 번은 놀이터 옆 쥐똥나무 울타리 안쪽에, 한 번은 상가 뒤편 실외기 틈에 쪼그려 앉아 계셨어요. '
          '이름을 불러도 대답을 안 하셔서 바로 옆을 몇 번이나 지나쳤어요.')],
        [v.spec('avoid_forest', 'rain_observed', ids=('N1',))],
        [v.case('trigger', v.nearby('forest', rain_observed=True),
                ['avoid_forest'], '비가 오고 숲길 근처이므로 숲을 피한다.'),
         v.case('non_trigger', v.scene(anxiety_high=True, lost_awareness=True,
                                       map_distance_m={'market': 40, 'park': 30, 'forest': 1000, 'water': 1000}),
                ['baseline'], '숲이 멀고 비도 없다. 숨어 있던 발견 기록은 불안·길 잃음 인지·공원이나 상가 근처에서 대기나 회피 명령이 되지 않는다.'),
         v.case('boundary_or_release', v.nearby('forest', rain_observed=False),
                ['baseline'], '맑은 날에는 숲길 근처여도 피하지 않는다. 다닌다는 말을 걷기 명령으로 바꾸지 않는다.'),
         v.case('unobserved_or_conflict', v.nearby('forest', rain_observed=None),
                [], '숲길 근처지만 비가 오는지 관측되지 않았다.', status='unknown',
                possible=['avoid_forest', 'baseline'])],
        '두 번 다 울타리 안쪽이나 실외기 틈에 숨어 있다가 발견된 어머니. 근거리 은신 후 정지는 표현할 수 없고, 보호자도 계기를 말하지 않았다. '
        '실행 가능한 것은 비 오는 날 숲길 회피다. 옛집과 다리 힘 진술은 행동 근거가 아니다.',
        ['비 오는 날 숲 근처에서 숲 회피', '은신 발견 기록이 불안·길 잃음·공원/상가 근처에서 대기나 회피가 되지 않음',
         '맑은 날 숲 근처는 반응 없음(걷기 명령 아님)', '비 미관측이면 미확인'],
        unsupported_sentences=('N3.s1', 'N3.s2', 'N3.s3'))

    # 03. Returning to the current home by asking passers-by (unsupported, N2);
    #     turning toward a registered market in a late-afternoon window unless
    #     it rains, also when already outside (supported, N1).
    v.persona(
        'R_unsupported_traits_03', FAMILY,
        ['webB:C43', 'corpusA:DM-32', 'webA:C30', 'local:C25'],
        [{'label': '한내 시장', 'place_type': 'market'},
         {'label': '바람재 공원', 'place_type': 'park'},
         {'label': '돌담 골목 옛집', 'place_type': 'past_home'}],
        [('세 곳이 남편분 생활에서 어떤 자리인지 말씀해 주세요.',
          '한내 시장은 남편이 오후마다 막걸리 받으러 다니던 데고, 바람재 공원은 지금 아파트 바로 앞이에요. '
          '돌담 골목 옛집은 신혼 살림을 차렸던 집인데 재개발로 헐린 지 오래예요.'),
         ('하루 중에 꼭 하시는 일이 있나요?',
          '오후 4시 반쯤 되면 밖에 계시다가도 시장 가야 한다면서 한내 시장 쪽으로 방향을 트세요. '
          '저녁 6시가 넘으면 그 말씀이 쏙 들어가고, 비가 오는 날은 시장 갈 생각을 아예 안 하세요.'),
         ('지난번에 늦게 들어오신 날은 어떻게 된 거였어요?',
          '아파트 이름은 또렷이 기억하셔서, 헤매시다가도 경비 아저씨나 가게 주인한테 그 이름을 대고 길을 물어 결국 집 앞까지는 오세요. '
          '지난달엔 나가신 지 두 시간 반쯤 지나서 혼자 초인종을 누르셨어요.')],
        [v.spec('seek_0', 'clock_hour >= 16.5 and clock_hour < 18 and not rain_observed', ids=('N1',))],
        [v.case('trigger', v.scene(clock_hour=16.75),
                ['seek_0'], '오후 4시 반 이후, 6시 전, 비가 없으므로 한내 시장 쪽으로 향한다.'),
         v.case('non_trigger', v.scene(lost_awareness=True, home_pull_high=True, clock_hour=11.5),
                ['baseline'], '시간대 밖이다. 물어물어 지금 집으로 돌아오는 성향은 실행 명령이 없고, 헐린 옛집이나 집 앞 공원 출발로 바꾸지 않는다.'),
         v.case('boundary_or_release', v.scene(clock_hour=18.4),
                ['baseline'], '저녁 6시가 넘으면 시장 쪽으로 가지 않는다.'),
         v.case('unobserved_or_conflict', v.scene(clock_hour=17.2, rain_observed=None),
                [], '시간대는 맞지만 비가 오는지 관측되지 않았다.', status='unknown',
                possible=['baseline', 'seek_0'])],
        '길을 잃어도 아파트 이름을 대고 물어 지금 집으로 돌아오는 남편. 현재 집 귀가는 표현할 수 없다. '
        '실행 가능한 것은 오후 4시 반~6시 사이 비가 없을 때 밖에 있다가도 한내 시장 쪽으로 향하는 반응이다.',
        ['시간대 안·비 없음이면 시장 쪽 출발', '길 잃음·귀소 충동만으로 옛집·공원 출발을 만들지 않음',
         '6시 이후 출발 없음', '비 미관측이면 미확인'],
        unsupported_sentences=('N2.s1', 'N2.s2'))

    # 04. Slipping through the gate onto any train and boarding any bus
    #     (unsupported, N1 and N3); a measured distance-limited rest (supported, N2).
    v.persona(
        'R_unsupported_traits_04', FAMILY,
        ['webA:C10', 'webB:C47', 'webB:C48', 'webA:C21'],
        [{'label': '두물목역', 'place_type': 'station'},
         {'label': '청기와 한의원', 'place_type': 'hospital'}],
        [('역이랑 한의원을 등록하신 이유가 있을까요?',
          '두물목역은 집에서 제일 가까운 지하철역이고, 청기와 한의원은 허리 침 맞으러 일주일에 두 번 저랑 같이 다니는 데예요.'),
         ('혼자 멀리 가신 적이 있나요?',
          '개찰구에서 앞사람 뒤에 바짝 붙어 들어가서는 오는 열차 아무거나 타고 가 버리세요. '
          '두 번이나 종점 근처 역에서 역무원이 연락을 줬어요.'),
         ('밖에서 걸으시다가 멈추시는 때가 있나요?',
          '휴대폰 걸음 앱으로 같이 재 봤더니 640미터쯤 걸으면 꼭 멈춰 서서 숨을 고르세요. '
          '9분쯤 그러고 계시다가 다시 걸으세요.'),
         ('버스는 어떠세요?',
          '정류장 앞을 지나다 문 열린 버스가 있으면 어디 가는 건지 상관없이 올라타세요. '
          '기사님이 말려도 손사래를 치세요.')],
        [v.spec('rest', 'is_walking and distance_since_rest_m >= 640', ids=('N2',), hold=9)],
        [v.case('trigger', v.scene(continuous_walk_minutes=14, distance_since_rest_m=700),
                ['rest'], '640미터를 넘겨 걸었으므로 멈춰 숨을 고른다.'),
         v.case('non_trigger', v.scene(current_place_label='두물목역', lost_awareness=True,
                                       continuous_walk_minutes=5, distance_since_rest_m=260),
                ['baseline'], '역에 있고 길 잃음 인지가 있어도 열차·버스를 탄다는 진술은 역 출발이나 대기 명령이 아니다. 휴식 거리 전이다.'),
         v.case('boundary_or_release', v.scene(continuous_walk_minutes=11.5, distance_since_rest_m=640),
                ['rest'], '640미터에 도달하면 멈춰 쉰다(이상 관례).'),
         v.case('unobserved_or_conflict', v.scene(continuous_walk_minutes=16, distance_since_rest_m=None),
                [], '마지막 휴식 뒤 걸은 거리가 관측되지 않아 휴식 여부를 정할 수 없다.', status='unknown',
                possible=['baseline', 'rest'])],
        '개찰구를 따라 들어가 아무 열차나 타고, 문 열린 버스에도 행선지를 안 보고 오르는 아버지. 대중교통 이동은 표현할 수 없다. '
        '실행 가능한 것은 걸음 앱으로 잰 640미터 보행 후 9분 휴식이다. 역 등록은 탑승이나 출발 근거가 아니다.',
        ['640미터 넘게 걸으면 휴식(9분)', '역·길 잃음 인지가 있어도 열차·버스 탑승 문장이 역 출발이나 대기가 되지 않음',
         '정확히 640미터 도달 시 휴식(이상 관례 검사)', '거리 미관측이면 미확인'],
        unsupported_sentences=('N1.s1', 'N1.s2', 'N3.s1', 'N3.s2'))

    # 05. Darting in and out of alleys once off the home block (unsupported, N3);
    #     leaving a packed market only when she gets agitated (supported, N1).
    v.persona(
        'R_unsupported_traits_05', FAMILY,
        ['corpusA:DM-17', 'corpusA:DM-18', 'corpusB:C17', 'corpusB:C49', 'corpusB:C11', 'corpusB:C51'],
        [{'label': '쑥부쟁이 공원', 'place_type': 'park'},
         {'label': '큰아들 타일 가게', 'place_type': 'workplace'}],
        [('어머님이 다니시던 곳들을 소개해 주시겠어요?',
          '쑥부쟁이 공원은 친구분들이랑 아침 체조하시던 데고, 큰아들 타일 가게는 제 남편 가게라 가끔 들르셨어요.'),
         ('어머님이 싫어하시는 장소나 상황이 있나요?',
          '시장통에 사람이 꽉 차 있으면 처음엔 그냥 다니시다가, 안절부절못하고 초조해지시면 그때는 시장 밖으로 빠져나오세요. '
          '사람이 많아도 마음이 편하실 땐 끝까지 구경하세요.'),
         ('식구들은 잘 알아보세요?',
          '저희 얼굴은 아직 다 알아보세요. 이름은 가끔 헷갈리셔도요.'),
         ('헤매실 때 모습을 보신 적이 있으세요?',
          '본인은 길 잃은 줄도 모르시고 이 골목에 들어갔다 도로 나와서 저 골목으로 들어가세요. '
          '저희 아파트 근처에서는 아직 괜찮은데 큰길 하나만 건너가시면 그렇게 갈피를 못 잡으세요.')],
        [v.spec('avoid_market', 'market.crowded and anxiety_high', ids=('N1',))],
        [v.case('trigger', v.nearby('market', crowded=True, anxiety_high=True),
                ['avoid_market'], '붐비는 시장 근처에서 초조해졌으므로 시장을 벗어난다.'),
         v.case('non_trigger', v.scene(anxiety_high=True, continuous_walk_minutes=19, distance_since_rest_m=860),
                ['baseline'], '시장이 멀다. 초조함만으로, 또 골목을 들락거리는 방향 전환 진술로 회피나 걷기 명령을 만들지 않는다.'),
         v.case('boundary_or_release', v.nearby('market', crowded=True, anxiety_high=False),
                ['baseline'], '사람이 많아도 초조하지 않으면 시장을 피하지 않는다.'),
         v.case('unobserved_or_conflict', v.nearby('market', crowded=True, anxiety_high=None),
                [], '붐비는 시장 근처지만 초조한지 관측되지 않았다.', status='unknown',
                possible=['avoid_market', 'baseline'])],
        '아파트 근처를 벗어나면 길 잃은 줄 모른 채 골목을 들락거리며 방향을 자주 바꾸는 시어머니. 방향 무작위성 개인차는 표현할 수 없다. '
        '실행 가능한 것은 붐비는 시장에서 초조해질 때 시장을 벗어나는 반응이다.',
        ['붐비는 시장 근처+초조함이면 시장 회피', '초조함만이나 방향 전환 진술로 회피·걷기 명령을 만들지 않음',
         '붐벼도 초조하지 않으면 회피 없음', '초조함 미관측이면 미확인'],
        unsupported_sentences=('N3.s1', 'N3.s2'))

    # 06. Going to where the path runs out and staying there (unsupported, N2);
    #     standing still while it is dark (supported, N1).
    v.persona(
        'R_unsupported_traits_06', FAMILY,
        ['webA:C01', 'webB:C03', 'webB:C35', 'webA:C02', 'webB:C02'],
        [{'label': '상촌 마을회관', 'place_type': 'senior_center'},
         {'label': '고갯마루 복숭아밭', 'place_type': 'workplace'}],
        [('마을회관과 복숭아밭을 등록하신 까닭이 궁금해요.',
          '상촌 마을회관은 동네 어르신들이 모이는 데라 낮에 가끔 앉아 계시던 곳이고, '
          '고갯마루 복숭아밭은 평생 농사지으신 밭인데 작년에 남한테 넘겼어요.'),
         ('시간대에 따라 달라지시는 게 있나요?',
          '어둑어둑해지면 걷던 걸 멈추고 그 자리에 서서 안 움직이세요. '
          '동이 트고 훤해져야 다시 걸음을 떼세요.'),
         ('막다른 길을 만나시면 어떻게 하세요?',
          '길이 끊긴 데까지 가시면 거기서 그만이에요. '
          '되짚어 나오실 생각을 못 하시고 끝에 그대로 서 계세요. '
          '지난번엔 비닐하우스 사이 농로가 끝나는 데서, 그 전엔 공사장 가림막 앞에서 찾았어요.')],
        [v.spec('wait', 'dark_observed', ids=('N1',))],
        [v.case('trigger', v.scene(dark_observed=True, continuous_walk_minutes=21, distance_since_rest_m=980),
                ['wait'], '어둠이 관측되어 그 자리에 멈춰 선다.'),
         v.case('non_trigger', v.scene(lost_awareness=True, fatigue_high=True, continuous_walk_minutes=38,
                                       distance_since_rest_m=2300, clock_hour=15),
                ['baseline'], '밝은 낮이다. 길 잃음 인지나 높은 피로가 있어도 길 끝에서 멈춰 서는 성향을 대기·휴식 명령으로 옮기지 않는다.'),
         v.case('boundary_or_release', v.scene(current_action='wait', clock_hour=6.5),
                ['baseline'], '훤해져 어둠이 관측되지 않으면 대기가 끝난다.'),
         v.case('unobserved_or_conflict', v.scene(dark_observed=None, continuous_walk_minutes=14, distance_since_rest_m=620),
                [], '어둠이 관측되지 않아 제자리 대기 여부를 정할 수 없다.',
                status='unknown', possible=['baseline', 'wait'])],
        '길이 끊긴 곳까지 가서 되짚어 나오지 않고 그 끝에 서 있는 장인어른. 막힘 정지는 표현할 수 없다. '
        '실행 가능한 것은 어두운 동안 제자리 대기다. 마을회관과 넘긴 밭은 행동 근거가 아니다.',
        ['어둠 관측 시 제자리 대기', '길 잃음·높은 피로가 있어도 길 끝 정지 문장이 대기·휴식이 되지 않음',
         '밝아지면 대기 해제', '어둠 미관측이면 미확인'],
        unsupported_sentences=('N2.s1', 'N2.s2', 'N2.s3'))

    # 07. Looping around an unregistered shop block (unsupported, N2);
    #     sheltering under the eaves of a registered church while it rains there
    #     (supported, N1). No loop stop is a registered place.
    v.persona(
        'R_unsupported_traits_07', FAMILY,
        ['corpusB:C50', 'webB:C54'],
        [{'label': '언덕배기 교회', 'place_type': 'religious'},
         {'label': '둘째딸네 빌라', 'place_type': 'relative_home'}],
        [('교회와 따님 댁을 고르신 이유가 있나요?',
          '언덕배기 교회는 집사람이 마흔 해 가까이 다닌 교회고, 둘째딸네 빌라는 손주 봐 주러 한동안 드나들던 집이에요. '
          '요즘은 딸네가 이리로 와요.'),
         ('교회 앞을 지나실 때 보이시는 모습이 있나요?',
          '교회 앞을 지나다가 비를 만나면 현관 처마 밑에 들어가서 비가 그칠 때까지 서 있어요. '
          '다른 데서는 비가 와도 그냥 맞고 다녀요.'),
         ('혼자 나가시면 주로 뭘 하세요?',
          '아파트 뒤 상가 블록을 빙빙 돌아요. '
          '세탁소 지나 떡집 지나 놀이터 앞으로 해서 다시 세탁소로, 그렇게 서너 바퀴씩 돌아요. '
          '뭘 사러 가는 것도 아니고 그 블록만 그렇게 돌아요.'),
         ('낮에 집 안에서는 어떻게 시간을 보내세요?',
          '텔레비전 앞에 앉아 계시다가 졸다가 하세요.')],
        [v.spec('wait', 'rain_observed', ids=('N1',), labels=('언덕배기 교회',))],
        [v.case('trigger', v.scene(current_place_label='언덕배기 교회', rain_observed=True),
                ['wait'], '교회 앞에서 비를 만났으므로 처마 밑에서 기다린다.'),
         v.case('non_trigger', v.scene(rain_observed=True, continuous_walk_minutes=31, distance_since_rest_m=1520,
                                       map_distance_m={'market': 40, 'park': 50, 'forest': 1000, 'water': 1000}),
                ['baseline'], '교회 밖에서는 비가 와도 기다리지 않는다. 상가 블록 순회를 장소 출발·회피·걷기 명령으로 만들지 않는다.'),
         v.case('boundary_or_release', v.scene(current_place_label='언덕배기 교회', current_action='wait', rain_observed=False),
                ['baseline'], '비가 그치면 처마 밑 대기가 끝난다.'),
         v.case('unobserved_or_conflict', v.scene(current_place_label='언덕배기 교회', rain_observed=None),
                [], '교회 앞이지만 비가 오는지 관측되지 않았다.', status='unknown',
                possible=['baseline', 'wait'])],
        '아파트 뒤 상가 블록(세탁소·떡집·놀이터, 모두 미등록)을 목적 없이 빙빙 도는 아내. 순회는 표현할 수 없다. '
        '실행 가능한 것은 언덕배기 교회 앞에서 비를 만나면 그칠 때까지 처마 밑에서 기다리는 반응이다. '
        '순회 근거(corpusB:C50 시뮬레이션 모델, webB:C54 부분 검증 발표)는 약하다.',
        ['교회 앞에서 비가 오면 대기', '교회 밖의 비·상가 블록 순회는 대기·출발·걷기 명령이 되지 않음',
         '비가 그치면 대기 해제', '비 미관측이면 미확인'],
        unsupported_sentences=('N2.s1', 'N2.s2', 'N2.s3'))

    # 08. Crossing wide roads without looking (N2) and trying to drive (N4)
    #     (unsupported); waiting at one registered park until fetched (N1) and
    #     avoiding a loud market only after dark (N3) (supported).
    v.persona(
        'R_unsupported_traits_08', FAMILY,
        ['corpusA:DM-11', 'local:C18', 'webA:C47', 'webA:C06', 'corpusA:DM-19', 'webA:C26', 'webB:C15'],
        [{'label': '석류나무 체육공원', 'place_type': 'park'},
         {'label': '나루터 화물 영업소', 'place_type': 'workplace'}],
        [('남편분께 두 곳이 어떤 의미인지 들려주세요.',
          '석류나무 체육공원은 집 근처 공원이고, 나루터 화물 영업소는 남편이 화물차를 몰던 시절에 속해 있던 곳이에요. '
          '퇴직하고는 그 근처에 간 적이 없어요.'),
         ('체육공원 얘기를 조금 더 해 주실 수 있을까요?',
          '요즘은 혼자 체육공원에 가시면 늘 앉던 정자에 자리 잡고 제가 데리러 갈 때까지 꼼짝 않고 기다려요. '
          '제가 가면 그제야 일어나요.'),
         ('길을 건너실 때는 어떤가요?',
          '차가 오든 말든 좌우를 안 살피고 그냥 건너요. '
          '저번엔 왕복 육차선 도로 건너편 주유소 앞에서 찾았어요.'),
         ('동네 시장 골목은 어떻게 다니세요?',
          '해 지고 나서 시장 골목이 왁자지껄하면 그쪽을 피해서 조용한 뒷길로 돌아가요. '
          '낮에는 아무리 시끄러워도 그냥 지나다녀요.'),
         ('운전은 지금도 하려고 하세요?',
          '면허를 반납한 지 두 해가 넘었는데도 현관에 차 열쇠가 보이면 들고 나가서 주차장 차 문을 열어 보려고 해요. '
          '그래서 열쇠는 제 가방에만 넣고 다녀요.')],
        [v.spec('wait', 'not family_present', ids=('N1',), labels=('석류나무 체육공원',)),
         v.spec('avoid_market', 'dark_observed and market.noisy', ids=('N3',))],
        [v.case('trigger', v.scene(current_place_label='석류나무 체육공원', current_action='wait', clock_hour=16),
                ['wait'], '체육공원에 있고 아내가 오지 않았으므로 정자에서 기다린다.'),
         v.case('non_trigger', v.nearby('market', noisy=True, lost_awareness=True, clock_hour=13),
                ['baseline'], '체육공원 밖이고 낮이다. 시장이 시끄러워도 어둠이 없으면 피하지 않는다. 차도 횡단과 운전 시도는 실행 명령이 아니다.'),
         v.case('boundary_or_release', v.scene(current_place_label='석류나무 체육공원', current_action='wait',
                                                family_present=True),
                ['baseline'], '아내가 데리러 오면 대기가 끝난다. 그 뒤 행동은 진술되지 않았다.'),
         v.case('unobserved_or_conflict', v.nearby('market', noisy=True, dark_observed=None),
                [], '시끄러운 시장 근처지만 어두운지 관측되지 않았다.', status='unknown',
                possible=['avoid_market', 'baseline'])],
        '좌우를 살피지 않고 큰길을 건너고 아직 차를 몰려고 하는 남편. 횡단 위험 무인식과 차량 이동은 표현할 수 없다. '
        '실행 가능한 것은 석류나무 체육공원에서만의 대기와 어두울 때 시끄러운 시장 회피다. 화물차 경력은 운전 근거가 아니다.',
        ['체육공원에서 아내가 없으면 대기', '낮의 시끄러운 시장·길 잃음 인지로 회피나 대기를 만들지 않음(차도 횡단·운전은 명령 아님)',
         '아내 도착 시 대기 해제', '어둠 미관측이면 시장 회피 미확인'],
        unsupported_sentences=('N2.s1', 'N2.s2', 'N4.s1'))

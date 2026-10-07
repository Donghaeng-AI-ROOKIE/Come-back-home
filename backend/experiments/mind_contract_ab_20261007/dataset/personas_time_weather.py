"""time_weather research personas: 하루 중 시각·어둠·비에 따라 달라지는 본인 반응.

AI draft (Claude), 2026-10-07, review_status=draft_unreviewed. 작성자는 dev128·variants_*
개발 자료를 읽지 않았다. 근거는 family_briefs/time_weather.json의 evidence id만 인용한다.
집단 통계(일몰증후군 유병률 등)를 개인 규칙으로 옮기지 않았고, 보호자가 이 사람에게서
실제로 본 모습만 조건부 행동으로 썼다. 참조 규칙은 장면 기대와의 내부 일관성 확인용이며
문장 의미나 임상 타당성을 보증하지 않는다. 같은 날 독립 검토 의견을 반영해 고쳤다.

덮는 축
- 어둠 관측 기반(R01, R05, R08)과 시각 기반(R02, R04, R06, R07) 구분, 시각으로 어둠을 추정하지 않는 반례(R01)
- 자정을 넘는 시각 구간(R02, R04, R06)과 종료 경계(R02, R04, R06, R07). 경계 장면은 원문의 끝점을
  포함·제외 어느 쪽으로 읽어도 구간이 끝난 게 분명한 시각에 둔다.
- 비 단독(R03), 어둠 AND 비(R05), 어둠 OR 비(R08), 비 미관측(R05)
- 해제 조건(R01 가족, R06 가족), 동행이 있어도 해제되지 않는 반례(R07), 장소 유형 범위(R03 공원 60m,
  R08 물가 100m), 지도 미확인(R08)
- 저녁이 아니라 이른 오후에 심해지는 반례(R07)
- 시각·보행량처럼 엔진이 늘 계산하는 값을 None으로 둔 미관측 장면(R02 S4, R04 S4)은 합성 장면이며
  규칙이 그 값에 의존하는지만 확인한다.
"""


def register(v):
    # R01: 어둠이 관측되면 눈에 띄는 자리에 앉아 기다림. 가족이 오면 해제. 시각으로 어둠을 추정하지 않음.
    v.persona(
        'R_time_weather_01', 'time_weather',
        ['corpusA:DM-12', 'webB:C36'],
        [{'label': '물푸레공원', 'place_type': 'park'},
         {'label': '장터골목 시장', 'place_type': 'market'},
         {'label': '예전 살던 연립', 'place_type': 'past_home'}],
        [(v.DEFAULT_INTRO,
          '물푸레공원은 집 앞에 있는 공원이라 적었고, 장터골목 시장은 예전에 장 보러 다니시던 데예요. '
          '예전 살던 연립은 이사 오기 전에 이십 년 넘게 사신 곳이고요. 요즘 혼자 그쪽으로 가신 적은 없어요.'),
         ('밖에서 날이 저물었을 때는 어떻게 하시던가요?',
          '날이 어둑어둑해지면 더 걷지를 않으시고, 가게 앞 계단이나 정류장 의자처럼 눈에 띄는 데 자리를 잡고 꼼짝을 안 하세요. '
          '지난겨울에 두 번을 그렇게 앉아 계신 걸 찾았어요. '
          '제가 가서 손을 잡아 드리면 그제야 일어나서 같이 걸어오시고요.'),
         ('그게 대략 몇 시쯤부터라고 보시나요?',
          '몇 시라고 딱 잘라 말하기는 어려워요. 여름엔 저녁 일곱 시 반이 넘어도 훤하잖아요. '
          '훤할 때는 계속 걸어 다니시고, 어두워져야 앉으시더라고요.'),
         ('흐리거나 궂은 날에는 달라지는 게 있나요?',
          '흐린 날엔 낮에도 길을 더 헤매시는 것 같아요. 그래도 그런 날 낮에 앉아 계신 적은 없어요.'),
         ('댁에 계실 때 저녁 무렵은 어떠세요?',
          '집에서는 저녁 드시고 나면 좀 예민해지세요. 창밖을 보시면서 집에 가야 한다고 몇 번씩 말씀하시고요.')],
        [v.spec('wait', 'dark_observed and not family_present', ids=('N1', 'N2'))],
        [v.case('trigger', v.scene(dark_observed=True, clock_hour=18.2), ['wait'],
                '어둠이 관측됐고 가족이 곁에 없음 → 앉아서 기다림.'),
         v.case('non_trigger', v.scene(dark_observed=False, clock_hour=19.8), ['baseline'],
                '저녁 늦은 시각이지만 어둠이 관측되지 않음(여름 저녁). 시각만으로 어둠을 만들지 않음.'),
         v.case('boundary_or_release', v.scene(dark_observed=True, family_present=True, clock_hour=21.0),
                ['baseline'], '가족이 와서 손을 잡으면 일어나 같이 걸음 → 대기 해제.'),
         v.case('unobserved_or_conflict', v.scene(dark_observed=None, clock_hour=20.3), [],
                '밤 8시 넘은 시각이지만 어둠 관측이 없음 → 시각으로 어둠을 추정하지 않고 미확인.',
                status='unknown', possible=['baseline', 'wait'])],
        '해가 저물어 어두워지면 눈에 띄는 자리에 앉아 꼼짝 않다가 가족이 오면 일어나는 어머니. '
        '보호자가 시각이 아니라 밝기로 구분한다고 직접 말함. 핵심 행동(어두워지면 앉아 기다림)의 직접 근거는 없음: '
        'DM-12는 사람마다 날씨·시간대 조건이 다르다는 데까지, C36은 어둠·흐림에서 길찾기가 떨어진다는 데까지다. '
        '해 진 뒤 밖 방황이 늘어난다는 webB:C56은 방향이 반대라 근거에서 뺐다. '
        '흐린 날 길찾기 저하는 표현 불가. 집 안 저녁 예민함과 창밖 보며 집에 가야 한다는 말(N4.s2)은 실내라 비행동으로 두었으나, '
        '귀가 충동이라는 본인 특성으로 볼지 사람 검토 필요.',
        ['trigger: 어둠 관측·가족 없음 → wait',
         'non_trigger: 19.8시·어둠 미관측 → baseline (시각으로 어둠 추정 금지)',
         'release: 어둠 관측·가족 도착 → baseline',
         'unobserved: 20.3시·어둠 None → unknown {baseline, wait}'],
        unsupported_sentences=('N3.s1',))

    # R02: 단지 카메라 녹화로 확인한 밤 10시 반~새벽 4시 반쯤(자정 넘음) 구간에 나간 시각과 상관없이 앉아 있음.
    v.persona(
        'R_time_weather_02', 'time_weather',
        ['corpusB:C04', 'corpusA:DM-23', 'corpusA:DM-39', 'webB:C08', 'corpusB:C20'],
        [{'label': '참샘 체육공원', 'place_type': 'park'},
         {'label': '큰길 버스정류장', 'place_type': 'station'},
         {'label': '둘째네 아파트', 'place_type': 'relative_home'}],
        [(v.DEFAULT_INTRO,
          '참샘 체육공원은 아파트 뒤편 공원이에요. 큰길 버스정류장은 복지관 버스를 타시던 데고, '
          '둘째네 아파트는 걸어서 삼십 분 거리라 예전에 자주 오가셨어요.'),
         ('밤중에 집을 나가신 적이 있었나요?',
          '올해만 세 번 있었어요. 세 번 다 제가 잠든 사이에 나가셔서 아침에 일어나서야 알았어요.'),
         ('밖에 계신 동안 어떻게 지내셨는지 아시는 게 있나요?',
          '세 번 다 다음 날 경비실에서 단지 카메라 녹화를 돌려 봤어요. '
          '일찍 나가신 날은 밤 10시 반까지 단지 안을 빙빙 도시다가 그때부터 정자나 계단참에 가만히 앉으셨고, '
          '자정 다 돼서 나가신 날은 나가자마자 바로 앉으셨어요. '
          '그러다 새벽 4시 반쯤 되면 일어나서 다시 걸어 나가셨고요.'),
         ('낮 시간에는 어떻게 지내세요?',
          '낮에는 혼자 나가지 않으세요. 복지관 차로 다녀오시고 오후엔 주무세요.')],
        [v.spec('wait', 'clock_hour >= 22.5 or clock_hour < 4.5', ids=('N2',))],
        [v.case('trigger', v.scene(clock_hour=1.25, dark_observed=True), ['wait'],
                '자정을 넘긴 새벽 1시 15분은 밤 10시 반~새벽 4시 반 구간 안 → 앉아서 기다림.'),
         v.case('non_trigger', v.scene(clock_hour=21.5, dark_observed=True), ['baseline'],
                '어둡지만 밤 10시 반 전 → 일찍 나간 날엔 이때 단지 안을 돌았음. 어둠은 이 사람의 조건이 아님.'),
         v.case('boundary_or_release', v.scene(clock_hour=5.0, dark_observed=None), ['baseline'],
                '새벽 5시는 4시 반쯤 일어난 뒤라 끝점을 어떻게 읽어도 구간이 끝남 → 다시 걷는 기본 이동.'),
         v.case('unobserved_or_conflict', v.scene(clock_hour=None), [],
                '합성 장면: 시각이 관측되지 않았다고 가정해 규칙이 시각에만 의존하는지 확인 '
                '(엔진에서는 시각이 늘 계산되어 실제로는 생기지 않음).',
                status='unknown', possible=['baseline', 'wait'])],
        '보호자가 자는 사이 밤에 나가는 아버지. 단지 카메라 녹화로 본 세 번 모두 나간 시각과 상관없이 밤 10시 반쯤부터 '
        '새벽 4시 반쯤까지 앉아 있다가 다시 걸어 나감(발견 시점 하나가 아니라 관찰된 구간). '
        '보호자 수면 중 출발했다는 문장은 출발 맥락(F18)이라 마음 규칙으로 표현되지 않음.',
        ['trigger: 01:15 → wait (자정 넘는 구간)',
         'non_trigger: 21:30·어둠 관측 → baseline (어둠 조건 아님)',
         'boundary: 05:00 → baseline (4시 반쯤 일어남, 끝점 해석과 무관)',
         'unobserved: 시각 None(합성) → unknown {baseline, wait}'],
        unsupported_sentences=('N1.s2',))

    # R03: 비가 오면 어느 공원이든 들어가지 않고 돌아섬(공원 60m 범위). 어둠에서의 모습은 미관찰.
    v.persona(
        'R_time_weather_03', 'time_weather',
        ['corpusA:DM-12', 'webB:C36', 'corpusA:DM-24', 'corpusB:C20'],
        [{'label': '둔덕골 공원', 'place_type': 'park'},
         {'label': '새벽시장 골목', 'place_type': 'market'},
         {'label': '옛 정비소', 'place_type': 'workplace'}],
        [(v.DEFAULT_INTRO,
          '둔덕골 공원은 남편이 매일 아침 운동하던 흙길 공원이에요. 새벽시장 골목은 지금도 가끔 같이 가는 데고, '
          '옛 정비소는 퇴직 전까지 일하던 곳이에요.'),
         ('비 오는 날 바깥에 계시면 어떻게 움직이세요?',
          '비가 오면 공원엔 아예 안 들어가요. 둔덕골 말고 딴 공원도 마찬가지고요. '
          '흙길 질척한 걸 질색해서 입구까지 갔다가도 돌아서 나와요. 비 안 오는 날엔 공원을 몇 바퀴씩 돌고요.'),
         ('날씨 때문에 특히 마음 쓰이는 날이 있으세요?',
          '이상하게 비만 오면 나가려고 해서 그런 날이 제일 조마조마해요.'),
         ('해가 진 다음에 밖에 계셨던 적은요?',
          '밤에는 나간 적이 없어요. 아침 먹자마자 나가려고 하죠. 그래서 어두울 때 밖에서 어떤지는 저도 몰라요.')],
        [v.spec('avoid_park', 'rain_observed', ids=('N1',))],
        [v.case('trigger', v.nearby('park', rain_observed=True, clock_hour=15.5), ['avoid_park'],
                '비가 관측되고 공원 20m 앞 → 공원에서 돌아섬.'),
         v.case('non_trigger', v.nearby('park', dark_observed=True, clock_hour=19.0), ['baseline'],
                '공원 앞이지만 비가 없음. 어둠에서의 반응은 관찰된 적 없어 만들지 않음.'),
         v.case('boundary_or_release',
                v.scene(rain_observed=True, clock_hour=10.5,
                        map_distance_m={'market': 1000, 'park': 90, 'forest': 1000, 'water': 1000}),
                ['baseline'], '비는 오지만 공원이 90m 떨어져 회피 범위(60m) 밖.'),
         v.case('unobserved_or_conflict', v.nearby('park', rain_observed=None, clock_hour=16.0), [],
                '공원 앞이지만 비 관측이 없음 → 미확인.',
                status='unknown', possible=['avoid_park', 'baseline'])],
        '비 오는 날엔 어느 공원이든 들어가지 않고 돌아서는 남편(보호자는 아내). '
        '비 오는 날 나가려 한다는 출발 위험(F30)과 아침 출발 습관(F18)은 실종 중 행동이 아니라 표현 불가. '
        '맑은 날 공원을 몇 바퀴씩 도는 경향(N1.s4)은 접근 행동 어휘와 순환 경로 표현이 없어 표현 불가. 밤 모습은 미관찰.',
        ['trigger: 비·공원 20m → avoid_park',
         'non_trigger: 어둠·공원 20m·비 없음 → baseline (미관찰 조건으로 확장 금지)',
         'boundary: 비·공원 90m → baseline (60m 범위 밖)',
         'unobserved: 비 None·공원 20m → unknown {avoid_park, baseline}'],
        unsupported_sentences=('N1.s4', 'N2.s1', 'N3.s2'))

    # R04: 낮엔 거리 한계, 저녁 6시 반~새벽 5시(자정 넘음)엔 짧은 시간 한계로 쉼. 휴식 7분.
    v.persona(
        'R_time_weather_04', 'time_weather',
        ['corpusA:DM-12', 'corpusB:C48'],
        [{'label': '청보리 공원', 'place_type': 'park'},
         {'label': '읍내 보건지소', 'place_type': 'hospital'},
         {'label': '옛 방앗간', 'place_type': 'workplace'}],
        [(v.DEFAULT_INTRO,
          '청보리 공원은 집에서 제일 가까운 공원이고, 읍내 보건지소는 혈압약 타러 가는 곳이에요. '
          '옛 방앗간은 어머니가 아버지랑 같이 하시던 곳인데 지금은 창고로 써요.'),
         ('걷다가 쉬어 가시는 건 어느 정도일 때인가요?',
          '낮에는 동네 한 바퀴가 1.2킬로쯤 되는데, 그걸 한 바퀴 돌고 나면 꼭 앉아서 쉬셔야 해요. '
          '그런데 저녁 6시 반이 넘으면 다리에 힘이 빠지시는지 15분만 걸어도 주저앉으세요.'),
         ('저녁에 그러신 게 밤사이까지 이어지나요?',
          '네, 새벽에 잠이 깨셔서 나가자고 하시면 제가 골목을 같이 걸어 드리는데 그때도 15분쯤 걸으시면 주저앉으세요. '
          '아침 다섯 시를 넘기면 다시 낮처럼 오래 걸으시고요.'),
         ('한 번 앉으시면 얼마나 쉬세요?',
          '한 칠 분쯤 숨 고르시고 다시 일어나세요.'),
         ('밤에 주무시는 건 괜찮으세요?',
          '잠을 깊이 못 주무셔서 밤에 거실을 왔다 갔다 하세요.')],
        [v.spec('rest',
                'is_walking and (distance_since_rest_m >= 1200 or '
                '((clock_hour >= 18.5 or clock_hour < 5) and continuous_walk_minutes >= 15))',
                ids=('N1', 'N2', 'N3'), hold=7)],
        [v.case('trigger',
                v.scene(clock_hour=23.5, dark_observed=True, continuous_walk_minutes=16, distance_since_rest_m=770),
                ['rest'], '밤 11시 반, 쉬지 않고 16분 보행 → 저녁·밤 한계(15분) 도달.'),
         v.case('non_trigger', v.scene(clock_hour=15.0, continuous_walk_minutes=19, distance_since_rest_m=900),
                ['baseline'], '낮 시간, 900m로 낮 한계(1.2km) 미달. 밤 한계는 낮에 적용되지 않음.'),
         v.case('boundary_or_release',
                v.scene(clock_hour=5.25, dark_observed=None, continuous_walk_minutes=16, distance_since_rest_m=770),
                ['baseline'], '새벽 5시 15분은 다섯 시를 넘긴 뒤라 끝점을 어떻게 읽어도 저녁·밤 구간 종료, 거리도 낮 한계 미달.'),
         v.case('unobserved_or_conflict',
                v.scene(clock_hour=None, continuous_walk_minutes=16, distance_since_rest_m=770), [],
                '합성 장면: 16분 보행했지만 시각이 관측되지 않았다고 가정 '
                '(엔진에서는 시각이 늘 계산되어 실제로는 생기지 않음). 저녁·밤 구간인지 몰라 미확인.',
                status='unknown', possible=['baseline', 'rest'])],
        '낮에는 1.2km쯤 걸으면 쉬어야 하고, 저녁 6시 반부터 새벽 5시까지는 15분만 걸어도 주저앉는 어머니. 한 번 앉으면 7분쯤 쉼. '
        '새벽 구간은 보호자가 함께 걸으며 직접 본 모습(발견 시점 일반화 아님). '
        '시간대별 휴식 한계의 직접 근거는 없음: DM-12는 사람마다 시간대 조건이 있다는 데까지, C48은 일주기 이상 일반론이다. '
        '밤 불면(집 안 서성임)은 실내라 비행동.',
        ['trigger: 23:30·16분·770m → rest (자정 넘는 구간의 짧은 한계)',
         'non_trigger: 15:00·19분·900m → baseline (낮 한계 미달)',
         'boundary: 05:15·16분·770m → baseline (구간 종료 뒤, 끝점 해석과 무관)',
         'unobserved: 시각 None(합성)·16분 → unknown {baseline, rest}'])

    # R05: 어둠 AND 비가 함께일 때만 그 자리에 멈춰 섬. 어둠 단독·비 단독은 걸음.
    v.persona(
        'R_time_weather_05', 'time_weather',
        ['webB:C36', 'corpusA:DM-12'],
        [{'label': '갈대숲 공원', 'place_type': 'park'},
         {'label': '역전 시장', 'place_type': 'market'},
         {'label': '옛 시청 정류장', 'place_type': 'station'}],
        [(v.DEFAULT_INTRO,
          '역전 시장은 아버지가 예전에 철물점을 하시던 곳이고, 갈대숲 공원은 남편이 모시고 산책 가던 데예요. '
          '옛 시청 정류장은 병원 갈 때 버스 타는 곳이에요.'),
         ('비 오는 날 밖에서 찾으신 적이 있나요?',
          '두 번 있어요. 한 번은 낮에 비 올 때였는데, 동네 경비 아저씨 말로는 우산도 없이 그냥 맞으면서 계속 걸으셨대요. '
          '다른 한 번은 작년 가을에 해 지고 캄캄한 데다 비까지 왔는데, '
          '제가 찾아갔을 때 길 한가운데 딱 멈춰 서서 한 발짝도 안 움직이셨어요.'),
         ('어둡기만 하고 비는 안 올 때는 어떠셨어요?',
          '어둡기만 할 때는 평소처럼 걸어 다니셨어요. '
          '낮에 비 맞으실 때도 걸으셨으니까, 그날은 캄캄한 데 비까지 겹쳐서 그러셨던 것 같아요.'),
         ('저녁 시간에 따로 신경 쓰시는 게 있나요?',
          '저녁엔 제가 퇴근해서 같이 있으니까 아버지가 밖에 혼자 계실 일은 거의 없어요.')],
        [v.spec('wait', 'dark_observed and rain_observed', ids=('N1', 'N2'))],
        [v.case('trigger', v.scene(dark_observed=True, rain_observed=True, clock_hour=19.4), ['wait'],
                '어둠과 비가 함께 관측됨 → 그 자리에 멈춰 섬.'),
         v.case('non_trigger', v.scene(rain_observed=True, clock_hour=13.0), ['baseline'],
                '낮에 비만 옴 → 맞으면서 계속 걸음(기본 이동).'),
         v.case('boundary_or_release', v.scene(dark_observed=True, rain_observed=False, clock_hour=21.5),
                ['baseline'], '어둠 단독(비 없음, N2.s1) → 두 조건 중 하나만 성립해 멈추지 않음.'),
         v.case('unobserved_or_conflict', v.scene(dark_observed=True, rain_observed=None, clock_hour=20.5), [],
                '캄캄한 건 관측됐지만 비가 오는지 관측이 없음 → 두 조건이 겹쳤는지 몰라 미확인.',
                status='unknown', possible=['baseline', 'wait'])],
        '어둡고 비까지 올 때만 길 위에 멈춰 서는 아버지. 비 단독·어둠 단독일 때는 걸었다고 보호자가 구분함. '
        '낮 비 장면은 경비원에게 전해 들은 것. 저녁엔 보호자가 함께 있다는 말은 보호자 일정이라 비행동. '
        'N1.s2의 우산 없이 비를 맞으며 걸었다는 부분은 위험 무인식(엔진 소비처 없음)으로 볼 여지가 있어 '
        'unsupported로 넣을지 사람 검토 필요.',
        ['trigger: 어둠+비 → wait',
         'non_trigger: 낮 비 단독 → baseline',
         'release: 어둠 단독(비 없음) → baseline',
         'unobserved: 어둠 관측·비 None → unknown {baseline, wait}'])

    # R06: 밤 9시 반~새벽 6시(자정 넘음)에 옛 공장으로 향함. 가족이 곁에 있으면 따라옴(해제).
    v.persona(
        'R_time_weather_06', 'time_weather',
        ['corpusA:DM-12'],
        [{'label': '가람 근린공원', 'place_type': 'park'},
         {'label': '옛 제지공장 정문', 'place_type': 'workplace'},
         {'label': '장미 연립', 'place_type': 'past_home'}],
        [(v.DEFAULT_INTRO,
          '가람 근린공원은 지금 집 바로 옆이에요. 제지공장은 아버지가 서른 해 가까이 야간조로 다니신 곳인데 '
          '지금은 문을 닫았고, 장미 연립은 그 시절에 살던 집이에요.'),
         ('밤에 없어지셨을 때는 주로 어디서 찾으셨나요?',
          '두 번 다 옛 제지공장 정문 가는 길에서 찾았어요. '
          '밤 9시 반 넘어서 밖에 계시면 출근해야 한다면서 꼭 그쪽으로 걸어가세요. '
          '새벽 6시, 교대 끝나는 시간이 지나면 공장 얘기도 안 하시고 그쪽으로 가지도 않으세요.'),
         ('누가 옆에 같이 있을 때는 어떠세요?',
          '제가 같이 나가 있으면 공장 가야 한다고 하시면서도 제 팔 잡고 집 쪽으로 따라오세요.'),
         ('하루 중에 기분이 달라지는 때가 있나요?',
          '오후에는 대체로 기분이 가라앉아 계세요. 말수도 줄고요.')],
        [v.spec('seek_1', '(clock_hour >= 21.5 or clock_hour < 6) and not family_present', ids=('N1', 'N2'))],
        [v.case('trigger', v.scene(clock_hour=0.5, dark_observed=True), ['seek_1'],
                '자정 넘은 0시 30분, 혼자 있음 → 옛 공장 쪽으로 향함.'),
         v.case('non_trigger', v.scene(clock_hour=6.5, dark_observed=None), ['baseline'],
                '교대 끝나는 새벽 6시가 지난 6시 30분, 혼자 있음 → 공장 쪽으로 가지 않음.'),
         v.case('boundary_or_release', v.scene(clock_hour=23.0, dark_observed=True, family_present=True), ['baseline'],
                '구간 안이지만 가족이 곁에 있음 → 공장 쪽으로 가지 않고 따라옴.'),
         v.case('unobserved_or_conflict', v.scene(clock_hour=2.5, dark_observed=True, family_present=None), [],
                '새벽 2시 반이지만 동행 여부가 확인되지 않음 → 미확인.',
                status='unknown', possible=['baseline', 'seek_1'])],
        '야간조로 오래 일한 아버지. 밤 9시 반부터 새벽 6시(교대 종료)까지 혼자 밖에 있으면 옛 공장 정문으로 향하고, '
        '가족이 곁에 있으면 따라옴. 옛 직장으로 향하는 행동과 시간 구간의 직접 근거는 없음: DM-12는 사람마다 '
        '시간대 조건이 있다는 데까지다. 원문에 보호자가 잠든 사이라는 맥락이 없어 수면 중 외출 근거(C04·C08)는 넣지 않음. '
        '오후 기분 저하는 정서 보고라 비행동.',
        ['trigger: 00:30·혼자 → seek_1 (자정 넘는 구간)',
         'non_trigger: 06:30·혼자 → baseline (교대 종료 뒤)',
         'release: 23:00·가족 동행 → baseline',
         'unobserved: 02:30·가족 None → unknown {baseline, seek_1}'])

    # R07: 저녁이 아니라 오후 1시~4시 반에 지쳐도 앉지 않고 계속 걸음(해질녘 통념의 반례). 동행이 권해도 안 앉음.
    v.persona(
        'R_time_weather_07', 'time_weather',
        ['webB:C27', 'corpusB:C48', 'webB:C26'],
        [{'label': '은행나무 공원', 'place_type': 'park'},
         {'label': '중앙 재래시장', 'place_type': 'market'},
         {'label': '단골 내과', 'place_type': 'hospital'}],
        [(v.DEFAULT_INTRO,
          '은행나무 공원은 아파트 단지 안에 있는 공원이에요. 중앙 재래시장은 엄마가 혼자 다니실 수 있던 마지막 장소였고, '
          '단골 내과는 매달 약 타러 가는 곳이에요.'),
         ('하루 중 언제가 제일 힘드신 것 같으세요?',
          '흔히 저녁에 심해진다고들 하던데 저희 엄마는 반대예요. '
          '점심 드시고 1시쯤부터 4시 반까지가 제일 안절부절하세요.'),
         ('그 시간에 바깥에 계시면 어떻게 하세요?',
          '그 시간에 밖에 계시면 지쳐서 다리를 끄시면서도 절대 안 앉으세요. '
          '벤치에 앉으시라고 해도 손을 뿌리치고 계속 걸으세요.'),
         ('해 지고 나서는 어떠세요?',
          '저녁 드시고 나면 오히려 차분해지셔서 텔레비전 보시다가 일찍 주무세요.')],
        [v.spec('walk', 'clock_hour >= 13 and clock_hour < 16.5 and fatigue_high', ids=('N1', 'N2'))],
        [v.case('trigger', v.scene(clock_hour=13.75, fatigue_high=True), ['walk'],
                '오후 1시 45분, 지쳐 있음 → 앉지 않고 계속 걸음.'),
         v.case('non_trigger', v.scene(clock_hour=18.5, fatigue_high=True, dark_observed=True), ['baseline'],
                '저녁·어둠·피로가 겹쳐도 이 사람은 저녁에 차분함 → 개인 반응 없음.'),
         v.case('boundary_or_release', v.scene(clock_hour=16.75, fatigue_high=True), ['baseline'],
                '오후 4시 45분은 4시 반을 넘긴 뒤라 끝점을 어떻게 읽어도 구간 종료.'),
         v.case('unobserved_or_conflict', v.scene(clock_hour=15.25, fatigue_high=True, family_present=True), ['walk'],
                '충돌 장면: 곁에서 앉으라고 권해도 손을 뿌리치고 걸음(N2.s2) → 동행을 해제 조건으로 만들지 않음.')],
        '해질녘이 아니라 이른 오후(1시~4시 반)에 안절부절하고, 그때 밖에서는 지쳐도, 곁에서 앉으라고 해도 앉지 않는 어머니. '
        '저녁에는 집에서 차분함. 집단 일몰증후군을 개인에게 덧씌우지 않는 반례.',
        ['trigger: 13:45·피로 → walk',
         'non_trigger: 18:30·피로·어둠 → baseline (저녁 통념 적용 금지)',
         'boundary: 16:45·피로 → baseline (구간 종료 뒤, 끝점 해석과 무관)',
         'conflict: 15:15·피로·동행 있음 → walk (동행이 해제 조건 아님)'])

    # R08: 깜깜하거나(OR) 비가 오면 물가를 피함(100m 범위). 맑은 날 물가 선호는 표현 불가.
    v.persona(
        'R_time_weather_08', 'time_weather',
        ['webB:C36', 'corpusA:DM-12'],
        [{'label': '버들개 공원', 'place_type': 'park'},
         {'label': '옛 양조장 사택', 'place_type': 'past_home'},
         {'label': '동네 체육관', 'place_type': 'community_center'}],
        [(v.DEFAULT_INTRO,
          '버들개 공원은 냇가 옆에 붙은 공원이고, 옛 양조장 사택은 어머님이 젊을 때 사시던 동네예요. '
          '동네 체육관은 노래교실 다니시던 데고요.'),
         ('물가 근처를 지나실 때는 어떠세요?',
          '바깥이 깜깜할 때는 냇가 쪽으로 절대 안 내려가세요. 비 오는 날도 마찬가지고요. '
          '다리 위에서 물을 한 번 내려다보시고는 바로 돌아서세요.'),
         ('날이 맑고 환할 때는요?',
          '해 있고 맑은 날엔 냇가 둑길을 따라 한참 걸으세요. 거기 바람이 제일 좋다고 하세요.')],
        [v.spec('avoid_water', 'dark_observed or rain_observed', ids=('N1',))],
        [v.case('trigger', v.nearby('water', dark_observed=True, clock_hour=18.0), ['avoid_water'],
                '어둠 관측·물가 20m → 물가에서 돌아섬(비는 없어도 하나로 충분).'),
         v.case('non_trigger', v.nearby('water', clock_hour=16.0), ['baseline'],
                '맑고 환한 오후·물가 20m → 피할 이유 없음. 둑길을 따라 걷는 경향은 표현 불가라 기본 이동.'),
         v.case('boundary_or_release',
                v.scene(rain_observed=True, clock_hour=11.0,
                        map_distance_m={'market': 1000, 'park': 1000, 'forest': 1000, 'water': 140}),
                ['baseline'], '비는 오지만 물가가 140m 떨어져 회피 범위(100m) 밖.'),
         v.case('unobserved_or_conflict',
                v.scene(rain_observed=True, clock_hour=14.0,
                        map_distance_m={'market': 1000, 'park': 1000, 'forest': 1000, 'water': None}), [],
                '비는 오지만 지도에 물가 거리가 없어 회피 범위인지 모름 → 미확인.',
                status='unknown', possible=['avoid_water', 'baseline'])],
        '깜깜할 때나 비 오는 날엔 냇가로 내려가지 않고 돌아서는 시어머니(보호자는 며느리). '
        '맑은 날 둑길을 따라 걷는 접근 경향은 접근 행동 어휘가 없어 표현 불가.',
        ['trigger: 어둠만·물가 20m → avoid_water (OR 결합)',
         'non_trigger: 16:00·맑음·물가 20m → baseline',
         'boundary: 비·물가 140m → baseline (100m 범위 밖)',
         'unobserved: 비·물가 거리 None → unknown {avoid_water, baseline}'],
        unsupported_sentences=('N2.s1',))

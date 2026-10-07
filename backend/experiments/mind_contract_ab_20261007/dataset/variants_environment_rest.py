"""Derived drafts for roots P01-P08 (environment, physical_rest).

AI-authored synthetic guardian Q&A (draft_unreviewed). Reference rules are
handwritten and only checked for internal coherence with the authored scenes;
they are not clinical ground truth. No model was called to write this file.
"""


def register(v):
    I, case, scene, nearby, spec = v.INTRO, v.case, v.scene, v.nearby, v.spec

    # ------------------------------------------------------------------ P01
    # Root: 해든상가에서 소음 AND 혼잡일 때만 회피. 다른 상가는 미관찰.
    v.variant(
        'P01', 'preserve', 'colloquial_reorder', 'preserve',
        [I, ('해든상가 앞에서 발길을 돌리신 적이 있나요?',
             '다른 상가는 같이 가 본 적이 없어서 모르겠고요. 해든상가는 두 번 같이 갔는데, '
             '북적이는 데다 시끄럽기까지 하면 입구에서 돌아서시더라고요. 둘 중 하나만 그럴 땐 안 돌아서셨어요.')],
        [spec('avoid_market', 'market.noisy and market.crowded', labels=('해든상가',))],
        [case('trigger', nearby('market', noisy=True, crowded=True, current_place_label='해든상가'),
              ['avoid_market'], '해든상가에서 소음과 혼잡 동시'),
         case('non_trigger', nearby('market', crowded=True, current_place_label='해든상가'),
              ['baseline'], '혼잡만'),
         case('boundary_or_release', nearby('market', noisy=True, crowded=True, current_place_label='다른 상가'),
              ['baseline'], '이름 범위 밖 상가'),
         case('unobserved_or_conflict',
              nearby('market', noisy=None, crowded=True, current_place_label='해든상가'),
              [], '소음 미관측', status='unknown', possible=['baseline', 'avoid_market'])],
        '문장 순서와 구어체만 바꿈. 해든상가 한정·소음 AND 혼잡 유지.',
        ['해든상가 두 자극 동시 회피', '한 자극만이면 회피 없음', '다른 상가로 일반화 금지', '소음 미관측은 거짓으로 처리 금지'])

    v.variant(
        'P01', 'counterfactual', 'named_to_category', 'change',
        [I, ('상가에서는 어떻게 행동하셨어요?',
             '해든상가 말고도 상가 몇 군데를 같이 다녀봤는데 어디서든 똑같았어요. 사람도 많고 소리도 클 때에만 '
             '입구에서 돌아섰고, 한 가지뿐일 때는 돌아서지 않았어요.')],
        [spec('avoid_market', 'market.noisy and market.crowded')],
        [case('trigger', nearby('market', noisy=True, crowded=True, current_place_label='다른 상가'),
              ['avoid_market'], '등록 이름이 아닌 상가에서도 회피'),
         case('non_trigger', nearby('market', noisy=True), ['baseline'], '소음만'),
         case('boundary_or_release', scene(noisy=True, crowded=True), ['baseline'], '상가가 근처에 없음'),
         case('unobserved_or_conflict', nearby('market', noisy=True, crowded=None),
              [], '혼잡 미관측', status='unknown', possible=['baseline', 'avoid_market'])],
        '적용 범위만 해든상가 한정에서 상가 유형 전체로 변경. AND는 유지.',
        ['다른 상가에서도 두 자극 동시 회피', '한 자극만이면 회피 없음', '상가에서 멀면 회피 없음', '혼잡 미관측은 unknown'])

    v.variant(
        'P01', 'hard', 'multi_turn_correction_third_party', 'preserve',
        [I, ('해든상가에서는 어떻게 하셨어요?', '시끄러우면 돌아서셨어요.'),
         ('소리만 커도 돌아서셨던 건가요?',
          '아, 다시 생각해 보니 제가 같이 간 두 번은 사람도 꽉 차 있었어요. 조용한데 붐비기만 하거나 '
          '한산한데 시끄럽기만 할 때는 안 돌아서셨어요. 그러니까 둘 다일 때만이에요.'),
         ('다른 상가 얘기도 들으셨나요?',
          '옆집 할머니는 다른 상가에서 시끄럽기만 해도 돌아가신다던데, 그건 그분 얘기예요. '
          '어머니가 다른 상가에서 어떠신지는 못 봤어요.')],
        [spec('avoid_market', 'market.noisy and market.crowded', ids=('N1', 'N2'), labels=('해든상가',))],
        [case('trigger', nearby('market', noisy=True, crowded=True, current_place_label='해든상가'),
              ['avoid_market'], '정정 후 두 자극 동시'),
         case('non_trigger', nearby('market', noisy=True, current_place_label='해든상가'),
              ['baseline'], '첫 답의 소음 단독은 정정됨'),
         case('boundary_or_release', nearby('market', noisy=True, current_place_label='다른 상가'),
              ['baseline'], '옆집 할머니의 소음 반응을 가져오지 않음'),
         case('unobserved_or_conflict',
              nearby('market', noisy=True, crowded=None, current_place_label='해든상가'),
              [], '혼잡 미관측', status='unknown', possible=['baseline', 'avoid_market'])],
        '첫 답(소음만)을 둘째 답에서 AND로 정정. 타인 사례 혼입. 최종 의미는 원형과 같음.',
        ['정정 후 소음 단독 비발동', '타인의 다른 상가 반응 제외', '해든상가 한정 유지', '혼잡 미관측은 unknown'])

    # ------------------------------------------------------------------ P02
    # Root: 상가 유형 전체에서 소음 OR 혼잡이면 회피.
    v.variant(
        'P02', 'preserve', 'colloquial_reorder', 'preserve',
        [I, ('상가 여러 곳에서 반응이 비슷했나요?',
             '세 곳 정도 같이 가 봤는데요, 사람만 북적여도 발길을 돌리셨고 사람이 없어도 시끄러우면 또 돌리셨어요. '
             '조용하고 한산할 때는 괜찮으셨어요.')],
        [spec('avoid_market', 'market.noisy or market.crowded')],
        [case('trigger', nearby('market', crowded=True), ['avoid_market'], '혼잡만으로 회피'),
         case('non_trigger', nearby('market'), ['baseline'], '두 자극 없음'),
         case('boundary_or_release', nearby('market', noisy=True), ['avoid_market'], '소음만으로 회피'),
         case('unobserved_or_conflict', nearby('market', noisy=None),
              [], '소음 미관측', status='unknown', possible=['baseline', 'avoid_market'])],
        '표현만 바꿈. 상가 유형 전체·소음 OR 혼잡 유지. 원형의 준비 정보 대신 같은 의미의 참조 규칙으로 기록.',
        ['혼잡 단독 회피', '소음 단독 회피', '두 자극 없으면 회피 없음', '소음 미관측은 unknown'])

    v.variant(
        'P02', 'counterfactual', 'observed_to_stated_wish', 'change',
        [I, ('서로 다른 상가에서도 같은 반응이었나요?',
             '상가는 시끄럽거나 사람 많으면 싫다고 늘 말씀은 하세요. 그런데 실제로 입구에서 돌아서시는 건 '
             '세 군데 다 다녀봐도 제가 본 적이 없어요.')],
        [],
        [case('trigger', nearby('market', noisy=True), ['baseline'], '싫다는 말만으로 회피 만들지 않음'),
         case('non_trigger', nearby('market'), ['baseline'], '자극 없음'),
         case('boundary_or_release', nearby('market', noisy=True, crowded=True), ['baseline'], '두 자극이어도 관찰 없음'),
         case('unobserved_or_conflict', nearby('market', crowded=None), ['baseline'], '개인 반응 근거 없음')],
        '실제 회피 관찰을 싫다는 발언과 미관찰로 변경. 규칙 없음.',
        ['발언을 회피로 바꾸지 않음', '소음·혼잡 모두여도 회피 없음', '미관측이어도 unknown 아님'])

    v.variant(
        'P02', 'hard', 'multi_turn_accumulate_third_party', 'preserve',
        [I, ('상가에서는 어떠셨어요?', '사람 많으면 돌아서셨어요.'),
         ('시끄러운 건요?',
          '그것도요. 사람이 별로 없어도 소리가 크면 돌아서셨어요. 해든상가 말고 다른 상가 두 군데에서도 똑같았어요.'),
         ('둘 다 없을 때는요?',
          '그땐 안 피하셨어요. 아, 아버지는 시끄러운 데를 오히려 구경하러 들어가시는데 그건 아버지 얘기고요.')],
        [spec('avoid_market', 'market.noisy or market.crowded', ids=('N1', 'N2'))],
        [case('trigger', nearby('market', noisy=True), ['avoid_market'], '둘째 답의 소음 단독'),
         case('non_trigger', nearby('market'), ['baseline'], '두 자극 없음'),
         case('boundary_or_release', nearby('market', crowded=True, current_place_label='다른 상가'),
              ['avoid_market'], '해든상가 이름에 한정하지 않음'),
         case('unobserved_or_conflict', nearby('market', crowded=None),
              [], '혼잡 미관측', status='unknown', possible=['baseline', 'avoid_market'])],
        '두 자극을 여러 문답에 나눠 OR로 누적. 아버지의 반대 행동 혼입. 최종 의미는 원형과 같음.',
        ['문답을 합쳐 OR로 읽음', '다른 상가에도 적용', '아버지 행동 제외', '혼잡 미관측은 unknown'])

    # ------------------------------------------------------------------ P03
    # Root: 공원 유형에서 어둠 AND 혼잡이면 회피.
    v.variant(
        'P03', 'preserve', 'colloquial_reorder', 'preserve',
        [I, ('공원에서 피하셨던 때가 언제였어요?',
             '공원 몇 군데서 봤는데요, 해 지고 깜깜한데 사람까지 몰려 있으면 공원 쪽을 피해서 가셨어요. '
             '밝을 때 북적이는 건 괜찮았고, 깜깜해도 사람이 없으면 안 피하셨어요.')],
        [spec('avoid_park', 'dark_observed and park.crowded')],
        [case('trigger', nearby('park', dark_observed=True, crowded=True, clock_hour=20),
              ['avoid_park'], '어둠과 혼잡'),
         case('non_trigger', nearby('park', crowded=True, clock_hour=14), ['baseline'], '밝을 때 혼잡'),
         case('boundary_or_release', nearby('park', dark_observed=True, clock_hour=20), ['baseline'], '어둡지만 한산'),
         case('unobserved_or_conflict', nearby('park', dark_observed=None, crowded=True, clock_hour=21),
              [], '밤 시각으로 어둠 추정 금지', status='unknown', possible=['baseline', 'avoid_park'])],
        '표현만 바꿈. 공원 유형 전체·어둠 AND 혼잡 유지.',
        ['어둠과 혼잡 동시 회피', '혼잡만이면 회피 없음', '어둠만이면 회피 없음', '시각으로 어둠을 만들지 않음'])

    v.variant(
        'P03', 'counterfactual', 'and_to_or', 'change',
        [I, ('공원에서 피한 상황을 알려주세요.',
             '여러 공원에서 직접 봤는데, 어둡거나 사람이 붐비거나 둘 중 하나만 있어도 공원 쪽에서 멀어졌어요. '
             '밝고 한산할 때는 피하지 않았어요.')],
        [spec('avoid_park', 'dark_observed or park.crowded')],
        [case('trigger', nearby('park', crowded=True, clock_hour=14), ['avoid_park'], '혼잡만으로 회피'),
         case('non_trigger', nearby('park'), ['baseline'], '밝고 한산'),
         case('boundary_or_release', scene(dark_observed=True), ['baseline'], '어둡지만 공원에서 멂'),
         case('unobserved_or_conflict', nearby('park', dark_observed=None),
              [], '어둠 미관측', status='unknown', possible=['baseline', 'avoid_park'])],
        '어둠 AND 혼잡을 OR로 변경. 공원 유형 범위는 유지.',
        ['혼잡 단독 회피', '두 자극 없으면 회피 없음', '공원 밖에서는 어둠만으로 회피 없음', '어둠 미관측은 unknown'])

    v.variant(
        'P03', 'hard', 'clock_vs_dark_clarification', 'preserve',
        [I, ('공원에서 피하신 적 있어요?', '저녁에 공원 가면 사람 많을 때 피하셨어요.'),
         ('저녁이라는 게 시간 때문인가요, 어두워서인가요?',
          '시간은 상관없었던 것 같아요. 흐린 날 낮에도 나무 밑이 깜깜하다고 하시면서 사람 많은 쪽을 피하셨거든요. '
          '저녁이라도 불이 환하면 사람이 많아도 안 피하셨고요.'),
         ('사람이 없을 때는요?', '깜깜해도 한산하면 안 피하셨어요.')],
        [spec('avoid_park', 'dark_observed and park.crowded', ids=('N1', 'N2', 'N3'))],
        [case('trigger', nearby('park', dark_observed=True, crowded=True, clock_hour=13),
              ['avoid_park'], '낮의 어둠과 혼잡'),
         case('non_trigger', nearby('park', dark_observed=False, crowded=True, clock_hour=20),
              ['baseline'], '밝은 저녁의 혼잡'),
         case('boundary_or_release', nearby('park', dark_observed=True, crowded=False, clock_hour=13),
              ['baseline'], '어둡지만 한산'),
         case('unobserved_or_conflict', nearby('park', dark_observed=None, crowded=True, clock_hour=20),
              [], '저녁 시각만으로 어둠 단정 금지', status='unknown', possible=['baseline', 'avoid_park'])],
        '첫 답의 저녁을 둘째 답에서 시각이 아닌 어둠 관찰로 해명. 최종 의미는 원형과 같음.',
        ['낮이어도 어둠과 혼잡이면 회피', '밝은 저녁 혼잡은 회피 없음', '어둡지만 한산하면 회피 없음', '시각으로 어둠을 만들지 않음'])

    # ------------------------------------------------------------------ P04
    # Root: 물가 회피는 옆집 어르신 이야기. 본인은 미관찰. 규칙 없음.
    v.variant(
        'P04', 'preserve', 'third_party_reorder', 'preserve',
        [I, ('물가에서는 어떻게 하세요?',
             '시끄러운 하천변에서 되돌아갔다는 건 옆집 어르신 얘기예요. 저희 아버지는 물가에서 어떻게 하시는지 '
             '아직 못 봤어요. 그러니 아버지 기록에는 넣지 말아 주세요.')],
        [],
        [case('trigger', nearby('water', noisy=True), ['baseline'], '타인의 소음 반응'),
         case('non_trigger', nearby('water', crowded=True), ['baseline'], '본인 관찰 없음'),
         case('boundary_or_release', nearby('water', noisy=True, crowded=True, clock_hour=18),
              ['baseline'], '자극을 더해도 근거 아님'),
         case('unobserved_or_conflict', nearby('water', noisy=None), ['baseline'], '규칙이 없어 unknown 아님')],
        '문장 순서만 바꿈. 타인 행동·본인 미관찰 유지.',
        ['옆집 어르신 반응을 아버지에게 옮기지 않음', '물가 자극이 있어도 회피 없음'])

    v.variant(
        'P04', 'counterfactual', 'third_party_to_patient', 'change',
        [I, ('물가 반응을 직접 보셨나요?',
             '시끄러운 하천변에서 되돌아가신 건 저희 아버지예요. 세 번 같이 걸었는데 그때마다 그러셨어요. '
             '조용할 때는 되돌아가지 않으셨고요.')],
        [spec('avoid_water', 'water.noisy')],
        [case('trigger', nearby('water', noisy=True), ['avoid_water'], '본인 소음 회피'),
         case('non_trigger', nearby('water', crowded=True), ['baseline'], '혼잡만'),
         case('boundary_or_release',
              scene(map_distance_m={'market': 1000, 'park': 1000, 'forest': 1000, 'water': 120}, noisy=True),
              ['baseline'], '물가가 근처 범위 밖'),
         case('unobserved_or_conflict', nearby('water', noisy=None),
              [], '소음 미관측', status='unknown', possible=['baseline', 'avoid_water'])],
        '행동 주체를 옆집 어르신에서 아버지 본인으로 변경. 물가 소음 회피 규칙 생성.',
        ['본인 소음 회피', '혼잡만이면 회피 없음', '물가에서 멀면 회피 없음', '소음 미관측은 unknown'])

    v.variant(
        'P04', 'hard', 'pronoun_third_party_correction', 'preserve',
        [I, ('물가에서는 어떠세요?', '시끄러운 하천변에서는 되돌아가시더라고요.'),
         ('아버님 말씀이신가요?',
          '아니요, 그분은 옆집 어르신이에요. 산책을 같이 다니셔서 제가 헷갈렸네요. '
          '아버지가 물가에서 어떻게 하시는지는 아직 못 봤어요.'),
         ('아버님은 사람 많은 물가에서는요?', '그것도 본 적 없어요.')],
        [],
        [case('trigger', nearby('water', noisy=True), ['baseline'], '첫 답 주어는 옆집 어르신'),
         case('non_trigger', nearby('water', crowded=True), ['baseline'], '혼잡 미관찰'),
         case('boundary_or_release', nearby('water', noisy=True, crowded=True, dark_observed=True),
              ['baseline'], '조건을 더해도 근거 아님'),
         case('unobserved_or_conflict', nearby('water', noisy=None), ['baseline'], '규칙이 없어 unknown 아님')],
        '첫 답의 생략된 주어를 둘째 답에서 옆집 어르신으로 정정. 최종 의미는 원형과 같음(규칙 없음).',
        ['생략된 주어를 본인으로 단정하지 않음', '정정 후 타인 반응 제외', '미관찰을 회피로 만들지 않음'])

    # ------------------------------------------------------------------ P05
    # Root: 보행 중 8분 OR 450m에서 휴식 필요.
    v.variant(
        'P05', 'preserve', 'digits_reorder', 'preserve',
        [I, ('걸으시다가 쉬셔야 할 때가 있나요?',
             '무릎이 안 좋으셔서요, 450미터쯤 가시거나 8분 정도 쭉 걸으시면 앉아서 쉬셔야 해요. '
             '어느 쪽이든 먼저 닿는 데서 쉬시고, 두 개가 다 차길 기다리진 않아요.')],
        [spec('rest', 'is_walking and (continuous_walk_minutes >= 8 or distance_since_rest_m >= 450)')],
        [case('trigger', scene(continuous_walk_minutes=8, distance_since_rest_m=100), ['rest'], '8분 도달'),
         case('non_trigger', scene(continuous_walk_minutes=7.9, distance_since_rest_m=449), ['baseline'], '두 한계 직전'),
         case('boundary_or_release', scene(continuous_walk_minutes=3, distance_since_rest_m=450), ['rest'], '450미터 도달'),
         case('unobserved_or_conflict', scene(continuous_walk_minutes=5, distance_since_rest_m=None),
              [], '거리 미측정', status='unknown', possible=['baseline', 'rest'])],
        '한글 수를 숫자로, 거리·시간 순서를 바꿈. 보행 중 OR 휴식 필요 유지.',
        ['7.9분·449미터 비발동', '8분 단독 휴식', '450미터 단독 휴식', '거리 미측정은 unknown'])

    v.variant(
        'P05', 'counterfactual', 'or_to_and', 'change',
        [I, ('보행 후 쉬어야 하나요?',
             '연속 팔 분을 걸었고 거리도 사백오십 미터를 넘긴 때에는 무릎 때문에 앉아 쉬어야 했어요. '
             '시간만 지났거나 거리만 넘었을 때 어떠신지는 아직 못 봤어요.')],
        [spec('rest', 'is_walking and continuous_walk_minutes >= 8 and distance_since_rest_m >= 450')],
        [case('trigger', scene(continuous_walk_minutes=8, distance_since_rest_m=450), ['rest'], '두 한계 모두'),
         case('non_trigger', scene(continuous_walk_minutes=10, distance_since_rest_m=300), ['baseline'], '시간만'),
         case('boundary_or_release', scene(continuous_walk_minutes=7.9, distance_since_rest_m=600),
              ['baseline'], '거리만, 시간 직전'),
         case('unobserved_or_conflict', scene(continuous_walk_minutes=9, distance_since_rest_m=None),
              [], '거리 미측정', status='unknown', possible=['baseline', 'rest'])],
        'OR을 AND로 변경. 한 한계만 넘은 경우는 미관찰.',
        ['두 한계 모두일 때만 휴식', '시간만이면 개인 휴식 없음', '거리만이면 개인 휴식 없음', '거리 미측정은 unknown'])

    v.variant(
        'P05', 'hard', 'threshold_correction', 'preserve',
        [I, ('얼마나 걸으시면 쉬셔야 해요?', '한 십 분쯤이요.'),
         ('십 분을 꽉 채워야 하나요?',
          '아니에요, 다시 재 보니까 팔 분이면 벌써 무릎을 짚으세요. 거리로는 사백오십 미터쯤 가면 그렇고요. '
          '시간이든 거리든 먼저 닿는 쪽에서 앉으셔야 해요.'),
         ('앉아 계실 때는요?', '앉아 계시는 동안은 그걸로 된 거고, 다시 일어나 걸으실 때부터 또 세요.')],
        [spec('rest', 'is_walking and (continuous_walk_minutes >= 8 or distance_since_rest_m >= 450)', ids=('N2',))],
        [case('trigger', scene(continuous_walk_minutes=9, distance_since_rest_m=100), ['rest'], '정정된 8분 이후, 옛 10분 이전'),
         case('non_trigger', scene(continuous_walk_minutes=7.9, distance_since_rest_m=300), ['baseline'], '8분 직전'),
         case('boundary_or_release', scene(current_action='rest', continuous_walk_minutes=12, distance_since_rest_m=600),
              ['baseline'], '이미 앉아 쉬는 중'),
         case('unobserved_or_conflict', scene(continuous_walk_minutes=None, distance_since_rest_m=200),
              [], '보행 시간 미측정', status='unknown', possible=['baseline', 'rest'])],
        '첫 답 10분을 둘째 답에서 8분 OR 450미터로 정정. 최종 의미는 원형과 같음.',
        ['9분은 정정값 기준 휴식', '7.9분 비발동', '휴식 중 재발동 없음', '시간 미측정은 unknown'])

    # ------------------------------------------------------------------ P06
    # Root: 25분 보행 능력만. 휴식 시점 미관찰. 규칙 없음.
    v.variant(
        'P06', 'preserve', 'colloquial_capacity', 'preserve',
        [I, ('한 번에 얼마나 걸으실 수 있어요?',
             '스물다섯 분은 안 쉬고 걸으세요. 근데 스물다섯 분이 되면 꼭 쉬신다는 얘기는 아니에요. '
             '언제 쉬시는지는 제가 못 봤어요.')],
        [],
        [case('trigger', scene(continuous_walk_minutes=25), ['baseline'], '능력 경계를 휴식으로 바꾸지 않음'),
         case('non_trigger', scene(continuous_walk_minutes=10), ['baseline'], '능력 이내'),
         case('boundary_or_release', scene(continuous_walk_minutes=26, distance_since_rest_m=1800),
              ['baseline'], '능력 초과도 휴식 근거 아님'),
         case('unobserved_or_conflict', scene(current_action='rest', fatigue_high=True), ['baseline'], '휴식 관찰 없음')],
        '구어체로만 바꿈. 걷는 능력만 있고 휴식 필요 근거 없음 유지.',
        ['능력을 휴식 명령으로 바꾸지 않음', '피로가 있어도 개인 규칙 없음'])

    v.variant(
        'P06', 'counterfactual', 'capacity_to_need', 'change',
        [I, ('어느 정도 보행이 가능한가요?',
             '쉬지 않고 이십오 분을 걸으시면 다리가 저려서 꼭 앉아 쉬셔야 해요. 제가 같이 걸을 때 매번 그랬어요.')],
        [spec('rest', 'is_walking and continuous_walk_minutes >= 25')],
        [case('trigger', scene(continuous_walk_minutes=25), ['rest'], '25분 도달'),
         case('non_trigger', scene(continuous_walk_minutes=24.9), ['baseline'], '25분 직전'),
         case('boundary_or_release', scene(current_action='rest', continuous_walk_minutes=30), ['baseline'], '이미 쉬는 중'),
         case('unobserved_or_conflict', scene(continuous_walk_minutes=None),
              [], '보행 시간 미측정', status='unknown', possible=['baseline', 'rest'])],
        '걸을 수 있는 능력을 25분 후 반드시 쉬어야 하는 필요로 변경.',
        ['25분 휴식', '24.9분 비발동', '휴식 중 재발동 없음', '시간 미측정은 unknown'])

    v.variant(
        'P06', 'hard', 'third_party_need_mixed', 'preserve',
        [I, ('한 번에 얼마나 걸으세요?', '이십오 분은 거뜬하세요.'),
         ('그 정도 걸으면 쉬셔야 하나요?',
          '꼭 쉬셔야 하는 건 저희 이모님이에요. 이모님은 십오 분만 걸어도 앉으셔야 하는데, '
          '어머니는 언제 쉬시는지 제가 확인을 못 했어요.'),
         ('어머니가 힘들다고 하신 적은요?', '가끔 하시는데, 그때 앉으셨는지는 기억이 안 나요.')],
        [],
        [case('trigger', scene(continuous_walk_minutes=15), ['baseline'], '이모님의 15분 한계를 옮기지 않음'),
         case('non_trigger', scene(continuous_walk_minutes=25), ['baseline'], '능력 경계'),
         case('boundary_or_release', scene(continuous_walk_minutes=30, fatigue_high=True),
              ['baseline'], '힘들다는 말에 대한 휴식 미관찰'),
         case('unobserved_or_conflict', scene(continuous_walk_minutes=None, fatigue_high=None),
              ['baseline'], '규칙이 없어 unknown 아님')],
        '능력과 타인(이모님)의 휴식 필요를 섞음. 본인 휴식 근거 없음. 최종 의미는 원형과 같음.',
        ['타인 한계 15분 제외', '능력을 휴식으로 바꾸지 않음', '피로 발언만으로 휴식 만들지 않음'])

    # ------------------------------------------------------------------ P07
    # Root: 보행 중 무릎 통증 → 3분 휴식.
    v.variant(
        'P07', 'preserve', 'digits_colloquial', 'preserve',
        [I, ('무릎 아프다고 하실 때 어떻게 하셨어요?',
             '걸으시다가 아프다고 하시면 앉아서 한 3분 쉬셨어요. 안 아프실 때 어떻게 쉬시는지는 잘 모르겠어요.')],
        [spec('rest', 'is_walking and pain_observed', hold=3)],
        [case('trigger', scene(pain_observed=True), ['rest'], '보행 중 통증'),
         case('non_trigger', scene(pain_observed=False, continuous_walk_minutes=20), ['baseline'], '통증 없음'),
         case('boundary_or_release', scene(current_action='rest', pain_observed=True), ['baseline'], '이미 쉬는 중'),
         case('unobserved_or_conflict', scene(pain_observed=None),
              [], '통증 미확인', status='unknown', possible=['baseline', 'rest'])],
        '삼 분을 3분으로, 구어체로 바꿈. 보행 중 통증 휴식 유지.',
        ['보행 중 통증 휴식', '통증 없으면 휴식 없음', '휴식 중 재발동 없음', '통증 미확인은 unknown'])

    v.variant(
        'P07', 'counterfactual', 'observed_to_stated_wish', 'change',
        [I, ('통증이 나타나면 실제로 어떻게 하셨나요?',
             '무릎이 아프면 앉아서 좀 쉬고 싶다고 늘 말씀은 하세요. 그런데 실제로 걷다가 아프실 때 앉으셨는지는 '
             '제가 본 적이 없어요.')],
        [],
        [case('trigger', scene(pain_observed=True), ['baseline'], '쉬고 싶다는 말만'),
         case('non_trigger', scene(pain_observed=False), ['baseline'], '통증 없음'),
         case('boundary_or_release', scene(pain_observed=True, continuous_walk_minutes=20), ['baseline'], '오래 걸어도 관찰 없음'),
         case('unobserved_or_conflict', scene(pain_observed=None), ['baseline'], '규칙이 없어 unknown 아님')],
        '통증 후 실제 휴식 관찰을 쉬고 싶다는 발언과 미관찰로 변경. 규칙 없음.',
        ['발언을 휴식 명령으로 바꾸지 않음', '통증이 있어도 개인 규칙 없음'])

    v.variant(
        'P07', 'hard', 'duration_correction_other_person', 'preserve',
        [I, ('걷다가 무릎이 아프다고 하시면 어떻게 해요?', '앉아서 오 분 쉬세요.'),
         ('그건 직접 보신 건가요?',
          '어, 오 분은 제 짐작이었어요. 시계를 봤더니 삼 분쯤 앉아 계시다 일어나셨어요. 그건 두 번 다 직접 봤어요.'),
         ('아프지 않을 때도 쉬시나요?',
          '그건 모르겠어요. 아버지가 같이 쉬자고 하실 때도 있는데 그건 아버지가 피곤하셔서고요.')],
        [spec('rest', 'is_walking and pain_observed', ids=('N1', 'N2'), hold=3)],
        [case('trigger', scene(pain_observed=True), ['rest'], '보행 중 통증'),
         case('non_trigger', scene(pain_observed=False, family_present=True), ['baseline'], '아버지 피로로 휴식 만들지 않음'),
         case('boundary_or_release', scene(current_action='rest', pain_observed=True), ['baseline'], '이미 쉬는 중'),
         case('unobserved_or_conflict', scene(pain_observed=None),
              [], '통증 미확인', status='unknown', possible=['baseline', 'rest'])],
        '휴식 시간 5분 짐작을 3분 관찰로 정정. 다른 사람의 피로 휴식 혼입. 최종 의미는 원형과 같음.',
        ['통증 휴식 유지', '아버지 피로를 본인 휴식으로 옮기지 않음', '휴식 중 재발동 없음', '통증 미확인은 unknown',
         '지속시간 3분은 장면 명령으로 검사되지 않음'])

    # ------------------------------------------------------------------ P08
    # Root: 시간·숨참으로는 쉬지 않고 본인 무릎 통증 발언일 때만 휴식.
    v.variant(
        'P08', 'preserve', 'colloquial_reorder', 'preserve',
        [I, ('쉬셨던 때를 구체적으로 알려주세요.',
             '앉아 쉬신 건 무릎 아프다고 직접 말씀하셨을 때뿐이에요. 같이 걸어 보니 십이 분 넘게 걸으셔도 그냥 가셨고, '
             '숨차 보여도 안 멈추셨어요.')],
        [spec('rest', 'is_walking and pain_observed')],
        [case('trigger', scene(continuous_walk_minutes=15, pain_observed=True), ['rest'], '본인 통증'),
         case('non_trigger', scene(continuous_walk_minutes=12, fatigue_high=True), ['baseline'], '숨참 추정만'),
         case('boundary_or_release', scene(continuous_walk_minutes=30, pain_observed=False), ['baseline'], '시간만'),
         case('unobserved_or_conflict', scene(continuous_walk_minutes=20, pain_observed=None),
              [], '통증 미확인', status='unknown', possible=['baseline', 'rest'])],
        '문장 순서와 구어체만 바꿈. 통증 단독 휴식 유지.',
        ['통증이면 휴식', '숨참만으로 휴식 없음', '시간만으로 휴식 없음', '통증 미확인은 unknown'])

    v.variant(
        'P08', 'counterfactual', 'add_time_limit_or', 'change',
        [I, ('언제 쉬셨는지 구체적으로 알려주세요.',
             '실제로 같이 걸어 보니 연속 십이 분을 걸으시면 아프단 말씀이 없어도 앉아 쉬셨어요. '
             '그 전이라도 무릎이 아프다고 하시면 앉으셨고요. 숨차 보이는 것만으로 멈추신 적은 없어요.')],
        [spec('rest', 'is_walking and (pain_observed or continuous_walk_minutes >= 12)')],
        [case('trigger', scene(continuous_walk_minutes=12, pain_observed=False), ['rest'], '12분 도달'),
         case('non_trigger', scene(continuous_walk_minutes=11.9, fatigue_high=True), ['baseline'], '12분 직전 숨참'),
         case('boundary_or_release', scene(continuous_walk_minutes=5, pain_observed=True), ['rest'], '12분 전 통증'),
         case('unobserved_or_conflict', scene(continuous_walk_minutes=8, pain_observed=None),
              [], '통증 미확인', status='unknown', possible=['baseline', 'rest'])],
        '12분 후에도 계속 걸음을 12분 후 휴식으로 변경. 통증 OR 12분.',
        ['12분 휴식', '11.9분 숨참 비발동', '12분 전 통증 휴식', '통증 미확인은 unknown'])

    v.variant(
        'P08', 'hard', 'observed_vs_suggested_correction', 'preserve',
        [I, ('언제 쉬셨어요?', '숨이 차 보이면 쉬셨어요.'),
         ('숨차 보이실 때 직접 멈추시는 걸 보셨어요?',
          '아니요, 다시 생각해 보니 숨차 보여도 계속 걸으셨어요. 쉬시라고 한 건 저였고요. '
          '실제로 앉으신 건 무릎 아프다고 하실 때였어요.'),
         ('오래 걸으시면요?', '십이 분 넘게 걸으셔도 아프단 말씀이 없으면 그냥 가셨어요.')],
        [spec('rest', 'is_walking and pain_observed', ids=('N2',))],
        [case('trigger', scene(continuous_walk_minutes=3, pain_observed=True), ['rest'], '본인 통증'),
         case('non_trigger', scene(continuous_walk_minutes=14, fatigue_high=True, pain_observed=False),
              ['baseline'], '정정된 숨참·시간'),
         case('boundary_or_release', scene(current_action='rest', pain_observed=True), ['baseline'], '이미 쉬는 중'),
         case('unobserved_or_conflict', scene(fatigue_high=True, pain_observed=None),
              [], '통증 미확인', status='unknown', possible=['baseline', 'rest'])],
        '첫 답(숨참 휴식)을 보호자 권유였다고 정정. 최종 의미는 원형과 같음.',
        ['정정 후 숨참 비발동', '시간만으로 휴식 없음', '휴식 중 재발동 없음', '통증 미확인은 unknown'])

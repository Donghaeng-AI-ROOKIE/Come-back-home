"""AI-drafted derived forms for roots P25-P32 (time_context, multiple_behaviors).

Synthetic guardian Q&A only; no real person, place or clinical claim. Every
variant is draft_unreviewed. The builder checks that the reference rule
reproduces each authored scene; it does not check that the Korean text means
what the reference says.
"""
from __future__ import annotations


def register(v):
    I = v.INTRO
    sc, nb, case, spec = v.scene, v.nearby, v.case, v.spec

    # ---------------- P25: 오전 8~9시, 가족 부재 시 대기 ----------------
    p25 = 'clock_hour >= 8 and clock_hour < 9 and not family_present'
    v.variant('P25', 'preserve', 'clock_paraphrase_digits', 'preserve',
              [I, ('아침에 혼자 계실 때는 어떠셨어요?',
                   '집에 식구가 아무도 없으면 아침 8시부터 현관 앞에 서서 기다리셨어요. 9시 되기 전까지 그러시다가 9시가 되면 더는 안 기다리셨고요. 그 뒤에 뭘 하셨는지는 적어 두지 못했어요.')],
              [spec('wait', p25)],
              [case('trigger', sc(clock_hour=8, family_present=False), ['wait'], '8시 시작 경계, 가족 부재'),
               case('non_trigger', sc(clock_hour=7.9, family_present=False), ['baseline'], '시작 직전'),
               case('boundary_or_release', sc(clock_hour=9, family_present=False), ['baseline'], '9시 종료 경계, 이후 행동 발명 금지'),
               case('unobserved_or_conflict', sc(clock_hour=8.5, family_present=None), [], '가족 여부 미관측',
                    status='unknown', possible=['baseline', 'wait'])],
              '의미 동일. 시각을 숫자로 표기하고 구어체로 바꿈. 경과 시간으로 바꾸지 않음.',
              ['07:54 비발동', '08:00 가족 부재 대기', '09:00 해제', '가족 미관측은 unknown'])

    v.variant('P25', 'counterfactual', 'time_window_shift_evening', 'change',
              [I, ('저녁에 혼자 계실 때는 어떠셨어요?',
                   '저녁 여덟 시부터 아홉 시 전까지, 가족이 옆에 없으면 현관에서 기다리셨어요. 밤 아홉 시가 되면 그 기다림은 끝났고요. 그 다음은 기록이 없어요.')],
              [spec('wait', 'clock_hour >= 20 and clock_hour < 21 and not family_present')],
              [case('trigger', sc(clock_hour=20, family_present=False), ['wait'], '20시 시작 경계'),
               case('non_trigger', sc(clock_hour=8.5, family_present=False), ['baseline'], '원형의 오전 시간대는 더 이상 근거 아님'),
               case('boundary_or_release', sc(clock_hour=21, family_present=False), ['baseline'], '21시 종료 경계'),
               case('unobserved_or_conflict', sc(clock_hour=None, family_present=False), [], '시각 미관측',
                    status='unknown', possible=['baseline', 'wait'])],
              '시간대를 오전 8~9시에서 저녁 20~21시로 이동. 가족 부재 조건과 해제는 유지. 어둠 관측은 추가하지 않음.',
              ['08:30 비발동', '20:00 가족 부재 대기', '21:00 해제', '시각 미관측은 unknown'])

    v.variant('P25', 'hard', 'correction_across_turns_release_unobserved', 'preserve',
              [I, ('아침에 가족이 없으면 어떻게 하셨나요?',
                   '가족이 없을 때 아침 일곱 시부터 여덟 시 전까지 현관에서 기다리셨어요.'),
               ('그 시간이 확실한가요?',
                   '아까 시간을 잘못 말씀드렸어요. 적어 둔 걸 다시 보니 일곱 시가 아니라 여덟 시부터 아홉 시 전까지였어요. 가족이 없을 때라는 건 맞아요.'),
               ('아홉 시 이후나 가족이 함께 있을 때는요?',
                   '제가 곁에 있는 날엔 기다리지 않으셨어요. 아홉 시가 되면 기다림은 끝났는데, 그 뒤에 어디로 가셨는지는 못 봤어요.')],
              [spec('wait', p25, ids=('N2', 'N3'))],
              [case('trigger', sc(clock_hour=8.99, family_present=False), ['wait'], '정정된 시간대 끝 직전'),
               case('non_trigger', sc(clock_hour=7.5, family_present=False), ['baseline'], '철회된 7시대'),
               case('boundary_or_release', sc(clock_hour=9, family_present=False), ['baseline'], '해제 후 행동은 미관찰'),
               case('unobserved_or_conflict', sc(clock_hour=8.5, family_present=None), [], '가족 여부 미관측',
                    status='unknown', possible=['baseline', 'wait'])],
              '첫 답의 7~8시를 둘째 답에서 8~9시로 정정. 최종 의미는 원형과 같음. 해제 후 행동은 미관찰로 명시.',
              ['철회된 07:30 비발동', '08:59 대기', '09:00 해제 후 새 행동 발명 금지', '가족 미관측은 unknown'])

    # ---------------- P26: 23시~익일 1시, 가족 부재 시 대기 ----------------
    p26 = '(clock_hour >= 23 or clock_hour < 1) and not family_present'
    v.variant('P26', 'preserve', 'midnight_paraphrase_digits', 'preserve',
              [I, ('밤늦게는 어떠세요?',
                   '밤 11시부터 새벽 1시 전까지는 식구가 안 보이면 기다리셨어요. 자정 넘어서도 마찬가지였고, 1시가 되면 그만 기다리셨어요. 제가 시계 보면서 직접 확인한 거예요.')],
              [spec('wait', p26)],
              [case('trigger', sc(clock_hour=0.99, family_present=False), ['wait'], '자정 이후 종료 직전'),
               case('non_trigger', sc(clock_hour=22.9, family_present=False), ['baseline'], '시작 전'),
               case('boundary_or_release', sc(clock_hour=1, family_present=False), ['baseline'], '1시 종료 경계'),
               case('unobserved_or_conflict', sc(clock_hour=23, family_present=None), [], '가족 여부 미관측',
                    status='unknown', possible=['baseline', 'wait'])],
              '의미 동일. 시각을 숫자로 표기하고 자정 통과를 다른 말로 표현.',
              ['22:54 비발동', '00:59 대기(자정 통과)', '01:00 해제', '가족 미관측은 unknown'])

    v.variant('P26', 'counterfactual', 'end_condition_midnight', 'change',
              [I, ('늦은 밤에 시간에 따라 달랐나요?',
                   '밤 열한 시부터 자정 전까지는 가족이 안 보이면 기다리셨어요. 자정이 되면 그 기다림은 끝났어요. 자정 넘어 새벽까지 기다리신 적은 없었어요.')],
              [spec('wait', 'clock_hour >= 23 and not family_present')],
              [case('trigger', sc(clock_hour=23.99, family_present=False), ['wait'], '자정 직전'),
               case('non_trigger', sc(clock_hour=0.5, family_present=False), ['baseline'], '원형이면 대기였을 새벽 0시 30분'),
               case('boundary_or_release', sc(clock_hour=0, family_present=False), ['baseline'], '자정 종료 경계'),
               case('unobserved_or_conflict', sc(clock_hour=23.5, family_present=None), [], '가족 여부 미관측',
                    status='unknown', possible=['baseline', 'wait'])],
              '종료 시각을 새벽 1시에서 자정으로 변경. 자정을 넘는 구간이 사라짐.',
              ['23:59 대기', '00:00 해제', '00:30 비발동', '가족 미관측은 unknown'])

    v.variant('P26', 'hard', 'split_turns_release_unobserved', 'preserve',
              [I, ('밤에 가족이 안 보이면 어떻게 하셨나요?',
                   '밤 열한 시가 되면 가족이 안 보일 때 그 자리에서 기다리셨어요.'),
               ('언제까지 기다리셨어요?',
                   '자정을 넘겨서도 계속 기다리셨고, 새벽 한 시가 되니까 그만 기다리셨어요. 그 다음에 주무셨는지 나가셨는지는 저도 잠들어서 못 봤어요.'),
               ('가족이 옆에 있으면요?',
                   '제가 옆에 있던 밤에는 기다리지 않으셨어요.')],
              [spec('wait', p26, ids=('N1', 'N2', 'N3'))],
              [case('trigger', sc(clock_hour=0, family_present=False), ['wait'], '자정 통과 구간'),
               case('non_trigger', sc(clock_hour=23.5, family_present=True), ['baseline'], '가족 있음'),
               case('boundary_or_release', sc(clock_hour=1, family_present=False), ['baseline'], '해제 후 행동 미관찰'),
               case('unobserved_or_conflict', sc(clock_hour=None, family_present=False), [], '시각 미관측',
                    status='unknown', possible=['baseline', 'wait'])],
              '시작·종료·가족 조건을 세 문답에 나눔. 해제 후 행동은 미관찰로 명시. 의미는 원형과 같음.',
              ['00:00 대기', '23:30 가족 있음 비발동', '01:00 해제 후 새 행동 발명 금지', '시각 미관측은 unknown'])

    # ---------------- P27: 관측된 어둠이면 시각 무관 대기 ----------------
    v.variant('P27', 'preserve', 'dark_colloquial', 'preserve',
              [I, ('어두운 데서는 어떠셨어요?',
                   '몇 시인지는 상관없었어요. 본인이 어둡다고 하시는 데서는 멈춰 서서 기다리셨고, 밝은 데로 나오면 더 안 기다리셨어요. 밤이라고 다 그러신 건 아니고요.')],
              [spec('wait', 'dark_observed')],
              [case('trigger', sc(clock_hour=14, dark_observed=True), ['wait'], '낮의 어둠'),
               case('non_trigger', sc(clock_hour=22, dark_observed=False), ['baseline'], '밝은 밤'),
               case('boundary_or_release', sc(clock_hour=13, dark_observed=False), ['baseline'], '밝은 곳으로 나와 해제'),
               case('unobserved_or_conflict', sc(clock_hour=23.5, dark_observed=None), [], '밤이어도 밝기 미관측',
                    status='unknown', possible=['baseline', 'wait'])],
              '의미 동일. 시각 무관·밝으면 해제를 구어체로 표현.',
              ['낮 어둠 대기', '밝은 밤 비발동', '밝아지면 해제', '시각으로 어둠 추정 금지(unknown)'])

    v.variant('P27', 'counterfactual', 'dark_limited_to_night_window', 'change',
              [I, ('어두운 데서 기다리시는 게 시간과 관계가 있었나요?',
                   '저녁 여섯 시부터 다음 날 아침 여섯 시 전까지, 그 밤 시간에 본인이 어둡다고 하실 때만 기다리셨어요. 낮에 지하도에서 어둡다고 하실 때는 기다리지 않고 지나가셨어요. 밝은 데서는 밤이어도 기다리지 않으셨고요.')],
              [spec('wait', 'dark_observed and (clock_hour >= 18 or clock_hour < 6)')],
              [case('trigger', sc(clock_hour=18, dark_observed=True), ['wait'], '18시 시작 경계와 어둠'),
               case('non_trigger', sc(clock_hour=12, dark_observed=True), ['baseline'], '원형이면 대기였을 낮의 어둠'),
               case('boundary_or_release', sc(clock_hour=6, dark_observed=True), ['baseline'], '06시 종료 경계'),
               case('unobserved_or_conflict', sc(clock_hour=23, dark_observed=None), [], '밤 시간이지만 밝기 미관측',
                    status='unknown', possible=['baseline', 'wait'])],
              '시각 무관이던 어둠 대기를 18시~익일 06시로 한정(AND 시간대 추가). 어둠 관측 자체는 여전히 필요.',
              ['18:00 어둠 대기', '12:00 어둠 비발동', '06:00 해제', '밤이어도 밝기 미관측은 unknown'])

    v.variant('P27', 'hard', 'other_person_mixed_in', 'preserve',
              [I, ('어두운 곳에서 기다리시는 건 언제였나요?',
                   '어머니는 지하 통로처럼 본인이 어둡다고 하시는 데서는 낮이든 밤이든 멈춰 서서 기다리셨어요.'),
               ('밤 열 시만 되면 멈춰 서신다는 얘기도 있던데요?',
                   '그건 같이 산책하시는 옆집 할머니 얘기예요. 그분은 밤 열 시가 되면 밝든 어둡든 서 계신대요. 어머니는 시계와는 상관없었어요.'),
               ('밝은 데로 나오시면요?',
                   '밝은 데로 나오시면 기다리지 않고 다시 걸으셨어요. 그 다음에 어디로 가셨는지는 따로 적지 않았어요.')],
              [spec('wait', 'dark_observed', ids=('N1', 'N3'))],
              [case('trigger', sc(clock_hour=12, dark_observed=True), ['wait'], '낮의 어둠'),
               case('non_trigger', sc(clock_hour=22.5, dark_observed=False), ['baseline'], '이웃의 밤 열 시 대기를 가져오지 않음'),
               case('boundary_or_release', sc(clock_hour=15, dark_observed=False), ['baseline'], '밝은 곳 해제'),
               case('unobserved_or_conflict', sc(clock_hour=22, dark_observed=None), [], '밤 열 시, 밝기 미관측',
                    status='unknown', possible=['baseline', 'wait'])],
              '이웃의 시각 기반 대기를 섞었으나 본인 의미는 원형과 같음.',
              ['낮 어둠 대기', '22:30 밝음 비발동(타인 사례 제외)', '밝아지면 해제', '22:00 밝기 미관측은 unknown'])

    # ---------------- P28: 연속 보행 10분이면 휴식(시각 무관) ----------------
    p28 = 'is_walking and continuous_walk_minutes >= 10'
    v.variant('P28', 'preserve', 'duration_digits_paraphrase', 'preserve',
              [I, ('쉬셔야 하는 때가 하루 중 시간이랑 관계가 있나요?',
                   '아침이든 저녁이든 상관없어요. 쉬지 않고 10분을 걸으시면 꼭 앉아서 쉬셔야 했어요. 시계로 몇 시냐가 아니라 걸은 시간이 문제였어요. 이미 앉아 계실 땐 쉬고 계신 거고요.')],
              [spec('rest', p28)],
              [case('trigger', sc(clock_hour=7, continuous_walk_minutes=10), ['rest'], '이른 아침 10분 보행'),
               case('non_trigger', sc(clock_hour=10, continuous_walk_minutes=9.9), ['baseline'], '10시지만 10분 전'),
               case('boundary_or_release', sc(current_action='rest', clock_hour=19, continuous_walk_minutes=12),
                    ['baseline'], '이미 휴식 중'),
               case('unobserved_or_conflict', sc(clock_hour=10, continuous_walk_minutes=None), [], '보행 시간 미관측',
                    status='unknown', possible=['baseline', 'rest'])],
              '의미 동일. 숫자 표기·구어체. 시각과 보행 지속시간 구분 유지.',
              ['10분 보행 휴식', '9.9분 비발동', '휴식 중 비발동', '보행 시간 미관측은 unknown'])

    v.variant('P28', 'counterfactual', 'duration_to_clock_window', 'change',
              [I, ('쉬셔야 하는 때가 하루 중 시간이랑 관계가 있나요?',
                   '매일 오전 열 시부터 열한 시 전까지는 걷다가도 꼭 벤치에 앉아 쉬셨어요. 그 전에 얼마나 오래 걸으셨는지와는 상관없었어요.')],
              [spec('rest', 'is_walking and clock_hour >= 10 and clock_hour < 11')],
              [case('trigger', sc(clock_hour=10, continuous_walk_minutes=0), ['rest'], '10시 시작 경계, 막 걷기 시작'),
               case('non_trigger', sc(clock_hour=9.99, continuous_walk_minutes=30), ['baseline'], '오래 걸었어도 시간대 전'),
               case('boundary_or_release', sc(clock_hour=11, continuous_walk_minutes=5), ['baseline'], '11시 종료 경계'),
               case('unobserved_or_conflict', sc(clock_hour=None, continuous_walk_minutes=12), [], '시각 미관측',
                    status='unknown', possible=['baseline', 'rest'])],
              '휴식 기준을 연속 보행 10분에서 하루 시각 10~11시로 바꿈. 보행 지속시간은 무관.',
              ['10:00 보행 0분 휴식', '09:59 30분 보행 비발동', '11:00 해제', '시각 미관측은 unknown'])

    v.variant('P28', 'hard', 'numeric_correction_and_clock_memo', 'preserve',
              [I, ('얼마나 걸으시면 쉬세요?',
                   '열다섯 분 정도 걸으시면 쉬셨던 것 같아요.'),
               ('다시 확인해 주실 수 있나요?',
                   '지난주에 시계 보면서 같이 걸어 봤는데 열 분이었어요. 열다섯 분은 제 착각이에요. 아침이든 밤이든 똑같았어요.'),
               ('오전 열 시에 쉬신다는 메모도 있던데요?',
                   '그건 요양보호사 선생님이 오전 열 시에 차를 드린다는 메모예요. 어머니가 열 시에 쉬신다는 뜻이 아니에요.')],
              [spec('rest', p28, ids=('N2',))],
              [case('trigger', sc(clock_hour=21, continuous_walk_minutes=12), ['rest'], '정정값 10분 이후(착각값 15분 전)'),
               case('non_trigger', sc(clock_hour=10, continuous_walk_minutes=0), ['baseline'], '오전 10시 메모 오독 금지'),
               case('boundary_or_release', sc(clock_hour=8, continuous_walk_minutes=9.9), ['baseline'], '10분 직전'),
               case('unobserved_or_conflict', sc(current_action=None, continuous_walk_minutes=15), [], '현재 걷는지 미관측',
                    status='unknown', possible=['baseline', 'rest'])],
              '15분을 10분으로 정정하고, 오전 10시 메모는 다른 사람 일정으로 배제. 최종 의미는 원형과 같음.',
              ['12분 휴식(정정 반영)', '10:00 보행 0분 비발동', '9.9분 비발동', '현재 행동 미관측은 unknown'])

    # ---------------- P29: 휴식(6분 OR 280m) + 길 잃음 대기 ----------------
    rest29 = 'is_walking and (continuous_walk_minutes >= 6 or distance_since_rest_m >= 280)'
    wait29 = 'lost_awareness and not family_present'
    v.variant('P29', 'preserve', 'multi_turn_reorder_digits', 'preserve',
              [I, ('길을 잃은 걸 아시면 어떻게 하세요?',
                   '길 잃은 걸 알아차리셨을 때 식구가 옆에 없으면, 두 번 다 그 자리에 서서 기다리셨어요. 식구가 오니까 더는 안 기다리셨고요.'),
               ('걸으시고 나서 쉬셔야 하나요?',
                   '무릎이 안 좋으셔서 6분을 걷든 280미터를 가든, 둘 중 먼저 되는 쪽에서 쉬셔야 해요.')],
              [spec('wait', wait29, ids=('N1',)), spec('rest', rest29, ids=('N2',))],
              [case('trigger', sc(lost_awareness=True, family_present=False), ['wait'], '길 잃음 인지와 가족 부재'),
               case('non_trigger', sc(continuous_walk_minutes=5.9, distance_since_rest_m=279, family_present=True),
                    ['baseline'], '두 한계 직전'),
               case('boundary_or_release', sc(lost_awareness=True, family_present=True, distance_since_rest_m=280),
                    ['rest'], '가족 도착으로 대기 해제, 거리 한계로 휴식'),
               case('unobserved_or_conflict', sc(lost_awareness=True, family_present=False, continuous_walk_minutes=6),
                    [], '두 반응 겹침, 우선순위 미제공', status='unknown', possible=['rest', 'wait'])],
              '문답 순서만 바꾸고 숫자 표기. 문답 순서로 우선순위를 만들지 않음.',
              ['길 잃음 대기', '5.9분·279m 비발동', '가족 도착 후 280m 휴식', '겹침은 unknown'])

    v.variant('P29', 'counterfactual', 'explicit_priority_rest_first', 'change',
              [I, ('보행 후 휴식은요?',
                   '무릎 때문에 육 분 걷거나 이백팔십 미터 가면 먼저 도달한 쪽에서 쉬어야 해요.'),
               ('길을 잃은 걸 알면 어떻게 하나요?',
                   '두 번 모두 길을 잃었다는 걸 알고 가족이 없으면 그 자리에서 기다렸어요. 가족이 오면 기다림은 끝났어요.'),
               ('많이 걸으신 참에 길까지 잃으셨을 때는요?',
                   '그럴 땐 길 잃은 것보다 무릎이 먼저였어요. 일단 앉아서 쉬시고, 쉬고 난 다음에 가족을 기다리셨어요.')],
              [spec('rest', rest29, ids=('N1', 'N3')),
               spec('wait', wait29 + ' and not (' + rest29 + ')', ids=('N2', 'N3'))],
              [case('trigger', sc(lost_awareness=True, family_present=False, continuous_walk_minutes=6),
                    ['rest'], '겹침에서 휴식 우선'),
               case('non_trigger', sc(lost_awareness=True, family_present=True, continuous_walk_minutes=3),
                    ['baseline'], '가족 있음, 한계 전'),
               case('boundary_or_release', sc(lost_awareness=True, family_present=False, continuous_walk_minutes=5.9,
                                              distance_since_rest_m=279), ['wait'], '한계 직전이면 대기'),
               case('unobserved_or_conflict', sc(lost_awareness=True, family_present=False, continuous_walk_minutes=None),
                    [], '보행 시간 미관측으로 어느 쪽인지 불명', status='unknown', possible=['rest', 'wait'])],
              '두 행동 사이 우선순위(휴식 먼저)를 추가. 각 행동의 조건 자체는 원형과 같음.',
              ['겹침 시 휴식', '가족 있으면 비발동', '5.9분·279m면 대기', '보행 시간 미관측은 unknown'])

    v.variant('P29', 'hard', 'split_limits_unknown_priority', 'preserve',
              [I, ('걸으시다 쉬시는 건요?',
                   '무릎 때문에 육 분 걸으시면 쉬셔야 해요.'),
               ('거리로 따지면요?',
                   '거리로는 이백팔십 미터예요. 시간이든 거리든 먼저 닿는 쪽에서 쉬셨어요.'),
               ('길을 잃으셨을 때는요?',
                   '길을 잃은 걸 아시고 가족이 곁에 없으면 그 자리에서 기다리셨어요. 가족이 오면 끝났고요. 한참 걸으신 참에 길까지 잃으셨을 때 뭘 먼저 하셨는지는 못 봤어요.')],
              [spec('rest', rest29, ids=('N1', 'N2')), spec('wait', wait29, ids=('N3',))],
              [case('trigger', sc(continuous_walk_minutes=2, distance_since_rest_m=280), ['rest'], '둘째 문답의 거리 한계'),
               case('non_trigger', sc(continuous_walk_minutes=5.9, distance_since_rest_m=279), ['baseline'], '두 한계 직전'),
               case('boundary_or_release', sc(lost_awareness=True, family_present=True, continuous_walk_minutes=1),
                    ['baseline'], '가족 도착 해제'),
               case('unobserved_or_conflict', sc(lost_awareness=True, family_present=False, continuous_walk_minutes=6),
                    [], '겹침 순서 미관찰', status='unknown', possible=['rest', 'wait'])],
              '휴식의 시간·거리 한계를 두 문답에 나누고, 겹침 시 순서를 못 봤다고 명시. 의미는 원형과 같음.',
              ['280m 휴식(분할 문답 OR)', '5.9분·279m 비발동', '가족 도착 해제', '겹침은 unknown'])

    # ---------------- P30: 해든상가 소음 회피 + 통증 휴식 ----------------
    rest30 = 'is_walking and pain_observed'
    v.variant('P30', 'preserve', 'reorder_short_answers', 'preserve',
              [I, ('걷다가 아프다고 하시면요?',
                   '앉아서 쉬셨어요. 그건 소리랑은 상관없는 일이에요.'),
               ('해든상가가 시끄러울 때는요?',
                   '피하셨어요. 다른 상가에서는 어떠신지 몰라요.')],
              [spec('rest', rest30, ids=('N1',)),
               spec('avoid_market', 'market.noisy', ids=('N2',), labels=('해든상가',))],
              [case('trigger', nb('market', noisy=True, current_place_label='해든상가'), ['avoid_market'], '해든상가 소음'),
               case('non_trigger', nb('market', noisy=True, current_place_label='다른 상가'), ['baseline'], '이름 범위 밖'),
               case('boundary_or_release', nb('market', noisy=False, pain_observed=True, current_place_label='해든상가'),
                    ['rest'], '소음 없음, 통증 휴식만'),
               case('unobserved_or_conflict', nb('market', noisy=True, pain_observed=True, current_place_label='해든상가'),
                    [], '두 반응 우선순위 미제공', status='unknown', possible=['avoid_market', 'rest'])],
              '문답 순서를 바꾸고 짧은 답으로 표현. 질문의 조건을 답이 받는 구조. 의미는 원형과 같음.',
              ['해든상가 소음 회피', '다른 상가 비발동', '조용하면 통증 휴식만', '겹침은 unknown'])

    v.variant('P30', 'counterfactual', 'explicit_priority_pain_first', 'change',
              [I, ('상가 반응은요?',
                   '해든상가에서 시끄러우면 피했어요. 다른 상가는 모르겠어요.'),
               ('통증 반응은요?',
                   '걷다가 아프다고 말하면 앉아서 쉬었어요. 시끄러운 해든상가 앞이었을 때도 피해 가기보다 그 자리에 먼저 앉으셨어요.')],
              [spec('avoid_market', 'market.noisy and not pain_observed', ids=('N1', 'N2'), labels=('해든상가',)),
               spec('rest', rest30, ids=('N2',))],
              [case('trigger', nb('market', noisy=True, pain_observed=True, current_place_label='해든상가'),
                    ['rest'], '겹침에서 휴식 우선'),
               case('non_trigger', nb('market', noisy=True, pain_observed=False, current_place_label='해든상가'),
                    ['avoid_market'], '통증 없으면 회피'),
               case('boundary_or_release', nb('market', noisy=True, current_place_label='다른 상가'),
                    ['baseline'], '이름 범위 밖'),
               case('unobserved_or_conflict', nb('market', noisy=True, pain_observed=None, current_place_label='해든상가'),
                    [], '통증 미관측', status='unknown', possible=['avoid_market', 'rest'])],
              '두 행동 사이 우선순위(통증 휴식 먼저)를 추가. 원형의 "별개" 진술을 대체.',
              ['겹침 시 휴식', '통증 없으면 회피', '다른 상가 비발동', '통증 미관측은 unknown'])

    v.variant('P30', 'hard', 'other_person_and_unobserved_overlap', 'preserve',
              [I, ('상가에서는 어떠세요?',
                   '시끄러우면 피하셨어요. 아, 장 보러 다니시는 해든상가 얘기예요. 다른 상가는 같이 가 본 적이 없어요.'),
               ('다른 상가에서도 피하셨다는 얘기가 있던데요?',
                   '그건 같이 다니는 이웃 어르신 얘기예요. 어머니는 해든상가에서만 봤어요.'),
               ('걷다가 아프다고 하실 땐요?',
                   '앉아서 쉬셨어요. 그런데 시끄러운 해든상가 앞에서 아프다고 하신 적은 없어서, 그땐 어떻게 하실지 모르겠어요.')],
              [spec('avoid_market', 'market.noisy', ids=('N1',), labels=('해든상가',)),
               spec('rest', rest30, ids=('N3',))],
              [case('trigger', nb('market', noisy=True, current_place_label='해든상가'), ['avoid_market'], '본인 관찰 장소'),
               case('non_trigger', nb('market', noisy=True, current_place_label='다른 상가'), ['baseline'], '이웃 사례 제외'),
               case('boundary_or_release', sc(pain_observed=True), ['rest'], '통증 휴식'),
               case('unobserved_or_conflict', nb('market', noisy=True, pain_observed=True, current_place_label='해든상가'),
                    [], '겹침 미관찰', status='unknown', possible=['avoid_market', 'rest'])],
              '이웃 사례를 섞고 겹침 미관찰을 명시. 본인 의미는 원형과 같음.',
              ['해든상가 소음 회피', '다른 상가 비발동(타인 사례)', '통증 휴식', '겹침은 unknown'])

    # ---------------- P31: 공원 혼잡 회피 + 불안·가족 부재 대기 ----------------
    wait31 = 'anxiety_high and not family_present'
    v.variant('P31', 'preserve', 'colloquial_paraphrase', 'preserve',
              [I, ('공원에 사람이 많으면요?',
                   '어느 공원이든 사람이 북적이면 공원 쪽에서 비켜 가셨어요.'),
               ('식구 없이 불안해하실 때는요?',
                   '불안하다고 하시는데 저희가 안 보이면 그 자리에서 기다리셨어요. 저희가 보이면 기다리시는 건 끝났고요.')],
              [spec('avoid_park', 'park.crowded', ids=('N1',)), spec('wait', wait31, ids=('N2',))],
              [case('trigger', nb('park', crowded=True, family_present=True), ['avoid_park'], '공원 혼잡'),
               case('non_trigger', sc(crowded=True), ['baseline'], '공원에서 멂'),
               case('boundary_or_release', sc(anxiety_high=True, family_present=True), ['baseline'], '가족 보임 해제'),
               case('unobserved_or_conflict', nb('park', crowded=True, anxiety_high=True, family_present=False),
                    [], '우선순위 미제공', status='unknown', possible=['avoid_park', 'wait'])],
              '의미 동일. 구어체로 바꿈.',
              ['공원 혼잡 회피', '공원 밖 혼잡 비발동', '가족 보이면 해제', '겹침은 unknown'])

    v.variant('P31', 'counterfactual', 'one_behavior_unobserved', 'change',
              [I, ('공원 반응은요?',
                   '공원 여러 곳에서 사람이 붐비면 공원 쪽에서 멀어졌어요.'),
               ('가족이 없을 때 불안하면요?',
                   '불안하다고 하시면서 가족이 안 보이면 기다리실 거라고들 하는데, 저는 실제로 그러시는 걸 본 적이 없어요. 그때 어떻게 하셨는지는 몰라요.')],
              [spec('avoid_park', 'park.crowded', ids=('N1',))],
              [case('trigger', nb('park', crowded=True), ['avoid_park'], '공원 혼잡'),
               case('non_trigger', sc(anxiety_high=True, family_present=False), ['baseline'], '대기 관찰 없음'),
               case('boundary_or_release', nb('park', crowded=True, anxiety_high=True, family_present=False),
                    ['avoid_park'], '대기 근거가 없어 충돌 아님'),
               case('unobserved_or_conflict', nb('park', crowded=None), [], '혼잡 미관측',
                    status='unknown', possible=['baseline', 'avoid_park'])],
              '불안·가족 부재 대기를 미관찰(남의 짐작)로 바꿈. 공원 회피만 남음.',
              ['공원 혼잡 회피', '불안·부재만으로 대기 금지', '겹침 장면에서 회피만', '혼잡 미관측은 unknown'])

    v.variant('P31', 'hard', 'split_turns_unknown_priority', 'preserve',
              [I, ('공원에 사람이 많을 때요?',
                   '느티공원이든 다른 공원이든 사람이 붐비면 공원에서 멀어지셨어요.'),
               ('불안해하실 때는요?',
                   '가족이 안 보이는데 불안하다고 하시면 기다리셨어요.'),
               ('가족이 다시 보이면요? 그리고 붐비는 공원 앞에서 불안해지신 적은요?',
                   '가족이 보이면 기다리시는 건 끝났어요. 붐비는 공원 앞에서 혼자 불안해지신 적은 아직 없어서, 그럴 때 어느 쪽을 먼저 하실지는 모르겠어요.')],
              [spec('avoid_park', 'park.crowded', ids=('N1',)), spec('wait', wait31, ids=('N2', 'N3'))],
              [case('trigger', nb('park', crowded=True, current_place_label='솔빛쉼터'), ['avoid_park'],
                    '다른 공원에서도 회피(범주 범위)'),
               case('non_trigger', sc(anxiety_high=True, family_present=True), ['baseline'], '가족 보임 해제'),
               case('boundary_or_release', sc(anxiety_high=True, family_present=False), ['wait'], '불안과 부재'),
               case('unobserved_or_conflict', nb('park', crowded=True, anxiety_high=True, family_present=False),
                    [], '겹침 순서 미관찰', status='unknown', possible=['avoid_park', 'wait'])],
              '대기의 발동과 해제를 두 문답에 나누고 겹침 순서 미관찰을 명시. 의미는 원형과 같음.',
              ['다른 공원 혼잡 회피', '가족 보이면 해제', '불안·부재 대기', '겹침은 unknown'])

    # ---------------- P32: 해든상가 인지 시 출발 + 비 대기 ----------------
    v.variant('P32', 'preserve', 'reorder_colloquial', 'preserve',
              [I, ('비 올 때는 어떠세요?',
                   '비가 오는 걸 아시면 그 자리에 서서 기다리셨어요.'),
               ('해든상가를 알아보시면요?',
                   '알아보셨다고 말씀하시면 그쪽으로 걸어가기 시작하셨어요. 상가 근처에 그냥 와 있는 거랑은 달라요. 비 오는 날 상가를 알아보신 적은 없었고요.')],
              [spec('wait', 'rain_observed', ids=('N1',)), spec('seek_1', 'target_recognized', ids=('N2',))],
              [case('trigger', sc(target_recognized=True), ['seek_1'], '인지 후 출발'),
               case('non_trigger', sc(physical_arrival=True, target_recognized=False), ['baseline'], '좌표 도착만'),
               case('boundary_or_release', sc(rain_observed=True), ['wait'], '비 대기만'),
               case('unobserved_or_conflict', sc(target_recognized=True, rain_observed=True), [], '겹침 미관찰',
                    status='unknown', possible=['seek_1', 'wait'])],
              '문답 순서 변경과 구어체. 의미는 원형과 같음.',
              ['인지 후 해든상가 출발', '도착만으로 비발동', '비 대기', '겹침은 unknown'])

    v.variant('P32', 'counterfactual', 'explicit_priority_rain_first', 'change',
              [I, ('상가를 알아보면요?',
                   '해든상가를 알아봤다고 말하면 실제로 그쪽으로 출발했어요. 그냥 근처에 도착했다는 것과는 달라요.'),
               ('비가 내릴 때는요?',
                   '비가 오는 걸 알고는 그 자리에서 기다렸어요. 상가를 알아본 날 비가 오고 있었을 때도 출발하지 않고 그 자리에서 기다리셨어요.')],
              [spec('seek_1', 'target_recognized and not rain_observed', ids=('N1', 'N2')),
               spec('wait', 'rain_observed', ids=('N2',))],
              [case('trigger', sc(target_recognized=True, rain_observed=True), ['wait'], '겹침에서 비 대기 우선'),
               case('non_trigger', sc(target_recognized=True, rain_observed=False), ['seek_1'], '비 없으면 출발'),
               case('boundary_or_release', sc(physical_arrival=True, target_recognized=False), ['baseline'], '좌표 도착만'),
               case('unobserved_or_conflict', sc(target_recognized=True, rain_observed=None), [], '비 미관측',
                    status='unknown', possible=['seek_1', 'wait'])],
              '두 행동 사이 우선순위(비 대기 먼저)를 추가. 원형의 "겹침 미관찰"을 대체.',
              ['겹침 시 대기', '비 없으면 출발', '도착만으로 비발동', '비 미관측은 unknown'])

    v.variant('P32', 'hard', 'goal_correction_release_unobserved', 'preserve',
              [I, ('어디를 알아보시면 그쪽으로 가세요?',
                   '느티공원을 알아보시면 그쪽으로 가셨어요.'),
               ('느티공원이 맞나요?',
                   '아니에요, 제가 헷갈렸어요. 알아보시고 출발하신 곳은 해든상가예요. 느티공원은 지나치기만 하셨어요. 상가 근처에 와 있기만 할 때는 출발이라고 할 게 없었고요.'),
               ('비가 오면요?',
                   '비 오는 걸 아시면 그 자리에서 기다리셨어요. 비가 그친 뒤에 어디로 가셨는지는 못 봤어요.')],
              [spec('seek_1', 'target_recognized', ids=('N2',)), spec('wait', 'rain_observed', ids=('N3',))],
              [case('trigger', sc(target_recognized=True), ['seek_1'], '정정된 목표(해든상가)로 출발'),
               case('non_trigger', sc(physical_arrival=True, target_recognized=False), ['baseline'], '좌표 도착만'),
               case('boundary_or_release', sc(rain_observed=False), ['baseline'], '비 그친 뒤 새 행동 발명 금지'),
               case('unobserved_or_conflict', sc(rain_observed=None), [], '비 미관측',
                    status='unknown', possible=['baseline', 'wait'])],
              '목표를 느티공원에서 해든상가로 정정, 비 그친 뒤 행동 미관찰 명시. 의미는 원형과 같음.',
              ['해든상가 출발(seek_0 아님)', '도착만으로 비발동', '비 그친 뒤 baseline', '비 미관측은 unknown'])

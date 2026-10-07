"""Derived drafts for roots P17-P24 (external_state, source_fidelity).

AI-authored synthetic drafts (draft_unreviewed). Reference rules only check the
internal coherence of authored scene expectations; they do not prove that the
Korean wording means what the reference says. No model was called.
"""
from __future__ import annotations


def register(v):
    I, sc, nb, c, sp = v.INTRO, v.scene, v.nearby, v.case, v.spec

    # ---------------- P17: 비 관측 -> 대기, 비 그치면 해제 ----------------
    v.variant(
        'P17', 'preserve', 'colloquial_reorder', 'preserve',
        [I, ('비 올 때는 어떠셨어요?',
             '그때마다 멈춰 서서 기다리셨어요. 본인도 비 오는 걸 아셨고요. 비가 그치니까 더는 안 기다리시더라고요. 저랑 같이 나간 날 여러 번 그랬어요.')],
        [sp('wait', 'rain_observed')],
        [c('trigger', sc(rain_observed=True), ['wait'], '비 관측'),
         c('non_trigger', sc(dark_observed=True, clock_hour=21, rain_observed=False), ['baseline'], '어둠은 비가 아님'),
         c('boundary_or_release', sc(current_action='wait', rain_observed=False), ['baseline'], '비 그침 해제'),
         c('unobserved_or_conflict', sc(rain_observed=None), [], '날씨 미관측', status='unknown',
           possible=['baseline', 'wait'])],
        '문장 순서·구어체만 변경. 비 관측 시 대기, 비 그치면 해제 유지.',
        ['비 관측 시 대기', '어둠을 비로 바꾸지 않음', '비 그치면 해제', '날씨 미관측은 행동 단정 금지'])

    v.variant(
        'P17', 'counterfactual', 'rain_to_dark', 'change',
        [I, ('어두워지면 어떤 행동을 했나요?',
             '가족과 여러 번 함께 나갔는데 어두워진 걸 본인이 알아차리면 그때마다 걷는 걸 멈추고 기다렸어요. 다시 밝은 데로 나오면 대기는 끝났어요.')],
        [sp('wait', 'dark_observed')],
        [c('trigger', sc(dark_observed=True), ['wait'], '어둠 관측'),
         c('non_trigger', sc(rain_observed=True, dark_observed=False), ['baseline'], '비는 이제 근거 아님'),
         c('boundary_or_release', sc(dark_observed=False, clock_hour=23), ['baseline'], '밤이어도 밝으면 해제'),
         c('unobserved_or_conflict', sc(dark_observed=None, clock_hour=21), [], '밝기 미관측', status='unknown',
           possible=['baseline', 'wait'])],
        '대기 촉발 요인을 비 관측에서 어둠 관측으로 바꿈. 해제도 밝아짐으로 바뀜.',
        ['어둠 관측 시 대기', '비만으로 대기하지 않음', '시각으로 어둠 추정 금지', '밝기 미관측은 행동 단정 금지'])

    v.variant(
        'P17', 'hard', 'retracted_then_other_person', 'preserve',
        [I, ('어머님이 비가 오면 어떻게 하셨어요?',
             '비 오면 해든상가 쪽으로 가셨던 것 같아요.'),
         ('확실한가요? 비 올 때 실제로 어떻게 하셨는지 다시 여쭤볼게요.',
          '아까 상가 쪽으로 가셨다고 한 건 제가 잘못 기억했어요. 다시 생각해 보니 어머니는 비 오는 걸 아시면 그 자리에 멈춰서 기다리셨어요. 비가 그치면 기다리는 건 끝났고요.'),
         ('같이 나가신 다른 가족분은 비 올 때 어떻게 하셨어요?',
          '아버지는 비가 와도 우산 쓰고 계속 걸으셨어요. 그건 어머니 얘기가 아니에요.')],
        [sp('wait', 'rain_observed', ids=('N2',))],
        [c('trigger', sc(rain_observed=True), ['wait'], '정정 후 본인 대기; 철회된 상가 출발·아버지 걷기 주입 금지'),
         c('non_trigger', sc(rain_observed=False, dark_observed=True, family_present=True), ['baseline'], '비 없음'),
         c('boundary_or_release', sc(current_action='wait', rain_observed=False), ['baseline'], '비 그침 해제'),
         c('unobserved_or_conflict', sc(rain_observed=None), [], '날씨 미관측', status='unknown',
           possible=['baseline', 'wait'])],
        '첫 답(상가 출발)을 다음 턴에서 같은 사람에 대해 철회·정정. 아버지의 걷기는 타인 행동. 본인 의미는 원형과 같음.',
        ['정정된 대기만 남김', '철회된 상가 출발 주입 금지', '아버지 걷기 주입 금지', '날씨 미관측은 행동 단정 금지'])

    # ---------------- P18: 어둠 AND 가족 부재 -> 대기 ----------------
    v.variant(
        'P18', 'preserve', 'short_answer_context', 'preserve',
        [I, ('어두운 데서 혼자 계시면 멈춰서 기다리셨나요?',
             '네, 그럴 때요. 본인이 어둡다고 하시고 옆에 가족이 아무도 없을 때만요. 제가 같이 있거나 환한 데서는 안 그러셨어요. 산책 여러 번에서 봤어요.')],
        [sp('wait', 'dark_observed and not family_present')],
        [c('trigger', sc(dark_observed=True, family_present=False), ['wait'], '어둠과 부재'),
         c('non_trigger', sc(dark_observed=True, family_present=True), ['baseline'], '동행 있음'),
         c('boundary_or_release', sc(dark_observed=False, family_present=False, clock_hour=22), ['baseline'],
           '밤이어도 관측상 밝음'),
         c('unobserved_or_conflict', sc(dark_observed=True, family_present=None), [], '가족 여부 미확인',
           status='unknown', possible=['baseline', 'wait'])],
        '짧은 답이 질문에 기대는 형태로 바꿈. 어둠 AND 가족 부재 유지.',
        ['두 조건 모두일 때 대기', '가족 동행 시 대기 없음', '시각으로 어둠 추정 금지', '가족 미확인은 행동 단정 금지'])

    v.variant(
        'P18', 'counterfactual', 'and_to_or', 'change',
        [I, ('어두운 곳과 가족 유무가 영향을 주나요?',
             '여러 산책에서 봤는데 어둡다고 본인이 느끼거나, 가족이 곁에 없거나, 둘 중 하나만 있어도 멈춰 기다렸어요. 밝고 가족도 같이 있을 때만 기다리지 않았어요.')],
        [sp('wait', 'dark_observed or not family_present')],
        [c('trigger', sc(dark_observed=True, family_present=True), ['wait'], '어둠만으로 충분'),
         c('non_trigger', sc(dark_observed=False, family_present=True), ['baseline'], '밝고 동행'),
         c('boundary_or_release', sc(dark_observed=False, family_present=False), ['wait'], '부재만으로 충분'),
         c('unobserved_or_conflict', sc(dark_observed=None, family_present=True), [], '밝기 미관측',
           status='unknown', possible=['baseline', 'wait'])],
        '어둠 AND 가족 부재를 OR로 바꿈.',
        ['어둠만으로 대기', '가족 부재만으로 대기', '밝고 동행이면 대기 없음', '밝기 미관측은 행동 단정 금지'])

    v.variant(
        'P18', 'hard', 'narrowing_correction', 'preserve',
        [I, ('어두울 때 어떻게 하셨어요?', '어두우면 무조건 멈춰서 기다리셨어요.'),
         ('가족이 같이 있을 때도 그랬나요?',
          '아, 아니에요. 제가 옆에 있을 땐 어두워도 기다리지 않으셨어요. 아까 말한 건 혼자 계실 때만이에요.'),
         ('밝은 곳에서 혼자 계실 때는요?', '그땐 멈추지 않으셨어요. 본인이 어둡다고 하셔야 그러셨어요.')],
        [sp('wait', 'dark_observed and not family_present', ids=('N1', 'N2', 'N3'))],
        [c('trigger', sc(dark_observed=True, family_present=False), ['wait'], '어둠과 부재'),
         c('non_trigger', sc(dark_observed=True, family_present=True), ['baseline'], '정정으로 동행 시 제외'),
         c('boundary_or_release', sc(dark_observed=False, family_present=False), ['baseline'], '밝으면 대기 없음'),
         c('unobserved_or_conflict', sc(dark_observed=None, family_present=False, clock_hour=22), [], '밝기 미관측',
           status='unknown', possible=['baseline', 'wait'])],
        '첫 답의 무조건 대기를 다음 턴에서 같은 사람에 대해 혼자일 때로 좁힘. 최종 의미는 원형과 같음.',
        ['정정 후 동행 시 대기 없음', '두 조건 모두일 때 대기', '밝으면 대기 없음', '밝기 미관측은 행동 단정 금지'])

    # ---------------- P19: 보행 중 피로 OR 통증 -> 휴식 ----------------
    v.variant(
        'P19', 'preserve', 'colloquial_split', 'preserve',
        [I, ('걷다가 쉬시는 건 언제였어요?',
             '피곤하다 하시면 앉으셨어요. 무릎 아프다 하셔도 그랬고요. 둘 중 하나만 있어도요. 걸으실 때 얘기예요. 둘 다 멀쩡하시면 그런 걸로 쉬진 않으셨어요.')],
        [sp('rest', 'is_walking and (fatigue_high or pain_observed)')],
        [c('trigger', sc(pain_observed=True), ['rest'], '통증만'),
         c('non_trigger', sc(), ['baseline'], '둘 다 없음'),
         c('boundary_or_release', sc(current_action='rest', fatigue_high=True), ['baseline'], '이미 쉬는 중'),
         c('unobserved_or_conflict', sc(fatigue_high=None, pain_observed=False), [], '피로 미확인',
           status='unknown', possible=['baseline', 'rest'])],
        '문장을 쪼개 구어체로 바꿈. 보행 중 피로 OR 통증 휴식 유지.',
        ['통증만으로 휴식', '둘 다 없으면 휴식 없음', '쉬는 중에는 새 휴식 아님', '피로 미확인은 행동 단정 금지'])

    v.variant(
        'P19', 'counterfactual', 'or_to_and', 'change',
        [I, ('피곤하다고 할 때와 아프다고 할 때는요?',
             '실제로 걸어 다닐 때 피곤하다고 하시면서 무릎도 아프다고 하실 때, 그렇게 둘 다일 때만 잠깐 앉아 쉬셨어요. 피곤하기만 하거나 아프기만 할 때는 쉬지 않으셨어요.')],
        [sp('rest', 'is_walking and fatigue_high and pain_observed')],
        [c('trigger', sc(fatigue_high=True, pain_observed=True), ['rest'], '둘 다'),
         c('non_trigger', sc(fatigue_high=True), ['baseline'], '피로만'),
         c('boundary_or_release', sc(pain_observed=True), ['baseline'], '통증만'),
         c('unobserved_or_conflict', sc(fatigue_high=True, pain_observed=None), [], '통증 미확인',
           status='unknown', possible=['baseline', 'rest'])],
        '피로 OR 통증을 AND로 바꿈.',
        ['둘 다일 때 휴식', '피로만으로 휴식 없음', '통증만으로 휴식 없음', '통증 미확인은 행동 단정 금지'])

    v.variant(
        'P19', 'hard', 'other_person_pain', 'change',
        [I, ('걷다가 피곤하다고 하시면요?', '실제로 걸을 때 피곤하다고 하시면 잠깐 앉아 쉬셨어요.'),
         ('무릎이 아프다고 할 때도 그러셨나요?',
          '그건 제가 직접 본 적이 없어요. 무릎 아파서 앉으신다는 건 옆집 할머니 얘기를 들은 거예요.'),
         ('피곤하다는 말씀 없이도 쉬셨나요?', '아니요, 그 말씀이 없으면 쉬지는 않으셨어요.')],
        [sp('rest', 'is_walking and fatigue_high', ids=('N1', 'N3'))],
        [c('trigger', sc(fatigue_high=True), ['rest'], '본인 피로'),
         c('non_trigger', sc(pain_observed=True), ['baseline'], '통증 휴식은 이웃 이야기'),
         c('boundary_or_release', sc(current_action='rest', fatigue_high=True), ['baseline'], '이미 쉬는 중'),
         c('unobserved_or_conflict', sc(fatigue_high=None, pain_observed=True), [], '피로 미확인',
           status='unknown', possible=['baseline', 'rest'])],
        '통증 휴식이 타인(옆집 할머니) 이야기로 바뀌어 본인 규칙은 피로만 남음. 원형 의미에서 변경.',
        ['본인 피로 휴식 보존', '이웃 통증 휴식 주입 금지', '쉬는 중에는 새 휴식 아님', '피로 미확인은 행동 단정 금지'])

    # ---------------- P20: 숲 소음 -> 숲 회피 ----------------
    v.variant(
        'P20', 'preserve', 'answer_first_reorder', 'preserve',
        [I, ('숲길에서 소리가 크면요?',
             '길 가장자리 쪽에서 떨어지셨어요. 숲길 두 곳에서 봤어요. 비가 오든 안 오든, 사람이 많든 적든 상관없었고 소리만 크면 그러셨어요.')],
        [sp('avoid_forest', 'forest.noisy')],
        [c('trigger', nb('forest', noisy=True), ['avoid_forest'], '숲 소음'),
         c('non_trigger', nb('forest', crowded=True), ['baseline'], '혼잡만'),
         c('boundary_or_release', nb('forest', noisy=True, crowded=True, rain_observed=True), ['avoid_forest'],
           '비·혼잡은 제한 조건 아님'),
         c('unobserved_or_conflict', nb('forest', noisy=None), [], '숲 소음 미관측', status='unknown',
           possible=['baseline', 'avoid_forest'])],
        '답을 먼저 두고 근거를 뒤로 보냄. 숲 소음 단독 회피 유지.',
        ['숲 소음 시 회피', '혼잡만으로 회피 없음', '비·혼잡을 조건으로 추가 금지', '소음 미관측은 행동 단정 금지'])

    v.variant(
        'P20', 'counterfactual', 'add_rain_condition', 'change',
        [I, ('숲길에서 무엇을 피하셨나요?',
             '두 군데 숲길에서 봤는데 비가 오는 날 소리가 크면 길 가장자리에서 멀어졌어요. 날이 맑을 때는 소리가 커도 그러지 않았어요. 사람이 많고 적은 건 상관없었어요.')],
        [sp('avoid_forest', 'forest.noisy and rain_observed')],
        [c('trigger', nb('forest', noisy=True, rain_observed=True), ['avoid_forest'], '비와 숲 소음'),
         c('non_trigger', nb('forest', noisy=True), ['baseline'], '맑은 날 소음'),
         c('boundary_or_release', sc(noisy=True, rain_observed=True), ['baseline'], '숲 근처 아님'),
         c('unobserved_or_conflict', nb('forest', noisy=True, rain_observed=None), [], '날씨 미관측',
           status='unknown', possible=['baseline', 'avoid_forest'])],
        '비와 관계없음을 비 오는 날에만으로 바꿈(소음 AND 비).',
        ['비와 소음이 모두일 때 회피', '맑은 날 소음만으로 회피 없음', '숲 밖으로 확대 금지', '날씨 미관측은 행동 단정 금지'])

    v.variant(
        'P20', 'hard', 'other_person_crowd_pronoun', 'preserve',
        [I, ('숲길에서 어머님이 피하신 게 있나요?', '숲길 두 곳에서 소리가 크면 어머니가 길 가장자리에서 멀어지셨어요.'),
         ('사람이 많을 때도 그러셨나요?',
          '사람 많은 걸 피한 건 같이 다니던 이모예요. 어머니는 사람 많은 건 신경 안 쓰셨어요.'),
         ('그분도 소리가 크면 멀어졌나요?',
          '이모는 잘 모르겠어요. 소리 얘기는 어머니 얘기예요. 비 오는 날에도 똑같으셨고요.')],
        [sp('avoid_forest', 'forest.noisy', ids=('N1', 'N3'))],
        [c('trigger', nb('forest', noisy=True), ['avoid_forest'], '어머니 숲 소음 회피'),
         c('non_trigger', nb('forest', crowded=True), ['baseline'], '이모의 혼잡 회피 주입 금지'),
         c('boundary_or_release', nb('forest', noisy=True, rain_observed=True), ['avoid_forest'], '비 오는 날도 같음'),
         c('unobserved_or_conflict', nb('forest', crowded=True, noisy=None), [], '소음 미관측',
           status='unknown', possible=['baseline', 'avoid_forest'])],
        '혼잡 회피는 이모의 행동, 대명사 그분=이모. 본인 의미는 원형과 같음.',
        ['어머니 소음 회피 보존', '이모 혼잡 회피 주입 금지', '그분 지시 대상 구분', '소음 미관측은 행동 단정 금지'])

    # ---------------- P21: 정정 후 본인 계속 걷기 ----------------
    v.variant(
        'P21', 'preserve', 'correction_paraphrase', 'preserve',
        [I, ('어머니가 길을 잃으면 기다리셨다는 게 맞나요?',
             '아니요, 그건 제가 섞어서 말한 거예요. 기다린 건 아버지세요. 어머니는 길 잃은 걸 아셔도 안 멈추고 계속 걸으셨어요. 어머니가 서서 기다리시는 건 한 번도 못 봤어요.')],
        [sp('walk', 'lost_awareness')],
        [c('trigger', sc(lost_awareness=True), ['walk'], '정정 후 본인 걷기'),
         c('non_trigger', sc(lost_awareness=False), ['baseline'], '인지 없음'),
         c('boundary_or_release', sc(lost_awareness=True, family_present=False), ['walk'], '아버지 대기 주입 금지'),
         c('unobserved_or_conflict', sc(lost_awareness=None), [], '인지 미확인', status='unknown',
           possible=['baseline', 'walk'])],
        '정정 문장을 바꿔 말함. 아버지 대기 제외·어머니 걷기 유지.',
        ['길 잃음 인지 시 걷기', '아버지 대기 주입 금지', '인지 없으면 반응 없음', '인지 미확인은 행동 단정 금지'])

    v.variant(
        'P21', 'counterfactual', 'correction_reversed', 'change',
        [I, ('전에 계속 걸으신다고 하셨는데 맞나요?',
             '지난번 계속 걷는다는 설명은 어머니가 아니라 아버지 이야기였어요. 어머니가 길을 잃었다고 알아차리면 실제로 그 자리에 멈춰 기다렸어요. 계속 걸어가는 건 어머니에게서 본 적 없어요.')],
        [sp('wait', 'lost_awareness')],
        [c('trigger', sc(lost_awareness=True), ['wait'], '정정 후 본인 대기'),
         c('non_trigger', sc(lost_awareness=False), ['baseline'], '인지 없음'),
         c('boundary_or_release', sc(lost_awareness=True, family_present=True), ['wait'], '가족 해제 조건 발명 금지'),
         c('unobserved_or_conflict', sc(lost_awareness=None), [], '인지 미확인', status='unknown',
           possible=['baseline', 'wait'])],
        '정정 방향을 뒤집음: 걷기가 아버지, 대기가 어머니.',
        ['길 잃음 인지 시 대기', '아버지 걷기 주입 금지', '해제 조건 발명 금지', '인지 미확인은 행동 단정 금지'])

    v.variant(
        'P21', 'hard', 'cross_turn_subject_correction', 'preserve',
        [I, ('길을 잃었다는 걸 아시면 어떻게 하세요?', '그 자리에 서서 가족을 기다리세요.'),
         ('그건 어머님 이야기인가요?', '아, 방금 그건 아버지 얘기를 한 거예요. 두 분을 같이 모시다 보니 헷갈렸네요.'),
         ('그럼 어머님은요?', '어머니는 길을 잃은 걸 아셔도 멈추지 않고 계속 걸으셨어요. 제가 두 번 봤어요. 기다리시는 건 본 적 없고요.')],
        [sp('walk', 'lost_awareness', ids=('N3',))],
        [c('trigger', sc(lost_awareness=True, family_present=False), ['walk'], '아버지 대기 대신 본인 걷기'),
         c('non_trigger', sc(lost_awareness=False, anxiety_high=True), ['baseline'], '인지 없음'),
         c('boundary_or_release', sc(lost_awareness=True, family_present=True), ['walk'], '가족 유무 무관'),
         c('unobserved_or_conflict', sc(lost_awareness=None), [], '인지 미확인', status='unknown',
           possible=['baseline', 'walk'])],
        '첫 답의 대기를 다음 턴에서 아버지 이야기로 재지정, 셋째 턴에서 어머니 걷기. 본인 의미는 원형과 같음.',
        ['첫 턴 대기를 어머니에게 주입 금지', '셋째 턴 걷기 보존', '가족 유무로 해제하지 않음', '인지 미확인은 행동 단정 금지'])

    # ---------------- P22: 정정 후 붐비는 물가 회피 ----------------
    v.variant(
        'P22', 'preserve', 'correction_colloquial', 'preserve',
        [I, ('공원 피하신다고 적혀 있는데 맞아요?',
             '아, 그거 제가 잘못 말했어요. 공원 말고 물가요. 하천변에 사람 붐비면 피하셨어요. 세 군데서 제가 직접 봤고, 사람 없는 물가는 괜찮으셨어요.')],
        [sp('avoid_water', 'water.crowded')],
        [c('trigger', nb('water', crowded=True), ['avoid_water'], '붐비는 물가'),
         c('non_trigger', nb('park', crowded=True), ['baseline'], '철회된 공원'),
         c('boundary_or_release', nb('water'), ['baseline'], '한산한 물가'),
         c('unobserved_or_conflict', nb('water', crowded=None), [], '물가 혼잡 미관측', status='unknown',
           possible=['baseline', 'avoid_water'])],
        '정정 문장을 구어체로 바꿈. 공원 철회·붐비는 물가 회피 유지.',
        ['붐비는 물가 회피', '철회된 공원 회피 주입 금지', '한산하면 회피 없음', '혼잡 미관측은 행동 단정 금지'])

    v.variant(
        'P22', 'counterfactual', 'correction_reversed', 'change',
        [I, ('예전에 물가를 피한다고 했던 기록은요?',
             '제가 잘못 말했어요. 물가가 아니라 사람이 붐비는 공원을 피했어요. 공원 세 곳에서 직접 본 거예요. 한산한 공원에서는 피하지 않았어요.')],
        [sp('avoid_park', 'park.crowded')],
        [c('trigger', nb('park', crowded=True), ['avoid_park'], '붐비는 공원'),
         c('non_trigger', nb('water', crowded=True), ['baseline'], '철회된 물가'),
         c('boundary_or_release', nb('park', crowded=False), ['baseline'], '한산한 공원'),
         c('unobserved_or_conflict', nb('park', crowded=None), [], '공원 혼잡 미관측', status='unknown',
           possible=['baseline', 'avoid_park'])],
        '정정 방향을 뒤집음: 물가가 철회되고 공원이 유지됨.',
        ['붐비는 공원 회피', '철회된 물가 회피 주입 금지', '한산하면 회피 없음', '혼잡 미관측은 행동 단정 금지'])

    v.variant(
        'P22', 'hard', 'retraction_other_person', 'preserve',
        [I, ('공원에서 피하시는 게 있나요?', '사람 많은 공원을 피하셨어요.'),
         ('확실한가요? 다른 기록과 달라서 여쭤봐요.',
          '다시 생각해 보니 공원이 아니었어요. 공원을 피한 건 제 남편이고요, 어머니는 사람 붐비는 하천변을 피하셨어요. 세 군데서 봤어요.'),
         ('어머니가 시끄러운 물가도 피하셨나요?', '시끄러운 건 잘 모르겠어요. 사람이 많을 때였어요. 한산하면 안 피하셨어요.')],
        [sp('avoid_water', 'water.crowded', ids=('N2', 'N3'))],
        [c('trigger', nb('water', crowded=True, noisy=None), ['avoid_water'], '소음 몰라도 혼잡이면 회피'),
         c('non_trigger', nb('park', crowded=True), ['baseline'], '남편의 공원 회피·철회 주입 금지'),
         c('boundary_or_release', nb('water', noisy=True, crowded=False), ['baseline'], '소음만으로 회피 없음'),
         c('unobserved_or_conflict', nb('water', crowded=None), [], '물가 혼잡 미관측', status='unknown',
           possible=['baseline', 'avoid_water'])],
        '첫 턴 공원 회피를 다음 턴에서 남편 행동으로 재지정·철회, 본인 물가 혼잡 회피 유지. 본인 의미는 원형과 같음.',
        ['본인 물가 혼잡 회피 보존', '남편 공원 회피 주입 금지', '소음 조건 추가 금지', '혼잡 미관측은 행동 단정 금지'])

    # ---------------- P23: 짧은 긍정 답 -> 길 잃음 AND 가족 부재 대기 ----------------
    v.variant(
        'P23', 'preserve', 'short_answer_paraphrase', 'preserve',
        [I, ('길을 잃었다는 걸 아셨을 때, 가족이 올 때까지 그 자리에서 기다리시는 걸 보신 적 있어요?',
             '봤죠. 두 번이요. 둘 다 제 눈으로요.')],
        [sp('wait', 'lost_awareness and not family_present')],
        [c('trigger', sc(lost_awareness=True, family_present=False), ['wait'], '짧은 답을 질문 문맥으로 해석'),
         c('non_trigger', sc(lost_awareness=False, family_present=False, anxiety_high=True), ['baseline'],
           '길 잃음 인지 없음'),
         c('boundary_or_release', sc(lost_awareness=True, family_present=True), ['baseline'], '가족 도착 해제'),
         c('unobserved_or_conflict', sc(lost_awareness=None, family_present=False), [], '인지 미확인',
           status='unknown', possible=['baseline', 'wait'])],
        '짧은 긍정 답을 다른 말로 바꿈. 질문 문맥의 조건과 가족 도착 해제 유지.',
        ['인지·부재 시 대기', '가족 오면 해제', '불안만으로 대기 없음', '인지 미확인은 행동 단정 금지'])

    v.variant(
        'P23', 'counterfactual', 'yes_to_never_saw', 'change',
        [I, ('길을 잃은 걸 알면 가족이 올 때까지 기다리는 모습을 직접 보셨나요?',
             '아니요, 그런 모습은 한 번도 못 봤어요.')],
        [],
        [c('trigger', sc(lost_awareness=True, family_present=False), ['baseline'], '질문 가정을 행동으로 바꾸지 않음'),
         c('non_trigger', sc(lost_awareness=True, family_present=True), ['baseline'], '근거 없음'),
         c('boundary_or_release', sc(lost_awareness=False, family_present=False), ['baseline'], '근거 없음'),
         c('unobserved_or_conflict', sc(lost_awareness=None, family_present=None), ['baseline'], '개인 반응 근거 없음')],
        '봤다는 답을 한 번도 못 봤다는 답으로 바꿈. 개인 반응 없음.',
        ['질문 속 행동을 근거로 쓰지 않음', '인지·부재 장면에서도 대기 없음', '미관찰을 다른 행동으로 바꾸지 않음'])

    v.variant(
        'P23', 'hard', 'short_answers_across_turns', 'preserve',
        [I, ('어머님이 길을 잃은 걸 아시면 어떻게 하세요?', '가만히 서 계세요.'),
         ('가족이 옆에 있을 때도 그러신가요?', '아뇨, 그땐 안 그래요. 가족이 오면 바로 그만두세요.'),
         ('직접 보신 건가요?', '네, 두 번 다요.'),
         ('아버님도 길을 잃으셨을 때 그러셨나요?', '아버지는 아니에요. 길 잃으셔도 그냥 계속 걸어가세요. 어머니 얘기랑은 달라요.')],
        [sp('wait', 'lost_awareness and not family_present', ids=('N1', 'N2', 'N3'))],
        [c('trigger', sc(lost_awareness=True, family_present=False), ['wait'], '아버지 걷기 주입 시 충돌'),
         c('non_trigger', sc(lost_awareness=True, family_present=True), ['baseline'], '둘째 턴의 가족 해제'),
         c('boundary_or_release', sc(lost_awareness=False, family_present=False), ['baseline'], '인지 없음'),
         c('unobserved_or_conflict', sc(lost_awareness=True, family_present=None), [], '가족 여부 미확인',
           status='unknown', possible=['baseline', 'wait'])],
        '짧은 답들이 질문 문맥에 기대며 턴을 넘어 조건이 좁혀짐. 아버지 걷기는 타인. 본인 의미는 원형과 같음.',
        ['턴을 넘는 가족 해제 결합', '아버지 걷기 주입 금지', '인지 없으면 반응 없음', '가족 미확인은 행동 단정 금지'])

    # ---------------- P24: 부정 답·타인 사례 -> 반응 없음 ----------------
    v.variant(
        'P24', 'preserve', 'negation_other_family_paraphrase', 'preserve',
        [I, ('길을 잃었다는 걸 아시면 기다리시나요?',
             '아니요, 제가 그런 걸 본 적은 없어요. 예전에 네라고 한 건 다른 집에서 모시는 어르신 얘기였어요.')],
        [],
        [c('trigger', sc(lost_awareness=True, family_present=False), ['baseline'], '부정 답변'),
         c('non_trigger', sc(lost_awareness=True, family_present=True), ['baseline'], '질문 자체를 근거로 쓰지 않음'),
         c('boundary_or_release', sc(lost_awareness=True, anxiety_high=True), ['baseline'], '타인 사례 제외'),
         c('unobserved_or_conflict', sc(lost_awareness=None), ['baseline'], '개인 반응 근거 없음')],
        '부정 답과 타인 사례 정정을 다른 말로 바꿈. 개인 반응 없음 유지.',
        ['부정 답을 행동으로 바꾸지 않음', '타인 대기 주입 금지', '미관찰을 다른 행동으로 바꾸지 않음'])

    v.variant(
        'P24', 'counterfactual', 'other_becomes_patient', 'change',
        [I, ('길을 잃은 걸 알면 기다리나요?',
             '네. 기다리시는 모습을 제가 두 번 봤어요. 다른 가족이 돌보는 분 이야기가 아니라 저희 어머니 이야기예요.')],
        [sp('wait', 'lost_awareness')],
        [c('trigger', sc(lost_awareness=True), ['wait'], '본인 관찰 대기'),
         c('non_trigger', sc(lost_awareness=False), ['baseline'], '인지 없음'),
         c('boundary_or_release', sc(lost_awareness=True, family_present=True), ['wait'], '가족 해제 조건 발명 금지'),
         c('unobserved_or_conflict', sc(lost_awareness=None), [], '인지 미확인', status='unknown',
           possible=['baseline', 'wait'])],
        '타인 사례·미관찰이 본인 관찰로 바뀜. 길 잃음 인지 시 대기 생성.',
        ['본인 관찰 대기', '인지 없으면 반응 없음', '해제 조건 발명 금지', '인지 미확인은 행동 단정 금지'])

    v.variant(
        'P24', 'hard', 'retracted_yes_plus_own_rain', 'change',
        [I, ('길을 잃은 걸 알면 기다리시나요?', '네, 기다리세요.'),
         ('직접 보신 건가요?',
          '아, 아니요. 제가 본 건 아니에요. 복지관에서 다른 보호자분이 자기 어머니가 그렇다고 한 걸 듣고 헷갈렸어요. 저희 어머니가 기다리시는 건 본 적 없어요.'),
         ('그럼 어머님이 실제로 멈춰 계셨던 적은 있나요?',
          '길 잃으셨을 때는 모르겠어요. 제가 본 건 비 오는 걸 아시면 그 자리에 멈춰 기다리셨던 거예요. 비가 그치면 다시 안 기다리셨고요.')],
        [sp('wait', 'rain_observed', ids=('N3',))],
        [c('trigger', sc(rain_observed=True), ['wait'], '본인 비 대기 보존'),
         c('non_trigger', sc(lost_awareness=True, family_present=False, rain_observed=False), ['baseline'],
           '철회된 길 잃음 대기 주입 금지'),
         c('boundary_or_release', sc(rain_observed=False, current_action='wait'), ['baseline'], '비 그침 해제'),
         c('unobserved_or_conflict', sc(lost_awareness=True, rain_observed=None), [], '날씨 미관측',
           status='unknown', possible=['baseline', 'wait'])],
        '첫 턴 긍정을 다음 턴에서 타인 전언으로 철회(원형과 같은 부분). 셋째 턴에 본인 비 대기가 추가돼 참조가 원형(빈 규칙)과 달라짐.',
        ['철회된 길 잃음 대기 주입 금지', '본인 비 대기 보존', '비 그치면 해제', '날씨 미관측 시 길 잃음으로 대기 단정 금지'])

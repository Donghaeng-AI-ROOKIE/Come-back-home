"""Derived drafts for roots P09-P12 (waiting) and P13-P16 (destination).

AI-authored synthetic drafts (draft_unreviewed). Reference rules only check the
internal coherence of the authored scene expectations; they do not prove that
the Korean wording means what the reference says. Never model input.
"""


def register(v):
    S, C, R, I = v.scene, v.case, v.spec, v.INTRO
    U = ['baseline', 'wait']

    # ---------------- P09: wait while aware of being lost and family absent ----------------
    v.variant('P09', 'preserve', 'short_answer_relies_on_question', 'preserve',
              [I, ('길 잃은 걸 스스로 아셨는데 옆에 가족이 없었을 때, 그 자리에 서서 기다리시던가요?',
                   '네, 제가 본 게 두 번인데 두 번 다 그러셨어요. 저희가 도착하니까 그때부터는 안 기다리셨고요. '
                   '그 뒤에 어디로 가셨는지는 기억이 잘 안 나요.')],
              [R('wait', 'lost_awareness and not family_present')],
              [C('trigger', S(lost_awareness=True, family_present=False), ['wait'], '짧은 답이 질문의 인지·부재를 이어받음'),
               C('non_trigger', S(lost_awareness=False, family_present=False), ['baseline'], '혼자만으로는 대기 아님'),
               C('boundary_or_release', S(lost_awareness=True, family_present=True), ['baseline'], '가족 도착으로 해제'),
               C('unobserved_or_conflict', S(lost_awareness=True, family_present=None), [], '가족 여부 미확인',
                 status='unknown', possible=U)],
              '없음. 질문에 조건을 두고 짧은 긍정 답으로 바꿈.',
              ['짧은 답을 질문 문맥으로 해석', '가족 부재 단독은 비발동', '가족 도착 시 해제', '가족 미확인은 단정 금지'])

    v.variant('P09', 'counterfactual', 'family_absent_to_present', 'change',
              [I, ('길을 잃은 걸 아셨을 때 어떻게 하셨어요?',
                   '두 번 봤는데 두 번 다 제가 옆에 있을 때였어요. 길을 잃었다는 걸 아시고는 제 옆에 멈춰 서서 기다리셨어요. '
                   '혼자 계실 때 어떻게 하시는지는 본 적이 없어요.')],
              [R('wait', 'lost_awareness and family_present')],
              [C('trigger', S(lost_awareness=True, family_present=True), ['wait'], '가족 동반 중 인지'),
               C('non_trigger', S(lost_awareness=True, family_present=False), ['baseline'], '혼자일 때는 관찰 없음'),
               C('boundary_or_release', S(lost_awareness=False, family_present=True), ['baseline'], '인지 없으면 비발동'),
               C('unobserved_or_conflict', S(lost_awareness=True, family_present=None), [], '가족 여부 미확인',
                 status='unknown', possible=U)],
              '가족 부재 시 대기 → 가족 동반 시 대기로 변경. 혼자일 때 반응은 미관찰.',
              ['원형의 가족 부재 대기를 복사하지 않음', '혼자일 때 대기 단정 금지', '인지 없이 동반만으로 비발동'])

    v.variant('P09', 'hard', 'cross_turn_subject_correction', 'preserve',
              [I, ('길을 잃은 걸 아셨을 때 어떻게 하셨어요?',
                   '가족이 올 때까지 계속 걸어 다니셨어요.'),
               ('계속 걸어 다니신 게 어머니 맞으세요?',
                '아, 제가 헷갈렸어요. 계속 걸어 다닌 건 아버지 얘기였어요. 어머니는 길 잃은 걸 아시고 혼자 계실 때 '
                '그 자리에 서서 기다리셨어요. 두 번 봤어요.'),
               ('어머니는 가족이 오면 어떻게 하셨나요?',
                '저희가 가면 그때 기다리시는 건 끝났어요.')],
              [R('wait', 'lost_awareness and not family_present', ids=('N2', 'N3'))],
              [C('trigger', S(lost_awareness=True, family_present=False), ['wait'], '정정 후 본인 대기, 아버지 걷기 아님'),
               C('non_trigger', S(lost_awareness=False, family_present=False), ['baseline'], '인지 없음'),
               C('boundary_or_release', S(lost_awareness=True, family_present=True), ['baseline'], '가족 도착 해제'),
               C('unobserved_or_conflict', S(lost_awareness=None, family_present=False), [], '인지 미확인',
                 status='unknown', possible=U)],
              '없음. 첫 답(걷기)을 다음 턴에서 아버지 이야기로 정정.',
              ['정정 전 걷기 진술을 본인에게 적용하지 않음', '해제 조건은 다른 턴에서 가져옴', '인지 미확인은 단정 금지'])

    # ---------------- P10: wait when lost-aware and anxious, family irrelevant ----------------
    v.variant('P10', 'preserve', 'colloquial_reorder', 'preserve',
              [I, ('길을 잃은 걸 아셨을 때 불안해하시면요?',
                   '불안하다고 말씀하시면 잠깐 멈춰 서서 기다리셨어요. 가족이 옆에 있든 없든 똑같았어요. '
                   '길 잃은 걸 아셔도 불안해하지 않으시면 기다리진 않으셨고요.')],
              [R('wait', 'lost_awareness and anxiety_high')],
              [C('trigger', S(lost_awareness=True, anxiety_high=True, family_present=True), ['wait'], '가족 동반이어도 대기'),
               C('non_trigger', S(lost_awareness=True, anxiety_high=False), ['baseline'], '불안 없음'),
               C('boundary_or_release', S(lost_awareness=False, anxiety_high=True), ['baseline'], '인지 없음'),
               C('unobserved_or_conflict', S(lost_awareness=True, anxiety_high=None), [], '불안 미확인',
                 status='unknown', possible=U)],
              '없음. 가족 무관을 앞으로 옮기고 구어체로 바꿈.',
              ['가족 유무를 종료 요인으로 추가하지 않음', '불안 없으면 비발동', '불안 미확인은 단정 금지'])

    v.variant('P10', 'counterfactual', 'family_irrelevant_to_absent_required', 'change',
              [I, ('길을 잃은 걸 알고 불안해하실 때 어떻게 하셨나요?',
                   '가족이 곁에 없을 때는 잠깐 멈춰서 기다리셨어요. 가족이 옆에 있을 때는 불안해하셔도 기다리지는 않으셨어요. '
                   '불안해하지 않으실 때도 기다리지 않으셨고요.')],
              [R('wait', 'lost_awareness and anxiety_high and not family_present')],
              [C('trigger', S(lost_awareness=True, anxiety_high=True, family_present=False), ['wait'], '인지·불안·부재'),
               C('non_trigger', S(lost_awareness=True, anxiety_high=True, family_present=True), ['baseline'], '가족 동반이면 대기 아님'),
               C('boundary_or_release', S(lost_awareness=True, anxiety_high=False, family_present=False), ['baseline'], '불안 없음'),
               C('unobserved_or_conflict', S(lost_awareness=True, anxiety_high=True, family_present=None), [], '가족 미확인',
                 status='unknown', possible=U)],
              '가족 무관 → 가족 부재가 필요한 대기로 변경. 가족 동반 시 기다리지 않음은 걷기 명령이 아님.',
              ['가족 동반 시 대기 없음', '기다리지 않음을 걷기로 바꾸지 않음', '가족 미확인은 단정 금지'])

    v.variant('P10', 'hard', 'short_answer_with_unobserved_limit', 'preserve',
              [I, ('길을 잃은 걸 아셨을 때 기다리시던가요?',
                   '불안해하실 때만요. 무섭다, 불안하다 하시면 그 자리에 잠깐 서 계셨어요.'),
               ('그때 옆에 누가 있었나요?',
                '한 번은 저랑 같이 있을 때, 한 번은 혼자 계실 때였는데 둘 다 서 계셨어요.'),
               ('불안해하시는데 길 잃은 건 모르시는 때도 있었나요?',
                '그런 때는 제가 제대로 본 적이 없어서 잘 모르겠어요.')],
              [R('wait', 'lost_awareness and anxiety_high', ids=('N1', 'N2'))],
              [C('trigger', S(lost_awareness=True, anxiety_high=True, family_present=True), ['wait'], '동반 중에도 대기'),
               C('non_trigger', S(lost_awareness=True, anxiety_high=False), ['baseline'], '불안할 때만'),
               C('boundary_or_release', S(lost_awareness=False, anxiety_high=True, family_present=False), ['baseline'],
                 '인지 없는 불안은 미관찰, 대기 확장 금지'),
               C('unobserved_or_conflict', S(lost_awareness=None, anxiety_high=True), [], '인지 미확인',
                 status='unknown', possible=U)],
              '없음. 조건을 세 턴에 나누고 인지 없는 불안은 미관찰로 둠.',
              ['짧은 답 "불안해하실 때만요"를 질문 문맥과 결합', '동반 여부는 다른 턴에서 무관 확인',
               '미관찰 경우로 대기를 확장하지 않음', '인지 미확인은 단정 금지'])

    # ---------------- P11: guardian advice only, no observed wait ----------------
    v.variant('P11', 'preserve', 'advice_paraphrase', 'preserve',
              [I, ('혼자 계시다가 길을 잃으시면 기다리시나요?',
                   '저희가 늘 혼자일 땐 그 자리에 계시라고 당부만 드렸어요. 진짜로 그렇게 기다리시는 건 한 번도 못 봤어요. '
                   '저희가 같이 있을 때는 어떠신지도 모르고요.')],
              [],
              [C('trigger', S(lost_awareness=True, family_present=False), ['baseline'], '당부를 관찰로 바꾸지 않음'),
               C('non_trigger', S(lost_awareness=True, family_present=True), ['baseline'], '동반 시도 모름'),
               C('boundary_or_release', S(family_present=False, anxiety_high=True), ['baseline'], '혼자·불안만으로 반응 아님'),
               C('unobserved_or_conflict', S(lost_awareness=None, family_present=False), ['baseline'], '근거 자체 없음')],
              '없음. 보호자 당부일 뿐 실제 대기 미관찰.',
              ['당부를 행동 근거로 쓰지 않음', '혼자만으로 대기 단정 금지'])

    v.variant('P11', 'counterfactual', 'advice_to_observed', 'change',
              [I, ('가족 없이 길을 잃으셨을 때 기다리시나요?',
                   '처음엔 혼자일 땐 기다리시라고 제가 당부만 했는데, 그 뒤로 실제로 두 번, 길 잃은 걸 아시고 혼자 계실 때 '
                   '그 자리에서 기다리시는 걸 봤어요. 가족이 같이 있을 때는 어떠신지 모르겠어요.')],
              [R('wait', 'lost_awareness and not family_present')],
              [C('trigger', S(lost_awareness=True, family_present=False), ['wait'], '실제 관찰된 대기'),
               C('non_trigger', S(lost_awareness=False, family_present=False), ['baseline'], '인지 없음'),
               C('boundary_or_release', S(lost_awareness=True, family_present=True), ['baseline'], '동반 시 관찰 없음'),
               C('unobserved_or_conflict', S(lost_awareness=True, family_present=None), [], '가족 미확인',
                 status='unknown', possible=U)],
              '당부만 → 당부 이후 실제 대기 두 번 관찰로 변경.',
              ['당부 뒤 관찰은 행동 근거', '인지 없이 혼자만으로 비발동', '가족 미확인은 단정 금지'])

    v.variant('P11', 'hard', 'advice_plus_other_person', 'preserve',
              [I, ('혼자일 때 길을 잃으시면 기다리세요?',
                   '그렇게 하시라고 제가 몇 번이나 말씀드렸어요.'),
               ('그럼 실제로 기다리시는 걸 보셨어요?',
                '아니요, 직접 본 건 없어요. 기다렸다는 건 같은 동네 사시는 이모 이야기예요. 이모는 길 잃으면 꼭 그 자리에 서 계신대요.'),
               ('어머니께서 직접 기다리겠다고 하신 적은요?',
                '"알았다, 기다릴게" 하고 대답은 하셨는데, 실제로 그렇게 하신다는 뜻인지는 모르겠어요.')],
              [],
              [C('trigger', S(lost_awareness=True, family_present=False), ['baseline'], '당부·대답·이모 사례 모두 본인 관찰 아님'),
               C('non_trigger', S(lost_awareness=True, family_present=True), ['baseline'], '동반 시도 근거 없음'),
               C('boundary_or_release', S(anxiety_high=True, family_present=False), ['baseline'], '불안도 근거 아님'),
               C('unobserved_or_conflict', S(lost_awareness=None, family_present=False), ['baseline'], '근거 자체 없음')],
              '없음. 당부·본인 대답·타인(이모) 사례를 섞었지만 본인 관찰은 여전히 없음.',
              ['타인 사례를 본인에게 옮기지 않음', '본인의 대답(약속)을 관찰로 보지 않음', '당부를 근거로 쓰지 않음'])

    # ---------------- P12: wait when anxious and family absent, lost awareness unknown ----------------
    v.variant('P12', 'preserve', 'colloquial_short_answer', 'preserve',
              [I, ('불안해하실 때 가족이 안 보이면요?',
                   '그럴 땐 안 걸으시고 그 자리에서 기다리셨어요. 저희를 다시 만나면 그걸로 끝이었고요. '
                   '길을 잃었다고 여기셨는지까지는 제가 알 수가 없어요.')],
              [R('wait', 'anxiety_high and not family_present')],
              [C('trigger', S(anxiety_high=True, family_present=False, lost_awareness=None), ['wait'], '길 잃음 인지 조건 추가 금지'),
               C('non_trigger', S(anxiety_high=False, family_present=False), ['baseline'], '불안 없음'),
               C('boundary_or_release', S(anxiety_high=True, family_present=True), ['baseline'], '가족 만남 해제'),
               C('unobserved_or_conflict', S(anxiety_high=True, family_present=None), [], '가족 미확인',
                 status='unknown', possible=U)],
              '없음. 질문에 조건 일부를 두고 짧게 답함.',
              ['길 잃음 인지를 조건에 넣지 않음', '가족 만남 해제', '가족 미확인은 단정 금지'])

    v.variant('P12', 'counterfactual', 'patient_to_other_person', 'change',
              [I, ('가족이 안 보이고 불안해하실 때 기다리시던가요?',
                   '걷지 않고 서서 기다렸다는 건 같은 주간보호센터 다니시는 다른 어르신 이야기를 제가 옮긴 거예요. '
                   '저희 아버지가 그러시는 건 본 적이 없어요.')],
              [],
              [C('trigger', S(anxiety_high=True, family_present=False), ['baseline'], '타인 사례'),
               C('non_trigger', S(anxiety_high=False, family_present=False), ['baseline'], '불안 없음'),
               C('boundary_or_release', S(anxiety_high=True, family_present=True), ['baseline'], '해제 대상 자체 없음'),
               C('unobserved_or_conflict', S(anxiety_high=None, family_present=False), ['baseline'], '본인 근거 없음')],
              '본인 관찰 → 다른 어르신 사례로 변경. 본인 대기 규칙 없음.',
              ['타인 행동을 본인 규칙으로 옮기지 않음', '불안·부재만으로 대기 단정 금지'])

    v.variant('P12', 'hard', 'guess_corrected_to_observation', 'preserve',
              [I, ('가족이 안 보일 때 불안해하시면요?',
                   '길을 잃으셨다고 생각해서 기다리시는 것 같았어요.'),
               ('길을 잃었다고 직접 말씀하셨나요?',
                '아니요, 그건 제 짐작이었어요. 본인이 길을 잃었다고 하신 적은 없어요. 확실한 건 불안하다고 하시면서 '
                '저희가 안 보이면 걷지 않고 서 계셨다는 거예요.'),
               ('언제 다시 움직이셨어요?',
                '저희를 만나면 그때 기다리시는 건 끝났어요.')],
              [R('wait', 'anxiety_high and not family_present', ids=('N2', 'N3'))],
              [C('trigger', S(anxiety_high=True, family_present=False, lost_awareness=False), ['wait'],
                 '보호자 짐작(길 잃음)을 조건에 넣지 않음'),
               C('non_trigger', S(anxiety_high=False, family_present=False, lost_awareness=True), ['baseline'], '불안 없음'),
               C('boundary_or_release', S(anxiety_high=True, family_present=True), ['baseline'], '가족 만남 해제'),
               C('unobserved_or_conflict', S(anxiety_high=True, family_present=None), [], '가족 미확인',
                 status='unknown', possible=U)],
              '없음. 첫 답의 짐작을 다음 턴에서 철회하고 관찰만 남김.',
              ['짐작으로 붙은 길 잃음 조건 제거', '해제는 다른 턴에서 가져옴', '가족 미확인은 단정 금지'])

    # ---------------- P13: wish to go to the park, no observed departure ----------------
    v.variant('P13', 'preserve', 'wish_paraphrase', 'preserve',
              [I, ('느티공원 얘기를 자주 하시나요?',
                   '하루도 안 빼고 "느티공원 가야지" 하세요. 그런데 정말 일어나서 나서신 걸 제가 본 적은 없어요. '
                   '공원 입구를 보시면 알아보실지도 모르겠고요.')],
              [],
              [C('trigger', S(target_recognized=True), ['baseline'], '인지가 출발 근거 아님'),
               C('non_trigger', S(clock_hour=9), ['baseline'], '발언만'),
               C('boundary_or_release', S(physical_arrival=True, target_recognized=False, current_place_label='느티공원'),
                 ['baseline'], '도착만'),
               C('unobserved_or_conflict', S(target_recognized=None, home_pull_high=True), ['baseline'], '다른 마음 상태도 근거 아님')],
              '없음. 희망 발언·출발 미관찰·인지 미확인 유지.',
              ['발언을 출발로 바꾸지 않음', '인지만으로 출발 만들지 않음'])

    v.variant('P13', 'counterfactual', 'wish_to_observed_departure', 'change',
              [I, ('느티공원에 가겠다고 하시나요?',
                   '요즘은 말로 끝나지 않으세요. 실제로 일어나서 느티공원 쪽으로 걸어 나가세요. 세 번 따라가 봤는데 '
                   '모두 오전 아홉 시부터 열 시 전 사이였고, 다른 시간에는 나가지 않으셨어요. 입구를 알아보시는지는 아직 모르겠어요.')],
              [R('seek_0', 'clock_hour >= 9 and clock_hour < 10')],
              [C('trigger', S(clock_hour=9), ['seek_0'], '공원 밖에서 시작하는 실제 출발, 범위 아님'),
               C('non_trigger', S(clock_hour=11), ['baseline'], '시간 밖'),
               C('boundary_or_release', S(clock_hour=10), ['baseline'], '종료 경계'),
               C('unobserved_or_conflict', S(clock_hour=9.5, target_recognized=None), ['seek_0'], '인지 미확인을 조건으로 추가 금지')],
              '희망 발언만 → 오전 9~10시 실제 출발 관찰로 변경. 목적지는 출발 방향이지 적용 범위가 아님.',
              ['느티공원 밖에서 seek_0', '목적지를 place_labels로 넣지 않음', '열 시 종료 경계', '인지 조건 추가 금지'])

    v.variant('P13', 'hard', 'wish_vs_other_person_departure', 'preserve',
              [I, ('느티공원에 가고 싶다고 하시나요?',
                   '네, 거의 매일 그러세요.'),
               ('실제로 나가신 적도 있어요?',
                '느티공원 간다고 실제로 나서시는 건 아버지세요. 어머니는 말씀만 하시고 그냥 앉아 계세요.'),
               ('어머니가 공원 입구를 보시면 알아보시던가요?',
                '같이 지나간 적은 있는데, 알아보셨는지 그쪽으로 가려고 하셨는지는 모르겠어요. 별말 없이 지나쳤어요.')],
              [],
              [C('trigger', S(target_recognized=True), ['baseline'], '아버지의 출발을 옮기지 않음'),
               C('non_trigger', S(clock_hour=9), ['baseline'], '발언만'),
               C('boundary_or_release', S(physical_arrival=True, current_place_label='느티공원'), ['baseline'], '지나침만'),
               C('unobserved_or_conflict', S(target_recognized=None, home_pull_high=True), ['baseline'], '근거 없음')],
              '없음. 본인 희망 발언과 아버지의 실제 출발을 섞음.',
              ['타인의 출발을 본인 규칙으로 옮기지 않음', '희망 발언을 출발로 바꾸지 않음', '지나친 기록을 도착 반응으로 쓰지 않음'])

    # ---------------- P14: recognised park -> walks toward it ----------------
    v.variant('P14', 'preserve', 'colloquial_quote', 'preserve',
              [I, ('느티공원 입구를 알아보시면 어떻게 하세요?',
                   '"어, 저기 느티공원이네" 하신 게 두 번인데, 두 번 다 그 말씀 하시자마자 입구 쪽으로 걸어가셨어요. '
                   '못 알아보셨을 땐 어떠신지 아직 몰라요.')],
              [R('seek_0', 'target_recognized')],
              [C('trigger', S(target_recognized=True), ['seek_0'], '공원 밖에서 인지 후 출발'),
               C('non_trigger', S(target_recognized=False), ['baseline'], '인지 없음'),
               C('boundary_or_release', S(physical_arrival=True, target_recognized=False, current_place_label='느티공원'),
                 ['baseline'], '도착과 인지 구분'),
               C('unobserved_or_conflict', S(target_recognized=None), [], '인지 미확인',
                 status='unknown', possible=['baseline', 'seek_0'])],
              '없음. 인지를 인용 발화로 표현.',
              ['공원 밖에서 seek_0', '목적지를 place_labels로 넣지 않음', '도착만으로 인지 만들지 않음'])

    v.variant('P14', 'counterfactual', 'departure_to_wish_only', 'change',
              [I, ('느티공원 입구를 알아보시면 그쪽으로 가시나요?',
                   '알아보시고 "저기 가고 싶다"고 말씀은 하셨어요. 그런데 실제로 그쪽으로 발을 옮기시는 건 못 봤어요.')],
              [],
              [C('trigger', S(target_recognized=True), ['baseline'], '인지+희망 발언만'),
               C('non_trigger', S(target_recognized=False), ['baseline'], '인지 없음'),
               C('boundary_or_release', S(physical_arrival=True, target_recognized=True, current_place_label='느티공원'),
                 ['baseline'], '도착 반응도 없음'),
               C('unobserved_or_conflict', S(target_recognized=None), ['baseline'], '근거 없음')],
              '인지 후 실제 출발 → 인지 후 희망 발언만으로 변경. seek 규칙 없음.',
              ['희망 발언으로 seek 만들지 않음', '인지만으로 출발 단정 금지'])

    v.variant('P14', 'hard', 'place_correction_seek_from_outside', 'preserve',
              [I, ('익숙한 장소를 알아보시면 어떻게 하세요?',
                   '해든상가를 알아보시면 그쪽으로 가세요.'),
               ('해든상가가 맞나요?',
                '아, 제가 잘못 말했어요. 상가가 아니라 느티공원이에요. 멀리서 느티공원 입구를 알아보셨다고 말씀하신 두 번 다 '
                '거기서부터 공원 쪽으로 걸어가셨어요.'),
               ('공원 안에 들어가신 뒤에는요?',
                '안에서 어떻게 다니셨는지는 제가 못 따라가서 몰라요.')],
              [R('seek_0', 'target_recognized', ids=('N2',))],
              [C('trigger', S(target_recognized=True), ['seek_0'], '정정된 장소, 공원 밖에서 출발'),
               C('non_trigger', S(target_recognized=False), ['baseline'], '인지 없음, 철회된 상가 출발 없음'),
               C('boundary_or_release', S(physical_arrival=True, target_recognized=False, current_place_label='느티공원'),
                 ['baseline'], '공원 안 행동 미관찰'),
               C('unobserved_or_conflict', S(target_recognized=None), [], '인지 미확인',
                 status='unknown', possible=['baseline', 'seek_0'])],
              '없음. 장소를 다음 턴에서 정정하고 공원 안 행동은 미관찰로 둠.',
              ['정정 전 해든상가 seek 금지', '공원 밖에서 seek_0, 목적지를 범위로 쓰지 않음', '공원 안 행동 발명 금지'])

    # ---------------- P15: 10-11h with family -> heads to the market ----------------
    v.variant('P15', 'preserve', 'digits_reorder', 'preserve',
              [I, ('해든상가에는 언제 가시나요?',
                   '가족이 옆에 있을 때만요. 오전 10시가 되면 해든상가 쪽으로 나서셨고 11시부터는 안 가셨어요. '
                   '제가 본 게 세 번이에요. 혼자 계실 땐 출발 안 하셨어요.')],
              [R('seek_1', 'clock_hour >= 10 and clock_hour < 11 and family_present')],
              [C('trigger', S(clock_hour=10.5, family_present=True), ['seek_1'], '시간 안·동반'),
               C('non_trigger', S(clock_hour=10.5, family_present=False), ['baseline'], '혼자'),
               C('boundary_or_release', S(clock_hour=11, family_present=True), ['baseline'], '종료 경계'),
               C('unobserved_or_conflict', S(clock_hour=10.2, family_present=None), [], '동반 미확인',
                 status='unknown', possible=['baseline', 'seek_1'])],
              '없음. 숫자 표기·문장 순서만 바꿈.',
              ['10~11시 창 유지', '혼자면 비발동', '11시 종료 경계', '동반 미확인은 단정 금지'])

    v.variant('P15', 'counterfactual', 'time_window_shift', 'change',
              [I, ('언제 상가로 향하셨나요?',
                   '직접 본 세 번 모두 오후 세 시부터 네 시 전까지, 가족이 곁에 있을 때 해든상가 쪽으로 출발하셨어요. '
                   '오전이나 다른 시간, 혼자 계실 때는 출발하지 않으셨어요.')],
              [R('seek_1', 'clock_hour >= 15 and clock_hour < 16 and family_present')],
              [C('trigger', S(clock_hour=15, family_present=True), ['seek_1'], '새 시작 경계'),
               C('non_trigger', S(clock_hour=10.5, family_present=True), ['baseline'], '원형 시간대는 비발동'),
               C('boundary_or_release', S(clock_hour=16, family_present=True), ['baseline'], '종료 경계'),
               C('unobserved_or_conflict', S(clock_hour=15.5, family_present=None), [], '동반 미확인',
                 status='unknown', possible=['baseline', 'seek_1'])],
              '오전 10~11시 → 오후 3~4시로 시간대만 변경.',
              ['원형 시간대 복사 금지', '15시 시작·16시 종료 경계', '동반 미확인은 단정 금지'])

    v.variant('P15', 'hard', 'wish_alone_vs_departure_with_family', 'preserve',
              [I, ('해든상가에 가고 싶다는 말씀을 하세요?',
                   '혼자 계실 때도 "상가 가야 하는데" 하세요. 그런데 혼자일 땐 말만 하시고 나서진 않으셨어요.'),
               ('실제로 출발하신 건 언제였어요?',
                '오전 열 시부터, 저나 동생이 옆에 있을 때요. 세 번 다 집 앞에서부터 해든상가 쪽으로 걸어가셨어요. '
                '열한 시부터는 그런 적이 없어요.'),
               ('동생분도 같은 걸 보셨어요?',
                '동생은 저녁에 상가 가시는 걸 봤다고 하는데, 그건 어머니가 아니라 이모를 모시고 간 날이었대요.')],
              [R('seek_1', 'clock_hour >= 10 and clock_hour < 11 and family_present', ids=('N1', 'N2'))],
              [C('trigger', S(clock_hour=10, family_present=True), ['seek_1'], '집 앞(상가 밖)에서 출발'),
               C('non_trigger', S(clock_hour=10.5, family_present=False), ['baseline'], '혼자일 땐 말만'),
               C('boundary_or_release', S(clock_hour=11, family_present=True), ['baseline'], '종료 경계'),
               C('unobserved_or_conflict', S(clock_hour=10.5, family_present=None), [], '동반 미확인',
                 status='unknown', possible=['baseline', 'seek_1'])],
              '없음. 혼자일 때 희망 발언, 동반 시 실제 출발, 이모 사례를 다른 턴에 섞음.',
              ['혼자일 때 발언을 출발로 바꾸지 않음', '상가 밖에서 seek_1, 목적지를 범위로 쓰지 않음',
               '이모의 저녁 방문을 본인 시간대로 넣지 않음', '동반 미확인은 단정 금지'])

    # ---------------- P16: arrive at and recognise the shelter -> wait there ----------------
    v.variant('P16', 'preserve', 'quote_paraphrase', 'preserve',
              [I, ('솔빛쉼터에 가셨을 때 멈추신 적 있어요?',
                   '쉼터 앞까지 실제로 가셔서 "여기 솔빛쉼터네" 하고 알아보신 때에는 거기 서서 기다리셨어요. '
                   '옆으로 그냥 지나가기만 할 때는 안 멈추셨고요.')],
              [R('wait', 'physical_arrival and target_recognized', labels=('솔빛쉼터',))],
              [C('trigger', S(physical_arrival=True, target_recognized=True, current_place_label='솔빛쉼터'), ['wait'], '도착과 인지'),
               C('non_trigger', S(physical_arrival=True, target_recognized=False, current_place_label='솔빛쉼터'), ['baseline'], '도착만'),
               C('boundary_or_release', S(physical_arrival=True, target_recognized=True, current_place_label='느티공원'),
                 ['baseline'], '다른 장소'),
               C('unobserved_or_conflict', S(physical_arrival=True, target_recognized=None, current_place_label='솔빛쉼터'), [],
                 '인지 미확인', status='unknown', possible=U)],
              '없음. 인지를 인용 발화로 표현.',
              ['도착+인지 AND 유지', '솔빛쉼터 한정', '인지 미확인은 단정 금지'])

    v.variant('P16', 'counterfactual', 'recognition_to_arrival_only', 'change',
              [I, ('솔빛쉼터에서 멈추신 적 있어요?',
                   '솔빛쉼터에 도착하시면 그 자리에서 기다리셨어요. 거기가 어딘지 알아보셨는지는 상관없었어요. '
                   '"여기가 어디냐" 하실 때도 멈춰 계셨거든요. 근처를 지나가기만 할 때는 안 멈추셨어요.')],
              [R('wait', 'physical_arrival', labels=('솔빛쉼터',))],
              [C('trigger', S(physical_arrival=True, target_recognized=False, current_place_label='솔빛쉼터'), ['wait'], '인지 없이 도착'),
               C('non_trigger', S(physical_arrival=False, target_recognized=True, current_place_label='솔빛쉼터'), ['baseline'], '지나감'),
               C('boundary_or_release', S(physical_arrival=True, current_place_label='느티공원'), ['baseline'], '다른 장소'),
               C('unobserved_or_conflict', S(physical_arrival=None, current_place_label='솔빛쉼터'), [], '도착 미확인',
                 status='unknown', possible=U)],
              '도착+인지 → 도착만으로 대기로 변경. 장소 한정은 유지.',
              ['인지 조건을 남기지 않음', '지나감은 비발동', '솔빛쉼터 한정', '도착 미확인은 단정 금지'])

    v.variant('P16', 'hard', 'seek_from_outside_then_wait_inside', 'change',
              [I, ('솔빛쉼터를 알아보시면 어떻게 하세요?',
                   '멀리서 솔빛쉼터 간판을 알아보시면 아직 도착 전인데도 그쪽으로 걸어가셨어요. 두 번 봤어요.'),
               ('쉼터에 도착해서는요?',
                '도착해서 거기가 쉼터인 걸 아시면 더 걸어가지 않고 그 자리에서 기다리셨어요.'),
               ('다른 장소를 알아보셨을 때도 그러셨나요?',
                '그건 못 봤어요. 제가 본 건 솔빛쉼터뿐이에요.')],
              [R('seek_2', 'target_recognized and not physical_arrival', ids=('N1',)),
               R('wait', 'physical_arrival and target_recognized', ids=('N2',), labels=('솔빛쉼터',))],
              [C('trigger', S(target_recognized=True, physical_arrival=False), ['seek_2'],
                 '쉼터 밖에서 시작하는 출발, 목적지를 범위로 쓰지 않음'),
               C('non_trigger', S(target_recognized=False, physical_arrival=False), ['baseline'], '인지 없음'),
               C('boundary_or_release',
                 S(target_recognized=True, physical_arrival=True, current_place_label='솔빛쉼터'), ['wait'],
                 '도착하면 출발이 대기로 바뀜'),
               C('unobserved_or_conflict', S(target_recognized=True, physical_arrival=None), [], '도착 여부 미확인',
                 status='unknown', possible=['baseline', 'seek_2'])],
              '원형의 도착 후 대기에 더해, 도착 전 멀리서 알아보면 쉼터 쪽으로 출발하는 행동을 추가.',
              ['쉼터 밖에서 seek_2(목적지는 범위가 아님)', '쉼터 안 도착+인지 시 wait로 전환',
               '다른 장소 인지로 확장하지 않음', '도착 미확인은 단정 금지'])

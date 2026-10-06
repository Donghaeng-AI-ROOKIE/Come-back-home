"""Research personas: source and certainty of guardian statements (draft, unreviewed).

Family source_certainty. Each persona mixes one or two behaviors the guardian
directly observed with statements that must not become behavior: an
observation gap, the person's own claim, a guardian guess, hearsay, another
relative's case, a general belief, or an answer corrected in a later turn.
Scenes check that only the observed behavior fires and that the other
statements leave the ordinary movement prior in place. The source of a
statement is meant to show through context, not through an explicit
"I did not see it" after every sentence.

Written by an author who did not read dev128, variants_*.py, the 2026-10-06
evidence_diverse profiles/scenes or the contract A/B tests. Revised the same
day after an independent review. AI draft; needs human review before it is
frozen as evaluation data. No model call.
"""
from __future__ import annotations

FAMILY = 'source_certainty'
FAR = {'market': 1000, 'park': 1000, 'forest': 1000, 'water': 1000}


def register(v):
    persona_01(v)
    persona_02(v)
    persona_03(v)
    persona_04(v)
    persona_05(v)
    persona_06(v)
    persona_07(v)
    persona_08(v)


def persona_01(v):
    # Observation gap: the guardian is away all day; only the evening is seen.
    v.persona(
        'R_source_certainty_01', FAMILY,
        ['corpusB:C20', 'corpusB:C47', 'corpusB:C01', 'corpusA:DM-24'],
        [{'label': '자귀나무공원', 'place_type': 'park'},
         {'label': '한빛내과', 'place_type': 'hospital'},
         {'label': '모래울시장', 'place_type': 'market'}],
        [('어머니 장소로 적어 주신 세 곳은 각각 어떤 곳인가요?',
          '자귀나무공원은 아파트 정문 바로 앞에 있는 공원이에요. 한빛내과는 혈압약 타러 한 달에 한 번 가는 병원이고, '
          '모래울시장은 어머니가 삼십 년 넘게 장을 보신 시장이에요.'),
         ('보호자분은 하루를 어떻게 보내세요?',
          '저는 아침 일곱 시 반에 나가서 저녁 여섯 시는 넘어야 들어와요. 어머니는 낮엔 밖에 전혀 안 나가세요. '
          '제가 나갈 때도 집에 계시고 들어와 보면 늘 집에 계시거든요.'),
         ('어머니는 낮에 뭘 하셨다고 이야기하세요?',
          '점심 드시고 자귀나무공원 한 바퀴 돌고 경로당에 가서 화투를 치다 오셨다고 하세요. '
          '같이 치신 할머니들 이름까지 하나하나 대시면서요.'),
         ('저녁 시간은 어떻게 보내세요?',
          '저녁 드시고 일곱 시가 넘으면 시장 문 닫기 전에 가 봐야 한다면서 모래울시장 쪽으로 나서세요. '
          '걱정돼서 세 번 뒤따라가 봤는데 세 번 다 다른 데 안 들르고 곧장 시장으로 가셨어요. '
          '그게 다 여름에 해가 길 때 얘기예요. '
          '겨울처럼 그 시간에 벌써 바깥이 캄캄하면 창밖만 내다보시고 시장 얘기는 안 꺼내세요. '
          '아홉 시만 되면 어느 철이든 주무실 채비를 하시고요.'),
         ('전에 길을 잃으셨던 적이 있나요?',
          '한 번도 없어요. 동네에서 길 헤매셨다는 얘기도 들어 본 적 없고요.')],
        [v.spec('seek_2', 'clock_hour >= 19 and clock_hour < 21 and not dark_observed', ('N3',))],
        [v.case('trigger', v.scene(clock_hour=19.5), ['seek_2'],
                '해가 남은 저녁 일곱 시 반에 시장으로 곧장 나서는 모습은 딸이 세 번 따라가 직접 봤다.'),
         v.case('non_trigger', v.scene(clock_hour=13.5, current_place_label='자귀나무공원'), ['baseline'],
                '낮은 딸이 집에 없는 시간이다. 공원·경로당 일과는 본인 말이고, "전혀 안 나가세요"도 부재 시간에 대한 '
                '추정이라 둘 다 개인 반응을 만들지 않는다.'),
         v.case('boundary_or_release', v.scene(clock_hour=21, dark_observed=None), ['baseline'],
                '아홉 시만 되면 잘 준비를 한다고 했으므로 21시 정각부터 출발이 끝난다. '
                '이 시각에는 어둠이 관측되지 않아도 결과가 같다.'),
         v.case('unobserved_or_conflict', v.scene(clock_hour=19.6, dark_observed=None), [],
                '저녁 출발 시간대지만 바깥이 어두운지 관측되지 않았다. 캄캄하면 나서지 않는다고 했으므로 '
                '시장행 출발과 기본 이동이 모두 가능하다.', status='unknown',
                possible=['baseline', 'seek_2'])],
        '딸은 평일 낮에 집을 비워 낮 행동은 미관찰이다. "낮엔 전혀 안 나가세요"는 부재 시간에 대한 추정이고, '
        '공원·경로당 일과는 본인 말이다. 딸이 직접 따라가 본 것은 해가 남은 저녁 7~9시의 시장행 출발이며, '
        '바깥이 캄캄하면 나서지 않는다. 길 잃은 이력이 없다는 말은 위험이 낮다는 근거가 아니다.',
        ['낮 장면에서 본인 말(공원·경로당)이나 부재 시간의 "전혀 안 나가세요"로 행동을 만들지 않는다',
         '해가 남은 저녁의 시장행 출발은 직접 관찰이므로 과소 표현하지 않는다',
         '21시 정각에 출발이 끝나고, 어둠이 관측되지 않은 저녁은 출발과 기본 이동을 모두 열어 둔다'])


def persona_02(v):
    # The person's own claim and lack of insight vs. the wife's observed limits.
    v.persona(
        'R_source_certainty_02', FAMILY,
        ['corpusB:C45', 'corpusB:C39', 'corpusB:C10', 'local:C25'],
        [{'label': '갈대섬 둔치', 'place_type': 'park'},
         {'label': '송골제분 공장', 'place_type': 'workplace'},
         {'label': '새봄정형외과', 'place_type': 'hospital'}],
        [('남편분 등록 장소들이 어떤 곳인지 알려 주세요.',
          '갈대섬 둔치는 남편이 운동하러 간다고 늘 말하는 강변이에요. '
          '송골제분 공장은 퇴직할 때까지 다닌 직장이고, 새봄정형외과는 무릎 때문에 다니는 병원이에요.'),
         ('남편분은 걷는 것에 대해 뭐라고 하세요?',
          '둔치까지 쉬지 않고 한 시간은 거뜬하다고 하세요. 지난주에도 혼자 공장까지 걸어갔다 왔다고 하시고요.'),
         ('두 분이 같이 걸으실 때는 어떠세요?',
          '천천히 걷는 날은 35분쯤 지나면, 걸음이 빠른 날은 그보다 일찍 1.5킬로쯤 가면 꼭 길가에 앉으셔야 해요. '
          '한번 앉으시면 7분쯤은 꼼짝 않고 계시고요. 지난달에 제가 같이 나간 날만 네 번을 그러셨어요.'),
         ('무릎은 요즘 어떠세요?',
          '걷다가 무릎이 시큰거린다고 하시면 얼마 안 걸었어도 그 자리에서 바로 앉으세요. '
          '그럴 땐 제가 일으켜 드려도 한참 있다가 일어나시고요.'),
         ('혼자 다니시는 것을 본인은 어떻게 생각하세요?',
          '자기는 아무 문제 없다고, 왜 자꾸 따라다니냐고 역정을 내세요. 길 한 번 잃어 본 적 없다고도 하시고요.'),
         ('버스 정류장에서는 어떠세요?',
          '정류장에 버스가 서 있으면 어디 가는 차인지도 안 보고 올라타려고 하세요. 제가 옆에서 두 번 붙잡아 말렸어요.')],
        [v.spec('rest', 'is_walking and (continuous_walk_minutes >= 35 or distance_since_rest_m >= 1500)',
                ('N2',), hold=7),
         v.spec('rest', 'is_walking and pain_observed', ('N3',))],
        [v.case('trigger', v.scene(continuous_walk_minutes=37, distance_since_rest_m=1250, clock_hour=16),
                ['rest'],
                '천천히 걷는 날처럼 1.5킬로에 못 미쳤어도 35분을 넘겼으므로 앉아 쉰다. '
                '본인의 "한 시간 거뜬"은 한계를 바꾸지 않는다.'),
         v.case('non_trigger', v.scene(continuous_walk_minutes=24, distance_since_rest_m=1000, clock_hour=9.5,
                                       current_place_label='송골제분 공장'), ['baseline'],
                '두 한계 모두 아래이고 무릎 통증도 없다. 공장까지 혼자 다녀왔다는 말은 본인 진술이라 행동을 만들지 않는다.'),
         v.case('boundary_or_release', v.scene(continuous_walk_minutes=28, distance_since_rest_m=1530,
                                               clock_hour=17.5), ['rest'],
                '걸음이 빠른 날처럼 35분 전에 1.5킬로를 넘겼으므로 거리 쪽 한계에서 쉰다.'),
         v.case('unobserved_or_conflict', v.scene(continuous_walk_minutes=18, distance_since_rest_m=760,
                                                  pain_observed=None, clock_hour=15.5), [],
                '보행 한계에는 한참 못 미쳤지만 무릎 통증 호소가 관측되지 않았다. 통증을 말하면 바로 앉으므로 '
                '휴식과 기본 이동이 모두 가능하다.', status='unknown',
                possible=['baseline', 'rest'])],
        '본인은 한 시간 넘게 쉬지 않고 걷고 혼자 공장에 다녀왔다고 하지만 아내가 같이 걸으며 본 모습과 다르다(병식결여 가능). '
        '아내가 본 것은 35분 또는 1.5km 중 먼저 닿는 쪽에서 7분쯤 쉬는 모습과, 무릎 통증을 호소하면 곧바로 앉는 모습이다. '
        '버스에 올라타려는 모습은 관찰됐지만 엔진에 표현할 수 없다.',
        ['본인 주장(한 시간 거뜬)으로 휴식 한계를 늘리거나 지우지 않는다',
         '35분·1.5km OR 결합과 보행 중 조건을 보존한다',
         '통증 호소가 관측되지 않으면 통증 휴식을 단정하지 않는다',
         '버스 승차 시도는 표현 불가 특성으로 남긴다'],
        unsupported_sentences=('N5.s1', 'N5.s2'))


def persona_03(v):
    # Guardian guess (aimless / old house) vs. a water-noise reaction seen at two waters.
    v.persona(
        'R_source_certainty_03', FAMILY,
        ['corpusB:C19', 'corpusA:DM-40', 'corpusA:DM-20'],
        [{'label': '느릅개천 산책로', 'place_type': 'park'},
         {'label': '갈매골 옛집', 'place_type': 'past_home'}],
        [('등록하신 두 곳이 어머니께 어떤 곳인지 궁금해요.',
          '느릅개천 산책로는 집 뒤 개천을 따라 난 길이에요. '
          '갈매골 옛집은 어머니가 시집와서 이십 년 사신 집인데, 지금은 다른 분이 살고 있어요.'),
         ('어머니가 혼자 나가시면 어디로 가시려는 것 같으세요?',
          '아마 목적 없이 그냥 걸으시는 것 같아요. 어쩌면 갈매골 옛집을 찾아가시는 건가 싶기도 하고요.'),
         ('바깥에서 큰 소리가 나면 어떻게 하세요?',
          '물가에서 공사 소리나 물 퍼내는 기계 소리가 요란하면 귀를 막고 물에서 멀어지는 쪽으로 바로 돌아서세요. '
          '올봄 집 뒤 개천 공사 때 옆에서 여러 번 봤고, 여름에 큰 강가 공원에 모시고 갔을 때도 '
          '준설선 소리가 나니까 똑같이 돌아서셨어요. '
          '물가가 조용할 때는 개천이든 강이든 물길 따라 잘 걸으시고요.'),
         ('길에서 낯선 사람과 마주치면 어떠세요?',
          '제가 옆에 있는데도 지나가는 사람을 붙잡고 여기가 어디냐고 물어보세요. '
          '대답을 들으면 고맙다고 인사하고 또 걸으시고요.')],
        [v.spec('avoid_water', 'water.noisy', ('N2',))],
        [v.case('trigger', v.nearby('water', noisy=True, clock_hour=15), ['avoid_water'],
                '등록 장소가 아닌 물가에서도 기계 소리가 나면 돌아선다. 아들은 집 뒤 개천과 강가 공원 두 곳에서 '
                '같은 반응을 봤다.'),
         v.case('non_trigger', v.scene(home_pull_high=True, anxiety_high=True, clock_hour=17), ['baseline'],
                '옛집을 찾아간다는 것은 아들의 짐작이라 옛집행 출발이나 다른 행동을 만들지 않는다.'),
         v.case('boundary_or_release', v.nearby('water', noisy=False, clock_hour=7.5,
                                                current_place_label='느릅개천 산책로'), ['baseline'],
                '물가가 조용할 때는 물길 따라 잘 걷는다고 했으므로 회피가 없다.'),
         v.case('unobserved_or_conflict', v.nearby('water', noisy=None, clock_hour=12.5), [],
                '물가 근처지만 소음이 관측되지 않아 회피 여부를 정할 수 없다.', status='unknown',
                possible=['avoid_water', 'baseline'])],
        '아들은 어머니가 목적 없이 걷거나 옛집을 찾는 것 같다고 짐작할 뿐이다. '
        '직접 본 것은 물가에서 기계 소리가 요란하면 물에서 멀어지는 쪽으로 돌아서는 반응이며, '
        '등록된 개천과 등록되지 않은 강가 두 곳에서 관찰돼 물가 유형 전체에 적용한다. '
        '낯선 사람에게 길을 묻는 모습은 관찰됐지만 엔진에 표현할 수 없다.',
        ['보호자 짐작(목적 없음, 옛집)으로 옛집행 출발을 만들지 않는다',
         '두 물가에서 관찰된 소음 회피를 등록 개천 한 곳으로 좁히지 않는다',
         '소음이 있을 때만 물가 회피, 조용하면 해제',
         '길 묻기는 표현 불가 특성으로 남긴다'],
        unsupported_sentences=('N3.s1', 'N3.s2'))


def persona_04(v):
    # Hearsay from a security guard and a care worker vs. an observed wait in rain.
    v.persona(
        'R_source_certainty_04', FAMILY,
        ['corpusB:C20', 'corpusB:C04', 'corpusA:DM-03', 'corpusB:C09', 'corpusA:DM-12'],
        [{'label': '도담마트', 'place_type': 'market'},
         {'label': '해바라기 놀이터', 'place_type': 'park'},
         {'label': '들꽃역', 'place_type': 'station'},
         {'label': '바른숨내과', 'place_type': 'hospital'}],
        [('아버님께 등록된 장소들은 어떤 의미가 있나요?',
          '도담마트는 제가 장 볼 때 같이 가는 동네 마트예요. 해바라기 놀이터는 아파트 단지 안에 있어요. '
          '들꽃역은 아버님이 예전에 출퇴근하시던 역이고, 바른숨내과는 정기 검진 받는 병원이에요.'),
         ('밤에는 주로 어떻게 지내세요?',
          '경비 아저씨가 그러는데 새벽에 혼자 놀이터 근처를 서성이시는 걸 몇 번 봤대요. '
          '저희 식구는 그 시간엔 다 자고 있고요.'),
         ('낮에는 누가 아버님 곁에 있나요?',
          '평일 낮에는 요양보호사 선생님이 오세요. '
          '선생님 말로는 마트에 사람이 많으면 짜증을 내면서 밖으로 나가 버리신대요.'),
         ('두 분이 같이 밖에 나가시면 어떠세요?',
          '같이 걷다가 빗방울이 떨어지기 시작하면 아무 가게 처마 밑으로 들어가서 비가 그칠 때까지 꼼짝을 안 하세요. '
          '우산을 씌워 드려도 안 움직이세요. 비가 그치면 그제야 다시 걸으시고요.'),
         ('전에 잠깐 놓치셨던 일이 있으면 말씀해 주세요.',
          '마트 앞 의자에 앉아 계시라고 하고 계산하고 나왔더니 안 계셨어요. '
          '지나가던 이웃분이 역 쪽으로 걸어가시는 걸 봤다고 해서 가 보니 들꽃역 앞에 서 계셨어요.')],
        [v.spec('wait', 'rain_observed', ('N3',))],
        [v.case('trigger', v.scene(rain_observed=True, clock_hour=16.5), ['wait'],
                '비가 오면 처마 밑에서 그칠 때까지 움직이지 않는 모습을 며느리가 같이 걸으며 봤다.'),
         v.case('non_trigger', v.nearby('market', crowded=True, clock_hour=12.5, current_place_label='도담마트'),
                ['baseline'],
                '마트 혼잡 때 나가 버린다는 것은 요양보호사에게 들은 말이라 마트 회피를 만들지 않는다.'),
         v.case('boundary_or_release', v.scene(rain_observed=False, clock_hour=16.8), ['baseline'],
                '비가 그치면 다시 걷는다고 했으므로 대기가 해제된다.'),
         v.case('unobserved_or_conflict', v.scene(rain_observed=None, clock_hour=18,
                                                  current_place_label='들꽃역'), [],
                '비가 오는지 관측되지 않아 대기 여부를 정할 수 없다. 들꽃역 앞이지만 놓쳤던 날 역 앞에서 찾은 일(N4)은 '
                '출발 맥락이라 역행 출발을 만들지 않으므로, 가능한 답은 대기와 기본 이동뿐이다.', status='unknown',
                possible=['baseline', 'wait'])],
        '새벽 놀이터 서성임(경비원)과 마트 혼잡 시 이탈(요양보호사)은 전해 들은 말이다. '
        '마트 앞에서 기다리라고 한 뒤 사라진 일은 보호자 지시와 이웃 전언이 섞인 신고 이전 출발 맥락이라 '
        '엔진 규칙이 아니라 온보딩·신고 맥락으로 남긴다. '
        '며느리가 직접 본 반응은 비가 오면 그칠 때까지 처마 밑에서 기다리는 것이다. '
        '새벽 놀이터 전언은 장면으로 따로 시험하지 않고 검토 항목으로만 둔다.',
        ['요양보호사 전언으로 마트 회피를 만들지 않는다',
         '기다리라는 보호자 지시와 역 앞에서 찾은 일로 대기나 역행 출발을 만들지 않는다',
         '비가 그치면 대기가 해제된다',
         '경비원 전언(새벽 놀이터)은 장면 없이 검토로만 확인한다'],
        unsupported_sentences=('N4.s1', 'N4.s2'))


def persona_05(v):
    # Another relative's case vs. the mother's own place-limited avoidance.
    v.persona(
        'R_source_certainty_05', FAMILY,
        ['corpusA:DM-05', 'local:C13', 'webB:C38', 'corpusB:C39', 'corpusB:C20'],
        [{'label': '참나리공원', 'place_type': 'park'},
         {'label': '노을골 외갓집', 'place_type': 'past_home'},
         {'label': '느루시장', 'place_type': 'market'}],
        [('어머니께 등록해 두신 곳들을 설명해 주시겠어요?',
          '참나리공원은 집에서 제일 가까운 공원이에요. 노을골 외갓집은 어머니가 어릴 때 자란 시골집이고, '
          '느루시장은 반찬거리 사러 일주일에 두어 번 가시는 곳이에요.'),
         ('집안 어르신들 중에도 비슷한 분이 계셨나요?',
          '외할머니도 치매셨는데 해만 지면 집에 가야 한다고 보따리를 싸서 나가셨대요. '
          '어머니가 그 얘기를 가끔 하세요.'),
         ('저녁에 같이 산책하시면 어떠세요?',
          '해 지고 깜깜해지면 참나리공원 안으로는 절대 안 들어가세요. 공원 입구까지 갔다가도 돌아서세요. '
          '그러고는 불 켜진 큰길로 빙 돌아서 가세요. 낮에는 그 공원 벤치에도 잘 앉아 계시고요.'),
         ('저녁 산책은 주로 어디로 가세요?',
          '저녁엔 늘 참나리공원 쪽으로만 같이 나가요. 다른 공원은 저녁에 같이 가 본 적이 없고요.'),
         ('어머니가 늦게 들어오신 적이 있나요?',
          '한 번 밤늦게 들어오셨는데 느루시장에 들렀다 왔다고 하셨어요. 그 시간엔 시장이 닫혀 있었을 텐데요.')],
        [v.spec('avoid_park', 'dark_observed', ('N2',), labels=('참나리공원',))],
        [v.case('trigger', v.nearby('park', dark_observed=True, clock_hour=20.2,
                                    current_place_label='참나리공원'), ['avoid_park'],
                '어두울 때 참나리공원 입구에서 돌아서는 모습을 딸이 같이 걸으며 봤다.'),
         v.case('non_trigger', v.nearby('park', dark_observed=True, home_pull_high=True, clock_hour=18.5),
                ['baseline'],
                '해 질 녘 집에 가야 한다며 나서는 것은 외할머니 사례라 귀가 출발이나 외갓집행을 만들지 않는다. '
                '근처 공원은 참나리공원이 아니고 저녁에 가 본 적이 없으므로 어둠 회피도 넓히지 않는다. '
                '틀리면 출력 명령(seek 또는 avoid_park)으로 어느 쪽 실패인지 구분된다.'),
         v.case('boundary_or_release', v.nearby('park', dark_observed=False, clock_hour=14.5,
                                                current_place_label='참나리공원'), ['baseline'],
                '낮에는 그 공원 벤치에도 잘 앉아 있다고 했으므로 밝을 때는 회피가 해제된다.'),
         v.case('unobserved_or_conflict', v.scene(map_distance_m={**FAR, 'park': 40}, dark_observed=None,
                                                  clock_hour=19, current_place_label='참나리공원'), [],
                '참나리공원에 있지만 어두운지 관측되지 않았다.', status='unknown',
                possible=['avoid_park', 'baseline'])],
        '외할머니의 해 질 녘 귀가 시도는 다른 가족 사례이고, 어머니가 전해 준 이야기다. '
        '늦게 귀가한 날의 시장 이야기는 본인 말이고 그 시간에 시장은 닫혀 있었다. '
        '딸이 본 것은 어두울 때 참나리공원에만 들어가지 않는 반응이며 낮에는 회피하지 않는다. 다른 공원은 저녁에 가 본 적이 없다. '
        '불 켜진 큰길로 돌아가는 경로 선호는 엔진에 조명 사실이 없어 표현할 수 없다.',
        ['다른 가족(외할머니) 사례로 귀가 출발이나 외갓집행을 만들지 않는다',
         '회피 범위를 참나리공원으로 한정하고 다른 공원으로 넓히지 않는다',
         '낮에는 회피하지 않는다는 해제 조건을 보존한다',
         '밝은 큰길 선호는 표현 불가 특성으로 남긴다'],
        unsupported_sentences=('N2.s3',))


def persona_06(v):
    # A later turn corrects an earlier answer; two observed behaviors can collide.
    v.persona(
        'R_source_certainty_06', FAMILY,
        ['webB:C40', 'webB:C38', 'local:C17', 'corpusA:DM-42'],
        [{'label': '여울시장', 'place_type': 'market'},
         {'label': '한길철공소', 'place_type': 'workplace'},
         {'label': '능금공원', 'place_type': 'park'}],
        [('아버님 장소 세 곳은 각각 어떤 곳인가요?',
          '여울시장은 집 앞 재래시장이에요. 한길철공소는 아버지가 마흔 해 가까이 일하신 공장이고, '
          '능금공원은 동네 뒷산 아래 공원이에요.'),
         ('시장 같은 데 가시면 어떠세요?',
          '시장처럼 사람 붐비는 데 가시면 질색을 하고 바로 빠져나오세요.'),
         ('길을 헤매신 적이 있나요?',
          '길을 잃으셨다 싶으면 꼭 저한테 전화해서 여기가 어딘지 모르겠다고 하세요. '
          '그러고는 전화를 붙든 채 한길철공소 쪽으로 걸어가세요. '
          '작년 가을이랑 올봄에 두 번 그러셨는데, 두 번 다 대낮이었고 통화하면서 쫓아가 보니 공장 쪽으로 가고 계셨어요. '
          '길 잃은 줄 모르실 때는 그냥 가던 대로 가시고요.'),
         ('저녁에 함께 나가시면 어떠세요?',
          '저녁 산책하다 제가 한눈판 사이에 서로 놓친 적이 두 번 있어요. '
          '두 번 다 날이 어두울 때였는데, 찾아가 보니 놓친 자리 근처 환한 가로등 밑에 꼼짝 않고 서 계셨어요. '
          '제가 가서 팔을 잡아 드리면 그제야 따라 걸으시고요.'),
         ('더 하실 말씀이 있으세요?',
          '아, 아까 시장 붐비면 빠져나오신다고 한 거요, 생각해 보니 그건 돌아가신 큰아버지 얘기예요. '
          '아버지는 오히려 북적이는 시장 구경을 좋아하세요.')],
        [v.spec('seek_1', 'lost_awareness', ('N2',)),
         v.spec('wait', 'dark_observed and not family_present', ('N3',))],
        [v.case('trigger', v.scene(lost_awareness=True, clock_hour=16), ['seek_1'],
                '대낮에 길 잃음을 알아채면 철공소 쪽으로 가는 모습을 아들이 통화하며 두 번 따라가 확인했다.'),
         v.case('non_trigger', v.nearby('market', crowded=True, noisy=True, family_present=True, clock_hour=11.5),
                ['baseline'],
                '시장 혼잡 회피는 마지막 답에서 큰아버지 이야기로 정정됐다. 아들이 곁에 있는 낮 장면이라 '
                '다른 반응도 걸리지 않는다.'),
         v.case('boundary_or_release', v.scene(dark_observed=True, family_present=True, clock_hour=19),
                ['baseline'],
                '어두워도 아들이 곁에 오면 기다림이 끝나고 따라 걷는다.'),
         v.case('unobserved_or_conflict', v.scene(lost_awareness=True, dark_observed=True, clock_hour=18.5), [],
                '길 잃음을 알아챈 상태와 어두운데 아들과 떨어진 상태가 겹친다. 철공소행은 두 번 다 대낮이었고 '
                '가로등 밑 대기는 어두울 때였으므로, 둘이 겹칠 때 어느 쪽인지 원문에 없다.',
                status='unknown', possible=['seek_1', 'wait'])],
        '첫 답의 시장 혼잡 회피는 마지막 답에서 돌아가신 큰아버지 이야기로 정정됐다. '
        '아들이 직접 확인한 반응은 대낮에 길 잃음을 알아채면 옛 직장인 철공소로 가는 것과, '
        '어두울 때 아들과 떨어지면 가로등 밑에서 아들이 올 때까지 기다리는 것이다. 두 반응이 겹칠 때의 우선순위는 말하지 않았다. '
        '아들에게 전화해 도움을 청하는 모습과 북적이는 시장을 좋아하는 성향은 엔진에 표현할 수 없다.',
        ['정정된 시장 혼잡 회피를 아버지 행동으로 실행하지 않는다',
         '길 잃음 인지 시 철공소행 출발과 어둠 속 단독 대기를 모두 보존한다',
         '가족이 곁에 오면 대기를 해제하고, 두 반응이 겹치면 우선순위를 지어내지 않는다',
         '전화로 도움 요청·시장 구경 선호는 표현 불가 특성으로 남긴다'],
        unsupported_sentences=('N2.s1', 'N4.s2'))


def persona_07(v):
    # General beliefs (TV, books) and 'no history' vs. an observed old-duty trip in rain.
    v.persona(
        'R_source_certainty_07', FAMILY,
        ['corpusB:C01', 'webB:C38', 'corpusA:DM-12', 'webB:C27', 'webA:C36'],
        [{'label': '달맞이시장 골목', 'place_type': 'market'},
         {'label': '연꽃못 저수지', 'place_type': 'park'}],
        [('할머니 장소로 등록하신 곳은 어떤 곳인가요?',
          '달맞이시장 골목은 할머니가 젊으셨을 때 채소 좌판을 하시던 데예요. '
          '연꽃못 저수지는 동네 어르신들이 많이 걷는 산책 코스고요.'),
         ('할머니께서 혼자 다니시다가 헤매신 적이 있나요?',
          '배회 같은 건 한 번도 없으셨어요.'),
         ('할머니가 나가시면 어디로 가실 것 같으세요?',
          '치매 어르신들은 물가로 많이 가신다고 텔레비전에서 봤어요. '
          '해 질 녘에 특히 불안해하신다는 것도 책에서 읽었고요.'),
         ('할머니와 지내시면서 눈에 띄는 모습이 있나요?',
          '비가 오기 시작하면 물건 젖는다고 우산도 안 챙기고 달맞이시장 골목 옛 좌판 자리로 나서세요. '
          '제가 다섯 번 넘게 따라가 봤는데 매번 곧장 그 자리까지 가셨어요. '
          '거기 닿아서 빈자리를 확인하고 나면 그 뒤로는 더 찾는 데 없이 평소처럼 걸으시고요.')],
        [v.spec('seek_0', 'rain_observed and not physical_arrival', ('N3',))],
        [v.case('trigger', v.scene(rain_observed=True, clock_hour=12), ['seek_0'],
                '비가 오기 시작하면 옛 좌판 자리로 곧장 가는 모습을 손녀가 다섯 번 넘게 따라가 봤다.'),
         v.case('non_trigger', v.nearby('water', noisy=True, crowded=True, anxiety_high=True, clock_hour=18.2),
                ['baseline'],
                '물가로 간다, 해 질 녘에 불안해한다는 것은 방송·책에서 본 일반론이라 할머니의 반응을 만들지 않는다.'),
         v.case('boundary_or_release', v.scene(rain_observed=True, physical_arrival=True, clock_hour=15,
                                               current_place_label='달맞이시장 골목'), ['baseline'],
                '좌판 자리에 닿고 나면 더 찾지 않고 평소처럼 걷는다고 했으므로, 비가 계속 와도 출발이 끝난다.'),
         v.case('unobserved_or_conflict', v.scene(rain_observed=None, clock_hour=16.5), [],
                '비가 오는지 관측되지 않아 좌판 자리로 출발하는지 정할 수 없다.', status='unknown',
                possible=['baseline', 'seek_0'])],
        '물가로 간다, 해 질 녘에 불안하다는 내용은 방송·책에서 본 일반론이다. 배회 이력이 없다는 말은 위험이 낮다는 근거가 아니다. '
        '손녀가 직접 본 것은 비가 오기 시작하면 예전 좌판 자리로 곧장 가는 반응이며, 그 자리에 닿으면 출발이 끝난다.',
        ['일반론으로 물가 접근·회피나 해 질 녘 행동을 만들지 않는다',
         '비 올 때 좌판 자리로 가는 직접 관찰을 과소 표현하지 않는다',
         '좌판 자리 도착 뒤에는 출발을 이어 가지 않는다',
         '배회 이력 없음은 행동 근거로 쓰지 않는다'])


def persona_08(v):
    # Confabulated or reordered self-reports vs. the daughter's two direct observations.
    v.persona(
        'R_source_certainty_08', FAMILY,
        ['corpusB:C39', 'corpusB:C44', 'corpusB:C47', 'corpusA:DM-29', 'corpusB:C10'],
        [{'label': '돌샘 약수터 정자', 'place_type': 'park'},
         {'label': '은하역', 'place_type': 'station'},
         {'label': '진달래골 고향집', 'place_type': 'past_home'}],
        [('어머니께 등록된 세 곳에 대해 말씀해 주세요.',
          '돌샘 약수터 정자는 뒷산 초입에 있는 쉼터예요. 은하역은 어머니가 고향 갈 때 늘 기차 타시던 역이고, '
          '진달래골 고향집은 어머니가 시집오기 전까지 사시던 집이에요.'),
         ('요즘 어머니는 다녀오신 곳 이야기를 어떻게 하세요?',
          '어제 은하역에서 고향 친구를 만나고 왔다고 아주 자세하게 얘기하세요. 어제는 하루 종일 저랑 집에 계셨거든요. '
          '그 말씀을 드리면 친구가 기차 시간 때문에 먼저 갔다고 그럴듯하게 둘러대시고요.'),
         ('어머니는 산책하다 쉬는 것에 대해 뭐라고 하세요?',
          '매일 약수터 정자에 가서 한참 쉬다 온다고 하세요. 정자 옆 약숫물이 달다는 얘기도 꼭 덧붙이시고요.'),
         ('같이 걸으실 때는 어떠세요?',
          '덜 지치셨을 땐 여느 어르신들처럼 걷다가 쉬다가 하세요. '
          '그런데 숨이 차고 다리가 후들거릴 만큼 지치시면 그때부터는 절대 안 앉으세요. '
          '제가 좀 쉬었다 가자고 붙잡아도 손을 뿌리치고 계속 걸으세요.'),
         ('처음 가 보는 동네에서는 어떠세요?',
          '같이 걷다가 길이 낯설다 싶으시면 여기가 어디냐면서 길가에 털썩 주저앉으세요. '
          '그럴 땐 제가 달래도 한참 있다가 일어나세요. '
          '지금까지 두 번 그러셨는데, 두 번 다 나선 지 얼마 안 돼 기운이 남아 있을 때였어요.'),
         ('예전에 잠깐 떨어지셨던 적이 있나요?',
          '두 달 전에 장에서 저를 놓치고 혼자 집에 오셨어요. '
          '버스를 탔다가 걸었다가 했다고 하시는데, 얘기하실 때마다 순서가 달라요.'),
         ('길에서 다른 사람을 보면 어떠세요?',
          '낯익은 얼굴이랑 비슷한 사람만 보면 그 사람을 졸졸 따라가세요. '
          '지난주에도 제 눈앞에서 모르는 아주머니를 한참 따라가셨어요.')],
        [v.spec('walk', 'is_walking and fatigue_high', ('N3',)),
         v.spec('rest', 'is_walking and lost_awareness', ('N4',))],
        [v.case('trigger', v.scene(fatigue_high=True, continuous_walk_minutes=74, distance_since_rest_m=3500,
                                   clock_hour=13), ['walk'],
                '숨이 찰 만큼 지쳐도 앉지 않고 계속 걷는 모습을 딸이 직접 봤다.'),
         v.case('non_trigger', v.scene(continuous_walk_minutes=38, distance_since_rest_m=1800, clock_hour=7,
                                       current_place_label='돌샘 약수터 정자'), ['baseline'],
                '정자에서 쉰다는 것은 본인 말이라 휴식을 만들지 않는다. 아직 지치지 않았으므로 버티는 반응도 걸리지 않는다.'),
         v.case('boundary_or_release', v.scene(continuous_walk_minutes=52, distance_since_rest_m=2450,
                                               clock_hour=15.5), ['baseline'],
                '오래 걸었어도 숨이 찰 만큼 지치기 전에는 여느 어르신처럼 걷다 쉬다 한다고 했으므로 개인 반응이 없다.'),
         v.case('unobserved_or_conflict', v.scene(fatigue_high=True, lost_awareness=True, continuous_walk_minutes=81,
                                                  distance_since_rest_m=3800, clock_hour=17.5,
                                                  current_place_label='은하역'), [],
                '지쳐도 버티는 반응과 길이 낯설면 주저앉는 반응이 겹친다. 주저앉은 두 번은 기운이 남아 있을 때였으므로 '
                '지쳤을 때 어느 쪽인지 원문에 없다. 은하역 앞이지만 작화 진술로 역행 출발을 만들지 않으므로 가능한 답은 둘뿐이다.',
                status='unknown', possible=['rest', 'walk'])],
        '은하역에서 친구를 만났다는 이야기는 작화이고, 정자에서 쉰다는 말과 혼자 귀가한 경위도 본인 진술이라 순서조차 일정하지 않다. '
        '딸이 직접 본 것은 숨이 찰 만큼 지치면 앉지 않고 계속 걷는 반응과, 길이 낯설면 길가에 주저앉는 반응이다. '
        '주저앉은 두 번은 기운이 있을 때라 지쳤을 때 둘이 겹치면 어느 쪽인지 정해지지 않는다. '
        '비슷한 얼굴을 따라가는 모습은 관찰됐지만 엔진에 표현할 수 없다.',
        ['본인 진술(정자 휴식, 역 방문, 귀가 경위)로 휴식이나 역행 출발을 만들지 않는다',
         '지치기 전에는 개인 반응 없이 두고, 지친 뒤 계속 걷는 직접 관찰을 휴식 규칙으로 뒤집지 않는다',
         '지침과 길 낯섦이 겹치면 우선순위를 지어내지 않는다',
         '사람 따라가기는 표현 불가 특성으로 남긴다'],
        unsupported_sentences=('N6.s1', 'N6.s2'))

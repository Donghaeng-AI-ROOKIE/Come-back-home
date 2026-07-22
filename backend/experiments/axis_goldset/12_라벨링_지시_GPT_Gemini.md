# GPT · Gemini 라벨링 지시서 (복붙용)

## 사용법 (여러분이 할 일)

1. 아래 `=== 프롬프트 시작 ===` ~ `=== 프롬프트 끝 ===` 사이 전체를 복사
2. **GPT**에 새 대화로 붙여넣기 → 나온 답표를 `12_정답표_GPT.md`로 저장
3. **Gemini**에 새 대화로 붙여넣기 → 나온 답표를 `13_정답표_Gemini.md`로 저장
4. (Claude 답표 = `11_정답표_v1.md`는 이미 있음)
5. `eval_axis_goldset.py`가 세 답표를 합쳐 ≥2/3 합의로 정답 확정 + EXAONE과 비교

> 출력 형식을 `11_정답표_v1.md`와 똑같이 맞춰놨으니 세 파일을 나란히 병합할 수 있다.
> 모델이 형식을 어기면 "형식만 다시" 요청. temperature 조절이 가능하면 0으로.

---

=== 프롬프트 시작 ===

너는 실종 위험 프로파일 채점자다. 아래 대상자들의 축별 근거 발화를 보고, 각 축을
기준표의 A~F 중 하나로 분류한다.

# 규칙
- 축 **하나씩 독립적으로** 판정한다. 다른 축 정보를 그 축 판정에 끌어오지 않는다.
- choice: A~E 중 하나. 그 축을 판정할 근거가 부족하면 F(판정 불가).
- 근거 발화에 없는 사실을 추측·창작하지 않는다.
- 여러 단계 근거가 공존하면 발견·구조를 더 어렵게 만드는 쪽(E에 가까운 쪽)을 고른다.
  단, '이동 능력' 축은 반대로 실제 확인된 최고 수준으로 고른다.
- quote는 판정 근거가 된 발화를 그대로 옮긴다. F면 빈칸.

# 축 방향 (E쪽이 뜻하는 것)
- mobility_transport_capacity: 이동 능력 큼 (수색 반경 확장 — 위험 아님)
- hazard_awareness_vulnerability: 위험 인식 낮음 (취약)
- communication_approach_vulnerability: 발견·구조 어려움 (취약)
- wayfinding_error_recovery_deficit: 길찾기·복귀 손상 심함 (취약)
- autobiographical_destination_pull: 과거 장소 지향이 실종과 반복 연결 (강함)
- distress_induced_movement_reactivity: 불안이 실제 이탈로 전환됨 (강함)
- preferred_target_seeking: 선호 대상이 실종과 반복 연결 (강함)
- aversive_context_escape: 회피가 실제 이탈로 전환됨 (강함)
- transition_routine_disruption: 전환 상황이 실종과 반복 연결 (취약)
- elopement_pattern_consistency: 이탈 패턴 고착 (개인화 가중 — 위험 크기보다 예측력)

# 기준표 (A=0.1 / B=0.3 / C=0.5 / D=0.7 / E=0.9)

## mobility_transport_capacity
A 혼자 걷기 어렵거나 실내에서 매우 짧은 거리만 이동 가능
B 집 주변 짧은 거리만, 장시간 보행·교통수단 이용은 어려움
C 생활권 내 30분~1시간 혼자 보행, 대중교통은 혼자 어려움
D 장시간 보행 가능하거나 익숙한 버스·지하철을 혼자 이용
E 장거리·여러 교통수단 이용 가능, 실제로 멀리 이동한 경험 있음

## hazard_awareness_vulnerability
A 차도·신호·물가·계단 등 위험을 스스로 인식하고 대부분 회피
B 기본 위험은 인식하나 낯선 환경·복잡한 상황에선 판단 불안정
C 위험을 일부 인식하나 반복 안내·보호자 확인이 필요
D 차도·물가·추락 위험을 제대로 인식 못하고 위험구역 진입 가능성 높음
E 위험을 거의 인식 못하며 교통사고·익사·추락 등 실제 사고 또는 중대한 위험 경험 있음

## communication_approach_vulnerability
A 이름·신원(소속 기관명 포함)을 말하고 시민·경찰 질문에 응답, 도움 받을 수 있음
B 이름 부르면 반응·간단한 대화는 가능하나 주소·연락처 설명은 어려움
C 이름 반응·의사소통이 일관되지 않고 낯선 사람 도움 받을지 불확실
D 질문에 거의 응답 못하고 낯선 접근 시 무시·회피·멈춤·도주
E 신원·도움 요청 불가, 접근 시 강한 도주·방어로 위험이 커짐

## wayfinding_error_recovery_deficit
A 익숙한 경로·목적지를 기억하고 잘못 들어가도 스스로 돌아옴
B 낯선 장소에서만 혼동하며 안내·표지판으로 경로 회복
C 익숙한 생활권에서도 가끔 목적지·방향 혼동, 간단한 도움 필요
D 익숙한 동네에서도 자주 길을 잃고 스스로 복구 어려움
E 위치·목적지·방향을 거의 유지 못하고 스스로 복구가 사실상 불가능

## autobiographical_destination_pull
A 과거 장소를 찾거나 언급하는 행동이 거의 없음
B 과거 장소를 가끔 이야기하지만 실제로 찾아가려는 행동은 없음
C 특정 과거 장소에 가야 한다는 말을 반복하거나 그 방향으로 이동하려 한 적 있음
D 옛집·직장·시장·병원 등 특정 기억 장소를 반복적으로 찾거나 혼자 이동하려 함
E 과거 실종에서 동일 기억 장소·주변에서 발견된 경험이 있거나 같은 장소로 반복 이동

## distress_induced_movement_reactivity
A 불안·초조·의심이 나타나도 이동 행동엔 거의 변화 없음
B 불편을 표현하거나 안절부절못하지만 장소를 벗어나진 않음
C 불안·의심 시 걷기 증가·자리 이동·출입구 접근이 가끔 나타남
D 불안·초조·망상 상황에서 도주·숨기·반복보행·외출 시도 등 뚜렷한 이동 변화
E 불안·망상·공포로 실제 이탈·실종이 발생했거나 같은 반응이 반복 확인됨

## preferred_target_seeking
A 선호 대상 때문에 이동 방향을 바꾼 적이 거의 없음 (관련 이력 자체가 없으면 F)
B 관심을 보이지만 보호자 범위를 벗어나지는 않음
C 선호 대상으로 이동하거나 보호자와 분리된 경험이 있음
D 특정 대상을 향해 반복적으로 이탈함
E 실제 실종이 동일한 선호 대상과 반복적으로 연결됨

## aversive_context_escape
A 불편 자극·상황이 이동에 거의 영향을 주지 않음 (관련 이력 자체가 없으면 F)
B 불편을 표현하지만 장소를 벗어나지는 않음
C 특정 상황에서 자리를 피하거나 이동함
D 불편 상황에서 실제로 보호자 범위를 벗어난 적이 1회 있음
E 같은 회피 상황에서 실제 이탈이 2회 이상 반복됨

## transition_routine_disruption
A 일정·장소 변화에 비교적 잘 적응 (관련 이력 자체가 없으면 F)
B 변화 시 불안하지만 이동 통제가 가능
C 전환 상황에서 멈춤·거부·되돌아감이 발생
D 루틴 변화 시 보호자와 분리되거나 이탈한 적이 1회 있음
E 특정 전환 상황에서 실종·이탈이 2회 이상 반복됨

## elopement_pattern_consistency
A 이탈 장소·계기·경로가 매번 다름 (관련 이력 자체가 없으면 F)
B 일부 유사한 행동이 있으나 일관성이 낮음
C 비슷한 장소나 계기가 반복됨
D 동일한 목적지·경로·행동이 여러 번 반복됨
E 실제 실종에서 거의 동일한 패턴이 반복적으로 확인됨

# 채점 대상 (축: 근거 발화)

## D1 (치매, 74세)
mobility_transport_capacity: 매일 약수터까지 왕복 한 시간 넘게 걷고, 시내버스도 노선 아시는 건 혼자 타세요
hazard_awareness_vulnerability: 신호랑 횡단보도는 꼬박꼬박 지키시고 물가나 공사장은 알아서 피하세요
communication_approach_vulnerability: 성함이랑 동네 잘 말씀하시고 경찰이 물어보면 아들 전화번호도 대세요
wayfinding_error_recovery_deficit: 낯선 데서만 가끔 헷갈리시는데 표지판 보고 알아서 돌아오세요
autobiographical_destination_pull: 옛날 얘기를 하시긴 해도 거길 찾아가려 하신 적은 없어요
distress_induced_movement_reactivity: 좀 답답해하셔도 자리를 뜨거나 나가시진 않아요

## D2 (치매, 82세)
mobility_transport_capacity: 부축 없이는 몇 걸음 못 걸으시고 집 안에서만 조금 움직이세요
hazard_awareness_vulnerability: 차도로 그냥 내려가시고 예전에 도로에서 교통사고 날 뻔한 적도 있어요
communication_approach_vulnerability: 성함도 못 대시고 모르는 사람이 다가오면 소리 지르고 뿌리치며 도망가려 하세요
wayfinding_error_recovery_deficit: 집 앞에서도 방향을 못 잡으시고 스스로 돌아오는 건 이제 불가능해요
autobiographical_destination_pull: 돌아가신 옛집에 가야 한다며 몇 번이나 나가셨고 지난 실종 때도 옛집 골목에서 찾았어요
distress_induced_movement_reactivity: 밤에 무섭다며 뛰쳐나가신 적이 있고 그렇게 나가서 실종된 적도 있어요

## D3 (치매, 70세)
mobility_transport_capacity: 아직 정정하셔서 지하철 두세 번 갈아타고 딸네까지 혼자 다녀오세요
hazard_awareness_vulnerability: 요즘 신호를 놓치실 때가 있어서 큰길에선 옆에서 봐야 해요
communication_approach_vulnerability: 성함은 대시는데 주소나 전화번호까지는 설명을 잘 못 하세요
wayfinding_error_recovery_deficit: 익숙한 동네에서도 가끔 방향을 헷갈려 하시는데 사람들 도움 받으면 돌아오세요
autobiographical_destination_pull: 그런 말씀은 거의 없으세요
distress_induced_movement_reactivity: 불안해하시긴 해도 그것 때문에 나가시진 않아요

## D4 (치매, 77세)
mobility_transport_capacity: 다리가 약하셔서 집 앞 골목 정도만 겨우 걸으시고 버스는 못 타세요
hazard_awareness_vulnerability: 기본적인 건 아시는데 복잡한 데선 판단이 흔들리세요
communication_approach_vulnerability: 이름 부르면 반응하시고 간단한 얘긴 하시는데 연락처 설명은 어려워요
wayfinding_error_recovery_deficit: 낯선 데선 헷갈리시지만 안내 받으면 돌아오세요
autobiographical_destination_pull: 매일같이 친정 가야 한다며 그쪽으로 나가려 하시고, 예전에 친정 동네에서 발견된 적도 있어요
distress_induced_movement_reactivity: 답답할 때 서성이긴 하는데 크게 벗어나진 않아요

## D5 (치매, 79세)
mobility_transport_capacity: 동네 안에서 30분쯤은 혼자 걸으시는데 버스는 혼자 못 타세요
hazard_awareness_vulnerability: 위험한 걸 일부는 아시는데 늘 옆에서 확인해줘야 해요
communication_approach_vulnerability: 이름 반응이 일관되지 않고 낯선 사람 도움을 받을지 잘 모르겠어요
wayfinding_error_recovery_deficit: 익숙한 데서도 가끔 목적지를 헷갈려 하셔서 간단한 도움이 필요해요
autobiographical_destination_pull: 가끔 시장 가야 한다고 그 방향으로 가시려 한 적은 있어요
distress_induced_movement_reactivity: 불안하면 걷기가 늘고 출입구 쪽으로 가실 때가 가끔 있어요

## P1 (발달장애, 19세)
mobility_transport_capacity: 익숙한 버스는 혼자 타고 복지관까지 잘 다녀와요
hazard_awareness_vulnerability: 신호랑 횡단보도 잘 지키고 위험한 데는 알아서 피해요
communication_approach_vulnerability: 이름이랑 다니는 복지관 이름 말하고 도움도 받을 수 있어요
preferred_target_seeking: 좋아하는 건 있어도 그거 따라 어디 가버린 적은 없어요
aversive_context_escape: 시끄러우면 싫어하지만 자리를 벗어나진 않아요
transition_routine_disruption: 조금 당황해도 금방 적응하는 편이에요
elopement_pattern_consistency: 벗어난 적이 거의 없어서 딱히 패턴이랄 게 없어요

## P2 (발달장애, 23세)
mobility_transport_capacity: 혼자선 집 앞 정도만 가능하고 길게는 못 걸어요
hazard_awareness_vulnerability: 차도로 뛰어든 적이 있고 물가도 위험한 줄 몰라요
communication_approach_vulnerability: 이름도 못 말하고 다가오면 밀치고 도망가요
preferred_target_seeking: 기차만 보면 무조건 따라가고 실종될 때마다 기차역에서 찾아요
aversive_context_escape: 큰 소리 나면 그 자리에서 뛰쳐나가 없어진 적이 여러 번이에요
transition_routine_disruption: 갑자기 바뀌면 주저앉거나 반대로 확 나가버려서 몇 번 잃어버렸어요
elopement_pattern_consistency: 나갈 때마다 거의 같은 길로 같은 기차역에 가 있어요

## P3 (발달장애, 17세)
mobility_transport_capacity: 동네 안에서 30분 정도는 혼자 다니는데 대중교통은 혼자 못 타요
hazard_awareness_vulnerability: 위험한 건 일부 알지만 확인이 필요해요
communication_approach_vulnerability: 이름은 말하는데 자세한 설명은 어렵고 상황 봐야 해요
preferred_target_seeking: 게임 오락실만 보이면 무조건 그리로 가고 실종될 때마다 오락실에서 찾아요
aversive_context_escape: 싫은 소리 나도 자리를 벗어나진 않아요
transition_routine_disruption: 바뀌어도 불안해하는 정도지 통제는 돼요
elopement_pattern_consistency: 나가는 계기가 매번 달라서 일정하진 않아요

## P4 (발달장애, 21세)
mobility_transport_capacity: 익숙한 길은 혼자 걷는데 대중교통은 혼자 못 타요
hazard_awareness_vulnerability: 기본적인 위험은 아는데 낯선 데선 판단이 흔들려요
communication_approach_vulnerability: 이름 부르면 반응하는데 낯선 사람 도움 받을진 불확실해요
preferred_target_seeking: 좋아하는 게 있어도 그것 때문에 이탈한 적은 없어요
aversive_context_escape: 사람 많고 시끄러우면 그 자리를 못 견디고 뛰쳐나가 없어진 적이 두세 번 있어요
transition_routine_disruption: 바뀌면 불안해하는데 자리를 뜨진 않아요
elopement_pattern_consistency: 없어질 때마다 늘 같은 공원 같은 벤치에 가 있어요

## P5 (발달장애, 20세)
mobility_transport_capacity: 생활권 안에서 30분쯤 혼자 다니고 대중교통은 혼자 어려워요
hazard_awareness_vulnerability: 위험을 일부 알지만 반복해서 알려주고 확인해야 해요
communication_approach_vulnerability: 이름 반응이 일관되지 않고 도움을 받을지 불확실해요
preferred_target_seeking: 좋아하는 편의점 쪽으로 가려다 보호자랑 떨어진 적이 있어요
aversive_context_escape: 특정 상황에서 자리를 피하거나 이동한 적이 있어요
transition_routine_disruption: 전환 상황에서 멈춤·거부·되돌아감이 발생함
elopement_pattern_consistency: 비슷한 장소나 계기가 반복되는 편이에요

## DAL (치매, 76세)
mobility_transport_capacity: 동네 안에서 30분 정도 혼자 걷고 버스는 혼자 못 타세요
hazard_awareness_vulnerability: 일부는 아시는데 옆에서 확인해줘야 해요
communication_approach_vulnerability: 이름 반응이 들쭉날쭉하고 도움 받을지 불확실해요
wayfinding_error_recovery_deficit: 익숙한 데서도 가끔 목적지를 헷갈리셔서 도움이 필요해요
autobiographical_destination_pull: 옛날 얘기를 가끔 하시지만 거길 찾아가려 하신 적은 없어요
distress_induced_movement_reactivity: 불안하면 서성이는 정도고 크게 벗어나진 않아요

## DAH (치매, 76세)
mobility_transport_capacity: 동네 안에서 30분 정도 혼자 걷고 버스는 혼자 못 타세요
hazard_awareness_vulnerability: 일부는 아시는데 옆에서 확인해줘야 해요
communication_approach_vulnerability: 이름 반응이 들쭉날쭉하고 도움 받을지 불확실해요
wayfinding_error_recovery_deficit: 익숙한 데서도 가끔 목적지를 헷갈리셔서 도움이 필요해요
autobiographical_destination_pull: 옛집 있던 신수동에 가야 한다며 몇 번이나 혼자 나가셨고 지난 실종 때도 신수동에서 찾았어요
distress_induced_movement_reactivity: 불안하면 서성이는 정도고 크게 벗어나진 않아요

## PAL (발달장애, 18세)
mobility_transport_capacity: 생활권 안에서 30분쯤 혼자 다니고 대중교통은 혼자 어려워요
hazard_awareness_vulnerability: 위험을 일부 알지만 확인이 필요해요
communication_approach_vulnerability: 이름 반응이 일관되지 않고 도움 받을지 불확실해요
aversive_context_escape: 특정 상황에서 자리를 피하거나 이동한 적이 있어요
transition_routine_disruption: 전환 상황에서 멈추거나 거부하고 되돌아가려 해요
elopement_pattern_consistency: 비슷한 장소나 계기가 반복되는 편이에요
preferred_target_seeking: 좋아하는 게 있어도 그것 때문에 따라가 이탈한 적은 없어요

## PAH (발달장애, 18세)
mobility_transport_capacity: 생활권 안에서 30분쯤 혼자 다니고 대중교통은 혼자 어려워요
hazard_awareness_vulnerability: 위험을 일부 알지만 확인이 필요해요
communication_approach_vulnerability: 이름 반응이 일관되지 않고 도움 받을지 불확실해요
aversive_context_escape: 특정 상황에서 자리를 피하거나 이동한 적이 있어요
transition_routine_disruption: 전환 상황에서 멈추거나 거부하고 되돌아가려 해요
elopement_pattern_consistency: 비슷한 장소나 계기가 반복되는 편이에요
preferred_target_seeking: 놀이터만 보이면 무조건 그리로 달려가고 실종될 때마다 놀이터에서 찾아요

# 출력 형식 (이 형식만, 다른 말 없이)
각 대상자마다 아래처럼. CHOICE는 A~F, quote는 근거 발화(F면 빈칸).

## D1 (dementia)
mobility_transport_capacity: D | 매일 약수터까지 왕복 한 시간 넘게 걷고...
hazard_awareness_vulnerability: A | 신호랑 횡단보도는 꼬박꼬박...
...(그 대상자의 모든 축)

(대상자 14명: D1~D5, P1~P5, DAL, DAH, PAL, PAH. 치매는 6축, 발달장애는 7축.)

=== 프롬프트 끝 ===

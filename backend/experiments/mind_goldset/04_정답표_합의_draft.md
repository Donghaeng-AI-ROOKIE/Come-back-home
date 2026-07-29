# 마음 골드셋 v1 — 합의 초안 (2/2 판정자 자동 대조)

판정자: Gemini·GPT (버전 미기재 — 확정 시 기입). 합의 규칙 R1~R7 은 build_consensus.py 헤더.
⚖️ 표시는 판정자 불일치 = **3번째 판정자(사람) 결정 필요** 항목. 결정 전까지 골드셋 미확정.

## G01
- gold_persona.attractions:
  - ✅ 청량리 수산시장 [previous_missing_found]
- A_귀소: allowed=[null, 청량리 수산시장] forbidden=[] confusion=[0.5, 0.8]
  - R1 제거(비후보): ['이문동(집)']
  - relation(Gemini): 귀소 충동이 높으므로 집과 수산시장 모두 타당함
  - relation(GPT): 과거 2회 발견 이력이 있는 청량리 수산시장이 최우선이어야 한다.
- B_불안: allowed=[null, 청량리 수산시장] forbidden=[] confusion=[0.6, 0.9]
  - relation(Gemini): 불안 시 귀소 충동이 낮아지므로 과거 강한 발견 이력인 수산시장 배회 가능성 높음
  - relation(GPT): 불안 상황에서도 반복된 자전적 시장 지향과 발견 이력이 우선해야 한다.

## G02
- gold_persona.attractions:
  - ✅ 성당 [caregiver_report]
  - ✅ 옛 봉제공장 [mention_only]
- A_귀소: allowed=[null, 성당] forbidden=[옛 봉제공장] confusion=[0.45, 0.7]
  - R1 제거(비후보): ['화곡동(집)']
  - relation(Gemini): 성당 지향성이 강하며, 봉제공장은 언급만 되었으므로 배제
  - relation(GPT): 매일 다니는 성당이 언급만 된 옛 봉제공장보다 우선해야 한다.
- B_불안: allowed=[null, 성당] forbidden=[옛 봉제공장] confusion=[0.5, 0.85]
  - relation(Gemini): 불안 시 성당을 찾는다는 직접적 근거가 있으므로 성당이 최우선
  - relation(GPT): 불안하면 성당부터 찾는다는 직접 관찰이 목표 선택에 강하게 반영되어야 한다.

## G03
- gold_persona.attractions:
  - ✅ 기원 [caregiver_report]
  - ✅ 복지관 [caregiver_report]
- A_귀소: allowed=[null, 기원, 복지관] forbidden=[] confusion=[0.3, 0.5]
  - R1 제거(비후보): ['신림동(집)']
  - relation(Gemini): 복지관과 기원 중 특정 장소의 우열 없음
  - relation(GPT): 복지관과 기원 사이에 근거 없는 우열을 두지 않아야 한다.
- B_불안: allowed=[null, 기원, 복지관] forbidden=[] confusion=[0.4, 0.7]
  - relation(Gemini): 귀소 거부 시 일상 루틴인 복지관이나 기원 배회 타당
  - relation(GPT): 불안 상황에서도 두 일상 장소는 동등한 후보이며 null도 허용되어야 한다.

## G04
- gold_persona.attractions:
- A_귀소: allowed=[null] forbidden=[] confusion=[0.5, 0.85]
  - R1 제거(비후보): ['쌍문동(집)']
  - relation(Gemini): 정보 빈약으로 특정 장소 추정 불가, 귀소 또는 방향 유지(null)만 타당
  - relation(GPT): 근거가 있는 구체 목적지가 없으므로 null만 허용되어야 한다.
- B_불안: allowed=[null] forbidden=[] confusion=[0.6, 0.9]
  - relation(Gemini): 목표 장소에 대한 단서가 전혀 없으므로 null만 타당
  - relation(GPT): 불안이 높더라도 목적지 정보가 없으므로 특정 장소를 단정할 수 없다.

## G05
- gold_persona.attractions:
  - ✅ 2012번 버스 종점 [previous_missing_found]
  - ⚖️ 복지관 [caregiver_report] — GPT만 등재
- A_귀소: allowed=[2012번 버스 종점, null] forbidden=[] confusion=[0.3, 0.65]
  - R1 제거(비후보): ['행당동(집)']
  - relation(Gemini): previous_missing_found인 2012번 버스 종점이 최우선 고려 대상
  - relation(GPT): 반복 발견 이력이 있는 2012번 버스 종점이 일상 장소인 복지관보다 우선해야 한다.
- B_불안: allowed=[2012번 버스 종점, null] forbidden=[] confusion=[0.5, 0.75]
  - relation(Gemini): 불안 시에도 버스를 찾는 특성상 버스 종점 지향이 우세
  - relation(GPT): 불안만으로 반복적인 버스 지향과 종점 발견 이력을 뒤집지 않아야 한다.

## G06
- gold_persona.attractions:
  - ✅ 상가 지하계단 [previous_missing_found]
  - ✅ 아파트 지하주차장 [previous_missing_found]
  - ⚖️ 학교 [caregiver_report] — GPT만 등재
- A_귀소: allowed=[null, 상가 지하계단, 아파트 지하주차장] forbidden=[] confusion=[0.45, 0.8]
  - R1 제거(비후보): ['응암동(집)']
  - relation(Gemini): 소음 자극 시 즉시 은신처(지하)로 이동하는 패턴 반영 필요
  - relation(GPT): 지하주차장과 지하계단은 모두 발견 근거가 있으며 지하주차장이 빈도상 더 강하다.
- B_불안: allowed=[null, 상가 지하계단, 아파트 지하주차장] forbidden=[] confusion=[0.6, 0.9]
  - relation(Gemini): 불안 상황에서 감각 회피를 위한 지하 공간 은신이 최우선 목표
  - relation(GPT): 불안 상황에서는 반복적으로 숨었던 조용하고 어두운 지하 공간 지향이 타당하다.

## G07
- gold_persona.attractions:
  - ✅ 놀이터 앞 벤치 [caregiver_report]
  - ✅ 집 앞 편의점 [caregiver_report]
- A_귀소: allowed=[null, 놀이터 앞 벤치, 집 앞 편의점] forbidden=[] confusion=[0.25, 0.5]
  - R1 제거(비후보): ['상도동(집)']
  - relation(Gemini): 특정 목적지가 없는 단순 배회
  - relation(GPT): 두 일상 장소는 동등한 후보이며 목적 없는 이동을 반영해 null도 유지해야 한다.
- B_불안: allowed=[null, 놀이터 앞 벤치, 집 앞 편의점] forbidden=[] confusion=[0.4, 0.7]
  - relation(Gemini): 목적 없는 배회 중 일상 루틴 장소에 머무를 가능성
  - relation(GPT): 불안 상황에서도 특정 장소를 확정하지 말고 두 장소와 null을 모두 허용해야 한다.

## G08
- gold_persona.attractions:
- A_귀소: allowed=[null] forbidden=[] confusion=[0.4, 0.8]
  - R1 제거(비후보): ['상계동 그룹홈']
  - relation(Gemini): 정보가 없어 그룹홈 귀소 또는 주변 산책(null)만 타당
  - relation(GPT): 근거가 있는 목적지가 없으므로 null만 허용되어야 한다.
- B_불안: allowed=[null] forbidden=[] confusion=[0.6, 0.85]
  - relation(Gemini): 알려진 목표가 없으므로 null 유지
  - relation(GPT): 불안이 높더라도 확인되지 않은 목적지나 회피 행동을 단정할 수 없다.

## G09
- gold_persona.attractions:
  - ✅ 경로당 [caregiver_report]
  - ⚖️ 김포 정미소 자리 — evidence 불일치: Gemini=previous_missing_found / GPT=caregiver_report
- A_귀소: allowed=[null, 경로당, 김포 정미소 자리] forbidden=[] confusion=[0.45, 0.8]
  - R1 제거(비후보): ['망원동(집)']
  - relation(Gemini): 김포 정미소 > 경로당 (대조쌍 강 케이스)
  - relation(GPT): 김포 정미소 선택은 G10보다 뚜렷하게 우세하고 경로당보다 강해야 한다.
- B_불안: allowed=[null, 김포 정미소 자리] forbidden=[] confusion=[0.6, 0.9]
  - relation(Gemini): 불안 및 배회 충동 시 가장 강력한 자전적 장소인 김포로 이동 시도
  - relation(GPT): 불안 시 외출 반응과 반복된 자전적 목적지 지향이 결합되어 김포 정미소가 우세해야 한다.

## G10
- gold_persona.attractions:
  - ✅ 경로당 [caregiver_report]
  - ✅ 김포 정미소 자리 [mention_only]
- A_귀소: allowed=[null, 경로당] forbidden=[김포 정미소 자리] confusion=[0.45, 0.7]
  - R1 제거(비후보): ['망원동(집)']
  - relation(Gemini): 대조쌍 약 케이스; 김포 정미소는 언급에 불과해 행동 목표로 설정 불가
  - relation(GPT): 경로당이 언급만 된 김포 정미소보다 우선하며 정미소 선택은 G09보다 현저히 약해야 한다.
- B_불안: allowed=[null, 경로당] forbidden=[김포 정미소 자리] confusion=[0.55, 0.9]
  - relation(Gemini): 일상 루틴인 경로당 주변 배회 가능, 김포 정미소는 배제
  - relation(GPT): 불안 시 외출 가능성은 높지만 목적지가 김포 정미소라고 연결해서는 안 된다.

## G11
- gold_persona.attractions:
  - ⚖️ 한강 산책로(강변 벤치) — evidence 불일치: Gemini=caregiver_report / GPT=previous_missing_found
- A_귀소: allowed=[null, 한강 산책로(강변 벤치)] forbidden=[] confusion=[0.45, 0.8]
  - R1 제거(비후보): ['자양동(집)']
  - relation(Gemini): 강변 및 물가로의 이동이 최우선 서사
  - relation(GPT): 반복된 물가 접근과 실제 발견 이력이 있는 한강 산책로가 우선해야 한다.
- B_불안: allowed=[null, 한강 산책로(강변 벤치)] forbidden=[] confusion=[0.6, 0.85]
  - relation(Gemini): 불안 시 심리적 안정을 주는 물가(강변)로 향할 확률이 극대화
  - relation(GPT): 물을 보면 편안함을 느낀다는 성향과 발견 이력 때문에 물가 방향이 유력해야 한다.

## G12
- gold_persona.attractions:
  - ⚖️ 을지로 인쇄소 — evidence 불일치: Gemini=previous_missing_found / GPT=caregiver_report
  - ⚖️ 지하철역 입구 [previous_missing_found] — Gemini만 등재
  - ⚖️ 큰길 버스정류장 [previous_missing_found] — Gemini만 등재
- A_귀소: allowed=[null, 을지로 인쇄소] forbidden=[] confusion=[0.5, 0.8]
  - R1 제거(비후보): ['길음동(집)']
  - relation(Gemini): 야간 배회 및 을지로 출근이라는 자전적 서사가 지배적임
  - relation(GPT): 야간이라는 맥락이 적용될 때 과거 직장인 을지로 인쇄소 방향이 우세해야 한다.
- B_불안: allowed=[null, 을지로 인쇄소] forbidden=[] confusion=[0.7, 0.9]
  - relation(Gemini): 불안하면 무조건 집 밖으로 나가 을지로 방향 교통수단을 찾음
  - relation(GPT): 불안 시 현관으로 향하는 반응과 야간 출근 서사가 결합되어 을지로 방향 이동이 강해져야 한다.

## G13
- gold_persona.attractions:
  - ✅ 면목시장 [caregiver_report]
  - ⚖️ 친정 [mention_only] — Gemini만 등재
- A_귀소: allowed=[null, 면목시장] forbidden=[] confusion=[0.4, 0.8]
  - R1 제거(비후보): ['면목동(집)']
  - relation(Gemini): 친정은 구체성이 전혀 없으므로 면목시장 배회만이 타당
  - relation(GPT): 유일하게 확인된 구체 장소인 면목시장과 null만 근거 있는 후보로 남겨야 한다.
- B_불안: allowed=[null, 면목시장] forbidden=[] confusion=[0.6, 0.85]
  - relation(Gemini): 정보 혼선이 있으나 언급된 루틴인 면목시장이 유일한 대안
  - relation(GPT): 불안 시 행동 정보가 없으므로 면목시장을 확정하지 말고 null을 함께 허용해야 한다.

## G14
- gold_persona.attractions:
  - ⚖️ 106번 버스 정류장 [previous_missing_found] — Gemini만 등재
  - ✅ 청량리 경동시장 [caregiver_report]
- A_귀소: allowed=[null, 청량리 경동시장] forbidden=[] confusion=[0.4, 0.7]
  - R1 제거(비후보): ['수유동(집)']
  - relation(Gemini): 원거리 연고지인 경동시장으로 가기 위한 정류장 접근이 주요 패턴
  - relation(GPT): 반복 언급과 실제 버스 탑승 시도가 뒷받침하는 경동시장이 우선해야 한다.
- B_불안: allowed=[null, 청량리 경동시장] forbidden=[] confusion=[0.6, 0.8]
  - relation(Gemini): 대중교통을 이용하려는 습관에 따라 정류장 대기/탑승 위험 높음
  - relation(GPT): 불안 상황에서도 평생의 단골 장소와 버스 이용 습관이 경동시장 지향을 지지해야 한다.

## G15
- gold_persona.attractions:
  - ⚖️ 치료실 [caregiver_report] — GPT만 등재
  - ⚖️ 학교 [caregiver_report] — GPT만 등재
  - ✅ 현대백화점 에스컬레이터 [previous_missing_found]
- A_귀소: allowed=[null, 치료실, 학교, 현대백화점 에스컬레이터] forbidden=[] confusion=[0.25, 0.6]
  - R1 제거(비후보): ['목동(집)']
  - relation(Gemini): 현대백화점 에스컬레이터 > 기타 일상 루틴 장소 (대조쌍 강 케이스)
  - relation(GPT): 현대백화점 에스컬레이터 선택은 G16보다 현저히 강하고 일상 장소보다 우선해야 한다.
- B_불안: allowed=[null, 현대백화점 에스컬레이터] forbidden=[] confusion=[0.5, 0.7]
  - relation(Gemini): 불안 시 강한 선호 대상인 백화점 에스컬레이터로 향할 가능성 매우 높음
  - relation(GPT): 불안 상황에서도 반복 발견 이력이 있는 에스컬레이터 지향이 G16보다 강해야 한다.

## G16
- gold_persona.attractions:
  - ⚖️ 치료실 [caregiver_report] — GPT만 등재
  - ⚖️ 학교 [caregiver_report] — GPT만 등재
  - ⚖️ 현대백화점 에스컬레이터 [mention_only] — Gemini만 등재
- A_귀소: allowed=[null, 치료실, 학교] forbidden=[현대백화점 에스컬레이터] confusion=[0.25, 0.5]
  - R1 제거(비후보): ['목동(집)']
  - relation(Gemini): 대조쌍 약 케이스; 백화점은 찾아가지 않는다고 명시되었으므로 목표에서 배제
  - relation(GPT): 에스컬레이터 목표 선택은 G15보다 현저히 약해야 하며 확인된 일상 장소와 null이 우선해야 한다.
- B_불안: allowed=[null, 치료실, 학교] forbidden=[현대백화점 에스컬레이터] confusion=[0.4, 0.7]
  - relation(Gemini): 이탈보다는 제자리 불안을 보일 가능성이 높음
  - relation(GPT): 불안이 높아도 약한 에스컬레이터 선호를 구체 목적지 지향으로 승격해서는 안 된다.

## G17
- gold_persona.attractions:
  - ⚖️ 복지관 [caregiver_report] — GPT만 등재
  - ✅ 석촌호수 분수대 [previous_missing_found]
  - ⚖️ 학교 [caregiver_report] — GPT만 등재
- A_귀소: allowed=[null, 석촌호수 분수대] forbidden=[] confusion=[0.35, 0.7]
  - R1 제거(비후보): ['잠실동(집)']
  - relation(Gemini): 석촌호수에 대한 강한 이끌림이 귀소 충동과 경합
  - relation(GPT): 강한 물 선호와 발견 이력이 있는 석촌호수 분수대가 일상 장소보다 우선해야 한다.
- B_불안: allowed=[null, 석촌호수 분수대] forbidden=[] confusion=[0.6, 0.8]
  - relation(Gemini): 물가(석촌호수)로 이동할 가능성이 매우 높으며 수난 사고 위험 매우 심각함
  - relation(GPT): 불안 상황에서도 반복된 물 지향과 석촌호수 발견 이력이 가장 강한 목표 근거다.

## G18
- gold_persona.attractions:
  - ✅ 예전 등굣길 [previous_missing_found]
- A_귀소: allowed=[null, 예전 등굣길] forbidden=[] confusion=[0.4, 0.65]
  - R1 제거(비후보): ['개봉동(집)']
  - relation(Gemini): 루틴이 깨졌을 때 옛 루틴(옛 등굣길)을 복원하려는 시도 타당
  - relation(GPT): 높은 귀소 충동에서는 익숙한 귀가 루틴과 과거 발견된 예전 등굣길이 유력해야 한다.
- B_불안: allowed=[null, 예전 등굣길] forbidden=[] confusion=[0.6, 0.8]
  - relation(Gemini): 불안 시 혼자 배회하며 과거 익숙했던 옛 등굣길로 향할 가능성
  - relation(GPT): 불안 상황에서는 루틴 붕괴 뒤 익숙한 길을 복원하려는 이동이 강하게 반영되어야 한다.

## G19
- gold_persona.attractions:
  - ⚖️ PC방 [mention_only] — Gemini만 등재
- A_귀소: allowed=[null] forbidden=[PC방] confusion=[0.5, 0.8]
  - R1 제거(비후보): ['독산동(집)']
  - relation(Gemini): 정보 부족으로 귀소나 방향 유지(null) 외의 목적지 추정 불가
  - relation(GPT): 게임 선호만으로 PC방이라는 구체 목적지를 생성해서는 안 되며 null만 허용되어야 한다.
- B_불안: allowed=[null] forbidden=[PC방] confusion=[0.6, 0.85]
  - relation(Gemini): 알려진 명확한 장소가 없으므로 무목적 배회(null) 타당
  - relation(GPT): 불안이 높더라도 확인되지 않은 PC방이나 다른 구체 장소를 목표로 단정할 수 없다.

## G20
- gold_persona.attractions:
  - ✅ 무악재역 [previous_missing_found]
  - ✅ 문구점 [caregiver_report]
  - ✅ 홍제역 [previous_missing_found]
- A_귀소: allowed=[null, 무악재역, 문구점, 홍제역] forbidden=[] confusion=[0.3, 0.6]
  - R1 제거(비후보): ['홍은동(집)']
  - relation(Gemini): 강한 고착인 홍제역/무악재역 > 약한 고착인 문구점
  - relation(GPT): 홍제역과 무악재역은 서로 우열을 단정하지 않되 두 역 모두 문구점보다 우선해야 한다.
- B_불안: allowed=[null, 무악재역, 홍제역] forbidden=[] confusion=[0.5, 0.7] ⚖️ 충돌: [문구점] (한쪽 allowed·다른쪽 forbidden)
  - relation(Gemini): 불안 시 강한 고착 대상인 지하철역으로 이동, 약한 고착인 문구점 배제
  - relation(GPT): 불안 상황에서도 반복 발견 이력이 있는 두 지하철역이 약한 문구점 방문보다 우세해야 한다.

---
## 집계: 자동 합의 필드 60 · ⚖️ 사람 결정 필요 18

### ⚖️ 결정 필요 목록
- G05 attractions/복지관: GPT만 등재
- G06 attractions/학교: GPT만 등재
- G09 attractions/김포 정미소 자리: evidence previous_missing_found vs caregiver_report
- G11 attractions/한강 산책로(강변 벤치): evidence caregiver_report vs previous_missing_found
- G12 attractions/을지로 인쇄소: evidence previous_missing_found vs caregiver_report
- G12 attractions/지하철역 입구: Gemini만 등재
- G12 attractions/큰길 버스정류장: Gemini만 등재
- G13 attractions/친정: Gemini만 등재
- G14 attractions/106번 버스 정류장: Gemini만 등재
- G15 attractions/치료실: GPT만 등재
- G15 attractions/학교: GPT만 등재
- G16 attractions/치료실: GPT만 등재
- G16 attractions/학교: GPT만 등재
- G16 attractions/현대백화점 에스컬레이터: Gemini만 등재
- G17 attractions/복지관: GPT만 등재
- G17 attractions/학교: GPT만 등재
- G19 attractions/PC방: Gemini만 등재
- G20 B_불안: allowed/forbidden 충돌 [문구점]
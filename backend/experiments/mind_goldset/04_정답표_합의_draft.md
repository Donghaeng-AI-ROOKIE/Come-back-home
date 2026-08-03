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


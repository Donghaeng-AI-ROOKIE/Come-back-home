# 온보딩 → 마음 판단 → 연속 보행 통합 진단

이 폴더의 상태: **1차 연구 실행기와 당시 검증 자료. 이 실행기를 제품 `run_prediction`에 연결하거나 배포하지 않음.**

같은 날 이어진 조건 해석 후보와 제품 함수 연결 검증은
[2차 결과](../mind_policy_candidates/evidence_20261004/완성검증_결과.md)에 있다.
아래의 “다음 완료 조건”과 181개 테스트는 1차 종료 시점의 기록이다.
두 단계의 차이와 현재 판정은 [통합 안내](../mind_policy_candidates/REVIEW_GUIDE.md)를 먼저 읽는다.

[사람이 읽는 결과 보고서](evidence_20261004/통합검증_결과.md)와
[모델 공개 응답 대조](evidence_20261004/모델_공개응답_대조.md)에
개인 원문, 선택된 행동, 실제 경로, 실패·유보의 이유를 정리했다.

## 이번 변경

- `mind_upgrade/runtime.py`: 저장된 개인 투영 적용, 경로 익숙함의 실제 게이지 소비,
  시각이 보존된 최신 관측 유지, 보행/휴식/대기 분리, 즉시 역방향 전환 가중치,
  유보 이후 가짜 시간 진행 방지.
- `bridge.py`: 완전히 같은 모델 요청만 캐시. 변경된 시간·조건에 이전 답을
  재사용하지 않으며, 미해결 워커를 제자리에 남겨 확률을 꾸미지 않음.
- `test_mind_closed_loop.py`: 개인 특성 전달과 소비, 관측 보존, 시간 및 질량
  보존의 회귀 검사. 입력 형식만 확인하는 검사가 아님.
- 온보딩 집 위치의 지역 필터 결과가 실제 저장 좌표에 반영되도록 수정.

## 증거의 범위

8명의 합성 보호자 원문에 대해 이전에 저장된 K 개인 해석을 재사용했다.
초기 진단 25회, 연속 실험 58회, 마지막 관측 복구 확인 1회로 K API 총 84회다.
요청 시작/종료 84쌍 모두 원장에 기록했으며 비용·지원 차수는 미확인이다.
실제 환자와 실제 실종 경로 정답은 없다. 128개 고정 명령 경로는 엔진 검사다.

`final_loop`의 8명 실행은 최신 관측 보존 및 익숙함 소비 수정 **전** 코드다.
정확히 실행된 소스는 `code_at_final_loop_launch/`와 해시로 보존했다.
관측 보존 수정의 실호출은 `repair_check`의 동일 장면 1회에 한정된다.
최신 코드 전체를 8명×6시간으로 다시 검증했다고 해석하지 않는다.

코드 회귀 181개 통과, 마지막 캐시 기록 수정 뒤 영향받는 10개 추가 재실행 통과.
6시간 완료 수나 JSON 통과 수를 개인 행동 정확도로 제시하지 않는다.

## 오프라인 회귀 실행

backend에서 기존 개발 환경으로 다음을 실행한다. KINTEX 지도 fixture가 없으면
공간 검사는 명시적으로 skip하며 다른 지도나 격자로 대체하지 않는다.

```sh
python -m pytest -q tests/test_mind_closed_loop.py tests/test_mind_upgrade.py tests/test_mind_person_handoff.py tests/test_mind_action_decision.py tests/test_initial_behavior_injection.py tests/test_person_evidence_projection.py tests/test_environment_conditions.py tests/test_gauges.py tests/test_pipeline_combine.py tests/test_pipeline_roadnet.py tests/test_home_disambiguation.py tests/test_home_validation.py tests/test_interview_correction.py tests/test_phase0_persona_api.py
```

증거 폴더의 요청 JSON과 실행 시점 소스는 감사·대조 자료다. 과거 API 실행기를
자동 실행하거나 새 예산으로 재호출하지 않는다. 원격 키·Authorization·모델의
비공개 추론은 포함하지 않았다.

## 다음 완료 조건

1. 목적지의 물리적 도달과 본인의 인식을 구분하고, 도착 후 행동을 원문 근거와
   모순 없이 결정할 것. 문헌·기존 엔진의 인식 처리도 누락 없이 검토할 것.
2. 정보 부족 시 개인 제약을 보존한 후속 가능성을 계산할 것. 모델 유보를
   멈춤으로 바꾸거나 성공 경로만 재정규화하지 않을 것.
3. 연속 시뮬레이션의 시간별 상태와 기존 발견거리 통계/물리 한계를 함께 검증할 것.
4. 예산 소진과 의미 오류를 구분하고, 조건이 바뀐 뒤 오래된 응답을 재사용하지 않을 것.
5. 이번 개발 사례 밖에서 여러 표현·사람·경로 seed를 검증한 뒤 운영 연결을 결정할 것.

지도: © OpenStreetMap contributors, ODbL. 실제 KINTEX 보행망에 합성 장소와
관측을 넣은 시험이며 실제 소음·혼잡 또는 부스 실내 경로를 뜻하지 않는다.

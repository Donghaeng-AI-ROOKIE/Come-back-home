# 행동 LoRA 학습 인계 조건 (민아용, v4 기준)

데이터 파일 두 개만이 아니라 아래 조건이 같이 지켜져야 학습-서빙이 정렬된다.

## 데이터

- 학습: `dataset/train_first_person.jsonl` (2,380행) — **이것만 학습에 사용**
- 검증(loss 감시): `dataset/val_first_person.jsonl` (298행 — 별도 논문 4종:
  치매 2·발달 2, 행동 4종 전부 포함)
- `train_analyst.jsonl`/`val_analyst.jsonl` 은 대조 실험용 — 기본 계획에서는 미사용
- 행의 최상위 `metadata` 필드는 학습 입력에 넣지 않는다. `messages` 만 사용.

## 학습 설정

- base 모델: 지금 서버에 `exaone-base` 로 서빙 중인 것과 **동일 가중치** 위에
  LoRA 어댑터 (sar 학습 때와 같은 파이프라인). 다른 체크포인트 금지 —
  서빙 모델과 다르면 어댑터가 안 맞는다.
- `messages` 에 모델 공식 chat template 적용.
- **loss 는 assistant 답변 토큰에만** (system·user 토큰 마스킹).
- 산출 어댑터 이름 제안: `exaone-mind` (prior 용 sar, 축 채점용 base 와 구분).

## 서빙 전제 (중요)

이 데이터는 **1인칭 v2 프롬프트·출력 계약**으로 만들어졌다:
- 시스템·입력 = `experiments/mind_goldset/first_person.py` 의 v2 빌더 출력과 동일
- 출력 = `{inner, status, confusion_level, behavior(4종), goal_label}`

따라서 어댑터를 운영에 꽂으려면 마음 재해석 경로가 같은 프롬프트·파서로
전환돼야 한다 (현재 운영 기본은 분석가형 v1 — 전환 PR은 별도 예정).
**분석가형 프롬프트로 이 어댑터를 호출하면 학습-서빙 형식이 다시 어긋난다.**

## 평가 (학습 후)

- 개발 중 평가는 골드셋 **dev G01~G08 만** (`experiments/mind_goldset/eval_mind_goldset.py
  --variant first_person_v2 --model <어댑터>`). G09~G20 은 봉인 — 실행 금지.
- 사전 등록 성공 기준: confusion 적합 83%→90%+, B_불안 행동 적중 개선,
  치명 0·어휘 밖 0·A_귀소 비퇴행 유지. val loss 는 과적합 감시용이지 성능 지표가
  아니다 (val 은 논문 4종·행동 7클래스라 전체 대표성이 제한적).

## 알려진 한계 (학습 차단 아님)

- 입력의 "끌림 강함"은 후보 간 상대 정규화라, 약근거 둘만 있어도 강함으로 표기됨
  — 운영 빌더와 동일 동작이라 정렬은 맞지만 의미 모호. 후속 수정 대상.
- 입력·정답 모두 합성(claim 기반 템플릿). 문장 표면형 다양화(paraphrase_pass.py,
  GPU 필요)는 선택 사항 — 실행 시 `train_first_person_final.jsonl` 을 대신 사용.

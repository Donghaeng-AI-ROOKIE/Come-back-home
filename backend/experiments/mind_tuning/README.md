# EXAONE 마음 재해석 튜닝셋

목표는 치매·발달장애 관련 원문 논문에서 검증된 행동 진술을 추출하고,
이를 `페르소나 + 현재 상황 -> 마음 상태·혼란도·목표` 형식의 학습 샘플로
변환하는 것이다.

## 데이터 원칙

1. 학습 샘플은 최소 한 개의 검증된 `claim_id`를 가져야 한다.
2. claim의 `quote`는 지정된 PDF 페이지 텍스트에 실제로 존재해야 한다.
3. 논문에서 관찰된 집단 경향만으로 개인의 구체 장소를 만들어내지 않는다.
4. 개인 관찰과 집단 경향이 충돌하면 개인 관찰을 우선한다.
5. 목표 근거는 `previous_missing_found > caregiver_report > mention_only` 순이다.
6. 주어진 후보에 근거 있는 목표가 없으면 `goal_label`은 `null`이다.
7. 치매의 time-shift 서사를 발달장애 사례에 자동 전이하지 않는다.
8. GitHub `mind_goldset`의 G01-G20은 평가 전용이며 학습에 포함하지 않는다.

## 산출물

- `corpus/manifest.jsonl`: PDF 파일 메타데이터와 추출 품질
- `corpus/pages/*.jsonl`: 페이지별 텍스트(로컬 작업용)
- `candidates.jsonl`: 키워드 기반 행동 문장 후보
- `claims/claims.jsonl`: 검수된 조건→행동 진술
- `dataset/train_analyst.jsonl`: 분석가 시점 학습셋
- `dataset/train_first_person.jsonl`: 1인칭 시점 학습셋
- `dataset/train_mixed.jsonl`: 두 시점 혼합 학습셋
- `dataset/report.json`: 출처·유형·행동·라벨 분포와 검증 결과

페이지 번호는 별도 표기가 없으면 PDF 뷰어 기준 1부터 시작하는
`pdf_page`이다. 인쇄 페이지 번호를 확인한 경우에만 `printed_page`를 추가한다.

## v2 갱신 (2026-07-29 저녁)

- **1인칭 셋은 출력 계약 v2** — `behavior`(끌림점 접근/귀소 시도/은신·멈춤/계속 배회)
  필드 추가, goal_label 은 끌림점 접근일 때만 (PR #99 실증 계약과 일치).
  analyst 셋은 v1 유지 (A/B 대조용).
- 불안 게이지 문구에서 "가만히 있기 어렵다" 제거 — 은신·멈춤을 밀어내는 유도
  문구로 실측됨 (PR #99).
- 템플릿 반복 축소: variants 8→6·goal_variants 22→10, 목소리 풀 8→16종,
  이름·장면·트리거·목소리 선택을 variant 상관에서 시드 rng 로 전환.
  (v1 생성본은 최빈 동일 inner 220회 — 모드 붕괴 위험)
- 성공 기준(학습 후 골드셋 dev 채점, 사전 등록): confusion 적합 83%→90%+,
  B_불안 행동 적중 개선, 치명 0·어휘 밖 0·A_귀소 비퇴행 유지.
- 재현: `python build_dataset.py && python validate_dataset.py`
  (corpus/pages 필요 — 원본 PDF 에서 extract_corpus.py 로 생성, git 미포함)

제작 이력: 논문 34편 원문 확보·claim 추출은 별도 세션(2026-07-29)에서 수행,
계약 v2 전환·유도문구 제거·다양성 보정은 이 레포 세션에서 수행. 두 작업 모두
Claude 계열 — 골드셋 시나리오 작성 편향 완화책(판정 분리)은 mind_goldset README 참조.


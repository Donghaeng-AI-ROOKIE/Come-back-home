# 행동 LoRA 학습 인계 조건 (민아용, 치매 단독 v5 기준)

> **2026-08-03 개정 — 치매 단독 재학습.** 대상 단일화로 발달장애(DEV) 코퍼스·클레임이
> 삭제돼 데이터셋을 재생성했다. 아래 수치는 전부 재생성본 기준이며, 기존 `mind-v5`
> 어댑터는 삭제 전 혼합 코퍼스 학습본이라 **재사용하지 않고 새로 학습한다**.

데이터 파일 두 개만이 아니라 아래 조건이 같이 지켜져야 학습-서빙이 정렬된다.

## 데이터

- 학습: `dataset/train_first_person.jsonl` (**1,332행**) — **이것만 학습에 사용**
- 검증(loss 감시): `dataset/val_first_person.jsonl` (**134행** — 별도 논문 2종:
  **DEM-23·DEM-33**, 행동 라벨 4종 전부 포함, val 비율 9%)
- **val 논문이 바뀐 이유**: 종전 val(DEM-32·DEM-33)을 그대로 두면 DEM-32 가 유일
  출처인 `repetitive_route`·`variable_route` 가 train 에서 사라져 val 194행 중
  104행(54%)이 "학습된 적 없는 클래스"가 된다. val loss 가 과적합 감시가 아니라
  OOD 측정이 돼버려 후보 전수 비교 후 DEM-23+DEM-33 으로 재지정했다
  (`build_dataset.py` 의 `val_papers` 주석에 근거 기록).
- 재생성 명령: `PYTHONPATH=. .venv/bin/python experiments/mind_tuning/build_dataset.py`
  → 검증: `... validate_dataset.py` (assert 통과 = 인용 검증·누수·형식 OK)
- `train_analyst.jsonl`/`val_analyst.jsonl` 은 대조 실험용 — 기본 계획에서는 미사용
- 행의 최상위 `metadata` 필드는 학습 입력에 넣지 않는다. `messages` 만 사용.

## 학습 설정

- base 모델: 지금 서버에 `exaone-base` 로 서빙 중인 것과 **동일 가중치** 위에
  LoRA 어댑터 (sar 학습 때와 같은 파이프라인). 다른 체크포인트 금지 —
  서빙 모델과 다르면 어댑터가 안 맞는다.
- **정확한 체크포인트를 기입할 것** (별칭 `exaone-base` 만으로는 부족):
  서버의 vLLM 기동 스크립트에서 `--model` 값(HF ID 또는 로컬 경로)·revision·
  tokenizer revision 을 확인해 아래에 기록하고 학습·서빙 양쪽에 동일 적용.
  - base 체크포인트: `LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct`
    (2026-07-30 서버 vLLM 기동 인자에서 확인 — `--served-model-name exaone-base`)
  - code-revision: `0ff6b5ec7c13b049b253a16a889aa269e6b79a94` (기동 인자 그대로)
  - 서버 vLLM 은 이미 `--enable-lora --max-loras 2 --max-lora-rank 16` 으로
    sar·axis 어댑터를 서빙 중 — exaone-mind 추가 시 `--max-loras 3` 으로 재시작.
    학습 LoRA rank 는 16 유지(서버 상한과 일치).
- `messages` 에 모델 공식 chat template 적용.
- **loss 는 assistant 답변 토큰에만** (system·user 토큰 마스킹).
- 산출 어댑터 이름 제안: **`exaone-mind-dem`** — 기존 `exaone-mind-v5`(혼합 코퍼스)와
  반드시 다른 이름을 쓴다. 같은 이름으로 덮으면 어느 코퍼스로 학습한 것인지 사후에
  구분할 수 없다.

## 서빙 전제 (중요)

이 데이터는 **1인칭 v2 프롬프트·출력 계약**으로 만들어졌다:
- 시스템·입력 = `experiments/mind_goldset/first_person.py` 의 v2 빌더 출력과 동일
- 출력 = `{inner, status, confusion_level, behavior(4종), goal_label}`

따라서 어댑터를 운영에 꽂으려면 마음 재해석 경로가 같은 프롬프트·파서로
전환돼야 한다 (현재 운영 기본은 분석가형 v1 — 전환 PR은 별도 예정).
**분석가형 프롬프트로 이 어댑터를 호출하면 학습-서빙 형식이 다시 어긋난다.**

- 어댑터는 **마음 재해석 호출에만** 적용한다 — prior 생성(sar)·축 채점(base)
  경로에 적용 금지 (경로별 라우팅 확인 필수).
- 배포는 골드셋 dev 게이트 통과 시에만. LoRA 는 goal 판단력 저하·특정 행동
  편향·형식 안정성 훼손 같은 퇴행을 만들 수 있다 — 기준 미달이면 배포하지
  않고 base 프롬프트-온리(현행 실측 기준선)로 복귀한다.

## 평가 (학습 후)

- 개발 중 평가는 골드셋 **dev G01~G04 만** (`experiments/mind_goldset/eval_mind_goldset.py
  --variant first_person_v2 --model <어댑터>`). **G09~G14 는 봉인 — 실행 금지.**
  (치매 단독 전환으로 dev 8 → 4종, test 12 → 6종이 됐다.)
- **사전 등록 성공 기준은 재설정이 필요하다.** 종전 기준(confusion 83%→90%+ 등)은
  발달장애를 포함한 dev 8종에서 나온 값이라 dev 4종에 그대로 옮길 수 없다.
  학습 전에 치매 단독 base 프롬프트-온리 기준선을 먼저 1회 측정해 그 값을
  기준선으로 등록하고, 어댑터는 그 대비로 판정한다.
- dev 가 4종(8셀)뿐이라 통계적 힘이 약하다. 판정이 갈리면 셀 수를 늘리는 것
  (치매 시나리오 신규 작성)이 먼저다 — 반복 측정으로 밀어붙이지 않는다.
- val loss 는 과적합 감시용이지 성능 지표가 아니다 (val 은 논문 2종·134행).

## 알려진 한계 (학습 차단 아님)

- 입력의 "끌림 강함"은 후보 간 상대 정규화라, 약근거 둘만 있어도 강함으로 표기됨
  — 운영 빌더와 동일 동작이라 정렬은 맞지만 의미 모호. 후속 수정 대상.
- 입력·정답 모두 합성(claim 기반 템플릿). 문장 표면형 다양화(paraphrase_pass.py)는
  **첫 학습에서는 쓰지 않는다** — 결정론 원본으로 베이스라인을 재고, 문체 다양성이
  병목으로 확인될 때 별도 실험으로 비교한다 (효과 분리 해석을 위해).

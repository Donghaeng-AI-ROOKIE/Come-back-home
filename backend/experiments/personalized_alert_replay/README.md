# 독립 궤적 기반 개인화 알림 replay

## 합성 페르소나 뱅크

`guardian_profiles.json`은 결과를 보기 전에 고정한 **합성 보호자 답변 조건**
10개다. 완성된 Persona나 축 점수를 직접 주입하지 않는다.
`build_persona_bank.py`가 매 턴 서버의 현재 슬롯을 조회해 해당 답변을 실제
Mi:dm 온보딩 API로 보내고, 요약 확인과 저장까지 운영 경로 그대로 수행한다.

- 12개 운영 슬롯 모두에 구체적인 답변이 있다. 인터뷰 종료만으로 통과시키지 않고
  최종 세션의 `filled_keys`가 12개 전부인지 검사한다.
- 저장된 Persona의 `completed_tiers`도 `[1,2,3]`인지 검사한다.
- 6개 축의 목표 단계는 답변 다양성 설계용일 뿐 모델 입력에 숫자로 보내거나
  Persona에 직접 쓰지 않는다. 실제 `axis_evidence`와 추후 `axis_scores`는 운영
  Mi:dm 경로의 출력이다.
- 행동 유형은 `stay` 2명, `move` 4명, `backtrack` 2명,
  `hide` 2명으로 구성했다. `move`는 직선 지속·무작위 방향 전환을 나눠다.
- 대중교통은 제외하고 도보만 다루며 실명·주거 주소 대신 합성 이름과 공공 장소를 쓴다.
- 같은 10명을 truth의 일치·중립·불일치 세 층에 반복 배치할 예정이므로 파일럿
  30건에서 층마다 보호자 정보 구성이 같다.

검증:

```bash
cd backend
.venv/bin/pytest tests/test_guardian_profiles.py -q
.venv/bin/python -m experiments.personalized_alert_replay.build_persona_bank \
  --base https://macmini.tail67859f.ts.net:8443 --profiles SP01
```

2026-08-12 배포 Mi:dm에서 10명 전원을 실제 등록했다.
12/12 슬롯·`completed_tiers=[1,2,3]` 통과, `llm_degraded=false`,
Mi:dm 호출 실패 0건이다. 10명의 운영 ID는 `persona_bank_manifest.json`에
있다. 자동 배치로 등록한 SP02~SP10의 전문과 저장 스냅샷은
`results/persona_bank_midm-bank-v2-final-20260812.jsonl`에 있고, SP01은 동일
대본을 수동 재개해 완료한 운영 세션 `a87d9139fa28`이다.

## 질문

동일한 알림 면적에서 Mi:dm 12슬롯 개인화(C)는 거리 기준(A)과 일반 치매
AI(B)보다 시간별 실제 위치를 알림 발송 구역에 더 자주 포함하는가? 특히
최초 근거리 구역(D1)을 벗어난 시점에서 개인화가 알림 구역을 더 유효하게
재배치하는지를 본다.

## 순환 논법 방지

- 정답 생성: `truth_routes.py`의 NetworkX 최단경로 + 고정 보행속도.
- 예측: 운영 도로망 MC.
- 정답 생성기는 `app.phase2`를 import하지 않고, Koester·6전략·게이지를
  사용하지 않는다.
- 두 경로가 공유하는 것은 도보 도로망뿐이다.

## A/B/C 비교 규약

- `A_distance_only`: EXAONE·MC 없이 LKP에서 가까운 셀 19개.
- `B_generic_ai`: 같은 나이·유형·집만 주고, 개인 장소·행동·6축 근거를 제거.
- `C_exaone_personalized`: Mi:dm 온보딩이 12슬롯으로 저장한 원본 Persona ID를 EXAONE E2E 예측에 사용.
- B/C의 도로망·MC 시드는 동일하고 순서는 시나리오마다 반전한다.
- 지도 사례는 D1 19셀과 D2 19셀, 총 38개의 H3 해상도 9 셀로 표현한다.
- 주 정량 비교는 면적을 더 직접 통제하기 위해 세 군 모두 H3 해상도 8
  상위 7구역(구역당 약 0.74 km², 총 약 5.16 km²)을 사용한다.

## 정답 층

- `consistent`: 등록 장소 방위와 정답 이동 방위가 거의 같음.
- `neutral`: 두 방위가 약 90도 다름.
- `counter`: 두 방위가 약 180도 반대.

각 인물의 이동능력 수준은 경로 길이·속도의 타당한 범위만 제어하고 방향
배정에는 쓰지 않는다. SP04는 Mi:dm 최종 Persona에 지오코딩된 끌림점이
없어, 기준 방향을 C군에 전달하지 않는 음성 대조군으로 표시한다.

세 층을 균등하게 만드는 것은 개인화가 유리한 사례만 고르는 것을 막기 위해서다.
실제 사례의 층 비율은 알 수 없으므로 세 층 결과를 따로 보고한다.

## 지표

- `알림 발송 구역 포함률`: 0·45·90·135분의 실제 위치가 해당 군의 알림
  발송 구역 안에 들어간 시점의 비율.
- `D1 외부 포함률`(주 해석 지표): 실제 위치가 최초 근거리 구역 D1을 벗어난
  시점만 분모로 삼은 알림 발송 구역 포함률.
- 실제 푸시 전송·열람·시민 제보·발견 성공은 이 replay에서 측정하지 않는다.

## 실행

```bash
cd backend
.venv/bin/python -m experiments.personalized_alert_replay.run_replay --pilot
.venv/bin/python -m experiments.personalized_alert_replay.analyze --pilot
```

Mi:dm 10명의 30개 정답 설계·A군만 읽기 전용으로 먼저 검증:

```bash
.venv/bin/python -m experiments.personalized_alert_replay.remote_persona_abc \
  --design-only --repeats 1 --out persona_abc_design_30.jsonl
```

배포 신고 API는 신고 즉시 D1 알림 로직을 탄다. 따라서 B/C 라이브
실험은 등록 기기에 실험 알림이 갈 수 있음을 승인하거나, 배포에
`suppress_alerts` 실험 가드를 먼저 추가한 후 실행해야 한다.

공식 배포의 EXAONE·도로망 라이브 파일럿과 trace:

```bash
.venv/bin/python -m experiments.personalized_alert_replay.remote_live_replay --pilot
.venv/bin/python -m experiments.personalized_alert_replay.remote_live_replay \
  --pilot --scenario neutral-00 --repeats 1 --arms C --trace
.venv/bin/python -m experiments.personalized_alert_replay.analyze_live
```

라이브 러너는 브라우저 `toISOString()`과 동일하게 UTC offset을 명시해 전송한다.
배포 컨테이너가 UTC이므로 KST naive 시각을 보내면 경과시간이 0.05시간으로
클램프되어 성능 결과가 무효가 된다.

## 최종 pause/resume 실험

10개 합성 페르소나를 일치·중립·불일치 방향층에 배치해 30개를 계획했다.
`SP04-counter`는 재시도 후에도 EXAONE 응답 형식 검증을 통과하지 못해 사전
규칙대로 제외했고, 최종 29개 시나리오 × 4개 시점 = 116개 대응 관측을 분석했다.
정지·은폐형 정답 경로는 `이동 → 45~90분 정지 → 재이동 → 은폐`로 고정했다.

동일한 H3 해상도 8의 7구역 예산에서 전체 포함률은 A 87.1%(101/116),
B 87.9%(102/116), C 86.2%(100/116)로 유사했다. D1 밖 31개 시점에서는
A 51.6%(16/31), B 58.1%(18/31), C 61.3%(19/31)로 C가 가장 높았다.
따라서 이 파일럿은 개인화가 전체 면적을 넓히지 않고도 근거리 밖 알림 구역을
재배치할 가능성을 보였지만, 실제 현장 효율이나 통계적 우월성을 입증하지는 않는다.

재현 파일:

- `results/persona_abc_behavior10_curated29_pause_resume_v1.jsonl`
- `results/persona_abc_behavior10_alert_targeting_pause_resume_v1.json`
- `results/PERSONA_ABC_PAUSE_RESUME_V1.md`
- `results/persona_abc_behavior10_selected_svg_v1/`

## 주장 제한

이 실험은 위치가 알림 구역에 들어온 **발견 기회의 상한**을 재다. 실제 시민이
알림을 보고 수색해 발견했다는 의미가 아니다. 실제 치매 실종 궤적도 아니므로
지도 규칙 기반 메커니즘 파일럿으로만 인용한다.

# 챗봇 성능 평가 하네스 (Phase 0 온보딩)

여기서 재는 것은 **대화 챗봇이 보호자 답변에서 페르소나를 얼마나 잘 뽑아내는가**.

## 무엇을 재나 (5지표)

| 묶음 | 지표 | 읽는 곳 |
| --- | --- | --- |
| 배관 | 페르소나 도달·종료·이름/나이·LLM 열화 | 세션/페르소나 API |
| 내용 | 끌림점 재현율 | `persona.attraction_points[].label` |
| 내용 | evidence 등급 정확도 | `persona.attraction_points[].evidence` |
| 내용 | 축 근거 커버리지 | `persona.axis_evidence` 키 |
| 효율 | 질문 수 · 중복 질문 | `session.messages` |

## 구조

```
scenarios.py  보호자 답변 대본 + 기대 페르소나 (시나리오 뱅크)
responder.py  챗봇 질문을 읽고 대본에서 답을 고르는 질문-매칭기
              ⚠ 고정 배열 금지 — 슬롯 순서가 비결정적이라 '지금 무엇을 묻는지'로 매칭
runner.py     TestClient 로 세션을 끝까지 굴려 Transcript 수집 (서버 불필요)
scorer.py     Transcript × 기대치 → ScoreCard
run_eval.py   엔트리포인트
judge.py      정답표 없이 (대본+추출 결과)만 보고 3차원 채점하는 LLM judge
run_judge_corr.py  P1-7 — 정답표 점수 vs judge 점수 피어슨 상관 (골드셋 8개, --real 전용)
```

## 실행

```
# backend 디렉토리에서. 콘솔이 cp949 면 UTF-8 강제 필요.
PYTHONUTF8=1 python -m experiments.chatbot_eval.run_eval                 # 스텁(기본)
PYTHONUTF8=1 python -m experiments.chatbot_eval.run_eval --scenario D1_kim
PYTHONUTF8=1 python -m experiments.chatbot_eval.run_eval --real          # .env Mi:dm 실키
PYTHONUTF8=1 python -m experiments.chatbot_eval.run_eval --quiet         # 점수만
```

## 스텁 모드의 의미

기본은 스텁(LLM 키 빈값 강제, conftest 와 동일). 스텁에서는 Mi:dm 추출이 빈
결과를 내므로 **내용 지표(끌림점·evidence·축)가 낮은 게 정상**이다 —
배관(세션 구동·종료·규칙 폴백·지오코딩)만 검증하는 모드다. 남는 신호:

- `_ensure_found_place`/`_PLACE_TOKEN_RE` 정규식 백스톱이 잡는 끌림점(예: "버스정류장")
- `_apply_extraction` 노트 폴백으로 원발화가 축 근거로 남는 것(축 커버리지 일부)
- 노트 품질 필터(`_NON_FACT`: "모르"/"못 알아")가 답변을 반려하는 경우 → 축 누락

내용 성능은 `--real` 로만 측정된다.

## 최종 목적 — 가드 다이어트

대화 가드 6종(질문 중복·화제 이탈·전제 질문·여부 먼저·부정 충족·무지 소진)을
하나씩 꺼보며 점수 변화로 실효성을 잰다. 하네스 없이는 불가능.

## 상태

- [x] 러너·리스폰더·채점기·엔트리포인트 — 스텁 E2E 통과 (2026-07-23)
- [x] 시나리오 7개 — D1 베이스라인 · D2 대흥역(0.9)+옛집 · 정정 5유형
- [x] `--real` Mi:dm 실측 — 배관 전부 OK, 정정 5유형 전부 라이브 작동 (2026-07-23)
- [x] 지오코딩 탈락 ↔ 수집 실패 구분 — draft_attractions 대조, 수집률→반영률
- [x] 가드 토글 6종(interview.GUARDS + retrieval.DENOISE) + `--sweep`/`--guard-off`/`--runs`
- [x] 가드 스윕 — 무지소진 강력, 부정충족·여부먼저 중간, 나머지 3종 N=3 평균 판정 중
- [x] P1-7 judge 상관 실측 (2026-07-26, `results/judge_corr.{md,json}`) — 2런: 1차 단독 collection 0.978 · evidence 0.982 · axis 0.328 → 2차(같은 전사에 judge 입력 2방식 통제) v1 축이름만 0.867/0.806/0.534 · v2 근거원문 0.710/0.519/0.564. **판정 = 도입 보류**: n=6~8에서 런간 r 변동이 기준(0.7) 근방을 넘나들어 확정 불가. 입력 보강(v2)은 axis 개선 없음(+0.03)에 무관 차원 점수까지 흔듦(judge 취약성) → v1 입력 유지. 경향은 collection·evidence 우세, axis 일관 열세. 골드셋 확장이 선행 조건 + judge=Mi:dm self-bias 한계.
- [x] 발달장애 시나리오 5개 — DD1·DD2·DD3(골드셋 이식) + DD_sparse·DD_rich(프로브). 발달 특화 슬롯 4종(선호대상·이탈·회피·전환) 전부 자극 (2026-07-28)
- [x] **발달 가드 스윕** — N=3 전체(`results/dd_sweep_20260728.log`, 7설정×2프로브×3회)
  + **N=5 확정 스윕**(`results/dd_sweep_n5.log`, 4설정×2프로브×5회)

  | 가드 OFF | N=3 질문수 | **N=5 질문수** | N=3 부정조건Q | **N=5 부정조건Q** | 판정 |
  | --- | --- | --- | --- | --- | --- |
  | ~ignorance_exhaust | **+4.7** | (미재측정) | +0.0 | — | 실효 |
  | ~negation_fill | +1.7 | **+4.0** | +0.0 | **+1.2** | **실효 (발달 최강)** |
  | ~dedup | −0.7 (중복 **+1.3**) | (미재측정) | — | — | 실효 |
  | ~existence_first | +0.3 | **+1.6** | −2.0 | **+0.6** | 실효 |
  | ~presupposition | +0.0 | **+1.2** | −0.7 | **+1.0** | 실효 |
  | ~topic_grounding | +0.3 | (미재측정) | −0.3 | — | 무효 — 단 자극 미생성 |

  ⚠️ **N=3 은 이 도메인에서 부족하다.** `existence_first`·`presupposition` 은 N=3 에서
  무효로 보였고 대상 지표가 **음수**(−2.0/−0.7)까지 나왔는데, N=5 에서 **부호가 뒤집혀
  실효로 확정**됐다. 효과 크기(질문 1~2개)가 Mi:dm 비결정성과 같은 스케일이라 3회로는
  부호조차 못 가른다. **작은 효과를 판정하려면 N=5 이상.**

  **지표 신뢰 규칙** — 수집률·축 커버리지는 추출·지오코딩 잔여 노이즈로 스윙하므로
  판정에 쓰지 않는다(치매 N=5 스윕 결론). 직접 지표(전제Q·부정조건Q·중복)와 질문수만 본다.
  이 규칙을 어기면 grounding 이 "수집 100→89%" 로 실효처럼 보인다 — 실제로는 무효다.

- [x] **가드 다이어트 최종 결론 = 6종 전부 유지.**
  - **발달 경로에서 5종이 실효로 측정됐다** — 무지소진(+4.7) · 부정충족(+4.0) · 여부먼저(+1.6) ·
    전제질문(+1.2) · 중복방지(중복 +1.3). `topic_grounding` 하나만 미검증.
  - **경로 의존성이 실증됐다.** `dedup` 은 치매에서 "사실상 무효(Mi:dm 이 거의 반복 안 함)"였는데
    발달에서는 중복이 실제로 발생한다(0 → 1.3). 한 경로의 측정만으로 지우면 다른 경로가
    조용히 나빠진다. `negation_fill` 도 치매 중간(+2) → 발달 최강(+4.0)으로 커졌다.
  - `topic_grounding` 은 양쪽 무효지만 **"효과 없음"이 아니라 "자극을 못 만듦"** 이다 —
    치매 때 단 카브아웃(긴 다턴 드리프트 프로브 부재)이 발달 프로브(36턴)에도 그대로 적용된다.
    지우려면 드리프트 전용 시나리오 재검증이 선행.
  - 가드는 전부 결정론적 코드 분기라 런타임 비용이 사실상 0 — 제거 이득이 없다.

## 가드 스윕 사용법

```
# 베이스라인 + 가드 하나씩 끈 실행 비교. 효율 가드는 --real 필수(스텁은 slot_filled 우회).
python -m experiments.chatbot_eval.run_eval --real --sweep \
    --scenario PROBE_sparse,PROBE_rich --runs 3
```

- 프로브: `PROBE_sparse`(희소응답 → 무지소진·부정충족·여부먼저 자극), `PROBE_rich`(풍부/드리프트 → 전제·중복·grounding 자극).
- 지표: 질문수·중복·전제Q·부정조건Q 가 OFF 시 오르면 그 가드가 실효.
- **--runs 3+ 필수**: 단일 실행은 Mi:dm 비결정성 노이즈(±1~2질문)에 지배돼 작은 효과를 못 가른다.

## ⚠ 2026-08-03 치매 단독 스코프 전환

발달장애 시나리오(DD1~DD3·DD_sparse·DD_rich)를 `scenarios.py` 에서 삭제했다(원본은 git 이력).
위 "발달 가드 스윕" 절의 수치와 `results/dd_sweep_20260728.log` 는 **삭제 전 구성**에서
나온 측정값이며, 지금 하네스로는 재현되지 않는다 — 가드 실효성 판단의 근거로 인용할 때
이 사실을 함께 밝힌다.

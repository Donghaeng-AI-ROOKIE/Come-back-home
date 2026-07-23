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
- [ ] 발달장애 시나리오

## 가드 스윕 사용법

```
# 베이스라인 + 가드 하나씩 끈 실행 비교. 효율 가드는 --real 필수(스텁은 slot_filled 우회).
python -m experiments.chatbot_eval.run_eval --real --sweep \
    --scenario PROBE_sparse,PROBE_rich --runs 3
```

- 프로브: `PROBE_sparse`(희소응답 → 무지소진·부정충족·여부먼저 자극), `PROBE_rich`(풍부/드리프트 → 전제·중복·grounding 자극).
- 지표: 질문수·중복·전제Q·부정조건Q 가 OFF 시 오르면 그 가드가 실효.
- **--runs 3+ 필수**: 단일 실행은 Mi:dm 비결정성 노이즈(±1~2질문)에 지배돼 작은 효과를 못 가른다.

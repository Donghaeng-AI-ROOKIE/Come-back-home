# P1-5 — 예측 소요시간: 스테이지 타이머 설계·코드 준비 + 스텁 베이스라인

실험 상세 설계안(0724 분업) [대흠] 몫. P2-1(EXAONE 서빙 후 소요시간 실측·budget 스윕)의
계측 기반을 만든다. 이 PR로 들어간 코드:

- `pipeline.run_prediction` 스테이지 타이머 8종 — prepare / prior / roadnet / topdown /
  bottomup / statistical / combine / total (ms). 매 예측마다 `[timing]` 로그 1줄,
  트레이스 예측이면 `PredictionDebug.timings` 로 저장(대시보드·실험이 조회).
- `exaone.call_log` 항목에 `ts`(ISO)·`elapsed_ms` 추가 — 기존에 kind/prompt/response만
  있어 LLM 호출당 소요를 잴 수 없었다. P2-1 budget 스윕이 이 값을 집계한다.

## 스텁 베이스라인 실측 (2026-07-25, M-시리즈 로컬)

조건: LLM 스텁(호출 0회), 500워커×2(agent+statistical), seed 42, 정릉 3km 캐시.

| 조건 | roadnet | bottomup | statistical | total |
|---|---|---|---|---|
| 도로망 off | 0ms | 16ms | 15ms | **32ms** |
| 도로망 on·콜드(그래프 로딩) | 3,059ms | 527ms | 523ms | **4,111ms** |
| 도로망 on·웜(캐시) | 19ms | 509ms | 512ms | **1,042ms** |

## 판정

1. **알고리즘 몫은 웜 기준 약 1초.** "17~27초"의 지배 항은 실 EXAONE 호출(prior 1회 +
   mind budget≤10회)이다 — 서빙이 붙기 전에는 시간 최적화 대상이 알고리즘이 아님이 확정.
2. **콜드 3초는 도로망 로딩** — 신고 접수 시 `roadnet_preload=True`로 선로딩하면
   예측 시점에서는 사라지는 비용(이미 config에 노브 존재).
3. P2-1 실측 방법이 단순해짐: 서빙 후 `prior_ms` + call_log의 mind `elapsed_ms` 합이
   곧 LLM 몫 — **budget 스윕 = (LLM 호출당 평균 elapsed) × budget 선형 추정**과
   실측의 대조로 끝난다.

## 남은 결정 (착수 전 결정 1건 — 팀 확인 필요)

시연 목표 소요: **10초면 budget ~4로 충분** / 3~5초면 mind 호출 병렬화까지 필요.
이 결정은 EXAONE 서빙 후 호출당 실측 elapsed(ms)가 나와야 확정 가능 — 타이머는 준비 완료.

## 재현

```bash
cd backend
.venv/bin/python -m pytest tests/test_stage_timings.py -q
# 베이스라인: use_roadnet on/off 로 run_prediction 2회씩 — [timing] 로그 확인
```

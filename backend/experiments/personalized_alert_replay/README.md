# 독립 궤적 기반 개인화 알림 replay

## 질문

동일한 D1·D2 셀 예산에서, 사전등록 장소를 사용한 예측(C)은 사용하지 않은
예측(B)보다 60분 동안 정답 위치를 알림 구역에 더 자주 포함하는가?

## 순환 논법 방지

- 정답 생성: `truth_routes.py`의 NetworkX 최단경로 + 고정 보행속도.
- 예측: 운영 도로망 MC.
- 정답 생성기는 `app.phase2`를 import하지 않고, Koester·6전략·게이지를
  사용하지 않는다.
- 두 경로가 공유하는 것은 도보 도로망뿐이다.

## 비교 규약

- `B_nonpersonalized`: 끌림점 없음.
- `C_personalized`: 사전등록 장소 1개와 그 장소의 prior weight 1.0.
- 나이·유형·Koester 반경·6전략 혼합·도로망·MC 시드는 동일.
- D1 19셀은 공통, D2는 D1과 겹치지 않는 상위 19셀로 고정.

## 정답 층

- `consistent`: 정답 목적지가 등록 장소 80~300m 내.
- `neutral`: 등록 장소와 정답 목적지의 방위가 60~120도 다름.
- `counter`: 두 방위가 140도 이상 반대.

세 층을 균등하게 만드는 것은 개인화가 유리한 사례만 고르는 것을 막기 위해서다.
실제 사례의 층 비율은 알 수 없으므로 세 층 결과를 따로 보고한다.

## 지표

- `GTCR@60`: 5분 간격 13개 정답 시점 중 D1∪D2가 위치를 포함한 비율.
- `D2 GTCR@60`: D1을 뺀 개인화 셀만의 포함 비율.
- `Any coverage@60`: 60분 내 1회 이상 포함.
- `TTFC`: 첫 포함 시점. 미포함은 `null`.
- `Irrelevant D2`: 정답 궤적과 한 번도 겹치지 않은 D2 셀 비율.

## 실행

```bash
cd backend
.venv/bin/python -m experiments.personalized_alert_replay.run_replay --pilot
.venv/bin/python -m experiments.personalized_alert_replay.analyze --pilot
```

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

## 주장 제한

이 실험은 위치가 알림 구역에 들어온 **발견 기회의 상한**을 재다. 실제 시민이
알림을 보고 수색해 발견했다는 의미가 아니다. 실제 치매 실종 궤적도 아니므로
지도 규칙 기반 메커니즘 파일럿으로만 인용한다.

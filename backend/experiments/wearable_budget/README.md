# P1-2(재정의) — 국내 치매군 이동 예산 실측 vs 워커 설계 상수

Geolife 재캘리브레이션 안을 대체하는 "거리 앵커 방어 패키지"의 국내 실증 1축.
μ/σ(ISRID Dementia Urban)는 불변 — 여기서 재는 것은 워커 동역학 상수
(`WALK_SPEED_M_PER_MIN` 48m/분·피로 1.3·v_max 4.5km/h)가 국내 치매군의
실측 활동 구조와 모순되지 않는가다.

데이터 = AI Hub 「치매 고위험군 웨어러블 라이프로그」 계열 병합 CSV
(반지형 웨어러블 person-day, CN 111명 / MCI 51명 / **Dem 12명**·유효일 681).
대용량 원본은 레포 밖 — `--csv` 로 지정. `activity_daily_movement` 단위는
미터로 검증됨(movement/steps 중앙값 0.802m/보 = 보폭 범위, 분 검산 10,261/10,261).

## 방법

유효일 필터(288블록 완전기록 + 비착용 2h 미만 + 보행 존재) 후 person-day 풀과
피험자 단위(의사반복 방지) 병행 집계. LLM 0회, stdlib 만.

## 결과 (results/budget_match.md 전문)

| 판정 | 근거 |
|---|---|
| **하루 예산 소진 1.7h** | Dem 일일 이동 p50 4,756m ÷ 48m/분 — 연속 보행 1.7h 이면 평소 하루 이동량 소진. 3h+ 시나리오에서 피로 정지(rest) 필수의 국내 근거 |
| **연속 활동 상한 실측** | Dem bout p50 10분 / p90 40분 / p99 120분, 피험자 최장 bout 중앙값 135분 — '수 시간 무정지 보행' 가정 불합치, fatigue_fired→rest() 설계와 정합 |
| **48m/분 위치 정당** | 활동 중 이동률(Dem 20.8m/분, 일상 저강도 하한) < 48 < v_max 75m/분(상한). 순간속도 직접 실측은 위치 부재로 불가(한계 명기) |
| **야간 배회 근거 아님** | Dem 야간(22~06) 활동 점유 4.7% < CN 6.1% — 역방향. 관리 코호트 특성으로 해석, 야간 prior 정당화 불가(정직 표기) |

## 한계

위치정보 없음(발견거리·μ/σ 검증 불가 — ISRID 몫 불변) · Dem 12명(경증 관리
코호트 가능성 — 표본 수 반드시 병기) · 활동 클래스는 강도 기반이라 보행과
제자리 활동 완전 구분 불가.

## 재현

```bash
cd backend
.venv/bin/python experiments/wearable_budget/run_budget_match.py \
    --csv "<wearable_activity_merged.csv 경로>"
```

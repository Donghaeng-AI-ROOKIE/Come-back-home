# 돌아오길 백엔드

실종자(치매 노인) 동선 예측 + 시민 타겟 알림 앱의 FastAPI 백엔드.
Phase 0~3을 그대로 모듈로 옮겼다. 전체 구조는 [`../docs/IMPLEMENTATION_ARCHITECTURE.md`](../docs/IMPLEMENTATION_ARCHITECTURE.md)에 있다.
모델 엔드포인트와 API 키가 있으면 실제 모델을 호출하고, 설정이 없거나 호출에 실패하면 통계·규칙 기반 폴백으로 전체 파이프라인을 계속 실행한다.

## 실행

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
# http://localhost:8000/docs (Swagger UI)
```

테스트: `python -m pytest -q` (2026-08-13 기준 890 passed · 2 skipped)

## 구조

```
app/
├── main.py            FastAPI 엔트리포인트
├── config.py          임계값·튜닝 파라미터 (전부 .env 오버라이드 가능)
├── storage.py         SQLite 영속 저장소 (안전 삭제·VACUUM, → 실서비스 DB 교체 지점)
├── schemas/           Pydantic 도메인 모델 (persona, report, prediction, tip, case)
├── llm/               모델 클라이언트 + 설정 누락·장애 시 폴백
│   ├── exaone.py        EXAONE — 지식 LoRA prior, 행동 LoRA 마음 재해석
│   ├── mind_v2.py       마음 재해석 v2 계약(행동·목표·혼란)
│   ├── midm.py          Mi:dm — 온보딩 인터뷰 전용
│   ├── tip_llm.py       제보 구조화·구체성 등급 (Mi:dm 2.0 Mini 선택, 스텁 폴백)
│   └── copy_llm.py      알림·안내 문구 작성
├── rag/                 수색 논문 인덱스와 발췌 검색 (prior 전용)
├── geo/
│   ├── h3grid.py        H3 육각격자, likelihood 커널, 좌표 유틸
│   ├── roadnet.py       OSMnx 보행 도로망 (USE_ROADNET=true 기본, 디스크 캐시)
│   └── reverse.py       역지오코딩 캐시 (경보 지역명)
├── phase0/interview.py  온보딩: 적응형 챗봇 인터뷰 → 페르소나. Tier1 빠른등록·보완 모드 포함
├── phase1/intake.py     신고 접수: 보호자 입력 인상착의 색상 추출 → Case 생성 → 1차 경보
├── phase2/
│   ├── topdown.py       2-1 Top-down: prior → POA (MC 없음)
│   ├── simulation.py    2-2 Bottom-up (agent+MC 500회) / 2-3 통계 MC (동적 마음 재해석 없음)
│   ├── combine.py       α-pool (linear=넓게 / log-linear=좁게)
│   ├── refresher.py     경과시간이 늘면 같은 모델을 더 늦은 시점에서 재평가 (기동 시 스레드)
│   └── pipeline.py      3종 계산(top-down은 디버그용) → bottom-up·통계 2-way 통합 → 최종 POA, baseline 저장
├── phase3/
│   ├── trust.py         제보 신뢰도 p 산출 (이진 아님 — p값 그대로 전달)
│   ├── poa_update.py    ★층1: 새POA ∝ 기존POA × [p·L + (1−p)·1], 잔여 제보 재적용
│   ├── triggers.py      ★층2 트리거: 새 LKP / 주기(45분) / KL 분포 이탈 + JS divergence(D3 예비스크린)
│   ├── tip_flow.py      제보 수신 → p → 판정 → 층1 (+층2 재실행) → D3(3차, 새 지역 한정 알림) 오케스트레이션
│   ├── presence.py      셀 단위 열람 집계 (불투명 토큰, 좌표 미수집)
│   ├── push.py          웹푸시(VAPID)·Expo Push 발송 경로
│   └── alerts.py        POA 상위 셀(누적 80%) 타겟 알림 + 새 지역 선별(D3, 집합차+합산질량임계 후 커버리지 타겟팅)
├── walk/stats.py        산책 세션 집계 (평시 모드)
└── api/                 Phase 0~3 · walk · geo · auth · privacy · debug 라우터 51개
```

## 작업별 모델 라우팅

| 작업 | 설정·운영 모델 | RAG | 폴백 |
|---|---|---|---|
| Phase 0 축 컴파일 | `AXIS_SCORING_MODEL` / EXAONE 기본 모델 | 미사용 | 미채점 상태로 두고 기본값 사용 |
| Phase 2 초기 prior | `EXAONE_MODEL` / `exaone-sar` | 상위 4개 발췌 사용 | 유형별 SAR 통계 prior |
| Phase 2 마음 재해석 | `MIND_MODEL=exaone-mind-dem5` | 미사용 | 혼란 증가 휴리스틱 |
| Phase 3 제보 구조화 | 별도 `TIP_LLM_*` / Mi:dm 2.0 Mini 선택 | 미사용 | 키워드 기반 결정적 스텁 |

`EXAONE_MODEL`과 `AXIS_SCORING_MODEL`은 기본값이 비어 있어 배포 환경에서 지정한다. `EXAONE_MODEL=exaone-sar`를 사용할 때 축 채점을 기본 모델로 분리하려면 `AXIS_SCORING_MODEL`을 반드시 별도로 지정해야 한다. RAG 인덱스가 없거나 검색이 실패하면 prior는 발췌 없이 계속 생성된다. 마음 재해석은 학습 계약과 출력 형식을 보호하기 위해 RAG를 사용하지 않으며, 실제 모델 호출 상한은 예측당 5회다.

`exaone-mind-dem5`의 v2 계약은 행동·목표·혼란을 모두 출력하며, 행동→이동 전략 연결은 구현돼 기본 켜짐이다(PR #109·#118). 완전한 규칙 기반 혼란 산정의 운영 연결은 후속 구현이다.

## POA 갱신 2층 설계 (2026-07-03 확정)

```
제보 수신 → 신뢰도 p 산출
├─ p < 0.2                    → 파기
├─ 0.2 ≤ p < 0.8              → 층1: 베이지안 갱신만 (p 가중, 약한 신호도 누적)
└─ p ≥ 0.8 + 위치·시각 특정    → 층1 + 층2: 새 LKP 앵커로 Phase 2 재실행
                                → 새 baseline 위에 잔여 유효 제보 재적용
```

핵심 기준: **"이 제보가 시뮬 출발점(LKP)을 바꾸는가?"**
임계값(0.2/0.8/45분/KL 0.5)은 전부 `config.py`에 있다. 45분 주기+KL과 주기-only를 비교한 합성 실험에서는 탐지율이 같고 주기-only의 재실행이 적었지만, 현재 코드는 아직 주기+KL을 유지한다.

재실행 판정을 물어보는 주체는 `phase2/refresher.py`다. 기동 시 시작해 `POA_REFRESH_INTERVAL_SECONDS`(기본 300초)마다 활성 케이스를 훑는다. 경과시간은 이미 예측에 들어가는데 예측을 다시 돌리는 쪽이 없어, 5시간 실종으로 신고하면 7시간이 지나도 화면이 5시간 지도였던 문제를 막는다. **이것은 베이지안 갱신이 아니다** — 같은 모델을 더 늦은 시점에서 다시 평가할 뿐이며, "알림 구역에서 제보가 없었다"는 정보는 POD를 알 수 없어 반영하지 않는다.

`tip_llm` 구조화 온도는 0.0이다. 다만 실모델 실험에서 시각 언급이 없는 26건 중 20건에 시각이 생성됐다. 현재 구현은 시각 형식과 범위만 검사하고 원문 포함 여부는 확인하지 않으므로, 현장 사용 전 원문 대조 가드가 필요하다.

## API 흐름 예시

```
POST /phase0/personas                  페르소나 등록
POST /phase1/reports                   신고 접수 → case_id
POST /phase2/cases/{id}/predict        예측(2-way 결합) → POA
POST /phase3/cases/{id}/alerts         1차 타겟 알림 (POA 기반, last_alert_poa 최초 시딩)
POST /phase3/cases/{id}/tips           시민 제보 → 층1/층2 자동 처리 → D3(새 지역 한정 3차 알림) 자동 평가
GET  /phase3/cases/{id}/poa            현재 POA 상위 셀 (지도용)
GET  /phase3/cases/{id}/rerun-check    층2 트리거 상태 (스케줄러용)
```

## 실제 연동으로 교체할 지점 (TODO)

| 지점 | 파일 | 내용 |
|---|---|---|
| 모델 배포 설정 | `config.py`, `.env` | Mi:dm·EXAONE 기본 모델·`exaone-sar`·`exaone-mind-dem5`·`tip_llm`·임베딩 엔드포인트와 LoRA 마운트 |
| 도로망 캐시 배포 | `geo/roadnet.py` | `USE_ROADNET=true`가 기본. 캐시 없는 좌표의 첫 요청은 Overpass 콜드 다운로드(15~110초) — `scripts/warm_roadnet.py`로 예열 |
| 규칙 기반 혼란도 | `phase2/guardrail.py` | 현재는 모델의 상·중·하를 `0.85/0.6/0.35` 고정값으로 변환. 규칙 산정으로의 완전 대체가 남음 |
| 제보 시각 원문 검증 | `llm/tip_llm.py`, `phase3/time_resolve.py` | 모델이 만든 시각이 시민 원문에 실제로 있는지 대조하는 가드 추가 필요 |
| 푸시 운영 전환 | `phase3/push.py`, `phase3/webpush.py` | 발송 경로 구현(기본 `push_enabled=false`, 실기기 수신 미검증) |
| API 인가 | `api/*.py` | `/auth/*`는 있으나 Phase·Privacy·Debug 라우터에 인증 의존성이 없다 |
| TTL 파기 스케줄러 | `privacy/lifecycle.py` | 재예측은 `refresher`가 돌지만 파기는 `POST /privacy/purge-expired` 수동 |

# 돌아오길 백엔드

실종자(치매 노인) 동선 예측 + 시민 타겟 알림 앱의 FastAPI 백엔드.
현재 등록→개인준비→SAR prior→K 보정→보행→알림→제보→종결 흐름은 [서비스 E2E 정본](../docs/SERVICE_E2E_20261012.md)에 있다. 이전 구현 세부사항은 [IMPLEMENTATION_ARCHITECTURE.md](../docs/IMPLEMENTATION_ARCHITECTURE.md)에 보존한다.

**전체 축 채점은OFF**다. 초기 prior와 저장 K 개인화는 계속 적용된다. develop 확정30/70·res9·5.8㎢와 이전 배포 worker(res7)는 구분한다. 이 문서는 새 배포 확인을 뜻하지 않는다.
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
│   ├── exaone.py        SAR prior 생성, legacy 마음 LoRA 호출
│   ├── initial_behavior.py  원문 입력 계약·시뮬레이션 프로필 보정
│   ├── mind_policy.py    준비된 K 조건부 행동 정책
│   ├── mind_v2.py       마음 재해석 v2 계약(행동·목표·혼란)
│   ├── midm.py          Mi:dm — 온보딩 인터뷰 전용
│   ├── tip_llm.py       제보 구조화·구체성 등급 (Mi:dm 2.0 Mini 선택, 스텁 폴백)
│   └── copy_llm.py      알림·안내 문구 작성
├── rag/                 기존 논문 인덱스 검색 (SAR prior·K 개인 준비)
├── geo/
│   ├── h3grid.py        H3 육각격자, likelihood 커널, 좌표 유틸
│   ├── roadnet.py       OSMnx 보행 도로망 (USE_ROADNET=true 기본, 디스크 캐시)
│   └── reverse.py       역지오코딩 캐시 (경보 지역명)
├── phase0/interview.py  온보딩: 적응형 챗봇 인터뷰 → 페르소나. Tier1 빠른등록·보완 모드 포함
├── phase1/intake.py     신고 접수: 보호자 입력 인상착의 색상 추출 → Case 생성 → 1차 경보
├── phase2/
│   ├── topdown.py       2-1 Top-down: prior → POA (MC 없음)
│   ├── continuous_prediction.py  개인 보행·문헌 통계 지도 어댑터
│   ├── persistent_context_walk.py 조건부 정책·시간·환경·체크포인트
│   ├── person_walk.py   초기 prior 소비·도로망 보행
│   ├── person_projection.py  저장 K 해석의 수치·프로필 보정
│   ├── literature_distance.py 독립 문헌 거리분포 지도
│   ├── simulation.py    기존 agent/statistical MC (legacy/fallback)
│   ├── combine.py       α-pool (linear=넓게 / log-linear=좁게)
│   ├── refresher.py     경과시간이 늘면 같은 모델을 더 늦은 시점에서 재평가 (기동 시 스레드)
│   └── pipeline.py      SAR 생성·K 보정 → 개인/문헌 지도 결합 → Case 저장
├── phase3/
│   ├── trust.py         제보 신뢰도 p 산출 (이진 아님 — p값 그대로 전달)
│   ├── poa_update.py    ★층1: 새POA ∝ 기존POA × [p·L + (1−p)·1], 잔여 제보 재적용
│   ├── triggers.py      ★층2 트리거: 새 LKP / 주기(45분) / KL 분포 이탈 + JS divergence(D3 예비스크린)
│   ├── tip_flow.py      제보 수신 → p → 판정 → 층1 (+층2 재실행) → D3(3차, 새 지역 한정 알림) 오케스트레이션
│   ├── presence.py      셀 단위 열람 집계 (불투명 토큰, 좌표 미수집)
│   ├── push.py          웹푸시(VAPID)·Expo Push 발송 경로
│   ├── area_budget.py   실제 지리적 발송 구역 합집합의 면적 상한 선택
│   └── alerts.py        대상 기기 매칭·새 구역 알림·실패 기록
├── walk/stats.py        산책 세션 집계 (평시 모드)
└── api/                 Phase 0~3 · walk · geo · auth · privacy · debug 라우터 51개
```

## 현재 모델 라우팅과 보정 경계

| 작업 | 모델·코드 | 현재 역할·폴백 |
|---|---|---|
| 온보딩 | KT Mi:dm / `MIDM_*` | 원문·맥락 저장, 답변 추출·질문 문장화. 제보 Mini와 별도 |
| 전체 축 채점 | `AXIS_SCORING_MODEL` / EXAONE Base | **OFF**. 기존 축 유지·빈 축 기본 계수. ON만으로 Base가 자동 선택되지는 않음 |
| SAR 초기 prior | `EXAONE_MODEL` / `exaone-sar` + RAG | 전략 확률·장소/반경 등급. 호출 실패는 기본값과 source로 표시 |
| K 사전 개인 준비 | K-EXAONE / `prepared_initial`·`prepared_mind` | 원문·RAG 해석·재검토·조건부 규칙 저장 |
| 사건별 개인 보정 | `apply_prepared → compile_person` | SAR 기준 위에 목적지·방향·이동 능력·길 익숙함·환경 반응 반영 |
| 보행 중 마음 반영 | 저장 K 정책 + 코드 | 정상 준비 경로의 조건부 행동·체크포인트. 입자별 모델 호출 없음 |
| legacy 마음 재해석 | `exaone-mind-dem5` | 예전/fallback 경로. 정상 K 정책 실행과 구분 |
| 제보 구조화 | `TIP_LLM_*` / Mi:dm 2.0 Mini | 장소/시각 표현·외모·방향·구체성. 설정된 호출 실패는 판정 없음 |
| 안내 문구 | `COPY_LLM_*`, 기본 Mini 상속 | 코드 초안 다듬기. 실패 시 초안 유지 |

`pipeline._initial_prior`가 SAR를 생성하고 저장 K 해석을 보정한 뒤 `case.prior`로 전달한다. `person_walk`는 전략·장소 가중치·반경을 실제 소비하며 `simulation_persona`는 프로필 복사본에 보정을 적용한다. 최종 문헌 통계70%는 개인화 prior의 일부가 아니라 별도로 계산한 지도다. 배포 worker 설정 읽기와 과거 합성 E2E 검증 자료는 [정본](../docs/SERVICE_E2E_20261012.md)에 연결했다.

다음 갱신2층·이전 실험 설명은 기존 구현 기록이다. 현재 정책/모델 경계를 대외 설명할 때는 위 정본을 기준으로 한다.

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

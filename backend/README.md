# 돌아오길 백엔드 (백본)

실종자(치매 노인·아동·지적장애인) 동선 예측 + 시민 타겟 알림 앱의 FastAPI 백엔드.
아키텍처 다이어그램(`../architecture/architecture.png`)의 Phase 0~3을 그대로 모듈로 옮겼다.
**모든 AI 모델은 스텁** — API 키 없이 전체 파이프라인이 end-to-end로 돈다.

## 실행

```powershell
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
# http://localhost:8000/docs (Swagger UI)
```

테스트: `python -m pytest tests/` (18개 — 층1 수식 수치 검증, α-pool, E2E 흐름)

## 구조

```
app/
├── main.py            FastAPI 엔트리포인트
├── config.py          임계값·튜닝 파라미터 (전부 .env 오버라이드 가능)
├── storage.py         인메모리 저장소 (→ DB 교체 지점)
├── schemas/           Pydantic 도메인 모델 (persona, report, prediction, tip, case)
├── llm/               모델 인터페이스 + 스텁 ★API 키 발급 후 _call_api 구현
│   ├── exaone.py        EXAONE — prior 생성(좌표 아님), 마음 예측, 리포트
│   ├── midm.py          Mi:dm — 온보딩 인터뷰, 제보 구조화
│   ├── varco_vision.py  VARCO-Vision — 인상착의 추출 (생성 아님, 시민 제보 사진 대조는 미수행으로 확정)
│   └── upstage.py       Solar Pro — 신고서 파싱
├── geo/
│   ├── h3grid.py        H3 육각격자, likelihood 커널, 좌표 유틸
│   └── roadnet.py       도로망 인터페이스 (OSMnx 교체 지점, 미구현)
├── phase0/interview.py  온보딩: 챗봇 인터뷰 → 페르소나 DB
├── phase1/intake.py     신고 접수: 인상착의·신고자 추출 → Case 생성
├── phase2/
│   ├── topdown.py       2-1 Top-down: prior → POA (MC 없음)
│   ├── simulation.py    2-2 Bottom-up (agent+MC 500회) / 2-3 통계 MC (AI 없음)
│   ├── combine.py       α-pool (linear=넓게 / log-linear=좁게)
│   └── pipeline.py      3종 계산(top-down은 디버그용) → bottom-up·통계 2-way 통합 → 최종 POA, baseline 저장
├── phase3/
│   ├── trust.py         제보 신뢰도 p 산출 (이진 아님 — p값 그대로 전달)
│   ├── poa_update.py    ★층1: 새POA ∝ 기존POA × [p·L + (1−p)·1], 잔여 제보 재적용
│   ├── triggers.py      ★층2 트리거: 새 LKP / 주기(45분) / KL 분포 이탈 + JS divergence(D3 예비스크린)
│   ├── tip_flow.py      제보 수신 → p → 판정 → 층1 (+층2 재실행) → D3(3차, 새 지역 한정 알림) 오케스트레이션
│   └── alerts.py        POA 상위 셀(누적 80%) 타겟 알림 + 새 지역 선별(D3, 집합차+합산질량임계 후 커버리지 타겟팅)
└── api/                 phase별 REST 라우터
```

## POA 갱신 2층 설계 (2026-07-03 확정)

```
제보 수신 → 신뢰도 p 산출
├─ p < 0.2                    → 파기
├─ 0.2 ≤ p < 0.8              → 층1: 베이지안 갱신만 (p 가중, 약한 신호도 누적)
└─ p ≥ 0.8 + 위치·시각 특정    → 층1 + 층2: 새 LKP 앵커로 Phase 2 재실행
                                → 새 baseline 위에 잔여 유효 제보 재적용
```

핵심 기준: **"이 제보가 시뮬 출발점(LKP)을 바꾸는가?"**
임계값(0.2/0.8/45분/KL 0.5)은 전부 `config.py` — 시뮬레이션 테스트로 튜닝.

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
| 모델 API | `llm/*.py` | 키 발급 후 각 클라이언트 `_call_api` + 메서드 구현 |
| 도로망 | `geo/roadnet.py`, `phase2/simulation.py::_walk` | OSMnx 그래프 탐색으로 교체 |
| 마음 예측 훅 | `phase2/simulation.py` | agent 모드에서 상태 변화 시에만 EXAONE 호출 |
| DB | `storage.py` | SQLite/Postgres Repository 로 교체 |
| 푸시 | `phase3/alerts.py` | FCM + 사용자 위치 인덱스 |
| 파일 업로드 | `api/phase1.py`, `api/phase3.py` | 플래그 → multipart UploadFile |

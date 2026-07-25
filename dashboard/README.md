# 돌아오길 — 경찰 관제 대시보드 (dashboard/)

경찰 관제(운영자) 역할의 웹 콘솔. 시민·보호자용 RN 앱(`frontend/`)과 별개의 세 번째 클라이언트다.
디자인 정본 = claude.ai/design 프로젝트 「경찰 관제 대시보드 웹」(S1/S2/S3 + 모달 2종 + 인계 토큰 문서),
스펙 = `본선/돌아오길_본선/관제대시보드-디자인브리프.md`.

## 실행

```bash
cd dashboard
npm install
npm run dev          # http://localhost:5173
```

- **라이브 모드**: 백엔드가 떠 있으면(기본 `http://localhost:8000`, `VITE_API_BASE`로 변경) 자동 감지해
  실데이터로 동작 — 케이스 목록, 실 POA 폴리곤 히트맵, 페르소나, 제보 판정, 알림(시뮬), 종결·파기.
  ```bash
  cd backend && .venv/bin/python -m uvicorn app.main:app --port 8000   # 스텁 모드로 충분
  ```
- **데모 모드**: 백엔드가 없으면 디자인 확정 데모 데이터(김순자 시나리오 4상태)로 동작.
  헤더 배지가 두 모드를 구분 표기한다.

## 화면

| 화면 | 내용 |
|---|---|
| S1 케이스 보드 | 진행 중 케이스 카드 — 경과시간 실시간 카운트, 골든타임 긴급도 에스컬레이션 |
| S2 관제 상세 | 지도(POA 육각 히트맵 + LKP + 제보 핀) + 패널(프로필/타임라인/알림·제보) + 4상태 데모 스위처 |
| S3 신고 접수 | Phase 1 접수 폼 → D1 자동 발송(시뮬) → 관제 상세 이동 |
| 모달 A 제보 입력 | `POST /tips` 이중 반환(Tip 또는 `need_more`) 분기 — 되묻기 UI + force 확정 |
| 모달 B 종결 | `POST /privacy/.../close` — 5일 파기 라이프사이클 고지 |

## 계약·정직성 규칙 (수정 시 유지할 것)

- API는 `src/api.ts` — `API_CONTRACT.md` v0.1 범위만 사용. 계약에 없는 수치는 화면에 표기하지
  않거나 "(데모)" 라벨을 붙인다(알림 도달 추정 등).
- FCM 실발송 미구현(`sent=false`) — "발송 시뮬레이션" 라벨과 헤더 배지는 제거 금지.
- 색 토큰(`src/theme.ts`)의 3색 의미 체계(긴급 빨강/수색 앰버/평시 그린)는 모바일 앱과 공유하는
  확정값. 액센트 블러플은 상호작용 표시 전용.
- 축 점수 표기는 실축 필드명(`axis_scores` 키) 기준 — 한국어 라벨 매핑은 `theme.ts`의
  `AXIS_LABELS_KO`.

## 현재 한계 (후속 작업)

- 지도는 도로망 플레이스홀더 SVG 위에 실 POA 폴리곤을 등장방형 투영으로 렌더 — 실 지도 타일
  (MapLibre/Leaflet)은 후속. 라이브 4층 POA 분해(top-down/bottom-up/statistical)는 debug bundle 연동 예정.
- 케이스 목록은 `GET /debug/overview` 재사용 — 관제 전용 목록 API 승격은 별도 PR.
- 알림 이력은 라이브에서 이 세션 발송분만 표시(백엔드에 알림 이력 조회 API 없음). 라이브
  타임라인의 접수·예측·제보 이벤트는 실데이터(`created_at`·`last_sim_at`·`tips`) 기준.

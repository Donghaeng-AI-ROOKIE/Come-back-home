# 돌아오길 API 계약 — front ↔ back 공유 진실

> 이 문서가 **유일한 계약**이다. 프론트 목(mock)은 이 스펙을 흉내내고, 백엔드는 이 스펙을 구현한다.
> **계약을 바꾸려면 이 문서를 먼저 고치고 양쪽에 공지.**
> 출처: `backend/app/api/*.py` + `backend/app/schemas/*.py`
> 갱신 2026-08-13: 라우터 전수 재추출(51개). Walk·Geo·Auth·presence·웹푸시·Phase 0 세션 API 추가, 제거된 사진·문서 첨부와 VARCO·Upstage 추출 경로 삭제.

- Base URL: 로컬 `http://localhost:8000`, Swagger `/docs`. 웹 배포본은 같은 출처의 `/api`를 쓴다(nginx가 백엔드로 넘긴다).
- 모든 시각은 **ISO 8601** 문자열(로컬 naive). 좌표는 `{lat, lng}`.
- **스텁 모드:** 모델 API 키가 없으면 백엔드가 **유효한 모양의 폴백 응답**을 반환한다. 실 배선·렌더 검증은 키 없이도 가능하다.
- **데모 케이스 미리 seed됨:** 서버 부팅 시 정릉동 케이스가 `case_id="case-jeongneung-001"`로 자동 생성·예측까지 완료된다. CORS는 열려 있다.

---

## 프론트가 꼭 알아야 할 4가지

1. **POA 응답에 폴리곤이 이미 포함됨** — `GET .../poa`의 각 셀이 `{ cell, prob, polygon: [{lat,lng} × 6] }`로 온다. h3-js 변환이 필요 없다. H3 res-9 육각형 변은 약 174m.
2. **POA는 `{셀ID: 확률}`, 합=1.** 상위 셀만 필요하면 `?top=N`.
3. **`POST /tips`는 두 형태를 반환한다.** `status` 키 유무로 분기해야 한다(아래 Phase 3 참고).
4. **고신뢰 제보는 응답이 오래 걸린다.** 층2(새 LKP 재예측)를 그 요청 하나가 품기 때문이다(실측 29.5초, 새 지역이면 2분 초과). 짧은 타임아웃으로 끊으면 사건에 POA가 없는 상태가 남는다. 끊긴 뒤에도 서버는 접수를 마치므로, 재전송 전에 접수 여부를 먼저 조회해야 중복 제보가 생기지 않는다.

---

## 데이터 모델

```jsonc
GeoPoint            { "lat": 37.61, "lng": 127.01 }
PersonaType         "dementia"
CaseStatus          "intake" | "predicted" | "searching" | "found" | "closed"
TipDecision         "discard" | "layer1" | "layer2"

AttractionPoint     { "label": "옛집(정릉동)", "location": GeoPoint, "weight": 1.0 }
RouteFamiliarity    { "route": "옛 직장", "score": 0.9 }    // 끌림점 라벨별 익숙함
EnvResponse         { "feature": "water", "direction": "접근", "strength": 0.9 }
                    // feature 는 water|forest|park|market 닫힌 어휘

Persona {
  "id": str, "type": PersonaType, "name": str, "age": int,
  "guardian_id": str,
  "home": GeoPoint,
  "attraction_points": [AttractionPoint],
  "behavior_notes": [str],
  "axis_evidence": { "mobility_transport_capacity": [str], ... },   // 축별 근거 노트
  "axis_scores": { "mobility_transport_capacity": 0.5, ... },       // 0.1~0.9. F·근거없음 축은 키 자체가 없음
  "axis_scoring_report": {},
  "route_familiarity": [RouteFamiliarity],
  "env_responses": [EnvResponse],
  "completed_tiers": [int],          // 등록 진행 판정용(Tier 1만이면 partial)
  "created_at": datetime
  // "axis_quotes" 는 응답에 없음 — 보호자 원발화라 response_model_exclude 로 제외
}

InterviewSession {
  "id": str, "guardian_name": str,
  "messages": [ {"role": "assistant"|"user", "text": str} ],
  "done": bool, "persona_id": str|null
}

Appearance   { "top","bottom","shoes","etc","summary": str, "top_color","bottom_color","shoes_color": str }
             // 보호자가 직접 입력. *_color 와 summary 는 서버가 규칙 기반으로 채운다(사진 분석 없음)
MissingReport {
  "id": str, "persona_id": str|null, "missing_type": PersonaType,
  "lkp": GeoPoint, "lkp_time": datetime, "situation": str,
  "appearance": Appearance|null, "created_at": datetime
}

PriorParams {           // EXAONE 출력 (좌표 아님)
  "strategy_probs": { "route_following": 0.6, ... },   // 6전략, 합=1
  "attraction_weights": { "옛집(정릉동)": 0.55, ... },
  "radius_lognormal": { "mu": 0.47, "sigma": 1.53 },
  "reasoning": str
}
MindState { "status": "이동 중", "confusion": 0.5, "changed": false }
POA        { "cells": { "8930e1d99abffff": 0.012, ... }, "source": "combined", "generated_at": datetime }

Case {
  "id": str, "report": MissingReport, "status": CaseStatus,
  "lkp": GeoPoint, "lkp_time": datetime,           // 현재 앵커 (층2 시 교체)
  "prior": PriorParams|null, "mind": MindState|null,
  "baseline_poa": {셀:확률}|null, "current_poa": {셀:확률}|null,
  "poa_by_hour": { "1": {셀:확률}, ... },          // 시간축 슬라이더용 캐시
  "roadnet_used": bool, "roadnet_fallback_reason": str,
  "last_alert_poa": {셀:확률}|null, "last_alert_at": datetime|null,
  "last_sim_at": datetime|null,
  "closed_at": datetime|null, "close_reason": str|null,
  "tips": [Tip]
}
// 지명은 Case 필드가 아니다. 신고 시 역지오코딩 캐시를 예열해 두고,
// 경보 조회(GET /phase3/alerts)가 그 캐시에서 지역명을 읽는다.

Tip {
  "id": str, "case_id": str, "text": str,
  "location": GeoPoint|null, "seen_at": datetime|null,
  "p": float|null, "decision": TipDecision|null, "created_at": datetime
}
```

---

## 엔드포인트

### Auth — 계정과 역할

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| POST | `/auth/signup` | `{ login_id, password, role }` | `{ token, user_id, login_id, role }` |
| POST | `/auth/login` | `{ login_id, password }` | 동일. 역할은 저장된 값을 따른다 |
| GET | `/auth/me` | `Authorization: Bearer <token>` | 동일 |
| POST | `/auth/role` | `{ role }` + Bearer | 동일 |
| POST | `/auth/logout` | Bearer | `{ ok: true }` |

> Phase·Privacy·Debug 라우터에는 인증 의존성이 없다. 토큰은 앱이 사용자를 구분하는 데 쓰고, 서버는 아직 강제하지 않는다.

### Phase 0 — 온보딩 (보호자 사전등록)

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| POST | `/phase0/interviews/sessions` | `{ guardian_name, guardian_id, mode, scope, persona_type? }` | `{ session_id, mode, persona_status, current_slot, progress:{answered,total}, question }` |
| POST | `/phase0/interviews/sessions/{id}/messages` | `{ text }` | 위와 같은 진행 상태 + 다음 질문 |
| POST | `/phase0/interviews/sessions/{id}/complete` | — | `{ persona_id, persona_status, persona_version }`. 확정 자체는 대화의 확인 게이트에서 끝나므로 이 호출은 최종 상태 조회다. 세션이 아직 안 끝났으면 `409` |
| POST | `/phase0/interviews` | `{ guardian_name }` | InterviewSession (초기 계약) |
| POST | `/phase0/interviews/{id}/answers` | `{ text }` | InterviewSession |
| GET | `/phase0/interviews/{id}` | — | InterviewSession |
| GET | `/phase0/slots` | `?persona_type=` | 슬롯 카탈로그 |
| POST | `/phase0/personas` | 구조화 필드 | Persona |
| GET | `/phase0/personas` | `?guardian_id=` | [Persona] |
| GET | `/phase0/personas/status` | `?guardian_id=` | `{ persona_id, persona_status, available_mode }` |
| GET | `/phase0/personas/{id}` | — | Persona |
| PATCH | `/phase0/personas/{id}` | 수정할 필드 | Persona |

- `mode`는 `create`(신규) 또는 `supplement`(남은 Tier 2·3만). `scope`는 `create` 전용으로 `all`(12문항) 또는 `tier1`(5문항, 신고 전 미니챗).
- `persona_status`/`available_mode`는 `none`/`create`, `partial`/`supplement`, `complete`/`update` 세 쌍이다. `update`는 **챗봇이 아니라 구조화 수정 화면(PATCH)** 으로 보내라는 신호다.
- `supplement`는 `partial` 상태에서만 열린다. 그 외에는 `409`.

### Phase 1 — 실종 신고 접수

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| POST | `/phase1/reports` | `{ missing_type, lkp, lkp_time, persona_id?, situation?, appearance? }` | Case |
| GET | `/phase1/cases/{case_id}` | — | Case |

접수 즉시 LKP 중심 H3 `k=2`(19셀) 1차 경보 경로가 실행된다(`reflex_alert_on_intake=true` 기본, 실패해도 접수는 계속). 사진·문서 첨부 플래그는 제거됐다(PR #136·#141).

### Phase 2 — 위치 예측

| 메서드 | 경로 | 쿼리 | 응답 |
|---|---|---|---|
| POST | `/phase2/cases/{case_id}/predict` | `?seed=` (재현용, 선택) | PredictionResult `{ case_id, prior, poa_topdown, poa_bottomup, poa_statistical, poa_combined, prior_source, roadnet_used, ... }` |

`prior_source`·`roadnet_used`는 조용한 폴백을 화면에 드러내기 위한 계약 필드다. `fallback`/`stub`이거나 `roadnet_used=false`면 그 예측은 개인화나 도로 제약이 빠진 것이므로 앱이 경고 배너를 띄운다.

### Phase 3 — 알림·제보·POA

| 메서드 | 경로 | 요청/쿼리 | 응답 |
|---|---|---|---|
| POST | `/phase3/cases/{case_id}/reflex-alerts` | — | `{ case_id, target_cells, message, sent, note }` — 1차 경보 수동 재발송 |
| POST | `/phase3/cases/{case_id}/alerts` | — | 동일 — POA 누적 80% 타겟 알림. 최초 호출 시 `last_alert_poa` 시딩 |
| GET | `/phase3/alerts` | `?cell_res7=` | 그 셀의 활성 알림 목록 |
| GET | `/phase3/alerts/resolved` | `?cell_res7=&hours=24` | 최근 해제(발견·종결)된 알림 |
| POST | `/phase3/cases/{case_id}/tips` | `{ text, location?, seen_at?, force?, reporter_user_id? }` | **Tip 또는 되묻기** (아래) |
| GET | `/phase3/cases/{case_id}/poa` | `?top=20&elapsed_hours=` | `{ case_id, total_cells, top_cells:[{cell,prob,polygon}], prior_source, roadnet_used, ... }` |
| GET | `/phase3/cases/{case_id}/guidance` | — | 시민 화면에 띄울 안내 문구 |
| GET | `/phase3/cases/{case_id}/rerun-check` | — | `{ case_id, should_rerun, reason }` |
| POST | `/phase3/cases/{case_id}/presence` | `{ token }` | 그 사건을 보고 있는 사람 수 |
| GET | `/phase3/cases/{case_id}/presence` | — | 동일 |
| POST | `/phase3/devices` | `{ token, platform, cell_res7?, engagement, web_subscription? }` | 등록 결과 |
| DELETE | `/phase3/devices/{token}` | — | 해제 결과 |
| GET | `/phase3/webpush/public-key` | — | `{ public_key }` (VAPID) |

> `POST /tips`는 두 가지 형태를 반환한다.
>
> - **Tip 객체** — 정상 접수. 저장·POA 갱신까지 완료됨
> - **`{ "status": "need_more", "missing": ["location"|"time"], "reason"?: str }`** — 저장하지 않고 되묻기. 프론트가 부족한 항목만 받아 **합친 전체 텍스트로 재제출**하거나 `force: true`로 확정한다. `reason`은 시각 분기에서만 오는 사유 코드(현재 `"layer2_needs_time"`)
>
> `text`는 자유 텍스트 한 덩어리다. 위치·시각은 별도 필드가 아니라 이 텍스트에서 구조화·지오코딩·시각 변환으로 뽑는다(`location`·`seen_at`은 지도 핀 등 명시값이 있을 때만).

**개인정보 경계.** `presence`의 `token`은 클라이언트가 만든 불투명 난수이며 계정·기기·좌표 어디에도 연결하지 않는다. 좌표 필드가 없는 것은 의도된 설계다 — 셀 단위 집계도 위치정보이기 때문이다. `devices`의 `cell_res7`은 폰이 자기 좌표를 res7로 낮춰 보낸 값이고 서버는 현재 값만 덮어쓴다. `reporter_user_id`는 Tip에 저장하지 않고 카운터만 올린다.

### Walk — 산책 (평시 모드)

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| POST | `/walk/sessions` | `{ user_id, area_label? }` | WalkSession |
| POST | `/walk/sessions/{id}/end` | `{ distance_km, duration_min }` | WalkSession |
| GET | `/walk/sessions/active` | `?user_id=` | WalkSession 또는 `null` |
| GET | `/walk/stats` | `?user_id=` | WalkStats |

좌표열은 받지 않는다. 거리·시간 요약만 서버로 온다.

### Geo — 장소와 지도

| 메서드 | 경로 | 요청/쿼리 | 응답 |
|---|---|---|---|
| GET | `/geo/search` | `?q=` | `{ lat, lng, label, precision, source }` |
| POST | `/geo/labels` | `{ points: [GeoPoint] }` | `{ labels: [str] }` — 역지오코딩 |
| GET | `/geo/nearby-walks` | `?lat=&lng=&limit=4` | `[{ name, lat, lng, distance_km, route_km, kind, path }]` |
| GET | `/geo/tiles/{z}/{x}/{y}.png` | — | 지도 타일 프록시 |

### 종결·개인정보 파기 (privacy)

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| POST | `/privacy/cases/{case_id}/close` | `{ reason: "found"\|"withdrawn" }` | Case — `closed_at` 기록, 5일 후 파기 예약 |
| GET | `/privacy/cases/{case_id}/retention` | — | `{ case_id, status, closed_at, retention_days, purge_due_at, expired }` |
| DELETE | `/privacy/cases/{case_id}` | — | `{ purged, case_id }` — 수색 중이면 `409`(철회 종결이 먼저) |
| DELETE | `/privacy/personas/{persona_id}` | — | `{ purged, persona_id }` — 인터뷰·종결 케이스 동반 파기 |
| POST | `/privacy/purge-expired` | — | `{ purged_case_ids, purged_interview_ids, count }` — TTL 만료분 일괄 파기(수동 트리거) |
| GET | `/privacy/audit` | — | `[AuditRecord]` — 개인정보 미포함, ID·행위·사유 코드만 |

### 디버그·관제 (debug) — 시연·검증용, 프로덕션 계약 아님

| 메서드 | 경로 | 요청/쿼리 | 응답 |
|---|---|---|---|
| GET | `/debug/overview` | — | 페르소나·인터뷰·케이스 목록. 관제 대시보드가 케이스 목록으로 사용 |
| POST | `/debug/cases/{case_id}/predict` | `?seed=` | 워커 궤적·EXAONE 이벤트 트레이스 포함 재예측 |
| GET | `/debug/cases/{case_id}/bundle` | — | 케이스+페르소나+인터뷰+트레이스+4층 POA 종합 |
| GET | `/debug/cases/{case_id}/buildings` | `?radius_m=800` | LKP 반경 건물 폴리곤+높이(첫 호출은 수십 초) |

> 공통 에러: 리소스 없음 `404`, POA 없이 알림·제보·조회 시도 `409`("Phase 2 예측을 먼저"), 종결 케이스에 예측·알림·제보 시도 `409`.

---

## 데모 시나리오 호출 순서

```
1. POST /phase0/interviews/sessions               → session_id  (보호자 등록 시작)
2. POST /phase0/interviews/sessions/{id}/messages → 반복        (확인 게이트에서 Persona 확정)
3. POST /phase0/interviews/sessions/{id}/complete → persona_id  (최종 상태 조회)
4. POST /phase1/reports                           → case_id + 1차 경보 자동 발송
5. POST /phase2/cases/{id}/predict                → POA
6. GET  /phase3/cases/{id}/poa                    → 히트맵 렌더 (폴리곤 포함)
7. POST /phase3/cases/{id}/alerts                 → 타겟 알림 (누적 80% 셀)
8. POST /phase3/cases/{id}/tips                   → Tip(decision) → 층1/층2
9. GET  /phase3/cases/{id}/poa                    → 좁혀진 히트맵
10. POST /privacy/cases/{id}/close                → 종결, 5일 후 파기 예약
```

Phase 1 이후 구간은 `backend/tests/test_e2e_flow.py`가 스텁 모드로 실제 통과시킨다.

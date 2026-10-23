# 돌아오길 API 계약 — front ↔ back 공유 진실

이 문서는 앱과 백엔드의 업무 API 계약을 설명합니다. 실제 입력/응답 스키마는 `backend/app/api/`와 `backend/app/schemas/`, 클라우드 공개 경로와 권한은 `backend/app/cloud_bridge/policy.py`를 함께 확인합니다.

2026-10-23: main #297 기준으로 전송 경계, 데모 기본값, 자동 예측, 비동기 제보, 알림 정책 설명을 정정했습니다. 아래 표는 주요 업무 API 참조이며 전체 OpenAPI 목록은 로컬 `/docs`를 사용합니다.

- **운영 클라우드:** 앱은 Supabase Auth로 로그인하고 인증된 RPC 작업을 제출합니다. 비공개 GPU worker가 허용된 FastAPI 경로를 실행하고 결과를 반환합니다. 소유자 ID는 검증된 사용자 UUID에서 주입합니다. [배포 연결](deploy/supabase/README.md).
- **로컬 HTTP:** `http://localhost:8000`, Swagger `/docs`. 기존 nginx `/api` 구성은 로컬/과거 배포 경로이며 현재 Pages 운영 경로와 구분합니다. FastAPI 라우터 전체를 인증된 공개 API로 직접 노출하지 않습니다.
- 시각 입력은 **ISO 8601, UTC `Z` 또는 명시적 offset 권장**입니다. 내부 naive 변환과 한국 시각 조건 변환을 구분합니다. 좌표는 `{lat, lng}`입니다.
- **스텁/폴백:** 모델 미설정 개발 실행의 결과는 실제 모델 품질 검증으로 사용하지 않습니다. 응답의 준비 상태, `prior_source`, `roadnet_used`를 확인합니다.
- **데모 자동 생성:** `SEED_DEMO_DATA=false`가 기본입니다. 서버 부팅만으로 데모 사건이 생성되지 않습니다.

---

## 프론트가 꼭 알아야 할 4가지

1. **POA 응답에 폴리곤이 이미 포함됨** — `GET .../poa`의 각 셀이 `{ cell, prob, polygon: [{lat,lng} × 6] }`로 온다. h3-js 변환이 필요 없다. H3 res-9 육각형 변은 약 174m.
2. **POA는 `{셀ID: 확률}`, 합=1.** 상위 셀만 필요하면 `?top=N`.
3. **`POST /tips`는 두 형태를 반환한다.** `status` 키 유무로 분기해야 한다(아래 Phase 3 참고).
4. **제보 접수와 무거운 재예측은 분리된다.** 구조화와 접수 결과를 먼저 반환하고, 층2 재예측과 추가 알림은 백그라운드에서 처리한다. cloud worker는 응답 본문이 완성되면 작업 결과를 먼저 게시한다. 지도는 재계산 중 저장된 결과를 반환한다. 접수 전 구조화와 큐 대기는 남으므로 전체 요청 지연이 0이라는 뜻은 아니다. 연결 중단 시에는 접수 상태를 먼저 확인한다.

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

### Auth — 로컬 HTTP 계정과 역할

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| POST | `/auth/signup` | `{ login_id, password, role }` | `{ token, user_id, login_id, role }` |
| POST | `/auth/login` | `{ login_id, password }` | 동일. 역할은 저장된 값을 따른다 |
| GET | `/auth/me` | `Authorization: Bearer <token>` | 동일 |
| POST | `/auth/role` | `{ role }` + Bearer | 동일 |
| POST | `/auth/logout` | Bearer | `{ ok: true }` |

> 위 `/auth/*`는 로컬 HTTP 경로다. 운영 앱은 Supabase Auth를 사용하며 cloud bridge가 소유권과 허용 경로를 검사한다. `/privacy/*` 관리자 경로는 별도 키를 요구하고 cloud bridge에서는 공개하지 않는다. `/debug/*`도 내부 검증용이다.

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

접수 시 마지막 목격 위치 중심의 1차 경보 경로를 실행한다(`reflex_alert_on_intake=true` 기본, 실패해도 접수는 계속). 실제 대상은 현재 알림 해상도와 면적 정책으로 선택한다.

앱의 신고 완료 화면(`ReportSentScreen`)이 `/predict`를 자동 요청하며 사용자가 별도 버튼을 누를 필요는 없다. `POST /reports` 자체는 사건을 접수하는 API이고 서버 refresher가 미예측 사건도 주기적으로 확인한다. 앱을 통한 자동 요청과 신고 API 한 번으로 동기 예측까지 완료하는 동작을 구분한다.

| 메서드 | 보호자 소유 사건 경로 | 설명 |
|---|---|---|
| GET | `/phase1/cases` | 인증 사용자 소유 사건 목록 |
| POST | `/phase1/cases/{case_id}/close` | 발견 또는 신고 철회로 종결 |
| DELETE | `/phase1/cases/{case_id}` | 종결 후 삭제 요청 |

Cloud bridge가 소유자 ID를 주입한다. 클라이언트가 보낸 다른 사용자 ID를 권한으로 사용하지 않는다.

### Phase 2 — 위치 예측

| 메서드 | 경로 | 쿼리 | 응답 |
|---|---|---|---|
| POST | `/phase2/cases/{case_id}/predict` | `?seed=` (재현용, 선택) | PredictionResult `{ case_id, prior, poa_topdown, poa_bottomup, poa_statistical, poa_combined, prior_source, roadnet_used, ... }` |

`prior_source`·`roadnet_used`는 조용한 폴백을 화면에 드러내기 위한 계약 필드다. `fallback`/`stub`이거나 `roadnet_used=false`면 그 예측은 개인화나 도로 제약이 빠진 것이므로 앱이 경고 배너를 띄운다.

### Phase 3 — 알림·제보·POA

| 메서드 | 경로 | 요청/쿼리 | 응답 |
|---|---|---|---|
| POST | `/phase3/cases/{case_id}/reflex-alerts` | — | `{ case_id, target_cells, message, sent, note }` — 1차 경보 수동 재발송 |
| POST | `/phase3/cases/{case_id}/alerts` | — | 동일 — 최종 `area_budget` 정책의 res9, 합집합 최대 5.8㎢ 대상. coverage 정책은 과거 호환 경로 |
| GET | `/phase3/alerts` | `?target_cell=` (기존 `cell_res7` 지원) | 그 셀의 활성 알림 목록 |
| GET | `/phase3/alerts/resolved` | `?target_cell=&hours=24` (기존 `cell_res7` 지원) | 최근 해제(발견·종결)된 알림 |
| POST | `/phase3/cases/{case_id}/tips` | `{ text, location?, seen_at?, force?, reporter_user_id? }` | **Tip 또는 되묻기** (아래) |
| GET | `/phase3/cases/{case_id}/poa` | `?top=20&elapsed_hours=` | `{ case_id, total_cells, top_cells:[{cell,prob,polygon}], prior_source, roadnet_used, ... }` |
| GET | `/phase3/cases/{case_id}/guidance` | — | 시민 화면에 띄울 안내 문구 |
| GET | `/phase3/cases/{case_id}/rerun-check` | — | `{ case_id, should_rerun, reason }` |
| POST | `/phase3/cases/{case_id}/presence` | `{ token }` | 그 사건을 보고 있는 사람 수 |
| GET | `/phase3/cases/{case_id}/presence` | — | 동일 |
| POST | `/phase3/devices` | `{ token, platform, target_cell?, engagement, web_subscription? }` | 등록 결과 |
| DELETE | `/phase3/devices/{token}` | — | 해제 결과 |
| GET | `/phase3/targeting-policy` | — | `{ target_res, coverage, targeting_policy, location_ttl_seconds, supported_location_resolutions }` |
| GET | `/phase3/webpush/public-key` | — | `{ key, enabled, ...targeting-policy }` (VAPID) |
| POST | `/phase3/webpush/subscription` | `{ subscription, target_cell?, engagement? }` | `{ device_id, registered, targetable }` |
| POST | `/phase3/webpush/location` | `{ device_id, target_cell? }` | `{ targets:[{case_id,cells,resolution,kind}], location_ttl_seconds }` |
| POST | `/phase3/webpush/enter` | `{ device_id, case_id }` | `{ status }` — 관측 기반 진입 판정, 실제 수신 증명이 아님 |

> `POST /tips`는 두 가지 형태를 반환한다.
>
> - **Tip 객체** — 제보 처리 결과. `decision`에 따라 폐기 또는 저장/지도 갱신하며, 필요한 무거운 재예측은 백그라운드에서 진행한다. Tip 반환을 새 지도 계산 완료로 해석하지 않는다.
> - **`{ "status": "need_more", "missing": ["location"|"time"], "reason"?: str }`** — 저장하지 않고 되묻기. 프론트가 부족한 항목만 받아 **합친 전체 텍스트로 재제출**하거나 `force: true`로 확정한다. `reason`은 시각 분기에서만 오는 사유 코드(현재 `"layer2_needs_time"`)
>
> `text`는 자유 텍스트 한 덩어리다. 위치·시각은 별도 필드가 아니라 이 텍스트에서 구조화·지오코딩·시각 변환으로 뽑는다(`location`·`seen_at`은 지도 핀 등 명시값이 있을 때만).

프런트 정책 조회는 기존 Supabase read lane `/phase3/webpush/public-key`의 정책 필드를 사용한다. `/phase3/targeting-policy`는 직접 API 진단 경로이며, 새로운 SQL migration은 필요하지 않다.

**개인정보 경계.** `presence`의 `token`은 클라이언트가 만든 불투명 난수이며 계정·기기·좌표 어디에도 연결하지 않는다. 좌표 필드가 없는 것은 의도된 설계다 — 셀 단위 집계도 위치정보이기 때문이다. `target_cell`은 서버 정책 해상도(res7/8/9)로 폰에서 변환한 현재 위치 셀이며 기본 res9는 기존 res7보다 작은 위치 구역을 드러낸다. 현재 셀만 덮어쓰고 좌표·이동 이력을 보내지 않는다. 인증 웹 위치와 새 fine 셀은 5분 후 발송 대상에서 제외되며, 이는 위치 값 자체의 자동 삭제를 뜻하지 않는다. 기존 `cell_res7`은 지리적 겹침 근사로 지원하고 fine 위치를 복원하지 않는다. 웹 null은 현재 셀을 지우고 native null은 이전 관측의 시각을 갱신하지 않는다. 서로 다른 두 위치 필드 또는 잘못된 H3는 422다. 웹 `owner_id`는 인증 브리지에서 주입한다. native `/devices`의 Cloud 브리지/EAS 실기기 연결과 외부 푸시 수신은 이 변경의 검증 범위가 아니다. `reporter_user_id`는 Tip에 저장하지 않고 카운터만 올린다.

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

자동 파기 관제 API는 `X-Privacy-Admin-Key` 헤더가 설정된 운영 환경에서 관리자 키가
필요하다. 응답의 작업 목록에서는 대상 내부 ID를 제외한다. 화면은 별도 구현이며,
이 API가 제공하는 상태를 사용한다.

| 메서드 | 경로 | 요청/쿼리 | 응답 |
|---|---|---|---|
| GET | `/privacy/automation/status` | — | 최근·다음 실행, 생존 신호, 기한 초과·재시도·최종 실패 건수 |
| GET | `/privacy/automation/runs` | `?page=1&size=50` | 실행 회차 목록과 검사·성공·실패 수 |
| GET | `/privacy/automation/jobs` | `?page=1&size=50` | 작업 상태·단계·시도 횟수·다음 재시도 시각 |
| POST | `/privacy/automation/jobs/{job_id}/retry` | — | `{ job_id, state }` — 관리자 수동 재시도 예약 |

### 디버그·관제 (debug) — 시연·검증용, 프로덕션 계약 아님

| 메서드 | 경로 | 요청/쿼리 | 응답 |
|---|---|---|---|
| GET | `/debug/overview` | — | 페르소나·인터뷰·케이스 목록. 관제 대시보드가 케이스 목록으로 사용 |
| POST | `/debug/cases/{case_id}/predict` | `?seed=` | 워커 궤적·EXAONE 이벤트 트레이스 포함 재예측 |
| GET | `/debug/cases/{case_id}/bundle` | — | 케이스+페르소나+인터뷰+트레이스+4층 POA 종합 |
| GET | `/debug/cases/{case_id}/buildings` | `?radius_m=800` | LKP 반경 건물 폴리곤+높이(첫 호출은 수십 초) |

> 공통 에러: 리소스 없음 `404`, POA 없이 알림·제보·조회 시도 `409`("Phase 2 예측을 먼저"), 종결 케이스에 예측·알림·제보 시도 `409`.

---

## 앱의 일반 흐름

```text
1. Supabase 로그인
2. POST /phase0/interviews/sessions               → session_id
3. POST /phase0/interviews/sessions/{id}/messages  → 보호자 대화, 등록 확정
4. POST /phase0/interviews/sessions/{id}/complete  → persona_id 및 등록 상태 조회
5. POST /phase1/reports                           → case_id, 1차 경보 경로
6. 신고 완료 화면이 /phase2/cases/{id}/predict 자동 요청 → 서버 계산
7. GET /phase3/cases/{id}/poa                     → 지도 조회
8. POST /phase3/cases/{id}/tips                   → 처리 결과, 필요한 재예측은 백그라운드
9. GET /phase3/cases/{id}/poa                     → 저장 지도 또는 갱신 결과
10. POST /phase1/cases/{id}/close                 → 보호자 종결, 보관/파기 절차
```

예측 완료 시 알림 경로는 서버에서 처리한다. `/predict`와 `/alerts` 수동 호출은 진단용이며 일반 사용자에게 추가 실행을 요구하지 않는다. `frontend/tests/tip-submit-no-wait.test.cjs`, `backend/tests/test_tip_deferred_reprediction.py`, `backend/tests/test_cloud_bridge.py`는 응답과 재계산 분리를 검사한다.

### 자동 파기 재시도 시 대상 재확인 (2026-09-28)

실행 직전 대상의 현재 상태와 만료 시각을 다시 확인한다. 인터뷰가 등록 완료되었거나 다시 사용되어 만료 전이면 삭제하지 않는다. 수색 중인 사건 또는 아직 만료되지 않은 사건도 삭제하지 않는다. 기존 작업은 `state=cancelled`, `stage=eligibility_changed`로 종료하고 회차의 `skipped_count`에 집계한다. 성공적으로 삭제한 수에 포함하지 않는다. 이후 다시 만료되면 새 작업으로 등록할 수 있다. 취소 작업도 완료 작업과 같은 제어 기록 보존 기간을 적용한다.

관리자 키 미설정은 503, 미제공·불일치는 403이다. 제어 API와 자동 워커는 단일 프로세스·SQLite 기준이다. 이번 검증은 격리된 합성 데이터로 수행했으며 운영 데이터 파기는 실행하지 않았다.

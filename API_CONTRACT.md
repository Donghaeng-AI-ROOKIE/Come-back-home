# 돌아오길 API 계약 (v0.1) — front ↔ back 공유 진실

> 이 문서가 **유일한 계약**이다. 프론트 목(mock)은 이 스펙을 흉내내고, 백엔드는 이 스펙을 구현한다.
> 둘은 서로 안 붙어 있어도 각자 이 계약을 상대로 개발한다. **계약을 바꾸려면 이 문서를 먼저 고치고 양쪽에 공지.**
> 출처: `backend/app/api/*.py` + `backend/app/schemas/*.py` (feat/backend-skeleton, 2026-07-09 기준 자동 추출).
> 갱신 2026-07-25: 백엔드에 실존하나 미문서였던 엔드포인트(reflex-alerts · privacy 6종 · debug) 문서화 — 관제 대시보드(PR #71) 정합.

- Base URL: `http://localhost:8000` (로컬), Swagger: `/docs`
- 모든 시각은 **ISO 8601** 문자열. 좌표는 `{lat, lng}`.
- **스텁 모드:** API 키(EXAONE/Mi:dm/VARCO/Upstage)가 없으면 백엔드가 **유효한 모양의 가짜 응답**을 반환 → 프론트는 지금 당장 실 배선·렌더 검증 가능. 실 AI는 나중에 스텁 자리에 교체.
- **데모 케이스 미리 seed됨:** 서버 부팅 시 정릉동 김순자 케이스가 `case_id="case-jeongneung-001"`(프론트 `DEMO_CASE_ID`와 동일) 로 자동 생성·예측까지 완료. 프론트는 케이스 생성 없이 **`GET /phase3/cases/case-jeongneung-001/poa` 로 바로** 실 데이터 히트맵 검증 가능. CORS 도 열려 있음(`*`).

---

## ⚠️ 프론트가 꼭 알아야 할 3가지

1. **POA 응답에 폴리곤이 이미 포함됨** — `GET .../poa`의 각 셀이 `{ cell, prob, polygon: [{lat,lng} × 6] }` 로 온다. **프론트는 `polygon`을 지도에 그대로 렌더**하면 됨(h3-js 변환 불필요 — 백엔드가 처리). H3 res-9 ≈ 육각형 변 174m.
2. **`with_photo` / `with_document` 플래그는 백본 단계 스텁.** 지금은 `true/false`만; 실제 구현 시 multipart 파일 업로드로 교체 예정. 프론트는 우선 플래그로 붙이면 됨.
3. **POA는 `{셀ID: 확률}` dict, 합=1.** 상위 셀만 필요하면 `GET .../poa?top=N` 사용.

---

## 데이터 모델

```jsonc
GeoPoint            { "lat": 37.61, "lng": 127.01 }
PersonaType         "dementia" | "intellectual_disability"
CaseStatus          "intake" | "predicted" | "searching" | "found" | "closed"
TipDecision         "discard" | "layer1" | "layer2"

AttractionPoint     { "label": "옛집(정릉동)", "location": GeoPoint, "weight": 1.0 }

RouteFamiliarity   { "route": "옛 직장", "score": 0.9 }   // 경로별 익숙함 — route_familiarity_compiler 가 채움. route 는 끌림점 라벨
EnvResponse        { "feature": "water", "direction": "접근", "strength": 0.9 }   // 개인 환경 반응. feature 는 water|forest|park|market 닫힌 어휘

Persona {
  "id": str, "type": PersonaType, "name": str, "age": int,
  "home": GeoPoint,
  "attraction_points": [AttractionPoint],
  "behavior_notes": [str],           // "해질녘 옛직장 방향으로 걷는 습관" 등
  "axis_evidence": { "mobility_transport_capacity": [str], ... },  // 축별 근거 노트(Mi:dm 재서술)
  "axis_scores": { "mobility_transport_capacity": 0.5, ... },      // 축 점수(0.1~0.9), F·근거없음 축은 키 자체가 없음
  "axis_scoring_report": {},                                      // 채점 진행상태·F율·quote검증 등 디버그용
  "route_familiarity": [RouteFamiliarity],  // 경로별 관계 변수 — 자전적 목적지 유래 끌림점만 컴파일(PR #44)
  "env_responses": [EnvResponse],           // 개인 환경 반응 {feature, direction, strength} — behavior_notes 에서 컴파일(PR #56)
  "created_at": datetime
  // "axis_quotes" 는 응답에 없음 — 모델에는 있지만 API 는 response_model_exclude 로 제외(아래 참고)
}
// ⚠️ axis_quotes 는 보호자가 실제로 한 말 그대로(quote 검증용 원문) — 민감도 때문에 POST/GET
// /phase0/personas 양쪽 다 response_model_exclude 로 API 응답에서 뺐다(저장·채점 로직엔 영향 없음).

InterviewSession {
  "id": str, "guardian_name": str,
  "messages": [ {"role": "assistant"|"user", "text": str} ],
  "done": bool, "persona_id": str|null
}

Appearance   { "top","bottom","shoes","physical","summary": str, "accessories": [str] }  // VARCO 추출
ReporterInfo { "name","relation","phone": str, "extra": {} }                              // Upstage 추출
MissingReport {
  "id": str, "persona_id": str|null, "missing_type": PersonaType,
  "lkp": GeoPoint, "lkp_time": datetime,
  "appearance": Appearance|null, "reporter": ReporterInfo|null, "created_at": datetime
}

PriorParams {           // EXAONE Top-down 출력 (좌표 아님)
  "strategy_probs": { "route_traveling": 0.6, ... },   // Hashimoto 6전략, 합=1
  "attraction_weights": { "옛집(정릉동)": 0.55, ... },  // 합=1
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
  "last_sim_at": datetime|null, "tips": [Tip]
}

Tip {
  "id": str, "case_id": str, "text": str,
  "location": GeoPoint|null, "seen_at": datetime|null,
  "p": float|null,                    // 신뢰도
  "decision": TipDecision|null, "created_at": datetime
}
```

---

## 엔드포인트

### Phase 0 — 온보딩 (보호자 사전등록)
| 메서드 | 경로 | 요청 body | 응답 |
|---|---|---|---|
| POST | `/phase0/interviews` | `{ guardian_name }` | InterviewSession |
| POST | `/phase0/interviews/{session_id}/answers` | `{ text }` | InterviewSession |
| POST | `/phase0/personas` | `{ session_id?, name, age, type, home, attraction_points[], behavior_notes[] }` | Persona |
| GET | `/phase0/personas/{persona_id}` | — | Persona |

### Phase 1 — 실종 신고 접수
| 메서드 | 경로 | 요청 body | 응답 |
|---|---|---|---|
| POST | `/phase1/reports` | `{ missing_type, lkp, lkp_time, persona_id?, with_photo, with_document }` | Case |
| GET | `/phase1/cases/{case_id}` | — | Case |

### Phase 2 — 동선 예측
| 메서드 | 경로 | 쿼리 | 응답 |
|---|---|---|---|
| POST | `/phase2/cases/{case_id}/predict` | `?seed=` (재현용, 선택) | PredictionResult `{ case_id, prior, poa_topdown, poa_bottomup, poa_statistical, poa_combined }` |

### Phase 3 — 알림·제보·POA
| 메서드 | 경로 | 요청/쿼리 | 응답 |
|---|---|---|---|
| POST | `/phase3/cases/{case_id}/reflex-alerts` | — | `{ case_id, target_cells, message, sent, note }` — LKP 반경 19셀 1차 경보(D1). **신고 접수 시 자동 발송됨**(`reflex_alert_on_intake=True` 기본, 실패해도 접수는 계속) — 이 엔드포인트는 수동 재발송용 |
| POST | `/phase3/cases/{case_id}/alerts` | — | `{ case_id, target_cells, message, sent, note }` |
| POST | `/phase3/cases/{case_id}/tips` | `{ text, location?, seen_at?, force? }` | **Tip 또는 되묻기 응답** (아래 참고). `decision`으로 파기/층1/층2 판정 — 시민 제보 사진 대조는 하지 않기로 확정되어 `with_photo` 제거됨 |

> ⚠️ `POST /tips` 는 두 가지 형태를 반환한다. 프론트는 `status` 키 유무로 분기해야 한다.
>
> - **Tip 객체** — 정상 접수. 저장·POA 갱신까지 완료됨
> - **`{ "status": "need_more", "missing": ["location"|"time"], "reason"?: str }`** — 저장하지 않고 되묻기를 요청. 프론트가 부족한 항목만 받아 **합친 전체 텍스트로 재제출**하거나 `force: true` 로 그대로 확정한다. `reason` 은 시각 분기에서만 오는 사유 코드(현재 `"layer2_needs_time"` 뿐) — 위치 분기 응답에는 없음
>
> `text` 는 자유 텍스트 한 덩어리다. 위치·시각은 별도 필드가 아니라 이 텍스트에서 구조화·지오코딩·시각 변환으로 뽑는다(`location`·`seen_at` 은 지도 핀 등 명시값이 있을 때만 사용).
| GET | `/phase3/cases/{case_id}/poa` | `?top=20` | `{ case_id, total_cells, top_cells: [{ cell, prob, polygon:[{lat,lng}×6] }] }` |
| GET | `/phase3/cases/{case_id}/rerun-check` | — | `{ case_id, should_rerun, reason }` |

> 에러: 리소스 없음 `404`, POA 없이 알림/제보/조회 시도 `409`("Phase 2 예측을 먼저").

### 종결·개인정보 파기 (privacy)
| 메서드 | 경로 | 요청 body | 응답 |
|---|---|---|---|
| POST | `/privacy/cases/{case_id}/close` | `{ reason: "found"\|"withdrawn" }` | Case — `closed_at` 기록, 5일(`privacy_retention_days`) 후 자동 파기 예약 |
| GET | `/privacy/cases/{case_id}/retention` | — | `{ case_id, status, closed_at, retention_days, purge_due_at, expired }` (종결 전 `purge_due_at=null`) |
| DELETE | `/privacy/cases/{case_id}` | — | `{ purged, case_id }` — 명시 삭제요청, 즉시 파기. 수색 중이면 `409`(철회 종결이 먼저) |
| DELETE | `/privacy/personas/{persona_id}` | — | `{ purged, persona_id }` — 페르소나·인터뷰·종결된 연결 케이스 동반 파기. 수색 중 케이스 연결 시 `409` |
| POST | `/privacy/purge-expired` | — | `{ purged_case_ids, purged_interview_ids, count }` — TTL 만료분 일괄 파기(스케줄러 수동 트리거) |
| GET | `/privacy/audit` | — | `[AuditRecord]` — 파기 증적(개인정보 미포함, ID·행위·사유 코드만) |

### 디버그·관제 (debug) — 시연·검증용, 프로덕션 계약 아님
| 메서드 | 경로 | 요청/쿼리 | 응답 |
|---|---|---|---|
| GET | `/debug/overview` | — | `{ personas: [{id,name,age,type,n_attractions,n_notes}], interviews: [{id,guardian_name,done,persona_id,n_messages}], cases: [{id,status,persona_id,lkp,lkp_time,has_trace}] }` — 관제 대시보드가 케이스 목록으로 임시 사용(관제 전용 목록 API 승격 예정) |
| POST | `/debug/cases/{case_id}/predict` | `?seed=` | PredictionDebug — 워커 궤적·EXAONE 이벤트 트레이스 포함 재예측 |
| GET | `/debug/cases/{case_id}/bundle` | — | 케이스+페르소나+인터뷰+트레이스+4층 POA 폴리곤 종합(1회 로딩 번들) |
| GET | `/debug/cases/{case_id}/buildings` | `?radius_m=800` | LKP 반경 내 건물 폴리곤+높이(envlayer, OSM — 첫 호출은 수십 초) |

---

## 데모 시나리오 호출 순서 (정릉동 김순자 9단계)

```
1. POST /phase0/personas            → persona_id  (사전등록 완료)
2. POST /phase1/reports             → case_id     (실종 발동, LKP·유형)
3. POST /phase2/cases/{id}/predict  → POA          (예측 지도)
4. GET  /phase3/cases/{id}/poa      → 히트맵 렌더  (H3→폴리곤 변환)
5. POST /phase3/cases/{id}/alerts   → 타겟 알림    (상위 80% 셀)
6. POST /phase3/cases/{id}/tips     → Tip(decision) (시민 제보 → 층1/층2)
7. GET  /phase3/cases/{id}/poa      → 좁혀진 히트맵 (제보 반영됨)
8. GET  /phase1/cases/{id}          → 발견/종료 상태 확인
```

프론트는 이 순서대로 목을 채우고, 백엔드는 이 순서가 스텁으로 실제 돈다(테스트 `test_e2e_flow.py`가 이미 통과). → **프론트 `USE_MOCK=false` + `localhost:8000` 가리키면 지금 실 배선 검증 가능.**

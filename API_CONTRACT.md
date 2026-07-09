# 돌아오길 API 계약 (v0.1) — front ↔ back 공유 진실

> 이 문서가 **유일한 계약**이다. 프론트 목(mock)은 이 스펙을 흉내내고, 백엔드는 이 스펙을 구현한다.
> 둘은 서로 안 붙어 있어도 각자 이 계약을 상대로 개발한다. **계약을 바꾸려면 이 문서를 먼저 고치고 양쪽에 공지.**
> 출처: `backend/app/api/*.py` + `backend/app/schemas/*.py` (feat/backend-skeleton, 2026-07-09 기준 자동 추출).

- Base URL: `http://localhost:8000` (로컬), Swagger: `/docs`
- 모든 시각은 **ISO 8601** 문자열. 좌표는 `{lat, lng}`.
- **스텁 모드:** API 키(EXAONE/Mi:dm/VARCO/Upstage)가 없으면 백엔드가 **유효한 모양의 가짜 응답**을 반환 → 프론트는 지금 당장 실 배선·렌더 검증 가능. 실 AI는 나중에 스텁 자리에 교체.
- **데모 케이스 미리 seed됨:** 서버 부팅 시 정릉동 김순자 케이스가 `case_id="demo"` 로 자동 생성·예측까지 완료. 프론트는 케이스 생성 없이 **`GET /phase3/cases/demo/poa` 로 바로** 실 데이터 히트맵 검증 가능. CORS 도 열려 있음(`*`).

---

## ⚠️ 프론트가 꼭 알아야 할 3가지

1. **POA 응답에 폴리곤이 이미 포함됨** — `GET .../poa`의 각 셀이 `{ cell, prob, polygon: [{lat,lng} × 6] }` 로 온다. **프론트는 `polygon`을 지도에 그대로 렌더**하면 됨(h3-js 변환 불필요 — 백엔드가 처리). H3 res-9 ≈ 육각형 변 174m.
2. **`with_photo` / `with_document` 플래그는 백본 단계 스텁.** 지금은 `true/false`만; 실제 구현 시 multipart 파일 업로드로 교체 예정. 프론트는 우선 플래그로 붙이면 됨.
3. **POA는 `{셀ID: 확률}` dict, 합=1.** 상위 셀만 필요하면 `GET .../poa?top=N` 사용.

---

## 데이터 모델

```jsonc
GeoPoint            { "lat": 37.61, "lng": 127.01 }
PersonaType         "dementia" | "child" | "intellectual_disability"
CaseStatus          "intake" | "predicted" | "searching" | "found" | "closed"
TipDecision         "discard" | "layer1" | "layer2"

AttractionPoint     { "label": "옛집(정릉동)", "location": GeoPoint, "weight": 1.0 }

Persona {
  "id": str, "type": PersonaType, "name": str, "age": int,
  "home": GeoPoint,
  "attraction_points": [AttractionPoint],
  "behavior_notes": [str],           // "해질녘 옛직장 방향으로 걷는 습관" 등
  "created_at": datetime
}

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
  "location": GeoPoint|null, "seen_at": datetime|null, "has_photo": bool,
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
| POST | `/phase3/cases/{case_id}/alerts` | — | `{ case_id, target_cells, message, sent, note }` |
| POST | `/phase3/cases/{case_id}/tips` | `{ text, location?, seen_at?, with_photo }` | Tip (`decision`으로 파기/층1/층2 판정) |
| GET | `/phase3/cases/{case_id}/poa` | `?top=20` | `{ case_id, total_cells, top_cells: [{ cell, prob, polygon:[{lat,lng}×6] }] }` |
| GET | `/phase3/cases/{case_id}/rerun-check` | — | `{ case_id, should_rerun, reason }` |

> 에러: 리소스 없음 `404`, POA 없이 알림/제보/조회 시도 `409`("Phase 2 예측을 먼저").

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

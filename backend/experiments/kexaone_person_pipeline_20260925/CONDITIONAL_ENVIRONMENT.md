# 조건별 환경 반응 계약

보호자 원문 ‘시장이 붐비고 시끄러울 때만 피한다’를 K가 의미 해석한다. 아래는 **코드 설명용 예시**이며 실제 v41 모델 출력에 새 필드를 덧붙인 것이 아니다.

```json
{"response":"avoid","scope":"conditional_category","condition":"present","note_ids":["N3"],"condition_clauses":[[{"signal":"crowded","state":"present"},{"signal":"noisy","state":"present"}]]}
```

위 조건은 혼잡 AND 소음이다. OR이면 두 항을 서로 다른 안쪽 배열에 넣는다. 근거 없는 조건식은 빈 배열로 보류한다. `noisy=absent`는 소음 없음이 관측돼야 하며, 미확인은 충족하지 않는다. 특정 장소 한 곳 회피, 어두움·날씨 등 미지원 조건은 임의로 혼잡/소음으로 바꾸지 않는다.

## 환경 관측 입력

기존 `POST /phase1/reports`에 선택적 `environment_observations` 배열을 추가했다. 보호자 성향과 별개이며 지도에서 자동 추론하지 않는다.

```json
{
  "missing_type":"dementia",
  "lkp":{"lat":37.6061,"lng":127.0106},
  "lkp_time":"2026-09-25T22:00:00",
  "environment_observations":[{
    "feature":"market",
    "location":{"lat":37.6061,"lng":127.0106},
    "radius_m":100,
    "valid_from":"2026-09-25T22:00:00",
    "valid_until":"2026-09-25T22:05:00",
    "crowded":true,
    "noisy":true,
    "source":"synthetic_scenario"
  }]
}
```

좌표·날짜는 합성 예시다. `source`는 입력 출처 표기이며 진실 보증이 아니다. 실제 관측의 공급·검증 체계와 프론트 UI는 별도 작업이다. 실시간 센서/API는 연결하지 않았다.

관측은 반경 0초과~500m, 시각은 valid_from 포함/valid_until 미포함, 신호는 true/false/null이다. 한 요청 최대 100개. 동일 지점·시간·환경 유형에서 관측이 상충하면 그 신호를 미확인으로 처리한다. 시뮬레이션의 각 보행 단계 시각으로 적용하며 캐시 도로망을 수정하지 않는다. 도로망 실패 시 연속공간 폴백에는 적용되지 않는다.

## 설정 및 실행

`KEXAONE_API_KEY`, `KEXAONE_BASE_URL`, `KEXAONE_MODEL`이 설정된 서버에서 초기 예측 시 K 해석이 연결된다. `.env.example`에 키 없는 항목을 추가했다. 추가 기능 스위치는 없다. 자동 재시도 없이 정상 K 3회이며, 실패 시 SAR 복귀 상태를 기록한다. `RESEARCH_USAGE_LEDGER_PATH`는 영속 저장 위치를 지정해야 한다. 모델 단가·지원 차수·실청구액은 정산 자료가 없으면 null이다.

신고마다 관측을 전달할 수 있으며, 관측 없이 ‘시장’이라는 이유만으로 회피를 활성화하지 않는다. 시간별 POA는 같은 사건별 조건을 사용한다. 이 조건 처리에는 새 LLM 호출이 없다.

# 개인 행동 조건과 연속 보행 후보

**2026-10-06 후속:** [시간별 보행 수정·146회 추가 요청·실제 K 출력 보행 진단](FOLLOWUP_20261006.md). 최신 기록은 이 문서를 먼저 읽는다. 아래는 #265 당시 결과이며, 이전 해시 검증기는 당시 커밋 `2d6af78`에서 실행한다. 현재 작업본은 `python -m experiments.mind_policy_candidates.verify_followup_evidence`로 공개 자료와 저장 출력 점수를 확인한다.

**운영 채택 미통과.** 기존 K 초기 해석·SAR·운영 마음모델은 교체하지 않았다. 새 후보는 코드 계약과 조건 해석의 실패를 포함해 평가했다.

[전체 결과·흐름·그림·비용](evidence_20261004/완성검증_결과.md)

[처음 읽는 팀원을 위한 통합 안내](REVIEW_GUIDE.md)에서 1차 연속 실호출과 2차 조건 해석 실험의 관계, 기존 PR과의 범위를 확인할 수 있다.

최초 고정 24개 평가와 후속 13개 원문 검토를 분리한다. 모델 출력이 유효한 것과 개인 행동이 타당한 것은 다르다. 이 폴더의 증거는 합성 자료이며 실제 환자 정확도 자료가 아니다. 큰 OSM GraphML은 외부 작업 폴더에 보존하며 해시와 취득 명세를 함께 제공한다.

## 추가 호출 없는 자료 확인

`backend` 디렉터리에서 실행한다. 저장된 최종 응답을 다시 파싱하고 같은 행동 검사에 대입해 9/24·15/38 및 후속 18/24·27/38을 재계산한다. 구현 해시·사용량 정산·문서 링크도 확인한다. 어떤 모델이나 지도 API도 호출하지 않는다.

```sh
python -m experiments.mind_policy_candidates.verify_evidence
python -m pytest -q tests/test_person_policy.py tests/test_person_walk_dynamics.py tests/test_continuous_prediction.py
```

공간 회귀는 저장소의 KINTEX fixture를 사용한다. 500명 규모 성능 측정에 쓴 확대 지도는 크기 때문에 포함하지 않았으므로, 그 측정값은 보존된 결과와 지도 명세로 검토한다. 위 명령이 확대 지도 성능 측정까지 다시 실행하는 것은 아니다.

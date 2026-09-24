# 문헌 기반 합성 타겟팅 시나리오

새 폴더에서 시나리오와 정답을 먼저 고정한 뒤, 기존 V2 산출물을 재사용하지 않고 새 입력으로 EXAONE 예측과 타겟팅 분석을 실행했다.

## 읽는 순서

1. `SOURCES.md`: 두 논문의 근거와 연구자가 추가한 가정.
2. `PROTOCOL.md`: 비교 대상, 개발/평가 분할, 지표, 판정, 실행 단계.
3. `SCENARIO_REVIEW.md`: 개발용 인물별 세 사건의 구체적인 예시.
4. `dataset_v1/SCENARIOS.md`: 전체 36개 사건 목록.
5. `VALIDATION.json`: 데이터 생성 검증 결과.
6. `EXECUTION.md`: 실제 모델 실행 조건과 재시도 기록.
7. `RESULTS.md`: 개발/평가 결과의 핵심 해석.

## 생성물

- `dataset_v1/development_inputs.json`, `evaluation_inputs.json`: 모델용 B/C 입력. 정답과 조건명 없음.
- `dataset_v1/development_truth.json`, `evaluation_truth.json`: 평가 전용 경로와 시점별 좌표. 모델에 주지 않는다.
- `dataset_v1/manifest.json`: 코드·문헌 문서·프로토콜·도로망·데이터 해시와 표본 수.

총 12명, 36개 사건, 144개 대응 시점. 개발/평가 각각 6명, 18개 사건, 72시점. 각 인물의 세 사건은 같은 개인화 정보를 공유한다. 사례마다 다른 미래를 모델에게 미리 알려주지 않는다.

## 재현

저장소 루트에서 실행한다. Python 패키지 networkx, shapely, h3가 필요하다.

```powershell
python -B -X utf8 backend/experiments/literature_targeting_20260924/build_dataset.py --output backend/experiments/literature_targeting_20260924/dataset_v2
python -B -X utf8 backend/experiments/literature_targeting_20260924/validate_dataset.py
```

첫 명령은 새 경로에만 생성하며 기존 폴더 덮어쓰기를 거부한다. 두 번째 명령은 기본 dataset_v1을 검증한다. 별도 경로 검증은 `--dataset`으로 지정한다. 예측 실패를 좋은 결과로 바꿀 수 있는 모의 예측은 생성하지 않는다.

## 다음 단계와 제약

정답과 모델 입력의 파일 분리, 새 예측 실행, res7/res8 타겟팅 분석까지 완료했다. 이전 실험의 예측을 새 정답에 붙인 결과가 아니라, dataset_v1 입력으로 새로 생성한 predictions_v2를 분석했다.

기존 라이브 러너는 신고 생성 시 실제 알림 경로에 들어갈 수 있어 사용하지 않았다. 신고 API, 푸시 함수, 실제 기기 대상 발송은 호출하지 않았다.

원하는 효과가 나오는 조건을 탐색하는 자료이며 현실 발생빈도를 추정한 표본은 아니다. 같은 합성 규칙이 개인화 단서와 정답을 연결한다는 가정 자체가 성능에 영향을 준다. 유효 조건과 이탈/불일치 조건을 따로 공개하고, 실제 환자 데이터로 검증한 것으로 표현하지 않는다.

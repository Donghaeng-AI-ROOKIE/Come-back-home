# 81행 문구 수정: personal_contrasts_v6

**기계적 학습 후보 검증 PASS. 아직 학습하지 않았으며 모델 성능을 새로 측정하지 않았다.**

PR #262의 `personal_contrasts_v5`에 있던 `PC009_P1`, `PC023_P1`, `PC037_P1`의
각 27행(9관측 × 3표현), 총 81행에서 조건에 따라 행동이 달라지지 않는데도
‘때만’, ‘겹쳐야’, ‘하나만 해당할 때까지 같은 반응이라고 말한 건 아니’라고 적은 모순을 수정했다.
두 조건이 모두 참·하나만 참·모두 거짓인 경우에 같은 이동을 지속한다는 뜻을 명시했다.
미확인은 거짓으로 바꾸지 않는다. 이 세 프로필은 가능한 모든 조건에서 행동이 같으므로
미확인이 남아도 `continue`이며, 조건에 따라 반응이 달라지는 비교 프로필은 `defer`가 될 수 있다.
관찰한 행동의 주체가 대상자라는 점도 명시해 보호자의 부탁이나 타인의 행동과 구별했다.

## 변경 범위와 보존

- 변경 필드: `/context/person/evidence_notes/0/text` 하나. 81행 이외 2,079행은 동일하다.
- 정답 명령·설명·출처 ID, 관측, 피로 proxy, ID, split, authoring oracle, 기존 품질/검토 플래그는 그대로다.
- 개발 180행과 평가 360행은 원본과 바이트 단위로 같다. 평가 프로필 `PC051_P1`, `PC065_P1`의 문구 주의사항도 남아 있다.
- `evidence/` 안의 과거 데이터·응답·점수·주의사항·보고서·코드를 수정하지 않는다. 동결 점수 72/80·71/80·15/16과 과거 96행 학습의 5/8·4/8은 재채점하지 않았다.
- 운영 모델·프롬프트·실행기는 변경하지 않는다. 자료 작성용 oracle은 모델 입력에 넣지 않는다.

## 새 버전 구성

v6는 **해시로 고정한 v5 + 9개 문구 교체 명세 + 결정적 생성기**로 보관한다.
같은 문구가 관측 9개에 반복되므로 문구 9개가 학습 행 81개에 적용된다.
8 MB 원본과 대형 SFT 파일을 중복 커밋하지 않고, 아래 명령으로 완전한 새 파일을 만든다.
`source_pins.json`은 부모 데이터와 사용한 계약 코드를 고정하며, 원본이 다르거나
81행보다 많거나 적게 바뀌면 생성을 중단한다. 기존 출력 폴더도 덮어쓰지 않는다.

| 파일 | 역할 |
|---|---|
| `replacements.json` | 3프로필 × 3표현의 수정 전/후 원문 |
| `changes.jsonl` | 실제 변경 81개 ID·경로·전후 문구 해시 |
| `dataset_manifest.json` | 생성되는 v6 학습/개발/평가 수량과 SHA-256 |
| `export_manifest.json` | SFT 학습 2,160행, 기본 표현 720행, 개발 180행 해시 |
| `mechanical_report.json` | 2,700행 계약·oracle·관측·출처·분할·개인 대비 일관성 검증 |
| `regression_report.json` | 회귀 검사 실행 결과와 검사 대상 코드 해시 |
| `tokenization_report.json` | 수정된 SFT의 새 CPU 토큰화 결과 |
| `readiness.json` | 위 결과와 현재 파일 해시를 종합한 기계적 준비 상태 |

## 재현

저장소 루트에서 실행한다. 생성·기계적 검증에는 Python 표준 라이브러리만 사용한다.

```bash
python backend/experiments/mind_alignment_20260930/revisions/wording_v6/build.py
python backend/experiments/mind_alignment_20260930/revisions/wording_v6/verify.py
```

생성 결과는 같은 폴더의 `generated/personal_contrasts_v6/`와
`generated/training_export_v3/`다. 학습 후보의 실제 입력은 후자의 `train.jsonl`이다.
`train_base.jsonl`은 720개 기본 표현 부분집합이므로 2,160행에 덧붙이지 않는다.
평가 자료는 SFT 내보내기에 포함하지 않는다. `verify.py`는 저장된 검증 결과의
해시가 현재 생성 파일과 일치하는지 다시 확인하며 토큰화를 실행하는 명령은 아니다.

새 회귀 검사:

```bash
python -m pytest -q backend/experiments/mind_alignment_20260930/revisions/wording_v6/test_wording_v6.py
```

CPU 토큰화 재실행에는 `transformers==4.57.6`, `tokenizers==0.22.2`,
`jinja2==3.1.6`과 `tokenizer_pin.json`에 고정된 EXAONE 토크나이저 파일이 필요하다.
검증기는 네트워크 다운로드나 원격 코드를 실행하지 않으며 모델 가중치를 사용하지 않는다.
기존 `preflight.encode_supervision`을 그대로 사용하여 프롬프트 마스킹,
정답 토큰 보존, 텍스트 왕복 일치, 길이 초과 시 잘라내기 대신 실패를 확인한다.

```bash
python backend/experiments/mind_alignment_20260930/revisions/wording_v6/validate_tokens.py \
  --tokenizer-path /absolute/path/to/pinned-tokenizer \
  --out /tmp/wording-v6-tokenization-new.json
```

## 회귀 검사의 의미와 한계

독립적으로 적은 진리표로 7종 조건 × 참/거짓/미확인 9조합을 검사한다.
불변 프로필 9조합과 81행 수정 범위도 확인한다. 별도 합성 회귀 사례 17개는
대상자 관찰, 보호자 부탁만 있는 경우, 타인의 행동만 있는 경우, 서로 충돌하는
다른 출처가 함께 있는 경우, 목적지만 다르고 경로 관계가 제공되지 않은 경우를 포함한다.
실제 입력 생성 함수를 통과시켜 원문·주체·관측 지식 상태가 보존되는지 검사하고,
미확인→거짓 치환, 잘못된 출처, 목적지를 이유로 회피 취소, 같은 목표로 불필요한 `seek`
선택을 탐지할 수 있는 부정 대조를 둔다.

**이 검사는 자유로운 자연어를 완벽히 이해하는 모델이 완성됐다는 증거가 아니다.**
17개 사례의 기대값은 독립 작성한 합성 라벨이며 실제 모델 응답이 아니다.
`regression.py --responses FILE`은 향후 수집한 `{id, output}` JSONL을 별도로
채점할 수 있지만 이번 작업에서 모델 호출은 0회다. 자유 서술 설명의 출처·경로 추정 오류는
명령 일치만으로 검출되지 않을 수 있어 별도 의미 검토가 필요하다.

81행 문구 차단 사유와 기계적/토큰화 차단 사유는 해소됐다. 기존 행의 검토 대기 플래그는
보존했으며 독립 보호자·임상 검토, 실제 학습, 학습 후 성능 검증은 수행하지 않았다.
모든 직전 동작이 `seek`, 경과 시간이 60분인 기존 커버리지 한계도 그대로다.
`mechanically_ready_training_candidate=true`는 이 범위의 합성 학습 후보 준비 완료를 뜻하며
전체 마음모델의 학습 승인이나 운영 배포 적합 판정이 아니다.

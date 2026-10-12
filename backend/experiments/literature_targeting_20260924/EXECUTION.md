# 새 시나리오 예측 실행 기록

기존 V2 예측 산출물을 재사용하지 않고 새 입력으로 실제 EXAONE을 호출한다. 신고 API나 푸시 함수는 사용하지 않는다. dataset_v1과 PROTOCOL.md는 고정 상태로 보존한다.

## 실행 조건

- prior: exaone-sar, 마음 재해석: exaone-mind-dem5.
- 기존 프로젝트 generate_prior, run_monte_carlo(agent/statistical), alpha_pool(0.7/0.3, linear)를 호출한다.
- seed 42, 워커 수와 마음 호출 예산은 predictions_v1/config.json의 실행 당시 설정을 사용한다.
- 입력마다 prior 한 번을 생성하고 신고 후 0/15/30/60분에 재사용한다.
- B/C 공통 정보는 동일하다. C에만 사전등록 산책 목적지(caregiver_report, weight 0.5)와 보호자 설명을 전달한다.
- 현재 Persona/예측 경로에 전체 산책 경로 좌표를 전달하는 동등한 입력이 없어 routine_route는 사용하지 않는다. 따라서 이번 실행은 전체 경로 개인화가 아닌 목적지·설명 개인화의 비교다.
- 두 군 모두 고정된 저장 도로망을 사용하고 주변 환경 레이어는 제외한다. 당시 V2의 배포 환경과 완전히 같지 않다. 효과는 이번 동일 조건의 B/C 사이에서 해석한다.
- 모델 실패 시 통계 스텁으로 계속하지 않고 중단한다. 실제 입력, prior, 모델 호출 기록과 시점별 res9 분포를 저장한다.

## 실행과 재개

backend에서 실행한다. 네트워크 접근과 SSH 터널이 필요하다. 키 파일 내용을 읽지 않는다.

```powershell
python -B -X utf8 -m experiments.literature_targeting_20260924.run_predictions --split development
python -B -X utf8 -m experiments.literature_targeting_20260924.run_predictions --split evaluation
python -B -X utf8 -m experiments.literature_targeting_20260924.analyze_predictions --split development --output experiments/literature_targeting_20260924/results/development_v1
python -B -X utf8 -m experiments.literature_targeting_20260924.analyze_predictions --split evaluation --output experiments/literature_targeting_20260924/results/evaluation_v1
```

예측은 사건/군 단위 JSON을 저장하며 같은 명령을 다시 실행하면 완료 파일을 건너뛴다. 완료되지 않은 사건/군은 다시 계산한다. 평가용은 개발용 실행 완료 표시가 있을 때만 시작한다. 분석은 기존 결과 경로 덮어쓰기를 거부한다. 예측이 완료되지 않은 상태에서 일부만 골라 평가하지 않는다.

## 시작 시 검증

- 로컬 SSH 터널을 통해 /v1/models 조회 및 두 모델 확인.
- 최초 샌드박스 실행에서 RAG 네트워크 제한을 발견해 중단. 그 시도에서는 완료 예측 파일이 생성되지 않았다.
- 네트워크 허용 후 첫 B/C에서 prior.source=exaone, 논문 grounding 기록, 각 4개 시점 확률 합 1을 확인.
- 데이터 해시/경로/입력 분리 검증 통과. 기존 타겟팅 계산 테스트 12개 통과.
- 첫 B/C 약 81초/91초. 초기 추정 전체 72개 군 실행 약 1시간 40분. 실제 완료시간은 저장된 elapsed_seconds 기준으로 확인한다.

이 파일은 실행 조건 기록이며 완료 또는 효과 입증 보고서가 아니다. 결과는 results 폴더에 별도로 기록한다.

## 형식 오류 재시도 버전

predictions_v1은 2개 군 완료 후 세 번째 군의 마음 모델 JSON 미완성으로 중단됐다. 완료 파일을 보존한다. predictions_v2는 같은 입력과 예측 정책을 유지하며 마음 응답 형식 오류만 최대 3회 재시도한다. 매 시도 동일 RNG 상태로 입력 후보 순서를 유지하며 실패 응답은 recovery_log.json에 기록한다. 3회 모두 실패하면 해당 사례를 제외하지 않고 중단한다. 새 버전에서는 두 분할 모두 --output experiments/literature_targeting_20260924/predictions_v2를 지정하며, 분석에도 --predictions로 같은 폴더를 지정한다.

## 초기 prior 형식 오류 복구

개발용 33개 완료 후 다음 prior에서 JSONDecodeError가 발생했다. resume_predictions 모듈로 초기 prior 형식 오류만 최대 3회 재시도하도록 보완했다. 기존 정상 예측 33개는 보존하며 예측 정책, 정답, 모델 설정은 바꾸지 않았다. 별도 prior_recovery_policy.json과 prior_recovery_log.jsonl에 변경 및 실패를 기록한다. 이후 개발용 재개와 평가용은 run_predictions 대신 resume_predictions를 사용한다.

## 완료 상태

- predictions_v2 development: 36/36 arm 완료.
- predictions_v2 evaluation: 36/36 arm 완료.
- 개발용 분석: `results/development_v2`.
- 평가용 분석: `results/evaluation_v2`.

평가용은 2개 arm 완료 후 세 번째 arm에서 마음 모델 JSON 형식 오류가 3회 연속 발생해 한 번 중단됐다. 완료된 2개 파일은 유지하고, 실패 로그를 `recovery_log_evaluation_fail_001.json`에 보존한 뒤 같은 설정으로 재개했다. 재개 후 36개 arm까지 완료했다.

평가 실행 중 LG EXAONE 정합 검사 경고가 두 차례 출력됐다. 경고는 실행 로그에 남겼고, 해당 arm 파일은 완료 파일로 저장됐다.

## 최종 해석 위치

결과 해석은 `RESULTS.md`와 `results/evaluation_v2/REPORT.md`를 우선 본다. 핵심 결론은 개인화가 res9 예측과 res8 부모 구역까지는 줄였지만, 사전 지정 주 비교에서 최종 발송구역 면적까지 줄였다고 말할 수 없다는 것이다.

# 논쟁 사례 32개: 개발 진단 자료

보호자 말에 근거가 있는 행동을 기존 정답이나 검사기 때문에 없애지 않기 위한 합성 자료입니다. AI가 작성했으며 사람 검토가 끝나지 않았습니다. 실제 보호자 사례 또는 독립적인 최종 평가로 사용하지 않습니다.

| 계열 | 사례 | 확인할 차이 |
|---|---:|---|
| 피로 상황에서의 이동 지속 | 8 | 계속 걸었다는 관찰과 쉬는 것을 못 봤다는 정보 부족 |
| 정지·대기 중 휴식 | 8 | 걷던 중의 휴식과 서 있거나 기다리던 중의 휴식 |
| 부재 조건 | 8 | 없다고 관찰됨과 관찰하지 않음 |
| 질문 전제 승계 | 8 | 짧은 답변에 앞선 질문의 조건을 함께 적용 |

각 사례 4장면, 총 128장면입니다. 참조 정책은 해당 장면과 128/128 일치하지만, 같은 제작 과정의 내부 일관성 검사일 뿐 정답의 임상적 타당성 증거가 아닙니다. 빈 규칙도 57장면을 통과하므로, 개인 행동을 구별하는 71장면의 결과를 함께 제시해야 합니다.

기존 dev128과 세부 구조 또는 문장 유사도로 표시된 사례는 7개, 거친 구조로만 검토 표시된 사례는 2개입니다. 상세 ID와 기준은 `../../results/d5_preflight/audit.json`에 있습니다. 기존 dev128의 입력·정답·장면을 수정하지 않았습니다.

`disputed_inputs.jsonl`만 모델 입력 후보입니다. 파일명에 `NOT_MODEL_INPUT`이 있는 정답·장면·검토 파일은 모델에 전달하지 않습니다. `disputed_summary.json`에 데이터 해시가 있습니다.

재생성:

```sh
python -m experiments.mind_contract_ab_20261007.dataset.build_personas --fragments disputed_absence_trigger disputed_fatigue_continuation disputed_question_premise disputed_stationary_rest --prefix disputed --split research_development --evidence experiments/mind_contract_ab_20261007/research/verified_evidence_ids.json --out experiments/mind_contract_ab_20261007/dataset/disputed_v1
```

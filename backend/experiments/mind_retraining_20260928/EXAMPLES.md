# 실제 입력과 모델 응답

모든 인물은 합성이며, 설명 검토는 AI 진단이다. 독립적인 돌봄 전문가 검수로 표시하지 않는다.

## 기존 마음모델: 앉고 싶다는 설명과 배회 행동

```json
{"inner": "다리가 아파 앉고 싶다. 도로 쪽이 보인다.", "status": "발걸음을 멈추고 도로 쪽을 바라본다.", "confusion_level": "중", "behavior": "계속 배회", "goal_label": null}
```

이 응답은 형식을 통과했지만 `behavior`가 계속 배회라 실제 엔진 입력이 휴식이 아니다.

## D02-2 · B에 도착하면 기다리는 개인

보호자 원문:

> 질문: 평소 어떤 행동을 직접 보셨나요?
> 답변: 해가 진 뒤에는 B에 갑니다. B에 다다르면 저를 기다리고요. 낮의 외출 목적은 잘 모르겠습니다.

현재 입력:

```json
{
  "state": {
    "anxiety": null,
    "confusion": 0.2,
    "current_action": "seek",
    "distance_m": 500,
    "elapsed_minutes": 60,
    "fatigue": 0.2,
    "interpreted_confusion": null,
    "last_rest_end_minutes": null,
    "recent_events": [
      {
        "elapsed_minutes": 60,
        "kind": "orientation_status_observation",
        "provenance": "synthetic condition, not a real sensor measurement",
        "value": "oriented"
      },
      {
        "elapsed_minutes": 59,
        "kind": "sunset_observation",
        "value": true
      }
    ],
    "target_label": "등록 장소 B",
    "target_reached": true
  },
  "environment": {
    "map_proximity_m": {
      "forest": null,
      "market": 20,
      "park": null,
      "water": null
    },
    "observed_place_labels": [],
    "observed_signals": {
      "market": {
        "crowded": null,
        "noisy": null
      }
    },
    "provenance": "synthetic scenario, not measured KINTEX sound/crowd",
    "visibility_of_other_places": "unknown"
  }
}
```

<details>
<summary>학습 전 전체 응답</summary>

````text
```json
{
  "status": "decision",
  "action": "seek",
  "goal_operation": "set",
  "goal_label": "등록 장소 B",
  "avoid_feature": null,
  "evidence_ids": ["D02-2", "N1", "state"],
  "reason": "어르신은 해가 진 뒤 '등록 장소 B'로 이동하는 습관이 있다고 보호자가 언급했습니다. 현재 상태에서 '등록 장소 B'가 목표로 설정되어 있으며, 어르신이 목적지로 향하고 있는 것으로 보입니다.",
  "confusion_level": "medium"
}
```

### 설명:
- **status**: `decision`으로 설정하여 현재 행동에 대한 결정을 내렸음을 나타냅니다.
- **action**: `seek`로 설정하여 어르신이 등록된 목적지로 이동 중임을 표현합니다.
- **goal_operation**: `set`으로 설정하여 현재 목표가 설정되었다는 것을 나타냅니다.
- **goal_label**: `등록 장소 B`로 설정하여 어르신의 목표 장소를 명확히 합니다.
- **avoid_feature**: `null`로 설정하여 현재 상황에서 회피 행동이 관찰되지 않았음을 나타냅니다.
- **evidence_ids**: 관련된 원문 ID, 보호자의 언급 내용, 그리고 현재 상태 정보를 포함합니다.
- **reason**: 보호자의 관찰 내용과 현재 상태를 바탕으로 어르신의 행동을 설명합니다. 치매 수준이 중간 정도로 판단되어 `confusion_level`을 `medium`으로 설정했습니다.
- **confusion_level**: 보호자의 언급과 현재 약간의 혼란 상태(`confusion: 0.2`)를 고려하여 `medium`으로 판단했습니다.
````

</details>

<details>
<summary>학습 후 전체 응답</summary>

````text
{"status": "decision", "action": "stay", "goal_operation": "keep", "goal_label": null, "avoid_feature": null, "evidence_ids": ["N1", "state", "environment", "history", "clock"], "reason": "해가 진 뒤의 B 방문은 이미 완료되었으므로 현재 대기한다.", "confusion_level": "unknown"}
````

</details>

합성 과제의 기대 지시: `stay`. 저녁 목표 B 도착이 확인되어 기다린다.

## D01-4 · 소음을 모르는 상태를 조용하다고 단정

보호자 원문:

> 질문: 평소 어떤 행동을 직접 보셨나요?
> 답변: 공원 소리를 꺼려 돌아가는 분이지만, 몸이 많이 지치면 우선 앉습니다. 덜 지쳤고 공원이 조용하면 그대로 걸어요.

현재 입력:

```json
{
  "state": {
    "anxiety": null,
    "confusion": 0.2,
    "current_action": "seek",
    "distance_m": 500,
    "elapsed_minutes": 60,
    "fatigue": 0.1,
    "interpreted_confusion": null,
    "last_rest_end_minutes": null,
    "recent_events": [
      {
        "elapsed_minutes": 60,
        "kind": "orientation_status_observation",
        "provenance": "synthetic condition, not a real sensor measurement",
        "value": "oriented"
      }
    ],
    "target_label": "등록 장소 A",
    "target_reached": false
  },
  "environment": {
    "map_proximity_m": {
      "forest": null,
      "market": null,
      "park": 20,
      "water": null
    },
    "observed_place_labels": [],
    "observed_signals": {
      "park": {
        "crowded": null,
        "noisy": null
      }
    },
    "provenance": "synthetic scenario, not measured KINTEX sound/crowd",
    "visibility_of_other_places": "unknown"
  }
}
```

<details>
<summary>학습 전 전체 응답</summary>

````text
```json
{
  "status": "decision",
  "action": "seek",
  "goal_operation": "set",
  "goal_label": "등록 장소 A",
  "avoid_feature": null,
  "evidence_ids": ["case_id:D01-4", "person:evidence_notes:N1"],
  "reason": "어르신은 현재 덜 지쳤고 공원이 조용한 상태에서 이동하려는 경향이 있으며, 목표로 설정된 '등록 장소 A'로 이동하려는 의도가 명확합니다. 이전 해석에 따르면 공원 소리를 피하는 경향이 있지만, 현재 상황에서는 목적지로의 이동을 선택하고 있습니다.",
  "confusion_level": "medium"
}
```

### 설명:
- **status**: 현재 상태는 결정되었으므로 `decision`으로 설정합니다.
- **action**: 어르신의 현재 행동은 이전과 동일하게 `seek`로 유지됩니다. 이는 등록된 목적지인 '등록 장소 A'로 이동하려는 의도를 반영합니다.
- **goal_operation**: 어르신이 목적지로 이동하려는 의도가 명확하므로 `set`으로 설정합니다.
- **goal_label**: 목표 장소는 '등록 장소 A'로 설정됩니다.
- **avoid_feature**: 현재 상황에서는 특정 방향을 피하는 행동이 없으므로 `null`로 설정합니다.
- **evidence_ids**: 관련 증거는 원문 ID와 보호자의 관찰 내용을 포함합니다.
- **reason**: 어르신의 현재 행동은 덜 지쳤고 조용한 환경에서 목적지로 이동하려는 의도를 반영하며, 이전 관찰 내용과 일치합니다. 치매 수준은 중간 정도로 판단됩니다 (`medium`).
- **confusion_level**: 어르신의 혼란 수준은 0.2로 주어졌지만, 현재 행동이 명확하게 목적지로 향하고 있으므로 `medium`으로 설정합니다. 이는 행동이 명확하지만 완전히 명확하지 않은 상태를 반영합니다.
````

</details>

<details>
<summary>학습 후 전체 응답</summary>

````text
{"status": "decision", "action": "continue", "goal_operation": "keep", "goal_label": null, "avoid_feature": null, "evidence_ids": ["N1", "state", "environment", "history", "clock"], "reason": "공원 소음이 없고 현재 이동 중이라 공원을 회피하지 않는다.", "confusion_level": "unknown"}
````

</details>

합성 과제의 기대 지시: `insufficient_information`. 피로는 낮지만 소음 관측이 없어 이동과 회피를 구분할 추가 정보가 필요하다.

## D04-2 · 행동은 맞지만 가족 동행 근거를 놓침

보호자 원문:

> 질문: 평소 어떤 행동을 직접 보셨나요?
> 답변: 시장이 시끄러울 때 혼자면 돌아갑니다. 가족이 옆에 있으면 시끄러워도 같이 원래 길을 갑니다. 조용하면 혼자라도 계속 갑니다.

현재 입력:

```json
{
  "state": {
    "anxiety": null,
    "confusion": 0.2,
    "current_action": "seek",
    "distance_m": 500,
    "elapsed_minutes": 60,
    "fatigue": 0.2,
    "interpreted_confusion": null,
    "last_rest_end_minutes": null,
    "recent_events": [
      {
        "elapsed_minutes": 60,
        "kind": "orientation_status_observation",
        "provenance": "synthetic condition, not a real sensor measurement",
        "value": "oriented"
      },
      {
        "elapsed_minutes": 59,
        "kind": "companion_observation",
        "value": true
      }
    ],
    "target_label": "등록 장소 A",
    "target_reached": false
  },
  "environment": {
    "map_proximity_m": {
      "forest": null,
      "market": 20,
      "park": null,
      "water": null
    },
    "observed_place_labels": [],
    "observed_signals": {
      "market": {
        "crowded": null,
        "noisy": true
      }
    },
    "provenance": "synthetic scenario, not measured KINTEX sound/crowd",
    "visibility_of_other_places": "unknown"
  }
}
```

<details>
<summary>학습 전 전체 응답</summary>

````text
```json
{
  "status": "decision",
  "action": "seek",
  "goal_operation": "set",
  "goal_label": "등록 장소 A",
  "avoid_feature": null,
  "evidence_ids": ["D04-2", "R1", "N1"],
  "reason": "어르신은 조용한 환경에서는 혼자서도 목표 장소로 이동하는 경향이 있지만, 시장이 시끄럽다면 가족이 동반되어 있지 않더라도 원래 경로를 유지하는 경향이 있습니다. 현재 상황이 noisy한 시장 환경이지만, 목표 장소 '등록 장소 A'로 이동하려는 의도가 명확하게 나타나고 있어 seek 동작을 취합니다.",
  "confusion_level": "medium"
}
```

### 설명:
- **status**: 현재 상태는 결정되었으므로 `decision`으로 설정합니다.
- **action**: 어르신의 현재 행동은 `seek`로, 등록된 목적지로 이동하려는 의도가 명확합니다.
- **goal_operation**: 목적지 설정을 위해 `set` 동작을 취합니다.
- **goal_label**: 목표 장소는 `등록 장소 A`로 설정됩니다.
- **avoid_feature**: 현재 상황에서 회피 행동이 필요하지 않으므로 `null`로 설정합니다.
- **evidence_ids**: 관련된 증거와 연구 발췌를 참조합니다.
  - `D04-2`: 전체 케이스 정보
  - `R1`: 시설 관찰에 대한 연구 발췌
  - `N1`: 보호자의 관찰 기록
- **reason**: 어르신의 행동 패턴과 현재 환경을 고려하여, noisy한 환경에서도 목표 장소로 이동하려는 의도가 명확하므로 `seek` 동작을 취하는 것으로 해석합니다. `confusion_level`은 중간 수준으로 설정하였습니다 (0.2의 혼란 수준과 행동 패턴을 고려).
- **confusion_level**: 어르신의 혼란 수준이 중간 정도로 판단되어 `medium`으로 설정합니다. 이는 명확한 행동 패턴이 있지만 완전히 명확하지 않은 상황을 반영합니다.
````

</details>

<details>
<summary>학습 후 전체 응답</summary>

````text
{"status": "decision", "action": "continue", "goal_operation": "keep", "goal_label": null, "avoid_feature": null, "evidence_ids": ["N1", "state", "environment", "history", "clock"], "reason": "혼잡이 없는 시장 소음은 개인의 원래 이동을 유지한다.", "confusion_level": "unknown"}
````

</details>

합성 과제의 기대 지시: `continue`. 가족 동행이라는 개인의 예외 조건 때문에 기존 이동을 유지한다.

원문32개는 [베이스](lora/results/base_development.jsonl)와 [LoRA](lora/results/lora_final_development.jsonl)에 있다. [설명 검토](lora/results/lora_explanation_review.json)는 행동 지시 일치와 별도다.

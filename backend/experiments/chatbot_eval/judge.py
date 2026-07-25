"""P1-7 — LLM judge: 정답표 없이 (대화 대본 + 추출 결과)만 보고 품질을 채점.

judge 가 유효하려면 "정답표 기반 점수(사람 판정 전사)"와 상관 r≥0.7 이어야 한다
(run_judge_corr.py 가 측정). 유효하면 정답표가 없는 신규 시나리오 평가에 judge 를
쓸 수 있다 — 골드셋 확장 비용이 사람 판정에서 LLM 호출로 내려간다.

차원 3개는 ScoreCard 의 내용 지표와 1:1 대응:
  collection  ↔ collection_recall  (말한 장소를 빠짐없이 수집했나)
  evidence    ↔ evidence_accuracy  (근거 등급을 옳게 붙였나)
  axis        ↔ axis_coverage      (행동 관찰이 축 근거로 남았나)

judge 는 Mi:dm(추출과 같은 모델) — 자기 출력 자기 평가라는 self-bias 한계가 있다.
상관이 높게 나와도 이 한계는 결과 문서에 명시한다.
"""

from __future__ import annotations

import json
import re

from app import llm

_JUDGE_SYSTEM = """당신은 실종자 사전등록 인터뷰 챗봇의 품질 평가자다.
보호자 발화 대본과, 챗봇이 그 대화에서 추출한 결과를 보고 세 차원을 0~10으로 채점한다.
정답지는 없다 — 대본만 근거로 판단한다.

채점 차원:
1. collection: 보호자가 말한 '갈 만한 장소'들이 추출 결과에 빠짐없이 담겼는가
   (0=거의 놓침, 10=전부 수집. 대본에 없는 장소를 지어냈으면 감점)
2. evidence: 각 장소의 근거 등급이 발화와 맞는가
   (previous_missing_found=과거 실종 발견지 / caregiver_report=보호자가 직접 관찰한
    반복 행동 / mention_only=단순 언급. 0=엉터리, 10=전부 정확)
3. axis: 이동력·배회 습관 같은 행동 관찰 발화가 축 근거로 기록됐는가
   (0=거의 누락, 10=관찰 발화 전부 반영)

반드시 아래 JSON 만 출력한다:
{"collection": 0-10, "evidence": 0-10, "axis": 0-10, "reasoning": "한두 문장"}"""


def _build_input(scenario, transcript, include_axis_texts: bool = True) -> str:
    lines = ["[보호자 발화 대본]"]
    for slot, text in scenario.answers.items():
        lines.append(f"- ({slot}) {text}")
    persona = transcript.persona or {}
    lines.append("\n[챗봇 추출 결과]")
    aps = persona.get("attraction_points", []) or []
    if aps:
        for a in aps:
            lines.append(f"- 장소: {a.get('label')} / 근거등급: {a.get('evidence')}")
    else:
        lines.append("- 장소: (없음)")
    drafts = transcript.draft_attractions or []
    if drafts:
        lines.append("[수집 단계 장소(좌표화 이전)]")
        for a in drafts:
            lines.append(f"- {a.get('label')}")
    axis_ev = persona.get("axis_evidence") or {}
    if include_axis_texts and axis_ev:
        # 축 이름만 주면 judge 가 커버리지를 추정으로 때워야 한다(P1-7 v1 에서
        # r=0.33 실측) — 근거 원문을 줘야 대본과의 대조가 된다.
        lines.append("[축 근거 기록 (축: 원문)]")
        for ax in sorted(axis_ev):
            for note in axis_ev[ax] or []:
                lines.append(f"- {ax}: {note}")
    else:
        axes = sorted(axis_ev.keys())
        lines.append(f"[축 근거가 기록된 축] {', '.join(axes) if axes else '(없음)'}")
    return "\n".join(lines)


def judge_scenario(scenario, transcript, include_axis_texts: bool = True) -> dict | None:
    """세 차원 0~1 정규화 점수. 파싱 실패 시 1회 재시도 후 None."""
    user_input = _build_input(scenario, transcript, include_axis_texts)
    for _ in range(2):
        raw = llm.midm.chat(
            [{"role": "system", "content": _JUDGE_SYSTEM},
             {"role": "user", "content": user_input}],
            temperature=0.0, max_tokens=300)
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            continue
        try:
            data = json.loads(m.group(0))
            return {
                "collection": max(0.0, min(10.0, float(data["collection"]))) / 10.0,
                "evidence": max(0.0, min(10.0, float(data["evidence"]))) / 10.0,
                "axis": max(0.0, min(10.0, float(data["axis"]))) / 10.0,
                "reasoning": str(data.get("reasoning", ""))[:200],
            }
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return None

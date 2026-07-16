"""축 점수 컴파일 — 인터뷰 근거(axis_quotes·axis_evidence) → EXAONE 채점 → 0.1~0.9.

골드셋 실험(experiments/axis_goldset, 2026-07-16 총 294호출)으로 검증된 방식 고정:
- 입력 = B안(축별 근거·원발화만). 대화 통짜(A안)는 판정 18~19/28 이동(대부분 상향
  오염) + 정보부족 케이스의 '판정 불가'를 억지 점수로 무너뜨리는 것이 실증됨.
- 프롬프트 = P1(기준표 A~E 분류). 숫자는 노출하지 않고 코드가 0.1~0.9 로 매핑
  (가드레일 관례: LLM 은 정성 라벨, 수치화는 코드). quote(원문 인용) 강제 +
  F(판정 불가) 선택지 + temperature 0.
- 축당 runs회(기본 3) 호출 후 다수결 — temp 0 에서도 비결정성이 실측됨(형식 위반·
  판정 차이가 특정 run 에서만 발생). 다수결 불성립 시 유효 점수의 중앙값.
- F(판정 불가)·근거 없음 축은 점수를 만들지 않는다 → 소비자(Phase 2)가 유형
  기본 prior 로 폴백. 축별 F율·quote 검증률은 앞단 추출 품질(병목) 감시 지표 겸용.

기준표 단일 소스 = data/axis_rubric.md (settings.axis_rubric_path). 회의에서
기준표가 갱신되면 코드 수정 없이 다음 채점부터 반영된다.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from app.config import settings
from app.phase0.slots import slots_for
from app.schemas.persona import Persona, PersonaType

CHOICE_SCORE = {"A": 0.1, "B": 0.3, "C": 0.5, "D": 0.7, "E": 0.9, "F": None}

_TYPE_LABEL = {
    PersonaType.dementia: "치매",
    PersonaType.child: "아동",
    PersonaType.intellectual_disability: "발달장애",
}


# ── 기준표 로드 (md 파싱 — 골드셋 실험 score_axes.py 와 공유) ──────────

def load_rubrics(path: str | Path | None = None) -> tuple[dict[str, dict], dict[str, str]]:
    """axis_rubric.md → ({axis: {label, anchors{"0.1"~"0.9"}}}, {axis: 방향 설명})."""
    p = Path(path or settings.axis_rubric_path)
    lines = p.read_text(encoding="utf-8").splitlines()

    directions: dict[str, str] = {}
    rubrics: dict[str, dict] = {}
    in_direction = False
    current: dict | None = None

    for line in lines:
        if line.startswith("## 축 방향 요약"):
            in_direction, current = True, None
            continue
        if line.startswith("#"):
            in_direction = False
            m = re.match(r"^##\s+.*?\(([a-z_]+)\)", line) if line.startswith("## ") else None
            if m:
                label = re.sub(r"^[①②③④⑤⑥⑦⑧⑨⑩]\s*", "",
                               re.sub(r"\([a-z_]+\).*$", "", line[3:]).strip()).strip(" —-")
                current = {"label": label, "anchors": {}}
                rubrics[m.group(1)] = current
            else:
                current = None
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]] if line.startswith("|") else []
        if in_direction and len(cells) == 2 and re.fullmatch(r"[a-z_]+", cells[0]):
            directions[cells[0]] = cells[1].replace("**", "")
        elif current is not None and len(cells) == 2 and re.fullmatch(r"0\.\d", cells[0]):
            current["anchors"][cells[0]] = cells[1]

    for axis, r in rubrics.items():
        missing = {"0.1", "0.3", "0.5", "0.7", "0.9"} - set(r["anchors"])
        if missing:
            raise ValueError(f"기준표 파싱 실패: {axis} 앵커 누락 {missing}")
    return rubrics, directions


# routine_destinations 는 공통 슬롯이지만 route_environment_familiarity 채점은
# 치매 전용 (회의 결정: 치매 = 공통3+특화3+route친숙 / 발달 = 공통3+특화4 = 각 7축)
_DEMENTIA_ONLY_SCORED = {"route_environment_familiarity"}


def scored_axes(ptype: PersonaType, rubrics: dict[str, dict]) -> list[str]:
    """채점 대상 축 = 유형 슬롯의 axis_field ∩ 기준표 보유 축.

    lost_behavior·dementia_wandering_pattern 은 점수 없는 관찰 지표 —
    기준표에 없으므로 자동 제외된다(치매·발달 각 7축).
    """
    fields = [s.axis_field for s in slots_for(ptype) if s.axis_field]
    return [f for f in fields if f in rubrics
            and (ptype == PersonaType.dementia or f not in _DEMENTIA_ONLY_SCORED)]


# ── P1 프롬프트 ─────────────────────────────────────────────────────

P1_SYSTEM = """\
너는 실종 위험 프로파일 채점자다. 보호자 상담 내용에서 지정된 '평가 축' 하나만 보고, \
기준표의 선택지 중 가장 부합하는 하나로 분류한다.

규칙:
- JSON 객체 하나만 출력한다. JSON 밖에 어떤 문장도 쓰지 않는다.
- choice: "A"~"E" 중 하나. 입력에 이 축을 판정할 근거가 부족하면 "F".
- quote: 판정의 핵심 근거인 보호자 발화를 입력에서 글자 그대로 옮겨 적는다. \
choice 가 "F" 면 빈 문자열.
- 입력에 없는 사실을 추측하거나 지어내지 않는다. 지정된 축과 무관한 정보는 판정에 쓰지 않는다.
- 여러 선택지의 근거가 공존하면 발견·구조를 더 어렵게 만드는 쪽(E에 가까운 쪽)을 고른다. \
단, 축의 방향이 '능력·예측성'인 축은 실제 확인된 최고 수준으로 고른다.
- reason: 판단 근거 1~2문장 (한국어)."""

P1_USER_TMPL = """\
[대상자] {info}
[평가 축] {label}
[축의 방향] 이 축의 상위 선택지(E쪽)가 뜻하는 것: {direction}
[기준표]
A. {a01}
B. {a03}
C. {a05}
D. {a07}
E. {a09}
F. 판정 불가 — 입력에 이 축을 판정할 근거가 부족함
[보호자 상담 내용]
{input_text}

출력 형식: {{"choice": "A~F 중 하나", "quote": "...", "reason": "..."}}"""


def build_p1_messages(rubric: dict, direction: str, info: str, input_text: str) -> list[dict]:
    a = rubric["anchors"]
    return [
        {"role": "system", "content": P1_SYSTEM},
        {"role": "user", "content": P1_USER_TMPL.format(
            info=info, label=rubric["label"], direction=direction, input_text=input_text,
            a01=a["0.1"], a03=a["0.3"], a05=a["0.5"], a07=a["0.7"], a09=a["0.9"])},
    ]


# ── 응답 파싱·검증 (골드셋 실험에서 검증된 복구·필터) ─────────────────

def _norm(s: str) -> str:
    return re.sub(r"[\s\"'“”‘’]", "", s)


def _quote_exists(quote: str, input_text: str) -> bool:
    """문장 단위 실존 검증 — 조합 인용은 인정, 글자 변형은 잡는다."""
    frags = [f.strip() for f in re.split(r"[.?!\n]", quote)]
    frags = [f for f in frags if len(_norm(f)) >= 4]
    if not frags:
        return False
    hay = _norm(input_text)
    return all(_norm(f) in hay for f in frags)


def _extract_json(raw: str) -> tuple[dict | None, bool]:
    """(파싱 결과, 엄격 통과 여부). 실측 위반(중괄호 중복·누락)을 복구하되 위반으로 기록."""
    try:
        start = raw.index("{")
    except ValueError:
        return None, False
    try:
        return json.loads(raw[start: raw.rindex("}") + 1]), True
    except ValueError:
        pass
    ends = [i for i, ch in enumerate(raw) if ch == "}"]
    for end in reversed(ends):
        try:
            return json.loads(raw[start: end + 1]), False
        except ValueError:
            continue
    for tail in ("}", '"}'):
        try:
            return json.loads(raw[start:].rstrip() + tail), False
        except ValueError:
            continue
    return None, False


def parse_p1(raw: str, input_text: str) -> dict:
    """P1 응답 → choice/score/quote 검증. 실패는 parse_error 로 기록."""
    out: dict = {"choice": None, "score": None, "quote": None,
                 "quote_verified": None, "reason": None, "parse_error": None,
                 "format_violation": False}
    data, strict = _extract_json(raw)
    out["format_violation"] = not strict
    if data is None:
        out["parse_error"] = "JSON 파싱 실패 (복구 불가)"
        return out
    out["reason"] = data.get("reason")
    choice = str(data.get("choice", "")).strip().upper()[:1]
    if choice not in CHOICE_SCORE:
        out["parse_error"] = f"choice 형식 위반: {data.get('choice')!r}"
        return out
    out["choice"] = choice
    out["score"] = CHOICE_SCORE[choice]
    quote = str(data.get("quote") or "")
    out["quote"] = quote
    if choice != "F":
        out["quote_verified"] = bool(quote) and _quote_exists(quote, input_text)
    return out


# ── 채점 본체 ───────────────────────────────────────────────────────

def _build_axis_input(persona: Persona, axis: str) -> str:
    """B안 입력 — 원발화(있으면) + 추출 노트. 원발화가 1차 근거(재서술 손실 우회)."""
    quotes = persona.axis_quotes.get(axis, [])
    notes = [n for n in persona.axis_evidence.get(axis, []) if n not in quotes]
    parts = []
    if quotes:
        parts.append("[보호자 발화]\n" + "\n".join(f"- {q}" for q in quotes))
    if notes:
        parts.append("[보호자 답변에서 추출한 사실]\n" + "\n".join(f"- {n}" for n in notes))
    return "\n".join(parts)


def _majority(scores: list[float | None]) -> tuple[float | None, str]:
    """runs 회 유효 판정 → (점수 또는 None, 사유). F 다수·전무는 None."""
    if not scores:
        return None, "유효 응답 없음"
    counts = Counter(scores)
    top, top_n = counts.most_common(1)[0]
    if top_n * 2 > len(scores):                      # 과반
        return (top, "다수결") if top is not None else (None, "판정 불가(F) 다수")
    numeric = sorted(s for s in scores if s is not None)
    if not numeric:
        return None, "판정 불가(F) 다수"
    return numeric[len(numeric) // 2], "다수결 불성립 — 중앙값"


def score_axes_for(persona: Persona, client=None, runs: int | None = None) -> tuple[dict[str, float], dict]:
    """Persona 의 축별 근거를 EXAONE 으로 채점 → (axis_scores, 리포트).

    리포트에는 미채점 축(사유), 축별 F율·quote 검증·형식 위반이 담긴다 —
    운영에서 앞단 추출 품질이 나빠지면 F율이 먼저 오르는 감시 지표.
    실패는 해당 run 만 버린다(채점 실패가 등록 자체를 막으면 안 됨).
    """
    if client is None:
        from app.llm.exaone import ExaoneClient
        client = ExaoneClient()
    if getattr(client, "is_stub", False):
        return {}, {"skipped": "EXAONE 스텁 모드 — 채점 생략"}

    runs = runs or settings.axis_scoring_runs
    rubrics, directions = load_rubrics()
    info = f"{_TYPE_LABEL.get(persona.type, persona.type)}, {persona.age}세"

    scores: dict[str, float] = {}
    report: dict = {"runs": runs, "unscored": {}, "axes": {}}
    for axis in scored_axes(persona.type, rubrics):
        input_text = _build_axis_input(persona, axis)
        if not input_text:
            report["unscored"][axis] = "근거 없음(추출 공백)"
            continue
        msgs = build_p1_messages(rubrics[axis], directions.get(axis, ""), info, input_text)
        run_scores: list[float | None] = []
        meta = {"choices": [], "quote_fails": 0, "format_violations": 0, "errors": 0}
        for _ in range(runs):
            try:
                raw = client.chat(msgs, temperature=0.0, max_tokens=400, enable_thinking=False)
                parsed = parse_p1(raw, input_text)
            except Exception:  # noqa: BLE001 — 호출 실패는 그 run 만 버림
                meta["errors"] += 1
                continue
            if parsed["parse_error"]:
                meta["errors"] += 1
                continue
            meta["choices"].append(parsed["choice"])
            meta["format_violations"] += parsed["format_violation"]
            if parsed["quote_verified"] is False:
                meta["quote_fails"] += 1
            run_scores.append(parsed["score"])
        score, how = _majority(run_scores)
        meta["decision"] = how
        report["axes"][axis] = meta
        if score is None:
            report["unscored"][axis] = how
        else:
            scores[axis] = score
    return scores, report

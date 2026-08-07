"""Phase 0 — Mi:dm 온보딩 인터뷰 프롬프트.

역할 분담(노트 설계): '다음에 어느 슬롯을 물을지'는 검색(retrieval.py)이 정한다.
Mi:dm 은 매 턴 두 가지만:
  (A) 추출  — 직전 답변에서 슬롯값을 뽑고, 그 슬롯이 충족됐는지 판정 → JSON.
  (B) 문장화 — 검색이 겨냥한 슬롯을 자연스러운 존댓말 질문 한 개로 → 평문.

추출과 문장화를 분리하면 "직전 답이 슬롯을 채웠는가"를 먼저 확정한 뒤 다음 슬롯을
고를 수 있어(이미 채운 슬롯 재질문 방지), 파이프라인이 명료해진다.

원칙(「인터뷰질문조사」·「챗봇」):
  1) 답하는 사람은 대상자 본인이 아니라 **보호자(제3자)**.
  2) **관찰 가능한 행동·장소**만. 내면 심리 단정·진단·의료조언 금지.
  3) **한 번에 한 질문**, 짧고 명확 — 골든타임.
  4) **존댓말**, 공감은 한 문장 이내. 5) 장소는 **동/랜드마크 수준**까지.

답변 예시(slot.answer_example) 정책 — 인터뷰 느낌 유지 + 앵커링 방지:
  첫 질문에서는 예시를 낭독하지 않는다(설문지화 방지). 꼬리질문 모드에서
  직전 답이 두루뭉술할 때만, 예시의 구체성 수준을 질문 문장 안(물음표 앞)에
  짧게 녹인다. clean_question 이 첫 물음표 뒤를 자르므로 뒤에 붙이면 소실됨.
"""

from __future__ import annotations

import json
import re

from app.phase0.slots import SlotSpec
from app.schemas.persona import PersonaType

_TYPE_LABEL = {
    PersonaType.dementia: "치매 어르신",
}


def _convo(conversation: list[dict]) -> str:
    return "\n".join(
        f"{'보호자' if m['role'] == 'user' else '챗봇'}: {m['text']}"
        for m in conversation
    ) or "(아직 없음)"


# ── (A) 추출 ─────────────────────────────────────────────────────────

EXTRACT_SYSTEM = """\
너는 '돌아오길' 온보딩 인터뷰의 추출기다. 보호자의 마지막 답변에서 실종자 페르소나에
쓸 사실만 뽑아 JSON 으로 낸다. 답변에 없는 내용을 지어내지 마라(환각 금지).
아래 JSON 스키마의 주석 예시 문구를 절대 출력에 복사하지 마라.
장소는 지오코딩 가능한 동/랜드마크 표현이 있으면 area_text 로 남긴다.

behavior_notes 규칙:
- 보호자 답변에 실제로 담긴 '관찰된 행동 사실'만. 답변 문장을 그대로 복사하지 말고
  "~하는 편", "~함" 같은 짧은 서술로 요약한다.
- 보호자가 "모르겠다", "글쎄요"라고 하거나 답에 정보가 없으면 빈 배열 [] — 무지·거부·
  잡담은 사실이 아니다.

evidence — 그 장소가 왜 중요한지의 근거 강도. 위에서부터 먼저 해당하는 것:
- "previous_missing_found": 과거에 길을 잃었을 때 그곳에서 **발견됐다**고 말함
- "caregiver_report": **자주 간다 / 가려고 한다 / 가야 한다고 반복해서 말한다** 중 \
하나라도 있음. 반복되는 '말'도 관찰된 지향이다
- "mention_only": 반복·지향 표현 없이 배경으로만 언급됨 ("젊을 때 다니셨대요")

반드시 아래 JSON 하나만 출력:
{
  "fields": {},               // name/age/home 중 이번 답에서 확인된 것만
  "attraction_points": [],    // [{"label":"옛 직장","area_text":"면목동","place_type":"workplace","evidence":"previous_missing_found"}] 좌표로 특정 가능한 장소 단서
  "behavior_notes": [],       // ["길 잃으면 계속 걷는 편"] 관찰된 행동 사실(짧게)
  "slot_filled": false        // 아래 지정된 슬롯의 '충족 기준'을 이 답이 만족하면 true
}
"""


def build_extract_input(target_slot: SlotSpec, conversation: list[dict]) -> str:
    """추출 입력 — 이전 대화는 '맥락 참고용', 마지막 보호자 발화는 '추출 대상'으로 분리.

    통짜 대화 뒤에 "마지막 발화를 대상으로 추출하라"만 붙이던 구버전은, 대화가
    길어지면 모델이 마지막 답변의 새 사실 대신 **이전 턴에서 이미 나온 장소들을
    재추출**했다 — 새로 말한 과거 발견지("원평중학교 앞에서 발견됐어요")가 통째로
    유실되던 라이브 실측(2026-07-21). 대상 발화를 헤더로 분리하고 기존 장소
    재출력을 금지하자 Mi:dm 실호출 A/B 에서 0/3 → 3/3 으로 회복됐다.
    (창 크기를 줄이는 대안은 2/3 에 그쳤고 지시대명사 맥락을 잃는다.)
    """
    head = f"""\
[방금 겨냥했던 슬롯]
- key: {target_slot.key} · {target_slot.label}
- 충족 기준: {target_slot.filled_when}
"""
    if not conversation or conversation[-1].get("role") != "user":
        return head + f"\n[대화]\n{_convo(conversation)}\n\n마지막 '보호자:' 발화를 대상으로 추출하라. 위 JSON 하나만 출력."
    return head + f"""
[이전 대화 — 맥락 참고용]
{_convo(conversation[:-1])}

[추출 대상 — 이 발화에서만 뽑는다]
보호자: {conversation[-1].get('text', '')}

위 '추출 대상' 발화에만 담긴 사실을 추출하라. 이전 대화에서 이미 나온 장소는 \
다시 넣지 마라. 위 JSON 하나만 출력."""


# ── (A') 확인 게이트 정정 ────────────────────────────────────────────
# 일반 추출과 분리한 이유(라이브 실측 2026-07-21): 요약 확인 단계의 발화는 '새 사실
# 진술'이 아니라 **이미 등록된 항목에 대한 변경 지시**다. 일반 추출로 처리하면
#  - "원평중학교가 아니라 원평초등학교예요" → 아무 일도 안 일어나고(이름 교체 수단 없음)
#  - "원마루 공원은 빼주세요"              → 삭제 수단이 없어 무시되며
#  - "예전에 살던 집은 수곡동이에요"        → 슬롯 랭킹이 home 을 골라 **자택이 바뀐다**
# 그래서 변경 대상·동작을 닫힌 어휘로 받고, 적용은 코드가 한다(가드레일 원칙).
CORRECTION_SYSTEM = """\
너는 '돌아오길' 온보딩의 정정 처리기다. 보호자가 등록 요약을 보고 말한 '수정 요청'을 \
읽고, 무엇을 어떻게 바꿔야 하는지만 JSON 으로 낸다. 새 정보를 지어내지 마라.

반드시 아래 JSON 하나만 출력:
{
  "fields": {},      // 바꿀 기본 정보만. 키는 name/age/home 중 실제로 정정된 것만. \
장소(가시려 할 만한 곳) 정정은 여기 넣지 마라 — home 은 '지금 사시는 집'을 고칠 때만.
  "place_ops": []    // 장소 변경 지시 배열
}

place_ops 의 각 항목:
- {"op":"rename","target":"<기존 장소명>","value":"<새 장소명>"}   이름이 틀렸을 때
- {"op":"set_area","target":"<기존 장소명>","value":"<동/주소>"}   위치(동네)가 틀렸을 때
- {"op":"remove","target":"<기존 장소명>"}                        더 이상 해당 없을 때
- {"op":"add","value":"<새 장소명>","area":"<동/주소 또는 null>"}  빠진 곳을 더할 때

규칙:
- target 은 아래 [현재 등록된 장소] 목록의 이름과 **글자 그대로** 일치해야 한다. \
목록에 없는 이름을 target 으로 쓰지 마라.
- 바꿀 것이 없으면 빈 값으로 둔다. 확실하지 않으면 넣지 마라."""


def build_correction_input(place_labels: list[str], utterance: str) -> str:
    places = ", ".join(place_labels) if place_labels else "(없음)"
    return f"""\
[현재 등록된 장소] {places}

[보호자의 수정 요청]
{utterance}

위 JSON 하나만 출력."""


# few-shot — 실측(2026-07-21)에서 흔들린 세 패턴을 그대로 시연한다:
# (1) 장소의 동네 정정을 fields.home 으로 잘못 보내던 것(2/2 오작동),
# (2) "A가 아니라 B" 이름 정정을 remove 로 처리해 장소가 사라지던 것,
# (3) "A가 아니라 B" 에서 새 값이 B(뒤쪽)라는 것.
CORRECTION_FEWSHOT_USER = """\
[현재 등록된 장소] 옛 직장, 예전에 살던 집, 망원중학교

[보호자의 수정 요청]
예전에 살던 집은 신수동이 아니라 수곡동이에요. 그리고 망원중학교가 아니라 망원초등학교예요

위 JSON 하나만 출력."""

CORRECTION_FEWSHOT_ASSISTANT = """\
{"fields": {}, "place_ops": [\
{"op":"set_area","target":"예전에 살던 집","value":"수곡동"}, \
{"op":"rename","target":"망원중학교","value":"망원초등학교"}]}"""


_PLACE_OPS = ("rename", "set_area", "remove", "add")


def parse_correction(raw: str, place_labels: list[str]) -> dict:
    """정정 응답 → 검증된 {fields, place_ops}. 실존 라벨·닫힌 동작만 통과."""
    empty: dict = {"fields": {}, "place_ops": []}
    try:
        data = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return empty
    if not isinstance(data, dict):
        return empty
    fields = {k: v for k, v in (data.get("fields") or {}).items()
              if k in ("name", "age", "home") and isinstance(v, str) and v.strip()}
    known = set(place_labels)
    ops = []
    for raw_op in data.get("place_ops") or []:
        if not isinstance(raw_op, dict):
            continue
        op = str(raw_op.get("op") or "").strip()
        target = str(raw_op.get("target") or "").strip()
        value = str(raw_op.get("value") or "").strip()
        if op not in _PLACE_OPS:
            continue
        if op == "add":
            if not value:
                continue
            ops.append({"op": op, "value": value,
                        "area": str(raw_op.get("area") or "").strip()})
            continue
        if target not in known:      # 지어낸 대상 차단 — goal_label '실존 라벨만' 원칙
            continue
        if op in ("rename", "set_area") and not value:
            continue
        ops.append({"op": op, "target": target, "value": value})
    return {"fields": fields, "place_ops": ops}


def parse_extract(raw: str) -> dict:
    try:
        data = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return {"fields": {}, "attraction_points": [],
                "behavior_notes": [], "slot_filled": False}
    data.setdefault("fields", {})
    data.setdefault("attraction_points", [])
    data.setdefault("behavior_notes", [])
    data.setdefault("slot_filled", False)
    return data


# ── (B) 문장화 ───────────────────────────────────────────────────────

PHRASE_SYSTEM = """\
너는 '돌아오길' 온보딩 인터뷰어다. 보호자에게 물을 질문을 딱 하나 만든다.

[문체]
- 답하는 사람은 보호자다. "어르신이/아이가 …하시나요?"처럼 제3자 관점, 존댓말.
- 겉으로 드러난 행동·장소만. 마음속 이유 단정·진단·의료/법률 조언 금지.

[질문 규칙 — 엄수]
- 질문은 정확히 하나. 물음표도 하나. 두 가지를 한 문장에 묶어 묻지 마라.
- **이미 확보한 정보(이름·집 주소 등)를 질문에서 다시 나열하지 마라.** 특히 거주지를
  매 질문마다 되풀이하지 말 것("○○동에서 …" 같은 반복 금지).
- 짧고 담백하게, 한 문장. 장황한 위로·수식어 금지(공감은 넣더라도 아주 짧게).
- 아래 '겨냥 슬롯'을 채우는 질문만. 스키마 밖 자유 질문 금지.
- **직전 답변에 나온 장소·고유명사를 새 질문에 끌어와 섞지 마라** — 겨냥 슬롯이
  그 장소와 무관하면("○○시장 말고 다른 곳 가실 때 신호를 지키시나요?" 식 결합 금지)
  슬롯 내용만 담백하게 물어라. 꼬리질문 모드에서 되받아 확인할 때만 예외.
- **보호자가 말하지 않은 사실을 전제로 묻지 마라** — "예전 집에 가야 한다고
  말씀하실 때…"처럼 대화에 없는 발화·행동을 기정사실처럼 깔지 말 것.
  그런 행동이 있는지 자체를 물어라("~하신 적이 있나요?").
- 장소를 물을 땐 새로 알아낼 곳만 콕 집어 묻고, 이미 아는 위치는 되풀이하지 마라.
- 질문 문장만 출력(따옴표·설명·JSON 없이).

[좋은 질문 예시 — 이 호흡을 따라라]
- 직전 답 "그냥 잘 걸으세요" (겨냥: 이동 능력 / 미확보: 지속 거리·속도)
  → 쉬지 않고 걸으시면 어디까지 가실 수 있을까요?
- 직전 답 "망원시장에 자주 가세요" (겨냥: 자주 가는 곳·경로 / 미확보: 다니는 길)
  → 망원시장 가실 때 늘 다니시는 길이 정해져 있나요?
- 직전 답 "네" (겨냥: 위험 인지 / 미확보: 물가·계단 등 나머지 위험)
  → 물가나 계단 같은 곳도 위험한 걸 알아보시는 편인가요?

[나쁜 질문 예시 — 금지]
- 복용 중인 약이 있나요? 거르면 어떤 증상이 나타나나요? (한 번에 질문 두 개)
- 예전 집에 가야 한다고 말씀하실 때 어디를 말씀하시나요? (하지 않은 말을 전제)
- 망원시장 말고 다른 곳에 가실 때도 신호를 지키시나요? (직전 화제를 무관 슬롯에 결합)"""

# 문장화에는 최근 대화만 준다 — 전체를 주면 모델이 거주지 등을 매번 되뇌며 과잉 앵커링.
_PHRASE_WINDOW = 4


# ── (C) 파고들기 — 판정과 문장화를 **따로** 부른다 ───────────────────
# 한 번에 "안 들은 게 있으면 질문을 만들고 없으면 NONE" 을 시키면 모델은 사실상
# 항상 질문을 만든다(실측 2026-08-07: 확인 목록이 전부 답해진 입력에도 6/6 질문
# 생성, NONE 0회). 질문을 만들라는 지시 자체가 생성 쪽으로 기울인다. 그래서
# 판정은 JSON 전용 호출로 떼어낸다 — 기존 원칙(정성 판단은 LLM, 반영은 코드).

PROBE_GAP_SYSTEM = """\
너는 보호자 인터뷰 기록을 검토한다. 질문을 만들지 마라. 채점만 한다.

'확인 목록'의 **모든 항목에 대해 하나도 빠짐없이** 답함(true)/안 답함(false)을
매긴다. 항목을 그대로 베껴 나열하지 마라 — 항목마다 실제로 판정해야 한다.

[판정 기준]
- **어휘가 달라도 뜻이 같으면 답함(true)**이다:
  · "그 자리에 서서 가만히 계세요" → '머무름·계속 이동·은신 중 우세 경향' = true
  · "신호도 잘 지키시고" → '차도·횡단보도에서 신호를 지키는지' = true
  · "위험 감지 능력은 좋아요" → '물가의 위험을 인식하는지' = true, '계단·높은 곳에서 조심하는지' = true
- true 로 매겼으면 `quote` 에 근거가 된 보호자 말을 **그대로 인용**한다.
  인용할 말을 못 찾겠으면 그건 false 다.
- **낱말만 겹치는 인용은 false 다.** 인용한 말이 그 항목이 묻는 **내용**을 실제로
  담고 있어야 한다:
  · '거르면 나타나는 증상' ← "가끔 거르고 나가십니다" = **false**
    (거른다는 사실일 뿐, 거른 뒤 달라지는 모습이 없다)
  · '거르면 나타나는 증상' ← "약을 거르시면 하루 종일 멍하게 계세요" = true
  · '야간 이동 가능성' ← "밤에도 나가신 적이 있어요" = true

[출력 — 이 JSON 만]
{"items": [{"i": <항목 번호>, "answered": true, "quote": "<보호자 말 그대로>"},
           {"i": <항목 번호>, "answered": false, "quote": ""}]}"""


PROBE_SYSTEM = """\
너는 '돌아오길' 온보딩 인터뷰어다. 아래 '물어볼 것' 하나만 묻는 질문을 만든다.

[규칙 — 엄수]
- 질문은 정확히 하나. 물음표도 하나. 짧고 담백하게.
- **'물어볼 것' 문구를 그대로 쓰지 마라.** 그건 내부 메모지 보호자가 쓰는 말이
  아니다. '우세 경향', '유인 취약성', '구체적 목격 사례' 같은 말 금지 — 풀어서 물어라.
- **보호자가 이미 한 말을 다시 묻지 마라.** 되받아 확인하는 것도 금지.
- 답하는 사람은 보호자다. "어르신이 …하시나요?" 제3자 관점, 존댓말.
- 진단·의료/법률 조언 금지. 겉으로 드러난 행동·장소만.
- 질문 문장만 출력(따옴표·설명·JSON 없이).

[예시]
물어볼 것: 구체적 목격 사례
→ 실제로 그런 모습을 보신 적이 있나요?

물어볼 것: 거르면 나타나는 증상
→ 약을 거르시면 평소와 달라지는 모습이 있나요?

물어볼 것: 태워주거나 데려간다고 하면 따라갈 가능성 (유인 취약성)
→ 낯선 사람이 태워준다고 하면 따라가실까요?"""


def _probe_labels(target_slot: SlotSpec) -> list[str]:
    """probes 에서 내부 태그("(destination_retention)")를 뗀 표시용 목록."""
    return target_slot.probe_labels


def build_probe_gap_input(
    ptype: PersonaType,
    target_slot: SlotSpec,
    evidence: list[str],
) -> str:
    """확인 목록(probes, 번호 매김) + 보호자가 실제로 한 말(노트 + 원발화)."""
    said = "\n".join(f"- {e}" for e in evidence) or "- (아직 없음)"
    checklist = "\n".join(
        f"{i}. {p}" for i, p in enumerate(_probe_labels(target_slot), 1))
    return (
        f"[대상 유형] {ptype.value}\n"
        f"[항목] {target_slot.label} — {target_slot.filled_when}\n"
        f"[확인 목록]\n{checklist}\n"
        f"[보호자가 한 말]\n{said}"
    )


def build_probe_input(
    ptype: PersonaType,
    target_slot: SlotSpec,
    angle: str,
    evidence: list[str],
) -> str:
    said = "\n".join(f"- {e}" for e in evidence) or "- (아직 없음)"
    return (
        f"[대상 유형] {ptype.value}\n"
        f"[항목] {target_slot.label}\n"
        f"[물어볼 것] {angle}\n"
        f"[보호자가 이미 한 말 — 다시 묻지 말 것]\n{said}"
    )


def parse_probe_gap(raw: str, target_slot: SlotSpec) -> list[str]:
    """채점 응답 → 아직 안 답한 확인 목록 항목들. 파싱 실패는 '남은 게 없음'.

    실패를 '전부 남았다'로 보면 판정 불능일 때마다 아무 각도나 묻게 된다 —
    파고들기는 보너스라 침묵하는 쪽이 안전하다.

    `answered=true` 인데 `quote` 가 비어 있으면 근거 없는 판정이라 **안 답함으로
    되돌린다** — 모델이 근거 인용을 요구받으면 실제로 읽는다는 점을 이용한 검증
    (다른 경로의 '발화 근거 검증'과 같은 원칙).
    """
    try:
        data = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    labels = _probe_labels(target_slot)
    answered: set[int] = set()
    for item in data.get("items") or []:
        if not isinstance(item, dict) or not item.get("answered"):
            continue
        quote = str(item.get("quote") or "").strip()
        if not quote:
            continue          # 근거 없는 '답함' 은 인정하지 않는다
        try:
            idx = int(item.get("i"))
        except (TypeError, ValueError):
            continue
        if 1 <= idx <= len(labels):
            answered.add(idx)
    return [lb for i, lb in enumerate(labels, 1) if i not in answered]


CLARIFY_SYSTEM = """\
너는 '돌아오길' 온보딩 인터뷰어다. 보호자가 **직전 질문을 못 알아들었다**고 말했다.
답을 모르는 게 아니라 질문이 어려웠던 것이다. 같은 질문을 되풀이하지 말고,
무엇을 묻는 것인지 쉬운 말로 풀어서 다시 물어라.

[출력 형식 — 엄수]
- 두 문장. 첫 문장은 무엇을 묻는지 일상어로 푼 설명(물음표 없이).
- 둘째 문장이 실제 질문. 물음표는 여기 딱 하나.
- **수집 항목 이름·전문용어를 그대로 쓰지 마라**("구체적 목격 사례", "이동 반경",
  "경로 회복", "유인 취약성" 등은 보호자가 쓰는 말이 아니다).
- 보호자가 바로 떠올릴 수 있게 구체적인 예를 하나 넣어라.
- 짧고 담백하게. 사과나 위로를 길게 늘어놓지 마라.
- 겉으로 드러난 행동·장소만. 진단·의료/법률 조언 금지.
- 문장만 출력(따옴표·설명·JSON 없이).

[예시]
못 알아들은 질문: 구체적 목격 사례에 대해서도 알려주세요.
보호자 말: 구체적 목격 사례가 무슨 의민지 모르겠어요
→ 실제로 길을 잃으셨던 때가 있으면 그때 어떠셨는지가 궁금해요. 예를 들어 어디서 무얼 하고 계셨는지 기억나시는 게 있을까요?

못 알아들은 질문: 유인 취약성에 대해서도 알려주세요.
보호자 말: 그게 무슨 말이에요?
→ 낯선 사람이 태워준다거나 데려다준다고 하면 따라가실까 봐 여쭤보는 거예요. 그런 말에 쉽게 따라가시는 편인가요?"""


def build_clarify_input(
    ptype: PersonaType,
    target_slot: SlotSpec,
    question: str,
    utterance: str,
) -> str:
    """못 알아들은 질문 + 보호자의 반응 + 이 슬롯이 원래 알고 싶은 것."""
    return (
        f"[대상 유형] {ptype.value}\n"
        f"[못 알아들은 질문] {question}\n"
        f"[보호자 말] {utterance}\n"
        f"[이 항목이 알고 싶은 것] {target_slot.label} — {target_slot.filled_when}\n"
        f"[답변 눈높이 예시(그대로 낭독 금지)] {target_slot.answer_example}"
    )


def build_phrase_input(
    ptype: PersonaType,
    target_slot: SlotSpec,
    is_followup: bool,
    conversation: list[dict],
    known: dict | None = None,
    collected: list[str] | None = None,
) -> str:
    """collected: 이 슬롯에서 이미 확보한 사실들 — '갭 기반 꼬리질문'의 재료.

    충족 기준(filled_when)과 확보 사실을 나란히 주면 '무엇이 아직 비었는지'를
    모델이 판단해 빠진 것만 묻는다. 이 판단을 코드 휴리스틱이 아니라 모델에
    맡기는 것이 능동 elicitation 설계의 핵심 (2026-07-17 결정).
    """
    mode = (
        "꼬리질문: 방금 보호자가 한 말을 아주 짧게 되받아 확인하며, 부족한 한 가지"
        "(구체적 지명·빈도·방향·구체 사례 중 하나)만 더 물어라."
        if is_followup
        else "새 화제: 군더더기 없이 이 슬롯을 묻는 질문으로 넘어가라."
    )
    # 답변 예시는 꼬리질문 모드에서만 — 첫 질문에 실으면 설문지처럼 되고
    # 보호자 답이 예시 문형에 앵커링된다. 예시는 물음표 앞에 녹여야 살아남는다
    # (clean_question 이 첫 물음표 뒤를 자름).
    example_block = (
        f"\n- 답변 눈높이 예시(그대로 낭독 금지): {target_slot.answer_example}"
        "\n  직전 답이 두루뭉술하면 이 예시 수준의 구체성(시간·거리·지명·행동)을"
        " 질문 문장 안에 짧게 녹여 물어라."
        if is_followup and target_slot.answer_example
        else ""
    )
    known = known or {}
    known_line = ", ".join(f"{k}={v}" for k, v in known.items() if v) or "(없음)"
    collected_line = "; ".join(collected) if collected else "(아직 없음)"
    recent = conversation[-_PHRASE_WINDOW:]
    return f"""\
[대상자 유형] {_TYPE_LABEL[ptype]}

[이미 확보한 정보 — 질문에서 반복하지 말 것] {known_line}

[최근 대화]
{_convo(recent)}

[겨냥 슬롯]
- {target_slot.label} (key: {target_slot.key})
- 씨앗 질문(참고용, 그대로 쓰지 말 것): {target_slot.question}
- 충족 기준: {target_slot.filled_when}
- 이 슬롯에서 이미 확보한 사실: {collected_line}
- 더 파고들 각도: {" / ".join(target_slot.probes) or "(없음)"}{example_block}
- 모드: {mode}

충족 기준과 확보한 사실을 비교해 **아직 비어 있는 부분 하나만** 콕 집어 물어라.
이미 확보한 사실을 다시 묻지 마라. 확보한 사실이 아직 없으면 **기본 사실(있는지/
하는지 여부)부터** 확인하라 — 존재를 전제로 한 세부 질문("약을 거르시면…")을
여부 확인보다 먼저 하지 마라. 질문 한 문장만 출력."""


# 되묻기 출력 길이 상한 — '설명 1문장 + 질문 1문장'이면 충분하다.
_CLARIFY_MAX = 220


# 되묻는 문장인지 판정하는 단서. Mi:dm 은 절반쯤을 물음표 없이 끝낸다
# ("…아니면 계속 걸어다니시는지 알고 싶어요.") — 물음표만 요구하면 멀쩡한 출력의
# 절반을 버리고 폴백으로 떨어진다(실측 2026-08-07, 6건 중 3건).
_CLARIFY_CUES = ("?", "궁금", "알고 싶", "알려주", "말씀해", "여쭤", "있을까", "실까")


def clean_clarify(raw: str) -> str:
    """되묻기 출력 정리 — '설명 + 질문' 2문장을 살린다. 못 살리면 빈 문자열.

    clean_question 은 첫 물음표에서 자르는데, 되묻기는 예시 안에 인용 물음표가
    섞이기 쉬워("모르는 사람이 '어디 가세요?'라고 하면…") 문장이 중동무이가 된다
    (실 Mi:dm 실측 2026-08-07, 2회 중 1회). 마지막 물음표까지 살리되 길이는 막는다.
    빈 문자열을 돌려주면 호출자가 결정론적 폴백을 쓴다 — 잘린 문장을 내보내느니
    예시 기반 안내가 낫다.
    """
    t = " ".join(raw.strip().strip('"').split())
    if not t or not any(c in t for c in _CLARIFY_CUES):
        return ""            # 되묻는 문장이 아니다 → 폴백
    if "?" in t:
        cut = t.rfind("?")
        if cut + 1 > _CLARIFY_MAX:
            cut = t.rfind("?", 0, _CLARIFY_MAX)
        if cut != -1:
            return t[:cut + 1].strip()
    if len(t) <= _CLARIFY_MAX:
        return t
    cut = t.rfind(".", 0, _CLARIFY_MAX)   # 한도 안 마지막 문장 끝에서 자른다
    return t[:cut + 1].strip() if cut != -1 else ""


def clean_question(raw: str) -> str:
    """모델 출력을 단일 질문으로 정리 — 복합질문/후행 공감문 컷.

    첫 물음표까지만 남긴다(두 번째 질문·뒤에 붙은 위로 제거). 물음표가 없으면
    첫 줄만 사용.
    """
    t = raw.strip().strip('"').strip()
    if "?" in t:
        return t.split("?")[0].strip() + "?"
    return t.splitlines()[0].strip() if t else t

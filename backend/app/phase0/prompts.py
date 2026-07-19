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

from app.phase0.slots import SlotSpec
from app.schemas.persona import PersonaType

_TYPE_LABEL = {
    PersonaType.dementia: "치매 어르신",
    PersonaType.child: "아동",
    PersonaType.intellectual_disability: "지적장애가 있는 분",
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

evidence 는 그 장소·대상이 왜 중요한지의 근거 강도다. 반드시 아래 3개 중 하나:
- "previous_missing_found": 과거 실종·이탈 때 실제로 거기서 발견됐다고 말함
- "caregiver_report": 보호자가 반복해서 가려는 걸 직접 봤다고 말함
- "mention_only": 지나가듯 언급만 (근거 발화가 없으면 이것)

반드시 아래 JSON 하나만 출력:
{
  "fields": {},               // name/age/type/home 중 이번 답에서 확인된 것만. type ∈ {dementia,child,intellectual_disability}
  "attraction_points": [],    // [{"label":"옛 직장","area_text":"면목동","place_type":"workplace","evidence":"previous_missing_found"}] 좌표로 특정 가능한 장소 단서
  "preferred_targets": [],    // [{"label":"지하철","target_type":"transport","evidence":"caregiver_report"}] 특정 장소가 아닌 카테고리 선호(지하철·자동문·편의점류). 특정 장소면 attraction_points 로.
  "behavior_notes": [],       // ["길 잃으면 계속 걷는 편"] 관찰된 행동 사실(짧게)
  "slot_filled": false        // 아래 지정된 슬롯의 '충족 기준'을 이 답이 만족하면 true
}
"""


def build_extract_input(target_slot: SlotSpec, conversation: list[dict]) -> str:
    return f"""\
[방금 겨냥했던 슬롯]
- key: {target_slot.key} · {target_slot.label}
- 충족 기준: {target_slot.filled_when}

[대화]
{_convo(conversation)}

마지막 '보호자:' 발화를 대상으로 추출하라. 위 JSON 하나만 출력."""


def parse_extract(raw: str) -> dict:
    try:
        data = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return {"fields": {}, "attraction_points": [], "preferred_targets": [],
                "behavior_notes": [], "slot_filled": False}
    data.setdefault("fields", {})
    data.setdefault("attraction_points", [])
    data.setdefault("preferred_targets", [])
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
- 직전 답 "그냥 잘 걸으세요" (겨냥: 이동 능력 / 미확보: 지속 거리·대중교통)
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


def clean_question(raw: str) -> str:
    """모델 출력을 단일 질문으로 정리 — 복합질문/후행 공감문 컷.

    첫 물음표까지만 남긴다(두 번째 질문·뒤에 붙은 위로 제거). 물음표가 없으면
    첫 줄만 사용.
    """
    t = raw.strip().strip('"').strip()
    if "?" in t:
        return t.split("?")[0].strip() + "?"
    return t.splitlines()[0].strip() if t else t

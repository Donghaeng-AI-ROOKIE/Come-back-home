"""슬롯 랭킹 측정용 코퍼스 — 골드 라벨은 chatbot_eval 시나리오에서 파생한다.

`scenarios.py` 의 `answers` 는 `{슬롯키: 그 슬롯 질문에 대한 보호자 답변}` 이므로
"이 발화의 정답 슬롯"이 이미 라벨링돼 있다. 별도 라벨링 없이 랭킹 정확도를 잴 수 있다.

⚠ 무정보 답변("잘 모르겠어요" 등)은 대본상 슬롯에 매달려 있지만 내용이 없다.
   ON(본론)으로 두면 분포가 오염되므로 반드시 OFF 로 분류한다 — 이걸 놓치면
   argmax 적중률이 실제보다 낮게(실측 61.5% vs 75.9%) 나온다.
"""

from __future__ import annotations

# 무정보 답변 판별 — 짧고 회피성인 것만. 긴 문장에 우연히 들어간 "없어요"는 제외.
NOINFO_MARKERS = ("모르", "없어요", "없습니다", "그 정도예요", "기억이 안", "글쎄")
NOINFO_MAX_LEN = 20

# 온보딩 중 실제로 나올 법한 잡담·회피·메타 발화 (정답 슬롯이 없는 발화).
# 헛피벗(무정보 발화에 피벗이 걸리는 것)을 재는 대조군.
CHITCHAT: list[str] = [
    "요즘 날씨가 참 덥네요",
    "안녕하세요",
    "네, 맞아요",
    "감사합니다",
    "아까 뭐라고 하셨죠?",
    "죄송한데 좀 있다가 다시 할게요",
    "점심은 드셨어요?",
    "회사 일이 요즘 바빠서 정신이 없네요",
    "빨리 좀 찾아주세요 답답해요",
]


def is_noinfo(text: str) -> bool:
    """내용 없는 회피성 답변인가 — ON/OFF 분류와 헛피벗 계측의 공통 기준."""
    return len(text) <= NOINFO_MAX_LEN and any(m in text for m in NOINFO_MARKERS)


def build_corpus(persona_type: str = "dementia") -> tuple[list[tuple[str, str]], list[str]]:
    """(ON, OFF) 반환.

    ON  = [(정답 슬롯키, 발화)] — 시나리오 대본의 내용 있는 답변
    OFF = [발화]               — 대본의 무정보 답변 + CHITCHAT

    같은 (슬롯, 문장) 쌍은 시나리오 간 중복되므로 한 번만 담는다.
    """
    from experiments.chatbot_eval.scenarios import SCENARIOS

    on: list[tuple[str, str]] = []
    noinfo: list[str] = []
    seen: set[tuple[str, str]] = set()

    for sc in SCENARIOS.values():
        if sc.persona_type != persona_type:
            continue
        for key, text in sc.answers.items():
            if (key, text) in seen:
                continue
            seen.add((key, text))
            if is_noinfo(text):
                if text not in noinfo:
                    noinfo.append(text)
            else:
                on.append((key, text))

    return on, noinfo + CHITCHAT

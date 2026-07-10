"""적응형 꼬리질문 시뮬레이터 — 검색 절반을 실제 코드로 검증.

Mi:dm 없이도 "다음에 어느 슬롯을 물을지(그라운딩)"와 "꼬리질문/피벗 여부"를
retrieval.py 실코드로 돌려 확인한다. Mi:dm 문장화는 PHRASING 목업으로 대체.
보호자 답변의 슬롯 충족(extraction)은 시나리오에 주석으로 스크립트한다
(실제로는 Mi:dm 이 slot_filled 로 반환).

실행:  PYTHONPATH=. python3 scripts/sim_elicitation.py
"""

from __future__ import annotations

from app.phase0 import retrieval
from app.phase0.slots import slot_by_key, slots_for
from app.schemas.persona import PersonaType

EMB = retrieval.get_embedder()   # EMBED_MODEL 설정 시 로컬 한국어 임베더, 없으면 해시 스텁

# 검색 유사도가 이 이상이면 "보호자의 말이 이 슬롯으로 이끈 것" = 꼬리질문/피벗.
FOLLOWUP_SIM = 0.20

# Mi:dm 문장화 목업 — (fresh, followup) 변형. 실제로는 prompts.SYSTEM_PROMPT 로 생성.
PHRASING: dict[str, tuple[str, str]] = {
    "home": ("지금 그분이 주로 지내시는 집은 어느 동네인가요?",
             "그 동네 어디쯤인지 조금만 더 알려주시겠어요? 가까운 랜드마크가 있을까요?"),
    "routine_destinations": ("혼자 나가실 때 주로 어디에 가시나요? 가시는 길도 정해져 있나요?",
                             "그곳에 가실 때 주로 어느 방향, 어느 길로 가시나요?"),
    "long_workplace": ("예전에 오래 다니셨던 직장이나 가게가 어느 동네에 있었나요?",
                       "말씀하신 그 일터가 어느 동네였는지 알려주시겠어요?"),
    "past_residences": ("지금 집에 오시기 전에는 어디에 사셨나요?",
                        "예전에 사시던 그 동네가 어디였는지 기억나시나요?"),
    "recurring_place": ("자꾸 얘기하시는 옛 장소(고향·옛 교회 등)가 있나요?",
                        "그 장소가 어느 동네인지, 지금도 그쪽으로 가려 하시는지 궁금해요."),
    "time_perception": ("지금을 몇 년도로, 본인을 몇 살쯤으로 여기시나요?",
                        "혹시 지금도 그 시절로 여기시며 그때 하시던 일을 하려 하세요?"),
    "prior_missing": ("예전에도 혼자 나가셔서 못 돌아오신 적이 있나요? 어디서 발견되셨나요?",
                      "그때 어디서 발견되셨는지 알려주시겠어요?"),
    "lost_behavior": ("길을 잃으시면 보통 어떻게 하세요? 머무시나요, 계속 걸으시나요?",
                      "그럴 때 한자리에 계시는 편인가요, 계속 이동하시는 편인가요?"),
    "mobility": ("한 번에 얼마나 걸으실 수 있나요? 걷는 데 불편한 곳이 있나요?",
                 "얼마나 오래 걸으실 수 있는지 알려주시겠어요?"),
    "transit": ("걸어서만 다니시나요, 버스·지하철도 타실 줄 아시나요?",
                "교통카드를 갖고 다니시는지, 혼자 대중교통을 타시는지 궁금해요."),
    "sensory_attraction": ("물·기차·자동차·동물처럼 유독 집착해서 가려는 대상이 있나요?",
                           "물 쪽에 유독 끌려 하나요? 강·호수·수영장 같은 물가도 가려 하나요?"),
    "sensory_avoidance": ("큰 소리나 붐비는 곳에서 어떻게 반응하나요? 숨는 편인가요?",
                          "그럴 때 좁은 구석이나 눈에 안 띄는 곳에 숨는 편인가요?"),
    "stranger_response": ("낯선 사람이 말을 걸면 어떻게 반응하시나요?",
                          "그럴 때 경계하시는 편인가요, 친근하게 대하시는 편인가요?"),
    "uniform_response": ("경찰관이나 제복 입은 사람을 보면 다가가나요, 피하나요?",
                         "제복 입은 사람을 보면 어떻게 반응하는지 궁금해요."),
    "follows_strangers": ("모르는 사람이 데려가겠다고 하면 따라갈 가능성이 있나요?",
                          "낯선 사람 차를 따라갈 수도 있을까요?"),
    "name_response": ("이름을 부르면 대답하나요? 특별히 반응하는 말·노래가 있나요?",
                      "이름을 부르면 반응하는지, 좋아하는 캐릭터나 노래가 있는지 궁금해요."),
    "cherished_person": ("특별히 그리워하거나 찾으시는 분이 있나요? 그분 계신 곳은요?",
                         "그분과 연관된 장소가 어디인지 알려주시겠어요?"),
    "medication": ("복용 중인 약이 있나요? 야간이나 추위에 이동이 어려운 상태인가요?",
                   "약을 거르면 어떤 증상이 나타나는지 궁금해요."),
    "crowd_pathing": ("사람 많은 곳을 좋아하시나요, 조용한 곳을 찾으시나요?",
                      "갈림길에선 큰길과 골목 중 어디로 가시는 편인가요?"),
    "repeated_phrases": ("'고향 간다' 같은 반복해서 하시는 말이 있나요?",
                         "그 말이 어디를 가리키는 것 같으세요?"),
    "identity": ("등록하실 분의 성함과 나이, 어떤 상황이신지 알려주세요.", ""),
}


def _q(slot_key: str, followup: bool) -> str:
    fresh, fu = PHRASING.get(slot_key, ("(질문)", "(꼬리질문)"))
    return fu if (followup and fu) else fresh


def run(title: str, ptype: PersonaType, script: list[dict]) -> None:
    """script: [{"answer": 보호자 답, "fills": [충족된 슬롯 key...]}] 순서대로."""
    print("\n" + "═" * 72)
    print(f"  {title}  (유형: {ptype.value})")
    print("═" * 72)

    user_turns: list[str] = []
    filled: set[str] = set()
    asked: dict[str, int] = {}   # 물었지만 안 채워진 슬롯 횟수(반복 억제)

    # 첫 질문 = 하드코딩(identity). (노트: "함수 서비스 — 첫 질문 하드코딩")
    print(f"\n[턴 0] 챗봇(하드코딩): {_q('identity', False)}")

    for i, step in enumerate(script):
        ans = step["answer"]
        user_turns.append(ans)
        for k in step.get("fills", []):
            filled.add(k)
            asked.pop(k, None)   # 채워지면 페널티 해제
        print(f"\n[턴 {i+1}] 보호자: {ans}")
        print(f"        · 이번 답으로 충족된 슬롯: {step.get('fills', []) or '—'}")

        ranked, kept = retrieval.rank_next_slots(
            ptype, user_turns, filled, EMB, top_k=3, asked_counts=asked
        )
        if not ranked:
            print("        · 남은 슬롯 없음 → 인터뷰 종료, 페르소나 생성.")
            break

        dropped = [j for j in range(len(user_turns) - 1) if j not in kept]
        print(f"        · [디노이즈] 쿼리에 채택한 과거턴 {kept or '—'} / 버린 과거턴 {dropped or '—'}")
        print("        · [슬롯 검색 top-3]")
        for s in ranked:
            print(f"            {s.slot.key:<20} sim={s.similarity:.3f} risk={s.risk:.2f} pen={s.penalty:.2f} score={s.score:.3f}")

        top = ranked[0]
        asked[top.slot.key] = asked.get(top.slot.key, 0) + 1
        followup = top.similarity >= FOLLOWUP_SIM
        tag = "꼬리질문(보호자 말이 이끈 슬롯)" if followup else "새 화제(우선순위로 선택)"
        print(f"        → 선택: {top.slot.key}  [{tag}]")
        print(f"[턴 {i+1}] 챗봇: {_q(top.slot.key, followup)}")


DEMENTIA = [
    {"answer": "어머니 김순자, 78세요. 치매 진단받으셨어요.", "fills": ["identity"]},
    {"answer": "성북구 정릉동이요. 정릉초등학교 근처예요.", "fills": ["home"]},
    {"answer": "예전엔 시장 가시는 걸 좋아하셨는데, 요즘은 자꾸 '회사 가야 한다'면서 나가려고 하세요.", "fills": []},
    {"answer": "면목동에서 방앗간을 아주 오래 하셨어요.", "fills": ["long_workplace"]},
    {"answer": "네, 자기가 아직 40대인 줄 아세요. 새벽에 방앗간 문 열어야 한다고 하세요.", "fills": ["time_perception"]},
    {"answer": "길 잃으면 절대 안 멈추고 계속 걸으세요. 한번 방향 잡으면 쭉 가요.", "fills": ["lost_behavior"]},
]

AUTISM = [
    {"answer": "아들 7살이요. 자폐 스펙트럼이에요.", "fills": ["identity"]},
    {"answer": "강서구 화곡동 살아요.", "fills": ["home"]},
    {"answer": "놀이터를 좋아하는데, 요즘 분수대만 보이면 그쪽으로 막 뛰어가요.", "fills": []},
    {"answer": "네 물만 보면 그래요. 근처 안양천에도 자꾸 가려고 해요.", "fills": ["sensory_attraction"]},
    {"answer": "사이렌이나 큰 소리 나면 귀 막고 차 밑 같은 데로 숨어버려요.", "fills": ["sensory_avoidance"]},
]

if __name__ == "__main__":
    run("시나리오 A — 치매 어르신 (정릉동 김순자)", PersonaType.dementia, DEMENTIA)
    run("시나리오 B — 자폐 아동 (화곡동 7세)", PersonaType.child, AUTISM)

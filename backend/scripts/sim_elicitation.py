"""적응형 꼬리질문 시뮬레이터 — 검색 절반을 실제 코드로 검증.

Mi:dm 없이도 "다음에 어느 슬롯을 물을지(그라운딩)"와 "꼬리질문/피벗 여부"를
retrieval.py 실코드로 돌려 확인한다. Mi:dm 문장화는 PHRASING 목업으로 대체.
보호자 답변의 슬롯 충족(extraction)은 시나리오에 주석으로 스크립트한다
(실제로는 Mi:dm 이 slot_filled 로 반환).

축 고도화(2026-07) 반영: 슬롯 = 몸축·마음축·행동축 16개 카탈로그.
시나리오 B 는 발달장애(자폐 포함) 케이스.

실행:  PYTHONPATH=. python3 scripts/sim_elicitation.py
"""

from __future__ import annotations

from app.phase0 import retrieval
from app.phase0.slots import slot_by_key, slots_for
from app.schemas.persona import PersonaType

EMB = retrieval.get_embedder()   # EMBED_MODEL 설정 시 로컬 한국어 임베더, 없으면 해시 스텁

# 검색 유사도가 이 이상이면 "보호자의 말이 이 슬롯으로 이끈 것" = 꼬리질문/피벗.
FOLLOWUP_SIM = 0.20

# Mi:dm 문장화 목업 — (fresh, followup) 변형. 실제로는 prompts.PHRASE_SYSTEM 으로 생성.
# followup 은 answer_example 의 구체성 눈높이를 문장 안에 녹인 형태를 흉내낸다.
PHRASING: dict[str, tuple[str, str]] = {
    "identity": ("등록하실 분의 성함과 나이, 어떤 상황이신지 알려주세요.", ""),
    "home": ("지금 그분이 주로 지내시는 집은 어느 동네인가요?",
             "그 동네 어디쯤인지 조금만 더 알려주시겠어요? 가까운 랜드마크가 있을까요?"),
    "routine_destinations": ("혼자 나가실 때 주로 어디에 가시나요?",
                             "그곳까지 가시는 길은 늘 같은 길인가요, 어느 방향으로 가시나요?"),
    "autobiographical_destination_pull": (
        "옛집이나 예전 직장처럼 반복해서 찾거나 가려고 하시는 과거의 장소가 있나요?",
        "말씀하신 그곳이 어느 동네였는지, 실제로 그쪽으로 가려 하신 적이 있는지 알려주시겠어요?"),
    "dementia_wandering_pattern": (
        "과거에 길을 잃거나 실종되신 적이 있다면 어디에서 발견되셨나요?",
        "그때 '시장 근처에서 계속 걷고 계셨다'처럼 발견 당시 어떤 행동을 하고 계셨는지 알려주시겠어요?"),
    "preferred_target_seeking": (
        "보호자와 떨어져서라도 찾아가려 할 만큼 강하게 좋아하는 장소나 물건, 교통수단이 있나요?",
        "그 대상 때문에 실제로 보호자와 떨어진 적이 있었는지, 주로 어디로 가는지 알려주시겠어요?"),
    "elopement_pattern_consistency": (
        "과거 이탈이나 실종에서 같은 장소, 경로, 교통수단 또는 행동이 반복됐나요?",
        "'세 번 모두 같은 역 방향'처럼 반복된 장소나 노선이 있었는지 알려주시겠어요?"),
    "mobility_transport_capacity": (
        "평소 보호자 도움 없이 얼마나 오래, 얼마나 멀리 걸으실 수 있나요?",
        "'쉬지 않고 30분, 1km 정도'처럼 시간이나 거리로 알려주시겠어요? 버스·지하철은 혼자 타시나요?"),
    "hazard_awareness_vulnerability": (
        "차도나 물가, 계단처럼 위험한 장소를 스스로 알아보고 피하실 수 있나요?",
        "횡단보도 신호는 지키시는지, 물가 위험은 인식하시는지 알려주시겠어요?"),
    "communication_approach_vulnerability": (
        "이름을 부르거나 말을 걸면 어떻게 반응하시나요?",
        "낯선 사람이나 경찰이 다가오면 피하시나요, 따라가시나요?"),
    "medication": ("복용 중인 약이 있나요?",
                   "약을 거르면 어떤 증상이 나타나는지, 밤에도 나가실 수 있는 상태인지 궁금해요."),
    "wayfinding_error_recovery_deficit": (
        "익숙한 동네에서도 길을 잘못 들거나 목적지를 잊으신 적이 있나요?",
        "잘못 간 것을 스스로 알아차리시나요, 다른 분 도움이 있어야 돌아오시나요?"),
    "lost_behavior": ("길을 잃으시면 보통 어떻게 하시나요?",
                      "그럴 때 한자리에 계시는 편인가요, 계속 이동하시는 편인가요?"),
    "distress_induced_movement_reactivity": (
        "불안하거나 초조해지시면 이동 행동이 어떻게 달라지나요?",
        "그럴 때 도망가기·숨기·계속 걷기·멈추기 중 실제로 보신 행동은 무엇인가요?"),
    "aversive_context_escape": (
        "큰 소리나 사람 많은 곳처럼 불편한 상황이 되면 자리를 벗어나려 하나요?",
        "그렇게 벗어나면 화장실이나 조용한 골목처럼 주로 가는 곳이 있나요?"),
    "transition_routine_disruption": (
        "예정된 일정이나 이동 경로가 바뀌면 어떤 행동을 보이나요?",
        "그럴 때 멈춰 서나요, 원래 출발한 곳으로 되돌아가나요?"),
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
            print(f"            {s.slot.key:<36} sim={s.similarity:.3f} risk={s.risk:.2f} pen={s.penalty:.2f} score={s.score:.3f}")

        top = ranked[0]
        asked[top.slot.key] = asked.get(top.slot.key, 0) + 1
        followup = top.similarity >= FOLLOWUP_SIM
        tag = "꼬리질문(보호자 말이 이끈 슬롯)" if followup else "새 화제(우선순위로 선택)"
        print(f"        → 선택: {top.slot.key}  [{tag}]  (축: {top.slot.axis.value})")
        print(f"[턴 {i+1}] 챗봇: {_q(top.slot.key, followup)}")


DEMENTIA = [
    {"answer": "어머니 김순자, 78세요. 치매 진단받으셨어요.", "fills": ["identity"]},
    {"answer": "성북구 정릉동이요. 정릉초등학교 근처예요.", "fills": ["home"]},
    {"answer": "예전엔 시장 가시는 걸 좋아하셨는데, 요즘은 자꾸 '회사 가야 한다'면서 나가려고 하세요.", "fills": []},
    {"answer": "면목동에서 방앗간을 아주 오래 하셨어요. 아직 새벽에 방앗간 문 열어야 한다고 하세요.",
     "fills": ["autobiographical_destination_pull"]},
    {"answer": "작년에 한 번 못 돌아오신 적 있어요. 면목동 쪽 버스정류장에서 발견됐고 계속 서성이고 계셨대요.",
     "fills": ["dementia_wandering_pattern"]},
    {"answer": "길 잃으면 절대 안 멈추고 계속 걸으세요. 한번 방향 잡으면 쭉 가요.", "fills": ["lost_behavior"]},
]

DEVELOPMENTAL = [
    {"answer": "아들 준호, 19살이요. 자폐성 발달장애예요.", "fills": ["identity"]},
    {"answer": "강서구 화곡동 살아요.", "fills": ["home"]},
    {"answer": "지하철을 정말 좋아해서 역만 보이면 혼자라도 들어가려고 해요.", "fills": []},
    {"answer": "네, 5호선을 특히 좋아해요. 분수대 물 보는 것도 좋아해서 안양천 쪽으로도 가려고 해요.",
     "fills": ["preferred_target_seeking"]},
    {"answer": "사이렌이나 큰 소리 나면 귀 막고 화장실 같은 데로 숨어버려요.", "fills": ["aversive_context_escape"]},
    {"answer": "복지관 하원 시간이 바뀌면 정류장에 그대로 서서 원래 버스를 기다려요.",
     "fills": ["transition_routine_disruption"]},
]

if __name__ == "__main__":
    run("시나리오 A — 치매 어르신 (정릉동 김순자)", PersonaType.dementia, DEMENTIA)
    run("시나리오 B — 발달장애 청년 (화곡동 19세)", PersonaType.intellectual_disability, DEVELOPMENTAL)

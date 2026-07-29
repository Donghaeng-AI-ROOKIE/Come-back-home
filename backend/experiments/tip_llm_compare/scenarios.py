"""P1-4 부속 — tip_llm 후보(Solar-mini vs Mi:dm 2.0 Mini) 대조실험용 시나리오.

70개 자유텍스트 제보(구어체)를 손으로 작성. `app.llm.tip_llm._TIP_STRUCTURE_SYSTEM`의
등급 기준(장소·시각·외모 3요소 중 구체적인 게 몇 개인지 — 3개=상, 1~2개=중, 0개인데 3요소
모두 언급은 됐으면 중, 언급된 요소도 1개 이하면 하)을 그대로 따라 상/중/하를 직접
라벨링했다 — 실제 시민 제보에서 가져온 게 아니라 자체 작성 시나리오다(한계, README 참고).

## 구성 (category 필드로 구분)

- 기본(20): 초기 셋. 한 문장 = 한 목적, 잡음 없이 깔끔. 베이스라인.
- 장황(10): 실질 정보가 잡담·사설 사이에 파묻힘.
- 모순(10): 시각·장소가 두 번 언급되며 정정되거나 충돌. `note`에 두 값을 기록만 하고
  "어느 값이 맞는지"는 채점하지 않는다(값 정확성 판정 안 함 — run_compare.py 상단 원칙).
- 과신(10): 자신감·확신 어조인데 실제 내용은 비거나 모호. "그럴싸함에 속는지" 시험대.
- 복수대상(10): 여러 사람이 언급돼 어느 쪽 묘사인지 불명확.
- 구어체잡음(10): 사투리·비문·오타가 섞임.

기본 셋만으로는 "버그 잡으려 의도적으로 깔끔하게 설계된 셋이라 실전 괴리"라는 지적이 있어(2026-07-29,
phase2 마음 재해석 골드셋에서 같은 문제로 처리했던 버그가 재발한 사례) 실제 제보에 가까운 잡음·
모순·과신·혼동 유형을 유형당 10개씩 추가했다.

expect_* 필드는 "이 정보가 텍스트에 존재하는가"의 정답(True/False) — 모델이 그 필드를 null 대신
값으로 채웠는지 채점하는 기준. 구체/모호와 무관하게 언급만 있으면 True(예: "동네"도 장소 언급이라
expect_location=True지만, 구체성 등급 계산에서는 모호로 쳐서 구체 개수에 안 넣는다). 시각은
relative/absolute/vague 어느 형태든 언급이 있으면 True.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass
class Scenario:
    id: str
    text: str
    gold_specificity: str  # "상"|"중"|"하"
    expect_location: bool
    expect_time: bool       # relative/absolute/vague 어느 형태든 시각 언급이 있으면 True
    expect_appearance: bool
    expect_direction: bool
    category: str = "기본"   # 기본/장황/모순/과신/복수대상/구어체잡음
    note: str = ""           # 모순형 두 값 기록 등 사람 검수용 메모(채점 안 함)


SCENARIOS: list[Scenario] = [
    # ── 기본 · 상(7) ────────────────────────────────────────────────
    Scenario("s01", "방금 전에 OO아파트 정문 앞에서 봤어요. 남색 조끼에 회색 모자 쓰신 할머니셨는데, 편의점 쪽으로 천천히 걸어가셨어요.",
             "상", True, True, True, True, "기본"),
    Scenario("s02", "10분 전쯤 지하철역 3번 출구 근처요. 빨간 패딩 입으신 남자분이 역 반대편으로 급하게 가시더라고요.",
             "상", True, True, True, True, "기본"),
    Scenario("s03", "오후 3시쯤 시장 골목에서 마주쳤어요. 체크무늬 남방에 검은 바지, 지팡이 짚고 시장 안쪽으로 들어가셨어요.",
             "상", True, True, True, True, "기본"),
    Scenario("s04", "30분 전 OO초등학교 담벼락 옆에서요. 노란 우산 쓰고 파란 우비 입은 아이가 학교 정문 쪽으로 뛰어가는 거 봤어요.",
             "상", True, True, True, True, "기본"),
    Scenario("s05", "1시간 전쯤 버스정류장 벤치에 앉아계셨어요. 흰머리에 갈색 카디건 입으시고, 그냥 가만히 앉아만 계셨어요.",
             "상", True, True, True, False, "기본"),
    Scenario("s06", "방금 편의점에서 나와서 저랑 부딪힐 뻔했는데, 초록색 조끼 입고 두리번거리시면서 큰길 쪽으로 가셨어요.",
             "상", True, True, True, True, "기본"),
    Scenario("s07", "새벽 2시쯤 편의점 앞에서 봤어요. 검은 패딩 입고 계셨어요.",
             "상", True, True, True, False, "기본"),

    # ── 기본 · 중(6) ────────────────────────────────────────────────
    Scenario("s08", "아까 공원 근처에서 본 것 같아요. 파란 옷 입으셨던 것 같은데 정확힌 모르겠어요.",
             "중", True, True, True, False, "기본"),
    Scenario("s09", "한 20분 전에 어디 골목이었는데... 정확한 위치는 기억 안 나고, 나이 드신 분이 혼자 걸어가고 계셨어요.",
             "중", True, True, False, False, "기본"),
    Scenario("s10", "역 앞에서 본 거 같은데 시간은 잘 모르겠어요. 회색 옷 입으셨던 분이요.",
             "중", True, False, True, False, "기본"),
    Scenario("s11", "방금 사거리 쪽에서 지나가시는 거 봤어요. 옷차림은 기억 안 나요.",
             "중", True, True, False, False, "기본"),
    Scenario("s12", "낮에 시장에서 봤는데 정확히 몇 시인지는 기억이 안 나요. 편한 복장이셨어요.",
             "중", True, True, False, False, "기본"),
    Scenario("s13", "누가 그러던데 이 근처에서 봤다고 하더라고요. 자세히는 몰라요.",
             "중", True, False, False, False, "기본"),

    # ── 기본 · 하(7) ────────────────────────────────────────────────
    Scenario("s14", "그냥 지나가다 봤는데 잘 기억 안 나요.",
             "하", False, False, False, False, "기본"),
    Scenario("s15", "누구였는지도 잘 모르겠고 그냥 비슷한 사람 본 것 같아요.",
             "하", False, False, False, False, "기본"),
    Scenario("s16", "저도 잘 모르겠는데 동네에서 본 거 같기도 하고...",
             "하", False, False, False, False, "기본"),
    Scenario("s17", "확실친 않은데 어디서 봤던 거 같아요.",
             "하", False, False, False, False, "기본"),
    Scenario("s18", "인상착의는 기억 안 나고 그냥 스쳐 지나갔어요.",
             "하", False, False, False, False, "기본"),
    Scenario("s19", "아마 봤던 거 같기도... 근데 헷갈려요.",
             "하", False, False, False, False, "기본"),
    Scenario("s20", "그냥 신고합니다.",
             "하", False, False, False, False, "기본"),

    # ── 장황(10) — 실질 정보가 잡담 사이에 파묻힘 ────────────────────
    Scenario("l01", "아 제가 오늘 마침 강아지 산책을 나왔거든요, 요새 날이 좋아서. 근데 롯데마트 정문 앞에서 한 10분 전에 봤어요. 갈색 코트에 빨간 목도리 하신 할머니가 지하철역 쪽으로 걸어가시더라고요.",
             "상", True, True, True, True, "장황"),
    Scenario("l02", "저기 제가 원래 이 동네 산 지 오래됐는데요, 하여튼 아까 그게... 아 맞다 편의점 앞에서요, 한 20분 전쯤이었나. 어떤 분이 계셨는데 옷은 뭐 잘 못 봤어요.",
             "중", True, True, False, False, "장황"),
    Scenario("l03", "날씨 얘기부터 하자면 비가 올 것 같더라고요. 그래서 우산을 챙겼는데, 30분 전에 큰길 어디쯤에서 나이 지긋한 분을 봤어요. 인상착의는 잘...",
             "중", True, True, False, False, "장황"),
    Scenario("l04", "제가 정신이 없어서 정확힌 기억 안 나는데요, 아까 어디 공원 근처였나... 무슨 색 옷이었는지도 가물가물하고. 암튼 그 근처에서 본 것 같아요.",
             "중", True, True, True, False, "장황"),
    Scenario("l05", "아이고 요새 세상이 흉흉해서요, 저도 걱정이 많아요. 뉴스 보면 맨날... 하여튼 저희 동네 어디선가 비슷한 사람을 스쳐 본 것 같기도 한데 확실친 않아요.",
             "하", True, False, False, False, "장황"),
    Scenario("l06", "제가 버스 기다리고 있었는데요, 405번이 안 와서 한참을 서 있었거든요. 그러다가 3시쯤에 봤어요. 파출소 앞에서. 검은 패딩에 회색 운동화 신은 남자분이 골목 안으로 뛰어 들어가셨어요.",
             "상", True, True, True, True, "장황"),
    Scenario("l07", "우리 손주가 오늘 학교를 안 가서 같이 있었는데, 하여튼 그 얘긴 됐고. 세븐일레븐 앞에서 파란 조끼 입은 분을 봤어요. 시간은 글쎄, 기억이 안 나네.",
             "중", True, False, True, False, "장황"),
    Scenario("l08", "제가 좀 수다스러워서 죄송한데요, 아무튼 한 시간 전에 어디 골목 쪽에서 봤는데, 옷차림은 그냥 평범했던 것 같아요.",
             "중", True, True, True, False, "장황"),
    Scenario("l09", "제가 사실 눈이 안 좋아서요. 안경을 새로 맞춰야 하는데 자꾸 미루고 있어요. 그래서 뭘 제대로 봤다고 하기가 좀 그래요. 그냥 누가 지나갔던 것 같은데 잘 모르겠어요.",
             "하", False, False, False, False, "장황"),
    Scenario("l10", "제가 그 집 앞을 매일 지나다니는데요, 오늘도 어김없이 지나갔죠. 그러다 참새슈퍼 앞에서 누굴 봤어요. 근데 그게 다예요, 시간이고 뭐고 기억이 안 나요.",
             "중", True, False, False, False, "장황"),

    # ── 모순(10) — 정정·충돌. note에 두 값 기록(값 정확성 채점 안 함) ──
    Scenario("c01", "3시쯤 봤나... 아니다, 4시였어요. 4시 맞아요. 은행 앞에서 남색 점퍼 입은 할아버지가 시장 쪽으로 가셨어요.",
             "상", True, True, True, True, "모순", note="시각: 처음 3시라 했다가 4시로 정정(최종 4시)"),
    Scenario("c02", "편의점 앞에서... 아니 우체국 앞이었나. 둘 중 하나예요. 10분 전에 빨간 모자 쓴 분이요.",
             "중", True, True, True, False, "모순", note="장소: 편의점 앞 vs 우체국 앞 — 둘 중 하나로 미확정(앞뒤 안 맞아 상 아님)"),
    Scenario("c03", "20분 전에... 아 아니 한 40분 됐겠다. 놀이터 앞에서 봤어요. 옷은 기억 안 나요.",
             "중", True, True, False, False, "모순", note="시각: 20분 전 → 40분 전으로 정정(최종 40분)"),
    Scenario("c04", "파란 옷이었어요, 아니 초록색이었나. 초록색 맞아요. 방금 지하철역 2번 출구에서 봤어요.",
             "상", True, True, True, False, "모순", note="외모: 파랑 → 초록으로 정정(최종 초록)"),
    Scenario("c05", "동네에서... 아니 정확히는 우리 아파트 상가 1층 약국 앞이요. 5분 전에 흰 셔츠 입은 분이 지하주차장 쪽으로요.",
             "상", True, True, True, True, "모순", note="장소: '동네'라 했다가 '약국 앞'으로 구체화(모순 아닌 정제)"),
    Scenario("c06", "아까였나 좀 전이었나... 어디 공원인지 놀이터인지도 헷갈리고. 옷도 잘...",
             "중", True, True, True, False, "모순", note="전 요소 미확정: 시각 아까/좀전, 장소 공원/놀이터 헷갈림"),
    Scenario("c07", "한 시간 전... 아니 두 시간 전이요. 그것만 기억나요, 나머진 잘.",
             "중", False, True, False, False, "모순", note="시각: 1시간 전 → 2시간 전으로 정정(최종 2시간)"),
    Scenario("c08", "북쪽으로 갔어요, 아니 남쪽인가. 하여튼 병원 앞에서 검은 코트 입은 분을 봤어요.",
             "중", True, False, True, True, "모순", note="방향: 북 ↔ 남 모순(방향은 등급 판정 제외 필드)"),
    Scenario("c09", "2시... 3시요. 그리고 학교 앞이 아니라 학원 앞이었어요. 노란 가방 멘 학생이 정문 쪽으로.",
             "상", True, True, True, True, "모순", note="시각 2→3시·장소 학교→학원 각각 정정, 최종값 명확"),
    Scenario("c10", "편의점 앞이요, 아니 그 근처 어디였나. 시간도 얼마 안 됐고, 옷차림도 뭐 평범했어요.",
             "중", True, True, True, False, "모순", note="장소: 편의점 앞 → '그 근처'로 후퇴(정정이 오히려 모호해짐)"),

    # ── 과신(10) — 확신 어조 + 빈/모호 내용. 톤에 속는지 시험 ─────────
    Scenario("o01", "제가 100% 확실하게 봤어요! 진짜예요, 틀림없어요! 딱 그 사람이었어요!",
             "하", False, False, False, False, "과신"),
    Scenario("o02", "확실해요, 제가 두 눈으로 똑똑히 봤다니까요. 우리 동네에서요. 진짜 확실합니다.",
             "하", True, False, False, False, "과신"),
    Scenario("o03", "틀림없어요! 농협 앞에서 봤어요. 제가 거긴 매일 지나가서 확실해요. 딱 봤어요.",
             "중", True, False, False, False, "과신"),
    Scenario("o04", "제가 장담하는데 방금 전에 시청 앞에서 봤어요. 확실합니다. 근데 옷은 못 봤어요.",
             "중", True, True, False, False, "과신"),
    Scenario("o05", "제가 시간 감각은 정확한 사람이에요. 아까 봤어요, 확실히 아까. 틀림없어요.",
             "하", False, True, False, False, "과신"),
    Scenario("o06", "제가 확실히 봤어요, 진짜로요. 공원 근처에서, 아까쯤, 무슨 어두운 색 옷 입은 분이요. 틀림없어요.",
             "중", True, True, True, False, "과신"),
    Scenario("o07", "제가 확실히 봤어요! 15분 전에 우리은행 앞에서 빨간 패딩에 검은 바지 입은 할머니가 버스정류장 쪽으로 가셨어요. 틀림없어요.",
             "상", True, True, True, True, "과신"),
    Scenario("o08", "제가 시간은 확실해요, 30분 전이요. 장소는 뭐 그 근처 어디였고. 확실히 30분 전입니다.",
             "중", True, True, False, False, "과신"),
    Scenario("o09", "제 친구가 봤다는데 걔가 눈썰미가 좋아서 확실해요. 어디서 봤댔는데, 하여튼 확실하대요.",
             "하", True, False, False, False, "과신"),
    Scenario("o10", "제가 장담해요. 명동성당 앞에서 초록 점퍼 입은 분 봤어요. 딱 그 사람. 시간은 모르겠지만 사람은 확실해요.",
             "중", True, False, True, False, "과신"),

    # ── 복수대상(10) — 여러 사람 언급, 대상 특정 모호 ────────────────
    Scenario("m01", "할머니 두 분이 계셨는데, 한 분은 빨간 옷, 한 분은 파란 옷이었어요. 3시쯤 시장 앞에서요. 누가 그분인지는 잘...",
             "중", True, True, True, False, "복수대상", note="외모: 두 사람(빨강/파랑) 중 대상 미확정"),
    Scenario("m02", "사람들이 여럿 있었는데, 그중에 검은 모자 쓴 남자분이요. 방금 편의점 앞에서 그분이 골목으로 뛰어갔어요.",
             "상", True, True, True, True, "복수대상", note="복수지만 대상(검은 모자 남자) 명확히 지목"),
    Scenario("m03", "두 명이 지나갔는데 앞사람 말고 뒷사람이요. 뒷사람을 롯데리아 앞에서 봤어요. 옷이나 시간은 기억 안 나요.",
             "중", True, False, False, False, "복수대상", note="대상=뒷사람으로 지목됐으나 그 대상 정보는 위치뿐"),
    Scenario("m04", "사람이 많아서 헷갈리는데, 누구는 모자 쓰고 누구는 안 쓰고... 아까 그 근처에서 봤어요.",
             "중", True, True, True, False, "복수대상", note="외모: 모자 착용 여부가 사람마다 뒤섞여 미확정"),
    Scenario("m05", "두 분 중에 지팡이 짚으신 할아버지요. 10분 전에 봤는데 장소가 그 동네 어디쯤이었어요.",
             "중", True, True, True, False, "복수대상", note="대상(지팡이 할아버지) 지목·외모 구체, 장소는 모호"),
    Scenario("m06", "일행 세 명이 같이 있었는데 그중 흰머리 할머니요. 오후 2시쯤 우체국 앞에서 큰길 쪽으로 걸어가셨어요.",
             "상", True, True, True, True, "복수대상", note="복수지만 대상(흰머리 할머니) 명확 + 3요소 구체"),
    Scenario("m07", "두 사람이 있었는데 누가 누군지 모르겠고, 그냥 정류장 근처였어요.",
             "하", True, False, False, False, "복수대상", note="대상 2인 전혀 미특정, 위치도 모호"),
    Scenario("m08", "애들 여러 명 중에 제일 키 큰 애요. 3시 반쯤 학교 앞에서 봤어요. 뭘 입었는지는 못 봤어요.",
             "중", True, True, False, False, "복수대상", note="'키 큰'은 옷차림 단서 아님(외모 미언급 처리)"),
    Scenario("m09", "한 명은 검은 코트, 한 명은 베이지 코트였는데, 백화점 앞에서요. 누가 실종자분인지는...",
             "중", True, False, True, False, "복수대상", note="외모: 검정/베이지 두 명 중 대상 미확정 → 장소만 구체"),
    Scenario("m10", "사람들이 우르르 있어서 정신없었는데, 그중 누군가를 아까 저 아래쪽에서 본 것 같아요. 옷은 다들 비슷비슷했고.",
             "중", True, True, True, False, "복수대상", note="대상 미특정 + 전 요소 모호"),

    # ── 구어체잡음(10) — 사투리·비문·오타 ───────────────────────────
    Scenario("n01", "아까막 봤다 아입니까, 한 10분 됐나. 지하철역 1번출구 앞에서 빨간 잠바 입은 할매가 시장쪽으로 가시더라꼬예.",
             "상", True, True, True, True, "구어체잡음"),
    Scenario("n02", "방금요 편의점압에서 봣어요 어떤분이 계셧는대 옷은 잘 모르게써요",
             "중", True, True, False, False, "구어체잡음"),
    Scenario("n03", "한시간쯤 됐을낀데 어데 골목서 할배 한 분 봤심더. 옷이야 뭐 기억이 안 나고예.",
             "중", True, True, False, False, "구어체잡음"),
    Scenario("n04", "그... 머시기 거기서 아까 좀 그 사람 같은 사람을 옷은 뭐 무슨 색이더라 봤는데 잘",
             "중", True, True, True, False, "구어체잡음"),
    Scenario("n05", "3시쯤에 우리은행앞에서요 검정패딩 회색바지 입은 남자분이 골목안으로 뛰어가는거 봗어요",
             "상", True, True, True, True, "구어체잡음"),
    Scenario("n06", "세븐일레븐 앞에서 파란 조끼 입은 아재 봤다카이. 시간은 잘 모르겠고예.",
             "중", True, False, True, False, "구어체잡음"),
    Scenario("n07", "머라캐야하노 그냥 동네서 비스무리한 사람 스쳐본거같은데 확실친안코예",
             "하", True, False, False, False, "구어체잡음"),
    Scenario("n08", "파리바게뜨 앞 거기 있잖아요 거기서 봤는데 뭐 시간이고 옷이고 하나도",
             "중", True, False, False, False, "구어체잡음"),
    Scenario("n09", "내가 눈이 침침해가꼬 뭘 봤는지도 잘 모르겠고 그냥 누가 지나간거 같기도 하고예",
             "하", False, False, False, False, "구어체잡음"),
    Scenario("n10", "20분전쯤 노란우산쓴애가 어디쪽으로 뛰어갓어요 위치는 그근처요",
             "중", True, True, True, True, "구어체잡음"),
]


def category_breakdown(rows: list[dict]) -> dict[str, dict]:
    """카테고리별 구체성 일치율·필드추출 정확도 집계.

    rows 는 각 실행 스크립트가 만든 채점 행 리스트로, 최소한 category /
    specificity_match / location_match / time_match / appearance_match /
    direction_match 키를 담고 있어야 한다. 유형별 정량 비교(장황·모순·과신 등에서
    모델이 어디서 무너지는지)를 위해 전체 요약과 별도로 뽑는다.
    """
    field_keys = ["location_match", "time_match", "appearance_match", "direction_match"]
    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        buckets[r.get("category", "기본")].append(r)
    out: dict[str, dict] = {}
    for cat, rs in buckets.items():
        n = len(rs)
        out[cat] = {
            "n": n,
            "specificity_agreement": round(sum(r["specificity_match"] for r in rs) / n, 3),
            "field_extraction_accuracy": round(
                sum(sum(r[k] for k in field_keys) for r in rs) / (n * len(field_keys)), 3),
        }
    return out

"""Phase 1 — 인상착의 텍스트에서 색상 추출 (규칙 기반, 모델 없음).

VARCO 3D 아바타 생성 설계 폐기 후속(2026-08-05, Notion "phase1 인상착의 아바타 — 고정
템플릿 + 색상 매핑 설계" 참고). 고정 실루엣(상의·하의·신발)에 색만 입히는 방식이라, 이
모듈은 색상 "이름"만 뽑는다 — 실제 hex 매핑·SVG 렌더링은 프론트 담당(백엔드는 이미지를
만들지 않는다).
"""

from __future__ import annotations

# 순서는 가독성용일 뿐 매칭 우선순위와 무관 — extract_color() 가 키워드 길이 내림차순으로
# 재정렬해서 검사하므로, 예를 들어 "카키그린"(olive)이 "카키"(khaki)보다 항상 먼저 매칭된다.
# 새 키워드를 추가할 때도 이 순서를 신경 쓸 필요 없다.
COLOR_KEYWORDS: list[tuple[str, str]] = [
    # red
    ("빨간", "red"), ("빨간색", "red"), ("빨강", "red"), ("빨강색", "red"),
    ("다홍", "red"), ("다홍색", "red"), ("진홍", "red"), ("진홍색", "red"),
    ("새빨간", "red"), ("레드", "red"),
    # orange
    ("주황", "orange"), ("주황색", "orange"), ("오렌지", "orange"),
    ("오렌지색", "orange"), ("귤색", "orange"),
    # yellow
    ("노란", "yellow"), ("노랑", "yellow"), ("노랑색", "yellow"), ("노란색", "yellow"),
    ("샛노란", "yellow"), ("황색", "yellow"),
    # mustard — 겨자색은 갈색 계열이 아니라 노랑에 가까운 옷 색이라 별도 태그로 분리
    ("머스타드", "mustard"), ("머스타드색", "mustard"), ("겨자색", "mustard"), ("겨자", "mustard"),
    # green
    ("초록", "green"), ("초록색", "green"), ("녹색", "green"),
    ("그린", "green"), ("풀색", "green"), ("풀빛", "green"),
    # olive — 카키그린을 khaki 보다 먼저 잡기 위한 전용 키워드
    ("올리브", "olive"), ("올리브색", "olive"), ("국방색", "olive"), ("카키그린", "olive"),
    # khaki
    ("카키", "khaki"), ("카키색", "khaki"), ("카키색상", "khaki"),
    # mint
    ("민트", "mint"), ("민트색", "mint"), ("민트그린", "mint"),
    # teal
    ("청록", "teal"), ("청록색", "teal"), ("틸", "teal"),
    # skyblue
    ("하늘색", "skyblue"), ("하늘빛", "skyblue"), ("스카이블루", "skyblue"), ("연파랑", "skyblue"),
    # blue
    ("파란", "blue"), ("파랑", "blue"), ("파란색", "blue"), ("파랑색", "blue"),
    ("블루", "blue"), ("청색", "blue"),
    # navy — "남색"만으로는 blue 와 구분이 안 되므로 별도 태그
    ("남색", "navy"), ("네이비", "navy"), ("네이비색", "navy"), ("진남색", "navy"), ("감청색", "navy"),
    # purple
    ("보라", "purple"), ("보라색", "purple"), ("퍼플", "purple"),
    ("자주색", "purple"), ("자주빛", "purple"),
    # lavender
    ("라벤더", "lavender"), ("연보라", "lavender"), ("연보라색", "lavender"),
    # pink
    ("분홍", "pink"), ("분홍색", "pink"), ("핑크", "pink"), ("핑크색", "pink"), ("연분홍", "pink"),
    # peach
    ("살구색", "peach"), ("살구빛", "peach"), ("피치", "peach"), ("피치색", "peach"),
    # brown
    ("갈색", "brown"), ("브라운", "brown"), ("고동색", "brown"),
    ("고동", "brown"), ("흙색", "brown"), ("밤색", "brown"),
    # camel
    ("카멜", "camel"), ("카멜색", "camel"), ("낙타색", "camel"),
    # beige
    ("베이지", "beige"), ("베이지색", "beige"),
    # ivory
    ("아이보리", "ivory"), ("크림색", "ivory"), ("크림", "ivory"), ("미색", "ivory"),
    # wine
    ("와인색", "wine"), ("와인", "wine"), ("버건디", "wine"), ("자두색", "wine"),
    # black
    ("검정", "black"), ("검정색", "black"), ("검은", "black"), ("검은색", "black"),
    ("까만", "black"), ("까만색", "black"), ("블랙", "black"), ("흑색", "black"),
    # white
    ("하양", "white"), ("하양색", "white"), ("하얀", "white"), ("하얀색", "white"),
    ("흰", "white"), ("흰색", "white"), ("화이트", "white"), ("백색", "white"),
    # gray
    ("회색", "gray"), ("쥐색", "gray"), ("그레이", "gray"), ("잿빛", "gray"), ("재색", "gray"),
    # charcoal — "진회색"은 gray 보다 charcoal 로 잡아야 렌더링 대비가 살아서 별도 태그
    ("차콜", "charcoal"), ("차콜색", "charcoal"), ("진회색", "charcoal"), ("숯색", "charcoal"),
    # gold
    ("금색", "gold"), ("골드", "gold"), ("금빛", "gold"),
    # silver
    ("은색", "silver"), ("실버", "silver"), ("은빛", "silver"),
]

# "카키그린"(olive, 4글자) 이 "카키"(khaki, 2글자) 보다 먼저 검사되도록 키워드 길이
# 내림차순으로 정렬 — COLOR_KEYWORDS 에 새 항목을 추가해도 이 정렬이 자동으로 처리한다.
_SORTED_KEYWORDS = sorted(COLOR_KEYWORDS, key=lambda kv: -len(kv[0]))


def extract_color(text: str) -> str:
    """텍스트에서 색상 키워드를 찾아 표준 ColorTag 문자열로 매핑.

    매칭 실패 시 "unknown"(프론트에서 중립 회색으로 폴백 렌더링) — 근거 없는 색을
    추측하지 않는다. 외부 호출 없는 순수 함수라 입력이 같으면 출력도 항상 같다.
    """
    if not text:
        return "unknown"
    for keyword, tag in _SORTED_KEYWORDS:
        if keyword in text:
            return tag
    return "unknown"

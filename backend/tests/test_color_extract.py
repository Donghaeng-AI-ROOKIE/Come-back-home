"""인상착의 텍스트 → 색상 태그 추출 (규칙 기반, 모델 없음) 테스트."""

from __future__ import annotations

import pytest

from app.phase1.color_extract import COLOR_KEYWORDS, extract_color

ALL_TAGS = sorted({tag for _, tag in COLOR_KEYWORDS})


def test_all_27_tags_reachable():
    """사전에 정의된 태그 전부 최소 한 키워드로 실제 매칭되는지 — 사전에 죽은 태그가
    남지 않게 한다."""
    assert len(ALL_TAGS) == 27
    for tag in ALL_TAGS:
        keywords = [kw for kw, t in COLOR_KEYWORDS if t == tag]
        assert keywords, f"{tag} 에 매칭되는 키워드가 사전에 없음"
        assert extract_color(f"{keywords[0]} 점퍼") == tag


@pytest.mark.parametrize(
    "text,expected",
    [
        ("빨간 점퍼를 입었어요", "red"),
        ("새빨간 니트", "red"),
        ("주황색 바람막이", "orange"),
        ("샛노란 우산을 들고 있었음", "yellow"),
        ("머스타드색 가디건", "mustard"),
        ("초록색 티셔츠", "green"),
        ("국방색 패딩", "olive"),
        ("카키색 바지", "khaki"),
        ("민트색 스카프", "mint"),
        ("청록색 조끼", "teal"),
        ("하늘색 셔츠", "skyblue"),
        ("파란 점퍼에 회색 바지", "blue"),
        ("네이비색 재킷", "navy"),
        ("진남색 코트", "navy"),
        ("보라색 목도리", "purple"),
        ("연보라 가디건", "lavender"),
        ("분홍색 원피스", "pink"),
        ("살구색 블라우스", "peach"),
        ("갈색 바지", "brown"),
        ("카멜색 코트", "camel"),
        ("베이지색 바지", "beige"),
        ("아이보리 니트", "ivory"),
        ("와인색 카디건", "wine"),
        ("검정 바지", "black"),
        ("까만 운동화", "black"),
        ("흰색 운동화", "white"),
        ("회색 후드티", "gray"),
        ("진회색 코트", "charcoal"),
        ("금색 목걸이", "gold"),
        ("은색 시계", "silver"),
    ],
)
def test_representative_keywords(text: str, expected: str):
    assert extract_color(text) == expected


def test_no_match_falls_back_to_unknown():
    assert extract_color("체크무늬 조끼를 입고 있었어요") == "unknown"


def test_empty_text_falls_back_to_unknown():
    assert extract_color("") == "unknown"
    assert extract_color(None) == "unknown"  # type: ignore[arg-type]


def test_olive_wins_over_khaki_substring():
    """'카키그린'은 'olive'로 잡혀야 한다 — 'khaki'(카키) 가 부분 문자열로 먼저
    매칭되면 안 된다(길이 내림차순 정렬로 보장)."""
    assert extract_color("카키그린 야상") == "olive"
    assert extract_color("카키색 면바지") == "khaki"


def test_navy_wins_over_blue():
    """'남색'은 'navy'로 잡혀야지 'blue'(파란/파랑)로 잘못 잡히면 안 된다."""
    assert extract_color("남색 정장 바지") == "navy"


@pytest.mark.parametrize(
    "text,expected",
    [
        # 긴 키워드가 짧은 다른 태그 키워드를 부분 문자열로 포함하는 경우 —
        # 정렬(_SORTED_KEYWORDS)이 항상 긴 쪽을 먼저 잡아야 한다.
        ("카키그린 야상", "olive"),      # '그린'(green) 포함
        ("스카이블루 셔츠", "skyblue"),  # '블루'(blue) 포함
        ("연파랑 니트", "skyblue"),      # '파랑'(blue) 포함
        ("연보라 원피스", "lavender"),   # '보라'(purple) 포함
        ("연보라색 가디건", "lavender"),  # '보라색'(purple) 포함
        ("진회색 코트", "charcoal"),     # '회색'(gray) 포함
        ("감청색 넥타이", "navy"),       # '청색'(blue) 포함
    ],
)
def test_longer_keyword_wins_over_embedded_shorter_keyword(text: str, expected: str):
    assert extract_color(text) == expected


def test_no_keyword_registered_under_two_different_tags():
    """같은 문자열이 서로 다른 태그로 이중 등록되면 사전 순서에 따라 결과가 뒤집힐
    수 있다 — 사전 자체의 무결성을 보장한다."""
    seen: dict[str, str] = {}
    for keyword, tag in COLOR_KEYWORDS:
        if keyword in seen and seen[keyword] != tag:
            pytest.fail(f"'{keyword}' 가 '{seen[keyword]}' 와 '{tag}' 양쪽에 등록됨")
        seen[keyword] = tag


def test_no_partial_word_false_positive():
    """'파' 한 글자로 오매칭되지 않아야 한다 — 색상과 무관한 단어에 색상 음절이
    섞여 있는 경우."""
    assert extract_color("파자마 차림이었어요") == "unknown"

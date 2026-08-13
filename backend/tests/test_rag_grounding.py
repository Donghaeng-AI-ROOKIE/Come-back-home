"""RAG 정합 검사 — 파인튜닝 답과 발췌가 어긋나는 지점을 신호로 뽑는다 (P1-4)."""

from app.rag.grounding import check_numeric_grounding, summarize

PASSAGE = ["도보 실종자의 53%가 최종 목격 지점에서 1마일 이내, 75%가 5마일 이내에서 "
           "발견되었다. 사망자의 50%는 0.5마일 이내였다."]


def test_발췌에_있는_수치는_근거로_인정된다():
    r = check_numeric_grounding("도보 실종자의 53%는 1마일 이내에서 발견된다.", PASSAGE)
    assert r["flagged"] is False
    assert r["ratio"] == 1.0


def test_발췌에_없는_수치는_신호로_잡힌다():
    r = check_numeric_grounding("실종자의 88%는 12km 이내에서 발견된다.", PASSAGE)
    assert r["flagged"] is True
    assert set(r["unsupported"]) == {"88", "12"}


def test_입력에_있는_수치도_근거로_인정된다():
    """실종자 나이처럼 발췌가 아니라 입력에서 온 수치를 환각으로 몰면 안 된다."""
    r = check_numeric_grounding("78세 치매 노인은 근거리에 머무를 가능성이 높다.",
                                PASSAGE, extra_context="- 유형: 치매, 나이: 78세")
    assert r["flagged"] is False


def test_수치가_없으면_판정하지_않는다():
    """수치 없는 답을 '근거 있음'으로 세면 지표가 부풀려진다."""
    r = check_numeric_grounding("근거리부터 수색하는 편이 낫다.", PASSAGE)
    assert r["ratio"] is None
    assert r["flagged"] is False
    assert r["checked"] == 0


def test_한자리_수는_대조에서_뺀다():
    """순위·개수 같은 작은 정수까지 잡으면 경고가 무의미해진다."""
    r = check_numeric_grounding("전략 3가지를 우선 고려한다.", PASSAGE)
    assert r["flagged"] is False


def test_천단위_쉼표와_소수점_표기를_같은_수로_본다():
    p = ["표본은 2,278건이며 평균 연령은 11.88세였다."]
    r = check_numeric_grounding("2278건에서 평균 11.880세로 나타났다.", p)
    assert r["flagged"] is False


def test_발췌가_없으면_검사_자체를_건너뛴다():
    """RAG 가 꺼진 경로에서 모든 수치를 근거 없음으로 표시하면 경고가 쏟아진다."""
    r = check_numeric_grounding("53%가 1마일 이내다.", [])
    assert r["unsupported"] == ["53"]      # 함수는 그대로 계산하고
    # 호출부(exaone._log_grounding)가 passages 없으면 아예 부르지 않는다


def test_요약_문구():
    assert "모두" in summarize(check_numeric_grounding("53%", PASSAGE))
    assert "⚠" in summarize(check_numeric_grounding("99%", PASSAGE))
    assert "없음" in summarize(check_numeric_grounding("수치 없는 문장", PASSAGE))


def test_앞자리_0을_생략한_소수도_같은_값으로_본다():
    """국내 저널·통계표는 .51 로 쓴다. 이걸 놓치면 원문에 있는 값을 환각으로 신고한다.

    실측: 자동생성 QA 감사에서 보행속도 0.51/0.98 이 원문에 `.51±.18m/s` 로
    적혀 있는데도 '근거 없음'으로 잡혔다.
    """
    p = ["Dementia Speed .51±.18m/s, STcv 12.88±6.78%"]
    r = check_numeric_grounding("치매군의 보행 속도는 0.51m/s였다.", p)
    assert r["flagged"] is False

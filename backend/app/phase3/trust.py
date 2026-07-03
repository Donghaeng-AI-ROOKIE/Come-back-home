"""Phase 3 — 제보 신뢰도 p 산출 (신뢰 온도 측정).

입력: Varco Vision 사진 대조 유사도 + Mi:dm 구조화 결과(구체성) + 위치·시각 특정 여부.
출력: p ∈ [0, 1]. 이 p 는 이진(통과/파기)이 아니라 값 그대로
POA 갱신 모듈에 전달된다 (설계 결정사항).
"""

from app.llm import midm, varco
from app.schemas.report import Appearance
from app.schemas.tip import Tip


def score_tip(tip: Tip, reference: Appearance | None, tip_image: bytes | None = None) -> float:
    """제보 신뢰도 p 산출. 가중치는 예시값 — 시뮬레이션 테스트로 튜닝."""
    structured = midm.structure_tip(tip.text)

    p = 0.3  # 기본값: 익명 제보의 사전 신뢰

    # 사진 대조 (가장 강한 신호)
    if tip.has_photo:
        similarity = varco.compare_photo(tip_image, reference)
        p += 0.4 * similarity

    # 위치·시각 특정 여부
    if tip.location is not None:
        p += 0.15
    if tip.seen_at is not None:
        p += 0.1

    # 제보 구체성 (Mi:dm 구조화 결과)
    p += 0.1 * structured.get("specificity", 0.0)

    return min(1.0, max(0.0, p))


def has_specific_location_time(tip: Tip) -> bool:
    """층2(새 LKP) 자격 조건 — 위치와 시각이 모두 특정되어야 시뮬 앵커가 될 수 있다."""
    return tip.location is not None and tip.seen_at is not None

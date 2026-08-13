"""검수한 문헌 진술을 재현 가능한 claims.jsonl로 만든다."""

from __future__ import annotations

import json
import re
from pathlib import Path


HERE = Path(__file__).resolve().parent

# candidate_id를 쓰면 extract_corpus.py가 만든 정규화 문장을 인용으로 사용한다.
# 표처럼 문장 후보에 잡히지 않는 경우 source=(paper_id, pdf_page, quote)를 쓴다.
SEEDS = [
    # 치매: 가족 돌봄 제공자 관찰 연구 Table 2
    dict(source=("DEM-24", 6, "Frequent and/or continuous movement from one place to another(usually the same place)"),
         population="dementia", domain="wandering_pattern",
         condition="배회가 나타나는 치매노인", behavior="같은 장소를 포함해 한 장소에서 다른 장소로 빈번하거나 지속적으로 이동한다.",
         behavior_class="continued_movement", evidence_type="caregiver_observation"),
    dict(source=("DEM-24", 6, "Continuous ambulation to find something, someone, or some place"),
         population="dementia", domain="goal_seeking",
         condition="무언가·누군가·어떤 장소를 찾는 배회가 나타날 때", behavior="찾는 대상을 향해 계속 걷는다.",
         behavior_class="goal_seeking", evidence_type="caregiver_observation"),
    dict(source=("DEM-24", 6, "Ambulation at random"),
         population="dementia", domain="wandering_pattern",
         condition="뚜렷한 목적이 없는 배회가 나타날 때", behavior="무작위로 걷는다.",
         behavior_class="aimless_movement", evidence_type="caregiver_observation"),
    dict(source=("DEM-24", 6, "Ambulation to enter other persons' room or prohibited area"),
         population="dementia", domain="boundary_crossing",
         condition="공간 경계를 구분하기 어려운 배회 상황", behavior="다른 사람의 방이나 금지된 구역으로 들어간다.",
         behavior_class="boundary_crossing", evidence_type="caregiver_observation"),
    dict(source=("DEM-24", 6, "Ambulation resulting in unpurposeful elopement"),
         population="dementia", domain="elopement",
         condition="목적이 분명하지 않은 배회 상황", behavior="목적 없는 이탈로 이어질 수 있다.",
         behavior_class="aimless_movement", evidence_type="caregiver_observation"),
    dict(source=("DEM-24", 6, "Continuous ambulation with no apparent destination"),
         population="dementia", domain="wandering_pattern",
         condition="겉으로 확인되는 목적지가 없는 배회 상황", behavior="특정 목적지 없이 계속 걷는다.",
         behavior_class="aimless_movement", evidence_type="caregiver_observation"),
    dict(source=("DEM-24", 6, "Anxious and restless ambulation"),
         population="dementia", domain="distress",
         condition="불안하고 안절부절못하는 상태", behavior="불안한 모습으로 계속 걷거나 왔다 갔다 한다.",
         behavior_class="distress_movement", evidence_type="caregiver_observation"),
    dict(source=("DEM-24", 6, "Inability to recognize important indicators in familiar places"),
         population="dementia", domain="wayfinding",
         condition="치매노인이 익숙한 장소에 있더라도", behavior="길찾기에 중요한 표시를 알아보지 못할 수 있다.",
         behavior_class="wayfinding_failure", evidence_type="caregiver_observation"),
    dict(source=("DEM-24", 6, "Ambulation cannot be stopped or switched to other activities"),
         population="dementia", domain="persistence",
         condition="지속적 배회가 시작된 상태", behavior="걷기를 멈추거나 다른 활동으로 전환하지 못할 수 있다.",
         behavior_class="continued_movement", evidence_type="caregiver_observation"),
    dict(source=("DEM-24", 6, "Shadowing other person or caregiver"),
         population="dementia", domain="social_following",
         condition="익숙한 사람이나 돌봄 제공자가 가까이 있을 때", behavior="그 사람을 그림자처럼 따라다닐 수 있다.",
         behavior_class="person_seeking", evidence_type="caregiver_observation"),
    dict(source=("DEM-24", 6, "Hyperactivity or searching behavior"),
         population="dementia", domain="search_behavior",
         condition="배회 중 활동성이 높거나 무언가를 찾는 상태", behavior="과잉 활동이나 탐색 행동을 보인다.",
         behavior_class="search_behavior", evidence_type="caregiver_observation"),
    dict(source=("DEM-24", 6, "Getting lost"),
         population="dementia", domain="wayfinding",
         condition="치매노인이 독립적으로 이동할 때", behavior="길을 잃을 수 있다.",
         behavior_class="wayfinding_failure", evidence_type="caregiver_observation"),

    # 치매: missing incident와 길찾기
    dict(candidate_id="DEM-31-P0006-S006", population="dementia", domain="missing_context",
         condition="지역사회 치매 실종 사건", behavior="예측 가능한 반복 보행보다 평범한 일상 활동 중 발생하는 경우가 많다.",
         behavior_class="routine_activity_loss", evidence_type="case_series"),
    dict(candidate_id="DEM-31-P0006-S009", population="dementia", domain="seclusion",
         condition="일부 치매 실종자가 자연 공간에 들어간 경우", behavior="마지막 확인 지점 가까운 자연 공간에 몸을 숨기고 발견될 때까지 거의 움직이지 않을 수 있다.",
         behavior_class="hiding_or_staying", evidence_type="case_series"),
    dict(candidate_id="DEM-31-P0006-S024", population="dementia", domain="error_recovery",
         condition="평소 활동 중 공간적 방향상실이 발생하면", behavior="길찾기 오류를 스스로 회복하지 못할 수 있다.",
         behavior_class="wayfinding_failure", evidence_type="case_series_inference"),
    dict(candidate_id="DEM-31-P0006-S007", population="dementia", domain="transport",
         condition="치매 실종 사건에서 이동할 때", behavior="걷기뿐 아니라 운전·자전거·대중교통 등 여러 이동수단을 사용할 수 있다.",
         behavior_class="transport_use", evidence_type="case_series"),
    dict(candidate_id="DEM-31-P0004-S010", population="dementia", domain="distance",
         condition="치매 실종자가 도보로 이동한 경우", behavior="절반 이상은 마지막 확인 지점 1마일 안에서, 4분의 3은 5마일 안에서 발견됐다.",
         behavior_class="distance_prior", evidence_type="case_series"),
    dict(candidate_id="DEM-34-P0004-S009", population="dementia", domain="missing_context",
         condition="치매 실종 사건이 발생하는 흔한 맥락", behavior="보호자가 허용한 일상적·독립적 지역사회 활동 중에도 실종될 수 있다.",
         behavior_class="routine_activity_loss", evidence_type="concept_review"),
    dict(candidate_id="DEM-34-P0004-S011", population="dementia", domain="familiarity",
         condition="일상적·독립적 외출을 하는 치매환자", behavior="대체로 익숙한 장소로 이동한다.",
         behavior_class="familiar_route", evidence_type="concept_review"),
    dict(candidate_id="DEM-34-P0004-S016", population="dementia", domain="temporal_trigger",
         condition="밤에 보호자가 자고 있거나 치매환자가 초조한 상태", behavior="집을 나가는 실종 선행 상황이 나타날 수 있다.",
         behavior_class="distress_movement", evidence_type="concept_review"),
    dict(candidate_id="DEM-34-P0005-S015", population="dementia", domain="caregiver_seeking",
         condition="돌봄 제공자를 기다리라는 지시를 기억하지 못하면", behavior="돌봄 제공자를 찾으려는 잘못된 시도로 그 장소를 떠날 수 있다.",
         behavior_class="person_seeking", evidence_type="concept_review"),
    dict(candidate_id="DEM-34-P0006-S002", population="dementia", domain="disease_progression",
         condition="치매가 초기일 때와 이후 더 진행됐을 때", behavior="초기에는 낯선 곳의 길찾기가 손상되고, 진행되면 익숙한 주변에서도 길찾기가 어려워진다.",
         behavior_class="wayfinding_failure", evidence_type="concept_review"),
    dict(candidate_id="DEM-34-P0006-S004", population="dementia", domain="error_recovery",
         condition="익숙한 경로에서 목적지를 지나친 뒤 반대 방향에서 다시 접근하면", behavior="목적지를 알아보지 못할 수 있다.",
         behavior_class="wayfinding_failure", evidence_type="concept_review"),
    dict(candidate_id="DEM-34-P0005-S018", population="dementia", domain="hazard_awareness",
         condition="자신의 결손을 인식하지 못하거나 과소평가하는 경우", behavior="초조할 때 집을 나가거나, 혼자 걷거나 운전하거나, 악천후에 준비 없이 나가는 위험 행동을 시도할 수 있다.",
         behavior_class="hazard_unawareness", evidence_type="concept_review"),
    dict(candidate_id="DEM-26-P0001-S007", population="dementia", domain="wayfinding",
         condition="단순 목적지 길찾기와 포괄적 전략 능력이 낮을수록", behavior="이탈행동과 공간적 방향상실이 더 많이 나타난다.",
         behavior_class="wayfinding_failure", evidence_type="correlational"),
    dict(candidate_id="DEM-22-P0006-S003", population="dementia", domain="familiarity",
         condition="치매노인의 환경 친숙성이 달라질 때", behavior="친숙성은 지속 보행·반복 보행·이탈 행동·부정적 결과의 유의한 예측변수였다.",
         behavior_class="familiar_route", evidence_type="correlational"),
    dict(candidate_id="DEM-23-P0002-S008", population="dementia", domain="emotion",
         condition="슬픔이나 분노 같은 부정적 감정을 잘 표현하는 치매환자", behavior="돌아다니기보다 혼자 앉아 있거나 방에 더 오래 머무를 수 있다.",
         behavior_class="hiding_or_staying", evidence_type="review"),
    dict(candidate_id="DEM-32-P0008-S029", population="dementia", domain="wayfinding",
         condition="단순 길찾기 목표 수행 효과가 낮아질수록", behavior="지속 보행·이탈 행동·부정적 결과의 빈도가 증가한다.",
         behavior_class="wayfinding_failure", evidence_type="correlational"),
    dict(source=("DEM-32", 5, "Repeatedly travels the same route while walking"), population="dementia", domain="route_pattern",
         condition="배회가 나타날 때", behavior="같은 경로를 반복해서 이동할 수 있다.",
         behavior_class="repetitive_route", evidence_type="caregiver_scale"),
    dict(source=("DEM-32", 5, "Travels many different routes while walking"), population="dementia", domain="route_pattern",
         condition="배회가 나타날 때", behavior="걸으면서 여러 다른 경로를 이동할 수 있다.",
         behavior_class="variable_route", evidence_type="caregiver_scale"),
    dict(candidate_id="DEM-33-P0011-S002", population="dementia", domain="wandering_core",
         condition="치매 배회의 핵심 양상을 설명할 때", behavior="공간적 방향상실과 지속 보행이 핵심 차원을 이룬다.",
         behavior_class="wayfinding_failure", evidence_type="psychometric"),
    dict(candidate_id="DEM-33-P0011-S004", population="dementia", domain="problem_wandering",
         condition="돌봄 제공자가 배회를 문제로 판단할 때", behavior="목적적이든 우발적이든 이탈 행동의 존재가 주된 영향을 준다.",
         behavior_class="boundary_crossing", evidence_type="psychometric"),
    dict(candidate_id="DEM-28-P0002-S008", population="dementia", domain="severity",
         condition="치매가 심하거나 인지기능이 낮고 공격성·우울·망상 등 행동심리증상이 동반될 때", behavior="배회 빈도가 증가할 수 있다.",
         behavior_class="continued_movement", evidence_type="systematic_review"),
]


def canonical(text: str) -> str:
    text = re.sub(r"(?<=\w)-\s+(?=\w)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> None:
    candidates = {row["candidate_id"]: row for row in load_jsonl(HERE / "candidates.jsonl")}
    manifest = {row["paper_id"]: row for row in load_jsonl(HERE / "corpus" / "manifest.jsonl")}
    page_cache: dict[tuple[str, int], str] = {}
    for paper_id in manifest:
        for row in load_jsonl(HERE / "corpus" / "pages" / f"{paper_id}.jsonl"):
            page_cache[(paper_id, row["pdf_page"])] = row["text"]

    out_dir = HERE / "claims"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "claims.jsonl"
    rows = []
    errors = []
    for index, seed in enumerate(SEEDS, 1):
        seed = dict(seed)
        candidate_id = seed.pop("candidate_id", None)
        if candidate_id:
            candidate = candidates[candidate_id]
            paper_id = candidate["paper_id"]
            pdf_page = candidate["pdf_page"]
            quote = candidate["sentence"]
        else:
            paper_id, pdf_page, quote = seed.pop("source")
        page_text = page_cache[(paper_id, pdf_page)]
        quote_verified = canonical(quote) in canonical(page_text)
        if not quote_verified:
            errors.append(f"{paper_id} p{pdf_page}: {quote[:80]}")
        meta = manifest[paper_id]
        rows.append({
            "claim_id": f"CLM-{index:04d}",
            **seed,
            "claim_scope": "group_tendency_not_individual_determinism",
            "confidence": 0.9 if seed["evidence_type"] in {
                "case_series", "correlational", "systematic_review", "experiment",
                "single_case_experiment", "fatality_case_series", "psychometric",
            } else 0.8,
            "source": {
                "paper_id": paper_id,
                "title": meta["title"],
                "source_path": meta["source_path"],
                "sha256": meta["sha256"],
                "pdf_page": pdf_page,
                "page_kind": "pdf_page_1_based",
                "quote": quote,
                "quote_verified": quote_verified,
            },
        })
    if errors:
        raise SystemExit("quote verification failed:\n" + "\n".join(errors))
    out_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(rows)} verified claims -> {out_path}")


if __name__ == "__main__":
    main()

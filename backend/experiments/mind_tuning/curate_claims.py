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

    # 발달장애/자폐: 이탈 기능·목표·공간행동
    dict(candidate_id="DEV-08-P0011-S003", population="developmental_disability", domain="elopement_goal",
         condition="자폐 아동의 이탈이 나타날 때", behavior="이탈은 흔히 목표 지향적이다.",
         behavior_class="goal_seeking", evidence_type="caregiver_survey"),
    dict(candidate_id="DEV-08-P0006-S003", population="developmental_disability", domain="elopement_motive",
         condition="달리기·탐색을 즐기거나 좋아하는 장소에 도달하려는 동기가 있을 때", behavior="이탈 행동이 나타날 수 있다.",
         behavior_class="goal_seeking", evidence_type="caregiver_survey"),
    dict(candidate_id="DEV-08-P0006-S013", population="developmental_disability", domain="missing_risk",
         condition="이탈한 자폐 아동 가운데 실제로 실종된 집단", behavior="더 나이가 많고 기술 퇴행을 경험했으며 이름에 반응하지 않는 경우가 더 많았다.",
         behavior_class="help_seeking_failure", evidence_type="caregiver_survey"),
    dict(candidate_id="DEV-08-P0007-S013", population="developmental_disability", domain="elopement_function",
         condition="자폐 아동의 이탈 기능을 분석할 때", behavior="선호 물건·활동, 관심, 회피 또는 감각 자극에 접근하기 위해 이탈할 수 있다.",
         behavior_class="goal_seeking", evidence_type="literature_summary"),
    dict(candidate_id="DEV-09-P0003-S019", population="developmental_disability", domain="elopement_function",
         condition="발달장애인의 이탈 기능을 분석할 때", behavior="관심, 회피, 유형물·활동 접근, 자동 강화 등 서로 다른 기능이 가능하다.",
         behavior_class="goal_seeking", evidence_type="systematic_review"),
    dict(candidate_id="DEV-03-P0005-S018", population="developmental_disability", domain="stereotypy",
         condition="상동행동에 접근할 수 있을 때", behavior="그 상동행동에 접근하기 위한 이탈이 유지될 수 있다.",
         behavior_class="goal_seeking", evidence_type="single_case_experiment"),
    dict(candidate_id="DEV-04-P0007-S009", population="developmental_disability", domain="interpersonal_trigger",
         condition="대인 갈등이 발생한 뒤", behavior="이탈의 선행 사건이 될 수 있다.",
         behavior_class="escape_behavior", evidence_type="critical_incident_analysis"),
    dict(candidate_id="DEV-04-P0007-S010", population="developmental_disability", domain="recurrence",
         condition="대인 갈등 뒤이며 과거 이탈 이력이 있을 때", behavior="다시 이탈할 위험에 대한 경계가 특히 필요하다.",
         behavior_class="escape_behavior", evidence_type="critical_incident_analysis"),
    dict(candidate_id="DEV-13-P0002-S023", population="developmental_disability", domain="water_risk",
         condition="자폐 아동의 치명적 익사 사례", behavior="주거지에서 이탈해 가까운 연못에서 익사한 사례가 대부분이었다.",
         behavior_class="water_seeking", evidence_type="fatality_case_series"),
    dict(candidate_id="DEV-16-P0005-S004", population="developmental_disability", domain="route_familiarity",
         condition="지적장애인이 일상적으로 길을 찾을 때", behavior="소수의 익숙한 경로는 따라갈 수 있는 경우가 많다.",
         behavior_class="familiar_route", evidence_type="experimental_background"),
    dict(candidate_id="DEV-16-P0014-S015", population="developmental_disability", domain="landmark",
         condition="지속적이고 정보성이 높은 랜드마크를 선택하도록 훈련받으면", behavior="경로에서 벗어날 위험을 줄일 수 있다.",
         behavior_class="landmark_seeking", evidence_type="experimental_inference"),
    dict(candidate_id="DEV-17-P0010-S022", population="developmental_disability", domain="route_familiarity",
         condition="자폐인의 경로 선택", behavior="잘 알고 익숙한 경로를 고수하는 경향이 보고된다.",
         behavior_class="familiar_route", evidence_type="experimental_discussion"),
    dict(candidate_id="DEV-17-P0010-S026", population="developmental_disability", domain="route_disruption",
         condition="익숙한 경로에서 벗어나야 할 때", behavior="높은 불안을 경험할 수 있다.",
         behavior_class="distress_movement", evidence_type="experimental_discussion"),
    dict(candidate_id="DEV-10-P0011-S005", population="developmental_disability", domain="search_pattern",
         condition="같은 공간 탐색 과제를 반복할 때", behavior="자폐 아동은 대조군보다 시행 간 탐색 경로 반복성이 낮았다.",
         behavior_class="variable_route", evidence_type="experiment"),
    dict(candidate_id="DEV-12-P0005-S026", population="developmental_disability", domain="visual_attention",
         condition="주의가 시각 장면의 세부에 강하게 집중될 때", behavior="주변 자극을 놓칠 수 있다.",
         behavior_class="attention_narrowing", evidence_type="experiment_discussion"),
    dict(candidate_id="DEV-14-P0001-S027", population="developmental_disability", domain="lost_assistance",
         condition="연구 참여 자폐 청소년들이 길을 잃었을 때", behavior="길을 잃었다는 사실을 알아차리지 못하고 도움을 요청하는 방법도 몰랐다.",
         behavior_class="help_seeking_failure", evidence_type="baseline_observation"),
    dict(candidate_id="DEV-14-P0005-S012", population="developmental_disability", domain="lost_assistance",
         condition="훈련 전 낯선 성인과 함께 있는 분리 상황", behavior="참여자 누구도 낯선 성인에게 도움을 요청하지 않았다.",
         behavior_class="help_seeking_failure", evidence_type="baseline_observation"),
    dict(candidate_id="DEV-20-P0007-S002", population="developmental_disability", domain="hazard_attraction",
         condition="공공장소에서 이탈한 일부 자폐 아동", behavior="위험을 거의 고려하지 않고 차량·물·숲 쪽으로 달려갈 수 있다.",
         behavior_class="hazard_attraction", evidence_type="caregiver_interview"),
    dict(candidate_id="DEV-20-P0007-S023", population="developmental_disability", domain="hazard_awareness",
         condition="일부 자폐 아동이 도로를 건널 때", behavior="위험을 인식하지 못하고 양쪽을 살피지 않을 수 있다.",
         behavior_class="hazard_unawareness", evidence_type="caregiver_interview"),
    dict(candidate_id="DEV-20-P0009-S014", population="developmental_disability", domain="water_fixation",
         condition="조사된 자폐 아동의 고착 관심을 비교할 때", behavior="물은 가장 흔히 보고된 고착 대상이었다.",
         behavior_class="water_seeking", evidence_type="qualitative_study"),
    dict(candidate_id="DEV-20-P0009-S018", population="developmental_disability", domain="sensory_avoidance",
         condition="감각 입력이나 통증에 과민한 일부 자폐 아동", behavior="높은 곳이나 물 같은 위험 자극을 조심하거나 회피할 수 있다.",
         behavior_class="hazard_avoidance", evidence_type="caregiver_interview"),
    dict(candidate_id="DEV-21-P0008-S023", population="developmental_disability", domain="repetition",
         condition="일부 보호자가 자녀의 이탈을 설명할 때", behavior="반복 활동을 좋아해 이탈을 즐기고 되풀이하는 의식처럼 나타날 수 있다.",
         behavior_class="repetitive_route", evidence_type="caregiver_interview"),
    dict(candidate_id="DEV-21-P0008-S027", population="developmental_disability", domain="visual_attraction",
         condition="반짝이는 불빛이 있는 가게를 지나갈 때", behavior="걸음을 멈추고 시각 자극에 반응할 수 있다.",
         behavior_class="attention_narrowing", evidence_type="caregiver_interview"),
    dict(candidate_id="DEV-01-P0016-S003", population="developmental_disability", domain="preparedness",
         condition="지적장애인이 보호자 없이 혼자 집을 나갈 때", behavior="휴대전화·배회감지기·미아방지 목걸이를 챙기지 않는 경우가 많다.",
         behavior_class="hazard_unawareness", evidence_type="caregiver_interview"),
    dict(candidate_id="DEV-01-P0014-S001", population="developmental_disability", domain="recognition",
         condition="성인 지적장애인이 혼자 길을 배회할 때", behavior="주변 시민이 실종 상황으로 알아차리기 어려울 수 있다.",
         behavior_class="help_seeking_failure", evidence_type="administrative_interview"),
    dict(candidate_id="DEV-01-P0026-S010", population="developmental_disability", domain="duration",
         condition="건강한 성인 지적장애인의 실종이 길어질 때", behavior="쉽게 탈진하지 않고 일반 성인처럼 보여 제보가 부족해질 수 있다.",
         behavior_class="continued_movement", evidence_type="police_interview"),
    # Encyclopedia of Autism Spectrum Disorders: Elopement 표적 항목
    dict(candidate_id="DEV-19-P1758-S014", population="developmental_disability", domain="elopement_location",
         condition="자폐 아동의 이탈이 발생한 장소를 조사했을 때", behavior="가정과 공원·야외 공간이 가장 흔한 이탈 장소였다.",
         behavior_class="boundary_crossing", evidence_type="encyclopedia_review"),
    dict(candidate_id="DEV-19-P1758-S016", population="developmental_disability", domain="severity",
         condition="자폐 중증도와 동반 어려움이 클수록", behavior="이탈 빈도가 더 높게 나타났다.",
         behavior_class="continued_movement", evidence_type="encyclopedia_review"),
    dict(candidate_id="DEV-19-P1758-S017", population="developmental_disability", domain="individual_function",
         condition="ADHD가 동반된 경우와 불안장애가 동반된 경우", behavior="전자는 과도한 에너지 때문에, 후자는 스트레스 환경을 벗어나기 위해 이탈할 가능성이 각각 높아 동기가 개인마다 달랐다.",
         behavior_class="escape_behavior", evidence_type="encyclopedia_review"),
    dict(candidate_id="DEV-19-P1757-S007", population="developmental_disability", domain="missing_hazard",
         condition="자폐 아동이 우려할 만큼 오래 실종된 경우", behavior="익사와 교통사고 위험에 처한 사례가 많이 보고됐다.",
         behavior_class="hazard_unawareness", evidence_type="encyclopedia_review"),
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

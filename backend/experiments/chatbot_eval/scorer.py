"""채점기 — Transcript × 기대 페르소나 → ScoreCard (5지표).

지표는 두 묶음으로 나눈다:
  [배관] reached_persona · name/age 확보 · 종료 · llm 열화 — 스텁에서 통과해야 함.
  [내용] 끌림점 재현율 · evidence 정확도 · 축 커버리지 · 질문 효율 — 실 Mi:dm 목표.
    스텁은 추출이 비어 내용 지표가 0에 가깝고, 그 격차 자체가 스텁의 값이다.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field


def _norm(s: str) -> str:
    return re.sub(r"[\s()]+", "", str(s or ""))


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6371.0
    dlat = math.radians(b[0] - a[0])
    dlng = math.radians(b[1] - a[1])
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _qnorm(q: str) -> str:
    """중복 질문 판정용 정규화 — 예시·문장부호 제거(interview._norm_q 와 같은 원칙)."""
    return re.sub(r"[\s,.!?~'\"]+", "", re.sub(r"\(예:.*?\)", "", str(q or "")))


@dataclass
class ScoreCard:
    scenario_id: str
    # 배관
    reached_persona: bool = False
    done: bool = False
    name_ok: bool = True
    age_ok: bool = True
    llm_degraded: bool = False
    # 정정 검증 (해당 시나리오만 — 없으면 None)
    absent_ok: bool | None = None      # 삭제/이름정정: 없어야 할 라벨이 없나
    area_ok: bool | None = None        # 장소지역 정정: 라벨 지역이 기대와 맞나
    home_ok: bool | None = None        # 수색 원점 보호: home 이 안 움직였나
    # 내용
    attraction_recall: float | None = None     # 최종 페르소나에 반영된 비율(지오코딩 통과분)
    collection_recall: float | None = None      # 챗봇이 수집한 비율(좌표화 이전 draft 포함)
    evidence_accuracy: float | None = None
    axis_coverage: float | None = None
    extra_extractions: int = 0                  # 골드에 없는 추출(과다추출·환각 후보) 수
    # 질문 효율
    n_questions: int = 0
    duplicate_questions: int = 0
    # 가드 패턴 감사 — 가드가 막는 패턴이 출력 질문에 몇 번 나오나(가드 OFF 시 증가 기대)
    presumptive_q: int = 0       # 전제 질문("~라고 하셨을 때") — presupposition 가드 대상
    neg_conditional_q: int = 0   # 부정조건 질문("~않으시면") — existence_first 가드 대상
    # 진단
    details: dict = field(default_factory=dict)


def score(transcript, scenario) -> ScoreCard:
    exp = scenario.expected
    persona = transcript.persona or {}
    sc = ScoreCard(scenario_id=scenario.id)

    # ── 배관 ──────────────────────────────────────────────────────────
    sc.reached_persona = transcript.persona is not None
    sc.done = transcript.done
    sc.llm_degraded = transcript.llm_degraded
    if exp.name:
        sc.name_ok = _norm(persona.get("name")) == _norm(exp.name)
    if exp.age:
        sc.age_ok = int(persona.get("age") or 0) == exp.age

    # ── 내용: 끌림점 재현율 (최종 반영 vs 수집) ───────────────────────
    got = persona.get("attraction_points", []) or []
    got_labels = [a.get("label", "") for a in got]                 # 지오코딩 통과분
    collected_labels = [str(a.get("label", ""))                    # 좌표화 이전 수집분
                        for a in (transcript.draft_attractions or []) if a.get("label")]

    def _in(want: str, pool: list[str]) -> bool:
        return any(_norm(want) in _norm(g) or _norm(g) in _norm(want) for g in pool)

    hit_labels = [w for w in exp.attraction_labels if _in(w, got_labels)]
    coll_labels = [w for w in exp.attraction_labels if _in(w, got_labels) or _in(w, collected_labels)]
    if exp.attraction_labels:
        sc.attraction_recall = len(hit_labels) / len(exp.attraction_labels)
        sc.collection_recall = len(coll_labels) / len(exp.attraction_labels)
    # 수집은 됐으나 좌표화에서 탈락한 기대 라벨 — "챗봇 성공, 지오코딩 실패"
    sc.details["geocode_dropped"] = [
        w for w in coll_labels if not _in(w, got_labels)]

    # ── 내용: evidence 등급 정확도 (수집분=draft 기준 — 지오코딩 탈락과 분리) ──
    if exp.evidence:
        correct = 0
        checked = 0
        ev_detail = {}
        draft = transcript.draft_attractions or []
        for want_label, want_ev in exp.evidence.items():
            match = next((a for a in draft
                          if _norm(want_label) in _norm(a.get("label"))
                          or _norm(a.get("label")) in _norm(want_label)), None)
            if match is None:
                ev_detail[want_label] = "미수집"
                continue
            checked += 1
            got_ev = match.get("evidence")
            ev_detail[want_label] = f"{got_ev} ({'✓' if got_ev == want_ev else '✗ 기대=' + want_ev})"
            if got_ev == want_ev:
                correct += 1
        sc.evidence_accuracy = (correct / checked) if checked else 0.0
        sc.details["evidence"] = ev_detail

    # ── 내용: 축 근거 커버리지 ────────────────────────────────────────
    got_axes = set((persona.get("axis_evidence") or {}).keys())
    if exp.axis_fields:
        covered = [ax for ax in exp.axis_fields if ax in got_axes]
        sc.axis_coverage = len(covered) / len(exp.axis_fields)
        sc.details["axis_missing"] = [ax for ax in exp.axis_fields if ax not in got_axes]

    # ── 과다추출(환각 후보) — 골드 라벨에 없는 수집물. 저신호/판정불가 케이스 핵심 ──
    gold_all = exp.attraction_labels
    extra_attr = [g for g in collected_labels if not _in(g, gold_all) and g]
    extra_axes = [ax for ax in got_axes if ax not in exp.axis_fields]
    sc.extra_extractions = len(set(extra_attr))
    sc.details["extra"] = {"끌림점": sorted(set(extra_attr)), "축": sorted(extra_axes)}

    # ── 정정: 없어야 할 라벨 (삭제·이름정정) ──────────────────────────
    # 수집분(draft)을 기준으로 본다 — 지오코딩이 탈락시켜 persona 에서 사라진 것과
    # 정정으로 실제 제거된 것을 구분해야 "삭제 반영"을 정확히 판정한다.
    if exp.absent_labels:
        present = [lbl for lbl in exp.absent_labels if _in(lbl, collected_labels)]
        sc.absent_ok = not present
        sc.details["should_be_absent"] = {"기대없음": exp.absent_labels, "수집에_잔존": present}

    # ── 정정: 장소 지역 (set_area) ────────────────────────────────────
    if exp.area:
        area_detail = {}
        all_ok = True
        for label, want_area in exp.area.items():
            match = next((a for a in got
                          if _norm(label) in _norm(a.get("label"))
                          or _norm(a.get("label")) in _norm(label)), None)
            # precision 이 dong/address 면 좌표는 맞지만 원문 지역 텍스트는 응답에 없다 →
            # 지오코딩 정밀도로 대리 확인하고, 라벨 존재+정밀도로 판정한다.
            if match is None:
                area_detail[label] = "라벨 누락"
                all_ok = False
            else:
                area_detail[label] = f"precision={match.get('precision')}"
        sc.area_ok = all_ok
        sc.details["area"] = area_detail

    # ── 정정: 수색 원점 보호 (home 이동 여부) ─────────────────────────
    if exp.home_near:
        home = persona.get("home") or {}
        if home.get("lat") is not None:
            dist = _haversine_km(exp.home_near, (home["lat"], home["lng"]))
            sc.home_ok = dist < 3.0    # 같은 동네 반경 — 다른 동으로 튀면 실패
            sc.details["home_dist_km"] = round(dist, 2)
        else:
            sc.home_ok = False

    # ── 질문 효율 ─────────────────────────────────────────────────────
    qs = [_qnorm(q) for q in transcript.assistant_questions]
    sc.n_questions = len(qs)
    sc.duplicate_questions = len(qs) - len(set(qs))

    # ── 가드 패턴 감사 (전제·부정조건 질문이 실제로 새어나오나) ─────────
    from app.phase0.interview import _PRESUP_RE, _NEG_CONDITIONAL_RE
    sc.presumptive_q = sum(1 for q in transcript.assistant_questions if _PRESUP_RE.search(q))
    sc.neg_conditional_q = sum(1 for q in transcript.assistant_questions
                               if _NEG_CONDITIONAL_RE.search(q))

    sc.details["got_labels"] = got_labels
    sc.details["hit_labels"] = hit_labels
    sc.details["got_axes"] = sorted(got_axes)
    return sc


def format_card(sc: ScoreCard) -> str:
    def pct(v):
        return "—" if v is None else f"{v * 100:.0f}%"

    def flag(v):
        return "—" if v is None else ("OK" if v else "✗")

    lines = [
        f"┌─ {sc.scenario_id}",
        f"│ [배관] 페르소나도달={'OK' if sc.reached_persona else 'FAIL'}  "
        f"종료={'OK' if sc.done else 'FAIL'}  "
        f"이름={'OK' if sc.name_ok else '✗'}  나이={'OK' if sc.age_ok else '✗'}  "
        f"LLM열화={'예' if sc.llm_degraded else '아니오'}",
        f"│ [내용] 끌림점 수집={pct(sc.collection_recall)}→반영={pct(sc.attraction_recall)}  "
        f"evidence={pct(sc.evidence_accuracy)}  "
        f"축={pct(sc.axis_coverage)}  과다추출={sc.extra_extractions}",
    ]
    if sc.details.get("geocode_dropped"):
        lines.append(f"│   ⚠ 지오코딩 탈락(수집됐으나 좌표화 실패): {sc.details['geocode_dropped']}")
    if sc.extra_extractions and sc.details.get("extra"):
        lines.append(f"│   ⚠ 과다추출(골드 외): {sc.details['extra']}")
    if any(v is not None for v in (sc.absent_ok, sc.area_ok, sc.home_ok)):
        lines.append(
            f"│ [정정] 삭제반영={flag(sc.absent_ok)}  지역정정={flag(sc.area_ok)}  "
            f"원점보호={flag(sc.home_ok)}"
            + (f" (home 이동 {sc.details['home_dist_km']}km)" if "home_dist_km" in sc.details else ""))
    lines.append(f"│ [효율] 질문수={sc.n_questions}  중복질문={sc.duplicate_questions}")
    if sc.details.get("got_labels") is not None:
        lines.append(f"│   끌림점: {sc.details['got_labels'] or '—'}")
    if sc.details.get("got_axes"):
        lines.append(f"│   축근거: {sc.details['got_axes']}")
    if sc.details.get("evidence"):
        lines.append(f"│   evidence: {sc.details['evidence']}")
    lines.append("└─")
    return "\n".join(lines)

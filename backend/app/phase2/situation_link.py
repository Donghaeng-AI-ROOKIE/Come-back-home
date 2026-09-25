"""신고 상황 문장 ↔ 등록 장소 — 이번 외출의 목적지를 신고 시점에 잇는다.

개인 해석(K)은 사건 전에 준비되므로 신고서의 '실종 당시 상황'("출근하셔야 한다며", "오늘
옛집에 가신다고")을 읽지 못한다. 그 문장이 등록된 장소 중 어디로 이어지는지는 Mi:dm 이
판정하고(prompts.SITUATION_LINK_SYSTEM), 코드는 등록된 이름인지와 근거 구절이 신고 문장에
글자 그대로 있는지만 확인한다. 보호자 문장을 단어 규칙으로 해석하지 않는다.

장소 설명은 K 가 그 장소의 목적·경로·발견 이력 판단에 인용한 보호자 원문이다 — 라벨만으로는
'킨텍스'가 옛 직장인지 알 수 없다. 준비 결과가 없으면 링크를 만들지 않는다(K 경로 전용).
"""
from __future__ import annotations

import hashlib
import json
import re

from app.llm import initial_behavior, midm

_MAX_CONTEXT = 3
_CONTEXT_CHARS = 160


def _compact(text) -> str:
    return re.sub(r"[\s.,!?~'\"“”‘’()\[\]·…-]+", "", str(text or ""))


def places_context(persona) -> list[dict]:
    """등록 장소마다 K 가 그 장소 판단에 인용한 보호자 원문(최대 3개)."""
    core = (persona.prepared_initial or {}).get("core") or {}
    goals = core.get("goals") or {}
    if not goals:
        return []
    notes = {n["id"]: n["text"] for n in initial_behavior.evidence_notes(
        initial_behavior.build_payload(persona, None, [], None))}
    out = []
    for label in goals:
        ids = []
        for section in ("goals", "found_history", "routes"):
            leaf = (core.get(section) or {}).get(label) or {}
            ids += [i for i in leaf.get("note_ids", []) if i not in ids]
        context = [notes[i][:_CONTEXT_CHARS] for i in ids if i in notes][:_MAX_CONTEXT]
        out.append({"label": label, "context": context})
    return out


def link(persona, report) -> dict:
    """{"status", "links", "rejected", "unconfirmed"} — status: linked / none / unavailable / not_prepared."""
    places = places_context(persona) if persona is not None else []
    if not places or not report.situation.strip():
        return {"status": "not_prepared" if not places else "none", "links": [], "rejected": [], "unconfirmed": []}
    judged = midm.link_situation(report.situation, places)
    if judged is None:
        return {"status": "unavailable", "links": [], "rejected": [], "unconfirmed": []}
    situation = _compact(report.situation)
    grounded, rejected = [], []
    for item in judged:
        quote = _compact(item["quote"])
        (grounded if quote and quote in situation else rejected).append(item)
    # 원문에 있는 구절이라도 뜻이 이어지는지는 다른 질문으로 한 번 더 묻는다 — 4회차 개발 세트:
    # "비 오는 오후, 우산을 두고 나가셨음"(S10)·"잠깐 나갔다 오신다고"(H8)가 '평소 외출'로 이어졌다.
    context = ["신고 상황: " + report.situation] + [
        f"'{p['label']}'에 대한 보호자 기록: " + " / ".join(p["context"]) for p in places if p["context"]]
    links, unconfirmed = [], []
    for item in grounded:
        statement = (f"대상자는 이번에 '{item['place']}'에 가려고 나갔다." if item["relation"] == "stated_destination"
                     else f"대상자는 이번에 평소 하던 외출(산책 등)을 하러 나갔고, 그 외출은 '{item['place']}'와 관련된다.")
        answer = midm.check_claim(context, statement)
        (links if answer is True else unconfirmed).append({**item, "check": answer})
    # 확인 호출이 실패한 링크가 있으면 캐시하지 않고 다음 예측 때 다시 묻는다(cached 참고).
    status = ("unavailable" if any(x["check"] is None for x in unconfirmed)
              else "linked" if links else "none")
    return {"status": status, "links": links, "rejected": rejected, "unconfirmed": unconfirmed}


def _key(case, persona) -> str:
    fingerprint = ((persona.prepared_initial or {}).get("fingerprint") if persona is not None else None)
    return hashlib.sha256(json.dumps([case.report.situation, fingerprint], ensure_ascii=False)
                          .encode()).hexdigest()


def cached(case, persona) -> list[dict]:
    """같은 신고 문장·같은 준비 결과면 재예측 때 다시 부르지 않는다. 판정 실패는 캐시하지 않는다."""
    key = _key(case, persona)
    saved = case.situation_links
    if saved and saved.get("key") == key and saved.get("status") != "unavailable":
        return list(saved.get("links") or [])
    result = link(persona, case.report)
    case.situation_links = {"key": key, **result}
    return list(result["links"])

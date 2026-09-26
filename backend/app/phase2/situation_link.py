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


# 행선지, 그리고 나간 이유. 10회차: '무엇을 하러(산책, 장보기, 출근처럼)'는 예시가 범위를 좁혀
# H10 "'애들 끝날 시간 됐다'면서 서둘러 나가셨어요"를 목적 없음으로 판정했다.
PURPOSE = ("대상자가 이번에 어디로 가는지가 신고 상황에 적혀 있다.",
           "대상자가 이번에 왜 나갔는지가 신고 상황에 적혀 있다.")


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
    # 먼저 신고 문장만 보고(보호자 기록 없이) 이번 외출의 행선지나 하려던 일이 적혀 있는지 묻는다.
    # 기록을 함께 주면 습관에서 행선지를 추론한다 — 최종 게이트 1회차 P02: "혼자 댁을 나서셨는데"가
    # '혼자 나가시면 딸 집으로 오려고 하신다'는 기록 때문에 딸 집 목적지로 확인됐다. 행선지와 하려던 일은
    # 따로 묻는다 — 한 문장에 '~나 ~'로 묶으면 틀린다(9회차 H7 "늘 하시던 대로 산책을 나가셨는데"가 '없음').
    purpose = None
    if grounded:
        answers = []
        for question in PURPOSE:
            answers.append(midm.check_claim(["신고 상황: " + report.situation], question))
            if answers[-1] is True:
                break
        # 하나라도 '예'면 목적 있음, 둘 다 '아니오'면 없음, 판정 실패가 섞이면 모름(None — 버리지 않는다)
        purpose = True if True in answers else (False if all(a is False for a in answers) else None)
    for item in grounded:
        if purpose is False:
            unconfirmed.append({**item, "check": False, "purpose": False})
            continue
        # 인용 구절이 그 장소를 가리키는지만 묻는다. 관계 종류와 무관하게(6회차 H10: 종류를 잘못
        # 붙여 맞는 링크 탈락), 시간대 습관 추론은 제외한다(7회차 H13 '바람 좀 쐬고 온다'→텃밭,
        # H16 '어디 가신다는 말씀은 없으셨어요'→대화역 — 습관 시간대는 K 의 목적 시간대가 맡는다).
        statement = (f"신고 상황의 '{item['quote']}'(이)라는 말은 대상자가 이번에 '{item['place']}'에 가려 했거나 "
                     "그곳에서 하던 일을 하러 나갔다는 뜻이다.")
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

"""시연 온보딩 템플릿 — 저장·복제·확인 게이트 통과·리셋.

템플릿은 임시 경로(DEMO_ONBOARDING_TEMPLATE)에 쓴다. Mi:dm 은 conftest 가 스텁으로
고정하므로 "맞아요" 판정은 결정론적으로 confirm 이다.
"""

import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app import storage
from app.api import demo_onboarding
from app.demo_main import app
from app.schemas.persona import InterviewSession

client = TestClient(app)

GUARDIAN = "booth-guardian-test"


@pytest.fixture(autouse=True)
def _template_path(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_ONBOARDING_TEMPLATE", str(tmp_path / "tpl.json"))


def _awaiting_session(sid: str = "src-session") -> InterviewSession:
    """요약 확인 대기 상태의 세션 — 실제 온보딩이 끝난 시점의 모양을 최소로 흉내낸다."""
    s = InterviewSession(
        id=sid, guardian_name="원본 보호자", guardian_id="template-author", persona_type="dementia",
        messages=[
            {"role": "assistant", "text": "성함과 연세를 알려주세요."},
            {"role": "user", "text": "김영숙, 76세예요."},
            {"role": "assistant", "text": "지금 사시는 집은 어디인가요?"},
            {"role": "user", "text": "고양시 일산서구 대화동이요."},
            {"role": "assistant", "text": "📋 이렇게 등록할게요. 확인 부탁드려요.\n• 김영숙 · 76세\n이대로 등록할까요?"},
        ],
        filled_keys=["identity", "home"],
        draft_fields={"name": "김영숙", "age": 76, "home": "고양시 일산서구 대화동"},
        home_geo={"query": "고양시 일산서구 대화동", "lat": 37.673, "lng": 126.747,
                  "precision": "dong", "source": "test", "matched": True, "address": "고양시 일산서구 대화동"},
        draft_behaviors=["큰길을 따라 계속 걷는 습관"],
        awaiting_confirmation=True,
    )
    storage.interviews.save(s.id, s)
    return s


def test_template_missing_reports_exists_false_and_blocks_next_turn():
    r = client.get("/phase0/demo/onboarding/template")
    assert r.status_code == 200 and r.json()["exists"] is False
    # 템플릿이 없으면 '다음 체험 준비'는 아무것도 지우지 않고 404
    s = _awaiting_session("keep-me"); s.guardian_id = GUARDIAN; storage.interviews.save(s.id, s)
    r = client.post("/phase0/demo/onboarding/sessions", json={"guardian_id": GUARDIAN})
    assert r.status_code == 404
    assert storage.interviews.get("keep-me") is not None


def test_capture_rejects_session_not_awaiting_confirmation():
    s = _awaiting_session("not-ready")
    s.awaiting_confirmation = False
    storage.interviews.save(s.id, s)
    r = client.post("/phase0/demo/onboarding/template", json={"guardian_id": "template-author", "session_id": s.id})
    assert r.status_code == 409
    s.done = True
    storage.interviews.save(s.id, s)
    assert client.post("/phase0/demo/onboarding/template", json={"guardian_id": "template-author", "session_id": s.id}).status_code == 409
    assert client.post("/phase0/demo/onboarding/template", json={"guardian_id": "template-author", "session_id": "nope"}).status_code == 404


def test_capture_then_clone_gives_fresh_session_with_same_content():
    src = _awaiting_session()
    r = client.post("/phase0/demo/onboarding/template", json={"guardian_id": "template-author", "session_id": src.id, "label": "킨텍스 v1"})
    assert r.status_code == 200
    meta = r.json()
    assert meta["name"] == "김영숙" and meta["age"] == 76 and meta["label"] == "킨텍스 v1"
    assert client.get("/phase0/demo/onboarding/template").json()["source_session_id"] == src.id

    r1 = client.post("/phase0/demo/onboarding/sessions", json={"guardian_id": GUARDIAN, "guardian_name": "체험자"})
    r2 = client.post("/phase0/demo/onboarding/sessions", json={"guardian_id": GUARDIAN})
    assert r1.status_code == 200 and r2.status_code == 200
    a, b = r1.json()["session"], r2.json()["session"]
    # 두 번째 '다음 체험 준비'가 첫 복제(미완료)를 치웠다
    assert a["id"] in r2.json()["reset"]["purged_interviews"]
    # 매번 새 세션 — id 가 다르고 원본과도 다르다
    assert a["id"] != b["id"] and a["id"] != src.id
    # 소유자·상태는 복제 시 새로 채운다
    assert a["guardian_id"] == GUARDIAN and a["guardian_name"] == "체험자"
    assert a["awaiting_confirmation"] is True and a["done"] is False and a["persona_id"] is None
    # 내용(대화·추출)은 템플릿 그대로
    assert a["messages"] == src.messages and a["filled_keys"] == src.filled_keys
    assert a["draft_fields"]["name"] == "김영숙"
    assert storage.interviews.get(b["id"]) is not None and storage.interviews.get(a["id"]) is None   # 최신 복제만 남는다
    # 원본 세션은 그대로 남아 있다(템플릿 저장은 복사일 뿐)
    assert storage.interviews.get(src.id).awaiting_confirmation is True


def test_cloned_session_confirms_through_existing_gate_and_registers_persona():
    src = _awaiting_session()
    client.post("/phase0/demo/onboarding/template", json={"guardian_id": "template-author", "session_id": src.id})
    cloned = client.post("/phase0/demo/onboarding/sessions", json={"guardian_id": GUARDIAN}).json()["session"]

    # 체험자의 유일한 입력 — 기존 확인 게이트 엔드포인트 그대로
    r = client.post(f"/phase0/interviews/{cloned['id']}/answers", json={"text": "네, 맞아요."})
    assert r.status_code == 200
    s = r.json()
    assert s["done"] is True and s["persona_id"]
    persona = storage.personas.get(s["persona_id"])
    assert persona is not None
    assert persona.name == "김영숙" and persona.age == 76
    assert persona.guardian_id == GUARDIAN            # 체험 계정이 소유자
    # 홈 화면 분기(persona status)도 이 계정 기준으로 잡힌다
    st = client.get(f"/phase0/personas/status?guardian_id={GUARDIAN}").json()
    assert st["persona_id"] == s["persona_id"]
    assert st["persona_status"] in ("partial", "complete")


def test_reset_purges_only_that_guardian():
    src = _awaiting_session()
    client.post("/phase0/demo/onboarding/template", json={"guardian_id": "template-author", "session_id": src.id})
    cloned = client.post("/phase0/demo/onboarding/sessions", json={"guardian_id": GUARDIAN}).json()["session"]
    done = client.post(f"/phase0/interviews/{cloned['id']}/answers", json={"text": "맞아요"}).json()
    pid = done["persona_id"]
    # 신고까지 넣어 '수색 중' 케이스를 연결해 둔다 — 리셋이 종결 후 파기해야 한다
    case = client.post("/phase1/reports", json={
        "missing_type": "dementia", "persona_id": pid,
        "lkp": {"lat": 37.6628, "lng": 126.7536}, "lkp_time": "2026-10-10T14:20:00"}).json()
    # 다른 계정의 페르소나는 남아야 한다
    other = client.post("/phase0/personas", json={
        "name": "박복자", "age": 81, "type": "dementia", "guardian_id": "someone-else",
        "home": {"lat": 37.60, "lng": 127.01}}).json()
    # 복제만 하고 답하지 않은 세션도 하나
    # '다음 체험 준비' 자체가 리셋이다 — 이전 체험(페르소나·수색 중 사건)을 정리하고 새 세션을 준다
    r = client.post("/phase0/demo/onboarding/sessions", json={"guardian_id": GUARDIAN})
    assert r.status_code == 200
    body, fresh = r.json()["reset"], r.json()["session"]
    assert pid in body["purged_personas"] and case["id"] in body["closed_cases"]
    assert fresh["awaiting_confirmation"] is True and storage.interviews.get(fresh["id"]) is not None
    # 복제만 하고 답하지 않은 세션은 다음 리셋(복제 없는 reset)에 치워진다
    dangling = fresh
    r = client.post("/phase0/demo/onboarding/reset", json={"guardian_id": GUARDIAN})
    assert r.status_code == 200
    assert dangling["id"] in r.json()["purged_interviews"]
    assert storage.personas.get(pid) is None
    assert storage.cases.get(case["id"]) is None
    assert storage.interviews.get(cloned["id"]) is None      # 완료 세션은 persona 파기에 딸려 지워진다
    assert storage.interviews.get(dangling["id"]) is None
    assert storage.personas.get(other["id"]) is not None     # 남의 것은 그대로
    assert storage.interviews.get(src.id) is not None        # 템플릿 원본(다른 계정)도 그대로


def test_capture_without_session_id_picks_newest_awaiting_of_that_guardian():
    """부스 설치날: 폰에서 온보딩을 요약까지 진행하고 버튼만 누른다 — 세션 id 를 모른다."""
    old = _awaiting_session("old"); old.guardian_id = GUARDIAN; storage.interviews.save(old.id, old)
    new = _awaiting_session("new"); new.guardian_id = GUARDIAN
    new.draft_fields = dict(new.draft_fields, name="최신")
    storage.interviews.save(new.id, new)
    r = client.post("/phase0/demo/onboarding/template", json={"guardian_id": GUARDIAN, "label": "현장"})
    assert r.status_code == 200 and r.json()["name"] == "최신" and r.json()["source_session_id"] == "new"
    # 확인 대기 세션이 하나도 없으면 409
    for sid in ("old", "new"):
        storage.interviews.delete(sid)
    assert client.post("/phase0/demo/onboarding/template", json={"guardian_id": GUARDIAN}).status_code == 409


def test_booth_account_list_gates_every_endpoint(monkeypatch):
    monkeypatch.setenv("DEMO_GUARDIAN_IDS", "booth-a, booth-b")
    src = _awaiting_session(); src.guardian_id = "booth-a"; storage.interviews.save(src.id, src)
    assert client.post("/phase0/demo/onboarding/template", json={"guardian_id": "booth-a", "session_id": src.id}).status_code == 200
    assert client.post("/phase0/demo/onboarding/template", json={"guardian_id": "stranger", "session_id": src.id}).status_code == 404
    assert client.post("/phase0/demo/onboarding/sessions", json={"guardian_id": "stranger"}).status_code == 404
    assert client.post("/phase0/demo/onboarding/reset", json={"guardian_id": "stranger"}).status_code == 404
    assert client.get("/phase0/demo/onboarding/template?guardian_id=stranger").status_code == 404
    assert client.post("/phase0/demo/onboarding/sessions", json={"guardian_id": "booth-b"}).status_code == 200


def test_clone_stamps_fresh_last_active_at():
    """템플릿 시각을 물려받으면 개인정보 TTL 이 바로 만료되고 대시보드 '최근 활동' 판정이 어긋난다."""
    from datetime import datetime, timedelta
    src = _awaiting_session(); src.last_active_at = datetime.now() - timedelta(days=30); storage.interviews.save(src.id, src)
    client.post("/phase0/demo/onboarding/template", json={"guardian_id": "template-author", "session_id": src.id})
    fresh = client.post("/phase0/demo/onboarding/sessions", json={"guardian_id": GUARDIAN}).json()["session"]
    assert datetime.fromisoformat(fresh["last_active_at"]) > datetime.now() - timedelta(minutes=1)


@pytest.mark.parametrize("invalid_fields", [
    {"persona_type": "unsupported-type"},
    {"awaiting_confirmation": False},
])
def test_invalid_template_does_not_reset_existing_records(monkeypatch, invalid_fields):
    src = _awaiting_session()
    assert client.post("/phase0/demo/onboarding/template", json={
        "guardian_id": "template-author", "session_id": src.id}).status_code == 200
    existing = _awaiting_session("keep-existing")
    existing.guardian_id = GUARDIAN
    storage.interviews.save(existing.id, existing)
    path = demo_onboarding.template_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    data["session"].update(invalid_fields)
    path.write_text(json.dumps(data), encoding="utf-8")
    reset = Mock(wraps=demo_onboarding._reset)
    monkeypatch.setattr(demo_onboarding, "_reset", reset)

    response = client.post("/phase0/demo/onboarding/sessions", json={"guardian_id": GUARDIAN})

    assert response.status_code == 500
    reset.assert_not_called()
    assert storage.interviews.get(existing.id).model_dump() == existing.model_dump()


def test_next_turn_saves_the_snapshot_validated_before_reset(monkeypatch):
    guardian = "snapshot-guardian-test"
    src = _awaiting_session()
    assert client.post("/phase0/demo/onboarding/template", json={
        "guardian_id": "template-author", "session_id": src.id}).status_code == 200
    real_reset = demo_onboarding._reset

    def reset_then_replace_template(guardian_id):
        # The clone must not be saved before reset, which would delete it again.
        assert not any(s.guardian_id == guardian_id for s in storage.interviews.list())
        result = real_reset(guardian_id)
        # Simulate a template replacement after validation but before saving the session.
        demo_onboarding.template_path().write_text(
            json.dumps({"session": {"awaiting_confirmation": False}}), encoding="utf-8")
        return result

    monkeypatch.setattr(demo_onboarding, "_reset", reset_then_replace_template)
    response = client.post("/phase0/demo/onboarding/sessions", json={"guardian_id": guardian})

    assert response.status_code == 200
    session = response.json()["session"]
    assert session["awaiting_confirmation"] is True
    assert session["messages"] == src.messages
    assert session["draft_fields"] == src.draft_fields
    assert storage.interviews.get(session["id"]).model_dump(mode="json") == session


# ── 미리 계산한 준비 결과 재사용 (10-31) ─────────────────────────────────────

TURNS = [
    {"slot": "identity", "question": "성함과 연세를 알려주세요.", "answer": "김영숙, 76세예요.", "recorded_at": "2026-10-31T13:15:00"},
    {"slot": "lost_behavior", "question": "길을 잃으시면 보통 어떻게 하시나요?", "answer": "그 자리에 가만히 서계시는 편이에요.", "recorded_at": "2026-10-31T13:19:00"},
]


def _template_with_turns() -> InterviewSession:
    src = _awaiting_session()
    src.slot_turns = [dict(t) for t in TURNS]
    storage.interviews.save(src.id, src)
    assert client.post("/phase0/demo/onboarding/template", json={
        "guardian_id": "template-author", "session_id": src.id}).status_code == 200
    return src


def _register_clone() -> str:
    cloned = client.post("/phase0/demo/onboarding/sessions", json={"guardian_id": GUARDIAN}).json()["session"]
    return client.post(f"/phase0/interviews/{cloned['id']}/answers", json={"text": "맞아요"}).json()["persona_id"]


def _mark_prepared(pid: str):
    """K 준비가 끝난 인물처럼 — 실제 사용처와 같은 지문·리비전으로 결과를 채운다."""
    from app.llm import mind_policy
    from app.phase0 import person_preparation

    def done(p):
        fp = person_preparation.fingerprint(p)
        q = p.model_copy(deep=True, update={
            "prepared_initial": {"version": person_preparation.VERSION, "fingerprint": fp,
                                 "core": {"persistence": {"value": "wait_for_help", "note_ids": ["N1"]}},
                                 "scope": {}, "prepared_at": "2026-10-31T13:30:01"},
            "initial_preparation_status": {"state": "ready", "fingerprint": fp, "updated_at": "2026-10-31T13:30:01"},
        })
        rule = {"id": "lost-wait", "when": [[{"fact": "lost_awareness", "op": "eq", "value": True}]],
                "action": "wait", "goal_label": None, "feature": None, "place_labels": [], "hold_minutes": None,
                "supersedes": [], "evidence": [{"note_id": "N1", "quote": "그 자리에 가만히 서계시는 편이에요."}]}
        return q.model_copy(deep=True, update={
            "prepared_mind": {"revision": mind_policy.revision(q), "policy": {"rules": [rule], "unrepresented": []}},
            "mind_preparation_status": {"state": "ready", "updated_at": "2026-10-31T13:31:36"},
        })

    return storage.personas.update_existing(pid, done)


def test_prepared_result_is_reused_by_the_next_visitor_without_new_preparation(monkeypatch):
    from app.llm import mind_policy
    from app.phase0 import person_preparation

    _template_with_turns()
    first = _mark_prepared(_register_clone())
    r = client.post("/phase0/demo/onboarding/template/prepared", json={"guardian_id": GUARDIAN})
    assert r.status_code == 200
    assert r.json()["prepared"] == {"exists": True, "captured_at": r.json()["prepared"]["captured_at"],
                                    "source_persona_id": first.id, "prepared_at": "2026-10-31T13:31:36", "n_rules": 1}
    # 다음 체험자 — 이전 가족은 리셋으로 파기되지만 템플릿에 붙인 결과는 남는다
    dispatched = []
    monkeypatch.setattr(person_preparation, "_dispatch", lambda *a, **k: dispatched.append(a))
    pid = _register_clone()
    assert storage.personas.get(first.id) is None
    p = storage.personas.get(pid)
    assert dispatched == []                                   # K 준비를 다시 걸지 않았다
    assert p.id == pid and p.id != first.id and p.guardian_id == GUARDIAN and p.created_at > first.created_at
    assert p.prepared_initial == first.prepared_initial and p.prepared_mind == first.prepared_mind
    assert p.initial_preparation_status["state"] == "ready" and p.mind_preparation_status["state"] == "ready"
    assert p.initial_preparation_status["reused_from_template"] is True
    assert p.initial_preparation_status["source_prepared_at"] == "2026-10-31T13:30:01"
    assert p.mind_preparation_status["source_prepared_at"] == "2026-10-31T13:31:36"
    # 실제 사용처(예측의 개인 해석·보행 규칙)가 이 결과를 유효하다고 본다
    assert p.prepared_initial["fingerprint"] == person_preparation.fingerprint(p)
    assert p.prepared_mind["revision"] == mind_policy.revision(p)


def test_corrected_registration_is_prepared_normally_not_reused():
    _template_with_turns()
    _mark_prepared(_register_clone())
    assert client.post("/phase0/demo/onboarding/template/prepared", json={"guardian_id": GUARDIAN}).status_code == 200
    # 체험자가 확인 단계에서 답을 정정한 경우 — 등록 내용이 다르면 미리 계산한 결과를 쓰지 않는다
    cloned = client.post("/phase0/demo/onboarding/sessions", json={"guardian_id": GUARDIAN}).json()["session"]
    s = storage.interviews.get(cloned["id"])
    s.slot_turns = [dict(TURNS[0]), dict(TURNS[1], answer="계속 앞으로 걸어가세요.")]
    storage.interviews.save(s.id, s)
    pid = client.post(f"/phase0/interviews/{s.id}/answers", json={"text": "맞아요"}).json()["persona_id"]
    p = storage.personas.get(pid)
    assert "reused_from_template" not in p.initial_preparation_status
    assert p.prepared_initial == {} and p.prepared_mind == {}


def test_reuse_needs_the_booth_router_and_a_listed_account(monkeypatch):
    _template_with_turns()
    _mark_prepared(_register_clone())
    assert client.post("/phase0/demo/onboarding/template/prepared", json={"guardian_id": GUARDIAN}).status_code == 200
    monkeypatch.setenv("DEMO_ONBOARDING", "false")
    pid = _register_clone()
    assert "reused_from_template" not in storage.personas.get(pid).initial_preparation_status
    # 같은 인물로 계정 목록만 바꿔 본다 — 목록 밖 계정은 재사용하지 않는다
    storage.personas.update_existing(pid, lambda p: p.model_copy(update={"initial_preparation_status": {}}))
    monkeypatch.setenv("DEMO_GUARDIAN_IDS", "someone-else")
    assert demo_onboarding.reuse_prepared(pid) is False
    monkeypatch.setenv("DEMO_GUARDIAN_IDS", GUARDIAN)
    assert demo_onboarding.reuse_prepared(pid) is True
    assert storage.personas.get(pid).initial_preparation_status["reused_from_template"] is True


def test_confirmation_after_a_correction_is_prepared_normally():
    _template_with_turns()
    _mark_prepared(_register_clone())
    assert client.post("/phase0/demo/onboarding/template/prepared", json={"guardian_id": GUARDIAN}).status_code == 200
    cloned = client.post("/phase0/demo/onboarding/sessions", json={"guardian_id": GUARDIAN}).json()["session"]
    s = storage.interviews.get(cloned["id"])
    # 확인 단계에서 한 번 정정을 거친 대화 — 확인 발화가 두 번이 된다
    s.slot_turns.append({"slot": "confirmation", "question": "등록 요약을 보고 확인·정정하는 단계",
                         "answer": "아니요, 고칠 게 있어요", "recorded_at": "2026-10-31T13:20:00+00:00"})
    storage.interviews.save(s.id, s)
    pid = client.post(f"/phase0/interviews/{s.id}/answers", json={"text": "맞아요"}).json()["persona_id"]
    assert "reused_from_template" not in storage.personas.get(pid).initial_preparation_status


def test_capture_prepared_rejects_unready_foreign_or_missing():
    assert client.post("/phase0/demo/onboarding/template/prepared", json={"guardian_id": GUARDIAN}).status_code == 404
    _template_with_turns()
    assert client.post("/phase0/demo/onboarding/template/prepared", json={"guardian_id": GUARDIAN}).status_code == 409
    pid = _register_clone()
    # 준비가 끝나지 않은 가족은 저장하지 않는다
    r = client.post("/phase0/demo/onboarding/template/prepared", json={"guardian_id": GUARDIAN, "persona_id": pid})
    assert r.status_code == 409 and "끝나지 않았습니다" in r.json()["detail"]
    # 다른 대화로 등록한 가족도 저장하지 않는다
    _mark_prepared(pid)
    p = storage.personas.get(pid)
    storage.personas.save(pid, p.model_copy(update={"onboarding_turns": [dict(TURNS[0])]}))
    r = client.post("/phase0/demo/onboarding/template/prepared", json={"guardian_id": GUARDIAN, "persona_id": pid})
    assert r.status_code == 409 and "템플릿 대화" in r.json()["detail"]
    # 남의 가족 id
    assert client.post("/phase0/demo/onboarding/template/prepared", json={
        "guardian_id": "someone-else", "persona_id": pid}).status_code == 404
    assert client.get("/phase0/demo/onboarding/template").json()["prepared"] == {"exists": False}


def test_saving_a_new_conversation_drops_the_prepared_result():
    _template_with_turns()
    _mark_prepared(_register_clone())
    assert client.post("/phase0/demo/onboarding/template/prepared", json={"guardian_id": GUARDIAN}).json()["prepared"]["exists"]
    _template_with_turns()   # 대화를 템플릿으로 다시 저장
    assert client.get("/phase0/demo/onboarding/template").json()["prepared"] == {"exists": False}

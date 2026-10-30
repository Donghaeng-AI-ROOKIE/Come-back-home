"""시연 온보딩 템플릿 — 저장·복제·확인 게이트 통과·리셋.

템플릿은 임시 경로(DEMO_ONBOARDING_TEMPLATE)에 쓴다. Mi:dm 은 conftest 가 스텁으로
고정하므로 "맞아요" 판정은 결정론적으로 confirm 이다.
"""

import pytest
from fastapi.testclient import TestClient

from app import storage
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

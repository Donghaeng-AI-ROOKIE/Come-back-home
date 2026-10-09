"""Guardian edits preserve unrelated original evidence and their own collection time."""

from datetime import datetime, timezone
import copy

import pytest

from app import storage
from app.api import phase0
from app.llm import initial_behavior
from app.phase0 import person_preparation as prep, persona_events
from tests.test_person_evidence_projection import sample as source_sample


@pytest.fixture
def sample():
    return source_sample.__wrapped__()


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    storage.reset_for_tests()
    monkeypatch.setattr(prep, "_dispatch", lambda *args: None)
    monkeypatch.setattr(persona_events, "notify_persona_updated", lambda *args: None)
    yield
    storage.reset_for_tests()


def test_identity_save_from_old_client_keeps_full_original(sample):
    p = sample[0]
    p.behavior_notes = ["산책 가능"]
    p.onboarding_turns = [
        {
            "slot": "capacity",
            "question": "얼마나 걸으세요?",
            "answer": "45분 걸으시지만 계단은 피하세요.",
        }
    ]
    storage.personas.save(p.id, p)
    original = initial_behavior.evidence_notes(
        initial_behavior.build_payload(p, None, [], None)
    )
    updated = phase0.update_persona(
        p.id,
        phase0.UpdatePersonaIn(
            name="수정 이름",
            age=p.age,
            behavior_notes=p.behavior_notes,
            attraction_points=p.attraction_points,
        ),
    )
    assert updated.guardian_edited_notes is None
    assert updated.guardian_note_revisions == []
    assert (
        initial_behavior.evidence_notes(
            initial_behavior.build_payload(updated, None, [], None)
        )
        == original
    )


def test_same_values_do_not_queue_or_increment_version(sample, monkeypatch):
    p = sample[0]
    storage.personas.save(p.id, p)
    monkeypatch.setattr(
        prep,
        "enqueue",
        lambda *a: pytest.fail("unchanged input must not invoke models"),
    )
    updated = phase0.update_persona(
        p.id, phase0.UpdatePersonaIn(name=p.name, behavior_notes=p.behavior_notes)
    )
    assert updated.version == p.version


def test_edit_and_delete_preserve_unrelated_facts_and_record_only_changes(sample):
    p = sample[0]
    p.behavior_notes = ["길을 잃으면 기다림", "45분 보행"]
    storage.personas.save(p.id, p)
    updated = phase0.update_persona(
        p.id,
        phase0.UpdatePersonaIn(behavior_notes=["길을 잃으면 계속 걸음", "45분 보행"]),
    )
    rev = updated.guardian_note_revisions[-1]
    assert rev["before"] == ["길을 잃으면 기다림"]
    assert rev["after"] == ["길을 잃으면 계속 걸음"]
    assert datetime.fromisoformat(rev["recorded_at"]).tzinfo is not None
    notes = initial_behavior.evidence_notes(
        initial_behavior.build_payload(updated, None, [], None)
    )
    assert any("45분 산책" in n["text"] for n in notes)
    assert any("계속 걸음" in n["text"] for n in notes)
    updated = phase0.update_persona(
        p.id, phase0.UpdatePersonaIn(behavior_notes=["45분 보행"])
    )
    assert updated.guardian_note_revisions[-1]["after"] == []
    assert updated.guardian_note_revisions[-1]["before"] == ["길을 잃으면 계속 걸음"]


def test_supplement_question_answer_survives_after_edit(sample):
    p = sample[0]
    storage.personas.save(p.id, p)
    p = phase0.update_persona(
        p.id, phase0.UpdatePersonaIn(behavior_notes=["정정: 계속 걷는다"])
    )
    p.onboarding_turns.append(
        {
            "slot": "capacity",
            "question": "밤에도 같은가요?",
            "answer": "아니요. 밤에는 기다려요.",
            "recorded_at": "2026-09-26T04:00:00+00:00",
        }
    )
    notes = initial_behavior.evidence_notes(
        initial_behavior.build_payload(p, None, [], None)
    )
    assert any(
        "밤에도 같은가요?" in n["text"] and "밤에는 기다려요" in n["text"]
        for n in notes
    )
    assert any("정정: 계속 걷는다" in n["text"] for n in notes)


@pytest.mark.parametrize("fresh_kind", ["revision", "interview"])
def test_current_incident_evidence_in_old_profile_survives(sample, fresh_kind):
    p, r, sar, default, _, core, scope = sample
    p.created_at = datetime(2026, 1, 1)
    r = r.model_copy(update={"lkp_time": datetime(2026, 9, 26, 10)})
    stamp = datetime(2026, 9, 26, 11).astimezone(timezone.utc).isoformat()
    if fresh_kind == "revision":
        p.guardian_note_revisions = [
            {"before": [], "after": ["오늘 공원에 간다고 하셨다"], "recorded_at": stamp}
        ]
    else:
        p.onboarding_turns = [
            {
                "slot": "destination",
                "question": "오늘은요?",
                "answer": "오늘 공원에 간다고 하셨다",
                "recorded_at": stamp,
            }
        ]
    payload = initial_behavior.build_payload(p, None, [], None)
    fresh = next(n["id"] for n in payload["notes"] if "오늘 공원" in n["text"])
    core = copy.deepcopy(core)
    core["goals"]["공원"].update(value="current_statement", note_ids=[fresh])
    key = prep.fingerprint(p)
    p.initial_preparation_status = {"state": "ready", "fingerprint": key}
    p.prepared_initial = {"fingerprint": key, "core": core, "scope": scope}
    out = prep.apply_prepared(p, r, sar, default)
    assert (
        out.initial_interpretation["semantic_contract"]["goals"]["공원"]["value"]
        == "current_statement"
    )
    # A fresh unrelated edit must never refresh an older destination statement.
    if fresh_kind == "revision":
        p.prepared_initial["core"]["goals"]["공원"]["note_ids"] = ["N2"]
        out = prep.apply_prepared(p, r, sar, default)
        assert (
            out.initial_interpretation["semantic_contract"]["goals"]["공원"]["value"]
            == "historical_only"
        )


def test_new_private_evidence_is_not_exposed(sample):
    from fastapi.testclient import TestClient
    from app.main import app

    p = sample[0]
    p.guardian_note_revisions = [
        {"before": ["old"], "after": ["new"], "recorded_at": "2026-01-01"}
    ]
    storage.personas.save(p.id, p)
    row = TestClient(app).get("/phase0/personas/" + p.id).json()
    assert "guardian_note_revisions" not in row

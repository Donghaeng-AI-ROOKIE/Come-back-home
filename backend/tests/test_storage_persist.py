"""저장소 영속화 — 재시작 생존 + **파기가 디스크까지 닿는지** 검증.

이 파일이 존재하는 이유는 두 번째다. 메모리 저장일 때는 프로세스가 죽으면
개인정보가 자동으로 사라져 "발견 즉시 파기"가 공짜로 성립했다. SQLite 로 옮기는
순간 그 공짜가 없어진다 — DELETE 후에도 페이지에 원본 바이트가 남기 때문에,
지웠다고 말하려면 **파일을 바이너리로 열어 이름이 안 나오는지** 확인해야 한다.

앱 화면이 "정보는 안전하게 보관되고, 발견 즉시 파기돼요"라고 약속하고 있다.
그 문구가 거짓이 되지 않게 하는 것이 여기 테스트의 일이다.

다른 테스트는 conftest 가 영속화를 끈다(디스크 상태 공유 = 순서 의존).
여기서는 tmp_path 로 격리한 DB 를 직접 켠다.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app import storage
from app.config import settings
from app.schemas.case import Case, CaseStatus, CloseReason
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, Persona, PersonaType
from app.schemas.report import Appearance, MissingReport

LKP = GeoPoint(lat=37.6061, lng=127.0106)
SECRET_NAME = "김파기검증"          # DB 파일에서 찾을 문자열
SECRET_PLACE = "정릉시장뒷골목"      # 끌림점 — 중첩 객체도 지워지는지
SECRET_APPEARANCE = "빨간목도리회색점퍼"   # 케이스에 들어가는 개인정보


@pytest.fixture
def persistent(tmp_path, monkeypatch):
    """격리된 SQLite 파일로 영속화를 켠다. 테스트마다 새 파일·새 커넥션."""
    db = tmp_path / "storage.db"
    monkeypatch.setattr(settings, "persist_storage", True)
    monkeypatch.setattr(settings, "storage_db_path", str(db))
    storage.reset_for_tests()
    yield db
    storage.reset_for_tests()
    monkeypatch.setattr(settings, "persist_storage", False)


def _persona(pid: str = "persist-1") -> Persona:
    return Persona(
        id=pid, type=PersonaType.dementia, name=SECRET_NAME, age=82, home=LKP,
        attraction_points=[
            AttractionPoint(label=SECRET_PLACE, location=LKP, weight=1.0,
                            place_type="market"),
        ])


def _case(cid: str, persona_id: str) -> Case:
    return Case(
        id=cid,
        report=MissingReport(id=f"r-{cid}", persona_id=persona_id,
                             missing_type=PersonaType.dementia, lkp=LKP,
                             lkp_time=datetime.now(timezone.utc),
                             appearance=Appearance(summary=SECRET_APPEARANCE)),
        lkp=LKP, lkp_time=datetime.now(timezone.utc),
    )


def _raw_bytes(db) -> bytes:
    """DB 파일 전체를 바이너리로 읽는다 — SQL 이 아니라 파일을 본다.

    SQL 로 SELECT 하면 '지워진 것처럼' 보인다. 실제로 페이지에 남았는지는
    파일을 직접 열어야만 알 수 있다.
    """
    return db.read_bytes() if db.exists() else b""


# ── 1. 재시작 생존 ────────────────────────────────────────────────
def test_persona_survives_restart(persistent):
    """서버가 재시작해도 사전등록이 남아야 한다 — 이 서비스의 전제."""
    storage.personas.save("persist-1", _persona())

    storage.reset_for_tests()          # 프로세스 재시작 시뮬레이션
    restored = storage.personas.get("persist-1")

    assert restored is not None, "재시작으로 사전등록이 사라지면 서비스가 성립하지 않는다"
    assert restored.name == SECRET_NAME
    assert restored.attraction_points[0].label == SECRET_PLACE
    assert restored.type == PersonaType.dementia   # enum 도 왕복돼야 한다


def test_case_survives_restart(persistent):
    storage.cases.save("c-1", _case("c-1", "persist-1"))
    storage.reset_for_tests()

    restored = storage.cases.get("c-1")
    assert restored is not None
    assert restored.report.persona_id == "persist-1"
    assert restored.lkp.lat == pytest.approx(LKP.lat)


def test_plain_value_repository_round_trips(persistent):
    """모델이 없는 저장소(제보 카운터 = int)도 복원돼야 한다."""
    storage.walk_tip_counts.save("demo-citizen", 3)
    storage.reset_for_tests()
    assert storage.walk_tip_counts.get("demo-citizen") == 3


def test_debug_traces_are_not_persisted(persistent):
    """워커 궤적·LLM 트레이스는 **일부러** 디스크에 남기지 않는다.

    시연 대시보드용 파생물이라 재시작 시 사라져도 되고, LLM 원문까지 디스크에
    쌓을 이유가 없다. 이 선택이 조용히 뒤집히지 않게 고정한다.
    """
    from app.schemas.debug import PredictionDebug

    storage.debug_traces.save("c-1", PredictionDebug(case_id="c-1"))
    storage.reset_for_tests()
    assert storage.debug_traces.get("c-1") is None


# ── 2. 파기가 디스크까지 닿는가 (핵심) ────────────────────────────
def test_persona_purge_erases_from_disk(persistent):
    """페르소나 파기 후 **DB 파일에 이름이 남아 있으면 안 된다.**

    SQL 조회로는 안 보이지만 파일에는 남는 경우가 이 테스트가 잡으려는 실패다.
    """
    from app.privacy import lifecycle

    storage.personas.save("persist-1", _persona())
    assert SECRET_NAME.encode() in _raw_bytes(persistent), "저장 자체가 안 됐다면 테스트가 무의미"

    lifecycle.purge_persona("persist-1", cause="test")

    raw = _raw_bytes(persistent)
    assert SECRET_NAME.encode() not in raw, "파기 후에도 DB 파일에 이름이 남아 있다"
    assert SECRET_PLACE.encode() not in raw, "중첩 객체(끌림점)가 파일에 남아 있다"
    assert storage.personas.get("persist-1") is None


def test_case_purge_erases_from_disk(persistent):
    from app.privacy import lifecycle

    persona = _persona("persist-2")
    storage.personas.save(persona.id, persona)
    case = _case("c-purge", persona.id)
    case.status = CaseStatus.closed
    case.close_reason = CloseReason.withdrawn
    case.closed_at = datetime.now()  # noqa: DTZ005 — Case.closed_at 은 naive(LocalNaiveDT)
    storage.cases.save(case.id, case)
    assert SECRET_APPEARANCE.encode() in _raw_bytes(persistent)

    lifecycle.purge_case(case, cause="test")

    raw = _raw_bytes(persistent)
    assert SECRET_APPEARANCE.encode() not in raw, "파기 후에도 인상착의가 파일에 남아 있다"
    # 케이스 ID 는 남는다 — 감사 증적(audit_logs.target_id)이 "무엇을 지웠는지"를
    # 기록하기 때문이고, 무작위 hex 라 개인정보가 아니다. 이게 지워지면 파기를
    # 증명할 수 없다(test_audit_record_survives_purge 참조).
    assert b"c-purge" in raw, "파기 증적이 사라지면 지웠다는 것을 증명할 수 없다"


def test_expired_purge_erases_from_disk(persistent):
    """TTL 일괄 파기도 디스크까지 회수해야 한다 (스케줄러 경로)."""
    from app.privacy import lifecycle

    case = _case("c-ttl", "persist-3")
    case.status = CaseStatus.found
    case.close_reason = CloseReason.found
    case.closed_at = (datetime.now()  # noqa: DTZ005 — 위와 같은 이유
                      - timedelta(days=settings.privacy_retention_days + 1))
    storage.cases.save(case.id, case)
    assert SECRET_APPEARANCE.encode() in _raw_bytes(persistent)

    purged = lifecycle.purge_expired()

    assert "c-ttl" in purged["cases"]
    assert SECRET_APPEARANCE.encode() not in _raw_bytes(persistent)


def test_audit_record_survives_purge(persistent):
    """파기 **증적**은 남아야 한다 — 개인정보가 없으므로 보존이 원칙과 모순되지 않는다.

    이게 지워지면 "언제 무엇을 지웠다"를 증명할 수 없다.
    """
    from app.privacy import lifecycle

    storage.personas.save("persist-4", _persona("persist-4"))
    lifecycle.purge_persona("persist-4", cause="test")

    actions = [r.action for r in lifecycle.get_audit_log()]
    assert "persona_purged" in actions
    # 증적에 개인정보가 섞이면 파기의 의미가 없다
    assert SECRET_NAME.encode() not in _raw_bytes(persistent)


# ── 3. 꺼져 있으면 아무것도 안 남는다 ─────────────────────────────
def test_disabled_writes_nothing(tmp_path, monkeypatch):
    """persist_storage=false 면 파일이 아예 생기지 않아야 한다 (테스트 기본 구성)."""
    db = tmp_path / "should_not_exist.db"
    monkeypatch.setattr(settings, "persist_storage", False)
    monkeypatch.setattr(settings, "storage_db_path", str(db))
    storage.reset_for_tests()

    storage.personas.save("persist-off", _persona("persist-off"))
    assert storage.personas.get("persist-off") is not None   # 메모리로는 동작
    assert not db.exists(), "영속화가 꺼졌는데 DB 파일이 생겼다"

    storage.reset_for_tests()

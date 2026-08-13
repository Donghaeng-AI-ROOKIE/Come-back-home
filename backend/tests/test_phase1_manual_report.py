from datetime import datetime

from app.phase1 import intake
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType
from app.schemas.report import Appearance


def test_manual_report_fields_are_persisted_without_photo():
    case = intake.create_report(
        missing_type=PersonaType.dementia,
        lkp=GeoPoint(lat=37.5511, lng=126.9410),
        lkp_time=datetime.now(),
        appearance=Appearance(top="회색 점퍼", bottom="검정 바지", etc="지팡이"),
        situation="산책 후 귀가하지 않음",
    )

    assert case.report.situation == "산책 후 귀가하지 않음"
    assert case.report.appearance is not None
    assert case.report.appearance.summary == "회색 점퍼, 검정 바지, 지팡이"

"""부스 시연 전용 — 온보딩 템플릿 복제와 턴 리셋 (결선).

## 왜 필요한가
부스 체험자가 12문항을 직접 답하면 체험 한 번에 10분이 간다. 그렇다고 신고만
시키면 "일상 정보가 수색 단서가 된다"는 핵심(01 페르소나 저장)이 빠진다. 그래서
**요약 확인("이렇게 등록할게요. 맞나요?") 직전 상태의 인터뷰 세션을 템플릿으로
저장해 두고, 체험자마다 새 세션으로 복제**한다. 체험자는 "맞아요"만 답하고,
그 뒤는 기존 확인 게이트(`interview._handle_confirmation` → `finalize_persona`)가
그대로 돈다 — 끌림점 좌표화·페르소나 저장이 실제로 일어나 대시보드에 보인다.

## 턴 리셋은 진행자가 한다
한 체험이 끝나면 진행자가 보호자 폰 "내 정보" 탭에서 **다음 체험 준비**를 누른다.
그 한 호출(`POST /sessions`)이 ① 수색 중 사건을 '신고 철회'로 종결하고 ② 페르소나와
완료·미완료 인터뷰를 정식 파기 경로(privacy.lifecycle)로 지운 뒤 ③ 템플릿을 새 세션으로
복제한다. 다음 체험자는 "맞아요"부터 시작하고, 대시보드는 아직 아무도 답하지 않은 복제
세션을 대기 화면으로 본다(피드의 awaiting_confirmation + 마지막 발화자).

## 경로가 /phase0/ 아래인 이유
공개 앱은 Supabase 큐(`cbh_submit`)를 거치는데 그 SQL 이 `^/(phase[0-3]|walk|geo)/`
만 통과시킨다. `/demo/...` 로 두면 SQL 함수를 다시 적용해야 하므로 `/phase0/demo/...`
로 둔다. worker 의 `cloud_bridge/policy.py` 가 이 경로를 **DEMO_GUARDIAN_IDS 에 적힌
계정만** 허용하고 소유자 id 를 로그인 계정으로 강제한다.

## 기존 코드를 건드리지 않는다
- 인터뷰 엔진·스키마·설정 파일은 수정하지 않는다. 이 모듈은 `InterviewSession` 을
  읽고 저장만 한다.
- `app.main` 은 환경변수 `DEMO_ONBOARDING=true` 일 때만 이 라우터를 얹는다(배포 compose).
  로컬에서는 `app.demo_main:app` 으로도 띄울 수 있다.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import storage
from app.privacy import lifecycle
from app.schemas.case import CaseStatus, CloseReason
from app.schemas.persona import InterviewSession

router = APIRouter(prefix="/phase0/demo/onboarding", tags=["Demo — 부스 온보딩 템플릿"])

# 템플릿 파일 위치. 환경변수로 바꿀 수 있다(배포는 /app/data/demo/..., 테스트는 임시 경로).
_DEFAULT_TEMPLATE = Path("data") / "demo" / "onboarding_template.json"

# 복제 시 **반드시 새로 채우는** 필드 — 템플릿의 값을 그대로 쓰면 안 되는 것들.
# id/소유자는 체험자마다 달라야 하고, 완료·연결 상태는 초기화돼야 확인 게이트가 돈다.
# last_active_at 은 복제 시각이어야 한다 — 템플릿 시각을 물려받으면 개인정보 TTL 이
# 바로 만료되고, 대시보드의 '가장 최근 활동' 판정도 어긋난다.
_RESET_ON_CLONE = {
    "id", "guardian_id", "guardian_name", "persona_id", "done",
    "skip_confirmation", "llm_call_failures", "last_active_at",
}

_ACTIVE = (CaseStatus.intake, CaseStatus.predicted, CaseStatus.searching)


def template_path() -> Path:
    return Path(os.environ.get("DEMO_ONBOARDING_TEMPLATE") or _DEFAULT_TEMPLATE)


def allowed_guardians() -> set[str]:
    """부스 계정 목록(쉼표 구분). 비어 있으면 제한 없음 — 로컬 시연용.

    공개 배포에서는 반드시 채운다. worker 의 policy 가 같은 목록으로 한 번 더 거른다.
    """
    raw = os.environ.get("DEMO_GUARDIAN_IDS", "")
    return {x.strip() for x in raw.split(",") if x.strip()}


def _require_booth(guardian_id: str) -> None:
    allowed = allowed_guardians()
    if allowed and guardian_id not in allowed:
        raise HTTPException(404, "부스 체험 계정이 아닙니다.")


class CaptureIn(BaseModel):
    guardian_id: str = Field(min_length=1)
    session_id: str | None = None   # 없으면 이 계정의 가장 최근 '확인 대기' 세션을 고른다
    label: str = ""                 # 메모 ("킨텍스 v1" 등)


class CloneIn(BaseModel):
    guardian_id: str = Field(min_length=1)   # 체험용 보호자 계정 — 페르소나 소유자가 된다
    guardian_name: str = "보호자"


class ResetIn(BaseModel):
    guardian_id: str = Field(min_length=1)


def _read_template() -> dict | None:
    p = template_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise HTTPException(500, f"템플릿을 읽지 못함: {type(e).__name__}") from e


def _meta(data: dict | None) -> dict:
    if data is None:
        return {"exists": False, "path": str(template_path())}
    s = data.get("session", {})
    f = s.get("draft_fields", {})
    return {
        "exists": True,
        "path": str(template_path()),
        "label": data.get("label", ""),
        "captured_at": data.get("captured_at"),
        "source_session_id": data.get("source_session_id"),
        "name": f.get("name"), "age": f.get("age"), "home": f.get("home"),
        "filled_keys": s.get("filled_keys", []),
        "n_attractions": len(s.get("draft_attractions", [])),
        "n_messages": len(s.get("messages", [])),
    }


@router.get("/template")
def get_template(guardian_id: str = ""):
    """저장된 템플릿의 요약 — 부스 준비 상태 점검용. 없으면 `exists: false` (404 아님:
    앱의 진행자 영역이 '템플릿 없음'을 표시해야 하므로)."""
    if guardian_id:
        _require_booth(guardian_id)
    return _meta(_read_template())


def _pick_awaiting(guardian_id: str) -> InterviewSession:
    cands = [s for s in storage.interviews.list()
             if s.guardian_id == guardian_id and not s.done and s.awaiting_confirmation]
    if not cands:
        raise HTTPException(409, "요약 확인 대기 중인 대화가 없습니다 — 온보딩을 '이렇게 등록할게요' 요약까지 진행한 뒤 저장하세요")
    return max(cands, key=lambda s: s.last_active_at)


@router.post("/template")
def capture_template(body: CaptureIn):
    """지금 **확인 대기 중**인 세션을 템플릿으로 저장한다.

    부스 설치날: 부스 계정으로 앱에서 온보딩을 진행해 "이렇게 등록할게요" 요약이 뜬
    시점에 "내 정보" 탭의 **지금 대화를 템플릿으로 저장**을 누른다. 세션 id 를 안 주면
    그 계정의 가장 최근 확인 대기 세션을 고른다. 세션은 그대로 두고(이어서 "맞아요"를
    답해 등록해도 된다) 내용만 파일로 복사한다.
    """
    _require_booth(body.guardian_id)
    if body.session_id:
        session = storage.interviews.get(body.session_id)
        if session is None or session.guardian_id != body.guardian_id:
            raise HTTPException(404, "인터뷰 세션 없음")
        if session.done:
            raise HTTPException(409, "이미 완료된 세션 — 확인 대기 상태의 세션만 템플릿이 된다")
        if not session.awaiting_confirmation:
            raise HTTPException(409, "아직 요약 확인 단계가 아님 — 질문을 끝까지 답한 뒤 저장하세요")
    else:
        session = _pick_awaiting(body.guardian_id)
    data = {
        "label": body.label[:80],
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "source_session_id": session.id,
        "session": session.model_dump(mode="json"),
    }
    p = template_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return _meta(data)


def _reset(guardian_id: str) -> dict:
    """이 보호자 계정의 사건·페르소나·인터뷰를 정식 파기 경로로 지운다(감사 증적 남음)."""
    personas = [p for p in storage.personas.list() if p.guardian_id == guardian_id]
    closed: list[str] = []
    for p in personas:
        for c in storage.cases.list():
            if c.report.persona_id == p.id and c.status in _ACTIVE:
                lifecycle.close_case(c, CloseReason.withdrawn)
                closed.append(c.id)
    purged_personas: list[str] = []
    for p in personas:
        lifecycle.purge_persona(p.id, cause=f"demo_reset:{guardian_id}")
        purged_personas.append(p.id)
    # 페르소나가 없는 미완료 세션(복제했지만 "맞아요"를 안 한 것, 또는 템플릿을 뜬 원본)도 치운다.
    purged_interviews: list[str] = []
    for s in storage.interviews.list():
        if s.guardian_id == guardian_id and not s.done:
            storage.interviews.delete(s.id)
            purged_interviews.append(s.id)
    return {"guardian_id": guardian_id, "closed_cases": closed,
            "purged_personas": purged_personas, "purged_interviews": purged_interviews}


def _clone(guardian_id: str, guardian_name: str) -> InterviewSession:
    data = _read_template()
    if data is None:
        raise HTTPException(404, f"온보딩 템플릿 없음 — 먼저 템플릿을 저장하세요 ({template_path()})")
    raw = dict(data.get("session", {}))
    for k in _RESET_ON_CLONE:
        raw.pop(k, None)
    try:
        session = InterviewSession(
            id=storage.new_id(), guardian_id=guardian_id, guardian_name=guardian_name,
            persona_id=None, done=False, skip_confirmation=False, llm_call_failures=0,
            **raw,
        )
    except Exception as e:  # noqa: BLE001 — 스키마가 바뀌어 템플릿이 안 맞으면 다시 저장해야 한다
        raise HTTPException(500, f"템플릿이 현재 세션 스키마와 맞지 않음 — 다시 저장하세요 ({type(e).__name__})") from e
    if not session.awaiting_confirmation:
        raise HTTPException(500, "템플릿이 확인 대기 상태가 아님 — 다시 저장하세요")
    storage.interviews.save(session.id, session)
    return session


class NextTurnOut(BaseModel):
    session: InterviewSession
    reset: dict


@router.post("/sessions", response_model=NextTurnOut)
def next_turn(body: CloneIn):
    """**다음 체험 준비** — 이 계정의 이전 체험을 정리하고 템플릿을 새 세션으로 복제한다.

    응답의 `session` 은 `InterviewSession` 전체(대화 전문 포함). 앱은 등록 채팅 화면을
    이 세션 id 로 열고, 체험자의 "맞아요"는 기존 `/phase0/interviews/{id}/answers` 로 간다.
    템플릿이 없으면 404 — 아무것도 지우지 않는다(리셋은 복제가 가능할 때만).
    """
    _require_booth(body.guardian_id)
    if _read_template() is None:
        raise HTTPException(404, f"온보딩 템플릿 없음 — 먼저 템플릿을 저장하세요 ({template_path()})")
    reset = _reset(body.guardian_id)
    session = _clone(body.guardian_id, body.guardian_name)
    return NextTurnOut(session=session, reset=reset)


@router.post("/reset")
def reset_guardian(body: ResetIn):
    """체험 정리만 — 복제 없이 이 보호자 계정의 페르소나·연결 케이스·인터뷰를 파기한다.

    정식 파기 경로(privacy.lifecycle)를 그대로 쓴다: 수색 중 케이스는 '신고 철회'로
    종결한 뒤 페르소나와 함께 파기하고, 감사 증적을 남긴다. 다른 계정은 건드리지 않는다.
    """
    _require_booth(body.guardian_id)
    return _reset(body.guardian_id)

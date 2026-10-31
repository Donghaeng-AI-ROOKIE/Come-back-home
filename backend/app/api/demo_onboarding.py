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

## 미리 계산한 준비 결과 재사용 (10-31)
"맞아요" 뒤 K-EXAONE 개인 해석·조건부 규칙 준비는 실측 약 5분 걸린다(10-31 부스 계정 실등록:
13:26:40 등록 → 13:31:36 규칙 완료). 체험자가 기다릴 수 없고, 그 전에 신고하면 예측은 규칙
없이 돈다. 그래서 진행자가 **같은 템플릿 대화로 등록해 준비가 끝난 인물**을 골라
`POST /template/prepared` 로 템플릿에 붙여 두면, 다음 체험자의 "맞아요"로 생긴 인물이
등록 내용(이름·나이·성별·집·장소·질문과 답)이 같을 때 그 인물의 내용과 준비 결과를 그대로
받는다(`reuse_prepared`, `person_preparation.enqueue` 가 부른다). K 호출 없이 바로 준비 완료가
되고, 보행 엔진도 실제로 그 규칙을 쓴다. 준비 상태에는 `reused_from_template` 과 원래 계산
시각(`source_prepared_at`)을 남겨 실시간 결과처럼 보이지 않게 한다. 등록 내용이 다르거나
(정정 대화 등) 지문이 맞지 않으면 아무것도 바꾸지 않고 평소처럼 새로 준비한다.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import storage
from app.privacy import lifecycle
from app.schemas.case import CaseStatus, CloseReason
from app.schemas.persona import InterviewSession, Persona

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

# 준비 결과를 재사용할 때 새 인물의 값을 지키는 필드 — 소유자·식별자·등록 시각.
# 나머지(질문과 답·추출 메모·장소·준비 결과)는 미리 계산한 인물의 것을 그대로 받아야
# 준비 지문(person_preparation.fingerprint)과 규칙 리비전(mind_policy.revision)이 맞는다.
_KEEP_ON_REUSE = ("id", "guardian_id", "created_at", "last_confirmed_at")


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


class CapturePreparedIn(BaseModel):
    guardian_id: str = Field(min_length=1)
    persona_id: str | None = None   # 없으면 이 계정의 가장 최근 인물을 고른다


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
        "prepared": _prepared_meta(data),
    }


def _prepared_meta(data: dict) -> dict:
    prepared = data.get("prepared_persona")
    if not prepared:
        return {"exists": False}
    policy = (prepared.get("prepared_mind") or {}).get("policy") or {}
    return {
        "exists": True,
        "captured_at": data.get("prepared_captured_at"),
        "source_persona_id": prepared.get("id"),
        "prepared_at": (prepared.get("mind_preparation_status") or {}).get("updated_at"),
        "n_rules": len(policy.get("rules") or []),
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


def _prepare_clone(guardian_id: str, guardian_name: str) -> InterviewSession:
    """템플릿을 한 번 읽고 검증한다. 기존 자료를 지우기 전에는 저장하지 않는다."""
    data = _read_template()
    if data is None:
        raise HTTPException(404, f"온보딩 템플릿 없음 — 먼저 템플릿을 저장하세요 ({template_path()})")
    try:
        raw = dict(data.get("session", {}))
        for k in _RESET_ON_CLONE:
            raw.pop(k, None)
        session = InterviewSession(
            id=storage.new_id(), guardian_id=guardian_id, guardian_name=guardian_name,
            persona_id=None, done=False, skip_confirmation=False, llm_call_failures=0,
            **raw,
        )
    except Exception as e:  # noqa: BLE001 — 스키마가 바뀌어 템플릿이 안 맞으면 다시 저장해야 한다
        raise HTTPException(500, f"템플릿이 현재 세션 스키마와 맞지 않음 — 다시 저장하세요 ({type(e).__name__})") from e
    if not session.awaiting_confirmation:
        raise HTTPException(500, "템플릿이 확인 대기 상태가 아님 — 다시 저장하세요")
    return session


class NextTurnOut(BaseModel):
    session: InterviewSession
    reset: dict


@router.post("/sessions", response_model=NextTurnOut)
def next_turn(body: CloneIn):
    """**다음 체험 준비** — 이 계정의 이전 체험을 정리하고 템플릿을 새 세션으로 복제한다.

    응답의 `session` 은 `InterviewSession` 전체(대화 전문 포함). 앱은 등록 채팅 화면을
    이 세션 id 로 열고, 체험자의 "맞아요"는 기존 `/phase0/interviews/{id}/answers` 로 간다.
    템플릿이 없거나 현재 스키마·확인 대기 조건을 충족하지 않으면 아무것도 지우지 않는다.
    """
    _require_booth(body.guardian_id)
    session = _prepare_clone(body.guardian_id, body.guardian_name)
    reset = _reset(body.guardian_id)
    # 리셋 사이 템플릿이 바뀌어도 다시 읽지 않고 검증한 객체를 그대로 저장한다.
    storage.interviews.save(session.id, session)
    return NextTurnOut(session=session, reset=reset)


@router.post("/reset")
def reset_guardian(body: ResetIn):
    """체험 정리만 — 복제 없이 이 보호자 계정의 페르소나·연결 케이스·인터뷰를 파기한다.

    정식 파기 경로(privacy.lifecycle)를 그대로 쓴다: 수색 중 케이스는 '신고 철회'로
    종결한 뒤 페르소나와 함께 파기하고, 감사 증적을 남긴다. 다른 계정은 건드리지 않는다.
    """
    _require_booth(body.guardian_id)
    return _reset(body.guardian_id)


def _turns(turns: list[dict]) -> list[tuple]:
    """템플릿 대화의 질문과 답. 확인 단계 발화(slot=confirmation)는 체험자마다 다르므로 뺀다.

    finalize_persona 가 세션의 slot_turns 를 중복 없이 옮기므로 양쪽 다 같은 기준으로 접는다.
    """
    out: list[tuple] = []
    for t in turns:
        key = (t.get("slot"), t.get("question"), t.get("answer"))
        if t.get("slot") != "confirmation" and key not in out:
            out.append(key)
    return out


def _registration(p: Persona) -> tuple:
    """같은 등록인지 가르는 값 — 보호자가 답한 내용과 그로 정해진 신원·장소.

    확인 단계 발화는 개수만 본다: "맞아요" 한 번이면 1, 정정을 거쳤으면 2 이상이라 다른 등록이
    된다(그때는 평소처럼 새로 준비한다). 추출 메모(behavior_notes 등)는 "맞아요" 때 Mi:dm 이 다시
    뽑아 회차마다 흔들리므로 비교하지 않는다. 그 흔들림이 준비 지문을 바꾸는 것이 재사용이
    필요한 이유다.
    """
    confirmations = sum(1 for t in p.onboarding_turns if t.get("slot") == "confirmation")
    return (p.type, p.name, p.age, p.sex, round(p.home.lat, 6), round(p.home.lng, 6),
            sorted(a.label for a in p.attraction_points), _turns(p.onboarding_turns), confirmations)


def _prepared_problem(p: Persona) -> str | None:
    """준비 결과가 이 인물 내용과 맞는지 — 실제 사용처와 같은 지문·리비전으로 본다."""
    from app.llm import mind_policy
    from app.phase0 import person_preparation
    if (p.initial_preparation_status.get("state") != "ready"
            or p.prepared_initial.get("fingerprint") != person_preparation.fingerprint(p)):
        return "개인 특성 해석이 아직 끝나지 않았습니다"
    if (p.mind_preparation_status.get("state") != "ready"
            or p.prepared_mind.get("revision") != mind_policy.revision(p)):
        return "조건부 규칙 준비가 아직 끝나지 않았습니다"
    return None


@router.post("/template/prepared")
def capture_prepared(body: CapturePreparedIn):
    """이 계정에서 템플릿 대화로 등록해 **준비가 끝난 인물**을 템플릿에 붙인다.

    진행자는 대시보드에서 개인 해석·조건부 규칙이 잘 나온 회차를 확인한 뒤 "내 정보" 탭의
    **지금 준비 결과를 템플릿에 저장**을 누른다. 그 뒤 체험자의 "맞아요"는 이 결과를 그대로
    받는다(`reuse_prepared`). 대화를 템플릿으로 다시 저장하면(`POST /template`) 이 결과는
    함께 사라진다 — 다른 대화로 계산한 결과를 붙이지 않기 위해서다.
    """
    _require_booth(body.guardian_id)
    data = _read_template()
    if data is None:
        raise HTTPException(404, "온보딩 템플릿 없음 — 먼저 대화를 템플릿으로 저장하세요")
    if body.persona_id:
        persona = storage.personas.get(body.persona_id)
        if persona is None or persona.guardian_id != body.guardian_id:
            raise HTTPException(404, "등록된 가족 없음")
    else:
        mine = [p for p in storage.personas.list() if p.guardian_id == body.guardian_id]
        if not mine:
            raise HTTPException(409, "등록된 가족이 없습니다 — 템플릿 대화에서 \"맞아요\"로 등록한 뒤 저장하세요")
        persona = max(mine, key=lambda p: p.created_at)
    if _turns(persona.onboarding_turns) != _turns(data.get("session", {}).get("slot_turns", [])):
        raise HTTPException(409, "이 가족은 지금 템플릿 대화로 등록한 것이 아닙니다 — 다음 체험 준비 후 \"맞아요\"로 등록하세요")
    problem = _prepared_problem(persona)
    if problem:
        raise HTTPException(409, f"{problem} — 대시보드에서 준비 완료를 확인한 뒤 다시 저장하세요")
    data.update(prepared_persona=persona.model_dump(mode="json"),
                prepared_captured_at=datetime.now().isoformat(timespec="seconds"))  # noqa: DTZ005 — captured_at 과 같은 서버 지역 시각
    template_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return _meta(data)


def reuse_prepared(persona_id: str) -> bool:
    """체험자의 "맞아요"로 막 생긴 인물에 템플릿의 미리 계산한 준비 결과를 붙인다.

    `person_preparation.enqueue` 가 K 준비를 걸기 전에 부른다. 붙였으면 True. 템플릿에 결과가
    없거나, 등록 내용이 다르거나, 붙인 뒤 지문·리비전이 맞지 않거나, 어떤 오류든 False 를
    돌려주고 인물은 그대로 둔다 — 그러면 평소처럼 K 준비가 돈다.
    """
    try:
        current = storage.personas.get(persona_id)
        if current is None or current.initial_preparation_status:
            return False
        allowed = allowed_guardians()
        if allowed and current.guardian_id not in allowed:
            return False
        raw = (_read_template() or {}).get("prepared_persona")
        if not raw:
            return False
        source = Persona.model_validate(raw)
        if _registration(source) != _registration(current):
            return False
        now = datetime.now().isoformat()  # noqa: DTZ005 — 준비 상태 updated_at 은 person_preparation 처럼 서버 지역 시각

        def reused(status: dict) -> dict:
            return dict(status, reused_from_template=True,
                        source_prepared_at=status.get("updated_at"), updated_at=now)

        candidate = source.model_copy(deep=True, update={
            **{k: getattr(current, k) for k in _KEEP_ON_REUSE},
            "initial_preparation_status": reused(source.initial_preparation_status),
            "mind_preparation_status": reused(source.mind_preparation_status),
        })
        if _prepared_problem(candidate):
            return False
        saved = storage.personas.update_existing(
            persona_id, lambda cur: candidate if not cur.initial_preparation_status else None)
        return saved is not None
    except Exception as exc:  # noqa: BLE001 — 재사용 실패가 등록을 막으면 안 된다
        logging.getLogger(__name__).error("Booth preparation reuse skipped: %s", type(exc).__name__)
        return False

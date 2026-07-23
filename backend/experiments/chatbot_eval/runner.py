"""러너 — TestClient 로 인터뷰 세션을 끝까지 굴려 Transcript 를 모은다.

e2e_smoke.py 와 같은 인프로세스 방식(서버 불필요). API 계약(app/api/phase0.py):
  POST /phase0/interviews            → 세션(첫 질문 = messages[-1])
  POST /phase0/interviews/{id}/answers {text} → 세션(다음 질문 = messages[-1])
  GET  /phase0/personas/{persona_id} → 종료 페르소나

종료 감지: 응답의 done=True → persona_id 로 페르소나 조회.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .responder import is_summary_gate, respond


@dataclass
class Transcript:
    scenario_id: str
    turns: list[dict] = field(default_factory=list)     # [{"q":.., "a":..}]
    assistant_questions: list[str] = field(default_factory=list)
    persona: dict | None = None
    session: dict | None = None
    # 좌표화 '이전' 수집 장소 — persona.attraction_points 와 비교해 지오코딩 탈락 구분
    draft_attractions: list[dict] = field(default_factory=list)
    done: bool = False
    llm_degraded: bool = False
    llm_call_failures: int = 0
    stopped_reason: str = ""


def _last_assistant(session: dict) -> str | None:
    for m in reversed(session.get("messages", [])):
        if m.get("role") == "assistant":
            return m.get("text")
    return None


def run_scenario(scenario, client, *, max_turns: int = 40, verbose: bool = False) -> Transcript:
    tr = Transcript(scenario_id=scenario.id)

    start = client.post("/phase0/interviews", json={
        "guardian_name": scenario.guardian_name,
        "persona_type": None,   # 유형 미지정 — identity 답변의 키워드로 감지시켜 그 경로도 검증
    })
    if start.status_code >= 300:
        tr.stopped_reason = f"start {start.status_code}: {start.text[:200]}"
        return tr
    session = start.json()
    sid = session["id"]

    # 확인 게이트 멀티턴 시퀀스 — 정정들 뒤에 긍정. 요약이 다시 뜰 때마다 다음 항목.
    confirm_seq = list(scenario.corrections) + [scenario.affirm]
    confirm_idx = 0

    for _ in range(max_turns):
        if session.get("done"):
            tr.done = True
            tr.stopped_reason = "done"
            break
        q = _last_assistant(session)
        if q is None:
            tr.stopped_reason = "챗봇 질문 없음"
            break
        # 요약 확인 게이트는 러너가 시퀀스로 처리(리스폰더는 무상태) — 정정→재요약→…→긍정
        if is_summary_gate(q):
            a = confirm_seq[min(confirm_idx, len(confirm_seq) - 1)]
            confirm_idx += 1
        else:
            a = respond(q, scenario)
        tr.assistant_questions.append(q)
        tr.turns.append({"q": q, "a": a})
        if verbose:
            print(f"\n  🤖 {q}")
            print(f"  🧑 {a}")

        resp = client.post(f"/phase0/interviews/{sid}/answers", json={"text": a})
        if resp.status_code >= 300:
            tr.stopped_reason = f"answer {resp.status_code}: {resp.text[:200]}"
            break
        session = resp.json()
    else:
        tr.stopped_reason = f"max_turns({max_turns}) 도달"

    # 최종 세션을 다시 읽어 draft_attractions(수집분)를 확정 — 지오코딩 탈락 구분용.
    fresh = client.get(f"/phase0/interviews/{sid}")
    if fresh.status_code < 300:
        session = fresh.json()
    tr.session = session
    tr.done = bool(session.get("done"))
    tr.llm_degraded = bool(session.get("llm_degraded"))
    tr.llm_call_failures = int(session.get("llm_call_failures") or 0)
    tr.draft_attractions = session.get("draft_attractions") or []

    pid = session.get("persona_id")
    if pid:
        pr = client.get(f"/phase0/personas/{pid}")
        if pr.status_code < 300:
            tr.persona = pr.json()
        else:
            tr.stopped_reason += f" | persona {pr.status_code}"
    return tr

"""합성 보호자 대본을 실제 Mi:dm 온보딩 API에 재생해 Persona를 저장한다.

직접 ``Persona``를 만들거나 축 점수를 주입하지 않는다. 매 턴 서버가 현재 겨냥한
슬롯을 조회하고, 그 슬롯에 해당하는 합성 보호자 답변을 보낸다. 완료 뒤에는 12개
슬롯이 전부 ``filled_keys``에 들어갔는지 확인한 경우만 결과로 인정한다.

실행 예:
    python -m experiments.personalized_alert_replay.build_persona_bank \
      --base https://macmini.tail67859f.ts.net:8443 --profiles SP01
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

HERE = Path(__file__).resolve().parent
PROFILE_PATH = HERE / "guardian_profiles.json"
RESULTS = HERE / "results"

AXES = (
    "mobility_transport_capacity",
    "hazard_awareness_vulnerability",
    "communication_approach_vulnerability",
    "autobiographical_destination_pull",
    "wayfinding_error_recovery_deficit",
    "distress_induced_movement_reactivity",
)
LEVELS = (0.1, 0.3, 0.5, 0.7, 0.9)
ALL_SLOT_KEYS = (
    "identity", "home", "routine_destinations", "autobiographical_destination_pull",
    "dementia_wandering_pattern", "mobility_transport_capacity",
    "hazard_awareness_vulnerability", "communication_approach_vulnerability",
    "medication", "wayfinding_error_recovery_deficit", "lost_behavior",
    "distress_induced_movement_reactivity",
)


class GuardianProfile(BaseModel):
    profile_id: str = Field(pattern=r"^SP\d{2}$")
    synthetic_name: str
    age: int = Field(ge=65, le=95)
    home_area: str
    behavior_archetype: str
    expected_behavior_tendency: Literal["stay", "move", "backtrack", "hide"]
    target_levels: dict[str, float]
    slot_answers: dict[str, str]

    @model_validator(mode="after")
    def validate_levels(self):
        if set(self.target_levels) != set(AXES):
            raise ValueError("target_levels는 운영 6축을 정확히 한 번씩 포함해야 함")
        if any(value not in LEVELS for value in self.target_levels.values()):
            raise ValueError(f"target_levels 허용값은 {LEVELS}")
        if set(self.slot_answers) != set(ALL_SLOT_KEYS):
            missing = sorted(set(ALL_SLOT_KEYS) - set(self.slot_answers))
            extra = sorted(set(self.slot_answers) - set(ALL_SLOT_KEYS))
            raise ValueError(f"slot_answers 불일치 missing={missing} extra={extra}")
        if any(not answer.strip() for answer in self.slot_answers.values()):
            raise ValueError("12개 슬롯 답변은 모두 빈 문자열이 아니어야 함")
        return self


class GuardianBank(BaseModel):
    schema_version: int
    generation_method: Literal["scripted_guardian_through_live_midm"]
    scope: Literal["dementia_walk_only_no_transit"]
    profiles: list[GuardianProfile] = Field(min_length=1)


def load_profiles(path: Path = PROFILE_PATH) -> list[GuardianProfile]:
    bank = GuardianBank.model_validate_json(path.read_text(encoding="utf-8"))
    ids = [profile.profile_id for profile in bank.profiles]
    if len(ids) != len(set(ids)):
        raise ValueError("profile_id 중복")
    return bank.profiles


def answers_for(profile: GuardianProfile) -> dict[str, str]:
    """한 인물씩 개별 작성된 12개 보호자 답변을 그대로 반환한다."""
    return dict(profile.slot_answers)


class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def request(self, method: str, path: str, body: dict | None = None, timeout: int = 180):
        data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        req = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise RuntimeError(f"{method} {path}: HTTP {exc.code} {detail}") from exc


def replay_profile(api: Api, profile: GuardianProfile, run_id: str, max_turns: int) -> dict:
    answers = answers_for(profile)
    started = api.request("POST", "/phase0/interviews/sessions", {
        "guardian_name": f"[합성실험] 보호자 {profile.profile_id}",
        "guardian_id": f"synthetic-{run_id}-{profile.profile_id}",
        "mode": "create",
        "scope": "all",
        "persona_type": "dementia",
    })
    session_id = started["session_id"]
    print(f"  session={session_id}", flush=True)
    transcript = []

    for turn in range(max_turns):
        session = api.request("GET", f"/phase0/interviews/{session_id}")
        if session["done"]:
            break
        question = session["messages"][-1]["text"]
        if session["awaiting_confirmation"]:
            # 운영 확인 게이트는 발화 전체가 _AFFIRM_WORDS로만
            # 이루어져야 한다. "등록된 내용이 모두"는 정정으로 간주된다.
            answer = "네 맞습니다"
            slot = "confirmation"
        else:
            slot = session["prev_target_key"]
            if session.get("asked_more_places") and slot == "routine_destinations" \
                    and "또 있을까요" in question:
                answer = "앞에서 말씀드린 곳 외에 추가로 자주 가거나 좋아하는 곳은 없습니다."
            elif session.get("pending_area_label"):
                answer = f"그 장소는 {profile.home_area}에서 걸어서 갈 수 있는 서울 지역입니다."
            elif slot in answers:
                answer = answers[slot]
            else:
                raise RuntimeError(f"{profile.profile_id}: 답변 대본이 없는 슬롯 {slot!r}")
        transcript.append({"turn": turn + 1, "slot": slot, "question": question, "answer": answer})
        print(
            f"  turn={turn + 1:02d} slot={slot} "
            f"filled={len(session['filled_keys'])}/{len(ALL_SLOT_KEYS)}",
            flush=True,
        )
        api.request("POST", f"/phase0/interviews/sessions/{session_id}/messages", {"text": answer})
    else:
        raise RuntimeError(
            f"{profile.profile_id}: session={session_id} "
            f"{max_turns}턴 안에 인터뷰가 끝나지 않음"
        )

    session = api.request("GET", f"/phase0/interviews/{session_id}")
    filled = set(session["filled_keys"])
    missing = sorted(set(ALL_SLOT_KEYS) - filled)
    if missing:
        raise RuntimeError(f"{profile.profile_id}: 완료됐지만 filled_keys 누락 {missing}")
    if not session.get("persona_id"):
        raise RuntimeError(f"{profile.profile_id}: 완료됐지만 persona_id 없음")
    persona = api.request("GET", f"/phase0/personas/{session['persona_id']}")
    if set(persona.get("completed_tiers", [])) != {1, 2, 3}:
        raise RuntimeError(f"{profile.profile_id}: completed_tiers 불완전")
    return {
        "profile_id": profile.profile_id,
        "target_levels": profile.target_levels,
        "session_id": session_id,
        "persona_id": session["persona_id"],
        "filled_keys": session["filled_keys"],
        "turns": len(transcript),
        "llm_degraded": session["llm_degraded"],
        "llm_call_failures": session["llm_call_failures"],
        "transcript": transcript,
        "persona": persona,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--profiles", default="", help="쉼표 구분 SP01,SP02; 빈 값은 전체")
    parser.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    parser.add_argument("--max-turns", type=int, default=40)
    args = parser.parse_args()

    profiles = load_profiles()
    selected = {value.strip() for value in args.profiles.split(",") if value.strip()}
    if selected:
        profiles = [profile for profile in profiles if profile.profile_id in selected]
        missing_ids = selected - {profile.profile_id for profile in profiles}
        if missing_ids:
            raise SystemExit(f"없는 profile_id: {sorted(missing_ids)}")

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"persona_bank_{args.run_id}.jsonl"
    api = Api(args.base)
    rows = []
    for index, profile in enumerate(profiles, start=1):
        print(f"[{index}/{len(profiles)}] {profile.profile_id} Mi:dm 온보딩 시작", flush=True)
        row = replay_profile(api, profile, args.run_id, args.max_turns)
        rows.append(row)
        # 중간에 한 명이 실패해도 앞서 완료한 운영 Persona와
        # transcript를 잃지 않도록 매 성공 후 checkpoint한다.
        out.write_text(
            "\n".join(json.dumps(item, ensure_ascii=False) for item in rows) + "\n",
            encoding="utf-8",
        )
        print(
            f"  persona={row['persona_id']} turns={row['turns']} "
            f"filled={len(row['filled_keys'])}/{len(ALL_SLOT_KEYS)} "
            f"degraded={row['llm_degraded']}",
            flush=True,
        )

    print(f"saved={out} n={len(rows)}")


if __name__ == "__main__":
    main()

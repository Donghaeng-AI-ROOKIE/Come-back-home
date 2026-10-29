"""부스 온보딩 템플릿 만들기 — 12문항을 대신 답해 '확인 대기' 세션을 만들고 템플릿으로 저장.

사용 (시연 진입점으로 띄운 서버가 필요하다 — uvicorn app.demo_main:app):
    python -m scripts.demo_onboarding_template                # 기본 킨텍스 시나리오
    python -m scripts.demo_onboarding_template --api http://127.0.0.1:8000 --label "킨텍스 v1"
    python -m scripts.demo_onboarding_template --answers my_answers.json

답은 **슬롯 키별**로 준다(세션의 prev_target_key 를 보고 고른다). 질문 순서는 검색이
정하므로 순서에 의존하지 않고, 되묻기(장소 주소·집 후보 고르기)도 키로 대응한다.
Mi:dm 실호출이 12번 들어가므로 1분 안팎 걸린다. 결과는 서버의 템플릿 파일에
저장되고, 이후 체험은 Mi:dm 을 "맞아요" 판정 1번만 부른다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

# 킨텍스 시나리오 — 가상 인물. 끌림점이 킨텍스 주변 지도 안에 들어오게 일산 지명으로 잡았다.
DEFAULT_ANSWERS: dict[str, str] = {
    "identity": "김영숙, 76세예요.",
    "home": "고양시 일산서구 대화동이요.",
    "routine_destinations": "아침마다 일산호수공원으로 산책을 가세요. 대화역 근처 시장에도 자주 가시고요.",
    "autobiographical_destination_pull": "예전에 살던 고양시 장항동 집 얘기를 자주 하세요. 그 집에 가려고 혼자 나가신 적도 있어요.",
    "dementia_wandering_pattern": "작년에 버스를 잘못 타고 백석동까지 가신 적이 있어요. 해질녘에 나가시는 편이에요.",
    "mobility_transport_capacity": "걸어 다니시고 버스도 혼자 타세요. 30분 정도는 쉬지 않고 걸으세요.",
    "hazard_awareness_vulnerability": "찻길을 건널 때 신호를 잘 안 보세요.",
    "communication_approach_vulnerability": "낯선 사람이 말을 걸면 친절하게 대답하시는 편이에요.",
    "medication": "치매약을 아침에 드세요. 거르면 많이 불안해하세요.",
    "wayfinding_error_recovery_deficit": "길을 잘못 들면 스스로 돌아오지 못하고 계속 한 방향으로 가세요.",
    "lost_behavior": "길을 잃으면 큰길을 따라 계속 걸으세요.",
    "distress_induced_movement_reactivity": "불안하거나 당황하면 사람 많은 곳을 피해서 골목으로 들어가세요.",
    # 되묻기 — 장소 주소를 물을 때(어느 장소든 같은 동네로 답한다)
    "_area": "고양시 일산동구 장항동이요.",
    # 집 후보 고르기(여러 개 나왔을 때)
    "_choice": "첫번째요.",
    # 그 밖의 예상 못 한 질문
    "_fallback": "특별히 없어요.",
}


def call(api: str, method: str, path: str, body=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(api + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path} → {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")


def pick_answer(session: dict, answers: dict[str, str], asked: dict[str, int]) -> str:
    if session.get("pending_area_label"):
        return answers["_area"]
    if session.get("home_choices"):
        return answers["_choice"]
    key = session.get("prev_target_key") or ""
    asked[key] = asked.get(key, 0) + 1
    if key in answers and asked[key] == 1:
        return answers[key]
    # 같은 슬롯을 다시 묻는 꼬리질문(probe) — 짧게 보탠다
    return answers.get("_fallback", "특별히 없어요.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--label", default="킨텍스 시나리오")
    ap.add_argument("--answers", help="슬롯 키별 답 JSON 파일(기본값 덮어쓰기)")
    ap.add_argument("--guardian-id", default="template-author")
    ap.add_argument("--max-turns", type=int, default=40)
    args = ap.parse_args()

    answers = dict(DEFAULT_ANSWERS)
    if args.answers:
        answers.update(json.load(open(args.answers, encoding="utf-8")))

    s = call(args.api, "POST", "/phase0/interviews", {"guardian_name": "보호자", "guardian_id": args.guardian_id})
    sid = s["id"]
    print(f"session {sid}")
    asked: dict[str, int] = {}
    for turn in range(args.max_turns):
        if s.get("awaiting_confirmation"):
            break
        if s.get("done"):
            raise SystemExit("세션이 확인 게이트 없이 끝났다 — skip_confirmation 설정을 확인하세요")
        q = s["messages"][-1]["text"] if s["messages"] else ""
        a = pick_answer(s, answers, asked)
        print(f"[{turn + 1:02d}] {s.get('prev_target_key')} Q: {q[:50]!r}\n     A: {a}")
        t0 = time.time()
        s = call(args.api, "POST", f"/phase0/interviews/{sid}/answers", {"text": a})
        print(f"     ({time.time() - t0:.1f}s, filled {len(s['filled_keys'])})")
    else:
        raise SystemExit("확인 단계에 도달하지 못했다 — 답 목록을 보완하세요")

    print("\n요약 확인 단계 도달:\n" + s["messages"][-1]["text"])
    meta = call(args.api, "POST", "/demo/onboarding/template", {"session_id": sid, "label": args.label})
    print("\n템플릿 저장:", json.dumps(meta, ensure_ascii=False, indent=2))
    print("\n이 세션은 그대로 둔다(원하면 앱에서 '맞아요'로 등록해도 된다).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

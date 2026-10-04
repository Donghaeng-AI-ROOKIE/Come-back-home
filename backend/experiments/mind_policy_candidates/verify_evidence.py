"""Recompute published checks from final responses; no API, GPU, or map request.

Run from backend: python -m experiments.mind_policy_candidates.verify_evidence
This verifies the archive, not clinical accuracy or release qualification.
"""
import hashlib
import json
import re
from pathlib import Path

from app.llm.initial_behavior import decode_json_content
from app.llm.mind_policy import possibilities
from app.llm.mind_policy_candidate import compile as compile_policy

ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence_20261004"
BACKEND = ROOT.parents[1]


def read(path):
    return json.loads(path.read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def final_policy(person_id, personal, adaptive):
    response_path = EVIDENCE / "shareable_model_outputs" / "diagnostic24" / person_id / "review.public.json"
    followup = EVIDENCE / "shareable_model_outputs" / "review_invalid" / person_id / "review.public.json"
    if adaptive and followup.exists():
        response_path = followup
    if not response_path.exists():
        return None
    response = read(response_path)
    if response["finish_reason"] != "stop":
        return None
    try:
        return compile_policy(decode_json_content(response["final_content"]), personal)
    except (ValueError, TypeError, KeyError, AssertionError, AttributeError):
        return None


def verify_evaluation(adaptive=False):
    inputs = {row["id"]: row for row in read(EVIDENCE / "holdout_inputs.json")}
    scenes = read(EVIDENCE / "holdout_scenarios.json")
    policies = {key: final_policy(key, row["personal"], adaptive) for key, row in inputs.items()}
    name = "adaptive_evaluation.json" if adaptive else "holdout_evaluation.json"
    saved = read(EVIDENCE / name)
    require(len(scenes) == len(saved["checks"]), "scene count differs")
    passed_by_person = {key: [] for key in inputs}
    for scene, expected in zip(scenes, saved["checks"]):
        require((scene["id"], scene["scene"]) == (expected["id"], expected["scene"]), "scene order differs")
        policy = policies[scene["id"]]
        actions = None
        passed = False
        if policy is not None:
            options, _ = possibilities(policy, scene["facts"], near_places=scene["near_places"], near_features=scene["near_features"])
            action_set = {rule.action if rule else None for rule in options}
            actions = sorted(action_set, key=str)
            passed = bool(action_set) and action_set <= set(scene["allowed_actions"])
        require(actions == expected["actual_actions"] and passed == expected["passed"], f"check differs: {scene['id']} / {scene['scene']}")
        passed_by_person[scene["id"]].append(passed)
    computed = {
        "completed_people": len(inputs),
        "valid_policy_people": sum(policy is not None for policy in policies.values()),
        "scene_checks": len(scenes),
        "scene_checks_passed": sum(sum(values) for values in passed_by_person.values()),
        "people_all_checks_passed": sum(bool(values) and all(values) for values in passed_by_person.values()),
    }
    for key, value in computed.items():
        require(saved[key] == value, f"summary differs: {name} / {key}")
    return computed


def main():
    manifest = read(EVIDENCE / "implementation_manifest.json")
    for relative, expected in manifest["current_source_sha256"].items():
        require(hashlib.sha256((BACKEND / relative).read_bytes()).hexdigest() == expected, f"implementation hash differs: {relative}")
    usage = read(EVIDENCE / "usage_summary.json")
    require(usage["started"] == usage["finished"] and not usage["pending_attempts"], "unreconciled usage")
    require(sum(usage["outcomes"].values()) == usage["finished"], "usage outcomes differ")
    require(sum(usage["by_role"].values()) == usage["started"], "usage role counts differ")
    require(usage["provider_reported_usage"]["total_tokens"] == usage["provider_reported_usage"]["prompt_tokens"] + usage["provider_reported_usage"]["completion_tokens"], "usage token sum differs")
    for root in (ROOT, ROOT.parent / "mind_closed_loop"):
        for path in root.rglob("*.md"):
            for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
                if "://" not in target and not target.startswith("#"):
                    require((path.parent / target.split("#")[0]).exists(), f"missing link: {path.name} / {target}")
    for path in (EVIDENCE / "shareable_model_outputs").rglob("*.json"):
        text = path.read_text()
        require("<think>" not in text and "</think>" not in text, f"non-final material in {path.name}")
    print(json.dumps({
        "original_frozen_evaluation": verify_evaluation(),
        "adaptive_followup_not_independent_holdout": verify_evaluation(adaptive=True),
        "implementation_hashes_checked": len(manifest["current_source_sha256"]),
        "usage_attempts_reconciled": usage["finished"],
        "external_requests": 0,
        "release_qualification": "not_passed",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

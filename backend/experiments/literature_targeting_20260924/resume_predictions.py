"""Bounded prior-format recovery, preserving successful v2 checkpoints and config."""
import json
from pathlib import Path
import sys

from app import llm
from experiments.literature_targeting_20260924.run_predictions import main, sha, write, HERE


def run():
    output = Path(sys.argv[sys.argv.index("--output") + 1]) if "--output" in sys.argv else HERE / "predictions_v1"
    output.mkdir(parents=True, exist_ok=True)
    policy = {"wrapper_sha256": sha(__file__), "max_prior_format_attempts": 3,
              "reason": "prior JSON format failure after 33 development checkpoints; no outcome-based retry",
              "completed_valid_checkpoints": "preserved; generation policy unchanged",
              "scope": "development remainder and evaluation"}
    policy_path = output / "prior_recovery_policy.json"
    if policy_path.exists() and json.loads(policy_path.read_text(encoding="utf-8")) != policy:
        raise RuntimeError("Prior recovery policy changed")
    write(policy_path, policy)
    original = llm.exaone.generate_prior
    log_path = output / "prior_recovery_log.jsonl"
    def generate_prior(persona, report):
        for attempt in range(3):
            result = original(persona, report)
            if result.source == "exaone":
                return result
            event = {"report_id": report.id, "attempt": attempt + 1,
                     "reason": result.fallback_reason, "call": llm.exaone.call_log[-1] if llm.exaone.call_log else None}
            with log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
            # Only parser/JSON-shape failures; authentication/transport errors are not retried here.
            if not any(name in result.fallback_reason for name in ("JSONDecodeError", "ValueError", "KeyError", "TypeError")):
                return result
        return result  # original runner fails closed rather than exclude this case
    llm.exaone.generate_prior = generate_prior
    main()


if __name__ == "__main__":
    run()

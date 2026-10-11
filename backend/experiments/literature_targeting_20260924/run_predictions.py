"""Inputs-only EXAONE + production MC runner; never registers cases or sends alerts."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import time
import urllib.request

from app import llm
from app.config import settings
from app.geo.roadnet import OSMnxNetwork
from app.phase2 import combine, simulation
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, Persona
from app.schemas.prediction import MindState
from app.schemas.report import MissingReport

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def preflight():
    c = llm.exaone
    if c.is_stub:
        raise RuntimeError("Real EXAONE configuration required; stub is not an experiment result")
    url = c.base_url.removesuffix("/chat/completions")
    if not url.endswith("/v1"):
        url += "/v1"
    req = urllib.request.Request(url + "/models", headers={"Authorization": "Bearer " + c.api_key})
    with urllib.request.urlopen(req, timeout=8) as r:
        models = sorted(x["id"] for x in json.load(r)["data"])
    required = {c.model, settings.mind_model or c.model}
    if not required.issubset(models):
        raise RuntimeError(f"Required model missing: {sorted(required - set(models))}")
    return models


def adapt(case, arm):
    source = case[arm]
    common, personal = source["common"], source["personal"]
    persona = Persona(id=case["profile_id"] + "-" + arm, name="합성 실험 인물",
                      age=common["age"], type=common["type"], home=common["home"],
                      behavior_notes=personal["caregiver_notes"] if personal else [],
                      attraction_points=[AttractionPoint(label="사전등록 산책 목적지",
                          location=personal["routine_destination"], evidence="caregiver_report",
                          weight=0.5, origin_slot="routine_destinations")] if personal else [])
    report = MissingReport(id=case["scenario_id"] + "-" + arm,
                           persona_id=persona.id, missing_type=common["type"],
                           lkp=common["last_seen"], lkp_time=datetime(2026, 9, 24, 10, 0),
                           situation=common["scene"])
    return persona, report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--split", choices=["development", "evaluation"], required=True)
    p.add_argument("--output", type=Path, default=HERE / "predictions_v1")
    p.add_argument("--preflight-only", action="store_true")
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    status_path = args.output / "STATUS.json"
    try:
        models = preflight()
    except Exception as e:
        write(status_path, {"status": "blocked_model_connection", "error": str(e),
                           "split": args.split, "predictions_generated": False})
        raise SystemExit(f"Preflight failed: {e}")
    if args.preflight_only:
        print(json.dumps({"models": models, "status": "ready"}))
        return
    original_mind = llm.exaone.reinterpret_mind
    recovery_log = []
    def strict_mind(*a, **kw):
        rng = kw.get("rng")
        state = rng.getstate() if rng else None
        for attempt in range(3):
            if rng and state is not None:
                rng.setstate(state)
            previous = llm.exaone.call_log[-1] if llm.exaone.call_log else None
            result = original_mind(*a, **kw)
            latest = llm.exaone.call_log[-1] if llm.exaone.call_log else None
            try:
                if latest is previous or latest is None or latest["kind"] != "mind":
                    raise RuntimeError("Mind model silently fell back")
                raw = latest["response"]
                parsed = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
                if not isinstance(parsed, dict):
                    raise ValueError("Non-object model response")
                return result
            except (ValueError, RuntimeError) as e:
                recovery_log.append({"attempt": attempt + 1, "error": str(e),
                    "call": latest if latest is not previous else None})
                write(args.output / "recovery_log.json", recovery_log)
                if attempt == 2:
                    raise RuntimeError("Mind response invalid after 3 attempts; no exclusion") from e
    llm.exaone.reinterpret_mind = strict_mind
    path = HERE / "dataset_v1" / f"{args.split}_inputs.json"
    cases = json.loads(path.read_text(encoding="utf-8"))
    if args.split == "evaluation":
        done = args.output / "development_complete.json"
        if not done.exists():
            raise SystemExit("Complete development execution before evaluation")
    # No truth files or manifest containing truth information are opened here.
    config = {"runner_sha256": sha(__file__), "seed": 42, "format_retries": 3,
              "model": llm.exaone.model, "mind_model": settings.mind_model,
              "mc_num_walkers": settings.mc_num_walkers, "mind_call_budget": settings.mind_call_budget,
              "environment": "fixed cached road graph; node environmental layer disabled in both arms",
              "mapping": "destination and caregiver notes used; full routine_route not consumed",
              "source_sha256": {str(f.relative_to(BACKEND)): sha(f) for f in
                  [BACKEND / "app/phase2/simulation.py", BACKEND / "app/phase2/combine.py",
                   BACKEND / "app/llm/exaone.py", BACKEND / "app/config.py"]}}
    # Include non-secret effective settings so resume cannot silently change policy.
    config["effective_settings"] = {k: v for k, v in settings.model_dump(mode="json").items()
        if not any(s in k.lower() for s in ("key", "secret", "token", "password", "credential"))}
    config_path = args.output / "config.json"
    if config_path.exists():
        if json.loads(config_path.read_text(encoding="utf-8")) != config:
            raise SystemExit("Frozen prediction configuration changed; use a new output directory")
    else:
        write(config_path, config)
    out = args.output / args.split
    out.mkdir(exist_ok=True)
    input_lock = out / "input_sha256.txt"
    if input_lock.exists() and input_lock.read_text().strip() != sha(path):
        raise SystemExit("Input changed")
    input_lock.write_text(sha(path) + "\n")
    nets, completed = {}, 0
    for index, case in enumerate(cases):
        graph_file = case["graph_file"]
        if graph_file not in nets:
            nets[graph_file] = OSMnxNetwork.from_graphml(BACKEND / "data/roadnet_cache" / graph_file)
        for arm in ("BC" if index % 2 == 0 else "CB"):
            checkpoint = out / f"{case['scenario_id']}_{arm}.json"
            if checkpoint.exists():
                completed += 1
                continue
            start = time.monotonic()
            persona, report = adapt(case, arm)
            llm.exaone.call_log.clear()
            prior = llm.exaone.generate_prior(persona, report)
            if prior.source != "exaone":
                write(status_path, {"status": "failed_prior", "scenario_id": case["scenario_id"],
                                   "arm": arm, "source": prior.source, "reason": prior.fallback_reason})
                raise SystemExit("Real prior failed; no silent fallback or exclusion")
            snapshots = []
            for minute in case["minutes_after_report"]:
                elapsed = (case[arm]["common"]["minutes_before_report"] + minute) / 60
                bu = simulation.run_monte_carlo(report.lkp, prior, persona, elapsed,
                    mode="agent", net=nets[graph_file], mind=MindState(), seed=42)
                stat = simulation.run_monte_carlo(report.lkp, prior, persona, elapsed,
                    mode="statistical", net=nets[graph_file], seed=42)
                surface = combine.alpha_pool([bu, stat], alphas=[.7, .3], mode="linear")
                snapshots.append({"minute_after_report": minute, "surface_cells": surface})
            write(checkpoint, {"scenario_id": case["scenario_id"], "profile_id": case["profile_id"],
                  "arm": arm, "prior": prior.model_dump(mode="json"),
                  "persona": persona.model_dump(mode="json"), "report": report.model_dump(mode="json"),
                  "snapshots": snapshots, "call_log": llm.exaone.call_log,
                  "elapsed_seconds": time.monotonic() - start})
            completed += 1
            print(f"{args.split}: {completed}/{2*len(cases)} arm checkpoints; {time.monotonic()-start:.1f}s", flush=True)
    write(args.output / f"{args.split}_complete.json", {"arms": completed, "input_sha256": sha(path)})
    write(status_path, {"status": "predictions_complete", "split": args.split, "arms": completed})


if __name__ == "__main__":
    main()

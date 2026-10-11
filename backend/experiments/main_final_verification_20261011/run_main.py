"""Final verification of main (ad9597f): product preparation and product prediction.

Adapted from EFFICIENCY_KINTEX_v1_20261009/run_experiment.py. Differences:
  - Preparation runs the product functions themselves: person_preparation.enqueue
    -> run_job -> mind_preparation.prepare (dispatch made synchronous here).
  - Each map is pipeline.run_prediction at 1/2/4/6 h on one continuous case, so
    main decides the engine (continuous engine with a prepared policy; the legacy
    walk with dem5 when no policy is ready) and generates the prior itself.
  - Two arms only: B (no personal answers) and D (full product). C is dropped.
  - Sharded: --shard k --shards n splits people; per-shard progress and ledger.
Truth is deliberately absent from this process/container.
"""
from pathlib import Path
import argparse, collections, hashlib, importlib, json, os, threading, time, uuid
from datetime import datetime, timedelta
R = Path(__file__).resolve().parent
OUT = Path(os.getenv("EVIDENCE_DIR", "/evidence")); OUT.mkdir(parents=True, exist_ok=True)
ap = argparse.ArgumentParser()
ap.add_argument("--execute", action="store_true")
ap.add_argument("--split", choices=["development", "evaluation"], default="development")
ap.add_argument("--shard", type=int, default=0)
ap.add_argument("--shards", type=int, default=1)
ARGS = ap.parse_args()
TAG = f"{ARGS.split[:3]}-s{ARGS.shard}"
LEDGER = Path(f"/usage/usage_events_{TAG}.jsonl")


def save(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp"); tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n"); tmp.replace(path)


def now():
    return datetime.now().isoformat()


def event(**kw):
    with (OUT / f"progress_{TAG}.jsonl").open("a") as f:
        f.write(json.dumps(dict(time=now(), **kw), ensure_ascii=False) + "\n")
    print(json.dumps(dict(time=now(), **kw), ensure_ascii=False), flush=True)


def configure():
    from dotenv import dotenv_values
    # Never print/save secrets. Only an explicit AI setting allowlist is copied.
    values = dotenv_values("/run/ai.env")
    prefixes = ("KEXAONE_", "EXAONE_", "MIDM_", "EMBED_", "UPSTAGE_", "RAG_", "LLM_")
    for k, v in values.items():
        if v is not None and k.startswith(prefixes):
            os.environ[k] = v
    # Deployed worker settings (compose.yml + worker.env non-secret values, 10/10 check).
    os.environ.update(PERSIST_STORAGE="false", PUSH_ENABLED="false", PRIVACY_SCHEDULER_ENABLED="false",
        POA_REFRESH_ENABLED="false", EXAONE_WARMUP_ENABLED="false", PYTHONDONTWRITEBYTECODE="1",
        CBH_API_ENABLED="false", REFLEX_ALERT_ON_INTAKE="false", ROADNET_PRELOAD="false",
        RAG_INDEX_PATH="/assets/rag/rag_index_upstage.npz", RESEARCH_USAGE_LEDGER_PATH=str(LEDGER),
        MIND_POLICY_CONTRACT="guarded_core", MIND_POLICY_DEPLOYMENT="staging", USE_ROADNET="true",
        PERSONAL_WALK_CACHE_PATH="/assets/kintex/kintex_walk.graphml", MC_NUM_WALKERS="500",
        MIND_CONTRACT="v2", MIND_MODEL="exaone-mind-dem5", MIND_CALL_BUDGET="5")


configure()
from app import storage  # noqa: E402
from app.config import settings  # noqa: E402
from app.llm import exaone, midm, initial_behavior, usage_ledger  # noqa: E402
from app.phase0 import person_preparation as pp, mind_preparation as mp  # noqa: E402
from app.phase2 import initial_person, pipeline, continuous_prediction  # noqa: E402, F401
from app.schemas.persona import Persona  # noqa: E402
from app.schemas.report import MissingReport  # noqa: E402
from app.schemas.case import Case  # noqa: E402
from app.geo.roadnet import verified_network  # noqa: E402

SCOPE = json.loads((R / "scope.json").read_text()); DATA = json.loads((R / "inputs.json").read_text())
CURRENT = "preflight"; LOCK = threading.Lock(); TOTAL = collections.Counter(); PERSON = {}
ORIGINAL = usage_ledger.logged_json_request


def group(provider, model):
    if provider == "FriendliAI": return "K_EXAONE"
    if provider == "KT Mi:dm": return "Mi_dm"
    if provider == "LG EXAONE (self-hosted)": return "dem5_mind" if model == settings.mind_model else "SAR_EXAONE"
    if provider == "embedding_api": return "embedding"
    raise ValueError("unexpected provider")


# Replay every shard ledger of this split so per-person caps survive a restart
# (the ledger records the model as model_requested).
for ledger in sorted(Path("/usage").glob(f"usage_events_{ARGS.split[:3]}-s*.jsonl")):
    for line in ledger.read_text().splitlines():
        row = json.loads(line)
        if row.get("event_type") == "api_attempt_started":
            g = group(row["provider"], row.get("model_requested")); pid = row["run_id"].split("/")[1]
            PERSON.setdefault(pid, collections.Counter())[g] += 1
            if ledger == LEDGER: TOTAL[g] += 1


def audited(url, payload, **kw):
    g = group(kw["provider"], kw.get("model")); pid = CURRENT
    assert pid != "preflight", "external call during offline preflight"
    with LOCK:
        pc = PERSON.setdefault(pid, collections.Counter())
        if pc[g] >= SCOPE["limits"]["per_person"][g]: raise RuntimeError("frozen call cap")
        if len(json.dumps(payload, ensure_ascii=False).encode()) > SCOPE["limits"]["max_input_bytes"]: raise ValueError("input cap")
        if payload.get("max_tokens", 0) > SCOPE["limits"]["max_output_tokens"].get(g, float("inf")): raise ValueError("output cap")
        TOTAL[g] += 1; pc[g] += 1; n = pc[g]
    kw["ledger_path"] = LEDGER; kw["run_id"] = SCOPE["experiment"] + "/" + pid + "/" + kw["run_id"]
    stamp = uuid.uuid4().hex
    record = dict(person_id=pid, group=g, ordinal=n, role=kw.get("role"), requested_model=kw.get("model"),
        request_body_sha256=hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        started_at=now(), request_body=payload)
    # Synthetic payloads are allowed in private evidence, never in cost ledger.
    path = OUT / "public_outputs" / pid / (g + "-" + stamp + ".json")
    save(path, record)
    try:
        response = ORIGINAL(url, payload, **kw)
        record.update(request_id=response.get("id"), usage=response.get("usage"), model_returned=response.get("model"),
            choices=[dict(finish_reason=c.get("finish_reason"), content=c.get("message", {}).get("content")) for c in response.get("choices", [])])
        return response
    except Exception as exc:
        record["error_type"] = type(exc).__name__; raise
    finally:
        record["finished_at"] = now(); save(path, record)


usage_ledger.logged_json_request = audited
# Replace aliases imported at module load, preserving actual transport and prompts.
initial_person.logged_json_request = audited; mp.logged_json_request = audited
importlib.import_module("app.llm.midm").logged_json_request = audited
# The product queues preparation on worker threads; run the same jobs synchronously.
pp._dispatch = lambda persona_id, job_id, kind="initial": (
    pp.run_job(persona_id, job_id) if kind == "initial" else mp.run_queued(persona_id, job_id))


def report_of(item):
    """Report times as the app sends them: the authored values are KST wall-clock
    times; the app sends an absolute instant (toISOString), which the schema turns
    into server-local naive time. Same path as production on this server."""
    raw = json.loads(json.dumps(item["report"]))
    def kst(v):
        return v if (v.endswith("Z") or "+" in v[10:]) else v + "+09:00"
    raw["lkp_time"] = kst(raw["lkp_time"])
    for obs in raw.get("environment_observations", []):
        obs["valid_from"] = kst(obs["valid_from"]); obs["valid_until"] = kst(obs["valid_until"])
    return MissingReport.model_validate(raw)


def items():
    z = [x for x in DATA if x["split"] == ARGS.split]
    return z[ARGS.shard::ARGS.shards]


def preflight():
    assert not exaone.is_stub and not midm.is_stub, "configured SAR and Mi:dm required"
    assert all((settings.kexaone_api_key, settings.kexaone_base_url, settings.kexaone_model))
    assert Path(settings.rag_index_path).is_file()
    assert settings.mind_policy_deployment == "staging" and settings.mind_policy_contract == "guarded_core"
    assert settings.mind_model == "exaone-mind-dem5" and settings.mind_contract == "v2" and settings.mind_call_budget == 5
    assert not settings.mind_policy_interpretation_review
    assert len(DATA) == 36 and len({x["person_id"] for x in DATA}) == 36
    for item in DATA:
        p = Persona.model_validate(item["persona"]); r = report_of(item)
        assert r.persona_id == p.id
        # The SAR input and preparation read lkp_time.astimezone(Asia/Seoul): must be the authored hour.
        from zoneinfo import ZoneInfo
        assert r.lkp_time.astimezone(ZoneInfo("Asia/Seoul")).hour == int(item["report"]["lkp_time"][11:13])
        assert initial_behavior.build_payload(p, None, [], None)["notes"]
    path = Path(settings.personal_walk_cache_path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == SCOPE["map_sha256"]
    net = verified_network(path)
    return dict(models=dict(K=settings.kexaone_model, SAR=settings.exaone_model, Mi_dm=settings.midm_model,
        mind=settings.mind_model, embedding=settings.embed_model), source_sha=SCOPE["source_sha"],
        map_sha256=SCOPE["map_sha256"], nodes=len(net.graph), edges=net.graph.number_of_edges(),
        dataset_people=len(DATA), shard=TAG, shard_people=[x["person_id"] for x in items()], calls=0,
        rag_sha256=hashlib.sha256(Path(settings.rag_index_path).read_bytes()).hexdigest())


def prepare(item):
    global CURRENT
    pid = item["person_id"]; CURRENT = pid; folder = OUT / "people" / pid; folder.mkdir(parents=True, exist_ok=True)
    done = folder / "prepared.json"
    if done.exists(): return json.loads(done.read_text())
    if (folder / "attempt_started.json").exists():
        # A crash may have been billable; preserve it instead of replaying silently.
        result = dict(person_id=pid, error_type="interrupted_preparation", status="failed")
        save(done, result); return result
    save(folder / "attempt_started.json", dict(time=now(), scope=SCOPE["experiment"]))
    event(person_id=pid, stage="prepare_started")
    start = time.monotonic()
    p = Persona.model_validate(item["persona"])
    storage.personas.save(pid, p)
    pp.enqueue(pid)  # product: initial K + Mi:dm claim check, then mind policy K
    prepared = storage.personas.get(pid)
    generic = Persona(id=p.id, type=p.type, name=p.name, age=p.age, home=p.home, created_at=p.created_at, version=p.version)
    result = dict(person_id=pid, split=item["split"], family=item["family"], status="completed",
        preparation_seconds=time.monotonic() - start, counts=dict(PERSON.get(pid, {})),
        initial_state=prepared.initial_preparation_status.get("state"),
        initial_error=prepared.initial_preparation_status.get("error_type"),
        mind_state=prepared.mind_preparation_status.get("state"),
        mind_error=prepared.mind_preparation_status.get("error_type"),
        mind_ready=mp.ready(prepared)[1],
        arms={"B_population": generic.model_dump(mode="json"), "D_full_prepared": prepared.model_dump(mode="json")})
    save(done, result)
    event(person_id=pid, stage="prepare_finished", seconds=round(result["preparation_seconds"], 1), counts=result["counts"],
          initial=result["initial_state"], mind=result["mind_state"], ready=result["mind_ready"])
    return result


def walk(item, prepared):
    global CURRENT
    pid = item["person_id"]; CURRENT = pid; folder = OUT / "people" / pid
    arms = prepared.get("arms")
    if prepared["status"] != "completed":
        # Interrupted preparation (crash/restart): D cannot be prepared without a
        # silent re-bill, so D is a recorded failure; B needs no preparation.
        p = Persona.model_validate(item["persona"])
        generic = Persona(id=p.id, type=p.type, name=p.name, age=p.age, home=p.home, created_at=p.created_at, version=p.version)
        save(folder / "walk_failure.json", dict(reason=prepared.get("error_type"), failed_arms=["D_full_prepared"]))
        arms = {"B_population": generic.model_dump(mode="json")}
    for arm, spec in arms.items():
        persona = Persona.model_validate(spec)
        storage.personas.save(pid, persona)  # arms run one after another under the same ID
        for seed in SCOPE["walk_seeds"]:
            output = folder / f"walk_{arm}_{seed}.json"
            if output.exists(): continue
            marker = folder / f"walk_{arm}_{seed}.started"
            if marker.exists():
                # Interrupted after calls may have been billed: record failure, never re-run.
                save(output, dict(person_id=pid, arm=arm, seed=seed, split=item["split"], family=item["family"], seconds=None,
                    snapshots=[dict(hour=h, complete=False, cells={}, error_type="interrupted_walk") for h in SCOPE["times_h"]]))
                continue
            save(marker, dict(time=now()))
            start = time.monotonic(); snapshots = []
            report = report_of(item)
            case = Case(id=f"{pid}-{arm}-{seed}", synthetic_test=True, report=report, lkp=report.lkp, lkp_time=report.lkp_time)
            for hour in SCOPE["times_h"]:
                t0 = time.monotonic()
                try:
                    result = pipeline.run_prediction(case, now=report.lkp_time + timedelta(hours=hour), seed=seed)
                    cells = dict(result.poa_combined.cells)
                    complete = bool(cells) and abs(sum(cells.values()) - 1) < 1e-6
                    q = result.quality
                    snapshots.append(dict(hour=hour, complete=complete, cells=cells if complete else {}, quality=q,
                        engine=q.get("engine"), prior_source=result.prior.source,
                        initial_prior_path=(result.prior.initial_interpretation or {}).get("initial_prior_path"),
                        seconds=round(time.monotonic() - t0, 1)))
                except Exception as exc:
                    stored = storage.cases.get(case.id)
                    snapshots.append(dict(hour=hour, complete=False, cells={}, error_type=type(exc).__name__,
                        quality=stored.prediction_quality if stored else {}, seconds=round(time.monotonic() - t0, 1)))
                case = storage.cases.get(case.id) or case
            save(output, dict(person_id=pid, arm=arm, seed=seed, split=item["split"], family=item["family"],
                seconds=time.monotonic() - start, snapshots=snapshots))
            event(person_id=pid, stage="walk_finished", arm=arm, seed=seed, complete=sum(x["complete"] for x in snapshots),
                  engines=[x.get("engine") for x in snapshots], seconds=round(time.monotonic() - start, 1))


def main():
    info = preflight(); save(OUT / f"preflight_{TAG}.json", info); event(stage="preflight_passed", **info)
    if not ARGS.execute: return
    plan = OUT / f"shard_plan_{ARGS.split}.json"
    if plan.exists():
        assert json.loads(plan.read_text())["shards"] == ARGS.shards, "shard count changed after the first launch"
    else:
        save(plan, dict(shards=ARGS.shards, time=now()))
    event(stage="batch_started", split=ARGS.split, limits=SCOPE["limits"], cost_amount=None, support_round=None)
    usage_ledger.append_event(dict(event_type="experiment_batch_started", run_id=SCOPE["experiment"] + "/" + TAG, split=ARGS.split,
        source_sha=SCOPE["source_sha"], limits=SCOPE["limits"], actual_cost=None, support_round=None), LEDGER)
    for item in items():
        walk(item, prepare(item))
    event(stage="batch_finished", split=ARGS.split, counts=dict(TOTAL))
    save(OUT / f"finished_{TAG}.json", dict(time=now(), counts=dict(TOTAL), people=[x["person_id"] for x in items()]))


if __name__ == "__main__":
    main()

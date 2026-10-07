# Mind context candidate — KINTEX pilot

Status: candidate implementation, **not production routing or verified model improvement**.
Baseline: develop `35817311f543bb25c287186d9a6072477f97ae37`.

## What is implemented

- Production guardian-source precedence, original onboarding quotes and complete
  prepared/incident K interpretation enter an explicit personal-context envelope.
- Current environment observations preserve true/false/unknown. Map proximity is
  separate from actual visibility. Time of day, elapsed time and recent events are
  separate fields. The builder performs no retrieval or inference.
- Six candidate actions distinguish temporary rest from continued staying.
  Destination updates, registered labels and evidence IDs are validated. No
  keyword parsing turns guardian wording into behavior.
- The executor uses the existing RoadNetwork/OSMnx interface, road/environment
  weighting and provisional gauge functions, but retains each walker's clock,
  position, edge progress, goal and event history across hourly snapshots.
- Rest consumes explicit simulated time; completed rest leads to reevaluation and
  can be followed by walking. A model error is surfaced, not converted into a
  successful-looking default response.
- The direct pilot freezes 12 synthetic development inputs and A/B requests before
  seeing any outputs. Legacy uses its existing input boundary. Candidate uses the
  new boundary: this is a **system contract comparison**, not model-only attribution.

## What is not yet validated

No claim of clinical behavior accuracy, real missing-person route accuracy, model
superiority, optimal budget, or full production compatibility. The candidate walk
executor is a small action-consumption probe; it does not replace the production
prior/radius/notification/report logic. It currently exposes no UI and is not
imported by production routes. Persistent simulation state remains in memory.

The runtime's rest duration, reevaluation interval, fatigue recovery and avoidance
scale must be explicitly supplied or identified as existing provisional engine
conventions. They are **sensitivity parameters**, not research-measured quantities.
Trigger detection at road nodes is a discrete approximation; it may react after an
observation changes mid-edge. A missing road neighbor is reported as blocked, not
classified as the person's decision to stop. A limited map cannot validate travel
outside its extent, especially for long elapsed times.

Output structure and evidence-ID existence do not establish that `reason` or an
action is semantically correct. Human/AI diagnostic reading is separate. No
word-based correction silently changes a model's action. RAG excerpts can be
provided as fixed paper excerpts, but RAG benefit has not been measured.

The same person's after-rest pair changes both fatigue and recorded history; it
can test scenario consistency, not isolate the causal effect of history. Places A/B
are explicit synthetic destinations, not verified KINTEX POIs. No current crowd or
noise measurement is asserted by the synthetic scene inputs.

## Geographic constraint

All new **spatial** probes require `tests/fixtures/kintex_walk.graphml` plus its
provenance JSON. If unavailable, spatial tests skip explicitly; there is no fallback
to Jeongneung or another city. Pure contract tests use a coordinate-free prompt and
inert geometry placeholders; they do not run a route. The shared cache belongs at
`결선/지도캐시/KINTEX_20260928/`. Preserve OSM attribution and content hashes.

## Reproduce (offline only)

```sh
python -m pytest -q tests/test_mind_upgrade.py tests/test_mind_upgrade_contract_v2.py tests/test_mind_upgrade_contract_v3.py
```

The KINTEX fixture and attribution are committed. Historical live API runners are
not included. Current findings and remaining gates are documented in
[the experiment report](../mind_retraining_20260928/README.md).

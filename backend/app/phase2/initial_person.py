"""SAR/RAG baseline + K interpretation of the person → existing simulation inputs.

Independent K tasks read the same source notes. Only code generates numeric factors.
No retries. Each request is reserved and logged before network IO. No production toggle:
configured credentials enable the candidate; provider/contract failures remain visible.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import logging
import uuid

from app.config import settings
from app.llm import initial_behavior, person_evidence, person_scope, person_audit
from app.llm.usage_ledger import logged_json_request
from app.phase2.person_projection import compile_person

log = logging.getLogger(__name__)


def cached_research(persona, report):
    from app.rag import get_retriever
    from app.llm.exaone import _build_rag_query
    retriever = get_retriever()
    if retriever is None:
        return []
    return [{"text": p.text, "source": p.source, "kind": p.kind}
            for p in retriever.search(_build_rag_query(persona, report.missing_type if report else persona.type))]


def refine(persona, report, sar, default):
    def status(value, **extra):
        return sar.model_copy(update={"initial_interpretation": {
            "status": value, "version": person_evidence.VERSION, **extra}})

    if persona is None:
        return status("no_persona")
    if not (settings.kexaone_base_url and settings.kexaone_api_key and settings.kexaone_model):
        return status("unconfigured")
    try:
        payload = initial_behavior.build_payload(persona, report, [], sar)
        if not payload["notes"]:
            return status("no_person_evidence")
        payload = initial_behavior.build_payload(persona, report, cached_research(persona, report), sar)
        parsed = interpret(payload)
        prior = compile_person(parsed["core"], parsed["context"], payload, persona, sar, default)
        prior.initial_interpretation["model"] = settings.kexaone_model
        prior.initial_interpretation["semantic_review"] = "original_evidence_rechecked_not_clinical_validation"
        return prior
    except Exception as exc:
        # Provider exception strings can contain content. Keep only the exception type.
        log.warning("K initial interpretation failed: %s", type(exc).__name__)
        return status("fallback_to_sar", error_type=type(exc).__name__)


def _empty_context(payload, reason):
    """Stored-form context with no personal claim, for a missing or failed context task."""
    ctx = {"persistence": {"evidence": "missing", "pattern": "unresolved", "value": "unknown",
                           "note_ids": [], "explanation": reason},
           "environment": {f: {"response": "unknown", "condition": "조건 미확인", "note_ids": [],
                               "scope": "unknown", "explanation": reason}
                           for f in ("water", "forest", "park", "market")}}
    if payload["incident"].get("status") == "not_reported":
        ctx["baseline_direction"] = {"value": "unknown", "note_ids": []}
    return ctx


def interpret(payload):
    """At most four logged K requests; used asynchronously before an incident.

    Core and context drafts are independent; each is re-judged against the guardian's
    notes. The core review replaces its draft. Context claims reach the engine only when
    draft and review agree, because a lone context reading produced most engine-visible
    errors (v47) and a review alone added new ones (v48 dev). Claims without a cited note
    are dropped item by item instead of voiding the preparation; every drop, disagreement
    and fallback is kept in the returned audit.
    """
    base = settings.kexaone_base_url.rstrip("/")
    url = base if base.endswith("/chat/completions") else base + (
        "/chat/completions" if base.endswith("/v1") else "/v1/chat/completions")
    run_id = "initial-person:" + str(uuid.uuid4())
    audit = {"dropped": [], "context_disagreements": [], "fallbacks": []}

    def call(role, body):
        return logged_json_request(url, body,
            headers={"Authorization": "Bearer " + settings.kexaone_api_key, "Content-Type": "application/json"},
            provider="FriendliAI", model=settings.kexaone_model, role=role,
            run_id=run_id, logical_request_id=run_id + ":" + role, timeout=settings.kexaone_timeout,
            ledger_path=settings.research_usage_ledger_path, max_started=4)

    def checked(contract, cleaner, role, body):
        response = call(role, body)
        choice = response["choices"][0]
        if choice.get("finish_reason") == "stop":
            z, dropped = cleaner(initial_behavior.decode_json_content(choice["message"].get("content")), payload)
            audit["dropped"] += [{**d, "task": role} for d in dropped]
            response = {"choices": [{"finish_reason": "stop",
                                     "message": {"content": json.dumps(z, ensure_ascii=False)}}]}
        return contract.validate(response, payload)

    def attempt(fn):
        try:
            return fn()
        except Exception as exc:  # type only; provider text can contain personal content
            return exc

    model = settings.kexaone_model
    with ThreadPoolExecutor(max_workers=2) as pool:
        core_f = pool.submit(attempt, lambda: checked(person_evidence, person_evidence.soft_clean,
            "initial_person_core", person_evidence.request(payload, model)))
        ctx_f = pool.submit(attempt, lambda: checked(person_scope, person_scope.soft_clean,
            "initial_person_context", person_scope.request(payload, model)))
        core_draft, ctx_draft = core_f.result(), ctx_f.result()
    for name, value in (("core_draft", core_draft), ("context_draft", ctx_draft)):
        if isinstance(value, Exception):
            audit["fallbacks"].append(f"{name}_failed:{type(value).__name__}")

    def review_core():
        draft = {} if isinstance(core_draft, Exception) else core_draft
        context = None if isinstance(ctx_draft, Exception) else ctx_draft
        return checked(person_audit, person_evidence.soft_clean, "initial_person_semantic_audit",
                       person_audit.request(payload, draft, model, context=context))

    def review_context():
        return checked(person_scope, person_scope.soft_clean, "initial_person_context_review",
                       person_scope.review_request(payload, ctx_draft, model))

    with ThreadPoolExecutor(max_workers=2) as pool:
        core_r = pool.submit(attempt, review_core)
        ctx_r = None if isinstance(ctx_draft, Exception) else pool.submit(attempt, review_context)
        core_review = core_r.result()
        ctx_review = ctx_r.result() if ctx_r else None

    if not isinstance(core_review, Exception):
        core = core_review
    elif not isinstance(core_draft, Exception):
        audit["fallbacks"].append(f"core_review_failed:{type(core_review).__name__}")
        core = core_draft
    else:
        raise core_review
    if isinstance(ctx_draft, Exception):
        context = _empty_context(payload, "조건 과업 실패로 미확인.")
    elif ctx_review is None or isinstance(ctx_review, Exception):
        audit["fallbacks"].append("context_review_failed" + (f":{type(ctx_review).__name__}" if ctx_review else ""))
        context, disagreements = person_scope.agree(ctx_draft, _empty_context(payload, "재검토 실패로 적용 보류."))
        audit["context_disagreements"] = [{**d, "cause": "no_second_reading"} for d in disagreements]
    else:
        context, audit["context_disagreements"] = person_scope.agree(ctx_draft, ctx_review)
    return {"core": core, "context": context, "audit": audit}

"""SAR/RAG baseline + K interpretation of the person → existing simulation inputs.

Independent K tasks read the same source notes. Only code generates numeric factors.
No retries. Each request is reserved and logged before network IO. No production toggle:
configured credentials enable the candidate; provider/contract failures remain visible.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
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


def interpret(payload):
    """Four logged K requests; used asynchronously before an incident.

    Core and context drafts are independent. Each draft is then re-judged against the
    guardian's original notes before anything reaches the engine; the context review
    exists because unreviewed context drafts produced most engine-visible errors (v47).
    """
    base = settings.kexaone_base_url.rstrip("/")
    url = base if base.endswith("/chat/completions") else base + (
        "/chat/completions" if base.endswith("/v1") else "/v1/chat/completions")
    run_id = "initial-person:" + str(uuid.uuid4())

    def call(role, body):
        return logged_json_request(url, body,
            headers={"Authorization": "Bearer " + settings.kexaone_api_key, "Content-Type": "application/json"},
            provider="FriendliAI", model=settings.kexaone_model, role=role,
            run_id=run_id, logical_request_id=run_id + ":" + role, timeout=settings.kexaone_timeout,
            ledger_path=settings.research_usage_ledger_path, max_started=4)

    drafts = {"core": (person_evidence, "initial_person_core"),
              "context": (person_scope, "initial_person_context")}

    def draft(item):
        group, (contract, role) = item
        return group, contract.validate(call(role, contract.request(payload, settings.kexaone_model)), payload)

    with ThreadPoolExecutor(max_workers=2) as pool:
        parsed = dict(pool.map(draft, drafts.items()))

    def review_core():
        body = person_audit.request(payload, parsed['core'], settings.kexaone_model, context=parsed['context'])
        return person_audit.validate(call("initial_person_semantic_audit", body), payload)

    def review_context():
        body = person_scope.review_request(payload, parsed['context'], settings.kexaone_model)
        return person_scope.validate(call("initial_person_context_review", body), payload)

    with ThreadPoolExecutor(max_workers=2) as pool:
        core, context = pool.submit(review_core), pool.submit(review_context)
        return {"core": core.result(), "context": context.result()}

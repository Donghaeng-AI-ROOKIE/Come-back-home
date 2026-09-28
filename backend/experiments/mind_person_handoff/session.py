"""Wire actual Persona/K preparation to the persistent KINTEX walker.

The old production dem5 prompt and calibrated radius path remain unchanged.
This factory is an explicit candidate entry point for offline and approved live
comparisons, not evidence that the production predictor runs this executor.
"""
from app.llm.mind_handoff import DecisionProvider, context_for, validate_decision
from experiments.mind_upgrade.runtime import WalkingSession


def create_session(net, persona, prior, start, started_at, *, request, model,
                   provider, policy, **kwargs):
    return WalkingSession(
        net, persona, prior, start, started_at,
        DecisionProvider(request, model=model, provider=provider),
        policy=policy, context_builder=context_for,
        decision_validator=validate_decision, **kwargs)

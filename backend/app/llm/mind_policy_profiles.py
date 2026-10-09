"""Explicit server-side interpreter selection; never selected by client input."""
from app.config import settings
from app.llm import mind_policy_candidate, mind_policy_guarded_core


def selected():
    return {'sourced_followup': mind_policy_candidate,
            'guarded_core': mind_policy_guarded_core}[settings.mind_policy_contract]

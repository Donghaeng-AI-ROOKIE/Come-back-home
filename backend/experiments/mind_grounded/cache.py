"""Exact-context reuse: unmatched conditions return a visible budget miss.

No keyword interpretation or cross-person pool sampling. This research executor
does not claim approximate reuse is validated. The caller supplies the provider.
"""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import threading
from .contract import validate


class MindBudgetExhausted(RuntimeError):
    pass


@dataclass(frozen=True)
class Resolution:
    output: dict
    source: str
    context_sha256: str


def context_key(context, model_revision):
    value={'model_revision':model_revision, 'context':context}
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


class GroundedBudget:
    def __init__(self, limit, provider, model_revision):
        if type(limit) is not int or limit < 0:
            raise ValueError('limit must be a non-negative integer')
        self.limit,self.provider,self.revision=limit,provider,model_revision
        self.attempts=0;self.cache={};self.events=[];self.lock=threading.Lock()

    def resolve(self, context):
        key=context_key(context,self.revision)
        with self.lock:
            if key in self.cache:
                self.events.append({'key':key,'source':'exact_cache'})
                return Resolution(deepcopy(self.cache[key]),'exact_cache',key)
            if self.attempts>=self.limit:
                self.events.append({'key':key,'source':'budget_exhausted'})
                raise MindBudgetExhausted('No validated result for this exact context')
            self.attempts+=1
            try:
                value=self.provider(deepcopy(context));validate(value,context)
            except Exception:
                self.events.append({'key':key,'source':'provider_or_validation_error'})
                raise
            self.cache[key]=deepcopy(value)
            self.events.append({'key':key,'source':'provider'})
            return Resolution(deepcopy(value),'provider',key)

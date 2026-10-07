"""D8's concise contract with explicit non-thinking, neutral-penalty generation."""
from experiments.mind_contract_ab_20261007 import contract_d8 as d8
RELEASE_QUALIFIED = False
VERSION = 'd11-d8-nonthinking-neutral-penalties-20261008-research'
SAMPLING = dict(d8.SAMPLING, presence_penalty=0.0, repetition_penalty=1.0)
compile_d11 = d8.compile_d8
trait_accounting = d8.trait_accounting
correction = d8.correction


def request(personal, model):
    body = d8.request(personal, model, thinking=False, constrained=True)
    body.update(SAMPLING)
    return d8._bounded(body)

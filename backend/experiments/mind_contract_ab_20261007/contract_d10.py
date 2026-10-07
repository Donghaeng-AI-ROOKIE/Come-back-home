"""D4's source contract with explicit non-thinking, neutral-penalty generation."""
from experiments.mind_contract_ab_20261007 import contract_d4 as d4, contract_d8 as d8
RELEASE_QUALIFIED = False
VERSION = 'd10-d4-nonthinking-neutral-penalties-20261008-research'
SAMPLING = dict(d4.SAMPLING, presence_penalty=0.0, repetition_penalty=1.0)
compile_d10 = d4.compile_d4
trait_accounting = d4.trait_accounting
correction = d8.correction


def request(personal, model):
    body = d4.request(personal, model, thinking=False)
    body.update(SAMPLING)
    return d8._bounded(body)

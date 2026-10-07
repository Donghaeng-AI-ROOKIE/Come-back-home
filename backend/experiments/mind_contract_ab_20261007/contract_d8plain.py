"""Exactly D8 prompt/validation; only API constrained decoding is removed."""
from experiments.mind_contract_ab_20261007 import contract_d8 as d8

RELEASE_QUALIFIED = False
VERSION = 'contract-d8-plain-decoding-20261008-research'
SAMPLING = dict(d8.SAMPLING)
schema = d8.schema
compile_d8plain = d8.compile_d8
trait_accounting = d8.trait_accounting
correction = d8.correction


def request(personal, model, *, thinking=True):
    return d8.request(personal, model, thinking=thinking, constrained=False)

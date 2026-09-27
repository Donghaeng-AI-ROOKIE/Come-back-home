import hashlib
import pytest
from experiments.literature_targeting_20260924.evidence_hash import matches_text_digest


@pytest.mark.parametrize("actual,original", [(b'a\nb\n', b'a\r\nb\r\n'), (b'a\r\nb\r\n', b'a\nb\n'), (b'a\nb\n', b'a\nb\n')])
def test_checkout_line_endings_preserve_frozen_evidence(tmp_path, actual, original):
    p = tmp_path / 'input.json'
    p.write_bytes(actual)
    assert matches_text_digest(p, hashlib.sha256(original).hexdigest())


@pytest.mark.parametrize("changed", [b'a\nCHANGED\n', b'a\nb', b'a\r\nb\n', b'a\rb\n'])
def test_content_and_mixed_line_endings_are_not_accepted(tmp_path, changed):
    p = tmp_path / 'input.json'
    p.write_bytes(changed)
    assert not matches_text_digest(p, hashlib.sha256(b'a\nb\n').hexdigest())

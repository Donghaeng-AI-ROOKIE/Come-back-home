"""Verify frozen text bytes across Git LF/CRLF checkout conversion.

Never update the recorded digest or canonicalize JSON/content. Only whole-file
newline conversion is accepted; graph/binary files must use exact byte hashes.
"""
import hashlib
from pathlib import Path


def matches_text_digest(path: Path, expected: str) -> bool:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() == expected:
        return True
    lf = raw.replace(b"\r\n", b"\n")
    # Reject lone CR and mixed styles rather than silently repairing content.
    if b"\r" in lf or (b"\r\n" in raw and raw.count(b"\n") != raw.count(b"\r\n")):
        return False
    return any(hashlib.sha256(data).hexdigest() == expected
               for data in (lf, lf.replace(b"\n", b"\r\n")))

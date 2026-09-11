"""Whole-file inverses to the accepted offered-summary physical recipe."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
UNBOUND = 'UNBOUND_PENDING_ACCEPTED_DESTINATION_ACTUAL'
ACTUAL_MANIFEST = '183a0ccce954efc48d30f598d4965459695e756e20e8ca32ba47c7ee21bf3363'
CASES = json.loads((HERE/'recipes.json').read_text())

def recipe(kind):
    case = CASES[kind]
    raw = (HERE/case['reference']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != case['sha256']:
        raise ValueError('original reference identity')
    original = raw.decode()
    text = original
    for (old, new), count in zip(case['edits'], case['counts'], strict=True):
        if text.count(old) != count or new in text:
            raise ValueError('forward literal anchor')
        text = text.replace(old, new)
    return ROOT/case['target'], original, text, list(zip(case['edits'], case['counts'], strict=True))

def inverse(kind, candidate):
    _, original, _, edits = recipe(kind)
    for (old, new), count in reversed(edits):
        if candidate.count(new) != count:
            raise ValueError('inverse literal count')
        candidate = candidate.replace(new, old)
    if candidate != original:
        raise ValueError('whole-source inverse')
    return candidate

if __name__ == '__main__':
    for kind in CASES:
        path, _, expected, _ = recipe(kind)
        if path.read_text() != expected:
            raise ValueError('derived source changed')
        inverse(kind, path.read_text())
        print(kind, hashlib.sha256(path.read_bytes()).hexdigest())

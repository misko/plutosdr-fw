from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from record_product_publication_cone_evidence import same_audit


def test_json_context_roundtrip():
    same_audit({'contexts': [('0', '4178')], 'words': 64512}, {'words': 64512, 'contexts': [['0', '4178']]})


def test_changed_numerical_audit_rejected():
    with pytest.raises(ValueError):
        same_audit({'contexts': [('0', '4178')], 'words': 64512}, {'contexts': [['0', '4179']], 'words': 64512})

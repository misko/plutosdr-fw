"""Same delay stimulus on original and cofactored publication permissions."""
import sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import product_local_framing_experiment_v2 as candidate

def test_exact_stimulus_mirror():
    original="before;force dut.product_commit_authorized=1'b0;middle;release dut.product_commit_authorized;after;"
    changed=candidate.mirror_publication_delay(original)
    assert changed==original.replace("force dut.product_commit_authorized=1'b0;","force dut.product_commit_authorized=1'b0;force dut.product_other_commit_authorized=1'b0;").replace("release dut.product_commit_authorized;","release dut.product_commit_authorized;release dut.product_other_commit_authorized;")
@pytest.mark.parametrize('text',["", "force dut.product_commit_authorized=1'b0;","force dut.product_commit_authorized=1'b0;release dut.product_commit_authorized;release dut.product_commit_authorized;"])
def test_unexpected_stimulus_inventory_rejected(text):
    with pytest.raises(ValueError):candidate.mirror_publication_delay(text)
def test_smoke_includes_original_delay_and_new_cases():
    text=(ROOT/'tools/product_local_framing_smoke_v2.py').read_text()
    assert 'auxiliary_active=1;product_retirement_boundary(0);run_product_local_framing_boundaries;' in text
def test_v2_only_adds_same_publication_delay():
    old=(ROOT/'tools/product_local_framing_experiment.py').read_text()
    new=Path(candidate.__file__).read_text()
    start=new.index('\ndef mirror_publication_delay(');end=new.index('\ndef prepare(',start)
    new=new[:start]+new[end:]
    new=new.replace("    if auxiliary:bench=mirror_publication_delay(bench)\n","",1)
    assert new.rstrip()==old.rstrip()

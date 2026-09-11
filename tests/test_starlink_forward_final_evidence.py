"""The new exact-current witness cannot be missing, duplicated or vacuous."""
from pathlib import Path
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from route_forward_final_commit import witness

GOOD='STAGED_FORWARD_FINAL_PASS checks=1000 accepts=18 exact_current=1 inverse_unchanged=1\n'

def test_valid_witness():
    assert witness(GOOD)=={'checks':1000,'accepts':18,'exact_current':True,'inverse_unchanged':True}

@pytest.mark.parametrize('bad',['',GOOD+GOOD,GOOD.replace('1000','999'),GOOD.replace('18','17'),
    GOOD.replace('exact_current=1','exact_current=0'),GOOD.replace('inverse_unchanged=1','inverse_unchanged=0')])
def test_invalid_witness_rejected(bad):
    with pytest.raises(ValueError):witness(bad)

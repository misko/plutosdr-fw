"""Reject missing, changed, duplicated and vacuous sticky-fault evidence."""
from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from route_distributed_sticky_fault import witness

GOOD='STAGED_STICKY_FAULT_PASS checks=1000 events=10 resets=10 seen=7ffff scalar_exact=1 same_edge=1\n'

def test_valid_witness():
    assert witness(GOOD)=={'checks':1000,'events':10,'resets':10,'seen':0x7ffff,'scalar_exact':True,'same_edge':True}

@pytest.mark.parametrize('bad',['',GOOD+GOOD,GOOD.replace('1000','999'),GOOD.replace('events=10','events=0'),
    GOOD.replace('resets=10','resets=0'),GOOD.replace('7ffff','00000'),GOOD.replace('7ffff','fffff'),
    GOOD.replace('scalar_exact=1','scalar_exact=0'),GOOD.replace('same_edge=1','same_edge=0')])
def test_invalid_witness_rejected(bad):
    with pytest.raises(ValueError):witness(bad)

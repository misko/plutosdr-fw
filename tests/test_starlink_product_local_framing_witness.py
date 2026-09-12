"""Reject incomplete or inconsistent local-framing actual boundary witnesses."""
import sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import product_local_framing_experiment as experiment
GOOD='PRODUCT_LOCAL_FRAMING_PASS checks=20000 publications=24 local_rejections=6 actual_request_exact=1\n'
GOOD+=''.join(f'PRODUCT_LOCAL_FRAMING_BOUNDARY_PASS boundary={n} fresh_reads=512 fresh_releases=1\n' for n in range(6))
GOOD+='PRODUCT_LOCAL_FRAMING_BOUNDARIES_PASS cases=6 local_checks=1 both_resets=1\n'

def test_full_local_boundary_witness():
    assert experiment.witness(GOOD,True)==dict(checks=20000,publications=24,local_rejections=6,auxiliary=True)

@pytest.mark.parametrize('before,after',[
    ('checks=20000','checks=9999'),('publications=24','publications=17'),
    ('local_rejections=6','local_rejections=5'),('actual_request_exact=1','actual_request_exact=0'),
    ('boundary=5','boundary=4'),('boundary=0','boundary=9'),
    ('fresh_reads=512','fresh_reads=511'),('fresh_releases=1','fresh_releases=0'),
    ('cases=6','cases=5'),('local_checks=1','local_checks=0'),('both_resets=1','both_resets=0'),
    ('PRODUCT_LOCAL_FRAMING_PASS','ERROR PRODUCT_LOCAL_FRAMING_PASS'),
    ('PRODUCT_LOCAL_FRAMING_PASS','Fatal: PRODUCT_LOCAL_FRAMING_PASS'),
])
def test_bad_boundary_witness_rejected(before,after):
    with pytest.raises(ValueError):experiment.witness(GOOD.replace(before,after,1),True)

def test_duplicate_summary_rejected():
    with pytest.raises(ValueError):experiment.witness(GOOD+GOOD.splitlines()[0]+'\n',True)

def test_missing_boundary_rejected():
    with pytest.raises(ValueError):
        experiment.witness('\n'.join(x for x in GOOD.splitlines() if 'boundary=5 ' not in x)+'\n',True)

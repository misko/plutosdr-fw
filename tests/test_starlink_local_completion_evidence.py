from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import local_completion_experiment as local
import local_completion_boundaries as boundaries

GOOD='LOCAL_COMPLETION_PASS checks=10000 owned=36 permits=36 private_differences=100 original_authority_exact=1 public_veto_unchanged=1\n'

def test_complete_reference_marker():
    assert local.witness(GOOD)['checks']==10000

@pytest.mark.parametrize('log',['',GOOD+GOOD,GOOD+'FATAL error\n',GOOD.replace('checks=10000','checks=9999'),
    GOOD.replace('owned=36','owned=35'),GOOD.replace('permits=36','permits=35'),
    GOOD.replace('private_differences=100','private_differences=99'),
    GOOD.replace('original_authority_exact=1','original_authority_exact=0'),
    GOOD.replace('public_veto_unchanged=1','public_veto_unchanged=0')])
def test_reference_marker_rejects_incomplete(log):
    with pytest.raises(ValueError):local.witness(log)

BOUNDARIES=''.join(f'LOCAL_COMPLETION_BOUNDARY_PASS boundary={n} phase={n//3 if n<6 else 1 if n>=8 else 0} cancelled_reuse=0 fresh_reads=512 fresh_releases=1\n' for n in range(10))
BOUNDARIES+='LOCAL_COMPLETION_BOUNDARIES_PASS cases=10 current_fault_fenced=1 fresh_recovery=1\n'

def test_complete_boundaries_marker():
    assert boundaries.witness(BOUNDARIES)['cases']==10

@pytest.mark.parametrize('line',range(11))
def test_each_missing_boundary_rejected(line):
    lines=BOUNDARIES.splitlines(True);del lines[line]
    with pytest.raises(ValueError):boundaries.witness(''.join(lines))

@pytest.mark.parametrize('log',[BOUNDARIES+BOUNDARIES,BOUNDARIES+'FATAL\n',
    BOUNDARIES.replace('cancelled_reuse=0','cancelled_reuse=1',1),
    BOUNDARIES.replace('fresh_reads=512','fresh_reads=511',1)])
def test_incomplete_or_duplicate_boundaries_rejected(log):
    with pytest.raises(ValueError):boundaries.witness(log)

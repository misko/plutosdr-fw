"""Nonvacuous observer markers and additive-only prepared bench assembly."""
from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from forward_return_bank_experiment import witness, PARENT, HEADER, REPORT, RTL, FRAGMENT

GOOD='FORWARD_RETURN_ACTUAL_PASS blocks=18 words=9216 reservations=21 seals=20 stalls=100 runtime_unchanged=1 observer_only=1\n'

def test_valid_witness():
    assert witness(GOOD)['blocks']==18

@pytest.mark.parametrize('bad',['',GOOD+GOOD,GOOD.replace('blocks=18','blocks=17'),
    GOOD.replace('words=9216','words=9000'),GOOD.replace('reservations=21','reservations=19'),
    GOOD.replace('seals=20','seals=17'),GOOD.replace('stalls=100','stalls=99'),
    GOOD.replace('observer_only=1','observer_only=0'),GOOD.replace('runtime_unchanged=1','runtime_unchanged=0')])
def test_incomplete_or_changed_witness_rejected(bad):
    with pytest.raises(ValueError):witness(bad)

def test_prepared_observer_does_not_change_runtime_or_reference_stimulus():
    prepared=Path('/dev/shm/starlink-forward-return.FEyGL1Bw/prepared-v2')
    original=(PARENT/'tb_fft_staged_output.sv').read_text()
    candidate=(prepared/'tb_fft_staged_output.sv').read_text()
    observer=(RTL/FRAGMENT).read_text()
    assert candidate.count(observer)==1
    assert candidate.replace('\n'+observer+'\nendmodule','\nendmodule',1).replace(
        REPORT+'      report_forward_return_observer;\n',REPORT,1)==original
    assert candidate.index(observer)>candidate.index('reg clk=')
    profile=(prepared/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    assert len(profile)==23
    for name in profile:
        if name!='starlink_pss_forward_return_bank.v':
            assert (prepared/name).read_bytes()==(PARENT/name).read_bytes(),name

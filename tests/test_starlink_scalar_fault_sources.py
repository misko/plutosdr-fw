"""Preserve the scalar register/CDC boundary; change only its checked input."""
from pathlib import Path
import re
import pytest
from tests import test_starlink_distributed_sticky_fault as contract

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
PARENT=Path('/dev/shm/starlink-sticky-fault.4qIKHja5/prepared-v1')
TOP='starlink_pss_fft_staged_output_impl.v'
PARENT_TEXT=(PARENT/TOP).read_text()
PARENT_BLOCK=re.search(r'  // BEGIN DISTRIBUTED STICKY FAULT\n.*?  // END DISTRIBUTED STICKY FAULT\n',PARENT_TEXT,re.S)[0]
SOURCES=re.search(r'  wire \[18:0\] sticky_fault_sources =.*?;\n',PARENT_BLOCK,re.S)[0]
NEW="""  // BEGIN SCALAR FAULT SOURCES
  // Flatten the checked cause expression BEFORE the original scalar register.
  // Keep its original synchronous reset, capture edge and direct CDC source.
  // Current publication vetoes and unsupported/unknown fallback are unchanged.
"""+SOURCES+"""  always @(posedge fft_clk)
    if (!fast_running) fast_fault <= 0;
    else if (|sticky_fault_sources) fast_fault <= 1;
  // END SCALAR FAULT SOURCES
"""

def undo_top(text):
    if '// BEGIN SCALAR FAULT SOURCES' not in text:return text
    assert text.count(NEW)==1
    text=text.replace(NEW,PARENT_BLOCK,1)
    line='  reg fast_fault;\n'
    assert text.count(line)==1
    return text.replace(line,'  wire fast_fault; // DISTRIBUTED STICKY FAULT OUTPUT\n',1)

def test_exact_scalar_register_delta():
    names=(PARENT/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    assert len(names)==22
    changed=[]
    for name in names:
        if not (RTL/name).exists():continue
        text=(RTL/name).read_text()
        if text!=(PARENT/name).read_text():changed.append(name)
        assert (undo_top(text) if name==TOP else text)==(PARENT/name).read_text(),name
    assert changed==[TOP]
    for name,path in [('tb_fft_staged_output.sv',RTL/'tb_fft_staged_output.sv'),
                      ('staged_fft_experiment.py',ROOT/'tools/staged_fft_experiment.py'),
                      ('staged_fft_experiment.tcl',ROOT/'tools/staged_fft_experiment.tcl')]:
        assert path.read_bytes()==(PARENT/name).read_bytes()

def test_actual_scalar_capture_fourstate(tmp_path):
    result=contract.run(tmp_path,scalar=True)
    assert result.returncode==0 and 'DISTRIBUTED_STICKY_CONTRACT_PASS checks=313297' in result.stdout,result.stdout+result.stderr

@pytest.mark.parametrize('mutation',['reset','not_sticky','skip_first','skip_last','context','fallback'])
def test_scalar_capture_mutants_rejected(tmp_path,mutation):
    result=contract.run(tmp_path,mutation,scalar=True)
    assert result.returncode!=0 and 'mismatch' in result.stdout,result.stdout+result.stderr

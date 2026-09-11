"""Reject incomplete numerical and fault evidence, independently of Vivado exit."""
from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import buffered_forward_experiment as main
from buffered_forward_auxiliary import witness, augment, FRAGMENT

GOOD=''.join(f'BUFFERED_FAULT_PASS case={n} rejected_publications=0 fresh_reads=512 fresh_releases=1\n' for n in range(6))
GOOD+=''.join(f'BUFFERED_RESET_PASS boundary={b} side={s} stale_outputs=0 fresh_reads=512 fresh_releases=1\n' for b in range(4) for s in range(2))
GOOD+=''.join(f'BUFFERED_DELAY_PASS case={n} fresh_reads=512 replay=512 products=512\n' for n in range(2))
GOOD+='BUFFERED_AUX_PASS faults=6 resets=8 delays=2 fresh_recovery=1 actual_fft=1\n'

def test_complete_auxiliary_marker():
    assert witness(GOOD)==dict(fault_cases=6,reset_boundaries=8,delays=2,fresh_recovery=True,actual_fft=True)

@pytest.mark.parametrize('line',range(17))
def test_each_missing_auxiliary_case_fails(line):
    lines=GOOD.splitlines(True);del lines[line]
    with pytest.raises(ValueError):witness(''.join(lines))

@pytest.mark.parametrize('log',[GOOD+GOOD,GOOD+'FATAL injected\n',GOOD.replace('fresh_reads=512','fresh_reads=511',1),
                              GOOD.replace('rejected_publications=0','rejected_publications=1',1)])
def test_duplicate_failure_or_incomplete_recovery_fails(log):
    with pytest.raises(ValueError):witness(log)

def test_auxiliary_preserves_runtime_and_numeric_bench():
    original=(main.RTL/'tb_fft_buffered_forward.sv').read_text()
    fragment=FRAGMENT.read_text();derived=augment(original,fragment)
    assert derived.count(fragment)==1
    assert derived.index(fragment)>derived.index('reg clk=')
    assert 'run_buffered_auxiliary;' in derived
    assert original.count('log_word(')==derived.replace(fragment,'').count('log_word(')

ACTUAL=Path('/dev/shm/starlink-buffered-forward.mZfKEBtK/actual-v1')
SIM=Path('project/staged_fft.sim/sim_1/behav/xsim')

def test_reaudit_all_actual_numerical_words():
    assert main.audit(ACTUAL)['numerical_words']==64512

@pytest.mark.parametrize('mutation',['missing_word','duplicate_word','wrong_value','wrong_exponent','unknown_context'])
def test_corrupted_numerical_receipt_rejected(tmp_path,mutation):
    folder=tmp_path/SIM;folder.mkdir(parents=True)
    (folder/'simulate.log').write_bytes((ACTUAL/SIM/'simulate.log').read_bytes())
    rows=(ACTUAL/SIM/'buffered_words.csv').read_text().splitlines(True)
    if mutation=='missing_word':rows.pop()
    elif mutation=='duplicate_word':rows.append(rows[-1])
    else:
        row=rows[1].strip().split(',')
        if mutation=='wrong_value':row[4]=format(int(row[4],16)^1,'012x')
        elif mutation=='wrong_exponent':row[5]=format(int(row[5],16)^1,'03x')
        else:row[0]='6'
        rows[1]=','.join(row)+'\n'
    (folder/'buffered_words.csv').write_text(''.join(rows))
    with pytest.raises(ValueError):main.audit(tmp_path)

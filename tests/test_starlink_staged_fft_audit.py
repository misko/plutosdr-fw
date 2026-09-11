"""Reject corrupted/missing actual receipts; these are parser tests, not RF."""
import importlib.util
from pathlib import Path
import shutil

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('staged_fft_experiment_audit',ROOT/'tools/staged_fft_experiment.py')
experiment=importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)
ACTUAL=ROOT.parent/'staged-output-actual-v5'
SIM='project/staged_fft.sim/sim_1/behav/xsim'

@pytest.fixture
def recorded(tmp_path):
    source=ACTUAL/SIM
    assert experiment.sha(source/'staged_words.csv')=='c35159d51b2ebdda97287ac9557a096da1931c0ced38911f8f142ec67d7a4f8b'
    destination=tmp_path/SIM;destination.mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:shutil.copyfile(source/name,destination/name)
    return tmp_path,destination

def test_complete_actual_numerical_receipt(recorded):
    output,_=recorded
    result=experiment.audit_sim(output)
    assert result['numerical_rows']==43008 and result['actual_fft'] and not result['physical_signoff']

@pytest.mark.parametrize('change',['fatal','missing_context','deadline','missing_word','duplicate_word','data','exponent','context'])
def test_corrupted_actual_receipts_are_rejected(recorded,change):
    output,sim=recorded
    if change in {'fatal','missing_context','deadline'}:
        path=sim/'simulate.log';text=path.read_text()
        if change=='fatal':text+='\nFatal: deliberately injected parser control\n'
        elif change=='missing_context':
            text='\n'.join(line for line in text.splitlines() if not line.startswith('STAGED_FFT_CONTEXT_PASS mode=1 '))+'\n'
        else:
            assert 'max_service=3655' in text
            text=text.replace('max_service=3655','max_service=5216',1)
        path.write_text(text)
    else:
        path=sim/'staged_words.csv';lines=path.read_text().splitlines()
        if change=='missing_word':lines.pop()
        elif change=='duplicate_word':lines.append(lines[1])
        else:
            fields=lines[1].split(',')
            if change=='data':fields[4]=f'{int(fields[4],16)^1:012x}'
            elif change=='exponent':fields[5]=f'{int(fields[5],16)^1:03x}'
            else:fields[0]='4'
            lines[1]=','.join(fields)
        path.write_text('\n'.join(lines)+'\n')
    with pytest.raises(ValueError):experiment.audit_sim(output)

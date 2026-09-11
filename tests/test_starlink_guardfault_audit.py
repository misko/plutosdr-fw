"""Reject incomplete or weakened exact guard-facing fault evidence."""
import importlib.util
from pathlib import Path
import re
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('guardfault_experiment', ROOT/'tools/staged_fft_experiment.py')
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)
SIM = 'project/staged_fft.sim/sim_1/behav/xsim'


@pytest.fixture
def recorded(tmp_path):
    sim = tmp_path/SIM
    sim.mkdir(parents=True)
    for name in ['simulate.log', 'staged_words.csv']:
        shutil.copyfile(ROOT.parent/'staged-guardfault-actual-v1'/SIM/name, sim/name)
    return tmp_path, sim


def test_complete_guardfault_evidence(recorded):
    root, _ = recorded
    result = experiment.audit_guardfault_sim(root)
    assert result['numerical_rows'] == 64512
    assert result['guardfault']['exact_accumulation']
    assert result['guardfault']['alias_checked']
    assert len(result['guardfault']['boundaries']) == 5
    assert min(result['guardfault']['cycles']) >= 1000
    assert not result['physical_signoff'] and not result['continuous_rx']


@pytest.mark.parametrize('change', [
    'missing_case', 'missing_terminal', 'missing_cycles', 'owner0', 'owner1',
    'unknown', 'absorption', 'release', 'accumulation',
])
def test_incomplete_guardfault_evidence_rejected(recorded, change):
    root, sim = recorded
    path = sim/'simulate.log'
    text = path.read_text()
    if change.startswith('missing_'):
        prefix = {'missing_case': 'STAGED_GUARDFAULT_CASE_PASS boundary=1 ',
                  'missing_terminal': 'STAGED_GUARDFAULT_PASS ',
                  'missing_cycles': 'STAGED_GUARDFAULT_CYCLES_PASS '}[change]
        assert any(line.startswith(prefix) for line in text.splitlines())
        text = '\n'.join(line for line in text.splitlines() if not line.startswith(prefix))+'\n'
    elif change in ('owner0', 'owner1'):
        text, count = re.subn(r'(?m)^(STAGED_GUARDFAULT_CYCLES_PASS .*?'+change+r'=)\d+', r'\g<1>999', text)
        assert count == 1
    else:
        before, after = {
            'unknown': ('boundary=2 input_fault_unknown=1', 'boundary=2 input_fault_unknown=0'),
            'absorption': ('boundary=1 input_fault_unknown=0 cutover_difference=1', 'boundary=1 input_fault_unknown=0 cutover_difference=0'),
            'release': ('boundary=4 input_fault_unknown=0 cutover_difference=0 reads=0 releases=0', 'boundary=4 input_fault_unknown=0 cutover_difference=0 reads=0 releases=1'),
            'accumulation': ('exact_accumulation=1 alias_checked=1', 'exact_accumulation=0 alias_checked=1'),
        }[change]
        assert before in text
        text = text.replace(before, after, 1)
    path.write_text(text)
    with pytest.raises(ValueError):
        experiment.audit_guardfault_sim(root)

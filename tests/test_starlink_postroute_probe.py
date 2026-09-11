"""No Vivado subprocess: immutable recipe and report/provenance boundaries."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
spec=importlib.util.spec_from_file_location('postroute_probe',ROOT/'tools/probe_staged_postroute.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
sys.path.pop(0)

def test_only_physical_step_changes():
    base=(ROOT/'tools/retained_destination_synthesis/route_retained_output.tcl').read_text()
    result=probe.recipe(base)
    assert result.count(probe.NEW_STEPS)==1
    assert result.replace(probe.NEW_STEPS,probe.OLD_STEPS)==base
    assert 'set_false_path' not in result and 'set_multicycle_path' not in result

@pytest.mark.parametrize('bad',['','  route_design\n','# altered\n'])
def test_changed_base_rejected(bad):
    with pytest.raises(ValueError,match='frozen base'):probe.recipe(bad)

@pytest.mark.parametrize('candidate',sorted(probe.PARENTS))
def test_parent_readonly_reaudit(candidate):
    parent=ROOT.parent/f'staged-{candidate}-route-v1'
    before=(parent/'audit.json').read_bytes()
    assert probe.audit(parent,record=False)==json.loads(before)
    assert (parent/'audit.json').read_bytes()==before
    assert probe.sha(parent/'route/retained_output_routed.dcp')==probe.PARENTS[candidate]
    report_only=probe.summarize(parent/'route')
    assert not report_only['source_and_checkpoint_verified']
    assert not report_only['deployment_eligible']

def test_constraint_normalization_keeps_commands(tmp_path):
    path=tmp_path/'test.xdc'
    path.write_text('# generated header\n\n create_clock -period 5.714 clk\n')
    assert probe.constraints(path)=='create_clock -period 5.714 clk'
    path.write_text('create_clock -period 6 clk\n')
    assert probe.constraints(path)!='create_clock -period 5.714 clk'

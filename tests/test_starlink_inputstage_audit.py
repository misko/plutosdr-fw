"""Fail-closed evidence controls using the actual integrated V2 run."""
import importlib.util
import hashlib
from pathlib import Path
import shutil

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('inputstage_experiment',ROOT/'tools/staged_fft_experiment.py')
experiment=importlib.util.module_from_spec(spec);spec.loader.exec_module(experiment)
ACTUAL=ROOT.parent/'staged-inputidentity-actual-v2'
SIM=Path('project/staged_fft.sim/sim_1/behav/xsim')


def test_v2_runtime_unchanged_and_bench_only_adds_boundaries():
    first=ROOT.parent/'staged-inputidentity-prepared-v1'
    second=ROOT.parent/'staged-inputidentity-prepared-v2'
    assert hashlib.sha256((first/'SHA256SUMS').read_bytes()).hexdigest()=='f7b174267326f92800ee27b4cbd518def346fd1cd73dcd56b188b0b2bb051007'
    names=(first/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    assert len(names)==19
    for name in names:assert (first/name).read_bytes()==(second/name).read_bytes(),name
    old=(first/'tb_fft_staged_output.sv').read_text()
    new=(second/'tb_fft_staged_output.sv').read_text()
    start=new.index('  task automatic input_stage_boundary(')
    end=new.index('  endtask\n',start)+len('  endtask\n')
    new=new[:start]+new[end:]
    new=new.replace('    for(integer boundary=0;boundary<6;boundary=boundary+1) input_stage_boundary(boundary);\n','',1)
    assert new==old,'all original numerical/fault/service assertions retained'


def fixture(tmp_path):
    target=tmp_path/SIM;target.mkdir(parents=True)
    for name in ['simulate.log','staged_words.csv']:
        shutil.copyfile(ACTUAL/SIM/name,target/name)
    return target/'simulate.log'


def test_actual_inputstage_evidence_passes(tmp_path):
    fixture(tmp_path);result=experiment.audit_inputstage_sim(tmp_path)
    assert result['numerical_rows']==64512
    assert result['inputstage']['boundaries']==[str(n) for n in range(6)]
    assert not result['physical_signoff'] and not result['continuous_rx']


@pytest.mark.parametrize('mutant',['missing_case','duplicate_case','short_recovery',
                                  'early_publication','missing_receipt','short_coverage','bad_numeric'])
def test_inputstage_evidence_mutants_fail(tmp_path,mutant):
    log=fixture(tmp_path);text=log.read_text()
    case=next(line for line in text.splitlines(True) if line.startswith('STAGED_INPUT_IDENTITY_CASE_PASS boundary=0 '))
    receipt=next(line for line in text.splitlines(True) if line.startswith('STAGED_INPUT_IDENTITY_PASS '))
    if mutant=='missing_case':text=text.replace(case,'',1)
    elif mutant=='duplicate_case':text+=case
    elif mutant=='short_recovery':text=text.replace(case,case.replace('fresh_reads=512','fresh_reads=511'),1)
    elif mutant=='early_publication':text=text.replace(case,case.replace('publications=0','publications=1'),1)
    elif mutant=='missing_receipt':text=text.replace(receipt,'',1)
    elif mutant=='short_coverage':
        import re
        text=text.replace(receipt,re.sub(r'checks=\d+','checks=1',receipt),1)
    else:
        csv=tmp_path/SIM/'staged_words.csv';csv.write_text(csv.read_text().replace(',inputF,',',unknownF,',1))
    log.write_text(text)
    with pytest.raises(ValueError):experiment.audit_inputstage_sim(tmp_path)

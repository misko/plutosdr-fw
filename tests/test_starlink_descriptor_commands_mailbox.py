"""Real dual-clock BRAM mailbox composition; no FFT or physical CDC claim."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
BANK=Path('/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-summary-actual-prelaunch-v1/source_snapshot/hdl/library/starlink_pss_acquisition/retained_output/starlink_pss_mailbox_owner_view.v')

def run_case(tmp_path,cancel,stall,bank=BANK,bench=BASE/'tb_descriptor_commands_mailbox.sv'):
    sources=[BASE/'starlink_pss_descriptor_commands.v',bank,bench]
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    (tmp_path/'sources.json').write_text(json.dumps(before,indent=2))
    (tmp_path/'inputs').mkdir()
    for path in sources:shutil.copyfile(path,tmp_path/'inputs'/path.name)
    compile=subprocess.run(['iverilog','-g2012','-s','tb',f'-Ptb.CANCEL_CASE={cancel}',f'-Ptb.STALL_CYCLES={stall}',
                            '-o',str(tmp_path/'sim'),*map(str,sources)],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(compile.stdout+compile.stderr)
    assert compile.returncode==0,compile.stdout+compile.stderr
    run=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'run.log').write_text(run.stdout+run.stderr)
    assert before=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    return run

@pytest.mark.parametrize('cancel',[0,1,2,3])
@pytest.mark.parametrize('stall',[1,37])
def test_real_mailbox_publication_and_ack(tmp_path,cancel,stall):
    assert hashlib.sha256(BANK.read_bytes()).hexdigest()=='de060a7930be1d65cc91903da447e51ead3efad4ebed4b61e4f257e45d76d2d6'
    run=run_case(tmp_path,cancel,stall)
    assert run.returncode==0,run.stdout+run.stderr
    assert run.stdout.splitlines()==[f'MAILBOX_COMPOSITION_PASS cancel={cancel} publications={1 if cancel else 2} words={512 if cancel else 1024}']

@pytest.mark.parametrize('change',['early_publish','early_ack','wrong_metadata','corrupt_final_replay'])
def test_unsafe_mailbox_composition_mutants_fail(tmp_path,change):
    if change=='corrupt_final_replay':
        source=BASE/'tb_descriptor_commands_mailbox.sv'
        before='input_data=word(tag,511);input_metadata=tag;response_ready=1;'
        after='input_data=word(tag,511)^1;input_metadata=tag;response_ready=1;'
    else:
        source=BANK
        before,after={
            'early_publish':('if (!EXPLICIT_COMMIT || input_commit_authorized)',"if (1'b1)"),
            'early_ack':('if (output_accept && output_last) begin','if (output_accept) begin'),
            'wrong_metadata':('metadata_out_hold <= metadata_in_hold;','metadata_out_hold <= 0;'),
        }[change]
    text=source.read_text();assert text.count(before)==1
    mutant=tmp_path/source.name;mutant.write_text(text.replace(before,after,1))
    run=run_case(tmp_path,0,37,**({'bench':mutant} if change=='corrupt_final_replay' else {'bank':mutant}))
    assert run.returncode!=0 and 'FATAL' in run.stdout and 'timeout' not in run.stdout,run.stdout+run.stderr

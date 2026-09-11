"""Real command arbiter/publication sequencer + explicit-commit RAM, not FFT/RF."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
BANK=Path('/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-summary-actual-prelaunch-v1/source_snapshot/hdl/library/starlink_pss_acquisition/retained_output/starlink_pss_mailbox_owner_view.v')
ADAPTER=BASE/'starlink_pss_staged_mailbox_control.v'

def run_case(tmp_path,cancel,stall,adapter=ADAPTER):
    assert hashlib.sha256(BANK.read_bytes()).hexdigest()=='de060a7930be1d65cc91903da447e51ead3efad4ebed4b61e4f257e45d76d2d6'
    sources=[BASE/'starlink_pss_descriptor_commands.v',adapter,BANK,BASE/'tb_staged_mailbox_control.sv']
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

@pytest.mark.parametrize('cancel',[0,1,2,3,4])
@pytest.mark.parametrize('stall',[1,37])
def test_adapter_real_bank_lifetimes(tmp_path,cancel,stall):
    run=run_case(tmp_path,cancel,stall)
    assert run.returncode==0,run.stdout+run.stderr
    assert run.stdout.splitlines()==[f'STAGED_ADAPTER_PASS cancel={cancel} publications={1 if cancel else 3} words={512 if cancel else 1536}']

@pytest.mark.parametrize('change',['early_release','wrong_replay','drop_replay','block_commit'])
def test_unsafe_adapter_mutants_fail(tmp_path,change):
    before,after={
        'early_release':('if (bank_ack_sync==bank_request) phase<=P_RELEASE;',"if (1'b1) phase<=P_RELEASE;"),
        'wrong_replay':('assign replay_data = final_data;','assign replay_data = final_data ^ 1;'),
        'drop_replay':('assign replay_valid = live && phase==P_REPLAY;',"assign replay_valid = 1'b0;"),
        'block_commit':('if (phase==P_RELEASE || phase==P_COMMIT) begin','if ((phase==P_RELEASE || phase==P_COMMIT) && !allocated_valid) begin'),
    }[change]
    source=ADAPTER.read_text();assert source.count(before)==1
    mutant=tmp_path/ADAPTER.name;mutant.write_text(source.replace(before,after,1))
    run=run_case(tmp_path,0,37,adapter=mutant)
    assert run.returncode!=0 and 'FATAL' in run.stdout and 'watchdog' not in run.stdout,run.stdout+run.stderr

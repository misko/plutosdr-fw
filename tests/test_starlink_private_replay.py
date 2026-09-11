"""Actual RAM/ledger tests: a private replay without authorization is not ACK."""
import hashlib
from pathlib import Path
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
BANK=ROOT.parent/'staged-replay-prepared-v1/starlink_pss_mailbox_owner_view.v'
ADAPTER=RTL/'starlink_pss_staged_mailbox_control.v'

def execute(tmp_path,abort,source):
    assert hashlib.sha256(BANK.read_bytes()).hexdigest()=='de060a7930be1d65cc91903da447e51ead3efad4ebed4b61e4f257e45d76d2d6'
    bench=(RTL/'tb_staged_mailbox_control.sv').read_text()
    prefix,tail=bench.split('  initial begin\n    descriptors[0]=',1)
    assert tail.endswith('endmodule\n')
    prefix=prefix.replace('reg resetn=0,abort_epoch=0;','reg resetn=0,abort_epoch=0,authorize=0;')
    before='.input_commit_authorized(replay_valid && allow_replay)'
    assert prefix.count(before)==1
    prefix=prefix.replace(before,'.input_commit_authorized(replay_valid && allow_replay && authorize)')
    bench=prefix+f'''
  initial begin
    descriptors[0]=70'h20000123456789abcd;descriptors[1]=0;descriptors[2]=0;
    seeds[0]=7;seeds[1]=13;seeds[2]=29;
    reset_all;request_allocation(0);consume_allocation(0);write_private(0);complete_block(0);
    await_replay;allow_replay=1;
    @(posedge clk);@(negedge clk);allow_replay=0;
    if(dut.phase!=4 || bank_request!==0 || bank_ack_sync!==0 || publications!=0)
      $fatal(1,"private consumption incorrectly proved publication");
    if({abort})abort_epoch=1;
    repeat(80) begin
      @(negedge clk);
      if(bank_request!==0 || published_valid || released_valid || publications!=0 || releases!=0 || reads[0]!=0)
        $fatal(1,"idle ACK/private receipt fabricated ownership transfer");
    end
    if(!fault || allocate_ready || complete_ready || replay_valid) $fatal(1,"missing publication not quarantined");
    reset_all;authorize=1;
    request_allocation(0);consume_allocation(0);write_private(0);complete_block(0);publish_and_drain(0);
    if(fault || publications!=1 || releases!=1 || reads[0]!=512 || occupied!=0)
      $fatal(1,"fresh authorized epoch failed recovery");
    $display("PRIVATE_REPLAY_PASS abort={abort} rejected=1 fresh_reads=512 fresh_release=1");$finish;
  end
  initial begin #1000000;$fatal(1,"watchdog");end
endmodule
'''
    (tmp_path/'tb.sv').write_text(bench);(tmp_path/'adapter.v').write_text(source)
    sources=[RTL/'starlink_pss_descriptor_commands.v',tmp_path/'adapter.v',BANK,tmp_path/'tb.sv']
    result=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),*map(str,sources)],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'run.log').write_text(result.stdout+result.stderr)
    return result

@pytest.mark.parametrize('abort',[0,1])
def test_private_replay_requires_real_bank_publication(tmp_path,abort):
    result=execute(tmp_path,abort,ADAPTER.read_text())
    assert result.returncode==0 and f'PRIVATE_REPLAY_PASS abort={abort} rejected=1 fresh_reads=512 fresh_release=1' in result.stdout,result.stdout

@pytest.mark.parametrize('change,abort',[('ignore_request',0),('early_notify',0),('early_notify',1),
                                        ('early_release',0),('early_release',1)])
def test_private_replay_unsafe_mutants_rejected(tmp_path,abort,change):
    before,after={
        'ignore_request':('if (bank_request !== !initial_request ||',"if (1'b0 ||"),
        'early_notify':('if (phase==P_REPLAY && replay_ready) phase<=P_ACK;',
                        'if (phase==P_REPLAY && replay_ready) begin phase<=P_ACK;published_pending<=1;end'),
        'early_release':('if (phase==P_REPLAY && replay_ready) phase<=P_ACK;',
                         'if (phase==P_REPLAY && replay_ready) phase<=P_RELEASE;'),
    }[change]
    source=ADAPTER.read_text();assert source.count(before)==1
    result=execute(tmp_path,abort,source.replace(before,after,1))
    assert result.returncode!=0 and 'FATAL' in result.stdout and 'watchdog' not in result.stdout,result.stdout

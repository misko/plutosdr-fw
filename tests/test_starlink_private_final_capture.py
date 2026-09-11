"""Compare complete real adapters, with actual bank, stalls, aborts and reset."""
import hashlib
from pathlib import Path
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
ORIGINAL=ROOT.parent/'staged-capture-prepared-v1/starlink_pss_staged_mailbox_control.v'
BANK=ROOT.parent/'staged-capture-prepared-v1/starlink_pss_mailbox_owner_view.v'

MONITOR=r'''
  golden reference_adapter (
    .clk(clk),.resetn(resetn),.abort_epoch(abort_epoch),
    .allocate_valid(allocate_valid),.allocate_ready(),.allocate_descriptor(allocate_descriptor),
    .allocated_valid(),.allocated_ready(allocated_ready),.allocated_tag(),
    .complete_valid(complete_valid),.complete_ready(),.complete_tag(complete_tag),
    .complete_final_data(complete_final_data),.replay_valid(),.replay_ready(replay_ready),
    .replay_tag(),.replay_data(),.bank_request(bank_request),.bank_ack_sync(bank_ack_sync),
    .bank_fault(bank_fault),.publication_busy(),.published_valid(),.released_valid(),.released_tag(),
    .lookup_valid(lookup_valid),.lookup_tag(lookup_tag),.lookup_found(),.lookup_committed(),
    .lookup_descriptor(),.occupied(),.committed(),.tags_exhausted(),.fault());
  integer private_loads=0,private_holds=0,checks=0,churn=0;
  reg [68:0] before_bundle,offered_bundle;
  reg was_capture;
  // Only invalid input payloads churn; real completion tasks retain ownership
  // of their valid payload. Churn continues during replay and reader stalls.
  always @(negedge clk) begin
    #0.1;
    if(resetn && !complete_valid) begin
      churn=churn+1;
      complete_tag=churn%2 ? 32'hxxxxxxxx : 32'(churn*73);
      complete_final_data=churn%2 ? 36'hzzzzzzzzz : 36'(churn*197);
    end
  end
  always @(posedge clk) begin
    if(resetn) begin
      before_bundle={dut.active_tag,dut.final_data,dut.initial_request};
      offered_bundle={complete_tag,complete_final_data,bank_request};
      was_capture=PRIVATE_MODE ? dut.phase==0 : !dut.fault && complete_valid && complete_ready;
      #0.001;
      if(resetn) begin
        if({dut.active_tag,dut.final_data,dut.initial_request} !==
           (was_capture ? offered_bundle : before_bundle)) $fatal(1,"private capture/hold");
        if(!PRIVATE_MODE || dut.phase!=0)
          if({dut.active_tag,dut.final_data,dut.initial_request} !==
             {reference_adapter.active_tag,reference_adapter.final_data,reference_adapter.initial_request})
            $fatal(1,"accepted/held payload differs from original");
        if({dut.phase,dut.command_state,dut.command_opcode,dut.command_tag,dut.command_descriptor,
            dut.allocate_ready,dut.allocated_valid,dut.allocated_tag,dut.complete_ready,dut.replay_valid,
            dut.publication_busy,dut.published_valid,dut.released_valid,dut.released_tag,
            dut.lookup_found,dut.lookup_committed,dut.lookup_descriptor,dut.occupied,dut.committed,
            dut.tags_exhausted,dut.fault} !==
           {reference_adapter.phase,reference_adapter.command_state,reference_adapter.command_opcode,
            reference_adapter.command_tag,reference_adapter.command_descriptor,
            reference_adapter.allocate_ready,reference_adapter.allocated_valid,reference_adapter.allocated_tag,
            reference_adapter.complete_ready,reference_adapter.replay_valid,
            reference_adapter.publication_busy,reference_adapter.published_valid,
            reference_adapter.released_valid,reference_adapter.released_tag,reference_adapter.lookup_found,
            reference_adapter.lookup_committed,reference_adapter.lookup_descriptor,reference_adapter.occupied,
            reference_adapter.committed,reference_adapter.tags_exhausted,reference_adapter.fault})
          $fatal(1,"original adapter control equivalence");
        checks=checks+1;
        if(was_capture) private_loads=private_loads+1;else private_holds=private_holds+1;
      end
    end
  end
'''

def run(tmp_path,mode=1,cancel=0,stall=37,mutant=None):
    original=ORIGINAL.read_bytes()
    assert hashlib.sha256(original).hexdigest()=='1f971b4a50421ac4162ba4ff9a30f42431e29ff926881e343a321a3519d95343'
    assert hashlib.sha256(BANK.read_bytes()).hexdigest()=='de060a7930be1d65cc91903da447e51ead3efad4ebed4b61e4f257e45d76d2d6'
    source=(RTL/'starlink_pss_staged_mailbox_control.v').read_text()
    mutations={
        'always_load':('PRIVATE_FINAL_CAPTURE ? phase==P_EMPTY :',"PRIVATE_FINAL_CAPTURE ? 1'b1 :"),
        'qualified_only':('PRIVATE_FINAL_CAPTURE ? phase==P_EMPTY :','PRIVATE_FINAL_CAPTURE ? (!fault && complete_valid && complete_ready) :'),
        'miss_accept':('PRIVATE_FINAL_CAPTURE ? phase==P_EMPTY :','PRIVATE_FINAL_CAPTURE ? (phase==P_EMPTY && !complete_valid) :'),
        'early_unlock':('PRIVATE_FINAL_CAPTURE ? phase==P_EMPTY :','PRIVATE_FINAL_CAPTURE ? (phase==P_EMPTY || phase==P_ACK) :'),
        'wrong_word':('final_data<=complete_final_data;','final_data<=complete_final_data ^ 1;'),
    }
    if mutant:
        before,after=mutations[mutant];assert source.count(before)==1
        source=source.replace(before,after,1)
    bench=(RTL/'tb_staged_mailbox_control.sv').read_text()
    bench=bench.replace('parameter integer CANCEL_CASE=0, STALL_CYCLES=17;',
                        'parameter integer CANCEL_CASE=0, STALL_CYCLES=17, PRIVATE_MODE=1;')
    bench=bench.replace('starlink_pss_staged_mailbox_control dut(.*);',
                        'starlink_pss_staged_mailbox_control #(.PRIVATE_FINAL_CAPTURE(PRIVATE_MODE)) dut(.*);')
    bench=bench.replace('    $finish(0);', '''    if(checks<1000 || private_holds<1000 || (PRIVATE_MODE && private_loads<1000))
      $fatal(1,"private final coverage");
    $display("PRIVATE_FINAL_PASS mode=%0d cancel=%0d checks=%0d loads=%0d holds=%0d",PRIVATE_MODE,CANCEL_CASE,checks,private_loads,private_holds);
    $finish(0);''')
    assert bench.count('endmodule')==1
    bench=bench.replace('endmodule',MONITOR+'\nendmodule')
    sources=[RTL/'starlink_pss_descriptor_commands.v',BANK]
    for name,text in [('candidate.v',source),('original.v',original.decode().replace('module starlink_pss_staged_mailbox_control','module golden',1)),('bench.sv',bench)]:
        path=tmp_path/name;path.write_text(text);sources.append(path)
    compiled=subprocess.run(['iverilog','-g2012','-s','tb',f'-Ptb.PRIVATE_MODE={mode}',f'-Ptb.CANCEL_CASE={cancel}',
                             f'-Ptb.STALL_CYCLES={stall}','-o',str(tmp_path/'sim'),*map(str,sources)],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(compiled.stdout+compiled.stderr)
    assert compiled.returncode==0,compiled.stdout+compiled.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result

@pytest.mark.parametrize('mode',[0,1])
@pytest.mark.parametrize('cancel',range(5))
@pytest.mark.parametrize('stall',[1,37])
def test_complete_adapter_equivalence(tmp_path,mode,cancel,stall):
    result=run(tmp_path,mode,cancel,stall)
    assert result.returncode==0 and 'PRIVATE_FINAL_PASS' in result.stdout,result.stdout+result.stderr

@pytest.mark.parametrize('mutant',['always_load','qualified_only','miss_accept','early_unlock','wrong_word'])
def test_unsafe_capture_rejected(tmp_path,mutant):
    result=run(tmp_path,mutant=mutant)
    assert result.returncode!=0 and 'FATAL' in result.stdout and 'watchdog' not in result.stdout,result.stdout+result.stderr

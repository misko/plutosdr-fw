"""Private write progress may differ only behind the unchanged fault fence."""
from pathlib import Path
import re
import subprocess
import pytest
from tests.test_starlink_forward_return_bank import RTL, SOURCE

PARENT=Path('/dev/shm/starlink-forward-return.FEyGL1Bw/prepared-v2')
BANK='starlink_pss_forward_return_bank.v'

def undo(source):
    start=source.index('  // BEGIN PRIVATE CAPTURE PROGRESS\n')
    end=source.index('  // END PRIVATE CAPTURE PROGRESS\n',start)+len('  // END PRIVATE CAPTURE PROGRESS\n\n')
    source=source[:start]+source[end:]
    source=source.replace('state<=IDLE;fault_q<=0;replay_valid<=0;read_count<=0;',
        'state<=IDLE;fault_q<=0;replay_valid<=0;write_count<=0;read_count<=0;',1)
    source=source.replace('descriptor<=0;output_position<=0;','descriptor<=0;exponent<=0;output_position<=0;',1)
    source=source.replace('descriptor<=reserve_descriptor;state<=CAPTURE;',
        'descriptor<=reserve_descriptor;state<=CAPTURE;write_count<=0;',1)
    source=source.replace('          if (capture_take) begin\n',
        "          if (capture_take) begin\n            write_count<=write_count+1'b1;\n            if (write_count==0) exponent<=capture_exponent;\n",1)
    return source

def test_exact_private_progress_delta():
    assert undo(SOURCE.read_text())==(PARENT/BANK).read_text()
    original=Path('/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/forward-return-bank-worktree-v1')
    for name in ['tb_forward_return_bank.sv','forward_return_actual_observer.svh']:
        assert (RTL/name).read_bytes()==(original/'hdl/library/starlink_pss_acquisition/staged_control'/name).read_bytes()

REFERENCE_INSTANCE=r'''
  wire old_reserve_ready,old_capture_ready,old_output_valid,old_output_last,old_done_pulse,old_busy,old_fault;
  wire [35:0] old_output_data;
  wire [8:0] old_output_position;
  wire [4:0] old_output_exponent;
  wire [69:0] old_output_descriptor;
  bank_reference original(
    .clk(clk),.resetn(resetn),.abort_epoch(abort_epoch),.reserve_valid(reserve_valid),
    .reserve_ready(old_reserve_ready),.reserve_descriptor(reserve_descriptor),
    .capture_valid(capture_valid),.capture_ready(old_capture_ready),.capture_data(capture_data),
    .capture_position(capture_position),.capture_last(capture_last),.capture_exponent(capture_exponent),
    .capture_descriptor(capture_descriptor),.seal_valid(seal_valid),.output_ready(output_ready),
    .output_valid(old_output_valid),.output_data(old_output_data),.output_position(old_output_position),
    .output_last(old_output_last),.output_exponent(old_output_exponent),.output_descriptor(old_output_descriptor),
    .done_pulse(old_done_pulse),.busy(old_busy),.fault(old_fault));
  integer equivalence_checks=0,private_differences=0;
  task automatic compare;
    begin
      if({reserve_ready,capture_ready,output_valid,done_pulse,busy,fault} !==
         {old_reserve_ready,old_capture_ready,old_output_valid,old_done_pulse,old_busy,old_fault})
        $fatal(1,"private progress changed current control/fault contract");
      if(output_valid && {output_data,output_position,output_last,output_exponent,output_descriptor} !==
         {old_output_data,old_output_position,old_output_last,old_output_exponent,old_output_descriptor})
        $fatal(1,"private progress changed valid replay");
      if(dut.write_count!==original.write_count || dut.exponent!==original.exponent)begin
        if(!fault || output_valid || reserve_ready || capture_ready)
          $fatal(1,"private difference escaped quarantine");
        private_differences=private_differences+1;
      end
      equivalence_checks=equivalence_checks+1;
    end
  endtask
  always @(posedge clk)begin compare;#0.1;compare;end
  final $display("PRIVATE_FORWARD_CAPTURE_EQ checks=%0d private_differences=%0d current_exact=1 valid_payload_exact=1",equivalence_checks,private_differences);
'''

@pytest.mark.parametrize('case',range(21))
def test_current_controls_and_valid_payload_match_reference(tmp_path,case):
    reference=(PARENT/BANK).read_text().replace('module starlink_pss_forward_return_bank #(', 'module bank_reference #(',1)
    bench=(RTL/'tb_forward_return_bank.sv').read_text().replace('\nendmodule','\n'+REFERENCE_INSTANCE+'\nendmodule',1)
    (tmp_path/'reference.v').write_text(reference);(tmp_path/'tb.sv').write_text(bench)
    result=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(SOURCE),str(tmp_path/'reference.v'),str(tmp_path/'tb.sv')],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim'),f'+CASE={case}'],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    row=re.search(r'PRIVATE_FORWARD_CAPTURE_EQ checks=(\d+) private_differences=(\d+) current_exact=1 valid_payload_exact=1',result.stdout)
    assert row and int(row[1])>2000,result.stdout
    if case in [1,2,3,4,5,14,15,16]:assert int(row[2])>0,result.stdout

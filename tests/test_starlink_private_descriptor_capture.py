"""Execute the actual capture always-block against pinned qualified capture.

This isolates writer sequencing, not the FFT/ledger/CDC authorization contract;
the generated-FFT campaign separately covers that complete integration.
"""
import hashlib
from pathlib import Path
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
CURRENT=ROOT/'hdl/library/starlink_pss_acquisition/staged_control/starlink_pss_fft_staged_output_impl.v'
GOLDEN=ROOT.parent/'staged-replay-prepared-v2/starlink_pss_fft_staged_output_impl.v'
PIN='a7586aa38c2548be4797671fa7c40cac784e0d331745f05ca3fe452a1d036b21'

def wrapper(name,source,current):
    start='  always @(posedge fft_clk) begin\n    if (!fast_running) begin\n      inverse_descriptor_live'
    end='  starlink_pss_core_job_cutover #('
    assert source.count(start)==1 and source.count(end)==1
    block=source[source.index(start):source.index(end)]
    capture='  wire output_descriptor_capture = inverse_descriptor_live && !output_descriptor_locked;'
    if current:
        assert source.count(capture)==1
    else:
        capture='wire output_descriptor_capture=0;'
    return f'''`timescale 1ns/1ps
    module {name}(
      input wire fft_clk,fast_running,output_allocated_valid,
      input wire [31:0] output_allocated_tag,
      input wire output_complete_accept,output_released_valid,output_published_valid,
      input wire [69:0] output_lookup_descriptor,
      input wire output_lookup_found,output_lookup_committed,
      input wire [74:0] metadata,
      output wire [177:0] payload,output wire [2:0] controls,
      output wire capture,locked);
      wire [74:0] guard_return_metadata[0:1];
      assign guard_return_metadata[0]=0;assign guard_return_metadata[1]=metadata;
      wire output_allocate_valid=0,output_allocate_ready=0,completion_accept=0,next_inverse=0;
      reg inverse_descriptor_live,inverse_allocation_pending;
      reg [31:0] inverse_tag,output_descriptor_tag;
      reg [74:0] output_descriptor_payload;
      reg [69:0] output_descriptor_expected;
      reg output_descriptor_valid,output_descriptor_fault,output_descriptor_pending,output_descriptor_lookup_ok;
      reg output_descriptor_locked=0,retained_published,producer_transfer_receipt;
      {capture}
      assign capture=output_descriptor_capture;assign locked=output_descriptor_locked;
      assign payload={{output_descriptor_tag,output_descriptor_payload,output_descriptor_expected,output_descriptor_lookup_ok}};
      assign controls={{output_descriptor_valid,output_descriptor_pending,output_descriptor_fault}};
      {block}
    endmodule
    '''

BENCH=r'''
module tb;
 reg fft_clk=0,fast_running=0,output_allocated_valid=0;
 always #5 fft_clk=~fft_clk;
 reg [31:0] output_allocated_tag=0;
 reg output_complete_accept=0,output_released_valid=0,output_published_valid=0;
 reg [69:0] output_lookup_descriptor=0;
 reg output_lookup_found=0,output_lookup_committed=0;
 reg [74:0] metadata=0;
 wire [177:0] payload,gpayload;wire [2:0] controls,gcontrols;
 wire capture,locked,gcapture,glocked;
 candidate dut(.*);
 golden refdut(.payload(gpayload),.controls(gcontrols),.capture(gcapture),.locked(glocked),.*);
 reg [177:0] before_payload,offered_payload;
 reg before_capture,before_locked;
 integer epoch,n,loads=0,holds=0,accepts=0;
 task tick;
   begin
     before_payload=payload;before_capture=capture;before_locked=locked;
     offered_payload={dut.inverse_tag,output_lookup_descriptor,metadata[4:0],metadata[74:5],
       (output_lookup_found===1'b1 && output_lookup_committed===1'b0)};
     @(posedge fft_clk);#0.01;
     if(controls!==gcontrols) $fatal(1,"qualified control equivalence");
     if(fast_running) begin
       if(payload!==(before_capture ? offered_payload : before_payload))
         $fatal(1,"private load/freeze");
       if(locked && payload!==gpayload) $fatal(1,"accepted payload equivalence");
       if(output_complete_accept && (!before_capture || !locked)) $fatal(1,"acceptance lock");
       if(output_released_valid && locked) $fatal(1,"release unlock");
       if(before_locked && !output_released_valid && !locked) $fatal(1,"early unlock");
       if(before_capture) loads=loads+1;else holds=holds+1;
       if(output_complete_accept) accepts=accepts+1;
     end
     @(negedge fft_clk);
   end
 endtask
 initial begin
   for(epoch=0;epoch<80;epoch=epoch+1) begin
     fast_running=0;tick;fast_running=1;
     output_allocated_tag=32'ha5a50000+epoch;output_allocated_valid=1;tick;output_allocated_valid=0;
     for(n=0;n<16;n=n+1) begin
       output_lookup_found=0;output_lookup_committed=1;
       output_lookup_descriptor=n%2 ? {70{1'bx}} : 70'(n*9876543+epoch);
       metadata=75'(n*7777777+epoch);tick;
     end
     output_lookup_descriptor=70'h2abcdef123456789ab;metadata={output_lookup_descriptor,5'(epoch)};
     output_lookup_found=epoch%4==1 ? 0 : epoch%4==2 ? 1'bx : 1;
     output_lookup_committed=0;
     if(epoch%4==3) metadata[50]=~metadata[50];
     output_complete_accept=1;tick;output_complete_accept=0;
     for(n=0;n<16;n=n+1) begin
       output_lookup_descriptor={70{1'bx}};output_lookup_found=0;output_lookup_committed=1;
       metadata=75'(n+epoch*393939);output_published_valid=n==3;tick;
     end
     output_published_valid=0;output_released_valid=1;tick;output_released_valid=0;tick;
   end
   if(loads!=1360 || accepts!=80 || holds<1000) $fatal(1,"coverage inventory");
   $display("PRIVATE_DESCRIPTOR_PASS epochs=80 accepts=80 loads=1360");$finish;
 end
 initial begin #100000;$fatal(1,"deadline");end
endmodule
'''

def run(tmp_path,mutant=None):
    original=GOLDEN.read_bytes();assert hashlib.sha256(original).hexdigest()==PIN
    source=CURRENT.read_text()
    changes={
        'missing_lock':('output_descriptor_locked<=1;','output_descriptor_locked<=0;'),
        'early_unlock':('output_descriptor_pending<=0;\n        output_descriptor_valid<=',
                        'output_descriptor_pending<=0;output_descriptor_locked<=0;\n        output_descriptor_valid<='),
        'qualified_load':('if (output_descriptor_capture) begin','if (output_complete_accept) begin'),
        'ignore_found':('output_descriptor_valid<=output_descriptor_lookup_ok &&',
                        'output_descriptor_valid<=1\'b1 &&'),
        'skip_comparison':('output_descriptor_payload[74:5]===output_descriptor_expected;',
                           '1\'b1;'),
    }
    if mutant:
        before,after=changes[mutant];assert source.count(before)==1;source=source.replace(before,after)
    path=tmp_path/'capture.sv'
    path.write_text(wrapper('candidate',source,True)+wrapper('golden',original.decode(),False)+BENCH)
    executable=tmp_path/'sim'
    compile_run=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(executable),str(path)],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(compile_run.stdout+compile_run.stderr)
    assert compile_run.returncode==0,compile_run.stdout+compile_run.stderr
    result=subprocess.run(['vvp',str(executable)],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result

def test_private_descriptor_matches_qualified_capture(tmp_path):
    result=run(tmp_path)
    assert result.returncode==0 and 'PRIVATE_DESCRIPTOR_PASS epochs=80 accepts=80 loads=1360' in result.stdout,result.stdout+result.stderr

@pytest.mark.parametrize('mutant',['missing_lock','early_unlock','qualified_load','ignore_found','skip_comparison'])
def test_capture_contract_mutants_rejected(tmp_path,mutant):
    result=run(tmp_path,mutant)
    assert result.returncode!=0 and 'FATAL:' in result.stdout,result.stdout+result.stderr

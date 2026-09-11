"""Complete source inverse and real-checker four-state/sequential comparison."""
import hashlib
from pathlib import Path
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
BASE=ROOT.parent/'staged-guardfacts-prepared-v1'
CHECKER='starlink_pss_realtime_input_guard_local_admission.v'
TOP='starlink_pss_fft_staged_output_impl.v'

def test_exact_checker_and_top_inverses():
    old=(BASE/CHECKER).read_text()
    assert hashlib.sha256(old.encode()).hexdigest()=='55438743eede0d346cec67351e079eb6ae21da437d4088a131a2a258b43ff233'
    text=(RTL/CHECKER).read_text()
    text=text.replace('  parameter integer LOCAL_FIRST_ADMISSION = 0,\n  parameter integer BANK_LOCAL_IDENTITY = 0\n',
                      '  parameter integer LOCAL_FIRST_ADMISSION = 0\n',1)
    text=text.replace('  // Opt-in caller wires input_metadata to the original phase-selected bus.\n  input wire bank_phase,\n  input wire [69:0] source_bank_metadata, product_bank_metadata,\n','',1)
    text=text.replace('    if (BANK_LOCAL_IDENTITY !== 0 && BANK_LOCAL_IDENTITY !== 1)\n      $fatal(1, "BANK_LOCAL_IDENTITY must be known zero or one");\n','',1)
    start=text.index('  // BEGIN BANK LOCAL IDENTITY\n');end=text.index('  // END BANK LOCAL IDENTITY\n')+len('  // END BANK LOCAL IDENTITY\n')
    text=(text[:start]+text[end:]).replace('selected_identity_matches','identity_matches')
    assert text==old,'no checker state, delivery, framing, or fault change'
    old=(BASE/TOP).read_text()
    assert hashlib.sha256(old.encode()).hexdigest()=='b3511a70b97b91e3e9b4106ea0c9bab8df4f7a43a07ff30a5447cd522dc5d143'
    text=(RTL/TOP).read_text().replace('    .BANK_LOCAL_IDENTITY(REGISTERED_SCHEDULING),\n','',1)
    text=text.replace('    .input_metadata(guard_metadata), .bank_phase(guard_phase),\n    .source_bank_metadata(source_metadata), .product_bank_metadata(product_bank_metadata),\n    .core_input_tdata(core_input_data),',
                      '    .input_metadata(guard_metadata), .core_input_tdata(core_input_data),',1)
    assert text==old,'no other top runtime change'

BENCH=r'''
`timescale 1ns/1ps
module tb;
 parameter integer MODE=1;
 reg clk=0,resetn=0,job_start=0,input_enable=1,input_valid=1,core_input_tready=1;
 reg bank_phase=0,input_last=0;
 reg [69:0] source_bank_metadata=0,product_bank_metadata=0,job_descriptor=0;
 wire [69:0] input_metadata=bank_phase ? product_bank_metadata : source_bank_metadata;
 reg [35:0] input_data=36'h123456789;
 reg [8:0] input_position=0;
 wire [63:0] c,r;
 starlink_pss_realtime_input_guard_local_admission #(.BALANCED_IDENTITY_EQ(1),
  .LOCAL_FIRST_ADMISSION(1),.BANK_LOCAL_IDENTITY(MODE)) candidate(
  .clk(clk),.resetn(resetn),.job_start(job_start),.job_descriptor(job_descriptor),
  .input_enable(input_enable),.input_valid(input_valid),.input_data(input_data),
  .input_position(input_position),.input_last(input_last),.input_metadata(input_metadata),
  .bank_phase(bank_phase),.source_bank_metadata(source_bank_metadata),.product_bank_metadata(product_bank_metadata),
  .core_input_tready(core_input_tready),
  .input_ready(c[0]),.input_transport_ready(c[1]),.core_input_tdata(c[49:2]),
  .core_input_tvalid(c[50]),.core_input_tlast(c[51]),.certified_input_beat(c[52]),
  .certified_input_complete(c[53]),.input_complete(c[54]),.fault_now(c[55]),
  .duplicate_start_fault_now(c[56]),.fault_events_now(c[59:57]),
  .protocol_fault(c[60]),.fault_reasons(c[63:61]));
 starlink_pss_realtime_input_guard_local_admission #(.BALANCED_IDENTITY_EQ(1),
  .LOCAL_FIRST_ADMISSION(1),.BANK_LOCAL_IDENTITY(0)) original(
  .clk(clk),.resetn(resetn),.job_start(job_start),.job_descriptor(job_descriptor),
  .input_enable(input_enable),.input_valid(input_valid),.input_data(input_data),
  .input_position(input_position),.input_last(input_last),.input_metadata(input_metadata),
  .bank_phase(bank_phase),.source_bank_metadata(source_bank_metadata),.product_bank_metadata(product_bank_metadata),
  .core_input_tready(core_input_tready),
  .input_ready(r[0]),.input_transport_ready(r[1]),.core_input_tdata(r[49:2]),
  .core_input_tvalid(r[50]),.core_input_tlast(r[51]),.certified_input_beat(r[52]),
  .certified_input_complete(r[53]),.input_complete(r[54]),.fault_now(r[55]),
  .duplicate_start_fault_now(r[56]),.fault_events_now(r[59:57]),
  .protocol_fault(r[60]),.fault_reasons(r[63:61]));
 function val(input integer n);case(n)0:val=0;1:val=1;2:val=1'bx;3:val=1'bz;endcase endfunction
 integer p,b,k,v,pos,step,cases=0,ticks=0,owner,scenario;
 task check;
 begin
  #1;
  if(c!==r || candidate.identity_matches!==original.identity_matches ||
     {candidate.descriptor,candidate.expected_position,candidate.job_started,candidate.input_started} !==
     {original.descriptor,original.expected_position,original.job_started,original.input_started})
    $fatal(1,"bank-local real checker mismatch phase=%b bit=%0d kind=%0d",bank_phase,b,k);
  cases=cases+1;
 end
 endtask
 task tick;begin check;clk=1;check;clk=0;ticks=ticks+1;end endtask
 initial begin
  tick;resetn=1;
  // Finite combinational premise: actual checker state set identically.
  for(p=0;p<4;p=p+1)for(b=0;b<70;b=b+1)for(k=0;k<8;k=k+1)
   for(v=0;v<64;v=v+1)for(pos=0;pos<3;pos=pos+1)begin
    bank_phase=val(p);source_bank_metadata=0;product_bank_metadata=0;job_descriptor=0;
    case(k)
     0: source_bank_metadata[b]=1;
     1: product_bank_metadata[b]=1;
     2: begin source_bank_metadata[b]=1'bx;product_bank_metadata[b]=1'bz;end
     3: begin source_bank_metadata[b]=1;product_bank_metadata[(b+1)%70]=1;end
     4: begin source_bank_metadata[b]=1;product_bank_metadata[b]=1;end
     5: job_descriptor[b]=1'bx;
     6: begin source_bank_metadata[b]=1'bz;product_bank_metadata[b]=1'bz;job_descriptor[b]=1'bz;end
     7: begin source_bank_metadata[b]=1'bx;product_bank_metadata[b]=1'bx;end
    endcase
    candidate.descriptor=job_descriptor;original.descriptor=job_descriptor;
    candidate.job_started=1;original.job_started=1;
    candidate.input_started=pos!=0;original.input_started=pos!=0;
    candidate.expected_position=pos==0 ? 0 : (pos==1 ? 32 : 511);
    original.expected_position=candidate.expected_position;
    candidate.input_complete=0;original.input_complete=0;
    candidate.fault_reasons=0;original.fault_reasons=0;
    input_position=candidate.expected_position;input_last=pos==2;
    input_valid=val(v&3);input_enable=val((v>>2)&3);core_input_tready=val((v>>4)&3);
    check;
   end
  // Evolving state: healthy, malformed position/last, unknown metadata,
  // duplicate start, unmet real-time demand, and reset in mid-input.
  for(owner=0;owner<2;owner=owner+1)for(scenario=0;scenario<8;scenario=scenario+1)begin
   resetn=0;job_start=0;input_valid=0;input_enable=1;core_input_tready=1;tick;
   resetn=1;bank_phase=owner;source_bank_metadata=0;product_bank_metadata=0;job_descriptor=0;
   job_start=1;tick;job_start=0;
   for(step=0;step<512;step=step+1)begin
    input_position=step;input_last=step==511;input_valid=1;core_input_tready=1;
    if(step==32)case(scenario)
     1: input_position=7;
     2: input_last=1;
     3: if(owner)product_bank_metadata[69]=1'bx;else source_bank_metadata[69]=1'bx;
     4: job_start=1;
     5: input_valid=0;
     6: resetn=0;
     7: core_input_tready=0;
    endcase
    tick;
    if(step==32 && scenario==7)begin core_input_tready=1;tick;end
    job_start=0;resetn=1;
   end
   if(scenario==0 || scenario==7)if(c[54]!==1'b1 || c[60]!==1'b0)
     $fatal(1,"healthy complete/stall control failed");
  end
  $display("BANK_LOCAL_CHECKER_PASS cases=%0d ticks=%0d mode=%0d exact_four_state=1",cases,ticks,MODE);$finish;
 end
endmodule
'''

def run(tmp_path,mode=1,mutant=None):
    source=(RTL/CHECKER).read_text()
    if mutant=='unknown_select':source=source.replace('known_phase ?',"1'b1 ?")
    elif mutant=='wrong_bank':source=source.replace('(bank_phase ? bank_matches[1] : bank_matches[0])','(bank_phase ? bank_matches[0] : bank_matches[1])')
    elif mutant=='drop_last_bit':source=source.replace('assign bank_matches[bank] = &group_equal;',"assign bank_matches[bank] = &leaf_equal[22:0];")
    path=tmp_path/'checker.v';path.write_text(source)
    bench=tmp_path/'bench.sv';bench.write_text(BENCH)
    result=subprocess.run(['iverilog','-g2012','-s','tb',f'-Ptb.MODE={mode}','-o',str(tmp_path/'sim'),str(path),str(bench)],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=60)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result

@pytest.mark.parametrize('mode',[0,1])
def test_complete_checker_equivalence(tmp_path,mode):
    result=run(tmp_path,mode)
    assert result.returncode==0 and 'BANK_LOCAL_CHECKER_PASS' in result.stdout,result.stdout

@pytest.mark.parametrize('mutant',['unknown_select','wrong_bank','drop_last_bit'])
def test_unsafe_comparator_mutants_rejected(tmp_path,mutant):
    result=run(tmp_path,mutant=mutant)
    assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout

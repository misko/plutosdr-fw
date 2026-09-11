from pathlib import Path
import re
import sys
import pytest
from tests.test_starlink_balanced_forward_identity import compile_run
from tests.test_starlink_private_forward_capture import REFERENCE_INSTANCE
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import private_forward_descriptor_transform as transform
import private_forward_descriptor_experiment as experiment
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
OLD='starlink_pss_forward_return_private_status'
BANK='starlink_pss_forward_return_private_descriptor'
TOP='starlink_pss_fft_private_forward_descriptor_impl'

@pytest.mark.parametrize('old,new,changes',[(OLD,BANK,transform.BANK_CHANGES),
    ('starlink_pss_fft_product_retirement_receipt_impl',TOP,transform.TOP_CHANGES)])
def test_exact_descriptor_only_delta(old,new,changes):
    a=(RTL/(old+'.v')).read_text();b=(RTL/(new+'.v')).read_text()
    assert transform.transform(a,changes)==b and transform.undo(b,changes)==a

def observer():
    text=REFERENCE_INSTANCE.replace('dut.write_count!==original.write_count || dut.exponent!==original.exponent',
        'dut.descriptor!==original.descriptor')
    text=text.replace('      equivalence_checks=equivalence_checks+1;',
        '''      if({dut.state,dut.fault_q,dut.write_count,dut.read_count,dut.exponent,dut.replay_valid,dut.output_position} !==
         {original.state,original.fault_q,original.write_count,original.read_count,original.exponent,original.replay_valid,original.output_position})
        $fatal(1,"descriptor load changed other bank state");
      equivalence_checks=equivalence_checks+1;''')
    return text

def run(tmp_path,bench,mutation=None,case=None):
    source=(RTL/(BANK+'.v')).read_text()
    if mutation=='ignore_current_fault':source=source.replace('if (fault_q || fault_now) begin','if (fault_q) begin',1)
    elif mutation=='unreserved_load':source=source.replace('else if (reserve_valid && reserve_ready) descriptor<=reserve_descriptor;',
        'else if (reserve_valid || reserve_ready) descriptor<=reserve_descriptor;',1)
    elif mutation=='wrong_reset':source=source.replace('if (!resetn) descriptor<=0;',"if (!resetn) descriptor<=70'h1;",1)
    (tmp_path/'bank.v').write_text(source)
    (tmp_path/'reference.v').write_text((RTL/(OLD+'.v')).read_text().replace('module '+OLD+' #(','module bank_reference #(',1))
    return compile_run(tmp_path,bench,[tmp_path/'bank.v',tmp_path/'reference.v'],case)

@pytest.mark.parametrize('case',range(21))
def test_existing_bank_campaign_exact_controls_and_payload(tmp_path,case):
    bench=(RTL/'tb_forward_return_bank.sv').read_text().replace('starlink_pss_forward_return_bank dut(',BANK+' dut(',1)
    bench=bench.replace('module tb;','module tb;\n  wire private_fault;',1)
    bench=bench.replace('\nendmodule','\n'+observer()+'\nendmodule',1)
    result=run(tmp_path,bench,case=case)
    assert result.returncode==0,result.stdout+result.stderr
    row=re.search(r'PRIVATE_FORWARD_CAPTURE_EQ checks=(\d+) private_differences=(\d+) current_exact=1 valid_payload_exact=1',result.stdout)
    assert row and int(row[1])>2000,result.stdout

@pytest.mark.parametrize('mutation',['none','ignore_current_fault','unreserved_load','wrong_reset'])
def test_reservation_four_state_grid_and_fresh_recovery(tmp_path,mutation):
    bench='''`timescale 1ns/1ps
module tb;
reg clk=0,resetn=0,abort_epoch=0,reserve_valid=0,capture_valid=0,seal_valid=0,output_ready=1;
reg [69:0] reserve_descriptor=0,capture_descriptor=0;
reg [35:0] capture_data=0;
reg [8:0] capture_position=0;
reg capture_last=0;
reg [4:0] capture_exponent=7;
wire reserve_ready,capture_ready,output_valid,output_last,done_pulse,busy,fault,private_fault;
wire [35:0] output_data;
wire [8:0] output_position;
wire [4:0] output_exponent;
wire [69:0] output_descriptor;
'''+BANK+''' #(.ADDRESS_WIDTH(2)) dut(.*);
integer n,k,tries,reads=0,recovered=0;
function automatic four(input integer n);
case(n%4)0:four=0;1:four=1;2:four=1'bx;3:four=1'bz;endcase
endfunction
task tick;begin #1;clk=1;#1;clk=0;#1;end endtask
task restart;begin
 resetn=0;abort_epoch=0;reserve_valid=0;capture_valid=0;seal_valid=0;output_ready=1;tick;
 reads=0;resetn=1;tick;
end endtask
always @(posedge clk)if(resetn && output_valid && output_ready)begin
 if(output_data!==36'(100+reads) || output_position!==9'(reads) || output_last!==(reads==3) ||
    output_descriptor!==70'h12345 || output_exponent!==7)$fatal(1,"fresh replay mismatch");
 reads=reads+1;
end
initial begin
 for(n=0;n<768;n=n+1)begin
  restart;
  reserve_descriptor=n<256?70'habcdef:n<512?{70{1'bx}}:{70{1'bz}};
  reserve_valid=four(n);capture_valid=four(n/4);seal_valid=four(n/16);abort_epoch=four(n/64);
  tick;
  if(fault===1)begin
    abort_epoch=0;reserve_valid=1;capture_valid=1;seal_valid=1;
    repeat(4)tick;
    if(reserve_ready || capture_ready || output_valid)$fatal(1,"quarantined reservation reused");
  end
  restart;reserve_descriptor=70'h12345;capture_descriptor=70'h12345;
  reserve_valid=1;tick;reserve_valid=0;
  for(k=0;k<4;k=k+1)begin capture_valid=1;capture_position=k;capture_last=k==3;capture_data=100+k;tick;end
  capture_valid=0;capture_last=0;seal_valid=1;tick;seal_valid=0;
  for(tries=0;tries<12 && reads<4;tries=tries+1)tick;
  if(reads!=4 || fault)$fatal(1,"fresh recovery missing");
  recovered=recovered+1;tick;
 end
 if(private_differences==0)$fatal(1,"private descriptor delta not exercised");
 $display("PRIVATE_DESCRIPTOR_GRID_PASS cases=%0d fresh_reads=%0d private_differences=%0d",recovered,recovered*4,private_differences);$finish;
end
'''+observer().replace('bank_reference original(','bank_reference #(.ADDRESS_WIDTH(2)) original(',1)+'''\nendmodule
'''
    result=run(tmp_path,bench,None if mutation=='none' else mutation)
    if mutation=='none':assert result.returncode==0 and 'PRIVATE_DESCRIPTOR_GRID_PASS cases=768 fresh_reads=3072' in result.stdout,result.stdout+result.stderr
    else:assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout

MAIN='PRIVATE_FORWARD_DESCRIPTOR_PASS checks=10000 loads=18 fault_loads=0 private_differences=0 controls_exact=1 valid_payload_exact=1 quarantined_difference=1\n'
HEAD=MAIN.replace('fault_loads=0','fault_loads=6').replace('private_differences=0','private_differences=6')
LINES=[f'PRIVATE_DESCRIPTOR_BOUNDARY_PASS boundary={n} fresh_reads=512 fresh_releases=1\n' for n in range(6)]
LINES+=['PRIVATE_DESCRIPTOR_BOUNDARIES_PASS cases=6 rejected_reservation=1 private_delta=1 fresh_recovery=1\n']
AUX=HEAD+''.join(LINES)
def test_main_witness():assert experiment.witness(MAIN)['loads']==18
def test_aux_witness():assert experiment.witness(AUX,True)['fault_loads']==6
@pytest.mark.parametrize('line',range(7))
def test_each_boundary_required(line):
    lines=LINES.copy();del lines[line]
    with pytest.raises(ValueError):experiment.witness(HEAD+''.join(lines),True)
@pytest.mark.parametrize('log',[AUX+AUX,AUX+'FATAL\n',AUX.replace('checks=10000','checks=9999'),
    AUX.replace('fault_loads=6','fault_loads=5'),AUX.replace('private_differences=6','private_differences=5'),
    AUX.replace('controls_exact=1','controls_exact=0'),AUX.replace('quarantined_difference=1','quarantined_difference=0'),
    AUX.replace('fresh_reads=512','fresh_reads=511',1)])
def test_incomplete_witness_rejected(log):
    with pytest.raises(ValueError):experiment.witness(log,True)

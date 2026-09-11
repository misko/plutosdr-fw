"""Private product staging and real mailbox identity-certificate boundary."""
import hashlib
from pathlib import Path
import re
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
PARENT=ROOT.parent/'retained-summary-actual-prelaunch-v1/source_snapshot/hdl/library/starlink_pss_acquisition/retained_output/starlink_pss_mailbox_owner_view.v'
BANK=RTL/'starlink_pss_product_mailbox_staged_identity.v'
STAGE=RTL/'starlink_pss_product_identity_stage.v'


def test_mailbox_inverse_preserves_all_other_checks():
    old=PARENT.read_text()
    assert hashlib.sha256(old.encode()).hexdigest()=='de060a7930be1d65cc91903da447e51ead3efad4ebed4b61e4f257e45d76d2d6'
    text=BANK.read_text().replace('module starlink_pss_product_mailbox_staged_identity #(',
                                  'module starlink_pss_mailbox_owner_view #(',1)
    text=text.replace('  // Captured with the word; the private stage owns this certificate.\n'
        '  input wire input_metadata_certified,\n'
        '  output wire [METADATA_WIDTH-1:0] writer_identity_metadata,\n'
        '  output wire writer_identity_load,\n','',1)
    text=text.replace('    if (EXPLICIT_COMMIT !== 1 || RESET_RELEASE_EXTERNAL !== 1)\n'
        '      $fatal(1, "staged identity requires explicit publication and common reset");\n','',1)
    start=old.index('  wire metadata_matches;\n');end=old.index('  wire input_framing_valid',start)
    first=text.index('  // The wide equality is registered');last=text.index('  wire input_framing_valid',first)
    text=text[:first]+old[start:end]+text[last:]
    text=text.replace('  assign writer_identity_metadata = metadata_in_hold;\n'
                      '  assign writer_identity_load = metadata_load;\n','',1)
    assert text.rstrip()==old.rstrip()


def test_existing_fft_runtime_is_not_yet_changed():
    parent=Path('/dev/shm/starlink-forward-receipt.7z0zKX/prepared-v1')
    assert hashlib.sha256((parent/'SHA256SUMS').read_bytes()).hexdigest()=='0d222aa4968145b0026ac4e8c9288c9b1ad5fc9f8f9b1bdd07a6d3eda4f1af8b'
    names=(parent/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    assert len(names)==19
    for name in names:
        if (RTL/name).exists():assert (RTL/name).read_bytes()==(parent/name).read_bytes(),name


def run(tmp_path,mutant=None):
    stage=STAGE.read_text();bank=BANK.read_text()
    bench=(RTL/'tb_product_identity_stage.sv').read_text()
    if mutant=='unchecked_identity':stage=stage.replace("(input_metadata == reference_metadata) === 1'b1","1'b1",1)
    elif mutant=='live_metadata':stage=stage.replace('output_metadata<=input_metadata;','output_metadata<=~input_metadata;',1)
    elif mutant=='lost_reset':stage=stage.replace('full<=0;fault_q<=0;', 'full<=1;fault_q<=0;',1)
    elif mutant=='lost_abort':stage=stage.replace("(abort_epoch !== 1'b0)","1'b0",1)
    elif mutant=='missing_reference_pause':stage=stage.replace("(output_ready && (reference_update === 1'b0))",'output_ready',1)
    elif mutant=='drop_unpublished_last':bench=bench.replace("((staged_last===1'b0) || bank_commit)","1'b1",1)
    elif mutant=='bypass_certificate':bank=bank.replace("input_metadata_certified === 1'b1","1'b1",1)
    files=[]
    for name,text in [('stage.v',stage),('bank.v',bank),('tb.sv',bench)]:
        path=tmp_path/name;path.write_text(text);files.append(str(path))
    compiled=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(PARENT),*files],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(compiled.stdout+compiled.stderr)
    assert compiled.returncode==0,compiled.stdout+compiled.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=60)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result


def test_actual_mailbox_conservation_faults_and_recovery(tmp_path):
    result=run(tmp_path)
    assert result.returncode==0,result.stdout+result.stderr
    match=re.search(r'PRODUCT_IDENTITY_COMPONENT_PASS good_blocks=(\d+) bad_metadata=420 bad_framing=6 resets=8 reads=(\d+) refills=(\d+) holds=(\d+) oracle=(\d+) pauses=(\d+)',result.stdout)
    assert match,result.stdout
    good,reads,refills,holds,oracle,pauses=map(int,match.groups())
    assert good==12 and reads==6144 and refills>=510 and holds>=200 and oracle>=1000 and pauses>=12


@pytest.mark.parametrize('mutant',['unchecked_identity','live_metadata','lost_reset','lost_abort',
                                  'missing_reference_pause','drop_unpublished_last','bypass_certificate'])
def test_unsafe_boundary_mutants_rejected(tmp_path,mutant):
    result=run(tmp_path,mutant)
    assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout+result.stderr


def bank_bench(tmp_path,text):
    path=tmp_path/'tb.sv';path.write_text(text)
    compiled=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(BANK),str(path)],
                            capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(compiled.stdout+compiled.stderr)
    assert compiled.returncode==0,compiled.stdout+compiled.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result


@pytest.mark.parametrize('certificate',["1'b0","1'bx","1'bz"])
def test_bad_or_unknown_final_certificate_cannot_publish(tmp_path,certificate):
    text=r'''`timescale 1ns/1ps
module tb;
reg clk=0,resetn=0,valid=0,last=0,certificate=1;
always #5 clk=~clk;
reg [1:0] position=0;
wire ready,fault,current_fault,request,output_valid;
starlink_pss_product_mailbox_staged_identity #(.ADDRESS_WIDTH(2),.RESET_RELEASE_EXTERNAL(1),.EXPLICIT_COMMIT(1)) dut(
 .input_clk(clk),.input_resetn(resetn),.input_valid(valid),.input_ready(ready),
 .input_commit_authorized(current_fault===1'b0),.input_data(36'h123456),.input_position(position),
 .input_last(last),.input_metadata(70'h12345),.input_metadata_certified(certificate),
 .input_fault(fault),.input_framing_fault_now(current_fault),.output_clk(clk),.output_resetn(resetn),
 .output_valid(output_valid),.output_ready(1'b0),.owner_request(request));
integer i;
initial begin
 repeat(3)@(negedge clk);resetn=1;
 for(i=0;i<4;i=i+1)begin
  @(negedge clk);valid=1;position=i;last=i==3;
  if(i==3)certificate=CERTIFICATE;
  #1;if(!ready || (i==3 && current_fault!==1))$fatal(1,"final certificate not rejected immediately");
  @(posedge clk);#1;
 end
 @(negedge clk);valid=0;
 repeat(10)@(negedge clk);
 if(!fault || request || output_valid)$fatal(1,"bad final certificate published");
 $display("BAD_FINAL_CERTIFICATE_REJECTED");$finish;
end
initial begin #1000;$fatal(1,"deadline");end
endmodule
'''.replace('CERTIFICATE',certificate)
    result=bank_bench(tmp_path,text)
    assert result.returncode==0 and 'REJECTED' in result.stdout,result.stdout+result.stderr


@pytest.mark.parametrize('parameters',['.EXPLICIT_COMMIT(0),.RESET_RELEASE_EXTERNAL(1)',
                                     '.EXPLICIT_COMMIT(1),.RESET_RELEASE_EXTERNAL(0)'])
def test_wrong_mailbox_contract_rejected(tmp_path,parameters):
    result=bank_bench(tmp_path,'module tb;starlink_pss_product_mailbox_staged_identity #('+parameters+') dut();initial #1 $finish;endmodule')
    assert result.returncode!=0 and 'staged identity requires' in result.stdout,result.stdout+result.stderr

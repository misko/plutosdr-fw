"""Consistent replay pause versus deliberately missing publication receipt."""
import re
import pytest
from tests.test_starlink_output_retirement_receipt import ROOT
import output_retirement_receipt_experiment_v5 as experiment
from tests.test_starlink_balanced_forward_identity import compile_run

def test_pause_and_missing_publication_are_distinct_boundaries():
    text=(experiment.RTL/'output_retirement_receipt_boundaries_v5.svh').read_text()
    pause=text.split('if(boundary==0)begin',1)[1].split('end else if(boundary<3)',1)[0]
    assert "force dut.output_stage_final_valid=1'b0;" in pause
    assert 'release dut.output_stage_final_valid;aux_finish;' in pause
    assert 'force dut.output_replay_accept' not in pause
    assert "else force dut.output_replay_accept=1'b0;" in text
    assert 'out_retirement_boundary<6' in text
    assert 'dut.output_request!==request_before' in text

@pytest.mark.parametrize('mutation',['none','force_stored_register'])
def test_pause_recovers_without_a_new_register_assignment(tmp_path,mutation):
    top=(experiment.RTL/(experiment.NEW+'.v')).read_text()
    declaration=re.search(r'  wire output_stage_final_valid = [^;]+;',top)[0]
    source=(experiment.RTL/'output_retirement_receipt_boundaries_v5.svh').read_text()
    target=re.search(r'force dut\.(\w+)=1\'b0;',source)[1]
    assert target=='output_stage_final_valid'
    if mutation=='force_stored_register':target='output_descriptor_valid'
    bench='''`timescale 1ns/1ps
module tb;
reg output_descriptor_valid=1,output_stage_valid=1,output_stage_last=1;
'''+declaration+'''
initial begin
 #1;force '''+target+'''=0;
 #10;release '''+target+''';
 #1;if(output_stage_final_valid!==1 || output_descriptor_valid!==1)
   $fatal(1,"pause did not recover without a new register assignment");
 $display("PAUSE_RELEASE_PASS");$finish;
end
endmodule
'''
    result=compile_run(tmp_path,bench)
    if mutation=='none':assert result.returncode==0 and 'PAUSE_RELEASE_PASS' in result.stdout,result.stdout
    else:assert result.returncode!=0 and 'pause did not recover' in result.stdout,result.stdout

def test_bad_certificate_is_generated_from_corrupted_metadata():
    source=(experiment.RTL/'output_retirement_receipt_boundaries_v5.svh').read_text()
    assert 'force dut.output_bank.input_metadata_certified' not in source
    assert "force dut.output_identity_stage.input_metadata=70'h1fffffffff;" in source
    assert 'dut.output_stage_identity_good!==0 || dut.output_bank_framing_fault_now!==1' in source
    assert 'release dut.output_identity_stage.input_metadata;' in source

def test_prepared_campaign_calls_each_group_once(tmp_path):
    path=tmp_path/'prepared';experiment.prepare(path,True)
    text=(path/'tb_fft_buffered_forward.sv').read_text()
    bodies=dict(re.findall(r'task automatic (\w+)[^;]*;(.*?)endtask',text,re.S))
    visited=[]
    def visit(name):
        assert name not in visited,'duplicate or recursive campaign group'
        visited.append(name)
        for child in re.findall(r'\b(run_\w+)\s*;',bodies[name]):visit(child)
    visit('run_buffered_auxiliary')
    assert visited[-1]=='run_output_retirement_boundaries'
    assert len(visited)==9
    assert 'output_retirement_boundary(out_retirement_boundary)' in bodies[visited[-1]]
    assert 'out_retirement_boundary<6' in bodies[visited[-1]]

MAIN='OUTPUT_RETIREMENT_RECEIPT_PASS checks=10000 publications=18 retires=18 extra_holds=18 exact_publication=1 no_post_publication_write=1 receipt_retirement=1\n'
LINES=[f'OUTPUT_RETIREMENT_BOUNDARY_PASS boundary={n} fresh_reads=512 fresh_releases=1\n' for n in range(6)]
LINES+=['OUTPUT_RETIREMENT_BOUNDARIES_PASS cases=6 delayed_publication=1 pending_reset=1 checked_receipt=1\n']
def test_main_witness():assert experiment.witness(MAIN)['publications']==18
def test_auxiliary_witness():assert experiment.witness(MAIN+''.join(LINES),True)['auxiliary']
@pytest.mark.parametrize('missing',range(7))
def test_every_boundary_required(missing):
    lines=LINES.copy();del lines[missing]
    with pytest.raises(ValueError):experiment.witness(MAIN+''.join(lines),True)
@pytest.mark.parametrize('change',['duplicate','five_cases','fatal'])
def test_bad_protocol_evidence_rejected(change):
    text=MAIN+''.join(LINES)
    if change=='duplicate':text+=LINES[0]
    elif change=='five_cases':text=text.replace('cases=6','cases=5')
    else:text+='Fatal: invalid publication\n'
    with pytest.raises(ValueError):experiment.witness(text,True)

"""Executed mutants and four-state interface cases for staged ownership."""
import importlib.util
from pathlib import Path
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('command_model_negative',ROOT/'tests/test_starlink_descriptor_commands.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

@pytest.mark.parametrize('change',['early_apply','accept_busy','ignore_tag','drop_response','ignore_abort','wrap','truncate'])
def test_unsafe_runtime_mutants_fail(tmp_path,monkeypatch,change):
    original=b.RTL.read_text()
    mutations={
        'early_apply':('if (pending) begin','if (pending || command_valid) begin'),
        'accept_busy':('!fault_q && !pending && !response_pending &&','!fault_q && !response_pending &&'),
        'ignore_tag':('wire tag_match0 = command_tag === tag0;',"wire tag_match0 = 1'b1;"),
        'drop_response':('if (response_pending && response_ready)','if (response_pending)'),
        'ignore_abort':('end else if (abort_now || fault_q) begin','end else if (fault_q) begin'),
        'wrap':('if (&next_tag) exhausted<=1;','if (&next_tag) next_tag<=0;'),
        'truncate':('descriptor0<=pending_descriptor;',"descriptor0<={1'b0,pending_descriptor[DESCRIPTOR_WIDTH-2:0]};"),
    }
    before,after=mutations[change];assert original.count(before)==1
    rtl=tmp_path/'mutant.v';rtl.write_text(original.replace(before,after,1));monkeypatch.setattr(b,'RTL',rtl)
    c=b.command;t=b.transaction
    if change=='ignore_tag':seq=[c(reset=0)]+t(desc=123)+t(op=1,tag=3)
    elif change=='drop_response':seq=[c(reset=0),c(valid=1,desc=123),c(ready=0)]+[c(ready=0)]*5
    elif change=='ignore_abort':seq=[c(reset=0),c(valid=1,desc=123),c(abort=1)]+[c()]*4
    elif change=='truncate':seq=[c(reset=0)]+t(desc=1<<69)+[c(lookup=1,query=0)]
    elif change=='wrap':
        seq=[c(reset=0)]
        for tag in range(4):seq+=t(desc=tag)+t(op=1,tag=tag)+t(op=2,tag=tag)
        seq += [c(valid=1,desc=9)]*3
    else:seq=[c(reset=0)]+t(desc=123)+[c()]*3
    with pytest.raises(AssertionError):b.simulate(tmp_path,2,seq)
    assert 'FATAL' in (tmp_path/'run.log').read_text()

@pytest.mark.parametrize('value',['x','z'])
@pytest.mark.parametrize('signal',['command_valid','response_ready','abort_epoch','command_opcode','command_tag','lookup_valid','lookup_tag'])
def test_unknown_controls_and_tags_do_not_authorize(tmp_path,signal,value):
    b.simulate(tmp_path,32,[b.command(reset=0),b.command()])
    declarations=(tmp_path/'bench.sv').read_text().split('initial begin\n',1)[0]
    read_only=signal.startswith('lookup')
    delayed=signal in ('command_tag','command_opcode')
    setup='send(1);' if read_only else ''
    issue='command_valid=1;command_opcode=1;command_tag=0;' if delayed else ''
    checks='''if(fault!==0 || lookup_found!==0 || lookup_committed!==0 || committed!==1)
      $fatal(1,"unknown query affected ownership");''' if read_only else (
        '''if(fault!==0 || command_ready!==1) $fatal(1,"tag/op validation was not staged");
  @(posedge clk);#0.1;
  if(fault!==1 || response_valid!==0 || lookup_found!==0) $fatal(1,"bad staged command authorized output");''' if delayed else
        '''if(fault!==1 || command_ready!==0 || response_valid!==0 || lookup_found!==0)
      $fatal(1,"unknown scalar did not immediately fence");
  @(posedge clk);#0.1;''')
    persistent='' if read_only else '''
  command_valid=0;response_ready=1;abort_epoch=0;command_opcode=0;command_tag=0;
  @(posedge clk);#0.1;
  if(fault!==1 || response_valid!==0) $fatal(1,"bad command escaped quarantine");
'''
    body='''task send(input [1:0] opcode);
begin
  @(negedge clk);command_valid=1;command_opcode=opcode;command_tag=0;command_descriptor=70'h123456;
  #1;if(command_ready!==1) $fatal(1,"setup not ready");
  @(posedge clk);#0.1;command_valid=0;
  @(posedge clk);#0.1;if(response_valid!==1) $fatal(1,"setup response missing");
  @(posedge clk);#0.1;if(response_valid!==0) $fatal(1,"setup response not consumed");
end
endtask
initial begin
  @(negedge clk);resetn=0;
  @(negedge clk);resetn=1;
  send(0);
  '''+setup+'''
  @(negedge clk);lookup_valid=1;lookup_tag=0;
  '''+issue+signal+"='"+value+''';
  #1;
  '''+checks+persistent+'''
  $display("COMMANDS_FOUR_STATE_PASS");$finish(0);
end
endmodule
'''
    bench=tmp_path/'four_state.sv';bench.write_text(declarations+body)
    p=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'four_sim'),str(b.RTL),str(bench)],capture_output=True,text=True,timeout=30)
    (tmp_path/'four_compile.log').write_text(p.stdout+p.stderr)
    assert p.returncode==0,p.stdout+p.stderr
    p=subprocess.run(['vvp',str(tmp_path/'four_sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'four_run.log').write_text(p.stdout+p.stderr)
    assert p.returncode==0 and p.stdout.splitlines()==['COMMANDS_FOUR_STATE_PASS'],p.stdout+p.stderr

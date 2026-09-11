from pathlib import Path
import re
import subprocess
import sys
import pytest
from tests.test_starlink_private_forward_capture import REFERENCE_INSTANCE
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import balanced_forward_identity_experiment as experiment
import balanced_forward_identity_transform as transform
RTL=experiment.RTL

@pytest.mark.parametrize('original,new,changes',[
    (experiment.base.NEW,experiment.NEW,transform.TOP_CHANGES),
    ('starlink_pss_forward_return_bank',experiment.BANK,transform.BANK_CHANGES)])
def test_exact_combinational_delta(original,new,changes):
    a=(RTL/(original+'.v')).read_text();b=(RTL/(new+'.v')).read_text()
    assert transform.transform(a,changes)==b and transform.undo(b,changes)==a

def compile_run(tmp_path,bench,sources=(),case=None):
    path=tmp_path/'bench.sv';path.write_text(bench)
    command=['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(path),*map(str,sources)]
    build=subprocess.run(command,capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(build.stdout+build.stderr);assert build.returncode==0,build.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')]+([] if case is None else [f'+CASE={case}']),capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result

@pytest.mark.parametrize('case',range(21))
def test_bank_current_controls_and_valid_payload_exact(tmp_path,case):
    reference=(RTL/'starlink_pss_forward_return_bank.v').read_text().replace('module starlink_pss_forward_return_bank #(','module bank_reference #(',1)
    (tmp_path/'reference.v').write_text(reference)
    observer=REFERENCE_INSTANCE.replace('  task automatic compare;','  task automatic compare;')
    # Unlike the older private-progress experiment, this change may not alter
    # any cursor/exponent value, even behind quarantine.
    observer=observer.replace('        private_differences=private_differences+1;',
        '        $fatal(1,"balanced comparison changed private progress");')
    bench=(RTL/'tb_forward_return_bank.sv').read_text().replace('starlink_pss_forward_return_bank dut(',experiment.BANK+' dut(',1)
    assert experiment.BANK+' dut(' in bench
    bench=bench.replace('\nendmodule','\n'+observer+'\nendmodule',1)
    result=compile_run(tmp_path,bench,[RTL/(experiment.BANK+'.v'),tmp_path/'reference.v'],case)
    assert result.returncode==0,result.stdout+result.stderr
    row=re.search(r'PRIVATE_FORWARD_CAPTURE_EQ checks=(\d+) private_differences=0 current_exact=1 valid_payload_exact=1',result.stdout)
    assert row and int(row[1])>2000,result.stdout

@pytest.mark.parametrize('mutation',['none','omit_high_bit','omit_middle_tile'])
def test_comparison_four_state_bits_and_random_vectors(tmp_path,mutation):
    source=(RTL/(experiment.BANK+'.v')).read_text()
    start=source.index('  (* keep = "true" *) wire [23:0]')
    end=source.index('  wire capture_bad =',start)
    fragment=source[start:end]
    if mutation=='omit_high_bit':fragment=fragment.replace('capture_descriptor[69] == descriptor[69]',"1'b1")
    if mutation=='omit_middle_tile':fragment=fragment.replace('wire capture_descriptor_equal = &capture_descriptor_tiles_equal;',"wire capture_descriptor_equal = &{capture_descriptor_tiles_equal[3:2],capture_descriptor_tiles_equal[0]};")
    bench='''`timescale 1ns/1ps
module tb;
reg [69:0] descriptor,capture_descriptor;
integer bit_index,n,seed=32'h526913ab,checks=0;
'''+fragment+'''
task automatic compare;
begin
  #1;
  if(capture_descriptor_equal !== (capture_descriptor==descriptor))$fatal(1,"four-state comparison differs");
  if((capture_descriptor_equal!==1'b1) !== ((capture_descriptor==descriptor)!==1'b1))$fatal(1,"fault authority differs");
  checks=checks+1;
end
endtask
initial begin
  descriptor=0;capture_descriptor=0;compare;
  for(bit_index=0;bit_index<70;bit_index=bit_index+1)begin
    descriptor=0;capture_descriptor=70'b1<<bit_index;compare;
    capture_descriptor[bit_index]=1'bx;compare;
    capture_descriptor[bit_index]=1'bz;compare;
    descriptor[bit_index]=1'bz;compare;
    capture_descriptor=~descriptor;compare;
  end
  for(n=0;n<20000;n=n+1)begin
    descriptor={$random(seed),$random(seed),$random(seed)};
    capture_descriptor={$random(seed),$random(seed),$random(seed)};
    if(n%4==0)capture_descriptor=descriptor;
    if(n%8==1)capture_descriptor[n%70]=1'bx;
    if(n%8==2)capture_descriptor[n%70]=1'bz;
    if(n%8==3)begin descriptor[n%70]=1'bx;capture_descriptor=descriptor;end
    compare;
  end
  $display("BALANCED_COMPARISON_PASS checks=%0d",checks);$finish;
end
endmodule
'''
    result=compile_run(tmp_path,bench)
    if mutation=='none':assert result.returncode==0 and 'BALANCED_COMPARISON_PASS checks=20351' in result.stdout,result.stdout
    else:assert result.returncode!=0 and 'four-state comparison differs' in result.stdout,result.stdout

GOOD='BALANCED_FORWARD_IDENTITY_PASS checks=10000 captures=9216 same_edge=1 four_state_exact=1\n'
def test_actual_witness():assert experiment.witness(GOOD)['same_edge'] is True
@pytest.mark.parametrize('log',['',GOOD+GOOD,GOOD+'FATAL\n',GOOD.replace('checks=10000','checks=9999'),
    GOOD.replace('captures=9216','captures=9215'),GOOD.replace('same_edge=1','same_edge=0'),GOOD.replace('four_state_exact=1','four_state_exact=0')])
def test_incomplete_actual_witness_rejected(log):
    with pytest.raises(ValueError):experiment.witness(log)

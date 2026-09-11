"""Original ROM comparison plus an independently offered, unpublished beat.

The local test models the caller's fault quarantine by withholding all subsequent
offers until flush. Actual FFT tests separately prove that caller behavior.
"""
import importlib.util
from pathlib import Path
import re

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('kernel_payload',ROOT/'tests/test_starlink_private_kernel_payload.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)

def ordinal_bench():
    text=base.bench()
    declarations='''reg private_only=0;
wire ready3,valid3,last3;wire [17:0] ki3,kq3;wire [8:0] bin3;wire [4:0] exp3;wire [63:0] start3;wire [5:0] flags3;
'''
    text=text.replace('module tb;\n','module tb;\n'+declarations,1)
    matches=re.findall(r'starlink_pss_kernel_rom #\([^;]+?\) d2\([^;]+?\);',text,re.S)
    assert len(matches)==1
    instance=matches[0].replace(') d2(',') d3(')
    instance=re.sub(r'(ready|valid|last|ki|kq|bin|exp|start|flags)2',r'\g<1>3',instance)
    instance=instance.replace('.PRIVATE_PAYLOAD_BUBBLES(1)', '.PRIVATE_PAYLOAD_BUBBLES(1),.PRIVATE_ORDINAL_ADVANCE(1)')
    instance=instance.replace('.input_valid(iv)', '.input_valid(iv),.input_private_valid(iv || private_only)')
    assert text.count('always @(posedge clk) begin\n')==1
    text=text.replace('always @(posedge clk) begin\n',instance+'\nalways @(posedge clk) begin\n',1)
    before='!=={ready2,valid2,flags2})'
    assert text.count(before)==1
    text=text.replace(before,'!=={ready2,valid2,flags2} || {ready0,valid0,flags0}!=={ready3,valid3,flags3})')
    before='!=={ki2,kq2,bin2,exp2,last2,start2}))'
    assert text.count(before)==1
    text=text.replace(before,'!=={ki2,kq2,bin2,exp2,last2,start2} || {ki0,kq0,bin0,exp0,last0,start0}!=={ki3,kq3,bin3,exp3,last3,start3}))')
    before='$display("PRIVATE_KERNEL_PASS healthy=4096'
    assert text.count(before)==1
    extra='''clear_epoch;iv=0;ib=0;il=0;ie=7;istart=64'ha5a5a5a500000000;private_only=1;
tick;private_only=0;
if(d3.expected_bin_index!==1 || valid3 || flags3[0] || flags3[2] || d3.have_previous_block)
  $fatal(1,"private-only ordinal advance gained public authority");
repeat(8)begin tick;if(valid3 || flags3[0] || flags3[2]) $fatal(1,"withheld beat became public");end
flush=1;tick;flush=0;tick;
if(d3.expected_bin_index!==0 || valid3) $fatal(1,"private ordinal survived flush");
send(0,0);while(valid0)tick;
$display("PRIVATE_ORDINAL_PASS withheld=1 no_publication=1 flush_recovery=1");
'''
    return text.replace(before,extra+before,1)

def test_private_ordinal_preserves_original_public_contract(tmp_path):
    result=base.execute(tmp_path,base.RTL.read_text(),ordinal_bench())
    assert result.returncode==0,result.stdout+result.stderr
    assert 'PRIVATE_KERNEL_PASS healthy=4096 malformed=4 flush=1' in result.stdout
    assert 'PRIVATE_ORDINAL_PASS withheld=1 no_publication=1 flush_recovery=1' in result.stdout

@pytest.mark.parametrize('change',['no_advance','ignore_backpressure','private_publish','no_flush'])
def test_private_ordinal_contract_mutants_rejected(tmp_path,change):
    before,after={
        'no_advance':('if (PRIVATE_ORDINAL_ADVANCE && private_ordinal_accept)', 'if (1\'b0 && private_ordinal_accept)'),
        'ignore_backpressure':('if (PRIVATE_ORDINAL_ADVANCE && private_ordinal_accept)', 'if (PRIVATE_ORDINAL_ADVANCE && input_private_valid)'),
        'private_publish':('if (input_accept) begin', 'if (input_accept || (PRIVATE_ORDINAL_ADVANCE && private_ordinal_accept)) begin'),
        'no_flush':('expected_bin_index <= 0;','if (!PRIVATE_ORDINAL_ADVANCE || !flush) expected_bin_index <= 0;'),
    }[change]
    source=base.RTL.read_text()
    if change=='no_flush':
        # Only the common reset/flush assignment; the default-mode end-of-block
        # reset remains untouched.
        before='      expected_bin_index <= 0;';after='      '+after
    assert source.count(before)==1
    result=base.execute(tmp_path,source.replace(before,after,1),ordinal_bench())
    assert result.returncode!=0 and 'FATAL' in result.stdout and 'watchdog' not in result.stdout,result.stdout

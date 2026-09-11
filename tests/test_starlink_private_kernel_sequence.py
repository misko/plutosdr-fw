"""Original-ROM equivalence, stride faults and private final quarantine."""
import importlib.util
from pathlib import Path
import re
from unittest.mock import patch

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('sequence_payload',ROOT/'tests/test_starlink_private_kernel_payload.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)

def sequence_bench():
    text=base.bench()
    text=text.replace('module tb;\n','''module tb;
reg private_only=0;
wire ready3,valid3,last3;wire [17:0] ki3,kq3;wire [8:0] bin3;wire [4:0] exp3;wire [63:0] start3;wire [5:0] flags3;
''',1)
    match=re.findall(r'starlink_pss_kernel_rom #\([^;]+?\) d2\([^;]+?\);',text,re.S)
    assert len(match)==1
    instance=match[0].replace(') d2(',') d3(')
    instance=re.sub(r'(ready|valid|last|ki|kq|bin|exp|start|flags)2',r'\g<1>3',instance)
    instance=instance.replace('.PRIVATE_PAYLOAD_BUBBLES(1)', '.PRIVATE_PAYLOAD_BUBBLES(1),.PRIVATE_SEQUENCE_ADVANCE(1)')
    instance=instance.replace('.input_valid(iv)', '.input_valid(iv),.input_private_valid(iv || private_only)')
    text=text.replace('always @(posedge clk) begin\n',instance+'\nalways @(posedge clk) begin\n',1)
    before='!=={ready2,valid2,flags2})';assert text.count(before)==1
    text=text.replace(before,'!=={ready2,valid2,flags2} || {ready0,valid0,flags0}!=={ready3,valid3,flags3})')
    before='!=={ki2,kq2,bin2,exp2,last2,start2}))';assert text.count(before)==1
    text=text.replace(before,'!=={ki2,kq2,bin2,exp2,last2,start2} || {ki0,kq0,bin0,exp0,last0,start0}!=={ki3,kq3,bin3,exp3,last3,start3}))')
    before='$display("PRIVATE_KERNEL_PASS healthy=4096';assert text.count(before)==1
    extra=r'''
// A full prior block must make wrong next-block stride a public fault.
clear_epoch;
for(pos=0;pos<512;pos=pos+1)send(0,pos);
while(valid0)tick;
iv=1;ib=0;il=0;ie=8;istart=64'ha5a5a5a500000000+448;
@(posedge clk);while(!ready0)@(posedge clk);#0.1;@(negedge clk);#0.1;iv=0;
repeat(3)tick;
if(!flags3[5] || valid3) $fatal(1,"wrong next-block stride escaped");
// Privately advance first bin, without publishing or reporting acceptance.
clear_epoch;iv=0;ib=0;il=0;ie=7;istart=64'ha5a5a5a500000000;private_only=1;
tick;private_only=0;
if(d3.expected_bin_index!==1 || valid3 || flags3[0] || flags3[2] || d3.have_previous_block)
  $fatal(1,"private first sequence state/authority");
repeat(8)begin tick;if(valid3 || flags3[0] || flags3[2]) $fatal(1,"withheld first published");end
flush=1;tick;flush=0;tick;
if(d3.expected_bin_index!==0 || d3.have_previous_block || d3.expected_next_block_start!==0)
  $fatal(1,"private sequence survived flush");
// A rejected final private offer updates ALL private sequence state, but not
// the public completion pulse. Caller offers remain withheld until flush.
clear_epoch;
for(pos=0;pos<511;pos=pos+1)send(0,pos);
while(valid0)tick;
iv=0;ib=511;il=1;ie=7;istart=64'ha5a5a5a500000000;private_only=1;
tick;private_only=0;
if(d3.expected_bin_index!==0 || !d3.have_previous_block ||
   d3.expected_next_block_start!==64'ha5a5a5a5000001bf || valid3 || flags3[0] || flags3[2])
  $fatal(1,"private final sequence state/authority");
repeat(8)begin tick;if(valid3 || flags3[0] || flags3[2]) $fatal(1,"withheld final published");end
flush=1;tick;flush=0;tick;
if(d3.expected_bin_index!==0 || d3.have_previous_block || d3.expected_next_block_start!==0)
  $fatal(1,"private final survived flush");
send(0,0);while(valid0)tick;
$display("PRIVATE_SEQUENCE_PASS withheld_first=1 withheld_final=1 bad_stride=1 flush_recovery=1");
'''
    return text.replace(before,extra+before,1)

def execute(tmp_path,source):
    bench=sequence_bench()
    with patch.object(base,'bench',return_value=bench):
        return base.execute(tmp_path,source)

def test_private_sequence_preserves_original_public_contract(tmp_path):
    result=execute(tmp_path,base.RTL.read_text())
    assert result.returncode==0,result.stdout+result.stderr
    assert 'PRIVATE_SEQUENCE_PASS withheld_first=1 withheld_final=1 bad_stride=1 flush_recovery=1' in result.stdout

@pytest.mark.parametrize('change',['no_advance','ignore_backpressure','private_publish','no_flush','no_next_capture','no_previous','bad_stride'])
def test_private_sequence_mutants_rejected(tmp_path,change):
    before,after={
        'no_advance':('if (PRIVATE_SEQUENCE_ADVANCE && private_sequence_accept)',"if (1'b0 && private_sequence_accept)"),
        'ignore_backpressure':('if (PRIVATE_SEQUENCE_ADVANCE && private_sequence_accept)','if (PRIVATE_SEQUENCE_ADVANCE && input_private_valid)'),
        'private_publish':('if (input_accept) begin','if (input_accept || (PRIVATE_SEQUENCE_ADVANCE && private_sequence_accept)) begin'),
        'no_flush':('      expected_bin_index <= 0;', '      if (!PRIVATE_SEQUENCE_ADVANCE || !flush) expected_bin_index <= 0;'),
        'no_next_capture':('expected_next_block_start <= input_block_start_index + VALID_RESULTS_PER_BLOCK;', 'expected_next_block_start <= expected_next_block_start;'),
        'no_previous':("          have_previous_block <= 1'b1;", "          have_previous_block <= 1'b0;"),
        'bad_stride':('expected_next_block_start <= input_block_start_index + VALID_RESULTS_PER_BLOCK;', 'expected_next_block_start <= input_block_start_index + 448;'),
    }[change]
    source=base.RTL.read_text()
    # Match indentation literally, without treating an inner assignment's
    # suffix as a second occurrence of the reset/flush assignment.
    if change in ('no_flush','no_previous'):
        matches=list(re.finditer('^'+re.escape(before)+'$',source,re.M));assert len(matches)==1
        m=matches[0];source=source[:m.start()]+after+source[m.end():]
    else:
        assert source.count(before)==1;source=source.replace(before,after,1)
    result=execute(tmp_path,source)
    assert result.returncode!=0 and 'FATAL' in result.stdout and 'watchdog' not in result.stdout,result.stdout

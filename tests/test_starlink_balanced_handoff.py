"""The complete current handoff equality, not a delayed identity certificate."""
import hashlib
from pathlib import Path
import re
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
PARENT=Path('/dev/shm/starlink-reset-cdc.nCo3Wwmo/prepared-v1')
TOP='starlink_pss_fft_staged_output_impl.v'
OLD="  wire forward_handoff_identity = product_bank_metadata ==\n    {1'b1, engine_metadata[68:5], return_metadata[4:0]};\n"


def undo_handoff(text):
    if 'starlink_pss_completion_mailbox_stage' in text:
        from tests.test_starlink_completion_mailbox_stage import undo_adapter_top
        text=undo_adapter_top(text)
    text,count=re.subn(r'  // BEGIN BALANCED HANDOFF IDENTITY\n.*?  // END BALANCED HANDOFF IDENTITY\n',
                      lambda _:OLD,text,flags=re.S)
    assert count==1
    return text


def undo_bench(text):
    if '// BEGIN COMPLETION MAILBOX WITNESS' in text:
        from tests.test_starlink_completion_mailbox_stage import undo_completion_bench
        text=undo_completion_bench(text)
    text,count=re.subn(r'  // BEGIN BALANCED HANDOFF WITNESS\n.*?  // END BALANCED HANDOFF WITNESS\n','',text,flags=re.S)
    assert count==1
    for spaces,mode in [(6,'AUXILIARY'),(4,'MAIN')]:
        line=' '*spaces+'report_balanced_handoff; // BALANCED HANDOFF '+mode+'\n'
        assert text.count(line)==1
        text=text.replace(line,'',1)
    return text


def test_exact_top_bench_delta_and_runtime_inventory():
    assert hashlib.sha256((PARENT/'SHA256SUMS').read_bytes()).hexdigest()=='28b4f9dbf7e61175b9dba8b87136438f6a134b88f111f0afb23e03ea344c736a'
    assert undo_handoff((RTL/TOP).read_text())==(PARENT/TOP).read_text()
    assert undo_bench((RTL/'tb_fft_staged_output.sv').read_text())==(PARENT/'tb_fft_staged_output.sv').read_text()
    names=(PARENT/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    assert len(names)==22
    for name in names:
        if name!=TOP and (RTL/name).exists():assert (RTL/name).read_bytes()==(PARENT/name).read_bytes(),name


@pytest.mark.parametrize('mutant',[None,'skip_top','skip_middle','ignore_exponent'])
def test_four_state_complete_comparison(tmp_path,mutant):
    source=(RTL/TOP).read_text()
    block=re.search(r'  // BEGIN BALANCED HANDOFF IDENTITY\n.*?  // END BALANCED HANDOFF IDENTITY\n',source,re.S)[0]
    if mutant=='skip_top':block=block.replace('wire forward_handoff_identity = &handoff_group_equal;',
                                           'wire forward_handoff_identity = &handoff_leaf_equal[22:0];')
    elif mutant=='skip_middle':block=block.replace('wire forward_handoff_identity = &handoff_group_equal;',
                                                 'wire forward_handoff_identity = &{handoff_group_equal[3:2],handoff_group_equal[0]};')
    elif mutant=='ignore_exponent':block=block.replace('return_metadata[4:0]','product_bank_metadata[4:0]')
    bench='''`timescale 1ns/1ps
module tb;
reg [69:0] product_bank_metadata,engine_metadata;
reg [74:0] return_metadata;
__BLOCK__
integer checks=0,bitno,kind,side,n;
reg [69:0] expected;
task check;begin #1;
 if(forward_handoff_identity !== (product_bank_metadata == {1'b1,engine_metadata[68:5],return_metadata[4:0]}))
  $fatal(1,"current handoff equality mismatch");
 checks=checks+1;
end endtask
task seed;begin
 engine_metadata=70'h155aa55aa55aa55aa55;return_metadata=75'h123456789abcdef0015;
 product_bank_metadata={1'b1,engine_metadata[68:5],return_metadata[4:0]};
end endtask
initial begin
 seed;check;
 for(side=0;side<2;side=side+1)for(bitno=0;bitno<70;bitno=bitno+1)for(kind=0;kind<3;kind=kind+1)begin
  seed;
  if(side==0)case(kind)0:product_bank_metadata[bitno]=~product_bank_metadata[bitno];1:product_bank_metadata[bitno]=1'bx;2:product_bank_metadata[bitno]=1'bz;endcase
  else if(bitno<5)case(kind)0:return_metadata[bitno]=~return_metadata[bitno];1:return_metadata[bitno]=1'bx;2:return_metadata[bitno]=1'bz;endcase
  else if(bitno<69)case(kind)0:engine_metadata[bitno]=~engine_metadata[bitno];1:engine_metadata[bitno]=1'bx;2:engine_metadata[bitno]=1'bz;endcase
  else product_bank_metadata[69]=0;
  check;
  // A known mismatch dominates an unrelated unknown in logical equality.
  product_bank_metadata[(bitno+1)%70]=~({1'b1,engine_metadata[68:5],return_metadata[4:0]} >> ((bitno+1)%70));check;
 end
 repeat(1000)begin
  engine_metadata={$random,$random,$random};return_metadata={$random,$random,$random};
  product_bank_metadata={$random,$random,$random};check;
  product_bank_metadata={1'b1,engine_metadata[68:5],return_metadata[4:0]};check;
 end
 $display("BALANCED_HANDOFF_PASS checks=%0d exact_current=1 four_state=1",checks);$finish;
end
endmodule
'''.replace('__BLOCK__',block)
    path=tmp_path/'tb.sv';path.write_text(bench)
    result=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(path)],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    if mutant is None:assert result.returncode==0 and 'checks=2841' in result.stdout,result.stdout+result.stderr
    else:assert result.returncode!=0 and 'current handoff equality mismatch' in result.stdout

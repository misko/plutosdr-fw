"""Selected-bank equality remains current and exact, including unknown phase."""
from pathlib import Path
import re
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
PARENT=Path('/dev/shm/starlink-private-quarantine.tu8FkVR0/prepared-v1')
TOP='starlink_pss_fft_staged_output_impl.v'

def strip_block(text,label,replacement=''):
    text,n=re.subn(r' *// BEGIN '+label+r'\n.*? *// END '+label+r'\n',lambda _:replacement,text,flags=re.S)
    assert n==1;return text

def undo_top(text):
    if 'parameter integer MONOTONIC_OUTER_RESET' in text:
        from tests.test_starlink_monotonic_reset_release import undo_top as undo_reset
        text=undo_reset(text)
    text=strip_block(text,'SPLIT PREFLIGHT PROFILE')
    text=strip_block(text,'SPLIT PREFLIGHT COMPARISON','      assign preflight_identity_equal[comparison] = &group_equal;\n')
    before='  parameter integer PRIVATE_QUARANTINE_OFFER = 0,\n  parameter integer SPLIT_PREFLIGHT_IDENTITY = 0'
    assert text.count(before)==1;return text.replace(before,'  parameter integer PRIVATE_QUARANTINE_OFFER = 0',1)

def undo_bench(text):
    if '// BEGIN MONOTONIC RESET WITNESS' in text:
        from tests.test_starlink_monotonic_reset_release import undo_bench as undo_reset
        text=undo_reset(text)
    text=strip_block(text,'SPLIT PREFLIGHT WITNESS')
    for value in ['      report_split_preflight; // SPLIT PREFLIGHT REPORT\n',',.SPLIT_PREFLIGHT_IDENTITY(1)']:
        assert text.count(value)==1;text=text.replace(value,'',1)
    return text

def test_exact_source_delta():
    assert undo_top((RTL/TOP).read_text())==(PARENT/TOP).read_text()
    name='tb_fft_staged_output.sv';assert undo_bench((RTL/name).read_text())==(PARENT/name).read_text()
    assert (ROOT/'tools/staged_fft_experiment.tcl').read_text().replace(' MONOTONIC_OUTER_RESET=1','',1).replace(' SPLIT_PREFLIGHT_IDENTITY=1','',1)==(PARENT/'staged_fft_experiment.tcl').read_text()
    names=(PARENT/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    assert len(names)==22
    for name in names:
        if name!=TOP and (RTL/name).exists():
            text=(RTL/name).read_text()
            if name=='starlink_pss_reset_receipt_barrier.v' and '// BEGIN MONOTONIC RESET RELEASE' in text:
                from tests.test_starlink_monotonic_reset_release import undo_barrier
                text=undo_barrier(text)
            assert text==(PARENT/name).read_text(),name

def run(tmp_path,mode='1',registered=1,seed=1,mutation=None):
    text=(RTL/TOP).read_text()
    start=text.index('  wire [1:0] preflight_identity_equal;')
    block=text[start:text.index('  wire descriptor_header_valid',start)]
    profile=re.search(r'    // BEGIN SPLIT PREFLIGHT PROFILE\n.*?    // END SPLIT PREFLIGHT PROFILE\n',text,re.S)[0]
    changes={
      'wrong_bank':("preflight_phase === 1'b1 ? bank_equal[1]","preflight_phase === 1'b1 ? bank_equal[0]"),
      'omit_high_bit':('assign bank_equal[bank] = &bank_group_equal;','assign bank_equal[bank] = &bank_leaf_equal[22:0];'),
      'unknown_merge':("preflight_phase === 1'b1 ? bank_equal[1] : &group_equal;","preflight_phase === 1'b1 ? bank_equal[1] : (preflight_phase ? bank_equal[1] : bank_equal[0]);"),
      'ignore_live':('bank_metadata[3*leaf +: BITS] == engine_metadata[3*leaf +: BITS]',"1'b1")}
    if mutation:
        before,after=changes[mutation];assert block.count(before)==1;block=block.replace(before,after,1)
    bench='''`timescale 1ns/1ps
module tb;
localparam REGISTERED_SCHEDULING=__REGISTERED__,SPLIT_PREFLIGHT_IDENTITY=__MODE__;
reg preflight_phase=0;
reg [69:0] source_metadata=0,product_bank_metadata=0,engine_metadata=0,expected_product_metadata=0;
wire [69:0] preflight_metadata=preflight_phase ? product_bank_metadata : source_metadata;
__BLOCK__
initial begin
__PROFILE__
end
integer n,side,b,k,p,checks=0;reg [31:0] rng=__SEED__;
function val(input integer n);case(n)0:val=0;1:val=1;2:val=1'bx;3:val=1'bz;endcase endfunction
task check;begin #0.001;
 if(preflight_identity_equal!=={engine_metadata==expected_product_metadata,preflight_metadata==engine_metadata})
   $fatal(1,"current preflight equality mismatch");checks=checks+1;
end endtask
task init_equal;begin
 source_metadata=70'h155555555555555555;product_bank_metadata=source_metadata;
 engine_metadata=source_metadata;expected_product_metadata=source_metadata;
end endtask
initial begin
 for(side=0;side<4;side=side+1)for(b=0;b<70;b=b+1)for(k=0;k<4;k=k+1)for(p=0;p<4;p=p+1)begin
   init_equal;preflight_phase=val(p);
   case(side)0:source_metadata[b]=val(k);1:product_bank_metadata[b]=val(k);2:engine_metadata[b]=val(k);3:expected_product_metadata[b]=val(k);endcase
   check;
 end
 // Equality does not distribute through X/Z vector selection.
 for(p=2;p<4;p=p+1)begin
   source_metadata=0;product_bank_metadata=3;engine_metadata=1;expected_product_metadata=1;
   preflight_phase=val(p);check;
 end
 for(n=0;n<4096;n=n+1)begin
   rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);
   source_metadata={rng,rng,rng[5:0]};product_bank_metadata=source_metadata;
   engine_metadata=source_metadata;expected_product_metadata=source_metadata;preflight_phase=val(n%4);
   case(n%4)0:source_metadata[rng%70]=val((rng>>9)%4);1:product_bank_metadata[rng%70]=val((rng>>9)%4);
     2:engine_metadata[rng%70]=val((rng>>9)%4);3:expected_product_metadata[rng%70]=val((rng>>9)%4);endcase
   check;
 end
 if(checks!=8578)$fatal(1,"short preflight campaign");
 $display("SPLIT_PREFLIGHT_COMPONENT_PASS checks=%0d four_state=1 current_exact=1",checks);$finish;
end
endmodule
'''.replace('__REGISTERED__',str(registered)).replace('__MODE__',str(mode)).replace('__BLOCK__',block).replace('__PROFILE__',profile).replace('__SEED__',str(seed))
    path=tmp_path/'bench.sv';path.write_text(bench)
    result=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(path)],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr);assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr);return result

@pytest.mark.parametrize('mode,registered',[(0,0),(0,1),(1,1)])
@pytest.mark.parametrize('seed',[1,7,12345,918273])
def test_current_four_state_comparison(tmp_path,mode,registered,seed):
    result=run(tmp_path,mode,registered,seed);assert result.returncode==0 and 'SPLIT_PREFLIGHT_COMPONENT_PASS checks=8578' in result.stdout,result.stdout+result.stderr

@pytest.mark.parametrize('mode,registered',[(1,0),(2,1),("32'bx",1),("32'bz",1)])
def test_invalid_profile_rejected(tmp_path,mode,registered):
    result=run(tmp_path,mode,registered);assert result.returncode!=0 and 'split preflight requires' in result.stdout,result.stdout+result.stderr

@pytest.mark.parametrize('mutation',['wrong_bank','omit_high_bit','unknown_merge','ignore_live'])
def test_unsafe_comparison_rejected(tmp_path,mutation):
    result=run(tmp_path,mutation=mutation);assert result.returncode!=0 and 'current preflight equality mismatch' in result.stdout,result.stdout+result.stderr

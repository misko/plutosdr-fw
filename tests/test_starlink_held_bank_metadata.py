"""Limited source inverse and four-state wiring; live bank witness is separate."""
import hashlib
from pathlib import Path
import re
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
TOP=ROOT/'hdl/library/starlink_pss_acquisition/staged_control/starlink_pss_fft_staged_output_impl.v'
OLD=ROOT.parent/'staged-guardfacts-prepared-v1'/TOP.name

def test_complete_top_inverse():
    old=OLD.read_bytes()
    assert hashlib.sha256(old).hexdigest()=='b3511a70b97b91e3e9b4106ea0c9bab8df4f7a43a07ff30a5447cd522dc5d143'
    # Historical metadata-only inverse; today's full handoff delta has its own
    # complete inverse against this SHA-pinned parent.
    parent=ROOT.parent/'staged-heldmeta-prepared-v1'/TOP.name
    assert hashlib.sha256(parent.read_bytes()).hexdigest()=='ad60442023cacf132a79ca384fe0612b83d7014421b8d11a1d01762779fa4270'
    text=parent.read_text()
    start=text.index('  // BEGIN HELD BANK METADATA\n')
    end=text.index('  // END HELD BANK METADATA\n',start)+len('  // END HELD BANK METADATA\n')
    text=text[:start]+text[end:]
    assert text.count('.input_metadata(output_write_metadata)')==1
    text=text.replace('.input_metadata(output_write_metadata)',
        '.input_metadata(output_publication_busy ? {output_replay_tag,output_descriptor_payload[4:0]} :\n'
        '      {inverse_tag,guard_return_metadata[1][4:0]})',1)
    assert text==old.decode(),'unrelated runtime change'

def run(tmp_path,mutant=None):
    matches=re.findall(r'  wire \[36:0\] output_write_metadata = .*?;',TOP.read_text(),re.S)
    assert len(matches)==1
    declaration=matches[0]
    if mutant=='wrong_tag':declaration=declaration.replace('{inverse_tag,','{(inverse_tag ^ 32\'d1),')
    if mutant=='wrong_exponent':declaration=declaration.replace('guard_return_metadata[1][4:0]',"(guard_return_metadata[1][4:0] ^ 5'd1)")
    if mutant=='drop_fallback':declaration=declaration.replace('REGISTERED_SCHEDULING ?',"1'b1 ?")
    bench=r'''`timescale 1ns/1ps
module tb;
reg REGISTERED_SCHEDULING,output_publication_busy;
reg [31:0] inverse_tag,output_replay_tag;
reg [74:0] guard_return_metadata[0:1];
reg [74:0] output_descriptor_payload;
'''+declaration+r'''
function val(input integer n);case(n)0:val=0;1:val=1;2:val=1'bx;3:val=1'bz;endcase endfunction
integer m,b,k,v,cases=0;
reg [36:0] desired;
initial begin
 for(m=0;m<2;m=m+1)for(b=0;b<4;b=b+1)for(k=0;k<37;k=k+1)for(v=0;v<4;v=v+1)begin
   REGISTERED_SCHEDULING=m;output_publication_busy=val(b);
   inverse_tag=32'h13579bdf;guard_return_metadata[1]=75'h12;
   if(k<5)guard_return_metadata[1][k]=val(v);else inverse_tag[k-5]=val(v);
   output_replay_tag=32'hfdb97531;output_descriptor_payload=75'h07;
   #1;
   desired=m ? {inverse_tag,guard_return_metadata[1][4:0]} :
     (output_publication_busy ? {output_replay_tag,output_descriptor_payload[4:0]} :
       {inverse_tag,guard_return_metadata[1][4:0]});
   if(output_write_metadata!==desired)$fatal(1,"held metadata wiring/fallback");
   cases=cases+1;
 end
 $display("HELD_METADATA_WIRING_PASS cases=%0d fallback_exact=1",cases);$finish;
end
endmodule
'''
    path=tmp_path/'bench.sv';path.write_text(bench)
    result=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(path)],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result

def test_four_state_wiring_and_fallback(tmp_path):
    result=run(tmp_path)
    assert result.returncode==0 and 'HELD_METADATA_WIRING_PASS cases=1184 fallback_exact=1' in result.stdout,result.stdout+result.stderr

@pytest.mark.parametrize('mutant',['wrong_tag','wrong_exponent','drop_fallback'])
def test_bad_metadata_wiring_rejected(tmp_path,mutant):
    result=run(tmp_path,mutant)
    assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout+result.stderr

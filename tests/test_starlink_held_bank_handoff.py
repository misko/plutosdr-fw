"""Exact handoff delta and four-state wiring; ownership is checked by live FFT."""
import hashlib
from pathlib import Path
import re
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
TOP=ROOT/'hdl/library/starlink_pss_acquisition/staged_control/starlink_pss_fft_staged_output_impl.v'
OLD=ROOT.parent/'staged-heldmeta-prepared-v1'/TOP.name

def test_complete_handoff_inverse():
    old=OLD.read_bytes()
    assert hashlib.sha256(old).hexdigest()=='ad60442023cacf132a79ca384fe0612b83d7014421b8d11a1d01762779fa4270'
    parent=ROOT.parent/'staged-heldhandoff-prepared-v1'/TOP.name
    assert hashlib.sha256(parent.read_bytes()).hexdigest()=='dac566ab9dbca3fbdfb748610e05835cc315196d65dac8528bce2270e70cf3c4'
    text=parent.read_text()
    start=text.index('  // BEGIN HELD BANK HANDOFF\n')
    end=text.index('  // END HELD BANK HANDOFF\n',start)+len('  // END HELD BANK HANDOFF\n')
    text=text[:start]+text[end:]
    for name,expr in {
        'valid':'output_publication_busy ? output_replay_valid : guard_private_out[1]',
        'data':'output_publication_busy ? output_replay_data : guard_return_data[1]',
        'position':"output_publication_busy ? 9'd511 : guard_return_position[1]",
        'last':"output_publication_busy ? 1'b1 : guard_last_out[1]",
    }.items():
        before=f'.input_{name}(output_write_{name})';assert text.count(before)==1
        text=text.replace(before,f'.input_{name}({expr})',1)
    assert text==old.decode(),'unrelated runtime change'

def run(tmp_path,mutant=None):
    source=TOP.read_text();declarations=[]
    for name in ['valid','data','position','last']:
        found=re.findall(r'  wire (?:\[[^\]]+\] )?output_write_'+name+r' = .*?;',source,re.S)
        assert len(found)==1;declarations.append(found[0])
    text='\n'.join(declarations)
    changes={
        'and_offers':('guard_private_out[1] || output_replay_valid','guard_private_out[1] && output_replay_valid'),
        'wrong_data':('REGISTERED_SCHEDULING ? guard_return_data[1]',"REGISTERED_SCHEDULING ? (guard_return_data[1] ^ 36'd1)"),
        'wrong_position':('REGISTERED_SCHEDULING ? guard_return_position[1]',"REGISTERED_SCHEDULING ? 9'd511"),
        'wrong_last':('REGISTERED_SCHEDULING ? guard_last_out[1]',"REGISTERED_SCHEDULING ? 1'b1"),
        'drop_fallback':('REGISTERED_SCHEDULING ?',"1'b1 ?"),
    }
    if mutant:
        a,b=changes[mutant];assert a in text;text=text.replace(a,b)
    bench=r'''`timescale 1ns/1ps
module tb;
reg REGISTERED_SCHEDULING,output_publication_busy,output_replay_valid;
reg [1:0] guard_private_out,guard_last_out;
reg [35:0] guard_return_data[0:1];reg [35:0] output_replay_data;
reg [8:0] guard_return_position[0:1];
'''+text+r'''
function val(input integer n);case(n)0:val=0;1:val=1;2:val=1'bx;3:val=1'bz;endcase endfunction
integer m,b,p,r,k,v,cases=0;
reg want_valid,want_last;reg [35:0] want_data;reg [8:0] want_position;
initial begin
 for(m=0;m<2;m=m+1)for(b=0;b<4;b=b+1)for(p=0;p<4;p=p+1)for(r=0;r<4;r=r+1)
 for(k=0;k<46;k=k+1)for(v=0;v<4;v=v+1)begin
   REGISTERED_SCHEDULING=m;output_publication_busy=val(b);
   guard_private_out={val(p),1'b0};output_replay_valid=val(r);
   guard_return_data[1]=36'h123456789;output_replay_data=36'habcdef012;
   guard_return_position[1]=9'd73;guard_last_out=0;
   if(k<36)guard_return_data[1][k]=val(v);
   else if(k<45)guard_return_position[1][k-36]=val(v);else guard_last_out[1]=val(v);
   #1;
   want_valid=m ? (guard_private_out[1] || output_replay_valid) :
     (output_publication_busy ? output_replay_valid : guard_private_out[1]);
   want_data=m ? guard_return_data[1] : (output_publication_busy ? output_replay_data : guard_return_data[1]);
   want_position=m ? guard_return_position[1] : (output_publication_busy ? 9'd511 : guard_return_position[1]);
   want_last=m ? guard_last_out[1] : (output_publication_busy ? 1'b1 : guard_last_out[1]);
   if({output_write_valid,output_write_data,output_write_position,output_write_last} !==
      {want_valid,want_data,want_position,want_last})$fatal(1,"held handoff wiring/fallback");
   cases=cases+1;
 end
 $display("HELD_HANDOFF_WIRING_PASS cases=%0d fallback_exact=1",cases);$finish;
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

def test_four_state_handoff_wiring(tmp_path):
    result=run(tmp_path)
    assert result.returncode==0 and 'HELD_HANDOFF_WIRING_PASS cases=23552 fallback_exact=1' in result.stdout,result.stdout+result.stderr

@pytest.mark.parametrize('mutant',['and_offers','wrong_data','wrong_position','wrong_last','drop_fallback'])
def test_bad_handoff_wiring_rejected(tmp_path,mutant):
    result=run(tmp_path,mutant)
    assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout+result.stderr

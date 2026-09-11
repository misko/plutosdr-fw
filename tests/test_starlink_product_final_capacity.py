"""Held-LAST capacity isolation preserves retirement, payload and nonfinal flow."""
import hashlib
from pathlib import Path
import re
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
PARENT=Path('/dev/shm/starlink-product-integrated.1FSkuP/prepared-v2')
NAME='starlink_pss_product_identity_stage.v'


def test_exact_stage_delta_and_other_twenty_modules_unchanged():
    assert hashlib.sha256((PARENT/'SHA256SUMS').read_bytes()).hexdigest()=='b84f82584aa9adfd144efb9a1e82ca1731af4cb00425d82e9cb491e577969e84'
    pins=dict((name,digest) for digest,name in (line.split() for line in (PARENT/'SHA256SUMS').read_text().splitlines()))
    old=(PARENT/NAME).read_text();assert hashlib.sha256(old.encode()).hexdigest()==pins[NAME]
    text=(RTL/NAME).read_text()
    start=text.index('  // A held LAST cannot refill')
    end=text.index('  assign idle',start)
    text=text[:start]+'  assign input_ready = live && (!full || output_ready);\n'+text[end:]
    assert text==old
    names=(PARENT/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    assert len(names)==21
    for name in names:
        if name!=NAME and (RTL/name).exists():
            source=(RTL/name).read_bytes()
            if name=='starlink_pss_fft_staged_output_impl.v':
                from tests.test_starlink_split_product_capacity import undo_split_top
                source=undo_split_top(source.decode()).encode()
            assert hashlib.sha256(source).hexdigest()==pins[name],name


def run(tmp_path,mutant=None):
    source=(RTL/NAME).read_text()
    if mutant=='old_refill':source=source.replace("((output_last === 1'b0) && output_ready)",'output_ready',1)
    elif mutant=='pause_nonfinal':source=source.replace("((output_last === 1'b0) && output_ready)","1'b0",1)
    elif mutant=='drop_final':source=source.replace('wire take_output = output_valid && output_ready;',"wire take_output = output_valid && (output_ready || output_last);",1)
    elif mutant=='late_reopen':source=source.replace('!full ||',"(!full && !output_last) ||",1)
    bench=r'''`timescale 1ns/1ps
module tb;
reg clk=0,resetn=0,abort_epoch=0,input_valid=0,input_last=0,output_ready=0;
reg [35:0] input_data=0;
reg [8:0] input_position=0;
reg [69:0] input_metadata=70'h12345,reference_metadata=70'h12345;
wire input_ready,output_valid,output_last,output_identity_good,idle,fault;
wire [35:0] output_data;wire [8:0] output_position;wire [69:0] output_metadata;
starlink_pss_product_identity_stage dut(.*);
integer n,retired=0;
task tick;begin #1;clk=1;#1;clk=0;#1;end endtask
initial begin
 tick;resetn=1;input_valid=1;input_data=36'h111;input_position=0;tick;
 // A nonfinal word refills on the same edge, with exact data/certificate.
 output_ready=1;input_data=36'h222;input_position=511;input_last=1;#1;
 if(!input_ready || !output_valid)$fatal(1,"nonfinal refill lost");tick;
 if(output_data!==36'h222 || !output_last || !output_identity_good)$fatal(1,"final capture mismatch");
 // A queued future offer must not displace a held LAST, regardless of whether
 // publication is blocked, known allowed, or unknown. The consumer is still
 // the only authority to retire it. Input capacity cannot follow that decision.
 input_data=36'h333;input_position=0;input_last=0;
 for(n=0;n<4;n=n+1)begin
  case(n)0:output_ready=0;1:output_ready=1'bx;2:output_ready=1'bz;3:output_ready=1;endcase
  #1;
  if(input_ready!==0)$fatal(1,"held final capacity depends on publication");
 end
 output_ready=0;
 repeat(10)begin tick;if(!output_valid || output_data!==36'h222)$fatal(1,"unpublished LAST dropped");end
 output_ready=1;tick;
 if(output_valid || !idle || !input_ready)$fatal(1,"retired slot not empty/reopened");
 // The queued offer can be taken on the FOLLOWING edge, not on LAST's edge.
 tick;
 if(!output_valid || output_data!==36'h333 || output_last)$fatal(1,"queued next word lost");
 input_valid=0;tick;
 resetn=0;tick;resetn=1;input_valid=1;input_last=1;output_ready=0;tick;
 abort_epoch=1;#1;if(!fault || input_ready || output_valid)$fatal(1,"current abort no longer fences slot");tick;
 abort_epoch=0;#1;if(!fault || input_ready || output_valid)$fatal(1,"abort quarantine lost");
 resetn=0;tick;resetn=1;#1;if(fault || !input_ready || output_valid)$fatal(1,"reset did not recover");
 $display("FINAL_CAPACITY_PASS nonfinal_refill=1 held_final_isolated=1 next_edge_reopen=1 publication_unchanged=1");$finish;
end
endmodule
'''
    files=[]
    for name,text in [('stage.v',source),('tb.sv',bench)]:
        path=tmp_path/name;path.write_text(text);files.append(str(path))
    result=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),*files],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result


def test_final_capacity_and_following_edge_acceptance(tmp_path):
    result=run(tmp_path)
    assert result.returncode==0 and 'FINAL_CAPACITY_PASS' in result.stdout,result.stdout+result.stderr


@pytest.mark.parametrize('mutant',['old_refill','pause_nonfinal','drop_final','late_reopen'])
def test_unsafe_capacity_mutants_rejected(tmp_path,mutant):
    result=run(tmp_path,mutant)
    assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout+result.stderr

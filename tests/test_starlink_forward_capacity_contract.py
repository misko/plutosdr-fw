"""Parallel readiness algebra and byte-identical runtime; no production change."""
from pathlib import Path
import re
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
PARENT=Path('/dev/shm/starlink-monotonic-reset.pL4aOpKf/prepared-v1')

def undo_bench(text):
    if '// BEGIN PARALLEL READY WITNESS' in text:
        from tests.test_starlink_parallel_kernel_ready import undo_bench as undo_ready
        text=undo_ready(text)
    text,n=re.subn(r'  // BEGIN FORWARD CAPACITY SHADOW\n.*?  // END FORWARD CAPACITY SHADOW\n','',text,flags=re.S)
    assert n==1
    line='      report_forward_capacity; // FORWARD CAPACITY REPORT\n'
    assert text.count(line)==1
    return text.replace(line,'',1)

def test_unchanged_runtime_and_exact_bench_delta():
    names=(PARENT/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    assert len(names)==22
    for name in names:
        if (RTL/name).exists():
            from tests.test_starlink_parallel_kernel_ready import undo_runtime
            assert undo_runtime((RTL/name).read_text(),name)==(PARENT/name).read_text(),name
    assert (ROOT/'tools/staged_fft_experiment.tcl').read_text().replace(' PARALLEL_KERNEL_READY=1','',1)==(PARENT/'staged_fft_experiment.tcl').read_text()
    name='tb_fft_staged_output.sv';assert undo_bench((RTL/name).read_text())==(PARENT/name).read_text()

def test_capacity_observes_owned_state_not_forced_transport_valid():
    text=(RTL/'tb_fft_staged_output.sv').read_text()
    vacancy=re.search(r'wire capacity_vacancy = ([^;]+);',text)[1]
    assert '!dut.product.arithmetic.output_valid' in vacancy
    assert '!dut.product_valid' not in vacancy
    assert 'else force dut.product_valid=1\'bx;' in text

def run(tmp_path,mutation=None):
    parallel='r && !kf && ((!v[0] || !v[1] || !v[2] || !v[3] || !v[4]) || (!sf && (!full || ((last===1\'b0)&&refill)) && !ff))'
    changes={
        'omit_tail_fault':('!sf &&',''),
        'omit_stage':('!v[2] || ',''),
        'ignore_last':("(last===1'b0)","1'b1"),
        'ignore_kernel_fault':('!kf && ',''),
        'ignore_reset':('r && ',''),
    }
    if mutation:
        old,new=changes[mutation];assert parallel.count(old)==1;parallel=parallel.replace(old,new,1)
    bench='''`timescale 1ns/1ps
module tb;
reg r=0,kf=0,sf=0,ff=0,full=0,last=0,refill=0;reg [4:0]v=0;
wire tail=r&&!sf&&(!full||((last===1'b0)&&refill));
wire arithmetic_ready=r&&(!v[2]||!v[3]||!v[4]||(tail&&!ff));
wire operand_ready=r&&(!v[1]||arithmetic_ready);
wire original=r&&!kf&&(!v[0]||operand_ready);
wire parallel_ready=__PARALLEL__;
integer n,side,k,checks=0;reg [31:0]rng=32'h91ace789;
function val(input integer i);case(i%4)0:val=0;1:val=1;2:val=1'bx;3:val=1'bz;endcase endfunction
task check;begin #0.001;if(original!==parallel_ready)$fatal(1,"parallel readiness mismatch");checks=checks+1;end endtask
initial begin
 // Exhaustive binary assignments include full pipeline and final-slot stalls.
 for(n=0;n<4096;n=n+1)begin {r,kf,sf,ff,full,last,refill,v}=n;check;end
 // Every nonreset field is individually X/Z on every binary occupancy pattern.
 for(n=0;n<4096;n=n+1)for(side=0;side<11;side=side+1)for(k=2;k<4;k=k+1)begin
  {r,kf,sf,ff,full,last,refill,v}=n;
  case(side)0:kf=val(k);1:sf=val(k);2:ff=val(k);3:full=val(k);4:last=val(k);5:refill=val(k);default:v[side-6]=val(k);endcase
  check;
 end
 for(n=0;n<16384;n=n+1)begin
  rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);
  r=rng[0];kf=val(rng>>1);sf=val(rng>>3);ff=val(rng>>5);full=val(rng>>7);last=val(rng>>9);refill=val(rng>>11);
  for(side=0;side<5;side=side+1)v[side]=val(rng>>(13+2*side));check;
 end
 if(checks!=110592)$fatal(1,"short campaign");
 $display("FORWARD_CAPACITY_ALGEBRA_PASS checks=%0d known_reset=1 four_state_data=1",checks);$finish;
end
endmodule
'''.replace('__PARALLEL__',parallel)
    (tmp_path/'bench.sv').write_text(bench)
    result=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(tmp_path/'bench.sv')],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr);assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr);return result

def test_exact_parallel_readiness(tmp_path):
    result=run(tmp_path);assert result.returncode==0 and 'checks=110592' in result.stdout,result.stdout+result.stderr

@pytest.mark.parametrize('mutation',['omit_tail_fault','omit_stage','ignore_last','ignore_kernel_fault','ignore_reset'])
def test_unsafe_capacity_rejected(tmp_path,mutation):
    result=run(tmp_path,mutation);assert result.returncode!=0 and 'parallel readiness mismatch' in result.stdout,result.stdout+result.stderr

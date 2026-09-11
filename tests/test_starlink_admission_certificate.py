"""Clocked private-certificate controls, not complete FFT or RX proofs."""
from pathlib import Path
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control/starlink_pss_admission_certificate.v'
BENCH=r'''
`timescale 1ns/1ps
module tb;
reg clk=0,resetn=0,request=0,quarantine=0,consume=0;
reg [21:0] checks_good=0;
wire permit,snapshot_valid;wire [21:0] snapshot_good;
always #5 clk=~clk;
starlink_pss_admission_certificate #(.CHECKS(22)) dut(.*);
task tick;begin @(posedge clk);#0.01;@(negedge clk);end endtask
integer bitno,kind;
initial begin
tick;resetn=1;tick;
for(kind=0;kind<3;kind=kind+1) begin
  for(bitno=0;bitno<22;bitno=bitno+1) begin
    request=0;tick;checks_good='1;
    case(kind) 0:checks_good[bitno]=0;1:checks_good[bitno]=1'bx;2:checks_good[bitno]=1'bz;endcase
    request=1;#0.01;if(permit) $fatal(1,"uncaptured evidence admitted");
    tick;if(permit!==0 || !snapshot_valid) $fatal(1,"bad/unknown check admitted");
    checks_good='1;tick;if(permit!==0) $fatal(1,"unrequested certificate refresh");
  end
end
request=0;tick;request=1;checks_good='1;tick;
if(permit!==1) $fatal(1,"good snapshot rejected");
checks_good=0;repeat(3) begin tick;if(permit!==1) $fatal(1,"held evidence changed");end
consume=1;tick;consume=0;checks_good='1;
repeat(3) begin tick;if(permit!==0) $fatal(1,"certificate consumed more than once");end
request=0;tick;request=1;tick;quarantine=1;#0.01;
if(permit!==0) $fatal(1,"quarantine did not fence certificate");
tick;quarantine=0;request=0;tick;
request=1;tick;resetn=0;#0.01;
if(permit!==0) $fatal(1,"reset did not fence certificate");
tick;resetn=1;request=0;tick;
if(permit!==0 || snapshot_valid) $fatal(1,"stale epoch certificate");
request=1;tick;if(permit!==1) $fatal(1,"fresh epoch could not acquire");
$display("ADMISSION_CERTIFICATE_PASS rejected=66 held=1 single_use=1 cancel=2 fresh=1");$finish;
end
initial begin #20000;$fatal(1,"watchdog");end
endmodule
'''

def run(tmp_path,source,width=22):
    rtl=tmp_path/'certificate.v';rtl.write_text(source)
    text=BENCH.replace('21:0',f'{width-1}:0').replace('CHECKS(22)',f'CHECKS({width})')
    text=text.replace('bitno<22',f'bitno<{width}').replace('rejected=66',f'rejected={width*3}')
    bench=tmp_path/'tb.sv';bench.write_text(text)
    compile=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(rtl),str(bench)],
                           capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(compile.stdout+compile.stderr)
    assert compile.returncode==0,compile.stdout+compile.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'run.log').write_text(result.stdout+result.stderr)
    return result

@pytest.mark.parametrize('width',[22,28],ids=['admission','completion'])
def test_clocked_admission_contract(tmp_path,width):
    result=run(tmp_path,RTL.read_text(),width)
    assert result.returncode==0,result.stdout+result.stderr
    assert result.stdout.splitlines()[0]==f'ADMISSION_CERTIFICATE_PASS rejected={width*3} held=1 single_use=1 cancel=2 fresh=1'
    assert 'FATAL' not in result.stdout

@pytest.mark.parametrize('change',['bypass','refresh','reuse','quarantine'])
@pytest.mark.parametrize('width',[22,28],ids=['admission','completion'])
def test_unsafe_certificate_mutant_rejected(tmp_path,change,width):
    before,after={
        'bypass':('((&snapshot_good) === 1\'b1)',"((&checks_good) === 1'b1)"),
        'refresh':('else if (!snapshot_valid && !consumed) snapshot_good<=checks_good;',
                   'else if (!consumed) snapshot_good<=checks_good;'),
        'reuse':('snapshot_valid<=0;consumed<=1;', 'snapshot_valid<=0;consumed<=0;'),
        'quarantine':('request && !quarantine && snapshot_valid', 'request && snapshot_valid'),
    }[change]
    source=RTL.read_text();assert source.count(before)==1
    result=run(tmp_path,source.replace(before,after,1),width)
    assert result.returncode!=0 and 'FATAL' in result.stdout and 'watchdog' not in result.stdout,result.stdout

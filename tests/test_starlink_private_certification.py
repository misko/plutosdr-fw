"""Source inverse and four-state private-capture/legacy-fallback truth table.

This tests the changed expression, not complete admission safety; actual FFT
snapshot/consume fault cases separately cover the unchanged admission gates.
"""
import hashlib
from pathlib import Path
import re
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
TOP=ROOT/'hdl/library/starlink_pss_acquisition/staged_control/starlink_pss_fft_staged_output_impl.v'
ORIGINAL=ROOT.parent/'staged-sequence-prepared-v1/starlink_pss_fft_staged_output_impl.v'

def test_only_private_capture_expression_changed():
    old=ORIGINAL.read_bytes()
    assert hashlib.sha256(old).hexdigest()=='2df734a229635ef94cc1017ab1bba6d0bcdfad762655619c0e28fd68c80df68d'
    text=TOP.read_text()
    start=text.index('          // In certified mode this is only a private descriptor snapshot.')
    end=text.index(';',start)+1
    restored=text[:start]+'          descriptor_certified <= preparation_valid && !any_fast_fault;'+text[end:]
    assert restored==old.decode(),'no other runtime admission, quarantine, or publication change'

def run(tmp_path,mutant=None):
    source=TOP.read_text()
    matches=re.findall(r'descriptor_certified <= (preparation_valid[^;]+);',source)
    assert len(matches)==1
    expr=matches[0]
    if mutant=='drop_descriptor':expr="1'b1 && (CERTIFIED_ADMISSION || !any_fast_fault)"
    if mutant=='drop_legacy':expr='preparation_valid'
    bench='''`timescale 1ns/1ps
module tb;
reg CERTIFIED_ADMISSION,preparation_valid,any_fast_fault;
wire candidate='''+expr+''';
function val(input integer n);case(n)0:val=0;1:val=1;2:val=1'bx;3:val=1'bz;endcase endfunction
integer mode,p,f,cases=0;
initial begin
 for(mode=0;mode<2;mode=mode+1)for(p=0;p<4;p=p+1)for(f=0;f<4;f=f+1)begin
  CERTIFIED_ADMISSION=mode;preparation_valid=val(p);any_fast_fault=val(f);#1;
  if(candidate !== (mode ? (preparation_valid && 1'b1) : (preparation_valid && !any_fast_fault)))
    $fatal(1,"private expression/fallback");
  cases=cases+1;
 end
 $display("PRIVATE_CERTIFICATION_PASS cases=%0d private_only=1 legacy_exact=1",cases);$finish;
end
endmodule
'''
    path=tmp_path/'bench.sv';path.write_text(bench)
    compiled=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(path)],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(compiled.stdout+compiled.stderr)
    assert compiled.returncode==0,compiled.stdout+compiled.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result

def test_private_capture_and_exact_legacy_fallback(tmp_path):
    result=run(tmp_path)
    assert result.returncode==0 and 'PRIVATE_CERTIFICATION_PASS cases=32 private_only=1 legacy_exact=1' in result.stdout,result.stdout

@pytest.mark.parametrize('mutant',['drop_descriptor','drop_legacy'])
def test_unsafe_expression_rejected(tmp_path,mutant):
    result=run(tmp_path,mutant)
    assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout

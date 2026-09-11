"""Exact runtime inverses and source-extracted four-state predicate proof."""
import hashlib
from pathlib import Path
import re
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
BASE=ROOT.parent/'staged-certification-prepared-v1'
TOP='starlink_pss_fft_staged_output_impl.v'
GUARD='starlink_pss_result_guard_owner_view.v'

def test_complete_guard_and_top_inverses():
    for name,pin in [(TOP,'6c181d830143c998ffa3fba15d51fe34cf087d08eb622591f698229b07b1a4a4'),
                     (GUARD,'6b3f4ff240f3f81edaaf694f7b2a926be320da71bfc3641d84a6ce3c87104f45')]:
        old=(BASE/name).read_bytes();assert hashlib.sha256(old).hexdigest()==pin
        # This historical whole-file inverse belongs to the pinned guard-fact
        # candidate. The held-metadata test separately inverts today's full top.
        current=ROOT.parent/'staged-guardfacts-prepared-v1'/name
        text=current.read_text()
        if name==TOP:
            assert hashlib.sha256(current.read_bytes()).hexdigest()=='b3511a70b97b91e3e9b4106ea0c9bab8df4f7a43a07ff30a5447cd522dc5d143'
        else:
            assert hashlib.sha256(current.read_bytes()).hexdigest()=='ba0b9e308e2747e43edeec6c9b4bb486b2c1fc12d7d850d2bbf6a6ff02cc4431'
        if name==GUARD:
            text=text.replace('  output wire [7:0] offered_local_faults_now,\n','',1)
            start=text.index('  // Same facts as the scalar view, before its OR reduction.')
            assignment=text.index('  assign offered_local_faults_now',start)
            end=text.index(';',assignment)+2;text=text[:start]+text[end:]
        else:
            text=text.replace('  wire [7:0] guard_offered_local_faults [0:1];\n','',1)
            start=text.index('  // Preserve the scalar predicate for current fault fencing.')
            end=text.index('  // Availability may legitimately rise',start);text=text[:start]+text[end:]
            text=text.replace('.CHECKS(36)', '.CHECKS(22)',1)
            text=text.replace('.checks_good(admission_checks),', '.checks_good({!next_inverse || inverse_descriptor_live,\n      cutover_admission_capacity,guard_capacity[next_inverse],~admission_reject}),',1)
            text=text.replace('    .offered_local_faults_now(guard_offered_local_faults[OWNER]),\n','',1)
            text=text.replace('  wire [41:0] completion_checks = {completion_good[27:19],~admission_reject_expanded};\n','',1)
            text=text.replace('.CHECKS(42)', '.CHECKS(28)',1)
            text=text.replace('.checks_good(completion_checks)', '.checks_good(completion_good)',1)
        assert text==old.decode(),'unrelated runtime change: '+name

def declaration(text,name):
    found=re.findall(r'  (?:wire\s+\[[^\]]+\]\s+|assign\s+)'+name+r'\s*=.*?;',text,re.S)
    assert len(found)==1,name
    return found[0]

def run(tmp_path,mutant=None):
    top=(RTL/TOP).read_text();guard=(RTL/GUARD).read_text()
    vector=declaration(guard,'offered_local_faults_now')
    if mutant=='drop_fault':vector=vector.replace('summary_faults_now :','(summary_faults_now & 8\'h7f) :')
    if mutant=='ignore_disable':vector=vector.replace('ENABLE_OFFERED_FAULT_SUMMARY ?',"1'b1 ?")
    if mutant=='unknown_zero':vector=vector.replace('summary_faults_now :',"((^summary_faults_now === 1'bx) ? 8'b0 : summary_faults_now) :")
    wrapper='''`timescale 1ns/1ps
module guard_view(input wire ENABLE_OFFERED_FAULT_SUMMARY,input wire [7:0] summary_faults_now,
 output wire offered_local_fault_now,output wire [7:0] offered_local_faults_now);
 wire summary_fault_now=|summary_faults_now;
'''+declaration(guard,'offered_local_fault_now')+'\n'+vector+'\nendmodule\n'
    bench=r'''
module tb;
 reg enable=0;reg [7:0] facts0=0,facts1=0;
 wire [1:0] guard_offered_local_fault;
 wire [7:0] guard_offered_local_faults[0:1];
 guard_view d0(enable,facts0,guard_offered_local_fault[0],guard_offered_local_faults[0]);
 guard_view d1(enable,facts1,guard_offered_local_fault[1],guard_offered_local_faults[1]);
 reg [18:0] other=0;
 wire [18:0] admission_reject={other[18:10],guard_offered_local_fault[1],guard_offered_local_fault[0],other[7:0]};
 reg next_inverse=1,inverse_descriptor_live=1,cutover_admission_capacity=1;
 reg [1:0] guard_capacity=3;
 reg [8:0] completion_prefix=9'h1ff;
 wire [27:0] completion_good={completion_prefix,~admission_reject};
 wire [21:0] old_admission={!next_inverse || inverse_descriptor_live,cutover_admission_capacity,guard_capacity[next_inverse],~admission_reject};
'''+ '\n'.join(declaration(top,name) for name in ['admission_reject_expanded','admission_checks','completion_checks'])+r'''
 function val(input integer n);case(n)0:val=0;1:val=1;2:val=1'bx;3:val=1'bz;endcase endfunction
 function [7:0] quad(input integer n);integer b;begin for(b=0;b<8;b=b+1)quad[b]=val((n>>(2*b))&3);end endfunction
 integer mode,side,n,context_kind,bitno,cases=0;
 task check;
 begin
   #1;
   if((|admission_reject_expanded)!==(|admission_reject) ||
      (&admission_checks)!==(&old_admission) || (&completion_checks)!==(&completion_good))
     $fatal(1,"expanded predicate differs");
   cases=cases+1;
 end
 endtask
 initial begin
   for(mode=0;mode<2;mode=mode+1)for(side=0;side<2;side=side+1)
    for(context_kind=0;context_kind<4;context_kind=context_kind+1)for(n=0;n<65536;n=n+1)begin
     enable=mode;facts0=side ? {8{val(context_kind)}} : quad(n);
     facts1=side ? quad(n) : {8{val(context_kind)}};check;
   end
   enable=1;facts0=0;facts1=0;
   for(bitno=0;bitno<19;bitno=bitno+1)if(bitno!=8 && bitno!=9)
    for(n=0;n<4;n=n+1)begin other=0;other[bitno]=val(n);check;end
   other=0;
   for(n=0;n<4;n=n+1)begin
     inverse_descriptor_live=val(n);check;inverse_descriptor_live=1;
     cutover_admission_capacity=val(n);check;cutover_admission_capacity=1;
     guard_capacity[1]=val(n);check;guard_capacity=3;
     for(bitno=0;bitno<9;bitno=bitno+1)begin
       completion_prefix=9'h1ff;completion_prefix[bitno]=val(n);check;
     end
   end
   $display("GUARD_FACTS_PASS cases=%0d exact_four_state=1 disabled_exact=1",cases);$finish;
 end
endmodule
'''
    path=tmp_path/'bench.sv';path.write_text(wrapper+bench)
    compiled=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(path)],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(compiled.stdout+compiled.stderr)
    assert compiled.returncode==0,compiled.stdout+compiled.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=60)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result

def test_source_extracted_four_state_predicates(tmp_path):
    result=run(tmp_path)
    assert result.returncode==0 and 'GUARD_FACTS_PASS cases=1048692 exact_four_state=1 disabled_exact=1' in result.stdout,result.stdout+result.stderr

@pytest.mark.parametrize('mutant',['drop_fault','ignore_disable','unknown_zero'])
def test_unsafe_fact_exports_rejected(tmp_path,mutant):
    result=run(tmp_path,mutant)
    assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout

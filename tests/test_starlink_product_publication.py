"""Product writer/reader phase separation, not a physical signoff."""
import sys,subprocess
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import product_publication_experiment as exp
import product_publication_transform as delta
import prove_product_publication_ownership as ownership

def test_exact_delta():
    assert delta.transform((exp.RTL/(exp.base.NEW+'.v')).read_text())==(exp.RTL/(exp.NEW+'.v')).read_text()

@pytest.mark.parametrize('index',range(2))
def test_delta_rejects_missing_duplicate(index):
    old=(exp.RTL/(exp.base.NEW+'.v')).read_text();before=delta.PAIRS[index][0]
    for source in [old.replace(before,'',1),old+'\n'+before]:
        with pytest.raises(ValueError):delta.transform(source)

def test_actual_mailbox(tmp_path):
    result=ownership.run(tmp_path/'ownership')
    assert result['passed'] and len(result['results'])==4

def expr(source,name):
    return source.split('wire '+name+' =',1)[1].split(';',1)[0].strip()

@pytest.mark.parametrize('mutant',['none','missing_current_fault','missing_idle_fence'])
def test_four_state_authorization(tmp_path,mutant):
    source=(exp.RTL/(exp.NEW+'.v')).read_text()
    full=expr(source,'external_fault_now');writer=expr(source,'product_writer_fault')
    assert full.replace(' || handoff_fault_now','')==writer
    assert expr(source,'handoff_fault_now')=='!next_inverse && forward_committed && product_bank_valid &&\n    (!forward_handoff_identity || product_bank_position != 0 || product_bank_last)'
    original=expr(source,'original_product_commit_authorized')
    candidate=expr(source,'product_commit_authorized')
    if mutant=='missing_current_fault':candidate=candidate.replace('!product_writer_fault && ','')
    if mutant=='missing_idle_fence':candidate=candidate.replace("(product_bank_valid === 1'b0) &&\n    ",'')
    bench=r"""
`timescale 1ns/1ps
module tb;
reg product_bank_valid,forward_committed,next_inverse,other_fault,handoff_bad,result_fault,guard_fault,forward_buffer_fault;
wire[1:0]guard_offered_local_fault={2{guard_fault}};
wire handoff_fault_now=!next_inverse && forward_committed && product_bank_valid && handoff_bad;
wire external_fault_now=other_fault || handoff_fault_now;
wire product_writer_fault=other_fault;
wire original_auth=__OLD__;
wire candidate_auth=__NEW__;
function four(input integer n);
case(n&3)0:four=0;1:four=1;2:four=1'bx;3:four=1'bz;endcase
endfunction
integer n,checks=0,reader_vetoes=0;
initial begin
 for(n=0;n<65536;n=n+1)begin
  product_bank_valid=four(n);forward_committed=four(n>>2);
  next_inverse=four(n>>4);other_fault=four(n>>6);handoff_bad=four(n>>8);
  result_fault=four(n>>10);guard_fault=four(n>>12);forward_buffer_fault=four(n>>14);
  #1;
  if(product_bank_valid===0)begin
   if(original_auth!==candidate_auth)$fatal(1,"writer authorization mismatch");
   checks=checks+1;
  end else begin
   if(candidate_auth!==0)$fatal(1,"reader idle fence not fail closed");
   reader_vetoes=reader_vetoes+1;
  end
 end
 if(checks!=16384 || reader_vetoes!=49152)$fatal(1,"vacuous vectors");
 $display("PRODUCT_AUTHORIZATION_PASS vectors=65536 writer_checks=16384 reader_vetoes=49152");$finish;
end
endmodule
""".replace('__OLD__',original).replace('__NEW__',candidate)
    path=tmp_path/'tb.sv';path.write_text(bench)
    build=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(path)],capture_output=True,text=True,timeout=30)
    assert build.returncode==0,build.stderr
    run=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(run.stdout+run.stderr)
    if mutant=='none':assert run.returncode==0 and 'PRODUCT_AUTHORIZATION_PASS' in run.stdout
    else:assert run.returncode!=0 and 'FATAL' in run.stdout

ROW='PRODUCT_PUBLICATION_PASS checks=10000 publications=18 reader_edges=512 authorization_differences=10 writer_exact=1\n'
@pytest.mark.parametrize('aux',[False,True])
def test_witness(aux):
    assert exp.witness(ROW,aux)['publications']==18

@pytest.mark.parametrize('row',['',ROW+ROW,ROW+'FATAL',ROW.replace('10000','1'),ROW.replace('publications=18','publications=0'),ROW.replace('reader_edges=512','reader_edges=0'),ROW.replace('differences=10','differences=0')])
def test_witness_rejects(row):
    with pytest.raises(Exception):exp.witness(row,True)

@pytest.mark.parametrize('layout',["if(1)begin end else force dut.product_commit_authorized=1'b0;release dut.product_commit_authorized;",
                                 "force dut.product_commit_authorized=1'b0;release dut.product_commit_authorized;begin end"])
def test_mirror_syntax(tmp_path,layout):
    bench="module child;wire product_commit_authorized=1;endmodule\nmodule tb;child dut();wire product_original_accept=1;initial begin "+exp.mirror_publication_veto(layout)+" $finish;end endmodule"
    path=tmp_path/'tb.sv';path.write_text(bench)
    build=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(path)],capture_output=True,text=True,timeout=30)
    assert build.returncode==0,build.stderr

@pytest.mark.parametrize('layout',["","force dut.product_commit_authorized=1'b0;"*2+"release dut.product_commit_authorized;"])
def test_mirror_rejects(layout):
    with pytest.raises(Exception):exp.mirror_publication_veto(layout)

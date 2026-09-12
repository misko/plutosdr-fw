"""Source-exact phase simplification and independent evidence gates."""
import sys
from pathlib import Path
import subprocess
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import phase_publication_experiment as exp
import phase_publication_transform as delta
import prove_guard_pulse_publication_phase as proof

def test_exact_delta():
    assert delta.transform((exp.RTL/(exp.base.NEW+'.v')).read_text()) == (exp.RTL/(exp.NEW+'.v')).read_text()

@pytest.mark.parametrize('index',range(3))
def test_delta_rejects_missing_or_duplicate(index):
    source=(exp.RTL/(exp.base.NEW+'.v')).read_text()
    before=delta.PAIRS[index][0]
    for changed in [source.replace(before,'',1),source+'\n'+before]:
        with pytest.raises(ValueError):delta.transform(changed)

def test_exhaustive_four_state_proof(tmp_path):
    assert proof.run(tmp_path/'proof')['vectors']==262144

def expression(source,name):
    return source.split('wire '+name+' =',1)[1].split(';',1)[0].strip()

@pytest.mark.parametrize('mutant',['none','context','other_fault'])
def test_actual_fault_expressions(tmp_path,mutant):
    source=(exp.RTL/(exp.NEW+'.v')).read_text()
    original=expression(source,'replay_publication_fault')
    reduced=expression(source,'replay_phase_fault')
    terms=[s.strip() for s in reduced.split('||')]
    assert len(terms)==10 and len(set(terms))==10
    assert original.replace(' || preparation_fault_now','')==reduced
    if mutant=='other_fault':reduced=reduced.replace(terms[0]+' || ','',1)
    context='1' if mutant=='context' else '!preparing'
    bench=proof.BENCH
    bench=bench.replace('wire old_accept=!preparing && !(other_fault || preparation_fault_now);',
        '\n'.join('wire '+term+' = other_fault;' for term in terms[1:])+
        '\nwire '+terms[0]+' = independent_fault;\nwire full_fault='+original+';\nwire phase_fault='+reduced+
        ';\nwire old_accept=!preparing && !full_fault;')
    # Independent first fault ensures removal cannot be masked by another veto.
    bench=bench.replace('reg preparing,fast_running,other_fault;','reg preparing,fast_running,other_fault,independent_fault;')
    bench=bench.replace('n<262144','n<1048576').replace('other_fault=four(n>>4);','other_fault=four(n>>4);independent_fault=four(n>>18);')
    bench=bench.replace('__NEW__',context+' && !phase_fault')
    bench=bench.replace('vectors=262144','vectors=1048576')
    path=tmp_path/'tb.sv';path.write_text(bench)
    build=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(path)],capture_output=True,text=True,timeout=30)
    assert build.returncode==0,build.stderr
    run=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=60)
    (tmp_path/'simulate.log').write_text(run.stdout+run.stderr)
    if mutant=='none':assert run.returncode==0 and 'vectors=1048576' in run.stdout
    else:assert run.returncode!=0 and 'phase equivalence differs' in run.stdout

ROW='PHASE_PUBLICATION_PASS checks=10000 accepts=18 preflight=10 fault_differences=10 exact=1\n'
@pytest.mark.parametrize('aux',[False,True])
def test_witness(aux):
    assert exp.witness(ROW,aux)['checks']==10000

@pytest.mark.parametrize('change',[
    '',ROW+ROW,ROW+'FATAL',ROW.replace('10000','1'),ROW.replace('accepts=18','accepts=0'),
    ROW.replace('preflight=10','preflight=0'),ROW.replace('fault_differences=10','fault_differences=0')])
def test_bad_witness(change):
    with pytest.raises(Exception):exp.witness(change,True)

@pytest.mark.parametrize('layout',[
    "if(1)begin end else force dut.output_replay_accept=1'b0;release dut.output_replay_accept;",
    "force dut.output_replay_accept=1'b0;release dut.output_replay_accept;begin end"])
def test_mirror_syntax(tmp_path,layout):
    mirrored=exp.mirror_publication_veto(layout)
    source="module child;wire output_replay_accept=1;endmodule\nmodule tb;child dut();wire phase_original_accept=1;initial begin "+mirrored+" $finish;end endmodule\n"
    path=tmp_path/'tb.sv';path.write_text(source)
    result=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(path)],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr

@pytest.mark.parametrize('source',["","force dut.output_replay_accept=1'b0;"*2+"release dut.output_replay_accept;"])
def test_mirror_rejects_missing_duplicate(source):
    with pytest.raises(Exception):exp.mirror_publication_veto(source)


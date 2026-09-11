from pathlib import Path
import subprocess
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import output_identity_experiment as identity
import output_identity_boundaries as boundaries
RTL=identity.RTL
GOOD='OUTPUT_IDENTITY_PASS checks=10000 words=9216 finals=18 first_refills=18 actual_word_exact=1 actual_publication=1\n'

def test_complete_identity_witness():
    assert identity.witness(GOOD)['words']==9216

@pytest.mark.parametrize('log',['',GOOD+GOOD,GOOD+'FATAL\n',GOOD.replace('checks=10000','checks=9999'),
    GOOD.replace('words=9216','words=9215'),GOOD.replace('finals=18','finals=17'),
    GOOD.replace('first_refills=18','first_refills=17'),GOOD.replace('actual_word_exact=1','actual_word_exact=0'),
    GOOD.replace('actual_publication=1','actual_publication=0')])
def test_incomplete_identity_rejected(log):
    with pytest.raises(ValueError):identity.witness(log)

BOUNDARIES=''.join(f'OUTPUT_IDENTITY_BOUNDARY_PASS boundary={n} cancelled_outputs=0 fresh_reads=512 fresh_releases=1\n' for n in range(9))
BOUNDARIES+='OUTPUT_IDENTITY_BOUNDARIES_PASS cases=9 current_publication_fenced=1 fresh_recovery=1\n'

def test_complete_boundaries():
    assert boundaries.witness(BOUNDARIES)['cases']==9

@pytest.mark.parametrize('line',range(10))
def test_each_missing_boundary_rejected(line):
    lines=BOUNDARIES.splitlines(True);del lines[line]
    with pytest.raises(ValueError):boundaries.witness(''.join(lines))

@pytest.mark.parametrize('log',[BOUNDARIES+BOUNDARIES,BOUNDARIES+'FATAL\n',
    BOUNDARIES.replace('cancelled_outputs=0','cancelled_outputs=1',1),
    BOUNDARIES.replace('fresh_reads=512','fresh_reads=511',1)])
def test_changed_boundaries_rejected(log):
    with pytest.raises(ValueError):boundaries.witness(log)

@pytest.mark.parametrize('mutation',['early_publish','bypass_certificate','no_first_word_forwarding','drop_unpublished_final'])
def test_broken_stage_or_bank_rejected(tmp_path,mutation):
    bench=(RTL/'tb_output_identity_bank.sv').read_text()
    bank=(RTL/'starlink_pss_output_mailbox_staged_identity.v').read_text()
    case=2 if mutation=='bypass_certificate' else 0
    if mutation=='early_publish':
        before='if (!EXPLICIT_COMMIT || input_commit_authorized)';assert bank.count(before)==1
        bank=bank.replace(before,"if (1'b1)")
    elif mutation=='bypass_certificate':
        before="wire metadata_matches = input_metadata_certified === 1'b1;";assert bank.count(before)==1
        bank=bank.replace(before,"wire metadata_matches = 1'b1;")
    elif mutation=='no_first_word_forwarding':
        before='(writer_load?stage_metadata[36:0]:writer_metadata)';assert bench.count(before)==1
        bench=bench.replace(before,'writer_metadata')
    else:
        before='.output_valid(stage_valid),.output_ready(consume)';assert bench.count(before)==1
        bench=bench.replace(before,'.output_valid(stage_valid),.output_ready(bank_ready)')
    (tmp_path/'bench.sv').write_text(bench);(tmp_path/'bank.v').write_text(bank)
    command=['iverilog','-g2012','-s','tb','-Ptb.CASE='+str(case),'-o',str(tmp_path/'sim'),
        str(tmp_path/'bench.sv'),str(tmp_path/'bank.v'),str(RTL/'starlink_pss_product_identity_split_capacity.v')]
    result=subprocess.run(command,capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr);assert result.returncode==0,result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout

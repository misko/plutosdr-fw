"""Actual mailbox lifecycle plus exact top delta; no physical signoff."""
from pathlib import Path
import re
import sys
import pytest
from tests import test_starlink_completion_mailbox_stage as bank
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import ownership_lock_transform as transform
import ownership_lock_experiment as experiment
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'

def test_only_lock_representation_changes():
    old=(RTL/'starlink_pss_fft_retry_admission_impl.v').read_text()
    new=(RTL/'starlink_pss_fft_ownership_lock_impl.v').read_text()
    assert transform.transform(old)==new
    assert new.count('output_descriptor_locked =')==1
    assert 'output_descriptor_locked<=' not in new
    for marker in ['wire replay_publication_fault =','wire output_complete_valid =',
                   'assign output_replay_accept =','assign registered_quarantine =']:
        assert old.split(marker)[1].split(';')[0]==new.split(marker)[1].split(';')[0]

def component(tmp_path,monkeypatch,cancel=0,stall=37,mutation=None,late_fault=None):
    top=(RTL/'starlink_pss_fft_ownership_lock_impl.v').read_text()
    expression=re.search(r'wire output_descriptor_locked = ([^;]+);',top)[1]
    mutations={
        'busy_only':'output_publication_busy',
        'published_only':'retained_published',
        'fault_unlock':'(output_publication_busy || retained_published) && !fault',
        'never_unlock':"1'b1",
    }
    if mutation:expression=mutations[mutation]
    observer=(RTL/'ownership_lock_observer.svh').read_text()
    for before,after in [
        ('dut.fast_running','resetn'),('dut.output_descriptor_locked','candidate_lock'),
        ('dut.output_publication_busy','publication_busy'),
        ('dut.retained_published','retained_published'),('dut.fast_fault','fault'),
        ('dut.output_complete_accept','(complete_valid && complete_ready)'),
        ('dut.output_released_valid','released_valid'),('fft_clk','clk')]:
        observer=observer.replace(before,after)
    # This real-bank component has 1 or 3 blocks rather than 18 actual-FFT jobs.
    observer=observer.replace('ownership_checks<10000 || ownership_accepts<18 ||\n         ownership_releases<18 || ownership_bridge<18',
                              'ownership_checks<100 || ownership_accepts<1')
    expression=expression.replace('output_publication_busy','publication_busy')
    extra=f'''
  reg retained_published=0;
  wire candidate_lock={expression};
  always @(posedge clk)begin
    if(!resetn)retained_published<=0;
    else begin
      if(published_valid)retained_published<=1;
      if(released_valid)retained_published<=0;
    end
  end
  {observer}
'''
    original=Path.read_text
    def read(path,*args,**kwargs):
        text=original(path,*args,**kwargs)
        if path==RTL/'tb_staged_mailbox_control.sv':
            if late_fault:
                target,value=late_fault
                first=text.index('    reset_all;\n    request_allocation')
                last=text.index('    $finish(0);',first)
                inject=f'force bank_fault={value};' if target=='bank' else f'abort_epoch = {value};'
                release='release bank_fault;' if target=='bank' else 'abort_epoch = 0;'
                text=text[:first]+f'''
    reset_all;
    request_allocation(0);consume_allocation(0);write_private(0);
    complete_block(0);publish_and_drain(0);
    if(publication_busy!==0 || released_valid!==1 || retained_published!==1)
      $fatal(1,"late-fault stimulus missed release bridge");
    {inject}
    #0.1;
    if(!fault || released_valid || replay_valid || allocate_ready)
      $fatal(1,"late fault did not veto release/reuse");
    repeat(10)begin
      @(negedge clk);
      if(candidate_lock!==1 || ownership_old_lock!==1 || released_valid)
        $fatal(1,"late-fault ownership escaped quarantine");
    end
    {release}
    reset_all;
    request_allocation(0);consume_allocation(0);write_private(0);
    complete_block(0);publish_and_drain(0);
    if(publications!=1 || releases!=1 || occupied!==0 || fault)
      $fatal(1,"late-fault fresh recovery failed");
    $display("LATE_RELEASE_FAULT_PASS fresh_reads=512 releases=1");
'''+text[last:]
            assert text.count('\nendmodule')==text.count('$finish(0);')==1
            text=text.replace('\nendmodule',extra+'\nendmodule',1)
            text=text.replace('$finish(0);','report_ownership_lock; $finish(0);',1)
        return text
    monkeypatch.setattr(Path,'read_text',read)
    return bank.run(tmp_path,cancel,stall,1)

@pytest.mark.parametrize('cancel',range(6))
@pytest.mark.parametrize('stall',[1,37])
def test_real_mailbox_ownership_release_abort_and_reset(tmp_path,monkeypatch,cancel,stall):
    result=component(tmp_path,monkeypatch,cancel,stall)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'OWNERSHIP_LOCK_PASS' in result.stdout
    row=re.search(r'fault_holds=(\d+)',result.stdout)
    if cancel in [1,2,3,4]:assert int(row[1])>0

@pytest.mark.parametrize('mutation',['busy_only','published_only','fault_unlock','never_unlock'])
def test_unsafe_lock_representations_rejected(tmp_path,monkeypatch,mutation):
    result=component(tmp_path,monkeypatch,4 if mutation=='fault_unlock' else 0,37,mutation)
    assert result.returncode!=0 and 'ownership lock differs' in result.stdout,result.stdout

@pytest.mark.parametrize('target',['abort','bank'])
@pytest.mark.parametrize('value',["1'b1","1'bx","1'bz"])
def test_fault_on_empty_to_release_bridge(tmp_path,monkeypatch,target,value):
    result=component(tmp_path,monkeypatch,late_fault=(target,value))
    assert result.returncode==0,result.stdout+result.stderr
    assert 'LATE_RELEASE_FAULT_PASS fresh_reads=512 releases=1' in result.stdout

GOOD='OWNERSHIP_LOCK_PASS checks=177096 accepts=18 releases=18 bridge=36 fault_holds=0 original_lock_exact=1\n'
def test_witness_accepts_complete_healthy():
    assert experiment.witness(GOOD)['accepts']==18

@pytest.mark.parametrize('text',['',GOOD+GOOD,GOOD+'FATAL bad',GOOD.replace('accepts=18','accepts=0'),
    GOOD.replace('bridge=36','bridge=0'),GOOD.replace('checks=177096','checks=1'),
    GOOD.replace('original_lock_exact=1','original_lock_exact=0')])
def test_missing_or_weak_witness_rejected(text):
    with pytest.raises(ValueError):experiment.witness(text)

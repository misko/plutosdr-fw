"""Unit tests of route admission; actual arithmetic remains a separate gate."""
import json
from pathlib import Path
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import route_private_replay_sequence as route

def save(path,value):
    path.write_text(json.dumps(value))

@pytest.fixture
def campaign(tmp_path,monkeypatch):
    actual,synth,aux=[tmp_path/name for name in ['actual','synth','aux']]
    prepared,aux_prepared=[tmp_path/name for name in ['prepared','aux-prepared']]
    names=[f'module_{n}.v' for n in range(41)]
    for p in [actual,synth,aux,prepared,aux_prepared]:p.mkdir()
    for p in [prepared,aux_prepared]:
        (p/'profile.tcl').write_text('set runtime_names {'+' '.join(names)+'}')
        for name in names:(p/name).write_text(name)
    for p,mode,source in [(actual,'sim',prepared),(synth,'synth',prepared),(aux,'sim',aux_prepared)]:
        save(p/'outcome.json',dict(passed=True,returncode=0,mode=mode,prepared_sha='pinned',
             command=[str(source),'pinned',str(p)],audit={'words':64512},dcp_sha256='dcp'))
    monkeypatch.setattr(route.publication,'witness',lambda text,is_aux: {'checks':10000,'takes':9216,'private_only':11 if is_aux else 0,'final_only':5 if is_aux else 0,'quarantined_differences':11 if is_aux else 0,'auxiliary':is_aux})
    monkeypatch.setattr(route.out_retirement,'witness',lambda text,is_aux: {'checks':10000,'publications':18,'retires':18,'extra_holds':18,'auxiliary':is_aux})
    monkeypatch.setattr(route.descriptor,'witness',lambda text,is_aux: {'checks':10000,'loads':18,'fault_loads':6 if is_aux else 0,'private_differences':6 if is_aux else 0,'auxiliary':is_aux})
    monkeypatch.setattr(route.retirement,'witness',lambda text,is_aux: {'checks':10000,'publications':18,'retires':18,'extra_holds':18,'auxiliary':is_aux})
    monkeypatch.setattr(route.parallel,'witness',lambda text: {'checks':10000,'captures':9216,'first_refills':18,'four_state_exact':True,'same_edge_capture':True})
    monkeypatch.setattr(route.private_status,'witness',lambda text,is_aux: {'checks':10000,'new_fault_edges':11 if is_aux else 0,'private_completions':2 if is_aux else 0,'guard_delays':int(is_aux),'auxiliary':is_aux})
    monkeypatch.setattr(route.balanced,'witness',lambda text: {'checks':10000,'captures':9216,'same_edge':True,'four_state_exact':True})
    monkeypatch.setattr(route.fence,'witness',lambda text,is_aux: {'local_fault':{'auxiliary':is_aux},'additional_boundaries':6 if is_aux else 0})
    monkeypatch.setattr(route,'verify',lambda p,pin: None)
    monkeypatch.setattr(route,'sha',lambda p:'dcp')
    monkeypatch.setattr(route.main,'audit',lambda p:{'words':64512})
    monkeypatch.setattr(route.auxiliary,'witness',lambda text:{'old_faults':16})
    monkeypatch.setattr(route.identity,'witness',lambda text:{'identity':True})
    monkeypatch.setattr(route.boundaries,'witness',lambda text:{'boundaries':9})
    save(aux/'auxiliary_outcome.json',dict(passed=True,auxiliary={'old_faults':16}))
    save(aux/'boundary_outcome.json',dict(passed=True,output_boundaries={'boundaries':9}))
    for p,is_aux in [(actual,False),(aux,True)]:
        log='REGISTERED_ABORT_PASS checks=10000 fault_edges={} private_captures={} private_writes={} current_publication_fenced=1 next_edge_global_abort=1\n'.format(6 if is_aux else 0,int(is_aux),int(is_aux))
        if is_aux:
            log+=''.join(f'REGISTERED_ABORT_BOUNDARY_PASS boundary={n} new_publications=0 fresh_reads=512 fresh_releases=1\n' for n in range(6))
            log+='REGISTERED_ABORT_BOUNDARIES_PASS cases=6 private_delta_exercised=1 fresh_recovery=1\n'
        directory=p/'project/staged_fft.sim/sim_1/behav/xsim';directory.mkdir(parents=True)
        (directory/'simulate.log').write_text(log)
        save(p/'identity_outcome.json',dict(passed=True,output_identity={'identity':True}))
        save(p/'abort_outcome.json',dict(passed=True,registered_abort=route.abort.witness(log,is_aux)))
        save(p/'product_fence_outcome.json',dict(passed=True,product_current_fence=route.fence.witness(log,is_aux)))
        save(p/'private_replay_outcome.json',dict(passed=True,private_replay_sequence=route.publication.witness(log,is_aux)))
        save(p/'output_retirement_outcome.json',dict(passed=True,output_retirement_receipt=route.out_retirement.witness(log,is_aux)))
        save(p/'private_descriptor_outcome.json',dict(passed=True,private_forward_descriptor=route.descriptor.witness(log,is_aux)))
        save(p/'retirement_outcome.json',dict(passed=True,product_retirement_receipt=route.retirement.witness(log,is_aux)))
        save(p/'parallel_identity_outcome.json',dict(passed=True,parallel_product_identity=route.parallel.witness(log)))
        save(p/'private_status_outcome.json',dict(passed=True,forward_private_status=route.private_status.witness(log,is_aux)))
        save(p/'balanced_identity_outcome.json',dict(passed=True,balanced_forward_identity=route.balanced.witness(log)))
    return actual,synth,aux

def test_complete_route_admission(campaign):
    result=route.evidence(*campaign)
    assert result['registered_abort']['aux']['private_captures']==1
    assert result['registered_abort']['actual']['fault_edges']==0

@pytest.mark.parametrize('folder',[0,2])
@pytest.mark.parametrize('mutation',['missing','failed','changed_count','wrong_campaign'])
def test_abort_receipt_required(campaign,folder,mutation):
    path=campaign[folder]/'abort_outcome.json'
    value=json.loads(path.read_text())
    if mutation=='missing':path.unlink()
    else:
        if mutation=='failed':value['passed']=False
        elif mutation=='changed_count':value['registered_abort']['checks']+=1
        else:value['registered_abort']['auxiliary']=not value['registered_abort']['auxiliary']
        save(path,value)
    with pytest.raises((ValueError,FileNotFoundError)):route.evidence(*campaign)

@pytest.mark.parametrize('mutation',['runtime_count','runtime_contents','private_delta','publication','recovery','fatal'])
def test_changed_source_or_live_witness_rejected(campaign,mutation):
    actual,synth,aux=campaign
    source=Path(json.loads((aux/'outcome.json').read_text())['command'][-3])
    log=aux/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log'
    if mutation=='runtime_count':
        path=source/'profile.tcl';path.write_text(path.read_text().replace('module_26.v',''))
    elif mutation=='runtime_contents':(source/'module_0.v').write_text('changed')
    else:
        before,after={'private_delta':('private_captures=1','private_captures=0'),
                      'publication':('new_publications=0','new_publications=1'),
                      'recovery':('fresh_reads=512','fresh_reads=511'),
                      'fatal':('REGISTERED_ABORT_PASS','FATAL REGISTERED_ABORT_PASS')}[mutation]
        log.write_text(log.read_text().replace(before,after,1))
    with pytest.raises(ValueError):route.evidence(*campaign)

@pytest.mark.parametrize('folder',[0,2])
@pytest.mark.parametrize('mutation',['missing','failed','changed_count','wrong_campaign'])
def test_current_product_fence_receipt_required(campaign,folder,mutation):
    path=campaign[folder]/'product_fence_outcome.json'
    value=json.loads(path.read_text())
    if mutation=='missing':path.unlink()
    else:
        if mutation=='failed':value['passed']=False
        elif mutation=='changed_count':value['product_current_fence']['additional_boundaries']+=1
        else:value['product_current_fence']['local_fault']['auxiliary']=not value['product_current_fence']['local_fault']['auxiliary']
        save(path,value)
    with pytest.raises((ValueError,FileNotFoundError)):route.evidence(*campaign)

@pytest.mark.parametrize('folder',[0,2])
@pytest.mark.parametrize('mutation',['missing','failed','changed_count','wrong_contract'])
def test_balanced_identity_receipt_required(campaign,folder,mutation):
    path=campaign[folder]/'balanced_identity_outcome.json'
    value=json.loads(path.read_text())
    if mutation=='missing':path.unlink()
    else:
        if mutation=='failed':value['passed']=False
        elif mutation=='changed_count':value['balanced_forward_identity']['captures']+=1
        else:value['balanced_forward_identity']['same_edge']=False
        save(path,value)
    with pytest.raises((ValueError,FileNotFoundError)):route.evidence(*campaign)

@pytest.mark.parametrize('folder',[0,2])
@pytest.mark.parametrize('mutation',['missing','failed','changed_count','wrong_campaign'])
def test_private_status_receipt_required(campaign,folder,mutation):
    path=campaign[folder]/'private_status_outcome.json'
    value=json.loads(path.read_text())
    if mutation=='missing':path.unlink()
    else:
        if mutation=='failed':value['passed']=False
        elif mutation=='changed_count':value['forward_private_status']['private_completions']+=1
        else:value['forward_private_status']['auxiliary']=not value['forward_private_status']['auxiliary']
        save(path,value)
    with pytest.raises((ValueError,FileNotFoundError)):route.evidence(*campaign)

@pytest.mark.parametrize('folder',[0,2])
@pytest.mark.parametrize('mutation',['missing','failed','changed_count','wrong_contract'])
def test_parallel_identity_receipt_required(campaign,folder,mutation):
    path=campaign[folder]/'parallel_identity_outcome.json'
    value=json.loads(path.read_text())
    if mutation=='missing':path.unlink()
    else:
        if mutation=='failed':value['passed']=False
        elif mutation=='changed_count':value['parallel_product_identity']['first_refills']+=1
        else:value['parallel_product_identity']['same_edge_capture']=False
        save(path,value)
    with pytest.raises((ValueError,FileNotFoundError)):route.evidence(*campaign)

@pytest.mark.parametrize('folder',[0,2])
@pytest.mark.parametrize('mutation',['missing','failed','changed_count','wrong_campaign'])
def test_retirement_receipt_required(campaign,folder,mutation):
    path=campaign[folder]/'retirement_outcome.json'
    value=json.loads(path.read_text())
    if mutation=='missing':path.unlink()
    else:
        if mutation=='failed':value['passed']=False
        elif mutation=='changed_count':value['product_retirement_receipt']['extra_holds']+=1
        else:value['product_retirement_receipt']['auxiliary']=not value['product_retirement_receipt']['auxiliary']
        save(path,value)
    with pytest.raises((ValueError,FileNotFoundError)):route.evidence(*campaign)

@pytest.mark.parametrize('folder',[0,2])
@pytest.mark.parametrize('mutation',['missing','failed','changed_count','wrong_campaign'])
def test_private_descriptor_receipt_required(campaign,folder,mutation):
    path=campaign[folder]/'private_descriptor_outcome.json'
    value=json.loads(path.read_text())
    if mutation=='missing':path.unlink()
    else:
        if mutation=='failed':value['passed']=False
        elif mutation=='changed_count':value['private_forward_descriptor']['private_differences']+=1
        else:value['private_forward_descriptor']['auxiliary']=not value['private_forward_descriptor']['auxiliary']
        save(path,value)
    with pytest.raises((ValueError,FileNotFoundError)):route.evidence(*campaign)

@pytest.mark.parametrize('folder',[0,2])
@pytest.mark.parametrize('mutation',['missing','failed','changed_count','wrong_campaign'])
def test_output_retirement_receipt_required(campaign,folder,mutation):
    path=campaign[folder]/'output_retirement_outcome.json'
    value=json.loads(path.read_text())
    if mutation=='missing':path.unlink()
    else:
        if mutation=='failed':value['passed']=False
        elif mutation=='changed_count':value['output_retirement_receipt']['checks']+=1
        else:value['output_retirement_receipt']['auxiliary']=not value['output_retirement_receipt']['auxiliary']
        save(path,value)
    with pytest.raises((ValueError,FileNotFoundError)):route.evidence(*campaign)

@pytest.mark.parametrize('folder',[0,2])
@pytest.mark.parametrize('mutation',['missing','failed','changed_count','wrong_campaign'])
def test_publication_cone_receipt_required(campaign,folder,mutation):
    path=campaign[folder]/'private_replay_outcome.json'
    value=json.loads(path.read_text())
    if mutation=='missing':path.unlink()
    else:
        if mutation=='failed':value['passed']=False
        elif mutation=='changed_count':value['private_replay_sequence']['checks']+=1
        else:value['private_replay_sequence']['auxiliary']=not value['private_replay_sequence']['auxiliary']
        save(path,value)
    with pytest.raises((ValueError,FileNotFoundError)):route.evidence(*campaign)

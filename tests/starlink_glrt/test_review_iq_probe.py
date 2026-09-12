"""Retained transport evidence must reject loss, misassociation and early STOP."""
import json

import pytest

from tools.review_glrt_iq_probe import review
from tools.starlink_glrt_tracking_abi import TrackingBatch


@pytest.fixture(params=[30000000,60000000])
def evidence(tmp_path,request):
    rate=request.param;ratio=rate//2500000;total=16384*160;origin=120000000
    batch=TrackingBatch(rate,1,9122001,origin+rate//10,0,(rate<<16)//750,0,0,0,16,origin+rate)
    lines=['submit '+batch.encode().strip()]
    for i in range(160):
        w=[0]*64
        for k,value in ((0,origin),(2,origin+(16384*(i+1)-1)*ratio),
                        (4,16384*(i+1)),(6,16384*(i+1)),(42,origin+16384*(i+1)*ratio)):
            w[k],w[k+1]=value%2**32,value//2**32
        w[19]=0x38 if i==159 else 0x19
        w[62:]=[rate,53*ratio]
        wire=f'GLI1 00010000 {rate} 2500000 {i+1} 0 {rate} 0 0 0 0 0 0 0 '+ ' '.join(f'{x:08x}' for x in w)
        lines.append('capture_snapshot '+wire)
    for i in range(16):
        start,step,phase=batch.prediction(i)
        w=[0]*32
        w[:9]=[0x474c5431,i,9122001,start%2**32,start//2**32,0,step,rate*33//25000,0]
        w[25:]=[rate,rate*33//25000,i,phase,0xb04a2fab,0x10000,0]
        lines.append('tracking_result GLT1 00010000 00000001 '+' '.join(f'{x:08x}' for x in w))
    def tracking(final):
        w=[0]*24;w[:3]=[0x474c5431,1,1];w[5]=2;w[6]=0 if final else 8
        if not final:
            for k in (7,8,14,15,17): w[k]=16
        w[20:]=[rate,rate*33//25000,0xb04a2fab,1]
        return 'tracking_snapshot GLT1SNAP 00010000 '+' '.join(f'{x:08x}' for x in w)
    lines.extend([tracking(False),'capture_final_snapshot '+wire,tracking(True)])
    (tmp_path/'journal.txt').write_text('\n'.join(lines)+'\n')
    (tmp_path/'stdout.json').write_text(json.dumps(dict(rate=rate,status=0,blocks=160,
                                                       results=16,tracking_lock_claimed=False)))
    with (tmp_path/'iq.ci16').open('wb') as f: f.truncate(total*4)
    return tmp_path


def test_full_finite_capture_and_native_retirement(evidence):
    result=review(evidence)
    assert result['status']=='pass' and not result['tracking_lock_qualified']


@pytest.mark.parametrize('during_visit',[False,True])
def test_boot_counters_cannot_be_mistaken_for_current_epoch_losses(evidence,during_visit):
    path=evidence/'journal.txt';lines=path.read_text().splitlines()
    w=[0]*24;w[:3]=[0x474c5431,1,0];w[5]=2;w[19]=5413836
    rate=json.loads((evidence/'stdout.json').read_text())['rate']
    w[20:]=[rate,rate*33//25000,0xb04a2fab,1]
    wire='tracking_snapshot GLT1SNAP 00010000 '+' '.join(f'{v:08x}' for v in w)
    lines.insert(2 if during_visit else 0,wire)
    path.write_text('\n'.join(lines)+'\n')
    if during_visit:
        with pytest.raises(ValueError,match='source drops'): review(evidence)
    else:
        assert review(evidence)['pre_epoch_cdc_pacer_counters']==[[0,5413836]]


@pytest.mark.parametrize('fault',['missing_head','repeated_head','early_stop','unclosed','short_iq','failed_probe'])
def test_incomplete_or_wrong_evidence_cannot_pass(evidence,fault):
    path=evidence/'journal.txt';lines=path.read_text().splitlines()
    heads=[i for i,s in enumerate(lines) if s.startswith('tracking_result')]
    if fault=='missing_head': lines.pop(heads[-1])
    elif fault=='repeated_head': lines[heads[-1]]=lines[heads[-2]]
    elif fault=='early_stop':
        stop=next(s for s in lines if s.startswith('tracking_snapshot'))
        lines.insert(1,stop)
    elif fault=='unclosed': lines=[s for s in lines if not s.startswith('capture_final_snapshot')]
    elif fault=='short_iq': (evidence/'iq.ci16').write_bytes(b'')
    elif fault=='failed_probe':
        p=evidence/'stdout.json';d=json.loads(p.read_text());d['status']=1;p.write_text(json.dumps(d))
    path.write_text('\n'.join(lines)+'\n')
    with pytest.raises(ValueError): review(evidence)

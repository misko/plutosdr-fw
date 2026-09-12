"""Independent retained-evidence review of GLI1 IQ/native transport probes."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from tools.starlink_glrt_tracking_abi import TrackingBatch, TrackingResult, TrackingSnapshot


def require(ok, message):
    if not ok:
        raise ValueError(message)


def capture(text, rate):
    f=text.split()
    require(len(f)==78 and f[:4]==['GLI1','00010000',str(rate),'2500000'], 'GLI1 envelope')
    require(all(re.fullmatch('[0-9a-fA-F]{8}',v) for v in f[14:]), 'GLI1 word encoding')
    h=[int(v) for v in f[4:14]]
    w=[int(v,16) for v in f[14:]]
    require(h[0]>0 and h[1:]==[0,rate,0,0,0,0,0,0,0], 'capture driver/source fault')
    require(w[62:]==[rate,53*(rate//2500000)], 'capture geometry')
    require(not any(w[17:19]+w[24:40]+w[50:57]+w[61:62]), 'capture loss or unexpected acquisition')
    require(w[44]==w[45] and w[46]==w[47], 'capture CDC/pacer loss')
    return h[0],w


def review(root):
    status=json.loads((root/'stdout.json').read_text())
    rate=status['rate']
    require(rate in (30000000,60000000) and status['status']==0 and
        status['blocks']==160 and status['results']==16 and status['tracking_lock_claimed'] is False,
        'probe did not complete')
    require((root/'iq.ci16').stat().st_size==4*16384*160, 'IQ payload size')
    lines=(root/'journal.txt').read_text().splitlines()
    blocks=[];heads=[];tracking=[];batch=None;final=None;clear=None
    pair=lambda w,k:w[k]+(w[k+1]<<32)
    for line in lines:
        if not line: continue
        key,wire=line.split(' ',1)
        if key=='submit':
            require(batch is None, 'duplicate submit')
            f=wire.split()
            require(len(f)==14 and f[:2]==['GLT1','00010000'], 'submit envelope')
            v=[int(x,16) for x in f[2:]]
            require(v[0]==rate and v[1]==0xb04a2fab, 'submitted rate/bank')
            batch=TrackingBatch(v[0],*v[2:])
        elif key=='capture_snapshot':
            gen,w=capture(wire,rate)
            require(w[19]&8 and pair(w,4)>=16384*(len(blocks)+1) and
                    pair(w,6)>=16384*(len(blocks)+1), 'delivered IQ beyond source prefix')
            origin,last=pair(w,0),pair(w,2)
            require(origin%(rate//2500000)==last%(rate//2500000)==0 and
                    last==origin+(pair(w,4)-1)*(rate//2500000), 'noncontiguous native IQ indices')
            require(pair(w,42)>=last, 'source clock behind IQ')
            if blocks:
                old_gen,old=blocks[-1]
                require(0<(gen-old_gen)%2**32<2**31 and origin==pair(old,0) and
                        pair(w,42)>=pair(old,42), 'capture epoch/index regression')
            blocks.append((gen,w))
        elif key=='capture_final_snapshot':
            require(final is None,'duplicate capture closure')
            _,final=capture(wire,rate)
            require(not final[19]&3 and pair(final,4)==pair(final,6)==16384*160,
                    'finite capture did not close completely')
        elif key=='tracking_result':
            require(batch is not None,'result before submission')
            head=TrackingResult.from_sysfs(wire)
            head.require_association(batch,sequence=len(heads))
            require(head.repeat==len(heads),'missing/reordered repeat')
            head.require_complete();heads.append(head)
        elif key=='tracking_snapshot':
            state=TrackingSnapshot.from_sysfs(wire)
            require(state.rate==rate and state.cdc_drops==state.pacer_drops==0,'native source drops')
            require(state.faults in (0,8), 'unexpected tracking fault')
            if state.faults==8:
                require(blocks and not blocks[-1][1][19]&3 and
                        pair(blocks[-1][1],4)==pair(blocks[-1][1],6)==16384*160,
                        'source invalidated before finite stop')
            tracking.append(state)
            if final is not None: clear=state
    require(len(blocks)==160 and len(heads)==16 and final is not None and batch is not None,
            'missing retained evidence')
    require(batch.repeats==16,'wrong configured repeat count')
    terminal=[s for s in tracking if s.configured==16 and s.popped==16]
    require(terminal,'no drained native completion')
    for s in terminal:
        s.require_drained()
        require(s.admitted==s.committed==16 and
                not any((s.late,s.no_space,s.unavailable,s.expired,s.cancelled)), 'native jobs rejected')
    require(clear is not None and not clear.status&16 and clear.faults==clear.configured==0,
            'tracking epoch was not cleared')
    clear.require_drained()
    return {'status':'pass','rate':rate,'iq_samples':16384*160,'native_results':16,
            'native_samples_per_result':rate*33//25000,'cdc_drops':0,'pacer_drops':0,
            'finite_stop_invalidated_epoch':True,'tracking_lock_qualified':False,
            'sha256':{name:hashlib.sha256((root/name).read_bytes()).hexdigest()
                      for name in ('stdout.json','journal.txt','iq.ci16')}}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence',type=Path)
    args=parser.parse_args()
    result=review(args.evidence)
    with (args.evidence/'independent-review.json').open('x') as stream:
        json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result))

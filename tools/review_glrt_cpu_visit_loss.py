"""Read-only clean-loss disposition review from retained component evidence.

Caller separately verifies binary/identity, IQ and numerical evidence, final
capture state, and the parent's transition snapshots. No RF accuracy claim.
"""
from .starlink_glrt_tracking_journal import review as review_native


def review_clean_loss(rows, journal, status, observer_rows):
    assert status['status']==3 and status['stage']=='worker_complete'
    assert status['worker_complete']==1 and status['retention_mode'] in ('full','selected_windows')
    assert status['reacquisitions']==status['native_completed_runs']==0
    assert status['handoffs']==status['native_runs']==1
    assert 0<status['completed_refills']==status['blocks']<=1536
    assert 0<status['attempts']<=6
    rate=status['rate']; assert rate in (30000000,60000000)
    terminals=[(i,r) for i,r in enumerate(rows) if r['kind']=='native_terminal']
    joins=[(i,r) for i,r in enumerate(rows) if r['kind']=='observer_join']
    assert len(terminals)==len(joins)==1
    ti,t=terminals[0];ji,j=joins[0]
    assert ti<ji and t['result']==j['native_result']==-4
    assert t['native_episode']==j['episode']==0
    assert t['epoch']==j['epoch'] and t['attempt']==j['attempt']==status['attempts']
    assert j['observer_joined']==1 and j['observer_result']==0
    assert j['observer_status'] in (0,-2,-3,-4,-5,-6)
    workers=[i for i,r in enumerate(rows) if r['kind']=='worker_terminal' and r['attempt']==t['attempt']]
    assert len(workers)==1 and workers[0]<ti and rows[workers[0]]['status']==1
    checked=review_native(journal,epoch=t['epoch'],rate=rate)
    heads=checked['heads']; estimates=checked['estimates']
    assert heads and 'handoff' in checked
    assert len(heads)==status['native_results']==t['configured']==t['retained_popped']
    assert t['paired_result']==0 and t['paired_queued']==t['paired_copied']==min(len(heads),64)
    for state in (checked['drained'],checked['final']):
        assert state.cdc_drops==state.pacer_drops==state.faults==0
    handoff=checked['handoff']
    last_supported=max([handoff.last_supported]+[e['frame'] for e in estimates if e['rejection']==0])
    assert estimates[-1]['frame']==last_supported+32
    assert estimates[-1]['frame']+1<handoff.limit
    starts=[r for r in observer_rows if r['kind']=='start']
    endings=[r for r in observer_rows if r['kind']=='terminal']
    assert len(starts)==len(endings)==1 and observer_rows[0]==starts[0] and observer_rows[-1]==endings[0]
    for r in (starts[0],endings[0]):
        assert (r['attempt'],r['episode'],r['epoch'])==(t['attempt'],0,t['epoch'])
    assert starts[0]['native_rate']==rate and starts[0]['rate']==2500000
    assert endings[0]['status']==j['observer_status']
    assert 0<=endings[0]['measurements']<=200
    return dict(status='pass',scope='retained_clean_native_loss_and_observer_join',
                epoch=t['epoch'],rate=rate,native_results=len(heads),
                last_supported_frame=last_supported,final_frame=estimates[-1]['frame'],
                native_tracking_qualified=False)

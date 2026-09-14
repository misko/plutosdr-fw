"""Read-only review of bounded ARM reacquisition and native journal ownership.

This supplements IQ arithmetic/source-counter review. It neither recomputes
native estimates nor certifies RF accuracy or a continuously supported track.
"""
from .starlink_glrt_tracking_abi import TrackingSnapshot
from .starlink_glrt_tracking_journal import review as review_native


def review_epochs(capture_text, rows, journals, status):
    rate=status['rate']; ratio=rate//2500000
    assert rate in (30000000,60000000)
    bindings=[]; before=[]
    for line in capture_text.splitlines():
        if line.startswith('epoch_binding '):
            binding=list(map(int,line.split()[1:])); assert len(binding)==4
            assert binding[3]==binding[2]//ratio+1
            if bindings:
                assert binding[0]==bindings[0][0] and binding[1]==bindings[-1][1]+1
                assert binding[2]>bindings[-1][2]
            bindings.append(binding)
        elif line.startswith('tracking_restart_snapshot '):
            state=TrackingSnapshot.from_sysfs(line.split(' ',1)[1])
            state.require_drained()
            assert state.rate==rate and state.status&48==32 and not state.configured
            assert state.faults==state.cdc_drops==state.pacer_drops==0
            before.append(state)
    assert 1<=len(bindings)<=4 and len(bindings)==status['reacquisitions']+1
    restart=[r for r in rows if r['kind']=='reacquisition']
    terminal=[r for r in rows if r['kind']=='native_terminal']
    scans=[r for r in rows if r['kind']=='scan']
    assert len(restart)==len(before)==len(bindings)-1
    assert [r['attempt'] for r in scans]==list(range(1,len(scans)+1))
    assert len(scans)<=status['attempts']<=256
    assert {r['epoch'] for r in scans}<=set(b[1] for b in bindings)
    assert len({r['native_episode'] for r in terminal})==len(terminal)==status['native_runs']
    assert len({r['deadline_ns'] for r in restart})<=1
    names=['native.journal',*(f'native-{i}.journal' for i in range(1,len(bindings)))]
    assert set(journals)==set(names)
    total=completed=handoffs=0; results=[]; paired=[]
    for episode,(binding,name) in enumerate(zip(bindings,names,strict=True)):
        rr=[r for r in terminal if r['native_episode']==episode]
        raw=journals[name]
        if raw==b'GLRJ1\n':
            assert not rr and episode==len(bindings)-1
            results.append(dict(episode=episode,epoch=binding[1],results=0,supported=0))
            continue
        checked=review_native(raw,epoch=binding[1],rate=rate)
        assert len(rr)==1
        t=rr[0]; heads=checked['heads']
        assert t['epoch']==binding[1] and t['retained_popped']==len(heads)
        if t['result'] in (0,-4):
            assert t['configured']==t['retained_popped']
        else:
            assert t['result']==-3 and t['configured']>t['retained_popped']
        assert t['paired_result']==0
        assert any(r['attempt']==t['attempt'] and r['epoch']==binding[1] for r in scans)
        total+=len(heads); handoffs+=bool(heads)
        assert t['paired_queued']==t['paired_copied']==min(total,64)
        completed+=t['result']==0 and len(heads)==1500
        for head in heads:
            assert head.start>=binding[3]*ratio
            if len(paired)<64: paired.append((episode,head.sequence,head.start,binding[1]))
        if episode<len(bindings)-1:
            r=restart[episode]
            assert t['result']==-4 and heads
            assert r['previous_epoch']==before[episode].epoch==binding[1]
            assert before[episode].latest_index<=bindings[episode+1][2]
            assert heads[-1].start+heads[-1].count-1<=before[episode].latest_index
            assert r['native_episode']==episode+1
            assert r['attempts_used']==t['attempt']<r['attempt_limit']<=256
            assert all(s['attempt']<=r['attempts_used'] for s in scans if s['epoch']==binding[1])
            assert all(s['attempt']>r['attempts_used'] for s in scans if s['epoch']==bindings[episode+1][1])
        results.append(dict(episode=episode,epoch=binding[1],results=len(heads),
                            supported=checked['supported'],controller_result=t['result']))
    pairs=[r for r in rows if r['kind']=='native_coarse_iq']
    assert len(pairs)==len(paired)
    for index,(row,expected) in enumerate(zip(pairs,paired,strict=True)):
        assert (row['native_episode'],row['native_sequence'],row['native_start'],row['source']['epoch'])==expected
        assert row['iq_offset']==index*3333 and row['iq_samples']==3333
    assert total==status['native_results'] and completed==status['native_completed_runs']
    assert handoffs==status['handoffs']
    return dict(status='pass',scope='bounded_reacquisition_epochs_and_native_ownership',
                epoch_bindings=bindings,episodes=results,reacquisitions=len(restart),
                native_results=total,native_completed_runs=completed,paired_results=len(pairs),
                live_tracking_qualified=False)

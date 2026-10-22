"""Re-read saved CI16 and verify rate-scaled counters, guards, ordering and payload hashes."""
import argparse
import hashlib
import json
import statistics
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directories',nargs='+',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    summaries=[]
    for directory in args.directories:
        for path in sorted(directory.glob('*/report.json')):
            report=json.loads(path.read_text())
            assert report['passed'],path
            rate=report['rate_hz']; count=rate//50; rx=report['rx_mask'].bit_count()
            guards=[]; starts=[]
            for n,row in enumerate(report['records']):
                record=row['record']; data=(path.parent/f'{n:05d}.ci16').read_bytes()
                assert record['visit']==n and record['target']==n%8
                assert record['source_rate_hz']==rate and record['result']==1
                assert record['valid_end']-record['valid_start']==count
                assert len(data)==record['iq_bytes']==count*4*rx
                assert hashlib.sha256(data).hexdigest()==row['iq_sha256']
                guard=record['valid_start']-max(record['transition_after'],record['selection_counter'])
                assert guard>=count
                assert not record['missing_samples_before']
                assert not starts or record['valid_start']>=starts[-1]+count
                guards.append(guard);starts.append(record['valid_start'])
            restored=report['receipt']['restoration']
            expected, observed = restored['expected'], restored['observed']
            # AGC gain is an observation, not restorable state. Require exact
            # settable settings and exact gains on receivers restored to manual.
            assert {k:v for k,v in expected.items() if k != 'gain_db'} == {
                k:v for k,v in observed.items() if k != 'gain_db'}
            assert all(mode != 'manual' or a == b for mode,a,b in zip(
                expected['gain_modes'],expected['gain_db'],observed['gain_db'],strict=True))
            assert restored['expected_kernel_buffers']==restored['observed_kernel_buffers']
            assert restored['fastlock_inactive']
            terminal=report['receipt']['terminal']
            assert terminal['flags']&1 and not terminal['error']
            summaries.append({'report':str(path),'rate_hz':rate,'rx_mask':report['rx_mask'],
                'windows':len(starts),'bytes':report['bytes'],'minimum_guard_ms':min(guards)*1000/rate,
                'median_sweep_ms':statistics.median([b-a for a,b in zip(starts,starts[8:])])*1000/rate,
                'saved_iq_verified':True,'settings_restored':True})
    assert summaries
    result={'passed':True,'windows':sum(r['windows'] for r in summaries),
        'bytes':sum(r['bytes'] for r in summaries),'cells':summaries}
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':
    main()

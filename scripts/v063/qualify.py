"""Bounded RX-only multirate eight-target hardware qualification; retain every window."""
import argparse
import dataclasses
import hashlib
import json
import secrets
import time
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host', required=True)
    p.add_argument('--serial', required=True)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--rates', default='1250000,2500000,5000000,7500000,10000000')
    p.add_argument('--windows', type=int, default=80)
    p.add_argument('--rx-mask', type=int, default=3)
    p.add_argument('--block-samples', type=int)
    args = p.parse_args()
    from pluto_plus.hardware.preflight import verify_metadata_runtime
    from pluto_plus.continuous_scan import build_continuous_setup, ContinuousClient
    from pluto_plus.continuous_scan_radio import ContinuousRadioOwner
    from pluto_plus.radio_lock import acquire_radio_lock
    import iio
    args.output.mkdir(parents=True, exist_ok=False)
    runtime = dataclasses.asdict(verify_metadata_runtime(3))
    context = iio.Context('ip:' + args.host)
    assert context.attrs['hw_serial'] == args.serial
    identity = dict(context.attrs)
    del context
    summaries = []
    with acquire_radio_lock(args.serial):
        for rate in map(int, args.rates.split(',')):
            setup = build_continuous_setup(session=secrets.randbits(63) or 1,
                generation=secrets.randbits(63) or 1, seed=secrets.randbits(63) or 1,
                source_rate_hz=rate, rx_mask=args.rx_mask,
                frequencies_hz=tuple(1_800_000_000 + i*10_000_000 for i in range(8)),
                analysis_digest=hashlib.sha256(b'v063-multirate-rx-qualification').digest())
            directory = args.output / str(rate)
            directory.mkdir()
            windows = []
            owner = None
            started = time.monotonic()
            report = {'rate_hz': rate, 'rx_mask': args.rx_mask, 'identity': identity,
                'runtime': runtime, 'requested_windows': args.windows, 'tx_enabled': False}
            try:
                owner = ContinuousRadioOwner.start('ip:'+args.host, args.serial, setup,
                    samples_per_block=args.block_samples or max(25000,rate//25))
                stopped = False
                for visit in owner.visits():
                    record = visit.record
                    payload = visit.iq
                    assert record.result.name == 'COMPLETE', record
                    assert len(payload) == rate//50 * 4 * args.rx_mask.bit_count()
                    assert record.valid_end-record.valid_start == rate//50
                    assert record.valid_start-max(record.transition_after,record.selection_counter) >= rate//50
                    assert record.target == len(windows)%8
                    windows.append((record, bytes(payload), time.monotonic()))
                    if len(windows) >= args.windows and not stopped:
                        owner.stop()
                        stopped=True
                receipt = owner.close()
                report['receipt'] = dataclasses.asdict(receipt)
                terminal = dataclasses.asdict(receipt.terminal)
                assert terminal['error'] == 0 and terminal['state'] == 1, terminal
                assert terminal['delivered'] == len(windows)
                assert all(terminal[k] == 0 for k in ('skipped','invalid','cancelled'))
                report['passed'] = True
            except BaseException as error:
                report['passed'] = False
                report['error'] = repr(error)
                if owner:
                    report['diagnostics'] = owner.session.failure_diagnostics
                    try:
                        owner.abort_read()
                        report['cleanup'] = dataclasses.asdict(owner.close())
                    except BaseException as cleanup:
                        report['cleanup_error'] = repr(cleanup)
                raise
            finally:
                # Write after release to avoid disk latency delaying DMA consumption.
                metadata=[]
                for n,(record,payload,observed) in enumerate(windows):
                    (directory/f'{n:05d}.ci16').write_bytes(payload)
                    metadata.append({'record':dataclasses.asdict(record),
                        'iq_sha256': hashlib.sha256(payload).hexdigest(), 'observed_monotonic':observed})
                report['windows'] = len(windows)
                report['bytes'] = sum(len(w[1]) for w in windows)
                report['wall_seconds'] = time.monotonic()-started
                report['records'] = metadata
                (directory/'report.json').write_text(json.dumps(report,indent=2,default=str)+'\n')
                summaries.append({k:v for k,v in report.items() if k not in ('records','receipt','runtime','identity')})
                (args.output/'summary.json').write_text(json.dumps(summaries,indent=2,default=str)+'\n')
                print(json.dumps(summaries[-1],default=str),flush=True)


if __name__ == '__main__':
    main()

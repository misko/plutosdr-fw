#!/usr/bin/env python3
"""One 10.067-second .20 live CPU acquisition/native-feedback qualification."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import uuid

from leo.acquisition.authority import LocalCaptureAuthority, RadioResource, CaptureTaskKind
from pluto_plus import bootstrap_firmware as b
from pluto_plus import glrt_canary as g
from pluto_plus.glrt_iq_tracking_profiles import ENDPOINT
from pluto_plus.radio_lock import acquire_radio_lock
from pluto_plus.release_candidate_rx_only_linux import _close_iio_context
from deploy_glrt_iq_tracking20 import EVIDENCE, PASSWORD

ARTIFACTS = ('capture.txt', 'iq.ci16', 'worker.jsonl', 'worker.iq.ci16', 'grids.u32', 'native.journal')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deployment', type=Path, required=True)
    parser.add_argument('--rate', type=int, choices=(30000000, 60000000), required=True)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--lo-hz', type=int, default=1690312496,
                        help='Receive LO for this one bounded dwell; default is the historical .20 upper edge')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 70000000 <= args.lo_hz <= 6000000000:
        raise ValueError('receive LO is outside the AD9361 range')
    plan, profile = g.deployment_identity(args.deployment, serial=ENDPOINT[0], host=ENDPOINT[1])
    if plan['expected_firmware'] != f'glrt-iq-tracking-r{args.rate}-v1':
        raise ValueError('deployment rate differs')
    payload = {'probe': args.binary.read_bytes(), 'bank': (EVIDENCE/'coarse-bank.ci16').read_bytes(),
               'references': (EVIDENCE/'direct-references.ci16').read_bytes()}
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in payload.items()}
    if hashes['bank'] != 'd9f3452e45180c560a200bb76c9bfe2d7c46b17560fd46495ea74c50f50547f0' or \
       hashes['references'] != '78b50e1aea5c350889b0798fc691491299925932e496a918cd5fbd3b9bc4faf2':
        raise ValueError('reference bank differs from reviewed image')
    args.output.mkdir(parents=True, exist_ok=False)
    evidence = {'rate': args.rate, 'requested_lo_hz': args.lo_hz, 'rf_sample_limit': 16384*1536,
                'rf_duration_limit_s': 16384*1536/2500000, 'payload_sha256': hashes,
                'status': 'started', 'live_tracking_qualified': False}
    remote = '/tmp/gli-live20-'+uuid.uuid4().hex
    evidence['remote_directory'] = remote
    ssh = ['sshpass', '-f', str(PASSWORD), 'ssh', '-o', 'StrictHostKeyChecking=yes',
           '-o', 'UserKnownHostsFile='+str(EVIDENCE/'radio20.known_hosts'),
           '-o', 'ConnectTimeout=5', 'root@'+ENDPOINT[1]]

    def run(command, data=None, timeout=45):
        return subprocess.run([*ssh, command], input=data, capture_output=True, timeout=timeout)

    def save():
        (args.output/'operator.json').write_text(json.dumps(evidence, indent=2)+'\n')

    authority = LocalCaptureAuthority(Path('/srv/bulk/leo/control'), (
        RadioResource('radio_pluto_5d4d', ENDPOINT[0], 'ip:'+ENDPOINT[1]),))
    try:
        lease = authority.claim(('radio_pluto_5d4d',), task_id='gli20-'+args.output.name,
                                task_kind=CaptureTaskKind.QUALIFICATION)
    except Exception as error:
        evidence.update(status='admission_refused', error=f'{type(error).__name__}: {error}',
                        rf_samples_collected=0)
        save()
        raise
    with lease, acquire_radio_lock(ENDPOINT[0]):
        transport = b.BoundSshBootstrapTransport(interface=None, host=ENDPOINT[1],
            password=PASSWORD.read_text().strip(), known_hosts_file=EVIDENCE/'radio20.known_hosts')
        staged = terminal = retrieved = False
        try:
            evidence['before'] = g.attest_tx_safe_idle(transport, plan, serial=ENDPOINT[0],
                host=ENDPOINT[1], layout=profile.return_iio_layout)
            import iio
            context = iio.Context('ip:'+ENDPOINT[1])
            try:
                context.set_timeout(5000)
                if context.attrs['hw_serial'] != ENDPOINT[0] or context.attrs['fw_version'] != plan['expected_firmware']:
                    raise ValueError('configuration identity differs')
                evidence['configured'] = g.configure_checked_rx(context, lo=args.lo_hz,
                    bandwidth=2500000, gain=30, port='A_BALANCED', source_rate=args.rate,
                    base_abi='GLI1-1.0-upper-only')
                evidence['calibration'] = {}
                save()
                g.calibrate_rx(context.find_device('ad9361-phy'), source_rate=args.rate,
                               evidence=evidence['calibration'])
            finally:
                _close_iio_context(iio, context)
                save()
            run('mkdir '+shlex.quote(remote)).check_returncode()
            staged = True
            for name, data in payload.items():
                run('cat > '+shlex.quote(remote+'/'+name), data).check_returncode()
                check = run('sha256sum '+shlex.quote(remote+'/'+name));check.check_returncode()
                if check.stdout.decode().split()[0] != hashes[name]:
                    raise ValueError('staged payload differs')
            run('chmod 700 '+shlex.quote(remote+'/probe')).check_returncode()
            print(json.dumps({'phase': 'starting_bounded_live_capture', 'rate': args.rate}), flush=True)
            result = run(shlex.join([remote+'/probe', str(args.rate), ENDPOINT[0],
                                    remote+'/bank', remote+'/references', remote]))
            terminal = True
            evidence['probe_exit_code'] = result.returncode
            (args.output/'stdout.json').write_bytes(result.stdout)
            (args.output/'stderr.txt').write_bytes(result.stderr)
            evidence['artifacts'] = {}
            for name in ARTIFACTS:
                present = run('test -f '+shlex.quote(remote+'/'+name))
                if present.returncode == 1:
                    evidence['artifacts'][name] = None
                    continue
                present.check_returncode()
                data = run('cat '+shlex.quote(remote+'/'+name));data.check_returncode()
                (args.output/name).write_bytes(data.stdout)
                evidence['artifacts'][name] = {'bytes': len(data.stdout), 'sha256': hashlib.sha256(data.stdout).hexdigest()}
            retrieved = True
            result.check_returncode()
            context = iio.Context('ip:'+ENDPOINT[1])
            try:
                context.set_timeout(5000)
                if context.attrs['hw_serial'] != ENDPOINT[0] or context.attrs['fw_version'] != plan['expected_firmware']:
                    raise ValueError('post-capture radio identity differs')
                evidence['rf_after'] = g.rf_state(context.find_device('ad9361-phy'))
                if evidence['rf_after'] != evidence['configured']['rf_state']:
                    raise ValueError('RF settings changed during the bounded capture')
            finally:
                _close_iio_context(iio, context)
            evidence['status'] = 'capture_complete_review_pending'
        except BaseException as error:
            evidence.update(status='failed', error=f'{type(error).__name__}: {error}')
            raise
        finally:
            try:
                evidence['after'] = g.attest_tx_safe_idle(transport, plan, serial=ENDPOINT[0],
                    host=ENDPOINT[1], layout=profile.return_iio_layout)
                if staged and terminal and retrieved:
                    names = (*payload, *ARTIFACTS)
                    run('rm -f '+shlex.join([remote+'/'+name for name in names])+
                        ' && rmdir '+shlex.quote(remote)).check_returncode()
                    evidence['temporary_files_removed'] = True
            finally:
                save()
    print(json.dumps({'status': evidence['status'], 'rate': args.rate, 'output': str(args.output)}), flush=True)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""One bounded .20 live CPU acquisition/native-feedback qualification."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shlex
import subprocess
import sys
import uuid

# Use the component's public GLT1 decoder, including its counter invariants.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.starlink_glrt_tracking_abi import TrackingSnapshot

from leo.acquisition.authority import LocalCaptureAuthority, RadioResource, CaptureTaskKind
from pluto_plus import bootstrap_firmware as b
from pluto_plus import glrt_canary as g
from pluto_plus.glrt_iq_tracking_profiles import ENDPOINT
from pluto_plus.radio_lock import acquire_radio_lock
from pluto_plus.release_candidate_rx_only_linux import _close_iio_context
from deploy_glrt_iq_tracking20 import EVIDENCE, PASSWORD

ARTIFACTS = ('capture.txt', 'iq.ci16', 'worker.jsonl', 'worker.iq.ci16', 'grids.u32', 'native.journal',
             'native.coarse.ci16', 'observer.jsonl', 'observer.iq.ci16')


def retention_budget_kib(blocks):
    if blocks not in (1536, 4096, 45000):
        raise ValueError('unsupported capture length')
    # Long expanded-scan modes bound worker IQ to 80 MB, searched IQ to 14.4 MB and
    # grids to 37.6 MB. The 256-MiB allowance also covers capture/worker
    # journals, native evidence and <= 10.56 MB of observer IQ (4*200*3300*4)
    # without retaining all 2.95 GB of raw IQ. Short profiles permit one episode
    # (2.64 MB); their existing 40-MiB filesystem / 80-MiB memory margin covers it.
    return 256*1024 if blocks == 45000 else 16384*blocks*4//1024


def observer_profile(blocks, spacing, candidate_budget=8):
    retention_budget_kib(blocks)
    if spacing not in (3,9) or (spacing==3 and blocks!=1536 and not (blocks==45000 and candidate_budget in (64,80))):
        raise ValueError('three-frame observer requires a bounded selected-IQ profile')
    if candidate_budget not in (8,64,80) or (candidate_budget>8 and (blocks not in (1536,45000) or spacing!=3)):
        raise ValueError('expanded candidates require a bounded selected-IQ three-frame observer profile')
    if candidate_budget>8:
        suffix='scan64' if candidate_budget==64 else 'scan80-local2'
        return f'1536-selected-observer3-{suffix}' if blocks==1536 else f'45000-selected-observer3-{suffix}'
    return '1536-selected-observer3' if spacing==3 else str(blocks)


def capture_artifacts(blocks, observer_spacing=9, candidate_budget=8):
    retention_budget_kib(blocks)
    observer_profile(blocks,observer_spacing,candidate_budget)
    names = tuple('scan.iq.ci16' if (blocks == 45000 or observer_spacing==3) and name == 'iq.ci16' else name
                  for name in ARTIFACTS)
    # At most three clean-loss restarts. Unopened episode files are recorded
    # as absent; every actual journal stays independently reviewable as GLRJ1.
    return names + tuple(f'native-{n}.journal' for n in range(1,4)) if blocks == 45000 else names


def preflight_memory(memory_info, blocks, evidence):
    required_kib = retention_budget_kib(blocks) + 80*1024
    matches = re.findall(r'^MemAvailable:\s+(\d+) kB$', memory_info, re.MULTILINE)
    if len(matches) != 1:
        raise ValueError('missing or malformed MemAvailable')
    available_kib = int(matches[0])
    evidence['memory_preflight'] = {'available_kib': available_kib, 'required_kib': required_kib,
                                  'headroom_kib': 80*1024}
    if available_kib < required_kib:
        raise ValueError('insufficient RAM for retained capture and worker headroom')


def preflight_filesystem(output, remote, blocks, evidence):
    # BusyBox df -Pk produces one header and one row for this exact path.
    lines = output.splitlines()
    fields = lines[1].split() if len(lines) == 2 else []
    if len(fields) != 6 or fields[0] != 'tmpfs' or not fields[3].isdigit() or \
       fields[5] != (remote if blocks != 1536 else '/tmp'):
        raise ValueError('unexpected evidence filesystem')
    required_kib = retention_budget_kib(blocks) + 40*1024
    evidence['filesystem_preflight'] = {'available_kib': int(fields[3]),
        'required_kib': required_kib, 'mountpoint': fields[5], 'df': output}
    if int(fields[3]) < required_kib:
        raise ValueError('insufficient evidence filesystem space')


def cleanup_evidence(run, remote, names, *, mounted, execution_attempted, terminal, retrieved):
    if execution_attempted and not (terminal and retrieved):
        return False
    run('rm -f '+shlex.join([remote+'/'+name for name in names])).check_returncode()
    if mounted:
        run('umount '+shlex.quote(remote)).check_returncode()
    run('rmdir '+shlex.quote(remote)).check_returncode()
    return True


def configure_idle_rx(context, *, rate, lo_hz, evidence, memory_info, blocks):
    preflight_memory(memory_info, blocks, evidence)
    device = context.find_device('starlink-glrt-iq')
    if device is None:
        raise ValueError('missing GLI1 capture device')
    wire = device.attrs['tracking_snapshot'].value
    evidence['tracking_before_configuration'] = wire
    state = TrackingSnapshot.from_sysfs(wire)
    state.require_drained()
    if state.rate != rate or state.status & 16 or state.faults or state.configured:
        raise ValueError('tracking must be drained and cleared before RF configuration')
    return g.configure_checked_rx(context, lo=lo_hz, bandwidth=2500000, gain=30,
                                  port='A_BALANCED', source_rate=rate,
                                  base_abi='GLI1-1.0-upper-only')


def check_terminal_capture(context, result, expected_firmware, evidence):
    # Retain the final RF comparison even when the executable reports a
    # tracking failure. A nonzero exit remains a failed qualification.
    if context.attrs['hw_serial'] != ENDPOINT[0] or context.attrs['fw_version'] != expected_firmware:
        raise ValueError('post-capture radio identity differs')
    evidence['rf_after'] = g.rf_state(context.find_device('ad9361-phy'))
    if evidence['rf_after'] != evidence['configured']['rf_state']:
        raise ValueError('RF settings changed during the bounded capture')
    result.check_returncode()


def require_observer_artifacts(evidence):
    # Even a dwell with no acquisition creates two empty observer files.
    # An older executable cannot qualify this composition by omitting them.
    for name in ('observer.jsonl', 'observer.iq.ci16'):
        if evidence['artifacts'].get(name) is None:
            raise ValueError('missing passive observer evidence: '+name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deployment', type=Path, required=True)
    parser.add_argument('--rate', type=int, choices=(30000000, 60000000), required=True)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--observer-spacing',type=int,choices=(3,9),default=9)
    parser.add_argument('--candidate-budget',type=int,choices=(8,64,80),default=8)
    parser.add_argument('--blocks', type=int, choices=(1536, 4096, 45000), default=1536,
                        help='1536/4096 retain full IQ for 10.066/26.844 s; '
                             '45000 retains searched windows for at most 294.912 s; expanded scans permit 256 attempts')
    parser.add_argument('--lo-hz', type=int, default=1690312496,
                        help='Receive LO for this one bounded dwell; default is the historical .20 upper edge')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    selected_profile=observer_profile(args.blocks,args.observer_spacing,args.candidate_budget)
    artifacts = capture_artifacts(args.blocks,args.observer_spacing,args.candidate_budget)
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
    evidence = {'rate': args.rate, 'requested_lo_hz': args.lo_hz, 'blocks': args.blocks,
                'rf_sample_limit': 16384*args.blocks,
                'rf_duration_limit_s': 16384*args.blocks/2500000, 'payload_sha256': hashes,
                'profile': selected_profile,
                'candidate_budget': args.candidate_budget,
                'ranking_fft': 512 if args.candidate_budget==80 else 4096 if args.candidate_budget==64 else 16384,
                'ranking_timing_radius': 2 if args.candidate_budget==80 else 0,
                'retention_mode': 'selected_windows' if args.blocks == 45000 or args.observer_spacing==3 else 'full',
                'passive_observer': {'rate': 2500000, 'feedback_authority': False,
                                     'frame_spacing': args.observer_spacing,
                                     'maximum_measurements_per_episode': 200, 'maximum_episodes': 4 if args.blocks == 45000 else 1},
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
        staged = mounted = execution_attempted = terminal = retrieved = False
        try:
            evidence['before'] = g.attest_tx_safe_idle(transport, plan, serial=ENDPOINT[0],
                host=ENDPOINT[1], layout=profile.return_iio_layout)
            memory = run('cat /proc/meminfo');memory.check_returncode()
            evidence['memory_before'] = memory.stdout.decode()
            preflight_memory(evidence['memory_before'], args.blocks, evidence)
            run('mkdir '+shlex.quote(remote)).check_returncode()
            staged = True
            if args.blocks != 1536:
                run('mount -t tmpfs -o size=320m,nosuid,nodev tmpfs '+shlex.quote(remote)).check_returncode()
                mounted = True
                evidence['private_tmpfs_kib'] = 320*1024
            filesystem = run('df -Pk '+shlex.quote(remote));filesystem.check_returncode()
            preflight_filesystem(filesystem.stdout.decode(), remote, args.blocks, evidence)
            import iio
            context = iio.Context('ip:'+ENDPOINT[1])
            try:
                context.set_timeout(5000)
                if context.attrs['hw_serial'] != ENDPOINT[0] or context.attrs['fw_version'] != plan['expected_firmware']:
                    raise ValueError('configuration identity differs')
                evidence['configured'] = configure_idle_rx(context, rate=args.rate,
                    lo_hz=args.lo_hz, evidence=evidence, blocks=args.blocks,
                    memory_info=evidence['memory_before'])
                evidence['calibration'] = {}
                save()
                g.calibrate_rx(context.find_device('ad9361-phy'), source_rate=args.rate,
                               evidence=evidence['calibration'])
            finally:
                _close_iio_context(iio, context)
                save()
            for name, data in payload.items():
                run('cat > '+shlex.quote(remote+'/'+name), data).check_returncode()
                check = run('sha256sum '+shlex.quote(remote+'/'+name));check.check_returncode()
                if check.stdout.decode().split()[0] != hashes[name]:
                    raise ValueError('staged payload differs')
            run('chmod 700 '+shlex.quote(remote+'/probe')).check_returncode()
            print(json.dumps({'phase': 'starting_bounded_live_capture', 'rate': args.rate}), flush=True)
            command = [remote+'/probe', str(args.rate), ENDPOINT[0],
                       remote+'/bank', remote+'/references', remote]
            if args.blocks != 1536 or args.observer_spacing==3:
                command.append(selected_profile)
            execution_attempted = True
            result = run(shlex.join(command), timeout=340 if args.blocks == 45000 else 60 if args.blocks == 4096 else 45)
            terminal = True
            evidence['probe_exit_code'] = result.returncode
            (args.output/'stdout.json').write_bytes(result.stdout)
            (args.output/'stderr.txt').write_bytes(result.stderr)
            evidence['artifacts'] = {}
            for name in artifacts:
                present = run('test -f '+shlex.quote(remote+'/'+name))
                if present.returncode == 1:
                    evidence['artifacts'][name] = None
                    continue
                present.check_returncode()
                data = run('cat '+shlex.quote(remote+'/'+name));data.check_returncode()
                (args.output/name).write_bytes(data.stdout)
                evidence['artifacts'][name] = {'bytes': len(data.stdout), 'sha256': hashlib.sha256(data.stdout).hexdigest()}
            retrieved = True
            context = iio.Context('ip:'+ENDPOINT[1])
            try:
                context.set_timeout(5000)
                check_terminal_capture(context,result,plan['expected_firmware'],evidence)
                require_observer_artifacts(evidence)
            finally:
                _close_iio_context(iio, context)
            evidence['status'] = 'bounded_capture_review_pending' if args.blocks == 45000 else 'capture_complete_review_pending'
        except BaseException as error:
            evidence.update(status='failed', error=f'{type(error).__name__}: {error}')
            raise
        finally:
            try:
                evidence['after'] = g.attest_tx_safe_idle(transport, plan, serial=ENDPOINT[0],
                    host=ENDPOINT[1], layout=profile.return_iio_layout)
                if staged:
                    names = (*payload, *artifacts)
                    evidence['temporary_files_removed'] = cleanup_evidence(run, remote, names,
                        mounted=mounted, execution_attempted=execution_attempted,
                        terminal=terminal, retrieved=retrieved)
            finally:
                save()
    print(json.dumps({'status': evidence['status'], 'rate': args.rate, 'output': str(args.output)}), flush=True)


if __name__ == '__main__':
    main()

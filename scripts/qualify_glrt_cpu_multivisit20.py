#!/usr/bin/env python3
"""Run bounded 30-MS/s authority tracking across upper-edge LO visits."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qualify_glrt_cpu_live20 as live

UPPER_EDGE_LOS = (1190312500, 1440312500, 1690312500, 1940312500)
BLOCKS = 45000
PROFILE = '45000-selected-observer9-scan80-local2-track10-authority'
SOURCE_SECONDS_PER_VISIT = 16384 * BLOCKS / 2_500_000


def validate_los(values):
    values = tuple(values)
    if not 1 <= len(values) <= 4 or len(set(values)) != len(values) or \
            any(value not in UPPER_EDGE_LOS for value in values):
        raise ValueError('LO plan requires one to four distinct reviewed upper-edge centers')
    if len(values) * SOURCE_SECONDS_PER_VISIT >= 30 * 60:
        raise ValueError('LO plan exceeds the 30-minute RF bound')
    return values


def decode_status(raw, rate):
    lines = raw.decode().splitlines()
    if len(lines) != 1:
        raise ValueError('probe returned an ambiguous status stream')
    status = json.loads(lines[0])
    required = {'scope', 'rate', 'status', 'blocks', 'attempts', 'handoffs',
                'native_results', 'native_completed_runs', 'worker_complete'}
    if not required <= set(status) or status['rate'] != rate or status['status'] != 0 or \
            status['blocks'] > BLOCKS or status['attempts'] > 256:
        raise ValueError('probe status is not a completed bounded visit')
    complete = status['native_completed_runs'] == 1
    if status['native_completed_runs'] not in (0, 1) or \
            complete and (status['native_results'] < 7500 or status['handoffs'] < 1 or
                          status['worker_complete'] != 1):
        raise ValueError('completed-track counters are inconsistent')
    return status, complete


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deployment', type=Path, required=True)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--lo-hz', type=int, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    los = validate_los(args.lo_hz)
    rate = 30_000_000
    selected = live.observer_profile(BLOCKS, 9, 80, 10, True)
    if selected != PROFILE:
        raise ValueError('long authority profile identity differs')
    artifacts = live.capture_artifacts(BLOCKS, 9, 80, 10, True)
    plan, deployment_profile = live.g.deployment_identity(
        args.deployment, serial=live.ENDPOINT[0], host=live.ENDPOINT[1])
    if plan['expected_firmware'] != 'glrt-iq-tracking-r30000000-v1':
        raise ValueError('deployment is not the reviewed 30-MS/s image')
    payload = {'probe': args.binary.read_bytes(),
               'bank': (live.EVIDENCE/'coarse-bank.ci16').read_bytes(),
               'references': (live.EVIDENCE/'direct-references.ci16').read_bytes()}
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in payload.items()}
    if hashes['bank'] != 'd9f3452e45180c560a200bb76c9bfe2d7c46b17560fd46495ea74c50f50547f0' or \
       hashes['references'] != '78b50e1aea5c350889b0798fc691491299925932e496a918cd5fbd3b9bc4faf2':
        raise ValueError('reference bank differs from reviewed image')

    args.output.mkdir(parents=True, exist_ok=False)
    evidence = {
        'scope': 'bounded_host_supervised_arm_fpga_frequency_visits',
        'rate': rate,
        'profile': PROFILE,
        'serial': live.ENDPOINT[0],
        'lo_plan_hz': list(los),
        'maximum_source_seconds': len(los) * SOURCE_SECONDS_PER_VISIT,
        'payload_sha256': hashes,
        'visits': [],
        'status': 'started',
        'live_tracking_qualified': False,
    }

    def save():
        (args.output/'operator.json').write_text(json.dumps(evidence, indent=2)+'\n')

    authority = live.LocalCaptureAuthority(Path('/srv/bulk/leo/control'), (
        live.RadioResource('radio_pluto_5d4d', live.ENDPOINT[0], 'ip:'+live.ENDPOINT[1]),))
    try:
        lease = authority.claim(('radio_pluto_5d4d',), task_id='gli20-multivisit-'+args.output.name,
                                task_kind=live.CaptureTaskKind.QUALIFICATION)
    except Exception as error:
        evidence.update(status='admission_refused', error=f'{type(error).__name__}: {error}',
                        rf_samples_collected=0)
        save()
        raise

    with lease, live.acquire_radio_lock(live.ENDPOINT[0]):
        transport = live.b.BoundSshBootstrapTransport(interface=None, host=live.ENDPOINT[1],
            password=live.PASSWORD.read_text().strip(), known_hosts_file=live.EVIDENCE/'radio20.known_hosts')
        ssh = ['sshpass', '-f', str(live.PASSWORD), 'ssh', '-o', 'StrictHostKeyChecking=yes',
               '-o', 'UserKnownHostsFile='+str(live.EVIDENCE/'radio20.known_hosts'),
               '-o', 'ConnectTimeout=5', 'root@'+live.ENDPOINT[1]]

        def run(command, data=None, timeout=45):
            return subprocess.run([*ssh, command], input=data, capture_output=True, timeout=timeout)

        try:
            evidence['before'] = live.g.attest_tx_safe_idle(transport, plan, serial=live.ENDPOINT[0],
                host=live.ENDPOINT[1], layout=deployment_profile.return_iio_layout)
            for number, lo_hz in enumerate(los):
                visit_dir = args.output/f'visit-{number}'
                visit_dir.mkdir()
                visit = {'number': number, 'requested_lo_hz': lo_hz, 'status': 'started'}
                evidence['visits'].append(visit);save()
                remote = '/tmp/gli-live20-'+uuid.uuid4().hex
                visit['remote_directory'] = remote
                staged = mounted = execution_attempted = terminal = retrieved = False
                try:
                    memory = run('cat /proc/meminfo');memory.check_returncode()
                    visit['memory_before'] = memory.stdout.decode()
                    live.preflight_memory(visit['memory_before'], BLOCKS, visit)
                    run('mkdir '+shlex.quote(remote)).check_returncode();staged = True
                    run('mount -t tmpfs -o size=320m,nosuid,nodev tmpfs '+shlex.quote(remote)).check_returncode()
                    mounted = True;visit['private_tmpfs_kib'] = 320*1024
                    filesystem = run('df -Pk '+shlex.quote(remote));filesystem.check_returncode()
                    live.preflight_filesystem(filesystem.stdout.decode(), remote, BLOCKS, visit)
                    import iio
                    context = iio.Context('ip:'+live.ENDPOINT[1])
                    try:
                        context.set_timeout(5000)
                        if context.attrs['hw_serial'] != live.ENDPOINT[0] or \
                                context.attrs['fw_version'] != plan['expected_firmware']:
                            raise ValueError('configuration identity differs')
                        visit['configured'] = live.configure_idle_rx(context, rate=rate, lo_hz=lo_hz,
                            evidence=visit, memory_info=visit['memory_before'], blocks=BLOCKS)
                        visit['calibration'] = {}
                        save()
                        live.g.calibrate_rx(context.find_device('ad9361-phy'), source_rate=rate,
                                            evidence=visit['calibration'])
                    finally:
                        live._close_iio_context(iio, context);save()
                    for name, data in payload.items():
                        run('cat > '+shlex.quote(remote+'/'+name), data).check_returncode()
                        check = run('sha256sum '+shlex.quote(remote+'/'+name));check.check_returncode()
                        if check.stdout.decode().split()[0] != hashes[name]:
                            raise ValueError('staged payload differs')
                    run('chmod 700 '+shlex.quote(remote+'/probe')).check_returncode()
                    print(json.dumps({'phase':'starting_visit','number':number,'lo_hz':lo_hz}), flush=True)
                    command = [remote+'/probe', str(rate), live.ENDPOINT[0], remote+'/bank',
                               remote+'/references', remote, PROFILE]
                    execution_attempted = True
                    result = run(shlex.join(command), timeout=340);terminal = True
                    visit['probe_exit_code'] = result.returncode
                    (visit_dir/'stdout.json').write_bytes(result.stdout)
                    (visit_dir/'stderr.txt').write_bytes(result.stderr)
                    visit['artifacts'] = {}
                    for name in artifacts:
                        present = run('test -f '+shlex.quote(remote+'/'+name))
                        if present.returncode == 1:
                            visit['artifacts'][name] = None;continue
                        present.check_returncode()
                        data = run('cat '+shlex.quote(remote+'/'+name));data.check_returncode()
                        (visit_dir/name).write_bytes(data.stdout)
                        visit['artifacts'][name] = {'bytes':len(data.stdout),
                                                    'sha256':hashlib.sha256(data.stdout).hexdigest()}
                    retrieved = True
                    context = iio.Context('ip:'+live.ENDPOINT[1])
                    try:
                        context.set_timeout(5000)
                        live.check_terminal_capture(context,result,plan['expected_firmware'],visit)
                        live.require_observer_artifacts(visit)
                    finally:
                        live._close_iio_context(iio, context)
                    status, complete = decode_status(result.stdout, rate)
                    visit.update(status='track_complete_review_pending' if complete else 'negative_review_pending',
                                 probe=status, track_complete=complete)
                except BaseException as error:
                    visit.update(status='failed', error=f'{type(error).__name__}: {error}');save()
                    raise
                finally:
                    if staged:
                        visit['temporary_files_removed'] = live.cleanup_evidence(run, remote,
                            (*payload,*artifacts), mounted=mounted, execution_attempted=execution_attempted,
                            terminal=terminal, retrieved=retrieved)
                    save()
                if visit['track_complete']:
                    evidence['status'] = 'track_complete_review_pending';break
            else:
                evidence['status'] = 'plan_exhausted_review_pending'
        except BaseException as error:
            evidence.update(status='failed', error=f'{type(error).__name__}: {error}')
            raise
        finally:
            try:
                evidence['after'] = live.g.attest_tx_safe_idle(transport, plan, serial=live.ENDPOINT[0],
                    host=live.ENDPOINT[1], layout=deployment_profile.return_iio_layout)
            finally:
                save()
    print(json.dumps({'status':evidence['status'],'visits':len(evidence['visits']),
                      'output':str(args.output)}), flush=True)


if __name__ == '__main__':
    main()

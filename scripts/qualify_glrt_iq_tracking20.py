#!/usr/bin/env python3
"""One .20 calibrated ARM-local 1.049-second IQ/native-job qualification."""
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deployment', type=Path, required=True)
    parser.add_argument('--rate', type=int, choices=(30000000,60000000), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--coarse-benchmark', action='store_true',
                        help='benchmark four saved IQ windows on ARM after stopping RX')
    args = parser.parse_args()
    plan, profile = g.deployment_identity(args.deployment, serial=ENDPOINT[0], host=ENDPOINT[1])
    if plan['expected_firmware'] != f'glrt-iq-tracking-r{args.rate}-v1':
        raise ValueError('deployment rate differs')
    binary = (EVIDENCE/'glrt-iq-probe').read_bytes()
    checksum = hashlib.sha256(binary).hexdigest()
    args.output.mkdir(parents=True,exist_ok=False)
    authority = LocalCaptureAuthority(Path('/srv/bulk/leo/control'), (
        RadioResource('radio_pluto_5d4d',ENDPOINT[0],'ip:'+ENDPOINT[1]),))
    evidence = {'rate': args.rate, 'rf_samples': 16384*160, 'rf_seconds': 16384*160/2500000,
                'probe_sha256': checksum, 'tracking_lock_claimed': False, 'status': 'started'}
    remote = '/tmp/gli20-'+uuid.uuid4().hex
    ssh = ['sshpass','-f',str(PASSWORD),'ssh','-o','StrictHostKeyChecking=yes',
           '-o','UserKnownHostsFile='+str(EVIDENCE/'radio20.known_hosts'),
           '-o','ConnectTimeout=5','root@'+ENDPOINT[1]]

    def run(command, data=None, timeout=30):
        return subprocess.run([*ssh,command],input=data,capture_output=True,timeout=timeout)

    def save():
        (args.output/'operator.json').write_text(json.dumps(evidence,indent=2)+'\n')

    with authority.claim(('radio_pluto_5d4d',), task_id='gli20-'+args.output.name,
                         task_kind=CaptureTaskKind.QUALIFICATION), acquire_radio_lock(ENDPOINT[0]):
        transport = b.BoundSshBootstrapTransport(interface=None,host=ENDPOINT[1],
            password=PASSWORD.read_text().strip(),known_hosts_file=EVIDENCE/'radio20.known_hosts')
        staged=False
        try:
            evidence['before'] = g.attest_tx_safe_idle(transport,plan,serial=ENDPOINT[0],
                host=ENDPOINT[1],layout=profile.return_iio_layout)
            import iio
            context=iio.Context('ip:'+ENDPOINT[1])
            try:
                context.set_timeout(5000)
                if context.attrs['hw_serial']!=ENDPOINT[0] or context.attrs['fw_version']!=plan['expected_firmware']:
                    raise ValueError('configuration identity differs')
                evidence['configured'] = g.configure_checked_rx(context,lo=1690312496,
                    bandwidth=2500000,gain=30,port='A_BALANCED',source_rate=args.rate,
                    base_abi='GLI1-1.0-upper-only')
                evidence['calibration']={}
                save()
                g.calibrate_rx(context.find_device('ad9361-phy'),source_rate=args.rate,
                               evidence=evidence['calibration'])
            finally:
                _close_iio_context(iio,context)
                save()
            print(json.dumps({'phase':'calibrated','rate':args.rate,
                              'calibration':evidence['calibration']['status']}),flush=True)
            result=run('mkdir '+shlex.quote(remote))
            result.check_returncode();staged=True
            command = 'cat > '+shlex.quote(remote+'/probe')+' && chmod 700 '+shlex.quote(remote+'/probe')
            run(command,binary).check_returncode()
            result=run('sha256sum '+shlex.quote(remote+'/probe'))
            result.check_returncode()
            if result.stdout.decode().split()[0]!=checksum:
                raise ValueError('staged ARM binary differs')
            result=run(shlex.join([remote+'/probe',str(args.rate),ENDPOINT[0],
                                  remote+'/journal',remote+'/iq']),timeout=45)
            (args.output/'stdout.json').write_bytes(result.stdout)
            (args.output/'stderr.txt').write_bytes(result.stderr)
            evidence['probe_exit_code']=result.returncode
            for name in ('journal','iq'):
                pulled=run('cat '+shlex.quote(remote+'/'+name))
                pulled.check_returncode()
                (args.output/('iq.ci16' if name=='iq' else 'journal.txt')).write_bytes(pulled.stdout)
            result.check_returncode()
            if args.coarse_benchmark:
                for source,name in ((EVIDENCE/'glrt-coarse-bench','coarse-bench'),
                                    (EVIDENCE/'coarse-bank.ci16','coarse-bank')):
                    data=source.read_bytes()
                    run('cat > '+shlex.quote(remote+'/'+name),data).check_returncode()
                    check=run('sha256sum '+shlex.quote(remote+'/'+name));check.check_returncode()
                    expected=hashlib.sha256(data).hexdigest()
                    if check.stdout.decode().split()[0]!=expected:
                        raise ValueError('coarse benchmark payload differs')
                    evidence[name+'_sha256']=expected
                run('chmod 700 '+shlex.quote(remote+'/coarse-bench')).check_returncode()
                bench=run(shlex.join([remote+'/coarse-bench',remote+'/coarse-bank',
                                    remote+'/iq',remote+'/coarse-grid']),timeout=45)
                (args.output/'coarse-benchmark.json').write_bytes(bench.stdout)
                (args.output/'coarse-stderr.txt').write_bytes(bench.stderr)
                evidence['coarse_exit_code']=bench.returncode
                bench.check_returncode()
                grid=run('cat '+shlex.quote(remote+'/coarse-grid'));grid.check_returncode()
                (args.output/'coarse-grid.u32').write_bytes(grid.stdout)
            evidence['status']='capture_complete_review_pending'
        except BaseException as error:
            evidence.update(status='failed',error=f'{type(error).__name__}: {error}')
            raise
        finally:
            try:
                evidence['after'] = g.attest_tx_safe_idle(transport,plan,serial=ENDPOINT[0],
                    host=ENDPOINT[1],layout=profile.return_iio_layout)
                if staged:
                    # Only this invocation's explicitly owned RAM files may be removed.
                    names=('probe','journal','iq','coarse-bench','coarse-bank','coarse-grid')
                    command='rm -f '+shlex.join([remote+'/'+name for name in names])
                    run(command+' && rmdir '+shlex.quote(remote)).check_returncode()
            finally:
                save()
    print(json.dumps(evidence),flush=True)


if __name__=='__main__':
    main()

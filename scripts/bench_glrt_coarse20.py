#!/usr/bin/env python3
"""Benchmark a coarse scanner build on reviewed saved IQ; never start RX."""
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
from deploy_glrt_iq_tracking20 import EVIDENCE, PASSWORD


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deployment',type=Path,required=True)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--tracking-references',type=Path,
                        help='Run the saved-IQ scan/resolver/catch-up benchmark with frozen receiver time')
    args=parser.parse_args()
    receipt=json.loads((args.source/'independent-review.json').read_text())
    iq=(args.source/'iq.ci16').read_bytes()
    if receipt['status']!='pass' or hashlib.sha256(iq).hexdigest()!=receipt['sha256']['iq.ci16']:
        raise ValueError('saved IQ differs from reviewed physical source')
    payload={'bench':args.binary.read_bytes(),'iq':iq[:4*14000*4],
             'bank':(EVIDENCE/'coarse-bank.ci16').read_bytes()}
    if args.tracking_references:
        payload['iq']=iq
        payload['references']=args.tracking_references.read_bytes()
        if len(iq)!=2621440*4 or len(payload['references'])!=105600:
            raise ValueError('tracking benchmark requires the complete reviewed capture and four phase banks')
    plan,profile=g.deployment_identity(args.deployment,serial=ENDPOINT[0],host=ENDPOINT[1])
    args.output.mkdir(parents=True,exist_ok=False)
    evidence={'scope':'saved_iq_only','rf_samples':0,'source':str(args.source),
        'payload_sha256':{k:hashlib.sha256(v).hexdigest() for k,v in payload.items()}}
    authority=LocalCaptureAuthority(Path('/srv/bulk/leo/control'),(
        RadioResource('radio_pluto_5d4d',ENDPOINT[0],'ip:'+ENDPOINT[1]),))
    with authority.claim(('radio_pluto_5d4d',),task_id='gli20-'+args.output.name,
                         task_kind=CaptureTaskKind.QUALIFICATION),acquire_radio_lock(ENDPOINT[0]):
        transport=b.BoundSshBootstrapTransport(interface=None,host=ENDPOINT[1],
            password=PASSWORD.read_text().strip(),known_hosts_file=EVIDENCE/'radio20.known_hosts')
        remote='/tmp/gli20-'+uuid.uuid4().hex
        ssh=['sshpass','-f',str(PASSWORD),'ssh','-o','StrictHostKeyChecking=yes',
             '-o','UserKnownHostsFile='+str(EVIDENCE/'radio20.known_hosts'),
             '-o','ConnectTimeout=5','root@'+ENDPOINT[1]]
        def run(command,data=None):
            return subprocess.run([*ssh,command],input=data,capture_output=True,timeout=45)
        staged=False
        try:
            evidence['before']=g.attest_tx_safe_idle(transport,plan,serial=ENDPOINT[0],
                host=ENDPOINT[1],layout=profile.return_iio_layout)
            run('mkdir '+shlex.quote(remote)).check_returncode();staged=True
            for key,data in payload.items():
                run('cat > '+shlex.quote(remote+'/'+key),data).check_returncode()
                check=run('sha256sum '+shlex.quote(remote+'/'+key));check.check_returncode()
                if check.stdout.decode().split()[0]!=evidence['payload_sha256'][key]:
                    raise ValueError('staged payload differs')
            run('chmod 700 '+shlex.quote(remote+'/bench')).check_returncode()
            command=['bench','bank','iq','grid']
            if args.tracking_references: command.append('references')
            result=run(shlex.join([remote+'/'+x for x in command]))
            (args.output/('tracking-benchmark.jsonl' if args.tracking_references else 'coarse-benchmark.json')).write_bytes(result.stdout)
            (args.output/'stderr.txt').write_bytes(result.stderr)
            evidence['exit_code']=result.returncode
            result.check_returncode()
            grid=run('cat '+shlex.quote(remote+'/grid'));grid.check_returncode()
            (args.output/'coarse-grid.u32').write_bytes(grid.stdout)
            print(result.stdout.decode(),flush=True)
        finally:
            try:
                if staged:
                    run('rm -f '+shlex.join([remote+'/'+x for x in (*payload,'grid')])+
                        ' && rmdir '+shlex.quote(remote)).check_returncode()
                evidence['after']=g.attest_tx_safe_idle(transport,plan,serial=ENDPOINT[0],
                    host=ENDPOINT[1],layout=profile.return_iio_layout)
            finally:
                (args.output/'operator.json').write_text(json.dumps(evidence,indent=2)+'\n')


if __name__=='__main__':
    main()

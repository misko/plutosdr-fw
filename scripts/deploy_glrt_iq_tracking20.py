#!/usr/bin/env python3
"""Dispatch one exact .20 GLI1 transition under the production capture lease.

No capture is started. The caller selects a frozen PPU transition; a failure
after updater dispatch is reported for reconciliation, never automatically retried.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path

from leo.acquisition.authority import LocalCaptureAuthority, RadioResource, CaptureTaskKind
from pluto_plus import bootstrap_firmware as b
from pluto_plus import glrt_iq_tracking_profiles as profiles

EVIDENCE = Path('/srv/bulk/leo/glrt-deployment-20260909/radio20-iq-tracking-20260912')
PASSWORD = Path('/home/mouse9911/gits/plutosdr-fw-glrt-deployment-review/artifacts/'
                'device-tool-glrt-ethernet/artifacts/native-lnb-20-20260910/ssh-password')
OLD_HOSTS = Path('/srv/bulk/leo/qualification/deployment/radio20-v049-network-20260911/'
                 'radio20.known_hosts')
ROLLBACK = Path('/srv/bulk/leo-dev/scanner-glrt-comparison-pngs/.leo/firmware-restore/'
                'plutoplus-spf-iq-direct-async-v4-bc00edb8c340-pluto.dfu')


def verify_inputs(profile):
    for rate, (size, fit, dfu) in profiles.IMAGES.items():
        package = EVIDENCE / f'ram-{rate}-v1'
        receipt = json.loads((EVIDENCE / f'verify-{rate}-v1/receipt.json').read_text())
        if receipt['status'] != 'pass':
            raise ValueError('independent package verification failed')
        for name, expected in (('pluto.itb', fit), ('pluto.dfu', dfu)):
            data = (package / name).read_bytes()
            if (hashlib.sha256(data).hexdigest() != expected
                    or receipt['outputs_sha256'][name] != expected):
                raise ValueError('package differs from frozen profile/extraction')
        if (package / 'pluto.itb').stat().st_size != size:
            raise ValueError('FIT size differs')
    baseline = b.IQ_DIRECT_ASYNC_V4_RELEASE_PERSISTENT_POLICY
    data = ROLLBACK.read_bytes()
    fit = b.validate_frm(b.generate_frm(data))
    if (hashlib.sha256(data).hexdigest() != baseline.asset_sha256
            or hashlib.sha256(fit).hexdigest() != baseline.fit_body_sha256
            or len(fit) != baseline.fit_body_size):
        raise ValueError('rollback image differs from pinned production image')
    if profile.ethernet_only_canary_endpoint != profiles.ENDPOINT:
        raise ValueError('profile is not bound to .20')
    label = profile.policy.device_firmware
    return ROLLBACK if label == baseline.device_firmware else (
        EVIDENCE / f'ram-{label.split("-r")[1].split("-")[0]}-v1/pluto.dfu')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', choices=tuple(profiles.frozen_profiles()))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    profile = b.STANDALONE_FLASH_PROFILES[args.profile]
    image = verify_inputs(profile)
    if args.check:
        print(json.dumps({'status': 'local_inputs_verified', 'image': str(image)}))
        return
    os.umask(0o077)
    args.output.mkdir(parents=True, exist_ok=False)
    authority = LocalCaptureAuthority(Path('/srv/bulk/leo/control'), (
        RadioResource('radio_pluto_5d4d', profiles.ENDPOINT[0], 'ip:'+profiles.ENDPOINT[1]),))
    with authority.claim(('radio_pluto_5d4d',), task_id='gli20-'+args.output.name,
                         task_kind=CaptureTaskKind.QUALIFICATION):
        hosts = EVIDENCE / 'radio20.known_hosts'
        if not hosts.exists():
            with hosts.open('xb') as stream:
                stream.write(OLD_HOSTS.read_bytes())
        password = PASSWORD.read_text().strip()
        transport = b.BoundSshBootstrapTransport(interface=None, host=profiles.ENDPOINT[1],
            password=password, known_hosts_file=hosts)
        plan, frm = b.prepare_lan_flash_plan(image, serial=profiles.ENDPOINT[0],
            host=profiles.ENDPOINT[1], mutation_profile_id=args.profile)
        (args.output/'plan.json').write_text(json.dumps(asdict(plan), indent=2)+'\n')
        print(json.dumps({'phase': 'dispatch', 'profile': args.profile,
                          'fit_sha256': plan.fit_sha256}), flush=True)

        def rotate():
            return b.rotate_lan_ssh_host_key_after_attested_return(
                serial=profiles.ENDPOINT[0], host=profiles.ENDPOINT[1],
                expected_firmware=plan.expected_firmware,
                expected_metadata_abi=plan.expected_metadata_abi,
                password=password, known_hosts_file=hosts)

        result = b.execute_lan_flash_plan(plan, frm, confirmation=plan.confirmation_phrase,
            receipt_directory=args.output/'receipts', transport=transport,
            host_key_rotator=rotate, return_timeout_s=180)
        (args.output/'result.json').write_text(json.dumps(asdict(result), indent=2)+'\n')
        print(json.dumps(asdict(result), indent=2), flush=True)
        if result.outcome != 'success':
            raise SystemExit(1)


if __name__ == '__main__':
    main()

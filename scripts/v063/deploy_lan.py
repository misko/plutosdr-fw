"""Install the exact RX-qualified v0.63 image through the guarded LAN firmware updater."""
import argparse
import dataclasses
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('host', 'serial'):
        parser.add_argument('--' + key, required=True)
    for key in ('image-dir', 'evidence', 'qualification-root', 'known-hosts', 'password-file'):
        parser.add_argument('--' + key, required=True, type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    from pluto_plus.hardware.preflight import verify_metadata_runtime
    verify_metadata_runtime(3)
    from pluto_plus import bootstrap_firmware as ppu
    from pluto_plus.doctor import FEATURE_103_V1_RELEASE_RAM_POLICY
    from pluto_plus.radio_lock import acquire_radio_lock
    from pluto_plus.release_candidate_lifecycle import validate_password_file

    binding = json.loads((args.image_dir / 'artifact.json').read_text())
    root = args.qualification_root
    plan = json.loads((root / 'ram-final-radio15/plan.json').read_text())
    result = json.loads((root / 'ram-final-radio15/result.json').read_text())
    assert plan['image_sha256'] == binding['dfu_sha256']
    assert result['outcome'] == 'success'
    evidence = []
    for name, rates, minimum in (
        ('qualification-radio15', {1250000,2500000,5000000,7500000,10000000}, 80),
        ('soak-radio15', {5000000,10000000}, 512),
    ):
        path = root / name / 'summary.json'
        reports = json.loads(path.read_text())
        assert {r['rate_hz'] for r in reports} == rates
        assert all(r['passed'] and r['windows'] >= minimum for r in reports)
        evidence.append(path)
    legacy = root / 'legacy-radio15/v063-legacy-v3-lan/report.json'
    report = json.loads(legacy.read_text())
    assert report['dfu_sha256'] == binding['dfu_sha256']
    assert report['settings_restored'] and report['ordinary_capture_after']['bytes'] == 32768
    evidence.append(legacy)
    image = args.image_dir / 'plutoplus-spf-continuous-fast-scan-v063-pluto.dfu'
    assert hashlib.sha256(image.read_bytes()).hexdigest() == binding['dfu_sha256']
    validate_password_file(args.password_file)
    password = args.password_file.read_text().rstrip('\n')
    base = ppu.STANDALONE_FLASH_PROFILES[FEATURE_103_V1_RELEASE_RAM_POLICY.profile_id]
    profile_id = 'continuous-v063-qualified-' + binding['dfu_sha256'][:12]
    policy = base.policy.model_copy(update={
        'profile_id': profile_id, 'release_tag': binding['firmware'],
        'device_firmware': binding['firmware'], 'asset_name': image.name,
        'asset_sha256': binding['dfu_sha256'], 'fit_body_sha256': binding['fit_sha256'],
        'fit_body_size': binding['fit_bytes'], 'source_commit': binding['libiio_source'],
        'release_url': 'https://github.com/misko/plutosdr-fw/tree/codex/continuous-scan-multirate-v063',
        'hardware_qualified': True, 'published_at': datetime.now(UTC),
    })
    ppu.STANDALONE_FLASH_PROFILES[profile_id] = dataclasses.replace(
        base, policy=policy, persistent_allowed=True, metadata_abi=3,
        source_iio_layout=ppu.PAIRED_RX_TX_CAPABLE_LAYOUT,
        return_iio_layout=ppu.PAIRED_RX_TX_CAPABLE_LAYOUT,
        allowed_before_firmwares=('v0.59-issue119-fastlock-rc2',
            'v0.60-plutoplus-spf-adaptive-native-fastlock',
            'v0.62-plutoplus-spf-continuous-fast-scan'),
    )
    args.evidence.mkdir(parents=True, exist_ok=False, mode=0o700)
    def save(name, value):
        (args.evidence / name).write_text(json.dumps(value,indent=2,default=str)+'\n')
    transport = ppu.BoundSshBootstrapTransport(interface=None, host=args.host,
        password=password, known_hosts_file=args.known_hosts)
    with acquire_radio_lock(args.serial):
        plan, frm = ppu.prepare_lan_flash_plan(image, serial=args.serial, host=args.host,
            mutation_profile_id=profile_id, flash_transport=transport)
        save('plan.json', dataclasses.asdict(plan))
        save('qualification-binding.json', {'dfu_sha256':binding['dfu_sha256'],
            'evidence':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in evidence]})
        if not args.execute:
            print(json.dumps(dataclasses.asdict(plan)),flush=True)
            return
        def rotate():
            return ppu.rotate_lan_ssh_host_key_after_attested_return(serial=args.serial,
                host=args.host, expected_firmware=binding['firmware'], expected_metadata_abi=3,
                password=password, known_hosts_file=args.known_hosts)
        result = ppu.execute_lan_flash_plan(plan, frm, confirmation=plan.confirmation_phrase,
            receipt_directory=args.evidence / 'receipts', transport=transport, host_key_rotator=rotate)
        save('result.json', dataclasses.asdict(result))
        print(json.dumps(dataclasses.asdict(result)),flush=True)
        if result.outcome != 'success':
            raise RuntimeError('Inspect deployment receipt; do not retry automatically')


if __name__ == '__main__':
    main()

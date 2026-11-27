"""Install the exact RAM-qualified v0.64 image through the guarded LAN updater."""
import argparse
import dataclasses
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def qualification_evidence(root, binding, serial):
    plan = json.loads((root / 'ram-radio15/plan.json').read_text())
    result = json.loads((root / 'ram-radio15/result.json').read_text())
    require(plan['image_sha256'] == binding['dfu_sha256'], 'RAM image binding mismatch')
    require(result['outcome'] == 'success', 'RAM boot did not succeed')
    path = root / 'qualification.json'
    qualification = json.loads(path.read_text())
    require(qualification['schema'] == 'plutosdr-fw.position-scan-qualification/v1', 'qualification schema mismatch')
    require(qualification['dfu_sha256'] == binding['dfu_sha256'], 'qualified image mismatch')
    require(qualification['serial'] == serial == plan['serial'], 'qualified radio mismatch')
    require(qualification['passed'] is True and qualification['complete_visits'] >= 576,
            'incomplete qualification')
    for check in ('saved_iq_verified', 'tuning_signatures_verified', 'slot_reuse_verified',
                  'stop_restored', 'interruption_restored', 'legacy_v5_passed', 'ordinary_rx_passed'):
        require(qualification[check] is True, 'qualification failed: ' + check)
    require(bool(qualification['evidence']), 'qualification evidence is empty')
    evidence = [path]
    for row in qualification['evidence']:
        item = (root / row['path']).resolve()
        require(item.is_relative_to(root.resolve()), 'evidence outside qualification root')
        require(hashlib.sha256(item.read_bytes()).hexdigest() == row['sha256'], 'evidence hash mismatch')
        evidence.append(item)
    return evidence


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
    evidence = qualification_evidence(root, binding, args.serial)
    image = args.image_dir / 'plutoplus-spf-position-scan-v064-pluto.dfu'
    require(hashlib.sha256(image.read_bytes()).hexdigest() == binding['dfu_sha256'], 'image hash mismatch')
    validate_password_file(args.password_file)
    password = args.password_file.read_text().rstrip('\n')
    base = ppu.STANDALONE_FLASH_PROFILES[FEATURE_103_V1_RELEASE_RAM_POLICY.profile_id]
    profile_id = 'position-v064-qualified-' + binding['dfu_sha256'][:12]
    policy = base.policy.model_copy(update={
        'profile_id': profile_id, 'release_tag': binding['firmware'],
        'device_firmware': binding['firmware'], 'asset_name': image.name,
        'asset_sha256': binding['dfu_sha256'], 'fit_body_sha256': binding['fit_sha256'],
        'fit_body_size': binding['fit_bytes'], 'source_commit': binding['libiio_source'],
        'release_url': 'https://github.com/misko/plutosdr-fw/tree/codex/position-scan-v064',
        'hardware_qualified': True, 'published_at': datetime.now(UTC),
    })
    ppu.STANDALONE_FLASH_PROFILES[profile_id] = dataclasses.replace(
        base, policy=policy, persistent_allowed=True, metadata_abi=3,
        source_iio_layout=ppu.PAIRED_RX_TX_CAPABLE_LAYOUT,
        return_iio_layout=ppu.PAIRED_RX_TX_CAPABLE_LAYOUT,
        allowed_before_firmwares=('v0.63-plutoplus-spf-continuous-fast-scan',),
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

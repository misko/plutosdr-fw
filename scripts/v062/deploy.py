"""RAM-only exact-image qualification using PPU's legacy-compatible guarded path.

Retains the supported set-attribute AD9361/2R2T boot tuple. This does not claim
a candidate-ram canonical-clear-attribute receipt and never changes U-Boot setup.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


def save(path, value):
    path.write_text(json.dumps(value, indent=2, default=str) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-dir", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--known-hosts", type=Path, required=True)
    parser.add_argument("--password-file", type=Path, required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--before", required=True)
    parser.add_argument("--usb-path", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    from pluto_plus.hardware.preflight import verify_metadata_runtime
    verify_metadata_runtime(3)
    from pluto_plus import bootstrap_firmware as ppu
    from pluto_plus.doctor import FEATURE_103_V1_RELEASE_RAM_POLICY
    from pluto_plus.radio_lock import acquire_radio_lock
    from pluto_plus.release_candidate_lifecycle import validate_password_file
    from pluto_plus.volatile_firmware import SshRamBootTransition, execute_ram_boot_plan, prepare_ram_boot_plan

    validate_password_file(args.password_file)
    password = args.password_file.read_text().rstrip("\n")
    binding = json.loads((args.image_dir / "artifact.json").read_text())
    image = args.image_dir / "plutoplus-spf-continuous-fast-scan-v062-pluto.dfu"
    if hashlib.sha256(image.read_bytes()).hexdigest() != binding["dfu_sha256"]:
        raise ValueError("image differs from artifact binding")
    args.evidence.mkdir(parents=True, exist_ok=False, mode=0o700)
    base = ppu.STANDALONE_FLASH_PROFILES[FEATURE_103_V1_RELEASE_RAM_POLICY.profile_id]
    profile_id = "continuous-v062-" + binding["dfu_sha256"][:12]
    policy = base.policy.model_copy(update={
        "profile_id": profile_id, "release_tag": binding["firmware"],
        "device_firmware": binding["firmware"], "asset_name": image.name,
        "asset_sha256": binding["dfu_sha256"], "fit_body_sha256": binding["fit_sha256"],
        "fit_body_size": binding["fit_bytes"], "source_commit": binding["libiio_source"],
        "release_url": "https://github.com/misko/plutosdr-fw/pull/125",
        "hardware_qualified": False, "published_at": datetime.now(UTC),
    })
    ppu.STANDALONE_FLASH_PROFILES[profile_id] = dataclasses.replace(
        base, policy=policy, persistent_allowed=False, metadata_abi=3,
        source_iio_layout=ppu.PAIRED_RX_TX_CAPABLE_LAYOUT,
        return_iio_layout=ppu.PAIRED_RX_TX_CAPABLE_LAYOUT,
        allowed_before_firmwares=(args.before,),
    )
    transport = ppu.BoundSshBootstrapTransport(interface=None, host=args.host,
        password=password, known_hosts_file=args.known_hosts)
    identity_command = (
        "cat /sys/kernel/config/usb_gadget/composite_gadget/strings/0x409/serialnumber; "
        "cat /opt/VERSIONS; cat /proc/sys/kernel/random/boot_id; "
        "sha256sum /dev/mtdblock3; fw_printenv attr_name attr_val compatible mode 2>/dev/null"
    )
    before = transport.run(identity_command)
    if args.serial not in before.splitlines() or "device-fw " + args.before not in before.splitlines():
        raise ValueError("serial or firmware mismatch")
    (args.evidence / "before.txt").write_text(before)
    with acquire_radio_lock(args.serial):
        plan = prepare_ram_boot_plan(image, args.usb_path, profile_id=profile_id,
            transition_host=args.host, known_hosts_file=args.known_hosts)
        if plan.serial != args.serial:
            raise ValueError("USB path belongs to another radio")
        save(args.evidence / "plan.json", dataclasses.asdict(plan))
        if not args.execute:
            print(json.dumps(dataclasses.asdict(plan), default=str))
            return
        result = execute_ram_boot_plan(plan, confirmation=plan.confirmation_phrase,
            known_hosts_file=args.known_hosts, transition=SshRamBootTransition(transport),
            receipt_directory=args.evidence / "receipts", timeout_s=90)
        save(args.evidence / "result.json", dataclasses.asdict(result))
        print(json.dumps(dataclasses.asdict(result), default=str), flush=True)
        if result.outcome != "success":
            raise RuntimeError("RAM boot needs inspection; no automatic retry")
        # DHCP/LAN may change across boot. Re-enroll only the returned physical
        # USB target into a new task-local pin; preserve the old LAN pin.
        returned_pin = args.evidence / "returned-usb.known_hosts"
        enrollment = ppu.enroll_bound_usb_ssh_host_key(serial=args.serial,
            usb_sysfs_path=args.usb_path, known_hosts_file=returned_pin,
            password=password)
        save(args.evidence / "returned-ssh.json", enrollment)
        returned = ppu.BoundSshBootstrapTransport(interface=enrollment["usb_interface"],
            host="192.168.2.1", password=password, known_hosts_file=returned_pin)
        after = returned.run(identity_command)
        (args.evidence / "after.txt").write_text(after)
        old_qspi = next(x for x in before.splitlines() if x.endswith("  /dev/mtdblock3"))
        if old_qspi not in after.splitlines():
            raise RuntimeError("QSPI changed during RAM qualification")
        if args.serial not in after.splitlines() or "device-fw " + binding["firmware"] not in after.splitlines():
            raise RuntimeError("returned SSH identity differs from qualified image")


if __name__ == "__main__":
    main()

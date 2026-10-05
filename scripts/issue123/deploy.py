"""Serial and digest bound deployment through the existing guarded PPU lifecycle."""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pluto_plus import bootstrap_firmware as ppu
from pluto_plus.doctor import FEATURE_103_V1_RELEASE_RAM_POLICY
from pluto_plus.radio_lock import acquire_radio_lock
from pluto_plus.volatile_firmware import (
    SshRamBootTransition, execute_ram_boot_plan, prepare_ram_boot_plan,
)


def save(path, value):
    path.write_text(json.dumps(dataclasses.asdict(value), indent=2, default=str) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-dir", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--known-hosts", type=Path, required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--before", required=True)
    parser.add_argument("--mode", choices=("ram", "lan"), required=True)
    parser.add_argument("--usb-path", type=Path)
    parser.add_argument("--qualification", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    binding = json.loads((args.image_dir / "artifact.json").read_text())
    image = args.image_dir / "issue123.dfu"
    if hashlib.sha256(image.read_bytes()).hexdigest() != binding["dfu_sha256"]:
        raise ValueError("image differs from its artifact binding")
    args.evidence.mkdir(parents=True, exist_ok=True)
    qualified = False
    if args.qualification:
        report = json.loads(args.qualification.read_text())
        qualified = (
            report["dfu_sha256"] == binding["dfu_sha256"]
            and report["boot_identity_verified"]
            and report["settings_restored"]
            and report["ordinary_capture_after"]["bytes"] == 32768
        )
        if not qualified:
            raise ValueError("qualification is not bound to this exact candidate")
    if args.mode == "lan" and not qualified:
        raise ValueError("LAN installation requires exact-image canary qualification")
    base = ppu.STANDALONE_FLASH_PROFILES[FEATURE_103_V1_RELEASE_RAM_POLICY.profile_id]
    profile_id = "issue123-" + binding["dfu_sha256"][:12]
    policy = base.policy.model_copy(update={
        "profile_id": profile_id,
        "release_tag": binding["firmware"], "device_firmware": binding["firmware"],
        "asset_name": image.name, "asset_sha256": binding["dfu_sha256"],
        "fit_body_sha256": binding["fit_sha256"], "fit_body_size": binding["fit_bytes"],
        "source_commit": binding["linux_source"],
        "release_url": "https://github.com/misko/plutosdr-fw/issues/123",
        "hardware_qualified": qualified, "published_at": datetime.now(UTC),
    })
    ppu.STANDALONE_FLASH_PROFILES[profile_id] = dataclasses.replace(
        base, policy=policy, persistent_allowed=qualified,
        source_iio_layout=ppu.PAIRED_RX_TX_CAPABLE_LAYOUT,
        return_iio_layout=ppu.PAIRED_RX_TX_CAPABLE_LAYOUT,
        allowed_before_firmwares=(args.before,),
    )
    transport = ppu.BoundSshBootstrapTransport(
        interface=None, host=args.host, password="analog", known_hosts_file=args.known_hosts)
    before = transport.run(
        "cat /sys/kernel/config/usb_gadget/composite_gadget/strings/0x409/serialnumber; "
        "head -n 1 /opt/VERSIONS; cat /proc/sys/kernel/random/boot_id")
    if args.serial not in before.splitlines() or "device-fw " + args.before not in before.splitlines():
        raise ValueError("serial or current firmware changed")
    (args.evidence / "before.txt").write_text(before)
    with acquire_radio_lock(args.serial):
        if args.mode == "ram":
            if args.usb_path is None:
                raise ValueError("RAM boot requires an exact USB topology path")
            plan = prepare_ram_boot_plan(image, args.usb_path, profile_id=profile_id,
                transition_host=args.host, known_hosts_file=args.known_hosts)
            if plan.serial != args.serial:
                raise ValueError("USB path belongs to another radio")
            save(args.evidence / "plan.json", plan)
            if not args.execute:
                print(json.dumps(dataclasses.asdict(plan), default=str)); return
            result = execute_ram_boot_plan(plan, confirmation=plan.confirmation_phrase,
                known_hosts_file=args.known_hosts, transition=SshRamBootTransition(transport),
                receipt_directory=args.evidence / "receipts", timeout_s=90)
        else:
            plan, frm = ppu.prepare_lan_flash_plan(image, serial=args.serial,
                host=args.host, mutation_profile_id=profile_id, flash_transport=transport)
            save(args.evidence / "plan.json", plan)
            if not args.execute:
                print(json.dumps(dataclasses.asdict(plan), default=str)); return
            def rotate():
                return ppu.rotate_lan_ssh_host_key_after_attested_return(
                    serial=args.serial, host=args.host, expected_firmware=binding["firmware"],
                    expected_metadata_abi=3, password="analog", known_hosts_file=args.known_hosts)
            result = ppu.execute_lan_flash_plan(plan, frm, confirmation=plan.confirmation_phrase,
                receipt_directory=args.evidence / "receipts", transport=transport,
                host_key_rotator=rotate)
        save(args.evidence / "result.json", result)
        print(json.dumps(dataclasses.asdict(result), default=str))
        if result.outcome != "success":
            raise RuntimeError("deployment needs inspection; no automatic retry")
        if args.mode == "ram":
            ppu.rotate_lan_ssh_host_key_after_attested_return(
                serial=args.serial, host=args.host, expected_firmware=binding["firmware"],
                expected_metadata_abi=3, password="analog", known_hosts_file=args.known_hosts)


if __name__ == "__main__":
    main()

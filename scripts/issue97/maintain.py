#!/usr/bin/env python3
"""Receipted mode changes for the one authorized issue-97 radio."""

import argparse
import dataclasses
import json
import os
import re
from pathlib import Path

from pluto_plus.bootstrap_firmware import (
    BoundSshBootstrapTransport,
    rotate_lan_ssh_host_key_after_attested_return,
)
from pluto_plus.doctor import setup_repair_policy_for_firmware
from pluto_plus.hardware.discovery import discover_network_iio
from pluto_plus.inventory import scan_local_usb_plutos
from pluto_plus.radio_lock import acquire_radio_lock
from pluto_plus.setup import CanonicalSetupManager, SetupExecutionError, SetupIdentity
from pluto_plus.setup_helper import FixedSshSetupExecutor
from pluto_plus.setup_profiles import SetupTarget

SERIAL = "1040007c4a94000211000b009186843ef2"
HOST = "192.168.1.18"
ROOT = Path(__file__).resolve().parents[2] / "evidence"
KEY = ROOT / "known_hosts"


def password():
    path = os.environ.get("PLUTO_PASSWORD_FILE")
    if path:
        return Path(path).read_text().rstrip("\n")
    config = Path(os.environ["PLUTO_BUILDROOT_CONFIG"]).read_text()
    return re.search(
        r'^BR2_TARGET_GENERIC_ROOT_PASSWD="([^"\n]+)"$', config, re.MULTILINE
    ).group(1)


def attest():
    devices = [d for d in scan_local_usb_plutos() if d.serial == SERIAL]
    assert len(devices) == 1
    observed = discover_network_iio([HOST + "/32"], max_hosts=1, workers=1)
    assert len(observed) == 1 and observed[0].serial == SERIAL
    return devices[0], observed[0]


def link():
    return BoundSshBootstrapTransport(
        host=HOST, interface=None, password=password(), known_hosts_file=KEY
    )


def rotate():
    _, observed = attest()
    return rotate_lan_ssh_host_key_after_attested_return(
        serial=SERIAL,
        host=HOST,
        expected_firmware=observed.firmware_version,
        expected_metadata_abi=3,
        password=password(),
        known_hosts_file=KEY,
        timeout_s=20,
    )


def manager():
    usb, observed = attest()
    identity = SetupIdentity(
        serial=SERIAL,
        usb_sysfs_path=usb.usb_path,
        observed_firmware=observed.firmware_version,
    )
    policy = setup_repair_policy_for_firmware(observed.firmware_version)
    executor = FixedSshSetupExecutor(
        identity=identity,
        transport=link(),
        state_root=ROOT,
        policy=policy,
        reenumeration_timeout_s=45,
    )
    return identity, CanonicalSetupManager(
        receipt_directory=ROOT / "setup-receipts",
        inspector=executor.inspect,
        executor=executor,
        policy=policy,
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["inspect", "1r1t", "2r2t", "rotate", "reconcile"])
    p.add_argument("--receipt")
    args = p.parse_args()
    with acquire_radio_lock(SERIAL):
        if args.action == "rotate":
            print(json.dumps(rotate(), default=str))
            return
        identity, setup = manager()
        if args.action == "inspect":
            result = setup.inspect_qualified(identity).model_dump(mode="json")
        elif args.action == "reconcile":
            result = dataclasses.asdict(setup.reconcile(args.receipt))
        else:
            target = (
                SetupTarget.AD9361_1R1T
                if args.action == "1r1t"
                else SetupTarget.AD9361_2R2T
            )
            planned = setup.create_plan(identity, target=target)
            document = dataclasses.asdict(planned.plan)
            (ROOT / f"setup-{args.action}-plan.json").write_text(
                json.dumps(document, default=str, indent=2)
            )
            try:
                receipt = setup.execute(planned.plan, planned.confirmation_token)
            except SetupExecutionError as error:
                receipt = error.receipt
            result = dataclasses.asdict(receipt)
        (ROOT / f"setup-{args.action}-result.json").write_text(
            json.dumps(result, default=str, indent=2)
        )
        print(json.dumps(result, default=str, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Exact-byte RAM qualification of issue 97 on the sole authorized serial."""

import argparse
import json
from dataclasses import asdict, replace
from pathlib import Path

from maintain import HOST, KEY, ROOT, SERIAL, attest, link
from pluto_plus.bootstrap_firmware import (
    SINGLE_RX_TX_CAPABLE_LAYOUT,
    STANDALONE_FLASH_PROFILES,
)
from pluto_plus.doctor import IQ_DIRECT_ASYNC_V4_CANDIDATE_RAM_POLICY
from pluto_plus.radio_lock import acquire_radio_lock
from pluto_plus.volatile_firmware import (
    SshRamBootTransition,
    execute_ram_boot_plan,
    prepare_ram_boot_plan,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--single-rx", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((ROOT.parent / "build/counter-rx-v1.json").read_text())
    assert manifest["serial"] == SERIAL
    policy = IQ_DIRECT_ASYNC_V4_CANDIDATE_RAM_POLICY.model_copy(
        update={
            "profile_id": "issue-97-counter-rx-v1-release-ram",
            "release_tag": "v0.50-plutoplus-spf-counter-rx-v1",
            "device_firmware": manifest["firmware"],
            "asset_name": Path(manifest["asset_path"]).name,
            "asset_sha256": manifest["asset_sha256"],
            "fit_body_sha256": manifest["fit_sha256"],
            "fit_body_size": manifest["fit_size"],
            "source_commit": manifest["sources"]["firmware_base"],
            "release_url": "https://github.com/misko/plutosdr-fw/issues/97",
        }
    )
    STANDALONE_FLASH_PROFILES[policy.profile_id] = replace(
        STANDALONE_FLASH_PROFILES[IQ_DIRECT_ASYNC_V4_CANDIDATE_RAM_POLICY.profile_id],
        policy=policy,
    )
    if args.single_rx:
        STANDALONE_FLASH_PROFILES[policy.profile_id] = replace(
            STANDALONE_FLASH_PROFILES[policy.profile_id],
            source_iio_layout=SINGLE_RX_TX_CAPABLE_LAYOUT,
            return_iio_layout=SINGLE_RX_TX_CAPABLE_LAYOUT,
        )
    with acquire_radio_lock(SERIAL):
        usb, _ = attest()
        plan = prepare_ram_boot_plan(
            Path(manifest["asset_path"]),
            Path(usb.usb_path),
            profile_id=policy.profile_id,
            transition_host=HOST,
            known_hosts_file=KEY,
        )
        assert plan.serial == SERIAL
        (ROOT / "candidate-ram-plan.json").write_text(
            json.dumps(asdict(plan), indent=2)
        )
        print(json.dumps(asdict(plan), indent=2), flush=True)
        if args.execute:
            result = execute_ram_boot_plan(
                plan,
                confirmation=plan.confirmation_phrase,
                known_hosts_file=KEY,
                transition=SshRamBootTransition(link()),
                receipt_directory=ROOT / "ram-receipts",
                timeout_s=60,
            )
            (ROOT / "candidate-ram-result.json").write_text(
                json.dumps(asdict(result), indent=2)
            )
            print(json.dumps(asdict(result), indent=2), flush=True)
            if result.outcome != "success":
                raise SystemExit(1)


if __name__ == "__main__":
    main()

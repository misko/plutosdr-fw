#!/usr/bin/env python3
"""Promote only the locally qualified candidate through the fixed FRM updater."""

import json
from dataclasses import asdict, replace
from pathlib import Path

from maintain import HOST, ROOT, SERIAL, attest, link, rotate
from pluto_plus.bootstrap_firmware import (
    SINGLE_RX_TX_CAPABLE_LAYOUT,
    STANDALONE_FLASH_PROFILES,
    execute_lan_flash_plan,
    prepare_lan_flash_plan,
)
from pluto_plus.doctor import IQ_DIRECT_ASYNC_V4_CANDIDATE_RAM_POLICY
from pluto_plus.radio_lock import acquire_radio_lock


def main():
    manifest = json.loads((ROOT.parent / "build/counter-rx-v1-rc1.json").read_text())
    assert manifest["serial"] == SERIAL
    for name in (
        "candidate-1r1t-low-lan",
        "candidate-1r1t-high",
        "candidate-1r1t-loss",
        "paired-0-hold",
        "paired-0-auto",
        "paired-1-hold",
        "paired-1-auto",
        "paired-01-hold",
        "paired-01-auto",
    ):
        result = json.loads((ROOT / (name + ".json")).read_text())
        assert result["serial"] == SERIAL and result["firmware"] == manifest["firmware"]
        assert (
            result["restored"] and result["restored_gain"] and result["restored_queue"]
        )
        assert all(c["outcome"] == "completed" and c["frames"] for c in result["cells"])
    lifecycle = json.loads((ROOT / "lifecycle.json").read_text())
    assert (
        lifecycle["iiod_death_releases_and_recaptures"]
        and lifecycle["timestamp_restored"]
    )
    ram = json.loads((ROOT / "candidate-ram-result.json").read_text())
    assert ram["outcome"] == "success" and ram["returned_serial"] == SERIAL
    ram_receipt = json.loads(Path(ram["receipt_path"]).read_text())
    assert ram_receipt["plan"]["image_sha256"] == manifest["asset_sha256"]
    assert ram_receipt["plan"]["fit_sha256"] == manifest["fit_sha256"]
    policy = IQ_DIRECT_ASYNC_V4_CANDIDATE_RAM_POLICY.model_copy(
        update={
            "profile_id": "issue-97-counter-rx-v1-rc1-local-persistent",
            "release_tag": "counter-rx-v1-rc1-local",
            "device_firmware": manifest["firmware"],
            "asset_name": Path(manifest["asset_path"]).name,
            "asset_sha256": manifest["asset_sha256"],
            "fit_body_sha256": manifest["fit_sha256"],
            "fit_body_size": manifest["fit_size"],
            "source_commit": manifest["sources"]["firmware_base"],
            "release_url": "https://github.com/misko/plutosdr-fw/issues/97",
            "hardware_qualified": True,
        }
    )
    profile = replace(
        STANDALONE_FLASH_PROFILES[IQ_DIRECT_ASYNC_V4_CANDIDATE_RAM_POLICY.profile_id],
        policy=policy,
        persistent_allowed=True,
        source_iio_layout=SINGLE_RX_TX_CAPABLE_LAYOUT,
        return_iio_layout=SINGLE_RX_TX_CAPABLE_LAYOUT,
        allowed_before_firmwares=("v0.49-plutoplus-spf-iq-direct-async-v4",),
        required_iio_capabilities=(
            ("iio,buffer-counter-metadata", "1"),
            ("iio,buffer-counter-metadata-topology-supported", "1"),
            ("iio,buffer-direct-async-exact-kernel-queue", "1"),
        ),
    )
    STANDALONE_FLASH_PROFILES[policy.profile_id] = profile
    with acquire_radio_lock(SERIAL):
        attest()
        plan, frm = prepare_lan_flash_plan(
            Path(manifest["asset_path"]),
            serial=SERIAL,
            host=HOST,
            mutation_profile_id=policy.profile_id,
        )
        (ROOT / "persistent-plan.json").write_text(json.dumps(asdict(plan), indent=2))
        print(json.dumps(asdict(plan), indent=2), flush=True)
        result = execute_lan_flash_plan(
            plan,
            frm,
            confirmation=plan.confirmation_phrase,
            receipt_directory=ROOT / "flash-receipts",
            transport=link(),
            host_key_rotator=rotate,
            return_timeout_s=90,
        )
        (ROOT / "persistent-result.json").write_text(
            json.dumps(asdict(result), indent=2)
        )
        print(json.dumps(asdict(result), indent=2), flush=True)
        assert result.outcome == "success"


if __name__ == "__main__":
    main()

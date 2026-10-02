"""Deploy the issue-120 component-qualified candidate through guarded PPU LAN flashing.

Component qualification: integrated daemon on .15, unchanged issue-119 kernel
previously qualified on .18, and byte-preserving packaging of the v0.59 base.
The combined image requires post-reboot qualification before publication.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pluto_plus.bootstrap_firmware import (
    PAIRED_RX_TX_CAPABLE_LAYOUT,
    STANDALONE_FLASH_PROFILES,
    BoundSshBootstrapTransport,
    execute_lan_flash_plan,
    prepare_lan_flash_plan,
    rotate_lan_ssh_host_key_after_attested_return,
)
from pluto_plus.doctor import FEATURE_103_V1_RELEASE_RAM_POLICY
from pluto_plus.radio_lock import acquire_radio_lock

SERIAL = "104000b29905000e17000800065934759d"
HOST = "192.168.1.15"
ROOT = Path("/home/mouse9911/release-evidence/v060")
BASELINE = "v0.60-plutoplus-spf-adaptive-native-1p25-rc1"
PARENT_FIT = "b18b3dbb09738cb218f2c478bd5a0e43fc378bbb0b414d0c9748797aab9539d9"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def qualify(binding):
    evidence = {}
    for name in (
        "pre-v3-1p25-retry",
        "pre-v3-2p5",
        "pre-v3-dma-fault",
        "pre-v3-cancel",
    ):
        path = ROOT / name / "report.json"
        raw = path.read_bytes()
        report = json.loads(raw)
        require(
            report["serial"] == SERIAL and report["host"] == HOST,
            "Validation failed: report['serial'] == SERIAL and report['host'] == HOST",
        )
        require(
            binding["iiod_sha256"] in report["daemon_attestation"],
            "Validation failed: binding['iiod_sha256'] in report['daemon_attestation']",
        )
        require(
            report["settings_restored"]
            and report["ordinary_capture_after"]["bytes"] == 32768,
            "Validation failed: report['settings_restored'] and report['ordinary_capture_after']['bytes'] == 32768",
        )
        require(
            report["elapsed_seconds"] < 30,
            "Validation failed: report['elapsed_seconds'] < 30",
        )
        if name.endswith("dma-fault"):
            require(
                report["terminal"]["state"] == 3 and report["terminal"]["error"] == -5,
                "Validation failed: report['terminal']['state'] == 3 and report['terminal']['error'] == -5",
            )
            require(
                report["terminal"]["flags"] == 1,
                "Validation failed: report['terminal']['flags'] == 1",
            )
        elif name.endswith("cancel"):
            require(
                "intentional client cancellation" in report["error"],
                "Validation failed: 'intentional client cancellation' in report['error']",
            )
        else:
            require(
                report["status"] == "completed",
                "Validation failed: report['status'] == 'completed'",
            )
            require(
                report["receipt"]["terminal"]["error"] == 0,
                "Validation failed: report['receipt']['terminal']['error'] == 0",
            )
            require(
                report["receipt"]["terminal"]["delivered"] > 50,
                "Validation failed: report['receipt']['terminal']['delivered'] > 50",
            )
            require(
                not report["receipt"]["terminal"]["invalid"],
                "Validation failed: not report['receipt']['terminal']['invalid']",
            )
            rate = report["setup"]["source_rate_hz"]
            require(
                report["receipt"]["preparation"]["configured"]["sample_rate_hz"]
                == rate,
                "Validation failed: report['receipt']['preparation']['configured']['sample_rate_hz'] == rate",
            )
            for row in report["visits"]:
                if row["result"] == 1:
                    require(
                        row["valid_end"] - row["valid_start"] == rate * 120 // 1000,
                        "Validation failed: row['valid_end'] - row['valid_start'] == rate * 120 // 1000",
                    )
                    require(
                        row["actual_iq_bytes"]
                        == row["iq_bytes"]
                        == rate * 120 // 1000 * 8,
                        "Validation failed: row['actual_iq_bytes'] == row['iq_bytes'] == rate * 120 // 1000 * 8",
                    )
        evidence[name] = hashlib.sha256(raw).hexdigest()
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    image = ROOT / "firmware/v060.dfu"
    binding = json.loads((image.parent / "artifact.json").read_text())
    evidence = qualify(binding)
    require(
        binding["kernel_sha256"]
        == "ea8d743df796a5bfea2597d9886ce8b4abe0720cdb03f0e82cf52c0a78f6bc81",
        "kernel differs from issue-119 qualified bytes",
    )
    require(
        binding["linux_source"] == "d3611e575b09fa4e43be99a513423cb1ab3f4d37",
        "kernel source differs from issue-119 qualification",
    )
    require(
        hashlib.sha256(image.read_bytes()).hexdigest() == binding["dfu_sha256"],
        "Validation failed: hashlib.sha256(image.read_bytes()).hexdigest() == binding['dfu_sha256']",
    )
    base = STANDALONE_FLASH_PROFILES[FEATURE_103_V1_RELEASE_RAM_POLICY.profile_id]
    profile_id = "v060-integrated-" + binding["dfu_sha256"][:12] + "-radio15"
    policy = base.policy.model_copy(
        update={
            "profile_id": profile_id,
            "release_tag": binding["firmware"],
            "device_firmware": binding["firmware"],
            "asset_name": image.name,
            "asset_sha256": binding["dfu_sha256"],
            "fit_body_sha256": binding["fit_sha256"],
            "fit_body_size": binding["fit_bytes"],
            "source_commit": binding["libiio_source"],
            "release_url": "https://github.com/misko/plutosdr-fw/issues/120",
            "hardware_qualified": True,
            "published_at": datetime.now(UTC),
        }
    )
    STANDALONE_FLASH_PROFILES[profile_id] = dataclasses.replace(
        base,
        policy=policy,
        persistent_allowed=True,
        source_iio_layout=PAIRED_RX_TX_CAPABLE_LAYOUT,
        return_iio_layout=PAIRED_RX_TX_CAPABLE_LAYOUT,
        allowed_before_firmwares=(BASELINE,),
    )
    known_hosts = ROOT / "private/radio15.known_hosts"
    transport = BoundSshBootstrapTransport(
        interface=None, password="analog", host=HOST, known_hosts_file=known_hosts
    )
    with acquire_radio_lock(SERIAL):
        parent = transport.run("head -c 12794623 /dev/mtdblock3 | sha256sum")
        require(PARENT_FIT in parent, "Validation failed: PARENT_FIT in parent")
        plan, frm = prepare_lan_flash_plan(
            image,
            serial=SERIAL,
            host=HOST,
            mutation_profile_id=profile_id,
            flash_transport=transport,
        )
        (ROOT / "lan-plan.json").write_text(
            json.dumps(
                {
                    "binding": binding,
                    "qualification_report_sha256": evidence,
                    "plan": dataclasses.asdict(plan),
                },
                indent=2,
                default=str,
            )
            + "\n"
        )
        print(json.dumps(dataclasses.asdict(plan), default=str), flush=True)
        if args.execute:

            def rotate():
                return rotate_lan_ssh_host_key_after_attested_return(
                    serial=SERIAL,
                    host=HOST,
                    expected_firmware=binding["firmware"],
                    expected_metadata_abi=3,
                    password="analog",
                    known_hosts_file=known_hosts,
                )

            result = execute_lan_flash_plan(
                plan,
                frm,
                confirmation=plan.confirmation_phrase,
                receipt_directory=ROOT / "lan-receipts",
                transport=transport,
                host_key_rotator=rotate,
            )
            print(json.dumps(dataclasses.asdict(result), default=str), flush=True)
            if result.outcome != "success":
                raise RuntimeError(
                    "Deployment did not succeed; inspect receipt before any retry"
                )


if __name__ == "__main__":
    main()

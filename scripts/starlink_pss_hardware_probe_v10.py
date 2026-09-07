#!/usr/bin/env python3
"""AD9361 launcher for the 30 MS/s acquisition-only v8 candidate.

Historical probe revisions remain immutable.  This DNM-only launcher admits
v8 for one operation, requires the exact 30 MS/s acquisition-only source
profile, and otherwise reuses v8's AD9361 identity plus the dependency-safe
measurement, restoration, radio-lock, route-lock, and receipt implementation.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.starlink_pss_hardware_probe_v8 as probe_v8

ProbeError = probe_v8.ProbeError
parser = probe_v8.parser

RUNTIME_TARGET = probe_v8.RUNTIME_TARGET
EXPECTED_MODEL = probe_v8.EXPECTED_MODEL
EXPECTED_FIRMWARE = "v0.50-plutoplus-starlink-pss-30m-rx-only-dnm-v8"
SOURCE_MANIFEST_NAME = "starlink-pss-multirate-rx-only-dnm-v8-source.yaml"
SOURCE_REVISION = "v8"
CANDIDATE_PROFILE = "acquisition-only"
RATE_MSPS = 30

probe_v1 = probe_v8.probe_v7.probe_v5.probe_v1
probe_v2 = probe_v8.probe_v7.probe_v2
probe_v5 = probe_v8.probe_v7.probe_v5


def _manifest_values(payload: bytes) -> dict[str, str]:
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise ProbeError("candidate source manifest is not UTF-8") from error
    values: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            raise ProbeError("candidate source manifest has a malformed line")
        key, value = (part.strip() for part in stripped.split(":", 1))
        if not key or key in values:
            raise ProbeError("candidate source manifest has an invalid key inventory")
        values[key] = value.strip('"')
    return values


def _require_acquisition_only_profile(handoff: Any) -> None:
    index_path = Path(handoff.candidate.artifact_index.path)
    expected_index = {
        "path": str(index_path),
        "bytes": handoff.candidate.artifact_index.bytes,
        "sha256": handoff.candidate.artifact_index.sha256,
    }
    if probe_v1._identity(index_path, label="candidate artifact index") != expected_index:
        raise ProbeError("candidate artifact index differs from the sealed plan")
    index = probe_v1._load_private_json(index_path, label="candidate artifact index")
    if (
        index.get("schema")
        != "plutosdr-fw.starlink-pss-multirate-candidate-index.v1"
        or index.get("schema_version") != 1
        or index.get("allowed_operation") != "ram-only"
        or index.get("allocated_radio_serial") != probe_v1.ALLOCATED_SERIAL
        or index.get("firmware_version") != EXPECTED_FIRMWARE
        or index.get("persistent_flash_eligible") is not False
        or index.get("rate_msps") != RATE_MSPS
        or index.get("runtime_target") != RUNTIME_TARGET
        or index.get("source_manifest_name") != SOURCE_MANIFEST_NAME
        or index.get("source_manifest_revision") != SOURCE_REVISION
    ):
        raise ProbeError("candidate artifact index is not the 30 MS/s v8 profile")

    manifest_payloads: list[bytes] = []
    for label in ("packaged_source_manifest", "qualification_source_manifest"):
        identity = index.get(label)
        if (
            not isinstance(identity, dict)
            or set(identity) != {"path", "bytes", "sha256"}
            or not isinstance(identity.get("path"), str)
        ):
            raise ProbeError(f"candidate {label} identity is invalid")
        path = Path(identity["path"])
        if probe_v1._identity(path, label=label.replace("_", " ")) != identity:
            raise ProbeError(f"candidate {label} differs from its artifact index")
        manifest_payloads.append(
            probe_v1._private_file(path, label=label.replace("_", " "))
        )
    if manifest_payloads[0] != manifest_payloads[1]:
        raise ProbeError("packaged and qualification source manifests differ")
    values = _manifest_values(manifest_payloads[0])
    if (
        values.get("schema") != "plutosdr-fw.source-manifest"
        or values.get("do_not_merge") != "true"
        or values.get("persistent_flash_eligible") != "false"
        or values.get("allocated_radio_serial") != probe_v1.ALLOCATED_SERIAL
        or values.get("starlink_pss_profile") != CANDIDATE_PROFILE
        or values.get("starlink_pss_profile_rate_gate_msps") != str(RATE_MSPS)
        or values.get("starlink_pss_30_ddc_stages") != "1"
        or values.get("starlink_pss_abi_30") != "1.2"
        or values.get("starlink_pss_group_delay_30_source_samples") != "7"
    ):
        raise ProbeError("candidate source manifest is not acquisition-only v8")


@contextmanager
def _ad9361_v8_acquisition_only_contract() -> Iterator[None]:
    """Scope v8 admission and profile verification to one operation."""

    original_revisions = probe_v2.SUPPORTED_SOURCE_REVISIONS
    original_loader = probe_v1._load_handoff

    def load_profiled_handoff(*args: Any, **kwargs: Any) -> Any:
        handoff = original_loader(*args, **kwargs)
        _require_acquisition_only_profile(handoff)
        return handoff

    with probe_v8._ad9361_1r1t_identity():
        probe_v2.SUPPORTED_SOURCE_REVISIONS = (
            "v2",
            "v3",
            "v4",
            "v5",
            "v6",
            "v8",
        )
        probe_v1._load_handoff = load_profiled_handoff
        try:
            yield
        finally:
            probe_v1._load_handoff = original_loader
            probe_v2.SUPPORTED_SOURCE_REVISIONS = original_revisions


def build_plan(args: Any) -> dict[str, Any]:
    with _ad9361_v8_acquisition_only_contract():
        return probe_v5.build_plan(args)


def execute_plan(args: Any) -> dict[str, Any]:
    with _ad9361_v8_acquisition_only_contract():
        return probe_v5.execute_plan(args)


def verify_receipt(args: Any) -> dict[str, Any]:
    with _ad9361_v8_acquisition_only_contract():
        return probe_v5.verify_receipt(args)


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.command == "plan":
            result = build_plan(arguments)
        elif arguments.command == "execute":
            result = execute_plan(arguments)
        else:
            result = verify_receipt(arguments)
    except (OSError, ValueError, ProbeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

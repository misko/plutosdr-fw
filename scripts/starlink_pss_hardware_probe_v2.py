#!/usr/bin/env python3
"""Revision-aware launcher for the immutable Starlink PSS hardware probe.

The v1 probe remains byte-for-byte reproducible. This launcher reuses its
measurement, receipt, and cleanup implementation while admitting both locked
v2 and RX-aperture-repaired v3 candidate firmware identities.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.starlink_pss_hardware_probe as probe_v1

SUPPORTED_SOURCE_REVISIONS = ("v2", "v3")
_validate_plan_v1 = probe_v1._validate_plan


def _expected_versions(rate_msps: int) -> set[str]:
    return {
        f"v0.50-plutoplus-starlink-pss-{rate_msps}m-rx-only-dnm-{revision}"
        for revision in SUPPORTED_SOURCE_REVISIONS
    }


def _load_handoff(
    *,
    ppu_repository: Path,
    ppu_commit: str,
    candidate_path: Path,
    operation_path: Path,
    ram_receipt_path: Path,
    rate_msps: int,
) -> SimpleNamespace:
    repository = probe_v1._verify_ppu_repository(ppu_repository, ppu_commit)
    ppu = probe_v1._import_ppu(repository)
    try:
        candidate = ppu.candidate.load_private_contract(
            candidate_path.absolute(), ppu.rx.ReleaseCandidatePlanV2
        )
        operation = ppu.candidate.load_private_contract(
            operation_path.absolute(), ppu.rx.ReleaseCandidateOperationPlanV2
        )
        receipt = ppu.candidate.load_private_contract(
            ram_receipt_path.absolute(), ppu.rx.ReleaseCandidateRamReceiptV2
        )
        ppu.rx.validate_rx_only_contract_bundle(
            candidate,
            operation,
            receipt,
            candidate_path=candidate_path.absolute(),
            operation_path=operation_path.absolute(),
        )
    except (OSError, ValueError, ppu.candidate.ReleaseCandidateContractError) as error:
        raise probe_v1.ProbeError(f"PPU RAM handoff is invalid: {error}") from error
    if (
        receipt.outcome != "pass"
        or not receipt.cleanup.verified
        or not receipt.host_route.release_verified
        or receipt.transition.persistent_write
        or candidate.expected_runtime.firmware_version
        not in _expected_versions(rate_msps)
        or candidate.expected_runtime.hardware_model != probe_v1.EXPECTED_MODEL
        or candidate.device_tool_repository != probe_v1.PPU_SLUG
        or candidate.device_tool_source_commit != ppu_commit
        or operation.runtime_target != probe_v1.RUNTIME_TARGET
        or operation.target.serial != probe_v1.ALLOCATED_SERIAL
        or receipt.target != operation.target
        or receipt.runtime_target != probe_v1.RUNTIME_TARGET
    ):
        raise probe_v1.ProbeError(
            "PPU RAM handoff is not a passing allocated-radio AD9363A trial"
        )
    return SimpleNamespace(
        ppu=ppu,
        candidate=candidate,
        operation=operation,
        receipt=receipt,
        repository=repository,
    )


def _validate_plan(plan: dict[str, Any]) -> None:
    expected = plan.get("expected_firmware")
    rate = plan.get("rate_msps")
    if not isinstance(rate, int) or expected not in _expected_versions(rate):
        raise probe_v1.ProbeError("probe plan firmware revision is unsupported")
    compatible = dict(plan)
    compatible["expected_firmware"] = (
        f"v0.50-plutoplus-starlink-pss-{rate}m-rx-only-dnm-v2"
    )
    _validate_plan_v1(compatible)


# The v1 implementation resolves these helpers from its own module globals.
# Replace only the two identity gates; all hardware, restoration, and receipt
# code remains the already-tested immutable implementation.
probe_v1._load_handoff = _load_handoff
probe_v1._validate_plan = _validate_plan

ProbeError = probe_v1.ProbeError
build_plan = probe_v1.build_plan
execute_plan = probe_v1.execute_plan
verify_receipt = probe_v1.verify_receipt
parser = probe_v1.parser


def main(argv: list[str] | None = None) -> int:
    return probe_v1.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())

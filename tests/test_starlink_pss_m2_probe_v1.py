from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

import scripts.starlink_pss_m2_probe_v1 as m2


def _identity(path: str, size: int, digest: str) -> dict[str, object]:
    return {"path": path, "bytes": size, "sha256": digest}


def _plan(receipt: str = "/tmp/m2-receipt.json") -> dict[str, object]:
    return {
        "schema": m2.PLAN_SCHEMA,
        "schema_version": 2,
        "plan_id": "1" * 32,
        "created_at": "2026-09-06T00:00:00Z",
        "hardware_accessed": False,
        "persistent_write": False,
        "serial": m2.probe_v1.ALLOCATED_SERIAL,
        "rate_msps": 15,
        "sample_rate_hz": 15_000_000,
        "rf_bandwidth_hz": 15_000_000,
        "runtime_target": m2.probe_v9.RUNTIME_TARGET,
        "expected_firmware": m2.EXPECTED_FIRMWARE,
        "phases": list(m2.PHASES),
        "controller_timeout_ms": 2_000,
        "ppu_repository": "/tmp/pluto-plus-utils",
        "ppu_source_commit": "2" * 40,
        "probe_plan": _identity("/tmp/probe-plan.json", 10, "3" * 64),
        "controller_binary": _identity("/tmp/m2ctl", 20, "4" * 64),
        "fixture_vector": _identity(
            "/tmp/fixture.mem", m2.FIXTURE_BYTES, m2.FIXTURE_SHA256
        ),
        "score_vector": _identity(
            "/tmp/scores.mem", m2.SCORES_BYTES, m2.SCORES_SHA256
        ),
        "receipt_path": receipt,
        "confirmation_phrase": (
            f"QUALIFY STARLINK PSS TIMING {m2.probe_v1.ALLOCATED_SERIAL} "
            f"15 MSPS PHASES {m2.PHASE_TEXT}"
        ),
    }


def _info(*, after: bool) -> dict[str, object]:
    return {
        "schema": m2.INFO_SCHEMA,
        "claim_scope": m2.INFO_CLAIM_SCOPE,
        "serial": m2.probe_v1.ALLOCATED_SERIAL,
        "input_rate_msps": 15,
        "psma_version": "0x00010001",
        "psma_status": "0x00000000",
        "psma_enabled": False,
        "pssi_identification": "0x50535349",
        "pssi_version": "0x00010000",
        "pssi_capabilities": "0x0000000f",
        "pssi_geometry": "0x00820082",
        "pssi_period_samples": 20_000,
        "pssi_last_sample_offset": 2_580_129,
        "pssi_current_index": 12_345_678,
        "pssi_status": "0x00000013" if after else "0x00000000",
        "pssi_fixture_count": 130 if after else 0,
        "pssi_fault_free": True,
        "live_pss_detected": False,
        "sss_detected": False,
        "frame_lock_claim": False,
    }


def _records() -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    targets = tuple(
        12_345 + multiplier * m2.TILE_SAMPLES for multiplier in (2, 5, 8)
    )
    generations = (11, 14, 17)
    for index, (phase, target, generation) in enumerate(
        zip(m2.PHASES, targets, generations, strict=True)
    ):
        delta = (32 + 20_000 - phase) % 20_000
        cases.append(
            {
                "schema": m2.CASE_SCHEMA,
                "stimulus": "deterministic_internal",
                "serial": m2.probe_v1.ALLOCATED_SERIAL,
                "case": index,
                "requested_phase": phase,
                "injection_start_index": target - m2.WARMUP_SAMPLES - delta,
                "target_map_start_index": target,
                "map_generation": generation,
                "actual_peak_phase": phase,
                "actual_peak_value": 16_320,
                "actual_runner_up_value": 7_424,
                "mismatch_count": 870,
                "unique_peak": True,
                "exact_map": False,
                "completed_generation": m2.PSSI_FIXTURE_GENERATION,
                "completed_repetitions": 130,
                "pss_timing_qualified": True,
                "live_pss_detected": False,
                "sss_detected": False,
                "frame_lock_claim": False,
            }
        )
    return [
        *cases,
        {
            "schema": m2.SUMMARY_SCHEMA,
            "stimulus": "deterministic_internal",
            "serial": m2.probe_v1.ALLOCATED_SERIAL,
            "input_rate_msps": 15,
            "cases_requested": 3,
            "cases_passed": 3,
            "maps_copied": 9,
            "first_map_generation": 9,
            "last_map_generation": 17,
            "final_health_flags": "0x00000000",
            "fault_free_epoch": True,
            "continuity_ok": True,
            "full_map_exactness_claimed": False,
            "pss_timing_qualified": True,
            "live_pss_detected": False,
            "sss_detected": False,
            "frame_lock_claim": False,
        },
    ]


def _write_private_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    path.chmod(0o600)


def test_plan_is_exactly_15_msps_v7_and_three_phase() -> None:
    plan = _plan()
    m2._validate_plan(plan)

    invalid = deepcopy(plan)
    invalid["phases"] = [0, 19_999]
    with pytest.raises(m2.ProbeError, match="deterministic"):
        m2._validate_plan(invalid)


def test_info_requires_disabled_fault_free_engine_and_completed_fixture() -> None:
    plan = _plan()
    m2._validate_info(_info(after=False), plan, after=False)
    m2._validate_info(_info(after=True), plan, after=True)

    invalid = _info(after=True)
    invalid["pssi_status"] = "0x00000033"
    with pytest.raises(m2.ProbeError, match="disabled fault-free"):
        m2._validate_info(invalid, plan, after=True)


def test_three_exact_timing_signatures_qualify_requested_phases() -> None:
    validated = m2._validate_qualification_records(_records(), _plan())
    assert [case["actual_peak_phase"] for case in validated["cases"]] == list(
        m2.PHASES
    )
    assert validated["summary"]["maps_copied"] == 9


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("inconsistent-exactness", "timing-signature"),
        ("wrong-peak", "timing-signature"),
        ("generation-gap", "contiguous"),
        ("target-gap", "contiguous"),
        ("false-live-claim", "timing-signature"),
        ("health-fault", "summary"),
    ],
)
def test_qualification_rejects_mismatch_discontinuity_fault_or_claim(
    mutation: str, message: str
) -> None:
    records = deepcopy(_records())
    if mutation == "inconsistent-exactness":
        records[0]["exact_map"] = True
    elif mutation == "wrong-peak":
        records[1]["actual_peak_phase"] = 0
    elif mutation == "generation-gap":
        records[1]["map_generation"] = 15
    elif mutation == "target-gap":
        records[1]["injection_start_index"] += 1
        records[1]["target_map_start_index"] += 1
    elif mutation == "false-live-claim":
        records[2]["live_pss_detected"] = True
    else:
        records[-1]["final_health_flags"] = "0x00000001"
    with pytest.raises(m2.ProbeError, match=message):
        m2._validate_qualification_records(records, _plan())


def test_committed_vectors_are_byte_exact(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    vector_root = root / "hdl/library/axi_starlink_pss_periodic_injector/tb"
    tmp_path.chmod(0o700)
    fixture_path = tmp_path / "fixture.mem"
    scores_path = tmp_path / "scores.mem"
    fixture_path.write_bytes(
        (vector_root / "upper_edge_pss_periodic_fixture_ci16.mem").read_bytes()
    )
    scores_path.write_bytes((vector_root / "m2_period_scores_u8.mem").read_bytes())
    fixture_path.chmod(0o644)
    scores_path.chmod(0o644)
    fixture, _ = m2._vector_identity(
        fixture_path, kind="fixture"
    )
    scores, _ = m2._vector_identity(scores_path, kind="scores")
    assert fixture["sha256"] == m2.FIXTURE_SHA256
    assert scores["sha256"] == m2.SCORES_SHA256


def test_passing_receipt_revalidates_all_strict_records(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    plan_path = tmp_path / "plan.json"
    receipt_path = tmp_path / "receipt.json"
    plan = _plan(str(receipt_path))
    _write_private_json(plan_path, plan)
    receipt = {
        "schema": m2.RECEIPT_SCHEMA,
        "schema_version": 2,
        "receipt_id": "5" * 32,
        "outcome": "pass",
        "started_at": "2026-09-06T00:00:00Z",
        "completed_at": "2026-09-06T00:00:01Z",
        "plan": m2.probe_v1._identity(plan_path, label="M2 plan"),
        "serial": m2.probe_v1.ALLOCATED_SERIAL,
        "rate_msps": 15,
        "runtime_target": m2.probe_v9.RUNTIME_TARGET,
        "expected_firmware": m2.EXPECTED_FIRMWARE,
        "hardware_accessed": True,
        "persistent_write": False,
        "claim_scope": m2.CLAIM_SCOPE,
        "pss_timing_qualified": True,
        "live_pss_detected": False,
        "sss_detected": False,
        "frame_lock_claim": False,
        "runtime": {
            "serial": m2.probe_v1.ALLOCATED_SERIAL,
            "firmware_version": m2.EXPECTED_FIRMWARE,
            "hardware_model": m2.probe_v9.EXPECTED_MODEL,
            "single_rx_setup": {"runtime_target": m2.probe_v9.RUNTIME_TARGET},
        },
        "measurement": {
            "uploads_verified": True,
            "uploads_removed": True,
            "iio_restore_verified": True,
            "engine_disable_verified": True,
            "timing_signatures_verified": True,
            "full_map_exactness_claimed": False,
            "controller_info_before": _info(after=False),
            "qualification_records": _records(),
            "controller_info_after": _info(after=True),
        },
        "route_release_verified": True,
        "recovery_required": True,
        "error": None,
    }
    _write_private_json(receipt_path, receipt)

    result = m2.verify_receipt(
        type("Arguments", (), {"plan": plan_path, "receipt": receipt_path})()
    )
    assert result["outcome"] == "pass"
    assert result["pss_timing_qualified"] is True


def test_m2_script_is_executable() -> None:
    assert Path(m2.__file__).stat().st_mode & 0o111


def _manifest_values(path: Path) -> dict[str, str]:
    return {
        key.strip(): value.strip().strip('"')
        for line in path.read_text().splitlines()
        if line and not line.startswith("#") and ":" in line
        for key, value in (line.split(":", 1),)
    }


def test_m2_v1_source_manifest_preserves_the_failed_probe_provenance() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = root / "manifests/starlink-pss-m2-probe-dnm-v1-source.yaml"
    values = _manifest_values(manifest)
    assert values["schema"] == "plutosdr-fw.starlink-pss-m2-probe-source"
    assert values["schema_version"] == "1"
    assert values["do_not_merge"] == "true"
    assert values["persistent_flash_eligible"] == "false"
    assert values["hardware_accessed"] == "false"
    assert values["runtime_target"] == "ad9361-1r1t"
    assert values["supported_sample_rate_msps"] == "15"
    assert values["test_phases"] == m2.PHASE_TEXT
    assert values["controller_sha256"] == (
        "135ff46e857d733a0508e6d41f66ec9f31c46d0bd8d9e4aec545b7cdc8d4aa1d"
    )
    assert values["host_test_sha256"] == (
        "1e2768d351aa2483902c6f50671e8ee2f3b51b7eefca1f97b5250c17a2fbba4a"
    )
    assert values["plan_sha256"] == (
        "c9d4bb1848affb28c064a96c84a96d1e72d6114900c256d8543111afa7a163e1"
    )
    for prefix in (
        "v9_probe",
        "v9_probe_manifest",
        "fixture_vector",
        "score_vector",
        "candidate_source_manifest",
    ):
        member = root / values[f"{prefix}_path"]
        assert member.is_file()
        assert m2.hashlib.sha256(member.read_bytes()).hexdigest() == values[
            f"{prefix}_sha256"
        ]


def test_m2_v2_source_manifest_supersedes_v1_and_is_byte_exact() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = root / "manifests/starlink-pss-m2-probe-dnm-v2-source.yaml"
    values = _manifest_values(manifest)

    assert values["schema"] == "plutosdr-fw.starlink-pss-m2-probe-source"
    assert values["schema_version"] == "2"
    assert values["supersedes_manifest"] == (
        "starlink-pss-m2-probe-dnm-v1-source.yaml"
    )
    assert values["source_change"] == "abi-1.1-fixed-rate-controller-correction"
    assert values["do_not_merge"] == "true"
    assert values["persistent_flash_eligible"] == "false"
    assert values["hardware_accessed"] == "false"
    assert values["runtime_target"] == "ad9361-1r1t"
    assert values["supported_sample_rate_msps"] == "15"
    assert values["test_phases"] == m2.PHASE_TEXT
    assert values["host_probe_sha256"] == (
        "0f9a1819ec1f19e99b2a9e1fa72581cf86ef807a2aedbabeddd03a8c39e9be92"
    )
    assert values["host_test_sha256"] == (
        "37d8764c4fcd586631b23431fdbb7dd73b9ca065c0e8ea3413acf5a7f500c452"
    )
    assert values["controller_sha256"] == (
        "f7b26e2b68d4dfa7afe471d55fb34c82696f6a719a2b0a64bd35594de5b57029"
    )
    for prefix in (
        "v9_probe",
        "v9_probe_manifest",
        "fixture_vector",
        "score_vector",
        "candidate_source_manifest",
    ):
        member = root / values[f"{prefix}_path"]
        assert member.is_file()
        assert m2.hashlib.sha256(member.read_bytes()).hexdigest() == values[
            f"{prefix}_sha256"
        ]

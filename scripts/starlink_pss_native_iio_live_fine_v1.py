#!/usr/bin/env python3
"""Trigger and qualify same-RF full-rate PSS refinement on the live receiver.

One fresh FPGA epoch scans coarse maps until the first frozen-policy positive
point.  The map stream is then closed and three short matched / energy-identical
mismatched / matched fine-timing brackets run immediately at the same RX LO.
Raw IQ never leaves the FPGA.  This can claim live PSS fine timing only; SSS and
frame lock remain explicitly out of scope.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from contextlib import ExitStack
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PPU = Path("/home/mouse9911/gits/pluto-plus-utils")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(PPU / "src") not in sys.path:
    sys.path.insert(0, str(PPU / "src"))

from pluto_plus.hardware.pss_iio import (
    PSS_MAP_CHUNKS,
    PSS_PACKET_BYTES,
    PssFinePacket,
    PssIioClient,
)
from pluto_plus.radio_lock import acquire_radio_lock

import scripts.starlink_pss_iio_cabled_v1 as cabled
import scripts.starlink_pss_native_iio_live_campaign_v2 as v2
import scripts.starlink_pss_native_iio_live_campaign_v3 as v3
from scripts.starlink_pss_iio_cabled_v1 import (
    RATE_PROFILES,
    RX_SERIAL,
    QualificationError,
    RateProfile,
    _configure_rx,
    _now,
    _number,
    _restore_rx,
)
from scripts.starlink_pss_native_iio_qualify_v1 import (
    FRAME_SAMPLES,
    MAP_CHUNKS,
    MAP_SCAN_BYTES,
    _identity,
    _integer,
    _load,
    _write_new,
)
from scripts.starlink_pss_native_iio_qualify_v1 import (
    POLICY as COARSE_POLICY,
)

RUN_SCHEMA = "plutosdr-fw.starlink-pss-native-iio-live-fine-run.v1"
ANALYSIS_SCHEMA = "plutosdr-fw.starlink-pss-native-iio-live-fine-analysis.v1"
TRIGGER_ROLE = "on_channel_trigger"
BRACKET_ROLES = ("matched_a", "energy_matched_mismatch", "matched_b")
BRACKET_COUNT = 3
RESULTS_PER_BLOCK = 64
MATCHED_GENERATION_BASE = 0x30F10000
REQUEST_BASE = 0xB0F10000
CONTROL_PATH = Path(
    "/home/mouse9911/pluto-state/starlink-rx-only-dnm/"
    "persistent-30-native-iio-17-20260908/fine-control-coefficients-v1/"
    "starlink_pss30_energy_matched_qpsk_mismatch_v1.mem"
)
CONTROL_SHA256 = "6699b12f1688c12c65ec576c18f9e006d8371d6d2ac65015bd9f0e0f34163ebf"
CONTROL_EVIDENCE_PATH = CONTROL_PATH.with_suffix(".json")
CONTROL_EVIDENCE_SHA256 = (
    "58a62c7fdb75a1c78f4522d7df3369722437c5537178b30985bcf5ca6392d1a6"
)
COEFFICIENT_ENERGY = 1_073_746_351
FINE_POLICY = {
    "bracket_count": BRACKET_COUNT,
    "results_per_block": RESULTS_PER_BLOCK,
    "minimum_qualifying_brackets": 1,
    "minimum_matched_median_normalized_score": 0.08,
    "minimum_matched_to_mismatch_median_ratio": 2.0,
    "minimum_matched_pair_median_ratio": 0.5,
    "maximum_matched_residual_source_samples": 1.0,
    "maximum_matched_period_error_source_samples": 2.0,
    "maximum_matched_period_disagreement_source_samples": 0.25,
    "maximum_matched_aperture_edge_hits": 0,
}

PACKET_FIELDS = {
    "ordinal",
    "request_id",
    "center_index",
    "center_timestamp",
    "winner_lag",
    "winner_timestamp",
    "coefficient_generation",
    "correlation_real",
    "correlation_imag",
    "sample_energy",
    "coefficient_energy",
    "saturation_events",
    "packet_words",
}
BLOCK_FIELDS = {
    "role",
    "coefficient_generation",
    "coefficient_sha256",
    "request_base",
    "schedule_anchor_source",
    "schedule_period_source",
    "first_center_source",
    "results",
    "analysis",
}
RUN_FIELDS = {
    "schema",
    "schema_version",
    "started_at",
    "completed_at",
    "outcome",
    "persistent_write",
    "transmitter_opened",
    "serial",
    "rate_msps",
    "sample_rate_hz",
    "geometry",
    "scan_offset_order_hz",
    "firmware_source_commit",
    "ppu_source_commit",
    "deployment",
    "policy",
    "coefficients",
    "receiver",
    "scan",
    "fine",
    "stream",
    "gates",
    "cleanup",
    "pss_detected",
    "fine_timing_qualified",
    "sss_detected",
    "frame_lock_claim",
}
GATE_FIELDS = {
    "fresh_map_counter_epoch",
    "fresh_fine_counter_epoch",
    "single_map_epoch_exact",
    "driver_map_count_exact",
    "driver_chunk_count_exact",
    "map_push_failure_free",
    "map_fault_free",
    "fine_packet_count_exact",
    "fine_last_schedule_submitted_exact",
    "fine_push_failure_free",
    "fine_validation_failure_free",
    "fine_fault_free",
    "final_matched_coefficient_active",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_control_evidence() -> dict[str, Any]:
    evidence = _load(CONTROL_EVIDENCE_PATH, label="energy-matched control evidence")
    matched = evidence.get("matched")
    memory = evidence.get("memory_file")
    diagnostic = evidence.get("correlation_diagnostic")
    if (
        _sha256(CONTROL_PATH) != CONTROL_SHA256
        or _sha256(CONTROL_EVIDENCE_PATH) != CONTROL_EVIDENCE_SHA256
        or evidence.get("schema")
        != "plutosdr-fw.starlink-pss-tracker-energy-matched-control.v1"
        or evidence.get("schema_version") != 1
        or evidence.get("offline_generation_only") is not True
        or evidence.get("radio_access") is not False
        or evidence.get("rate_msps") != 30
        or evidence.get("tap_count") != 132
        or evidence.get("energy_exact") is not True
        or evidence.get("matched_coefficient_energy") != COEFFICIENT_ENERGY
        or evidence.get("control_coefficient_energy") != COEFFICIENT_ENERGY
        or not isinstance(matched, dict)
        or matched.get("sha256") != RATE_PROFILES[30].coefficient_sha256
        or not isinstance(memory, dict)
        or memory.get("sha256") != CONTROL_SHA256
        or not isinstance(diagnostic, dict)
        or diagnostic.get("aperture_samples") != RATE_PROFILES[30].aperture_samples
        or not 0.0
        <= float(diagnostic.get("maximum_overlap_normalized_score", 1.0))
        < 0.08
    ):
        raise QualificationError("energy-matched control evidence differs")
    return evidence


def _fine_counters(client: PssIioClient) -> dict[str, int]:
    return {
        "schedule_submitted": _number(client.tracker, "schedule_submitted"),
        "packets_delivered": _number(client.tracker, "packets_delivered"),
        "buffer_push_failures": _number(client.tracker, "buffer_push_failures"),
        "packet_validation_failures": _number(
            client.tracker, "packet_validation_failures"
        ),
        "fault_flags": _number(client.tracker, "fault_flags"),
        "active_coefficient_generation": _number(
            client.tracker, "active_coefficient_generation"
        ),
    }


def _generation(bracket: int, role_index: int) -> int:
    return MATCHED_GENERATION_BASE + bracket * len(BRACKET_ROLES) + role_index + 1


def _request_base(bracket: int, role_index: int) -> int:
    return REQUEST_BASE + bracket * 0x1000 + role_index * 0x100


def _last_passing_anchor(point: dict[str, Any]) -> tuple[float, float]:
    passing = [
        window
        for window in point["coarse_windows"]
        if window["peak_to_median"] >= COARSE_POLICY["minimum_peak_to_median"]
        and window["robust_z"] >= COARSE_POLICY["minimum_robust_z"]
    ]
    if not passing:
        raise QualificationError("positive coarse point has no passing timing seed")
    latest = passing[-1]
    return (
        float(latest["candidate_start_index_source_center"]),
        float(latest["estimated_frame_period_source_samples"]),
    )


def _run_block(
    client: PssIioClient,
    *,
    profile: RateProfile,
    role: str,
    coefficient_path: Path,
    coefficient_sha256: str,
    generation: int,
    request_base: int,
    anchor: float,
    period: float,
) -> dict[str, Any]:
    client.load_coefficient_file(coefficient_path, generation=generation)
    if _number(client.tracker, "active_coefficient_generation") != generation:
        raise QualificationError("fine coefficient generation did not become active")
    first_center = cabled._future_center(
        anchor,
        cabled._current_index(client),
        period,
        host_lead_samples=profile.host_lead_samples,
    )
    results = cabled._read_fine(
        client,
        first_center=first_center,
        request_base=request_base,
        count=RESULTS_PER_BLOCK,
        period=period,
    )
    if any(
        result["coefficient_generation"] != generation
        or result["coefficient_energy"] != COEFFICIENT_ENERGY
        or result["saturation_events"] != 0
        for result in results
    ):
        raise QualificationError(
            "fine packet coefficient or saturation identity differs"
        )
    return {
        "role": role,
        "coefficient_generation": generation,
        "coefficient_sha256": coefficient_sha256,
        "request_base": request_base,
        "schedule_anchor_source": anchor,
        "schedule_period_source": period,
        "first_center_source": first_center,
        "results": results,
        "analysis": cabled._analyze(
            results,
            period_samples=profile.period_samples,
            aperture_samples=profile.aperture_samples,
        ),
    }


def _matched_tracking_quality(
    analysis: dict[str, Any], *, profile: RateProfile
) -> bool:
    return (
        analysis["normalized_score_median"]
        >= FINE_POLICY["minimum_matched_median_normalized_score"]
        and analysis["residual_max_abs_source_samples"]
        <= FINE_POLICY["maximum_matched_residual_source_samples"]
        and abs(analysis["fitted_period_source_samples"] - profile.period_samples)
        <= FINE_POLICY["maximum_matched_period_error_source_samples"]
        and analysis["aperture_edge_hits"]
        <= FINE_POLICY["maximum_matched_aperture_edge_hits"]
    )


def evaluate_bracket(
    bracket: dict[str, Any], *, profile: RateProfile
) -> dict[str, Any]:
    if set(bracket) != set(BRACKET_ROLES):
        raise QualificationError("fine bracket role inventory differs")
    matched_a = bracket["matched_a"]["analysis"]
    mismatch = bracket["energy_matched_mismatch"]["analysis"]
    matched_b = bracket["matched_b"]["analysis"]
    score_a = float(matched_a["normalized_score_median"])
    score_b = float(matched_b["normalized_score_median"])
    control_score = float(mismatch["normalized_score_median"])
    contrast = min(score_a, score_b) / max(control_score, sys.float_info.min)
    symmetry = min(score_a, score_b) / max(score_a, score_b, sys.float_info.min)
    period_disagreement = abs(
        float(matched_a["fitted_period_source_samples"])
        - float(matched_b["fitted_period_source_samples"])
    )
    gates = {
        "matched_a_tracking_quality": _matched_tracking_quality(
            matched_a, profile=profile
        ),
        "matched_b_tracking_quality": _matched_tracking_quality(
            matched_b, profile=profile
        ),
        "matched_to_mismatch_contrast_met": contrast
        >= FINE_POLICY["minimum_matched_to_mismatch_median_ratio"],
        "matched_pair_symmetry_met": symmetry
        >= FINE_POLICY["minimum_matched_pair_median_ratio"],
        "matched_period_agreement_met": period_disagreement
        <= FINE_POLICY["maximum_matched_period_disagreement_source_samples"],
    }
    return {
        "qualified": all(gates.values()),
        "gates": gates,
        "matched_to_mismatch_median_ratio": contrast,
        "matched_pair_median_ratio": symmetry,
        "matched_period_disagreement_source_samples": period_disagreement,
    }


def _run_brackets(
    client: PssIioClient,
    *,
    profile: RateProfile,
    anchor: float,
    period: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    brackets: list[dict[str, Any]] = []
    for bracket_index in range(BRACKET_COUNT):
        blocks: dict[str, Any] = {}
        matched_a = _run_block(
            client,
            profile=profile,
            role="matched_a",
            coefficient_path=profile.coefficient_path,
            coefficient_sha256=profile.coefficient_sha256,
            generation=_generation(bracket_index, 0),
            request_base=_request_base(bracket_index, 0),
            anchor=anchor,
            period=period,
        )
        blocks["matched_a"] = matched_a
        if _matched_tracking_quality(matched_a["analysis"], profile=profile):
            anchor = float(matched_a["results"][-1]["winner_timestamp"])
            period = float(matched_a["analysis"]["fitted_period_source_samples"])
        blocks["energy_matched_mismatch"] = _run_block(
            client,
            profile=profile,
            role="energy_matched_mismatch",
            coefficient_path=CONTROL_PATH,
            coefficient_sha256=CONTROL_SHA256,
            generation=_generation(bracket_index, 1),
            request_base=_request_base(bracket_index, 1),
            anchor=anchor,
            period=period,
        )
        matched_b = _run_block(
            client,
            profile=profile,
            role="matched_b",
            coefficient_path=profile.coefficient_path,
            coefficient_sha256=profile.coefficient_sha256,
            generation=_generation(bracket_index, 2),
            request_base=_request_base(bracket_index, 2),
            anchor=anchor,
            period=period,
        )
        blocks["matched_b"] = matched_b
        if _matched_tracking_quality(matched_b["analysis"], profile=profile):
            anchor = float(matched_b["results"][-1]["winner_timestamp"])
            period = float(matched_b["analysis"]["fitted_period_source_samples"])
        evaluation = evaluate_bracket(blocks, profile=profile)
        brackets.append(
            {"ordinal": bracket_index + 1, "blocks": blocks, "evaluation": evaluation}
        )
    passing = [
        value["ordinal"] for value in brackets if value["evaluation"]["qualified"]
    ]
    return brackets, {
        "qualified": len(passing) >= FINE_POLICY["minimum_qualifying_brackets"],
        "qualifying_bracket_ordinals": passing,
        "qualifying_bracket_count": len(passing),
    }


def run(
    output: Path,
    *,
    profile: RateProfile,
    on_if_hz: int,
    deployment_receipt: Path,
    known_hosts_file: Path,
    reboot_receipts: list[Path],
    firmware_source_commit: str,
    ppu_source_commit: str,
) -> dict[str, Any]:
    if profile.rate_msps != 30:
        raise ValueError("live fine v1 is frozen for 30 MS/s")
    geometry = v3._scan_geometry(on_if_hz)
    firmware_source_commit = v2._validate_source_commit(
        firmware_source_commit, label="firmware source commit"
    )
    ppu_source_commit = v2._validate_source_commit(
        ppu_source_commit, label="PPU source commit"
    )
    v2._verify_source_checkout(
        ROOT,
        firmware_source_commit,
        label="firmware source",
        expected_origin_suffix="/misko/plutosdr-fw",
    )
    v2._verify_source_checkout(
        PPU,
        ppu_source_commit,
        label="PPU source",
        expected_origin_suffix="/misko/pluto-plus-utils",
    )
    deployment = v2._deployment_binding(
        deployment_receipt,
        known_hosts_file,
        rate_msps=profile.rate_msps,
        reboot_receipts=reboot_receipts,
    )
    control_evidence = _load_control_evidence()
    if _sha256(profile.coefficient_path) != profile.coefficient_sha256:
        raise QualificationError("matched coefficient identity differs")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    receipt: dict[str, Any] = {
        "schema": RUN_SCHEMA,
        "schema_version": 1,
        "started_at": _now(),
        "outcome": "started",
        "persistent_write": False,
        "transmitter_opened": False,
        "serial": RX_SERIAL,
        "rate_msps": profile.rate_msps,
        "sample_rate_hz": profile.rate_hz,
        "geometry": geometry,
        "scan_offset_order_hz": list(v3.OFFSET_ORDER_HZ),
        "firmware_source_commit": firmware_source_commit,
        "ppu_source_commit": ppu_source_commit,
        "deployment": deployment,
        "policy": {"coarse": COARSE_POLICY, "fine": FINE_POLICY},
        "coefficients": {
            "matched": {
                "path": str(profile.coefficient_path.resolve()),
                "sha256": profile.coefficient_sha256,
                "energy": COEFFICIENT_ENERGY,
            },
            "mismatch": {
                "path": str(CONTROL_PATH.resolve()),
                "sha256": CONTROL_SHA256,
                "energy": COEFFICIENT_ENERGY,
                "evidence": _identity(CONTROL_EVIDENCE_PATH),
                "construction": control_evidence["mask"]["construction"],
            },
        },
        "receiver": {"transport": "ethernet", "uri": v2.ETHERNET_URI},
        "scan": {"points": [], "trigger_point_ordinal": None},
        "fine": {"brackets": [], "evaluation": {"qualified": False}},
        "stream": {},
        "gates": {},
        "cleanup": {"errors": []},
        "pss_detected": False,
        "fine_timing_qualified": False,
        "sss_detected": False,
        "frame_lock_claim": False,
    }
    client: PssIioClient | None = None
    before: dict[str, Any] | None = None
    stream: v2.ContinuousMapStream | None = None
    body_error: BaseException | None = None
    lock_stack = ExitStack()
    try:
        lock_stack.enter_context(acquire_radio_lock(RX_SERIAL))
        client = PssIioClient.connect(v2.ETHERNET_URI, expected_serial=RX_SERIAL)
        before, selected = _configure_rx(client, profile, lo_hz=on_if_hz)
        receipt["receiver"].update(
            {"firmware": profile.firmware, "original": before, "selected": selected}
        )
        initial_map_counters = v2._driver_counters(client)
        initial_fine_counters = _fine_counters(client)
        client.load_coefficient_file(
            profile.coefficient_path, generation=profile.coefficient_generation
        )
        stream = v2.ContinuousMapStream(client, rate_msps=profile.rate_msps)
        client.open_maps(refill_chunks=PSS_MAP_CHUNKS)
        trigger: dict[str, Any] | None = None
        for ordinal, offset_hz in enumerate(v3.OFFSET_ORDER_HZ, 1):
            point = v3._capture_point(
                client,
                stream,
                role=TRIGGER_ROLE,
                ordinal=ordinal,
                base_if_hz=on_if_hz,
                offset_hz=offset_hz,
            )
            receipt["scan"]["points"].append(point)
            if point["metrics"]["classification"] == "positive_track":
                trigger = point
                receipt["scan"]["trigger_point_ordinal"] = ordinal
                break
        client.close_maps()
        if trigger is not None:
            anchor, period = _last_passing_anchor(trigger)
            brackets, fine_evaluation = _run_brackets(
                client,
                profile=profile,
                anchor=anchor,
                period=period,
            )
            receipt["fine"] = {
                "seed_anchor_source": anchor,
                "seed_period_source": period,
                "brackets": brackets,
                "evaluation": fine_evaluation,
            }
        final_map_counters = v2._driver_counters(client)
        final_fine_counters = _fine_counters(client)
        expected_maps = len(receipt["scan"]["points"]) * v3.MAPS_PER_POINT
        expected_packets = (
            BRACKET_COUNT * len(BRACKET_ROLES) * RESULTS_PER_BLOCK
            if trigger is not None
            else 0
        )
        expected_final_generation = (
            _generation(BRACKET_COUNT - 1, len(BRACKET_ROLES) - 1)
            if trigger is not None
            else profile.coefficient_generation
        )
        gates = {
            "fresh_map_counter_epoch": initial_map_counters["maps_delivered"] == 0
            and initial_map_counters["chunks_delivered"] == 0,
            "fresh_fine_counter_epoch": initial_fine_counters["packets_delivered"] == 0,
            "single_map_epoch_exact": stream.count == expected_maps,
            "driver_map_count_exact": final_map_counters["maps_delivered"]
            == expected_maps,
            "driver_chunk_count_exact": final_map_counters["chunks_delivered"]
            == expected_maps * PSS_MAP_CHUNKS,
            "map_push_failure_free": final_map_counters["map_buffer_push_failures"]
            == 0,
            "map_fault_free": final_map_counters["map_fault_flags"] == 0,
            "fine_packet_count_exact": final_fine_counters["packets_delivered"]
            == expected_packets,
            "fine_last_schedule_submitted_exact": final_fine_counters[
                "schedule_submitted"
            ]
            == (RESULTS_PER_BLOCK if trigger is not None else 0),
            "fine_push_failure_free": final_fine_counters["buffer_push_failures"] == 0,
            "fine_validation_failure_free": final_fine_counters[
                "packet_validation_failures"
            ]
            == 0,
            "fine_fault_free": final_fine_counters["fault_flags"] == 0,
            "final_matched_coefficient_active": final_fine_counters[
                "active_coefficient_generation"
            ]
            == expected_final_generation,
        }
        receipt["stream"] = {
            "complete_maps": stream.count,
            "map_digest_sha256": stream.digest.hexdigest(),
            "logical_map_bytes": stream.count * FRAME_SAMPLES * 2,
            "map_transport_bytes": stream.count * MAP_CHUNKS * MAP_SCAN_BYTES,
            "fine_packets": expected_packets,
            "fine_transport_bytes": expected_packets * 128,
            "initial_map_counters": initial_map_counters,
            "final_map_counters": final_map_counters,
            "initial_fine_counters": initial_fine_counters,
            "final_fine_counters": final_fine_counters,
        }
        receipt["gates"] = gates
        failed = [name for name, passed in gates.items() if not passed]
        if failed:
            raise QualificationError(
                f"native live fine transport gates failed: {failed}"
            )
        receipt["pss_detected"] = trigger is not None
        receipt["fine_timing_qualified"] = receipt["fine"]["evaluation"].get(
            "qualified", False
        )
        receipt["outcome"] = "pass"
    except BaseException as error:  # noqa: BLE001
        body_error = error
        receipt["outcome"] = "failed"
        receipt["pss_detected"] = False
        receipt["fine_timing_qualified"] = False
        receipt["error"] = f"{type(error).__name__}: {error}"
    finally:
        cleanup_errors: list[str] = receipt["cleanup"]["errors"]
        if client is not None:
            try:
                client.close_fine()
                client.close_maps()
            except BaseException as error:  # noqa: BLE001
                cleanup_errors.append(f"RX stream close: {error}")
            if before is not None:
                try:
                    receipt["cleanup"]["rx_restored"] = _restore_rx(client, before)
                except BaseException as error:  # noqa: BLE001
                    cleanup_errors.append(f"RX restore: {error}")
            try:
                client.close()
            except BaseException as error:  # noqa: BLE001
                cleanup_errors.append(f"RX context close: {error}")
        try:
            lock_stack.close()
        except BaseException as error:  # noqa: BLE001
            cleanup_errors.append(f"RX lock release: {error}")
        receipt["cleanup"]["verified"] = not cleanup_errors
        if cleanup_errors:
            receipt["outcome"] = "failed"
            receipt["pss_detected"] = False
            receipt["fine_timing_qualified"] = False
        receipt["completed_at"] = _now()
        receipt_path = output / "run-receipt.json"
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        receipt["receipt"] = str(receipt_path)
    if body_error is not None:
        raise body_error
    if receipt["outcome"] != "pass":
        raise QualificationError("native live fine cleanup did not verify")
    return receipt


def _decode_packet(document: dict[str, Any], *, rate_msps: int) -> PssFinePacket:
    if not isinstance(document, dict) or set(document) != PACKET_FIELDS:
        raise QualificationError("fine packet document field inventory differs")
    words = document.get("packet_words")
    if (
        not isinstance(words, list)
        or len(words) != PSS_PACKET_BYTES // 4
        or any(
            not isinstance(word, str)
            or len(word) != 10
            or not word.startswith("0x")
            or any(character not in "0123456789abcdef" for character in word[2:])
            for word in words
        )
    ):
        raise QualificationError("fine packet word encoding differs")
    try:
        packet = PssFinePacket.decode(
            struct.pack(f"<{len(words)}I", *(int(word, 16) for word in words)),
            rate_msps=rate_msps,
        )
    except (ValueError, struct.error) as error:
        raise QualificationError("fine packet ABI replay failed") from error
    if document != cabled._packet_document(packet, document["ordinal"]):
        raise QualificationError("fine packet fields differ from its encoded words")
    return packet


def _validate_block(
    block: dict[str, Any],
    *,
    profile: RateProfile,
    role: str,
    bracket_index: int,
    role_index: int,
) -> None:
    expected_sha = (
        CONTROL_SHA256
        if role == "energy_matched_mismatch"
        else profile.coefficient_sha256
    )
    generation = _generation(bracket_index, role_index)
    request_base = _request_base(bracket_index, role_index)
    results = block.get("results") if isinstance(block, dict) else None
    if (
        not isinstance(block, dict)
        or set(block) != BLOCK_FIELDS
        or block.get("role") != role
        or block.get("coefficient_generation") != generation
        or block.get("coefficient_sha256") != expected_sha
        or block.get("request_base") != request_base
        or not isinstance(results, list)
        or len(results) != RESULTS_PER_BLOCK
        or block.get("first_center_source")
        != (
            results[0].get("center_timestamp") if isinstance(results[0], dict) else None
        )
    ):
        raise QualificationError("fine block root contract differs")
    for ordinal, document in enumerate(results):
        packet = _decode_packet(document, rate_msps=profile.rate_msps)
        if (
            document["ordinal"] != ordinal
            or packet.request_id != request_base + ordinal
            or packet.coefficient_generation != generation
            or packet.coefficient_energy != COEFFICIENT_ENERGY
            or packet.saturation_events != 0
        ):
            raise QualificationError("fine packet sequence or coefficient differs")
    if block.get("analysis") != cabled._analyze(
        results,
        period_samples=profile.period_samples,
        aperture_samples=profile.aperture_samples,
    ):
        raise QualificationError("fine block analysis differs from replay")


def replay(*, receipt_path: Path, output: Path) -> dict[str, Any]:
    receipt = _load(receipt_path, label="native live fine campaign")
    rate_msps = _integer(receipt.get("rate_msps"), label="rate", minimum=1)
    profile = RATE_PROFILES.get(rate_msps)
    if profile is None or rate_msps != 30:
        raise QualificationError("native live fine receipt rate differs")
    geometry = receipt.get("geometry")
    receiver = receipt.get("receiver")
    selected = receiver.get("selected") if isinstance(receiver, dict) else None
    scan = receipt.get("scan")
    points = scan.get("points") if isinstance(scan, dict) else None
    stream = receipt.get("stream")
    cleanup = receipt.get("cleanup")
    gates = receipt.get("gates")
    fine = receipt.get("fine")
    brackets = fine.get("brackets") if isinstance(fine, dict) else None
    if (
        set(receipt) != RUN_FIELDS
        or receipt.get("schema") != RUN_SCHEMA
        or receipt.get("schema_version") != 1
        or receipt.get("outcome") != "pass"
        or receipt.get("persistent_write") is not False
        or receipt.get("transmitter_opened") is not False
        or receipt.get("serial") != RX_SERIAL
        or receipt.get("sample_rate_hz") != profile.rate_hz
        or receipt.get("scan_offset_order_hz") != list(v3.OFFSET_ORDER_HZ)
        or not isinstance(geometry, dict)
        or geometry != v3._scan_geometry(geometry.get("on_channel_if_hz"))
        or receipt.get("policy") != {"coarse": COARSE_POLICY, "fine": FINE_POLICY}
        or not isinstance(receiver, dict)
        or set(receiver) != {"transport", "uri", "firmware", "original", "selected"}
        or receiver.get("transport") != "ethernet"
        or receiver.get("uri") != v2.ETHERNET_URI
        or receiver.get("firmware") != profile.firmware
        or not isinstance(selected, dict)
        or selected.get("phy_rate") != profile.rate_hz
        or selected.get("adc_rate") != profile.rate_hz
        or selected.get("bandwidth") != v2.RX_BANDWIDTH_HZ
        or selected.get("gain_mode") != "slow_attack"
        or selected.get("lo") != geometry["on_channel_if_hz"]
        or selected.get("lo_powerdown") != 0
        or not isinstance(scan, dict)
        or not isinstance(points, list)
        or not 1 <= len(points) <= len(v3.OFFSET_ORDER_HZ)
        or not isinstance(stream, dict)
        or not isinstance(gates, dict)
        or set(gates) != GATE_FIELDS
        or any(value is not True for value in gates.values())
        or not isinstance(cleanup, dict)
        or cleanup.get("verified") is not True
        or cleanup.get("errors") != []
        or cleanup.get("rx_restored") != receiver.get("original")
        or not isinstance(fine, dict)
        or not isinstance(brackets, list)
        or not isinstance(receipt.get("deployment"), dict)
        or set(receipt["deployment"]) != v3.DEPLOYMENT_FIELDS
    ):
        raise QualificationError("native live fine root contract differs")
    v2._validate_source_commit(
        receipt.get("firmware_source_commit"), label="firmware source commit"
    )
    v2._validate_source_commit(
        receipt.get("ppu_source_commit"), label="PPU source commit"
    )
    coefficients = receipt.get("coefficients")
    matched_coefficient = (
        coefficients.get("matched") if isinstance(coefficients, dict) else None
    )
    mismatch_coefficient = (
        coefficients.get("mismatch") if isinstance(coefficients, dict) else None
    )
    if (
        not isinstance(coefficients, dict)
        or set(coefficients) != {"matched", "mismatch"}
        or not isinstance(matched_coefficient, dict)
        or set(matched_coefficient) != {"path", "sha256", "energy"}
        or not isinstance(matched_coefficient.get("path"), str)
        or not isinstance(mismatch_coefficient, dict)
        or set(mismatch_coefficient)
        != {"path", "sha256", "energy", "evidence", "construction"}
        or not isinstance(mismatch_coefficient.get("path"), str)
        or matched_coefficient.get("sha256") != profile.coefficient_sha256
        or mismatch_coefficient.get("sha256") != CONTROL_SHA256
        or matched_coefficient.get("energy") != COEFFICIENT_ENERGY
        or mismatch_coefficient.get("energy") != COEFFICIENT_ENERGY
        or mismatch_coefficient.get("evidence") != _identity(CONTROL_EVIDENCE_PATH)
        or _sha256(Path(matched_coefficient["path"])) != profile.coefficient_sha256
        or _sha256(Path(mismatch_coefficient["path"])) != CONTROL_SHA256
    ):
        raise QualificationError("native live fine coefficient contract differs")
    _load_control_evidence()

    previous_generation: int | None = None
    previous_start: int | None = None
    for ordinal, point in enumerate(points, 1):
        previous_generation, previous_start = v3._validate_point(
            point,
            role=TRIGGER_ROLE,
            ordinal=ordinal,
            base_if_hz=geometry["on_channel_if_hz"],
            rate_msps=rate_msps,
            previous_generation=previous_generation,
            previous_start=previous_start,
        )
    positive_ordinals = [
        index
        for index, point in enumerate(points, 1)
        if point["metrics"]["classification"] == "positive_track"
    ]
    trigger_ordinal = scan.get("trigger_point_ordinal")
    if (
        (positive_ordinals and positive_ordinals != [len(points)])
        or trigger_ordinal != (positive_ordinals[0] if positive_ordinals else None)
        or (not positive_ordinals and len(points) != len(v3.OFFSET_ORDER_HZ))
    ):
        raise QualificationError("coarse trigger stopping rule differs")

    expected_maps = len(points) * v3.MAPS_PER_POINT
    final_maps = stream.get("final_map_counters")
    initial_maps = stream.get("initial_map_counters")
    final_fine = stream.get("final_fine_counters")
    initial_fine = stream.get("initial_fine_counters")
    expected_packets = (
        BRACKET_COUNT * len(BRACKET_ROLES) * RESULTS_PER_BLOCK
        if positive_ordinals
        else 0
    )
    if (
        stream.get("complete_maps") != expected_maps
        or stream.get("logical_map_bytes") != expected_maps * FRAME_SAMPLES * 2
        or stream.get("map_transport_bytes")
        != expected_maps * MAP_CHUNKS * MAP_SCAN_BYTES
        or stream.get("fine_packets") != expected_packets
        or stream.get("fine_transport_bytes") != expected_packets * 128
        or not isinstance(initial_maps, dict)
        or initial_maps.get("maps_delivered") != 0
        or initial_maps.get("chunks_delivered") != 0
        or not isinstance(final_maps, dict)
        or final_maps.get("maps_delivered") != expected_maps
        or final_maps.get("chunks_delivered") != expected_maps * PSS_MAP_CHUNKS
        or not isinstance(initial_fine, dict)
        or initial_fine.get("packets_delivered") != 0
        or not isinstance(final_fine, dict)
        or final_fine.get("packets_delivered") != expected_packets
        or final_fine.get("schedule_submitted")
        != (RESULTS_PER_BLOCK if positive_ordinals else 0)
        or final_fine.get("active_coefficient_generation")
        != (
            _generation(BRACKET_COUNT - 1, len(BRACKET_ROLES) - 1)
            if positive_ordinals
            else profile.coefficient_generation
        )
        or any(
            final_maps.get(key) != 0
            for key in (
                "map_buffer_push_failures",
                "map_fault_flags",
                "tracker_buffer_push_failures",
                "tracker_packet_validation_failures",
                "tracker_fault_flags",
            )
        )
        or any(
            final_fine.get(key) != 0
            for key in (
                "buffer_push_failures",
                "packet_validation_failures",
                "fault_flags",
            )
        )
    ):
        raise QualificationError("native live fine stream accounting differs")

    if positive_ordinals:
        expected_anchor, expected_period = _last_passing_anchor(points[-1])
        if (
            len(brackets) != BRACKET_COUNT
            or set(fine)
            != {"seed_anchor_source", "seed_period_source", "brackets", "evaluation"}
            or fine.get("seed_anchor_source") != expected_anchor
            or fine.get("seed_period_source") != expected_period
        ):
            raise QualificationError("fine bracket count differs")
        for bracket_index, bracket in enumerate(brackets):
            blocks = bracket.get("blocks") if isinstance(bracket, dict) else None
            if (
                not isinstance(bracket, dict)
                or set(bracket) != {"ordinal", "blocks", "evaluation"}
                or bracket.get("ordinal") != bracket_index + 1
                or not isinstance(blocks, dict)
                or set(blocks) != set(BRACKET_ROLES)
            ):
                raise QualificationError("fine bracket root contract differs")
            for role_index, role in enumerate(BRACKET_ROLES):
                _validate_block(
                    blocks[role],
                    profile=profile,
                    role=role,
                    bracket_index=bracket_index,
                    role_index=role_index,
                )
            if bracket.get("evaluation") != evaluate_bracket(blocks, profile=profile):
                raise QualificationError("fine bracket evaluation differs from replay")
        passing = [
            bracket["ordinal"]
            for bracket in brackets
            if bracket["evaluation"]["qualified"]
        ]
        fine_evaluation = {
            "qualified": len(passing) >= FINE_POLICY["minimum_qualifying_brackets"],
            "qualifying_bracket_ordinals": passing,
            "qualifying_bracket_count": len(passing),
        }
        if fine.get("evaluation") != fine_evaluation:
            raise QualificationError("fine campaign evaluation differs from replay")
    elif fine != {"brackets": [], "evaluation": {"qualified": False}}:
        raise QualificationError("fine output exists without a coarse trigger")

    qualified = bool(fine["evaluation"]["qualified"])
    if (
        receipt.get("pss_detected") is not bool(positive_ordinals)
        or receipt.get("fine_timing_qualified") is not qualified
        or receipt.get("sss_detected") is not False
        or receipt.get("frame_lock_claim") is not False
    ):
        raise QualificationError("native live fine claims differ from replay")
    analysis = {
        "schema": ANALYSIS_SCHEMA,
        "schema_version": 1,
        "outcome": "pass",
        "hardware_accessed": False,
        "persistent_write": False,
        "source_receipt": _identity(receipt_path),
        "serial": RX_SERIAL,
        "rate_msps": rate_msps,
        "trigger_point_ordinal": trigger_ordinal,
        "trigger_offset_hz": points[-1]["offset_hz"] if positive_ordinals else None,
        "fine_evaluation": fine["evaluation"],
        "pss_detected": bool(positive_ordinals),
        "fine_timing_qualified": qualified,
        "sss_detected": False,
        "frame_lock_claim": False,
    }
    identity = _write_new(output, analysis)
    return {"analysis": identity, **analysis}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    execute = commands.add_parser(
        "run", help="run one live coarse-triggered fine campaign"
    )
    execute.add_argument("--rate-msps", type=int, choices=(30,), default=30)
    execute.add_argument("--on-if-hz", type=int, default=1_937_500_000)
    execute.add_argument("--deployment-receipt", type=Path, required=True)
    execute.add_argument("--known-hosts-file", type=Path, required=True)
    execute.add_argument("--reboot-receipt", type=Path, action="append", default=[])
    execute.add_argument("--firmware-source-commit", required=True)
    execute.add_argument("--ppu-source-commit", required=True)
    execute.add_argument("output", type=Path)
    verify = commands.add_parser("replay", help="independently replay one fine receipt")
    verify.add_argument("--receipt", type=Path, required=True)
    verify.add_argument("--output", type=Path, required=True)
    return result


def main() -> int:
    arguments = parser().parse_args()
    try:
        if arguments.command == "run":
            result = run(
                arguments.output,
                profile=RATE_PROFILES[arguments.rate_msps],
                on_if_hz=arguments.on_if_hz,
                deployment_receipt=arguments.deployment_receipt,
                known_hosts_file=arguments.known_hosts_file,
                reboot_receipts=arguments.reboot_receipt,
                firmware_source_commit=arguments.firmware_source_commit,
                ppu_source_commit=arguments.ppu_source_commit,
            )
        else:
            result = replay(receipt_path=arguments.receipt, output=arguments.output)
    except BaseException as error:  # noqa: BLE001
        print(json.dumps({"outcome": "failed", "error": str(error)}, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "outcome": result["outcome"],
                "rate_msps": result["rate_msps"],
                "pss_detected": result["pss_detected"],
                "fine_timing_qualified": result["fine_timing_qualified"],
                "sss_detected": result["sss_detected"],
                "frame_lock_claim": result["frame_lock_claim"],
                "receipt": result.get("receipt"),
                "analysis": result.get("analysis"),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

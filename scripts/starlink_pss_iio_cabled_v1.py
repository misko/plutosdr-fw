#!/usr/bin/env python3
"""Qualify native PSS IIO maps and fine packets on the fixed cabled fixture.

This guarded runner is intentionally bound to the allocated .17 receiver and
the .18 transmitter through the declared 30 dB attenuator.  Firmware is loaded
and recovered separately; this runner never writes persistent radio storage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
from contextlib import ExitStack, nullcontext
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PPU = Path("/home/mouse9911/gits/pluto-plus-utils")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(PPU / "src") not in sys.path:
    sys.path.insert(0, str(PPU / "src"))

import iio
from pluto_plus.hardware.iio import exact_usb_iio_uri
from pluto_plus.hardware.pss_iio import (
    PssCoarseEstimate,
    PssFinePacket,
    PssIioClient,
    PssMapReassembler,
    PssPhaseMap,
    analyze_phase_maps,
)
from pluto_plus.radio_lock import acquire_radio_lock

from scripts.starlink_pss_m3_iio_tx_v1 import DAC_SELECT_ZERO
from scripts.starlink_pss_m3_iio_tx_v2 import (
    close_iio_context,
    load_exact_payload,
)
from scripts.starlink_pss_m8_cabled_v1 import (
    PhaseContinuousSingleTx as _PhaseContinuousSingleTx,
)

RX_SERIAL = "104000bac4950008230026001b440a003a"
TX_SERIAL = "1040007c4a94000211000b009186843ef2"
RX_TOPOLOGY = "5-2"
TX_TOPOLOGY = "3-11"
LO_HZ = 2_400_000_000


@dataclass(frozen=True, slots=True)
class RateProfile:
    """Immutable source-rate contract for one cabled qualification."""

    rate_msps: int
    firmware: str
    bandwidth_hz: int
    period_samples: int
    aperture_samples: int
    host_lead_samples: int
    coefficient_generation: int
    coefficient_path: Path
    coefficient_sha256: str
    waveform_path: Path
    waveform_sha256: str
    waveform_bytes: int

    @property
    def rate_hz(self) -> int:
        return self.rate_msps * 1_000_000

    @property
    def request_prefix(self) -> int:
        return 0x80000000 | (self.rate_msps << 20)


RATE_PROFILES = {
    30: RateProfile(
        rate_msps=30,
        firmware="starlink-pss30-iio-v1-dnm",
        bandwidth_hz=20_000_000,
        period_samples=40_000,
        aperture_samples=60,
        host_lead_samples=6_000_000,
        coefficient_generation=0x30000017,
        coefficient_path=Path(
            "/home/mouse9911/pluto-state/starlink-rx-only-dnm/"
            "m6-30-native-iio-20260907/coefficients/"
            "starlink_pss30_upper_+0.000hz_coefficients_q15.mem"
        ),
        coefficient_sha256=(
            "547aaae167be8c1b410adf5189b0e6f67b9ad26c6a5c68f072b959b833be3ec5"
        ),
        waveform_path=Path(
            "/home/mouse9911/pluto-state/starlink-rx-only-dnm/m5-live-20260907/"
            "candidate-30-v9/cabled-smoke-v1/waveform/"
            "starlink_pss30_upper_cabled_ci16le.bin"
        ),
        waveform_sha256=(
            "ee13cf9d3214104c506944ef7ebe68e00aef17e8817fb9c961e907a6ac15619c"
        ),
        waveform_bytes=160_000,
    ),
    60: RateProfile(
        rate_msps=60,
        firmware="starlink-pss-iio-v5-dnm",
        bandwidth_hz=20_000_000,
        period_samples=80_000,
        aperture_samples=120,
        host_lead_samples=12_000_000,
        coefficient_generation=0x60000016,
        coefficient_path=Path(
            "/home/mouse9911/pluto-state/starlink-rx-only-dnm/iio-v5-20260907/"
            "candidate/starlink_pss60_upper_+0.000hz_coefficients_q15.mem"
        ),
        coefficient_sha256=(
            "6aed4f4883fce03982f12af0d28ea9186599daa5564e045cb9bc636c1fef3289"
        ),
        waveform_path=Path(
            "/home/mouse9911/pluto-state/starlink-rx-only-dnm/m6-live-20260907/"
            "candidate-60-v10/cabled-v1/waveform/"
            "starlink_pss60_upper_cabled_ci16le.bin"
        ),
        waveform_sha256=(
            "be24d054510c8d5ec7bb5d122d8a0604e2d3c742f00cb2582de312a40611458f"
        ),
        waveform_bytes=320_000,
    ),
}


class QualificationError(RuntimeError):
    """The fixed cabled qualification failed a required contract."""


class PhaseContinuousSingleTx(_PhaseContinuousSingleTx):
    """Retain phase gating and make final zero selection survive buffer release."""

    def mute(self) -> dict[str, Any]:
        evidence = super().mute()
        # Legacy buffer destruction can restore the DDS selector after the base
        # mute readback. Reassert ZERO only after that destruction is complete.
        evidence["selector_i"] = self._write_selector(0, DAC_SELECT_ZERO)
        evidence["selector_q"] = self._write_selector(1, DAC_SELECT_ZERO)
        evidence["selectors_verified_after_buffer_release"] = True
        return evidence


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _attribute(owner: Any, name: str) -> Any:
    attrs = getattr(owner, "attrs", {})
    if name not in attrs:
        raise QualificationError(f"IIO object lacks required attribute {name!r}")
    return attrs[name]


def _number(owner: Any, name: str) -> int:
    try:
        return round(float(str(_attribute(owner, name).value).strip().split()[0]))
    except (IndexError, TypeError, ValueError) as error:
        raise QualificationError(f"invalid IIO numeric readback for {name}") from error


def _write_number(owner: Any, name: str, value: int, tolerance: float) -> int:
    _attribute(owner, name).value = str(value)
    observed = _number(owner, name)
    if abs(observed - value) > tolerance:
        raise QualificationError(f"{name} readback {observed} differs from {value}")
    return observed


def _required_channel(device: Any, name: str, output: bool) -> Any:
    channel = device.find_channel(name, output)
    if channel is None:
        raise QualificationError(f"missing IIO channel {name!r}, output={output}")
    return channel


def _future_center(
    anchor: float, current: int, period: float, *, host_lead_samples: int
) -> int:
    target = current + host_lead_samples
    steps = max(0, math.ceil((target - anchor) / period))
    center = round(anchor + steps * period)
    while center < target:
        steps += 1
        center = round(anchor + steps * period)
    return center


def _packet_document(packet: PssFinePacket, ordinal: int) -> dict[str, Any]:
    return {
        "ordinal": ordinal,
        "request_id": packet.request_id,
        "center_index": packet.center_index,
        "center_timestamp": packet.center_timestamp,
        "winner_lag": packet.lag,
        "winner_timestamp": packet.winner_timestamp,
        "coefficient_generation": packet.coefficient_generation,
        "correlation_real": packet.correlation_real,
        "correlation_imag": packet.correlation_imag,
        "sample_energy": packet.sample_energy,
        "coefficient_energy": packet.coefficient_energy,
        "saturation_events": packet.saturation_events,
        "packet_words": [f"0x{word:08x}" for word in packet.words],
    }


def _analyze(
    results: list[dict[str, Any]], *, period_samples: int, aperture_samples: int
) -> dict[str, Any]:
    if len(results) < 2:
        raise QualificationError("fine result set is too short")
    xs = [float(item["ordinal"]) for item in results]
    ys = [float(item["winner_timestamp"]) for item in results]
    x_mean = statistics.fmean(xs)
    y_mean = statistics.fmean(ys)
    denominator = sum((value - x_mean) ** 2 for value in xs)
    slope = (
        sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys, strict=True))
        / denominator
    )
    intercept = y_mean - slope * x_mean
    residuals = [y - (intercept + slope * x) for x, y in zip(xs, ys, strict=True)]
    lags = [int(item["winner_lag"]) for item in results]
    scores = []
    for item in results:
        real = int(item["correlation_real"])
        imag = int(item["correlation_imag"])
        energy = int(item["sample_energy"]) * int(item["coefficient_energy"])
        scores.append((real * real + imag * imag) / energy)
    return {
        "count": len(results),
        "fitted_period_source_samples": slope,
        "relative_clock_error_ppm": (slope / period_samples - 1.0) * 1e6,
        "residual_max_abs_source_samples": max(abs(value) for value in residuals),
        "residual_rms_source_samples": math.sqrt(
            statistics.fmean(x * x for x in residuals)
        ),
        "winner_lag_min": min(lags),
        "winner_lag_median": statistics.median(lags),
        "winner_lag_max": max(lags),
        "aperture_edge_hits": sum(abs(value) == aperture_samples for value in lags),
        "normalized_score_min": min(scores),
        "normalized_score_median": statistics.median(scores),
        "normalized_score_max": max(scores),
    }


def _coarse_document(estimate: PssCoarseEstimate) -> dict[str, Any]:
    return asdict(estimate)


def _read_maps(
    client: PssIioClient,
    reassembler: PssMapReassembler,
    count: int,
) -> list[PssPhaseMap]:
    maps: list[PssPhaseMap] = []
    while len(maps) < count:
        maps.extend(client.read_maps(reassembler))
    if len(maps) != count:
        raise QualificationError("map refill crossed a role boundary")
    return maps


def _read_fine(
    client: PssIioClient,
    *,
    first_center: int,
    request_base: int,
    count: int,
    period: float,
) -> list[dict[str, Any]]:
    client.open_fine(
        first_center=first_center,
        period_q32_32=round(period * (1 << 32)),
        request_base=request_base,
        count=count,
        queue_target=7,
        refill_results=min(16, count),
    )
    packets: list[PssFinePacket] = []
    try:
        while len(packets) < count:
            packets.extend(client.read_fine())
    finally:
        client.close_fine()
    if len(packets) != count:
        raise QualificationError("fine IIO stream returned the wrong packet count")
    return [_packet_document(packet, ordinal) for ordinal, packet in enumerate(packets)]


def _current_index(client: PssIioClient) -> int:
    return _number(client.tracker, "current_index")


def _refine(
    client: PssIioClient,
    *,
    profile: RateProfile,
    anchor: float,
    period: float,
    request_id: int,
) -> dict[str, Any]:
    center = _future_center(
        anchor,
        _current_index(client),
        period,
        host_lead_samples=profile.host_lead_samples,
    )
    return _read_fine(
        client,
        first_center=center,
        request_base=request_id,
        count=1,
        period=period,
    )[0]


def _configure_rx(
    client: PssIioClient, profile: RateProfile
) -> tuple[dict[str, Any], dict[str, Any]]:
    context = client.context
    setter = getattr(context, "set_timeout", None)
    if not callable(setter):
        raise QualificationError("RX context cannot set a bounded timeout")
    setter(5_000)
    attrs = {str(key): str(value) for key, value in context.attrs.items()}
    phy = context.find_device("ad9361-phy")
    adc = context.find_device("cf-ad9361-lpc")
    if (
        attrs.get("hw_serial") != RX_SERIAL
        or attrs.get("fw_version") != profile.firmware
        or client.rate_msps != profile.rate_msps
        or phy is None
        or adc is None
        or context.find_device("cf-ad9361-dds-core-lpc") is not None
    ):
        raise QualificationError(
            "RX identity, firmware, or detector-only layout differs"
        )
    phy_rx = _required_channel(phy, "voltage0", False)
    capture_rx = _required_channel(adc, "voltage0", False)
    rx_lo = _required_channel(phy, "altvoltage0", True)
    before = {
        "phy_rate": _number(phy_rx, "sampling_frequency"),
        "adc_rate": _number(capture_rx, "sampling_frequency"),
        "bandwidth": _number(phy_rx, "rf_bandwidth"),
        "gain_mode": str(_attribute(phy_rx, "gain_control_mode").value),
        "lo": _number(rx_lo, "frequency"),
        "lo_powerdown": _number(rx_lo, "powerdown"),
    }
    selected = {
        "phy_rate": _write_number(
            phy_rx, "sampling_frequency", profile.rate_hz, profile.rate_hz * 100e-6
        ),
        "adc_rate": _write_number(
            capture_rx,
            "sampling_frequency",
            profile.rate_hz,
            profile.rate_hz * 100e-6,
        ),
        "bandwidth": _write_number(phy_rx, "rf_bandwidth", profile.bandwidth_hz, 2),
        "lo": _write_number(rx_lo, "frequency", LO_HZ, 2),
        "lo_powerdown": _write_number(rx_lo, "powerdown", 0, 0),
    }
    _attribute(phy_rx, "gain_control_mode").value = "slow_attack"
    selected["gain_mode"] = str(_attribute(phy_rx, "gain_control_mode").value)
    if selected != {
        "phy_rate": profile.rate_hz,
        "adc_rate": profile.rate_hz,
        "bandwidth": profile.bandwidth_hz,
        "gain_mode": "slow_attack",
        "lo": LO_HZ,
        "lo_powerdown": 0,
    }:
        raise QualificationError("RX selected setting readback differs")
    time.sleep(2.0)
    return before, selected


def _restore_rx(client: PssIioClient, before: dict[str, Any]) -> dict[str, Any]:
    phy = client.context.find_device("ad9361-phy")
    adc = client.context.find_device("cf-ad9361-lpc")
    if phy is None or adc is None:
        raise QualificationError("RX devices disappeared before restore")
    phy_rx = _required_channel(phy, "voltage0", False)
    capture_rx = _required_channel(adc, "voltage0", False)
    rx_lo = _required_channel(phy, "altvoltage0", True)
    restored = {
        "phy_rate": _write_number(
            phy_rx, "sampling_frequency", int(before["phy_rate"]), 2
        ),
        "adc_rate": _write_number(
            capture_rx, "sampling_frequency", int(before["adc_rate"]), 2
        ),
        "bandwidth": _write_number(phy_rx, "rf_bandwidth", int(before["bandwidth"]), 2),
        "lo": _write_number(rx_lo, "frequency", int(before["lo"]), 2),
        "lo_powerdown": _write_number(
            rx_lo, "powerdown", int(before["lo_powerdown"]), 0
        ),
    }
    _attribute(phy_rx, "gain_control_mode").value = str(before["gain_mode"])
    restored["gain_mode"] = str(_attribute(phy_rx, "gain_control_mode").value)
    if restored != before:
        raise QualificationError("RX restore readback differs from original settings")
    return restored


def run(output: Path, *, profile: RateProfile) -> dict[str, Any]:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    payload = load_exact_payload(
        profile.waveform_path,
        expected_bytes=profile.waveform_bytes,
        expected_sha256=profile.waveform_sha256,
    )
    if (
        hashlib.sha256(profile.coefficient_path.read_bytes()).hexdigest()
        != profile.coefficient_sha256
    ):
        raise QualificationError("coefficient file identity differs")
    receipt: dict[str, Any] = {
        "schema": "plutosdr-fw.starlink-pss-native-iio-cabled.v2",
        "started_at": _now(),
        "outcome": "started",
        "persistent_write": False,
        "rate_msps": profile.rate_msps,
        "sample_rate_hz": profile.rate_hz,
        "period_source_samples": profile.period_samples,
        "fixture": {
            "path": ".18 TX1 -> exact 30 dB attenuator -> .17 RX1",
            "antennas": False,
            "attenuation_db": 30,
        },
        "receiver": {"serial": RX_SERIAL, "topology": RX_TOPOLOGY, "port": "RX1"},
        "transmitter": {"serial": TX_SERIAL, "topology": TX_TOPOLOGY, "port": "TX1"},
        "coefficient": {
            "path": str(profile.coefficient_path),
            "sha256": profile.coefficient_sha256,
            "generation": profile.coefficient_generation,
            "file_layout": "I-high-Q-low",
            "fpga_register_layout": "Q-high-I-low",
        },
        "waveform": {
            "path": str(profile.waveform_path),
            "sha256": profile.waveform_sha256,
        },
        "roles": {},
        "cleanup": {"errors": []},
    }
    client: PssIioClient | None = None
    tx_context: Any = None
    tx: PhaseContinuousSingleTx | None = None
    before: dict[str, Any] | None = None
    body_error: BaseException | None = None
    lock_stack = ExitStack()
    try:
        lock_stack.enter_context(acquire_radio_lock(RX_SERIAL))
        lock_stack.enter_context(acquire_radio_lock(TX_SERIAL))
        with nullcontext():
            rx_uri = exact_usb_iio_uri(
                Path("/sys/bus/usb/devices") / RX_TOPOLOGY, RX_SERIAL
            )
            tx_uri = exact_usb_iio_uri(
                Path("/sys/bus/usb/devices") / TX_TOPOLOGY, TX_SERIAL
            )
            client = PssIioClient.connect(rx_uri, expected_serial=RX_SERIAL)
            before, selected = _configure_rx(client, profile)
            receipt["receiver"].update(
                {
                    "uri": rx_uri,
                    "firmware": profile.firmware,
                    "original": before,
                    "selected": selected,
                }
            )
            client.load_coefficient_file(
                profile.coefficient_path, generation=profile.coefficient_generation
            )
            receipt["coefficient"]["active_generation"] = _number(
                client.tracker, "active_coefficient_generation"
            )

            tx_context = iio.Context(tx_uri)
            tx = PhaseContinuousSingleTx(iio, tx_context, expected_serial=TX_SERIAL)
            tx_context = None
            receipt["transmitter"]["uri"] = tx_uri
            receipt["transmitter"]["initial_mute"] = tx.mute()
            receipt["transmitter"]["configuration"] = tx.configure(
                sample_rate_hz=profile.rate_hz,
                rf_bandwidth_hz=profile.bandwidth_hz,
                tx_lo_hz=LO_HZ,
            )

            reassembler = PssMapReassembler()
            client.open_maps(refill_chunks=200)
            baseline_maps = _read_maps(client, reassembler, 3)
            baseline = analyze_phase_maps(baseline_maps, rate_msps=profile.rate_msps)
            receipt["roles"]["muted_coarse"] = _coarse_document(baseline)
            receipt["transmitter"]["positive_start"] = tx.start(payload, gain_db=-30.0)
            transition_maps = _read_maps(client, reassembler, 3)
            positive_maps = _read_maps(client, reassembler, 3)
            positive_coarse = analyze_phase_maps(
                positive_maps, rate_msps=profile.rate_msps
            )
            receipt["roles"]["transition_map_generations"] = [
                phase_map.generation for phase_map in transition_maps
            ]
            receipt["roles"]["positive_coarse"] = _coarse_document(positive_coarse)
            client.close_maps()

            probe_a = _refine(
                client,
                profile=profile,
                anchor=float(positive_coarse.candidate_start_index_source_center),
                period=positive_coarse.estimated_frame_period_source_samples,
                request_id=profile.request_prefix | 0x100001,
            )
            first_a = _future_center(
                float(probe_a["winner_timestamp"]),
                _current_index(client),
                profile.period_samples,
                host_lead_samples=profile.host_lead_samples,
            )
            results_a = _read_fine(
                client,
                first_center=first_a,
                request_base=profile.request_prefix | 0x110000,
                count=128,
                period=profile.period_samples,
            )
            analysis_a = _analyze(
                results_a,
                period_samples=profile.period_samples,
                aperture_samples=profile.aperture_samples,
            )
            receipt["roles"]["positive_a"] = {
                "refinement_probe": probe_a,
                "results": results_a,
                "analysis": analysis_a,
            }

            receipt["transmitter"]["control_gate"] = tx.gate_preserving_cycle()
            time.sleep(0.25)
            first_control = _future_center(
                float(results_a[-1]["winner_timestamp"]),
                _current_index(client),
                float(analysis_a["fitted_period_source_samples"]),
                host_lead_samples=profile.host_lead_samples,
            )
            control_results = _read_fine(
                client,
                first_center=first_control,
                request_base=profile.request_prefix | 0x120000,
                count=64,
                period=float(analysis_a["fitted_period_source_samples"]),
            )
            control_analysis = _analyze(
                control_results,
                period_samples=profile.period_samples,
                aperture_samples=profile.aperture_samples,
            )
            receipt["roles"]["muted_control"] = {
                "results": control_results,
                "analysis": control_analysis,
            }

            receipt["transmitter"]["positive_b_resume"] = tx.resume_preserved_cycle(
                gain_db=-30.0
            )
            time.sleep(0.25)
            probe_b = _refine(
                client,
                profile=profile,
                anchor=float(results_a[-1]["winner_timestamp"]),
                period=float(analysis_a["fitted_period_source_samples"]),
                request_id=profile.request_prefix | 0x130001,
            )
            first_b = _future_center(
                float(probe_b["winner_timestamp"]),
                _current_index(client),
                profile.period_samples,
                host_lead_samples=profile.host_lead_samples,
            )
            results_b = _read_fine(
                client,
                first_center=first_b,
                request_base=profile.request_prefix | 0x140000,
                count=128,
                period=profile.period_samples,
            )
            analysis_b = _analyze(
                results_b,
                period_samples=profile.period_samples,
                aperture_samples=profile.aperture_samples,
            )
            receipt["roles"]["positive_b"] = {
                "refinement_probe": probe_b,
                "results": results_b,
                "analysis": analysis_b,
            }

            final_tx_mute = tx.close()
            tx = None
            receipt["cleanup"]["tx_final_mute"] = final_tx_mute
            tracker_fault = _number(client.tracker, "fault_flags")
            map_fault = _number(client.phase_map, "fault_flags")
            gates = {
                "positive_coarse_exceeds_muted": positive_coarse.peak_to_median
                > 2.0 * baseline.peak_to_median,
                "positive_a_score_exceeds_control_5x": analysis_a[
                    "normalized_score_median"
                ]
                > 5.0 * control_analysis["normalized_score_median"],
                "positive_b_score_exceeds_control_5x": analysis_b[
                    "normalized_score_median"
                ]
                > 5.0 * control_analysis["normalized_score_median"],
                "positive_a_period_within_one_sample": abs(
                    analysis_a["fitted_period_source_samples"] - profile.period_samples
                )
                <= 1.0,
                "positive_b_period_within_one_sample": abs(
                    analysis_b["fitted_period_source_samples"] - profile.period_samples
                )
                <= 1.0,
                "positive_a_residual_within_one_sample": analysis_a[
                    "residual_max_abs_source_samples"
                ]
                <= 1.0,
                "positive_b_residual_within_one_sample": analysis_b[
                    "residual_max_abs_source_samples"
                ]
                <= 1.0,
                "positive_a_no_aperture_edges": analysis_a["aperture_edge_hits"] == 0,
                "positive_b_no_aperture_edges": analysis_b["aperture_edge_hits"] == 0,
                "map_fault_free": map_fault == 0,
                "tracker_fault_free": tracker_fault == 0,
                "map_push_failure_free": _number(
                    client.phase_map, "buffer_push_failures"
                )
                == 0,
                "fine_push_failure_free": _number(
                    client.tracker, "buffer_push_failures"
                )
                == 0,
                "fine_validation_failure_free": _number(
                    client.tracker, "packet_validation_failures"
                )
                == 0,
                "tx_final_mute_verified": final_tx_mute.get("verified") is True,
            }
            receipt["gates"] = gates
            failed = [name for name, passed in gates.items() if not passed]
            if failed:
                raise QualificationError(f"native-IIO cabled gates failed: {failed}")
            receipt["outcome"] = "pass"
    except BaseException as error:  # noqa: BLE001 - receipt every hardware outcome
        body_error = error
        receipt["outcome"] = "failed"
        receipt["error"] = f"{type(error).__name__}: {error}"
    finally:
        cleanup_errors: list[str] = receipt["cleanup"]["errors"]
        if tx is not None:
            try:
                receipt["cleanup"]["tx_final_mute_after_error"] = tx.close()
            except BaseException as error:  # noqa: BLE001 - continue fail-safe cleanup
                cleanup_errors.append(f"TX final mute/close: {error}")
        elif tx_context is not None:
            try:
                receipt["cleanup"]["tx_context_release"] = close_iio_context(
                    iio, tx_context
                )
            except BaseException as error:  # noqa: BLE001 - continue fail-safe cleanup
                cleanup_errors.append(f"TX context close: {error}")
        if client is not None:
            try:
                client.close_fine()
                client.close_maps()
            except BaseException as error:  # noqa: BLE001 - continue fail-safe cleanup
                cleanup_errors.append(f"RX stream close: {error}")
            if before is not None:
                try:
                    receipt["cleanup"]["rx_restored"] = _restore_rx(client, before)
                except BaseException as error:  # noqa: BLE001 - continue cleanup
                    cleanup_errors.append(f"RX restore: {error}")
            try:
                client.close()
            except BaseException as error:  # noqa: BLE001 - continue fail-safe cleanup
                cleanup_errors.append(f"RX context close: {error}")
        receipt["cleanup"]["verified"] = not cleanup_errors
        if cleanup_errors:
            receipt["outcome"] = "failed"
        receipt["completed_at"] = _now()
        lock_stack.close()
        receipt_path = output / "run-receipt.json"
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        receipt["receipt"] = str(receipt_path)
    if body_error is not None:
        raise body_error
    if receipt["outcome"] != "pass":
        raise QualificationError("native-IIO cleanup did not verify")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rate-msps", type=int, choices=tuple(RATE_PROFILES), default=60
    )
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    try:
        receipt = run(arguments.output, profile=RATE_PROFILES[arguments.rate_msps])
    except BaseException as error:  # noqa: BLE001 - report guarded interruption
        print(
            json.dumps(
                {"outcome": "failed", "error": f"{type(error).__name__}: {error}"}
            )
        )
        return 2
    print(
        json.dumps(
            {
                "outcome": receipt["outcome"],
                "receipt": receipt["receipt"],
                "gates": receipt["gates"],
                "muted_coarse": receipt["roles"]["muted_coarse"],
                "positive_coarse": receipt["roles"]["positive_coarse"],
                "positive_a": receipt["roles"]["positive_a"]["analysis"],
                "muted_control": receipt["roles"]["muted_control"]["analysis"],
                "positive_b": receipt["roles"]["positive_b"]["analysis"],
                "cleanup": receipt["cleanup"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
from dataclasses import asdict
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
RX_FIRMWARE = "starlink-pss-iio-v5-dnm"
RATE_HZ = 60_000_000
RATE_MSPS = 60
BANDWIDTH_HZ = 20_000_000
LO_HZ = 2_400_000_000
PERIOD_SAMPLES = 80_000
APERTURE_SAMPLES = 120
HOST_LEAD_SAMPLES = 12_000_000
COEFFICIENT_GENERATION = 0x60000016
COEFFICIENT_PATH = Path(
    "/home/mouse9911/pluto-state/starlink-rx-only-dnm/iio-v5-20260907/"
    "candidate/starlink_pss60_upper_+0.000hz_coefficients_q15.mem"
)
COEFFICIENT_SHA256 = "6aed4f4883fce03982f12af0d28ea9186599daa5564e045cb9bc636c1fef3289"
WAVEFORM_PATH = Path(
    "/home/mouse9911/pluto-state/starlink-rx-only-dnm/m6-live-20260907/"
    "candidate-60-v10/cabled-v1/waveform/starlink_pss60_upper_cabled_ci16le.bin"
)
WAVEFORM_SHA256 = "be24d054510c8d5ec7bb5d122d8a0604e2d3c742f00cb2582de312a40611458f"


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


def _future_center(anchor: float, current: int, period: float) -> int:
    target = current + HOST_LEAD_SAMPLES
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


def _analyze(results: list[dict[str, Any]]) -> dict[str, Any]:
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
        "relative_clock_error_ppm": (slope / PERIOD_SAMPLES - 1.0) * 1e6,
        "residual_max_abs_source_samples": max(abs(value) for value in residuals),
        "residual_rms_source_samples": math.sqrt(
            statistics.fmean(x * x for x in residuals)
        ),
        "winner_lag_min": min(lags),
        "winner_lag_median": statistics.median(lags),
        "winner_lag_max": max(lags),
        "aperture_edge_hits": sum(abs(value) == APERTURE_SAMPLES for value in lags),
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
    period: float = PERIOD_SAMPLES,
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
    anchor: float,
    period: float,
    request_id: int,
) -> dict[str, Any]:
    center = _future_center(anchor, _current_index(client), period)
    return _read_fine(
        client,
        first_center=center,
        request_base=request_id,
        count=1,
        period=period,
    )[0]


def _configure_rx(client: PssIioClient) -> tuple[dict[str, Any], dict[str, Any]]:
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
        or attrs.get("fw_version") != RX_FIRMWARE
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
            phy_rx, "sampling_frequency", RATE_HZ, RATE_HZ * 100e-6
        ),
        "adc_rate": _write_number(
            capture_rx, "sampling_frequency", RATE_HZ, RATE_HZ * 100e-6
        ),
        "bandwidth": _write_number(phy_rx, "rf_bandwidth", BANDWIDTH_HZ, 2),
        "lo": _write_number(rx_lo, "frequency", LO_HZ, 2),
        "lo_powerdown": _write_number(rx_lo, "powerdown", 0, 0),
    }
    _attribute(phy_rx, "gain_control_mode").value = "slow_attack"
    selected["gain_mode"] = str(_attribute(phy_rx, "gain_control_mode").value)
    if selected != {
        "phy_rate": RATE_HZ,
        "adc_rate": RATE_HZ,
        "bandwidth": BANDWIDTH_HZ,
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


def run(output: Path) -> dict[str, Any]:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    payload = load_exact_payload(
        WAVEFORM_PATH,
        expected_bytes=320_000,
        expected_sha256=WAVEFORM_SHA256,
    )
    if hashlib.sha256(COEFFICIENT_PATH.read_bytes()).hexdigest() != COEFFICIENT_SHA256:
        raise QualificationError("coefficient file identity differs")
    receipt: dict[str, Any] = {
        "schema": "plutosdr-fw.starlink-pss-native-iio-cabled.v1",
        "started_at": _now(),
        "outcome": "started",
        "persistent_write": False,
        "fixture": {
            "path": ".18 TX1 -> exact 30 dB attenuator -> .17 RX1",
            "antennas": False,
            "attenuation_db": 30,
        },
        "receiver": {"serial": RX_SERIAL, "topology": RX_TOPOLOGY, "port": "RX1"},
        "transmitter": {"serial": TX_SERIAL, "topology": TX_TOPOLOGY, "port": "TX1"},
        "coefficient": {
            "path": str(COEFFICIENT_PATH),
            "sha256": COEFFICIENT_SHA256,
            "generation": COEFFICIENT_GENERATION,
            "file_layout": "I-high-Q-low",
            "fpga_register_layout": "Q-high-I-low",
        },
        "waveform": {"path": str(WAVEFORM_PATH), "sha256": WAVEFORM_SHA256},
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
            before, selected = _configure_rx(client)
            receipt["receiver"].update(
                {
                    "uri": rx_uri,
                    "firmware": RX_FIRMWARE,
                    "original": before,
                    "selected": selected,
                }
            )
            client.load_coefficient_file(
                COEFFICIENT_PATH, generation=COEFFICIENT_GENERATION
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
                sample_rate_hz=RATE_HZ,
                rf_bandwidth_hz=BANDWIDTH_HZ,
                tx_lo_hz=LO_HZ,
            )

            reassembler = PssMapReassembler()
            client.open_maps(refill_chunks=200)
            baseline_maps = _read_maps(client, reassembler, 3)
            baseline = analyze_phase_maps(baseline_maps, rate_msps=RATE_MSPS)
            receipt["roles"]["muted_coarse"] = _coarse_document(baseline)
            receipt["transmitter"]["positive_start"] = tx.start(payload, gain_db=-30.0)
            transition_maps = _read_maps(client, reassembler, 3)
            positive_maps = _read_maps(client, reassembler, 3)
            positive_coarse = analyze_phase_maps(positive_maps, rate_msps=RATE_MSPS)
            receipt["roles"]["transition_map_generations"] = [
                phase_map.generation for phase_map in transition_maps
            ]
            receipt["roles"]["positive_coarse"] = _coarse_document(positive_coarse)
            client.close_maps()

            probe_a = _refine(
                client,
                anchor=float(positive_coarse.candidate_start_index_source_center),
                period=positive_coarse.estimated_frame_period_source_samples,
                request_id=0x87100001,
            )
            first_a = _future_center(
                float(probe_a["winner_timestamp"]),
                _current_index(client),
                PERIOD_SAMPLES,
            )
            results_a = _read_fine(
                client, first_center=first_a, request_base=0x87110000, count=128
            )
            analysis_a = _analyze(results_a)
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
            )
            control_results = _read_fine(
                client, first_center=first_control, request_base=0x87120000, count=64
            )
            control_analysis = _analyze(control_results)
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
                anchor=float(results_a[-1]["winner_timestamp"]),
                period=float(analysis_a["fitted_period_source_samples"]),
                request_id=0x87130001,
            )
            first_b = _future_center(
                float(probe_b["winner_timestamp"]),
                _current_index(client),
                PERIOD_SAMPLES,
            )
            results_b = _read_fine(
                client, first_center=first_b, request_base=0x87140000, count=128
            )
            analysis_b = _analyze(results_b)
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
                    analysis_a["fitted_period_source_samples"] - PERIOD_SAMPLES
                )
                <= 1.0,
                "positive_b_period_within_one_sample": abs(
                    analysis_b["fitted_period_source_samples"] - PERIOD_SAMPLES
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
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    try:
        receipt = run(arguments.output)
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

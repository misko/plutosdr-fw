#!/usr/bin/env python3
"""Run the guarded 60 MS/s full-rate PSS tracker cabled qualification.

This runner is intentionally fixed to the two declared bench radios and the
attenuated TX1-to-RX1 fixture.  It never persists firmware.  It uses PPU's
shared radio/route locks, the fail-safe single-TX driver, and a one-second
host scheduling lead so a fresh SSH connection cannot make a fine-tracker
center stale.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import subprocess
import sys
import time
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
from pluto_plus.radio_lock import acquire_radio_lock
from pluto_plus.release_candidate_lifecycle import ssh_fixed_argv
from pluto_plus.release_candidate_linux import (
    LinuxReleaseCandidateBackend,
)

from scripts.starlink_pss_m3_iio_tx_v1 import (
    DAC_SELECT_DMA,
    TX_MUTE_DB,
    dac_selector_register,
)
from scripts.starlink_pss_m3_iio_tx_v2 import (
    SingleTxCyclicIio,
    close_iio_context,
    load_exact_payload,
)

RX_SERIAL = "104000bac4950008230026001b440a003a"
TX_SERIAL = "1040007c4a94000211000b009186843ef2"
RX_TOPOLOGY = "5-2"
TX_TOPOLOGY = "3-11"
RX_INTERFACE = "enx00e0221686a8"
RX_FIRMWARE = "starlink-pss60-fullrate-tracker-dnm-v11"
SSH_HOST = "192.168.2.1"
RATE_HZ = 60_000_000
BANDWIDTH_HZ = 20_000_000
LO_HZ = 2_400_000_000
PERIOD_SAMPLES = 80_000
APERTURE_SAMPLES = 120
HOST_LEAD_SAMPLES = 60_000_000
COEFFICIENT_GENERATION = 0x60000015
COEFFICIENT_PATH = Path(
    "/home/mouse9911/pluto-state/starlink-rx-only-dnm/"
    "m8-fullrate-60-20260907/coefficients/"
    "starlink_pss60_upper_+0.000hz_coefficients_q15.mem"
)
COEFFICIENT_SHA256 = "6aed4f4883fce03982f12af0d28ea9186599daa5564e045cb9bc636c1fef3289"
WAVEFORM_PATH = Path(
    "/home/mouse9911/pluto-state/starlink-rx-only-dnm/"
    "m6-live-20260907/candidate-60-v10/cabled-v1/waveform/"
    "starlink_pss60_upper_cabled_ci16le.bin"
)
WAVEFORM_SHA256 = "be24d054510c8d5ec7bb5d122d8a0604e2d3c742f00cb2582de312a40611458f"
PASSWORD_PATH = Path(
    "/home/mouse9911/pluto-state/starlink-rx-only-dnm/"
    "setup-ad9361-1r1t-20260906/private/radio.password"
)
STATE_ROOT = Path(
    "/home/mouse9911/pluto-state/starlink-rx-only-dnm/"
    "m8-fullrate-60-20260907/hardware-v11b/state"
)
REMOTE_COEFFICIENT = "/tmp/starlink_pss60_fullrate_coeff.mem"


class QualificationError(RuntimeError):
    """The cabled qualification could not satisfy its guarded contract."""


class PhaseContinuousSingleTx(SingleTxCyclicIio):
    """Apply a minimum-gain control without disturbing cyclic DMA phase."""

    def _phase_state(self) -> dict[str, Any]:
        return {
            "selectors": (
                int(self.tx.reg_read(dac_selector_register(0))) & 0xF,
                int(self.tx.reg_read(dac_selector_register(1))) & 0xF,
            ),
            "tx_lo_powerdown": round(float(self._read_attr(self.tx_lo, "powerdown"))),
            "cyclic_buffer_retained": self.active,
        }

    def gate_preserving_cycle(self) -> dict[str, Any]:
        if not self.active:
            raise QualificationError("phase-preserving gate requires active cyclic TX")
        evidence = self._phase_state()
        evidence["tx_hardwaregain_db"] = self._write_numeric(
            self.phy_tx, "hardwaregain", TX_MUTE_DB, tolerance=0.26
        )
        evidence["control_policy"] = "minimum_hardware_gain_only"
        if (
            evidence["tx_hardwaregain_db"] > -80.0
            or evidence["selectors"] != (DAC_SELECT_DMA, DAC_SELECT_DMA)
            or evidence["tx_lo_powerdown"] != 0
            or evidence["cyclic_buffer_retained"] is not True
        ):
            raise QualificationError("phase-preserving TX gate readback failed")
        evidence["verified"] = True
        return evidence

    def resume_preserved_cycle(self, *, gain_db: float) -> dict[str, Any]:
        if not self.active or not TX_MUTE_DB <= gain_db <= -10.0:
            raise QualificationError("phase-preserving resume state or gain is invalid")
        evidence = self._phase_state()
        evidence["muted_gain_before_resume_db"] = round(
            float(self._read_attr(self.phy_tx, "hardwaregain").strip().split()[0]),
            2,
        )
        evidence["tx_hardwaregain_db"] = self._write_numeric(
            self.phy_tx, "hardwaregain", gain_db, tolerance=0.26
        )
        if (
            evidence["muted_gain_before_resume_db"] > -80.0
            or evidence["selectors"] != (DAC_SELECT_DMA, DAC_SELECT_DMA)
            or evidence["tx_lo_powerdown"] != 0
            or abs(evidence["tx_hardwaregain_db"] - gain_db) > 0.26
            or evidence["cyclic_buffer_retained"] is not True
        ):
            raise QualificationError("phase-preserving TX resume readback failed")
        evidence["verified"] = True
        return evidence


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_new_json(path: Path, value: Any) -> None:
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise QualificationError(f"short write to {path}")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _run(
    argv: tuple[str, ...],
    *,
    timeout_s: float,
    stdin: bytes | None = None,
    maximum_output: int = 16 << 20,
) -> bytes:
    try:
        completed = subprocess.run(
            argv,
            input=stdin,
            capture_output=True,
            check=False,
            timeout=timeout_s,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise QualificationError(f"child process failed: {error}") from error
    if len(completed.stdout) > maximum_output or len(completed.stderr) > maximum_output:
        raise QualificationError("child output exceeded its size bound")
    if completed.returncode:
        detail = (completed.stdout + completed.stderr).decode(errors="replace")[-4000:]
        raise QualificationError(
            f"child {argv[0]!r} exited {completed.returncode}: {detail}"
        )
    return completed.stdout


def _required_channel(device: Any, identifier: str, output: bool) -> Any:
    channel = device.find_channel(identifier, output)
    if channel is None:
        raise QualificationError(f"missing IIO channel {identifier!r}, output={output}")
    return channel


def _attribute(channel: Any, name: str) -> Any:
    if name not in channel.attrs:
        raise QualificationError(f"missing IIO attribute {name!r}")
    return channel.attrs[name]


def _read_number(channel: Any, name: str) -> int:
    try:
        return round(float(str(_attribute(channel, name).value).strip().split()[0]))
    except (IndexError, TypeError, ValueError) as error:
        raise QualificationError(f"invalid IIO numeric readback for {name}") from error


def _write_number(channel: Any, name: str, value: int, tolerance: float) -> int:
    attribute = _attribute(channel, name)
    attribute.value = str(value)
    observed = _read_number(channel, name)
    if abs(observed - value) > tolerance:
        raise QualificationError(f"{name} readback {observed} differs from {value}")
    return observed


def _future_center(anchor: float, current: int, period: float) -> int:
    target = current + HOST_LEAD_SAMPLES
    steps = max(0, math.ceil((target - anchor) / period))
    center = round(anchor + steps * period)
    while center < target:
        steps += 1
        center = round(anchor + steps * period)
    return center


def _analyze(results: list[dict[str, Any]]) -> dict[str, Any]:
    if len(results) < 2:
        raise QualificationError("tracking result set is too short")
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
    scores: list[float] = []
    for item in results:
        real = int(item["correlation_real"])
        imag = int(item["correlation_imag"])
        energy = int(item["sample_energy"]) * int(item["coefficient_energy"])
        scores.append((real * real + imag * imag) / energy if energy > 0 else 0.0)
    maximum_residual = max(abs(value) for value in residuals)
    return {
        "count": len(results),
        "fitted_period_source_samples": slope,
        "relative_clock_error_ppm": (slope / PERIOD_SAMPLES - 1.0) * 1e6,
        "residual_rms_source_samples": math.sqrt(
            statistics.fmean(value * value for value in residuals)
        ),
        "residual_max_abs_source_samples": maximum_residual,
        "residual_max_abs_ns_at_60msps": maximum_residual * 1e9 / RATE_HZ,
        "winner_lag_min": min(lags),
        "winner_lag_median": statistics.median(lags),
        "winner_lag_max": max(lags),
        "aperture_edge_hits": sum(abs(value) == APERTURE_SAMPLES for value in lags),
        "normalized_score_min": min(scores),
        "normalized_score_median": statistics.median(scores),
        "normalized_score_max": max(scores),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = args.output.absolute()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(output, 0o700)
    receipt_path = output / "run-receipt.json"

    if (
        _sha256(COEFFICIENT_PATH) != COEFFICIENT_SHA256
        or COEFFICIENT_PATH.stat().st_size != 2376
        or COEFFICIENT_PATH.stat().st_mode & 0o777 != 0o600
    ):
        raise QualificationError("coefficient artifact identity is not exact")
    payload = load_exact_payload(
        WAVEFORM_PATH,
        expected_bytes=320000,
        expected_sha256=WAVEFORM_SHA256,
    )
    if PASSWORD_PATH.stat().st_mode & 0o777 != 0o600:
        raise QualificationError("password file is not mode 0600")

    receipt: dict[str, Any] = {
        "schema": "plutosdr-fw.starlink-pss-m8-cabled.v1",
        "started_at": _now(),
        "outcome": "running",
        "hardware_accessed": False,
        "persistent_write": False,
        "do_not_merge": True,
        "claim_scope": "synthetic_cabled_pss_full_rate_timing_only",
        "pss_timing_claim": False,
        "sss_detected": False,
        "frame_lock_claim": False,
        "runner": {
            "path": str(Path(__file__).absolute()),
            "sha256": _sha256(Path(__file__).absolute()),
        },
        "receiver": {
            "serial": RX_SERIAL,
            "topology": RX_TOPOLOGY,
            "expected_firmware": RX_FIRMWARE,
        },
        "transmitter": {
            "serial": TX_SERIAL,
            "topology": TX_TOPOLOGY,
            "port": "TX1",
            "gain_db": -30.0,
        },
        "fixture": {
            "path": ".18 TX1 -> exact 30 dB attenuator -> .17 RX1",
            "antennas": False,
            "attenuation_db": 30,
        },
        "negative_control": {
            "policy": "minimum_hardware_gain_with_phase_continuous_dma",
            "tx_hardwaregain_db": TX_MUTE_DB,
            "dac_selector": "DMA retained",
            "tx_lo": "powered for phase continuity",
            "final_full_mute_required": True,
        },
        "configuration": {
            "sample_rate_hz": RATE_HZ,
            "rf_bandwidth_hz": BANDWIDTH_HZ,
            "lo_hz": LO_HZ,
            "period_source_samples": PERIOD_SAMPLES,
            "host_scheduling_lead_samples": HOST_LEAD_SAMPLES,
        },
        "coefficient": {
            "path": str(COEFFICIENT_PATH),
            "bytes": COEFFICIENT_PATH.stat().st_size,
            "sha256": COEFFICIENT_SHA256,
            "generation": f"0x{COEFFICIENT_GENERATION:08x}",
        },
        "waveform": {
            "path": str(WAVEFORM_PATH),
            "bytes": len(payload),
            "sha256": WAVEFORM_SHA256,
            "samples": len(payload) // 4,
        },
        "roles": {},
        "cleanup": {"errors": []},
    }
    body_error: BaseException | None = None
    backend = LinuxReleaseCandidateBackend(state_root=STATE_ROOT, timeout_s=45.0)
    route: Any = None
    rx_context: Any = None
    tx_context: Any = None
    tx: PhaseContinuousSingleTx | None = None

    targets = [
        target for target in backend._runtime_targets() if target.serial == RX_SERIAL
    ]
    if len(targets) != 1:
        raise QualificationError(f"expected one exact RX target, found {len(targets)}")
    target = targets[0]
    if target.topology != RX_TOPOLOGY or target.network_interface != RX_INTERFACE:
        raise QualificationError("fresh RX topology or interface differs")
    receipt["receiver"]["fresh_target"] = target.model_dump(mode="json")

    try:
        with backend.transaction_locks(target, SSH_HOST):
            backend.revalidate_target(target)
            route = backend.acquire_host_route(target, SSH_HOST)
            receipt["route"] = route.model_dump(mode="json")
            receipt["hardware_accessed"] = True

            def remote(
                command: str,
                *,
                timeout_s: float = 45.0,
                stdin: bytes | None = None,
            ) -> bytes:
                backend.ensure_host_route(route, target)
                return _run(
                    ssh_fixed_argv(
                        target,
                        ssh_host=SSH_HOST,
                        password_path=PASSWORD_PATH,
                        remote_command=command,
                    ),
                    timeout_s=timeout_s,
                    stdin=stdin,
                )

            def remote_json(command: str, *, timeout_s: float = 45.0) -> dict[str, Any]:
                try:
                    value = json.loads(remote(command, timeout_s=timeout_s))
                except json.JSONDecodeError as error:
                    raise QualificationError(
                        "remote output is not one JSON object"
                    ) from error
                if not isinstance(value, dict):
                    raise QualificationError("remote JSON is not an object")
                return value

            def current_index() -> int:
                snapshot = remote_json(
                    f"/usr/sbin/starlink_pssctl --expect-serial {RX_SERIAL} snapshot"
                )
                if snapshot.get("serial") != RX_SERIAL:
                    raise QualificationError("tracker snapshot serial differs")
                return int(snapshot["current_index"])

            def coarse() -> dict[str, Any]:
                candidate = remote_json(
                    f"/usr/sbin/starlink_pss_acqctl --expect-serial {RX_SERIAL} "
                    "candidate --timeout-ms 10000",
                    timeout_s=30.0,
                )
                if (
                    candidate.get("serial") != RX_SERIAL
                    or candidate.get("input_rate_msps") != 60
                    or candidate.get("continuity_ok") is not True
                    or candidate.get("fault_free_epoch") is not True
                ):
                    raise QualificationError("coarse candidate contract failed")
                return candidate

            def refine_from_anchor(
                request_id: int, anchor: int, period: float
            ) -> dict[str, Any]:
                center = _future_center(float(anchor), current_index(), period)
                result = remote_json(
                    f"/usr/sbin/starlink_pssctl --expect-serial {RX_SERIAL} track "
                    f"--request 0x{request_id:08x} --center {center} --timeout-ms 5000",
                    timeout_s=20.0,
                )
                if (
                    result.get("serial") != RX_SERIAL
                    or result.get("all_counter_gates_passed") is not True
                    or result.get("result_released") is not True
                ):
                    raise QualificationError("refinement probe contract failed")
                return result

            def refine(request_id: int, candidate: dict[str, Any]) -> dict[str, Any]:
                return refine_from_anchor(
                    request_id,
                    int(candidate["candidate_start_index_source_center"]),
                    float(candidate["estimated_frame_period_source_samples"]),
                )

            def batch(
                request_base: int, anchor: int, count: int
            ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
                first = _future_center(float(anchor), current_index(), PERIOD_SAMPLES)
                raw = remote(
                    f"/usr/sbin/starlink_pssctl --expect-serial {RX_SERIAL} "
                    "track-batch "
                    f"--request-base 0x{request_base:08x} --count {count} "
                    f"--period {PERIOD_SAMPLES} --first-center {first} "
                    "--queue-target 7 --timeout-ms 5000",
                    timeout_s=45.0,
                )
                records = [
                    json.loads(line)
                    for line in raw.decode().splitlines()
                    if line.strip()
                ]
                results = [
                    item for item in records if item.get("kind") == "batch_result"
                ]
                summaries = [
                    item for item in records if item.get("kind") == "batch_summary"
                ]
                if len(results) != count or len(summaries) != 1:
                    raise QualificationError("batch output shape differs")
                summary = summaries[0]
                if (
                    summary.get("serial") != RX_SERIAL
                    or summary.get("requested") != count
                    or summary.get("submitted") != count
                    or summary.get("completed") != count
                    or summary.get("all_error_counter_deltas_zero") is not True
                    or summary.get("all_counter_gates_passed") is not True
                ):
                    raise QualificationError("batch counter contract failed")
                return results, summary

            rx_uri = exact_usb_iio_uri(
                Path("/sys/bus/usb/devices") / RX_TOPOLOGY, RX_SERIAL
            )
            rx_context = iio.Context(rx_uri)
            rx_context.set_timeout(5000)
            context_attrs = {
                str(key): str(value) for key, value in rx_context.attrs.items()
            }
            phy = rx_context.find_device("ad9361-phy")
            adc = rx_context.find_device("cf-ad9361-lpc")
            if (
                context_attrs.get("hw_serial") != RX_SERIAL
                or context_attrs.get("fw_version") != RX_FIRMWARE
                or phy is None
                or adc is None
                or rx_context.find_device("cf-ad9361-dds-core-lpc") is not None
                or any(channel.scan_element for channel in adc.channels)
            ):
                raise QualificationError("RX detector-only identity/layout differs")
            phy_rx = _required_channel(phy, "voltage0", False)
            capture_rx = _required_channel(adc, "voltage0", False)
            rx_lo = _required_channel(phy, "altvoltage0", True)
            before = {
                "phy_sampling_frequency_hz": _read_number(phy_rx, "sampling_frequency"),
                "capture_sampling_frequency_hz": _read_number(
                    capture_rx, "sampling_frequency"
                ),
                "rf_bandwidth_hz": _read_number(phy_rx, "rf_bandwidth"),
                "gain_control_mode": str(_attribute(phy_rx, "gain_control_mode").value),
                "rx_lo_hz": _read_number(rx_lo, "frequency"),
                "rx_lo_powerdown": _read_number(rx_lo, "powerdown"),
            }
            selected = {
                "phy_sampling_frequency_hz": _write_number(
                    phy_rx, "sampling_frequency", RATE_HZ, RATE_HZ * 100e-6
                ),
                "capture_sampling_frequency_hz": _write_number(
                    capture_rx, "sampling_frequency", RATE_HZ, RATE_HZ * 100e-6
                ),
                "rf_bandwidth_hz": _write_number(
                    phy_rx, "rf_bandwidth", BANDWIDTH_HZ, 2
                ),
                "rx_lo_hz": _write_number(rx_lo, "frequency", LO_HZ, 2),
                "rx_lo_powerdown": _write_number(rx_lo, "powerdown", 0, 0),
            }
            _attribute(phy_rx, "gain_control_mode").value = "slow_attack"
            selected["gain_control_mode"] = str(
                _attribute(phy_rx, "gain_control_mode").value
            )
            if selected != {
                "phy_sampling_frequency_hz": RATE_HZ,
                "capture_sampling_frequency_hz": RATE_HZ,
                "rf_bandwidth_hz": BANDWIDTH_HZ,
                "rx_lo_hz": LO_HZ,
                "rx_lo_powerdown": 0,
                "gain_control_mode": "slow_attack",
            }:
                raise QualificationError("RX selected setting readback differs")
            rates = tuple(
                int(value)
                for value in str(
                    _attribute(capture_rx, "sampling_frequency_available").value
                )
                .replace("[", "")
                .replace("]", "")
                .split()
            )
            gp_control = int(adc.reg_read(0x800000BC)) & 0xFFFFFFFF
            if rates != (RATE_HZ, RATE_HZ // 8) or gp_control & 1:
                raise QualificationError("RX factor-one source path differs")
            receipt["receiver"]["iio"] = {
                "uri": rx_uri,
                "before": before,
                "selected": selected,
                "capture_rates_available_hz": rates,
                "adc_gp_control": f"0x{gp_control:08x}",
            }

            coefficient = COEFFICIENT_PATH.read_bytes()
            remote(
                f"umask 077; /bin/cat > {REMOTE_COEFFICIENT}",
                timeout_s=20.0,
                stdin=coefficient,
            )
            remote_hash = (
                remote(
                    f'test "$(wc -c < {REMOTE_COEFFICIENT})" -eq 2376; '
                    f"sha256sum {REMOTE_COEFFICIENT}"
                )
                .decode()
                .split()[0]
            )
            if remote_hash != COEFFICIENT_SHA256:
                raise QualificationError("remote coefficient identity differs")
            receipt["remote_coefficient"] = {
                "path": REMOTE_COEFFICIENT,
                "sha256": remote_hash,
                "upload_verified": True,
            }

            acquisition_info = remote_json(
                f"/usr/sbin/starlink_pss_acqctl --expect-serial {RX_SERIAL} info"
            )
            tracker_info = remote_json(
                f"/usr/sbin/starlink_pssctl --expect-serial {RX_SERIAL} info"
            )
            if (
                acquisition_info.get("input_rate_msps") != 60
                or tracker_info.get("rate_msps") != 60
                or tracker_info.get("taps") != 264
                or tracker_info.get("capture_samples") != 520
                or tracker_info.get("lags") != 241
                or tracker_info.get("contract_valid") is not True
            ):
                raise QualificationError("FPGA acquisition/tracker contract differs")
            receipt["acquisition_info"] = acquisition_info
            receipt["tracker_info_before_load"] = tracker_info
            clock = remote_json(
                f"/usr/sbin/starlink_pssctl --expect-serial {RX_SERIAL} "
                "clock-slope --duration-ms 1000 --tolerance-ppm 5000",
                timeout_s=15.0,
            )
            if clock.get("passed") is not True:
                raise QualificationError("accepted-sample clock slope failed")
            receipt["clock_slope"] = clock
            loaded = remote_json(
                f"/usr/sbin/starlink_pssctl --expect-serial {RX_SERIAL} load "
                f"--coeff {REMOTE_COEFFICIENT} "
                f"--generation 0x{COEFFICIENT_GENERATION:08x} --timeout-ms 5000",
                timeout_s=20.0,
            )
            if loaded.get("taps_loaded") != 264:
                raise QualificationError("coefficient load count differs")
            receipt["coefficient_load"] = loaded

            with acquire_radio_lock(TX_SERIAL):
                tx_uri = exact_usb_iio_uri(
                    Path("/sys/bus/usb/devices") / TX_TOPOLOGY, TX_SERIAL
                )
                tx_context = iio.Context(tx_uri)
                tx = PhaseContinuousSingleTx(iio, tx_context, expected_serial=TX_SERIAL)
                tx_context = None
                receipt["transmitter"]["exact_uri"] = tx_uri
                receipt["transmitter"]["initial_mute"] = tx.mute()
                receipt["transmitter"]["configuration_readback"] = tx.configure(
                    sample_rate_hz=RATE_HZ,
                    rf_bandwidth_hz=BANDWIDTH_HZ,
                    tx_lo_hz=LO_HZ,
                )

                def positive(
                    *,
                    name: str,
                    refine_request: int,
                    batch_request: int,
                ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
                    receipt["transmitter"][f"{name}_start"] = tx.start(
                        payload, gain_db=-30.0
                    )
                    time.sleep(0.25)
                    candidate = coarse()
                    probe = refine(refine_request, candidate)
                    results, summary = batch(
                        batch_request, int(probe["winner_timestamp"]), 256
                    )
                    analysis = _analyze(results)
                    artifact = output / f"{name}.json"
                    _write_new_json(
                        artifact,
                        {
                            "coarse": candidate,
                            "refinement_probe": probe,
                            "batch_results": results,
                            "batch_summary": summary,
                            "analysis": analysis,
                        },
                    )
                    receipt["roles"][name] = {
                        "artifact": str(artifact),
                        "coarse_period_source_samples": candidate[
                            "estimated_frame_period_source_samples"
                        ],
                        "coarse_anchor_source": candidate[
                            "candidate_start_index_source_center"
                        ],
                        "probe_scheduled_center": probe["scheduled_center"],
                        "probe_winner_timestamp": probe["winner_timestamp"],
                        "probe_correction_source_samples": probe["winner_lag"],
                        "analysis": analysis,
                    }
                    return analysis, results

                analysis_a, results_a = positive(
                    name="positive_a",
                    refine_request=0x86100001,
                    batch_request=0x86110000,
                )
                receipt["transmitter"]["control_mute"] = tx.gate_preserving_cycle()
                time.sleep(0.25)
                control_results, control_summary = batch(
                    0x86120000, int(results_a[-1]["winner_timestamp"]), 64
                )
                control_analysis = _analyze(control_results)
                control_artifact = output / "muted_control.json"
                _write_new_json(
                    control_artifact,
                    {
                        "batch_results": control_results,
                        "batch_summary": control_summary,
                        "analysis": control_analysis,
                    },
                )
                receipt["roles"]["muted_control"] = {
                    "artifact": str(control_artifact),
                    "analysis": control_analysis,
                }
                receipt["transmitter"]["positive_b_resume"] = tx.resume_preserved_cycle(
                    gain_db=-30.0
                )
                time.sleep(0.25)
                probe_b = refine_from_anchor(
                    0x86130001,
                    int(results_a[-1]["winner_timestamp"]),
                    float(analysis_a["fitted_period_source_samples"]),
                )
                results_b, summary_b = batch(
                    0x86140000, int(probe_b["winner_timestamp"]), 256
                )
                analysis_b = _analyze(results_b)
                artifact_b = output / "positive_b.json"
                _write_new_json(
                    artifact_b,
                    {
                        "acquisition_seed": "positive_a_fine_timing_prediction",
                        "refinement_probe": probe_b,
                        "batch_results": results_b,
                        "batch_summary": summary_b,
                        "analysis": analysis_b,
                    },
                )
                receipt["roles"]["positive_b"] = {
                    "artifact": str(artifact_b),
                    "acquisition_seed": "positive_a_fine_timing_prediction",
                    "prediction_period_source_samples": analysis_a[
                        "fitted_period_source_samples"
                    ],
                    "probe_scheduled_center": probe_b["scheduled_center"],
                    "probe_winner_timestamp": probe_b["winner_timestamp"],
                    "probe_correction_source_samples": probe_b["winner_lag"],
                    "analysis": analysis_b,
                }
                final_tx_mute = tx.close()
                tx = None
                receipt["cleanup"]["tx_final_mute"] = final_tx_mute

            gates = {
                "positive_a_count_256": analysis_a["count"] == 256,
                "positive_b_count_256": analysis_b["count"] == 256,
                "control_count_64": control_analysis["count"] == 64,
                "positive_a_period_within_one_source_sample": abs(
                    analysis_a["fitted_period_source_samples"] - PERIOD_SAMPLES
                )
                <= 1.0,
                "positive_b_period_within_one_source_sample": abs(
                    analysis_b["fitted_period_source_samples"] - PERIOD_SAMPLES
                )
                <= 1.0,
                "positive_a_residual_lte_one_source_sample": analysis_a[
                    "residual_max_abs_source_samples"
                ]
                <= 1.0,
                "positive_b_residual_lte_one_source_sample": analysis_b[
                    "residual_max_abs_source_samples"
                ]
                <= 1.0,
                "positive_a_no_aperture_edge_hits": analysis_a["aperture_edge_hits"]
                == 0,
                "positive_b_no_aperture_edge_hits": analysis_b["aperture_edge_hits"]
                == 0,
                "positive_a_score_exceeds_muted": analysis_a["normalized_score_median"]
                > control_analysis["normalized_score_median"],
                "positive_b_score_exceeds_muted": analysis_b["normalized_score_median"]
                > control_analysis["normalized_score_median"],
                "final_tx_mute_verified": final_tx_mute.get("verified") is True,
            }
            receipt["gates"] = gates
            failed_gates = [name for name, passed in gates.items() if not passed]
            if failed_gates:
                raise QualificationError(f"qualification gates failed: {failed_gates}")
            receipt["pss_timing_claim"] = True
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
            except BaseException as error:  # noqa: BLE001 - continue cleanup
                cleanup_errors.append(f"TX final mute/close: {error}")
        elif tx_context is not None:
            try:
                receipt["cleanup"]["tx_context_release"] = close_iio_context(
                    iio, tx_context
                )
            except BaseException as error:  # noqa: BLE001 - continue cleanup
                cleanup_errors.append(f"TX context close: {error}")
        if route is not None:
            try:
                try:
                    _run(
                        ssh_fixed_argv(
                            target,
                            ssh_host=SSH_HOST,
                            password_path=PASSWORD_PATH,
                            remote_command=(
                                f"/bin/rm -f {REMOTE_COEFFICIENT}; "
                                f"test ! -e {REMOTE_COEFFICIENT}"
                            ),
                        ),
                        timeout_s=15.0,
                    )
                    receipt["cleanup"]["remote_coefficient_removed"] = True
                except BaseException as error:  # noqa: BLE001 - continue cleanup
                    cleanup_errors.append(f"remote coefficient cleanup: {error}")
                if rx_context is not None:
                    try:
                        receipt["cleanup"]["rx_context_release"] = close_iio_context(
                            iio, rx_context
                        )
                        rx_context = None
                    except BaseException as error:  # noqa: BLE001 - continue cleanup
                        cleanup_errors.append(f"RX context close: {error}")
                backend.release_host_route(route)
                receipt["cleanup"]["route_release_verified"] = True
                route = None
            except BaseException as error:  # noqa: BLE001 - preserve receipt
                cleanup_errors.append(f"route release: {error}")
        elif rx_context is not None:
            try:
                receipt["cleanup"]["rx_context_release"] = close_iio_context(
                    iio, rx_context
                )
            except BaseException as error:  # noqa: BLE001 - continue cleanup
                cleanup_errors.append(f"RX context close: {error}")
        receipt["cleanup"]["verified"] = not cleanup_errors
        if cleanup_errors:
            receipt["outcome"] = "failed"
            receipt["pss_timing_claim"] = False
        receipt["completed_at"] = _now()
        _write_new_json(receipt_path, receipt)

    print(
        json.dumps(
            {
                "receipt": str(receipt_path),
                "outcome": receipt["outcome"],
                "error": receipt.get("error"),
                "gates": receipt.get("gates"),
                "positive_a": receipt.get("roles", {})
                .get("positive_a", {})
                .get("analysis"),
                "muted_control": receipt.get("roles", {})
                .get("muted_control", {})
                .get("analysis"),
                "positive_b": receipt.get("roles", {})
                .get("positive_b", {})
                .get("analysis"),
                "cleanup": receipt["cleanup"],
            },
            sort_keys=True,
        )
    )
    return 0 if body_error is None and receipt["outcome"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())

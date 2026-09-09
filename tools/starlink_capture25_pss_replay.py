#!/usr/bin/env python3
"""Evidence-selected, read-only capture25 replay through the existing Q17 model.

This is offline spectral conditioning and a host C-model replay, not native
25 MS/s FPGA support, live acquisition, independent RF validation, or lock.
The fixed windows were selected using saved evidence; optional CFO assistance
is externally supplied and is never described as a blind FPGA search.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from collections import Counter
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path, PurePosixPath

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.starlink_oracle import (
    AcquisitionConfig,
    fold_phase_map_tiles,
    projected_pss,
    quantize_q15,
    search_phase_map_drift,
    xfft_bitacc,
)
from tools.starlink_capture25_condition import condition_capture25
from tools.starlink_pss_acquisition_study import _drift_bank, _scramble_complete_frames

CAPTURE = Path("/srv/bulk/leo/recordings/2026/09/09/cap-20260909T121248-414fb81f488c")
MANIFEST_SHA256 = "aaadf18494225b2ce55b9e1247d45a09e31e4a13ea1b88896ccadabff6ebe20a"
SERIAL = "10400056f695001322002d0010ad1719f2"
RADIO_ID = "radio_pluto_19f2"
STREAM_ID = "stream-1"
WINDOWS = {"negative": (12_500_000, 20_500_000), "positive": (900_000_000, 908_000_000)}
HALO = 5_000
SOURCE_RATE = 25_000_000
CANONICAL_RATE = 15_000_000
KERNEL = ROOT / "hdl/library/starlink_pss_acquisition/tb/upper_edge_pss_kernel_q17.mem"
MAX_CHUNK_BYTES = 134_217_728
SCHEMA = "starlink-capture25-pss-replay-v1"


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def integer(value, name: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def digest(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise ValueError("malformed sha256 digest")
    return value[7:]


def decode_json(payload: bytes):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError(f"nonfinite JSON constant: {value}")

    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError(f"nonfinite JSON number: {value}")
        return result

    return json.loads(payload, object_pairs_hook=pairs, parse_constant=reject_constant,
                      parse_float=finite_float)


def capture_path(relative: str) -> Path:
    """No arbitrary sudo paths, traversal, symlink aliases, or other captures."""
    rel = PurePosixPath(relative)
    if (not isinstance(relative, str) or str(rel) != relative or rel.is_absolute()
            or any(part in (".", "..") for part in rel.parts)):
        raise ValueError("invalid capture-relative path")
    allowed = relative == "manifest.json" or bool(re.fullmatch(
        rf"radio-{SERIAL}/(?:iq-[0-9]{{6}}\.ci16\.zst|gap-map\.json|"
        r"validity-inventory\.json|timeline\.jsonl\.zst)", relative))
    if not allowed:
        raise ValueError("path is outside the exact admitted capture inventory")
    path = CAPTURE / relative
    if path.resolve(strict=True) != path or not path.is_file():
        raise ValueError("capture path must be a regular non-aliased file")
    return path


def read_capture(relative: str, *, expected_bytes: int | None = None,
                 maximum_bytes: int = MAX_CHUNK_BYTES) -> bytes:
    path = capture_path(relative)
    size = path.stat().st_size
    if size > maximum_bytes or (expected_bytes is not None and size != expected_bytes):
        raise ValueError(f"capture size mismatch: {relative}")
    try:
        with path.open("rb") as source:
            payload = source.read(maximum_bytes + 1)
    except PermissionError:
        # A fixed argument vector, after exact path/size validation; never a shell.
        payload = subprocess.run(
            ["sudo", "-n", "-u", "leo", "cat", "--", str(path)],
            check=True, capture_output=True, timeout=120,
        ).stdout
    if len(payload) != size:
        raise ValueError(f"capture changed during read: {relative}")
    return payload


def _checked_metadata(relative: str, expected_hash: str, provenance: list) -> dict:
    payload = read_capture(relative, maximum_bytes=4 * 1024 * 1024)
    if sha256(payload) != digest(expected_hash):
        raise ValueError(f"metadata digest mismatch: {relative}")
    provenance.append({"relative_path": relative, "bytes": len(payload),
                       "sha256": sha256(payload)})
    return decode_json(payload)


def _covering(items: list, start: int, stop: int) -> list:
    """Validate the entire ordered interval inventory, then select overlaps."""
    cursor = 0
    selected = []
    for item in items:
        begin = integer(item["device_sample_start"], "device_sample_start")
        count = integer(item["sample_count"], "sample_count", minimum=1)
        if begin != cursor:
            raise ValueError("inventory has an overlap, hole, or unordered interval")
        cursor = begin + count
        if cursor > start and begin < stop:
            selected.append(item)
    if not selected or selected[0]["device_sample_start"] > start or cursor < stop:
        raise ValueError("inventory does not cover the halo-extended interval")
    return selected


def admit_capture(window: str) -> tuple[dict, list[dict]]:
    start, stop = WINDOWS[window]
    extended_start, extended_stop = start - HALO, stop + HALO
    payload = read_capture("manifest.json", maximum_bytes=4 * 1024 * 1024)
    if sha256(payload) != MANIFEST_SHA256:
        raise ValueError("named capture manifest digest mismatch")
    manifest = decode_json(payload)
    if manifest["schema_version"] != 6 or manifest["session_id"] != CAPTURE.name:
        raise ValueError("unsupported named capture manifest identity/schema")
    streams = [item for item in manifest["streams"] if item["stream_id"] == STREAM_ID]
    if len(streams) != 1:
        raise ValueError("expected exactly one target stream")
    stream = streams[0]
    if (stream["schema_version"] != 3 or stream["radio"]["serial"] != SERIAL
            or stream["radio"]["radio_id"] != RADIO_ID):
        raise ValueError("target stream/radio identity mismatch")
    plans = [item for item in manifest["capture_plan"]["radio_plans"]
             if item["radio_id"] == RADIO_ID]
    if len(plans) != 1:
        raise ValueError("expected exactly one resolved target radio plan")
    plan = plans[0]
    expected_settings = {"sample_rate_hz": SOURCE_RATE, "bandwidth_hz": SOURCE_RATE,
                         "center_frequency_hz": 1_932_500_000, "receiver_ids": [0]}
    for settings in (stream["applied_settings"], stream["requested_settings"],
                     plan["requested_settings"]):
        if any(settings.get(key) != value for key, value in expected_settings.items()):
            raise ValueError("target rate/RX0/applied IF LO mismatch")
    for key, value in {"starlink_edge": "upper", "starlink_channel": 4,
                       "captured_if_start_hz": 1_920_000_000,
                       "captured_if_stop_hz": 1_945_000_000,
                       "channel_if_start_hz": 1_705_000_000,
                       "channel_if_stop_hz": 1_945_000_000,
                       "pilot_if_center_frequency_hz": 1_940_312_500}.items():
        if plan.get(key) != value:
            raise ValueError(f"resolved upper channel geometry mismatch: {key}")
    profile = plan["profile_revision"]["profile"]
    if profile["lnb_lo_hz"] != 9_750_000_000:
        raise ValueError("LNB LO mismatch")
    continuity = stream["continuity"]
    if continuity.get("sample_loss_observable") is not True:
        raise ValueError("sample loss is not observable")
    origin = integer(continuity["first_device_sample_counter"], "counter origin")
    generation = continuity["validated_stream_generation"]
    if not isinstance(generation, str) or not generation.isdecimal():
        raise ValueError("missing validated stream generation")
    provenance = [{"relative_path": "manifest.json", "bytes": len(payload),
                   "sha256": sha256(payload)}]
    inventory = _checked_metadata(stream["validity_inventory_relative_path"],
                                  stream["validity_inventory_sha256"], provenance)
    gap_map = _checked_metadata(stream["gap_map_relative_path"],
                                stream["gap_map_sha256"], provenance)
    for metadata in (inventory, gap_map):
        if (metadata["schema_version"] != 1 or metadata["stream_id"] != STREAM_ID
                or metadata["first_device_sample_counter"] != origin
                or metadata["timeline_sha256"] != stream["timeline_sha256"]):
            raise ValueError("continuity metadata identity/counter/timeline mismatch")
    if (inventory["algorithm_version"] != "counter-authoritative-validity-v1"
            or inventory["gap_map_content_digest"] != stream["gap_map_sha256"]
            or inventory["logical_sample_count"] != stream["logical_sample_count"]):
        raise ValueError("validity inventory cross-binding mismatch")
    runs = _covering(inventory["runs"], extended_start, extended_stop)
    if len(runs) != 1 or runs[0]["content_kind"] != "observed":
        raise ValueError("window and halos must fit one observed continuity island")
    segment = integer(runs[0]["continuity_segment_index"], "continuity segment")
    for boundary in gap_map["boundaries"]:
        offset = integer(boundary["device_sample_offset"], "gap offset")
        missing = integer(boundary["missing_sample_count"], "gap length")
        if extended_start < offset + missing and offset < extended_stop:
            raise ValueError("gap-map boundary intersects selected interval")
        if missing == 0 and extended_start <= offset < extended_stop:
            raise ValueError("unquantified discontinuity intersects selected interval")
    chunks = _covering(stream["chunks"], extended_start, extended_stop)
    for chunk in chunks:
        if (chunk["content_kind"] != "observed"
                or chunk["continuity_segment_index"] != segment
                or chunk["sample_format"] != "ci16_le"
                or chunk["sample_layout"] != "sample_receiver_iq"):
            raise ValueError("chunk is zero-filled, discontinuous, or not single-RX CI16")
        if chunk["uncompressed_bytes"] != chunk["sample_count"] * 4:
            raise ValueError("chunk CI16 byte geometry mismatch")
        index = integer(chunk["chunk_index"], "chunk index")
        if chunk["relative_path"] != f"radio-{SERIAL}/iq-{index:06d}.ci16.zst":
            raise ValueError("chunk index/path mismatch")
        for key in ("compressed_bytes", "uncompressed_bytes"):
            if integer(chunk[key], key, minimum=1) > MAX_CHUNK_BYTES:
                raise ValueError("chunk exceeds bounded byte geometry")
        digest(chunk["compressed_sha256"])
        digest(chunk["uncompressed_sha256"])
        capture_path(chunk["relative_path"])
    return {
        "capture_path": str(CAPTURE), "manifest_sha256": MANIFEST_SHA256,
        "manifest_state": manifest["state"], "stream_state": stream["state"],
        "whole_stream_error": stream["error"], "stream_id": STREAM_ID,
        "serial": SERIAL, "radio_id": RADIO_ID, "receiver_id": 0,
        "applied_settings": stream["applied_settings"],
        "resolved_plan": plan, "profile_label_is_not_resolved_tuning": True,
        "historical_radio_metadata_only_no_radio_access": True,
        "source_sample_axis": "stream-relative device-counter axis, NOT compact observed axis",
        "first_device_sample_counter": origin, "validated_stream_generation": generation,
        "window": window, "evidence_selected_not_blind": True,
        "source_start_index": start, "source_stop_index": stop,
        "source_halo_start_index": extended_start, "source_halo_stop_index": extended_stop,
        "source_counter_start": origin + start, "source_counter_stop": origin + stop,
        "continuity_segment_index": segment, "observed_island": runs[0],
        "metadata_artifacts": provenance,
        "timeline_digest_crossbound_but_timeline_payload_not_reread": stream["timeline_sha256"],
        "whole_stream_logical_iq_digest_not_recomputed": stream["logical_iq_sha256"],
        "verified_chunks": [],
    }, chunks


def decompress_chunk(payload: bytes, expected_bytes: int) -> bytes:
    # Only called after the pinned compressed digest has matched. No extraction
    # paths, source writes, shell expansion, or zstd output files are used.
    result = subprocess.run(["zstd", "--decompress", "--stdout", "--quiet"],
                            input=payload, capture_output=True, check=True, timeout=120)
    if len(result.stdout) != expected_bytes:
        raise ValueError("uncompressed chunk byte count mismatch")
    return result.stdout


def load_window(provenance: dict, chunks: list[dict]) -> np.ndarray:
    start = provenance["source_halo_start_index"]
    stop = provenance["source_halo_stop_index"]
    output = np.empty((stop - start, 2), dtype="<i2")
    copied = 0
    for chunk in chunks:
        provenance["chunk_in_progress"] = dict(chunk)
        compressed = read_capture(chunk["relative_path"], expected_bytes=chunk["compressed_bytes"])
        if sha256(compressed) != digest(chunk["compressed_sha256"]):
            raise ValueError("compressed chunk digest mismatch")
        raw = decompress_chunk(compressed, chunk["uncompressed_bytes"])
        if sha256(raw) != digest(chunk["uncompressed_sha256"]):
            raise ValueError("uncompressed chunk digest mismatch")
        begin = max(start, chunk["device_sample_start"])
        end = min(stop, chunk["device_sample_start"] + chunk["sample_count"])
        offset = begin - chunk["device_sample_start"]
        selected = np.frombuffer(raw, dtype="<i2").reshape(-1, 2)[offset:offset + end - begin]
        if not np.any(selected):
            raise ValueError("selected observed chunk region contains only zero IQ")
        output[begin - start:end - start] = selected
        copied += end - begin
        provenance["verified_chunks"].append({**chunk, "selected_start_index": begin,
                                               "selected_stop_index": end,
                                               "selected_ci16_sha256": sha256(selected.tobytes())})
        provenance.pop("chunk_in_progress")
    if copied != len(output):
        raise ValueError("selected chunk copies do not exactly cover the source window")
    provenance["halo_ci16_sha256"] = sha256(output.tobytes())
    return output


def fft_geometry(score_count: int) -> tuple[int, int]:
    count = integer(score_count, "score count", minimum=1)
    blocks = (count + 446) // 447
    return blocks, 512 + 447 * (blocks - 1)


def select_model_input(conditioned, source_start: int, score_count: int) -> np.ndarray:
    if source_start % 5:
        raise ValueError("source start must have an exact canonical integer origin")
    begin = source_start * 3 // 5 - conditioned.first_canonical_index
    _, count = fft_geometry(score_count)
    if begin < 0 or begin + count > len(conditioned.samples_iq):
        raise ValueError("insufficient fully supported halo for complete unpadded FFT blocks")
    result = conditioned.samples_iq[begin:begin + count]
    if (len(result) - 65) % 447:
        raise ValueError("partial FFT input forbidden")
    return result


def derotate_ci16(samples: np.ndarray, first_index: int, cfo_hz: float) -> tuple[np.ndarray, int]:
    if not math.isfinite(cfo_hz) or abs(cfo_hz) >= CANONICAL_RATE / 2:
        raise ValueError("assisted CFO must be finite and inside canonical Nyquist")
    cycles = Fraction(str(cfo_hz)) / CANONICAL_RATE
    output = np.empty(samples.shape, dtype="<i2")
    clipped = 0
    for begin in range(0, len(samples), 2048):
        end = min(begin + 2048, len(samples))
        initial = float(((first_index + begin) * cycles) % 1)
        phase = np.remainder(initial + np.arange(end - begin) * float(cycles), 1.0)
        source = samples[begin:end, 0].astype(float) + 1j * samples[begin:end, 1]
        mixed = source * np.exp(-2j * np.pi * phase)
        rounded = np.rint(np.column_stack((mixed.real, mixed.imag)))
        clipped += int(np.count_nonzero((rounded < -32768) | (rounded > 32767)))
        output[begin:end] = np.clip(rounded, -32768, 32767).astype("<i2")
    return output, clipped


@contextmanager
def model_q17(directory: Path):
    """Bind globals BEFORE C-model state construction; restore on all exits."""
    previous = xfft_bitacc.XFFT_DATA_BITS, xfft_bitacc.XFFT_FRACTION_BITS
    xfft_bitacc.XFFT_DATA_BITS, xfft_bitacc.XFFT_FRACTION_BITS = 18, 17
    try:
        with xfft_bitacc.XfftBitAccModel(directory) as model:
            yield model
    finally:
        xfft_bitacc.XFFT_DATA_BITS, xfft_bitacc.XFFT_FRACTION_BITS = previous


def check_kernel(model, coefficients: np.ndarray) -> dict:
    if (xfft_bitacc.XFFT_DATA_BITS, xfft_bitacc.XFFT_FRACTION_BITS) != (18, 17):
        raise ValueError("kernel/model width must be 18-bit Q17")
    actual = xfft_bitacc._template_kernel(coefficients.astype(np.int64), model)
    payload = KERNEL.read_bytes()
    words = payload.decode("ascii").split()
    if len(words) != 512 or any(not re.fullmatch(r"[0-9a-fA-F]{9}", word) for word in words):
        raise ValueError("frozen Q17 kernel memory geometry mismatch")
    encoded = np.asarray([int(word, 16) for word in words], dtype=np.uint64)
    decoded = np.column_stack((encoded & 0x3ffff, encoded >> 18)).astype(np.int32)
    decoded[decoded >= 1 << 17] -= 1 << 18
    if not np.array_equal(actual, decoded):
        raise ValueError("generated 18-bit upper kernel differs from existing frozen memory")
    return {"path": str(KERNEL), "memory_sha256": sha256(payload),
            "int32le_sha256": sha256(np.asarray(actual, dtype="<i4").tobytes()),
            "data_bits": 18, "fraction_bits": 17, "word_count": 512,
            "exact_existing_kernel_match": True, "golden_regenerated": False}


def artifact(output: Path, name: str, payload: bytes) -> dict:
    path = output / name
    with path.open("xb") as destination:
        destination.write(payload)
    return {"path": str(path), "bytes": len(payload), "sha256": sha256(payload)}


def candidate_document(candidate) -> dict:
    result = {name: getattr(candidate, name) for name in (
        "phase_bin", "phase_bin_start_sample", "phase_bin_center_sample",
        "drift_bins_per_tile", "estimated_frame_period_samples", "combined_score",
        "combined_median", "tile_count")}
    for name in ("peak_to_median", "robust_z"):
        value = getattr(candidate, name)
        result[name] = value if math.isfinite(value) else None
        result[name + "_unbounded"] = math.isinf(value) and value > 0
    result["estimated_period_error_ppm"] = (
        candidate.estimated_frame_period_samples / 20_000 - 1) * 1e6
    result["passes_existing_epoch_gates"] = (
        candidate.peak_to_median >= 1.15 and candidate.robust_z >= 6.0)
    return result


def describe_maps(stream, output: Path, prefix: str, *, required_maps: int = 3) -> dict:
    config = AcquisitionConfig(phase_bin_samples=1, tile_frames=64)
    tiles = fold_phase_map_tiles(stream, config)
    if len(tiles.maps) != required_maps:
        raise ValueError(f"expected exactly {required_maps} complete 64-frame phase maps")
    map_artifact = artifact(output, prefix + ".maps.u16le",
                            np.asarray(tiles.maps, dtype="<u2").tobytes())
    maps = []
    for index, start in enumerate(tiles.tile_start_sample_indexes):
        # Block-floating score arithmetic can depend on every input in its
        # 512-word transform, not only the 66 correlation taps. Include each
        # whole intersecting overlap-save block, then the centered FIR support.
        score_start, score_stop = int(start), int(start) + 64 * 20_000
        fft_start = stream.first_sample_index + (score_start - stream.first_sample_index) // 447 * 447
        fft_stop = stream.first_sample_index + (score_stop - 1 - stream.first_sample_index) // 447 * 447 + 512
        single = replace(tiles, maps=tiles.maps[index:index + 1],
                         tile_start_sample_indexes=tiles.tile_start_sample_indexes[index:index + 1])
        maps.append({"map_index": index, "start_sample_index": int(start),
                     "stop_sample_index": int(start) + 64 * 20_000,
                     "canonical_full_fft_dependency_start_index": fft_start,
                     "canonical_full_fft_dependency_stop_index": fft_stop,
                     "source_full_fft_and_fir_dependency_start_index": (5 * fft_start - 240 + 2) // 3,
                     "source_full_fft_and_fir_dependency_stop_index": (5 * (fft_stop - 1) + 240) // 3 + 1,
                     "dependency_scope": "whole 512-input BFP blocks plus centered 481-tap 75MHz FIR support",
                     "candidate_zero_drift": candidate_document(search_phase_map_drift(single))})
    bank = _drift_bank(config, 10.0, 3.125)
    combined = candidate_document(search_phase_map_drift(tiles, drift_bins_per_tile=bank))
    return {"artifact": map_artifact, "shape": list(tiles.maps.shape),
            "encoding": "row-major unsigned16 little-endian; one row per complete map",
            "phase_bin_samples": 1, "tile_frames": 64, "maps": maps,
            "discarded_leading_scores": tiles.discarded_leading_scores,
            "discarded_trailing_scores": tiles.discarded_trailing_scores,
            "drift_bank_bins_per_tile": bank.tolist(),
            "drift_bank_ppm": (bank / 64 / 20_000 * 1e6).tolist(),
            "bounded_search_maximum_ppm": 10.0, "period_step_ppm": 3.125,
            "combined_candidate": combined,
            "three_map_existing_epoch_gates_pass": required_maps == 3
                and combined["passes_existing_epoch_gates"],
            "hardware_qualified": False, "lock_proven": False}


def replay_variant(samples: np.ndarray, *, first_index: int, score_count: int,
                   cfo_hz: float, model, coefficients: np.ndarray, output: Path,
                   name: str, kernel: dict, conditioning_clipped_components: int = 0) -> dict:
    blocks, needed = fft_geometry(score_count)
    if len(samples) != needed:
        raise ValueError("model must receive exact whole-block unpadded geometry")
    corrected, clips = derotate_ci16(samples, first_index, cfo_hz)
    result = xfft_bitacc.xfft_bitacc_match_scores(
        corrected, coefficients, model, first_sample_index=first_index)
    if (result.block_count != blocks or len(result.stream.scores) != blocks * 447
            or result.kernel_sha256 != kernel["int32le_sha256"]):
        raise ValueError("C-model block/score/kernel receipt mismatch")
    if (result.forward_overflow_blocks or result.inverse_overflow_blocks
            or result.product_overflow_blocks):
        raise ValueError("C-model arithmetic overflow")
    scores = replace(result.stream, scores=result.stream.scores[:score_count])
    if np.any(scores.scores > 255):
        raise ValueError("model returned a score outside the frozen eight-bit contract")
    score_artifact = artifact(output, name + ".scores.u8", scores.scores.astype("u1").tobytes())
    maps = describe_maps(scores, output, name)
    scrambled = _scramble_complete_frames(scores, seed=0xCA250017)
    control = describe_maps(scrambled, output, name + ".frame-scrambled")
    qualification_errors = []
    if conditioning_clipped_components:
        qualification_errors.append(f"conditioner clipped {conditioning_clipped_components} components")
    if clips:
        qualification_errors.append(f"CFO derotation clipped {clips} components")
    return {"name": name, "assisted_cfo_hz": cfo_hz,
            "externally_assisted_not_blind": name == "assisted",
            "derotation": "exp(-j*2*pi*cfo*stream_relative_canonical_index/15e6)",
            "derotation_clipped_components": clips,
            "conditioning_clipped_components": conditioning_clipped_components,
            "numerical_qualification_pass": not qualification_errors,
            "qualification_errors": qualification_errors,
            "three_map_candidate_qualified": not qualification_errors
                and maps.get("three_map_existing_epoch_gates_pass", False),
            "model_input_ci16_sha256": sha256(corrected.tobytes()),
            "model_first_canonical_index": first_index, "model_input_samples": needed,
            "block_count": blocks, "computed_score_count": blocks * 447,
            "retained_score_count": score_count, "discarded_extra_scores": blocks * 447 - score_count,
            "zero_padded_input_blocks": 0, "scores": score_artifact,
            "forward_block_exponent_histogram": dict(sorted(Counter(result.forward_block_exponents).items())),
            "inverse_block_exponent_histogram": dict(sorted(Counter(result.inverse_block_exponents).items())),
            "forward_overflow_blocks": result.forward_overflow_blocks,
            "inverse_overflow_blocks": result.inverse_overflow_blocks,
            "product_overflow_blocks": result.product_overflow_blocks,
            "maps": maps,
            "negative_control": {"kind": "independent random circular shifts of complete score frames",
                                 "seed": 0xCA250017, "independent_rf_capture": False,
                                 "maps": control}}


def checkpoint(output: Path, report: dict) -> None:
    # All artifacts live only under the newly admitted output directory.
    (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True,
                                                  allow_nan=False) + "\n")


def run(window: str, output: Path, assisted_cfo_hz: float | None = None) -> int:
    if window not in WINDOWS:
        raise ValueError("unknown fixed evidence window")
    if assisted_cfo_hz is not None and (
            not math.isfinite(assisted_cfo_hz) or abs(assisted_cfo_hz) >= CANONICAL_RATE / 2):
        raise ValueError("assisted CFO must be finite and inside canonical Nyquist")
    output = output.absolute()
    resolved = output.resolve(strict=False)
    if output != resolved or resolved == CAPTURE or CAPTURE in resolved.parents:
        raise ValueError("output must not alias or write inside the source capture")
    if not output.parent.is_dir():
        raise ValueError("output parent must already exist")
    output.mkdir(exist_ok=False)
    report = {"schema": SCHEMA, "status": "RUNNING", "stage": "admission",
              "started_utc": datetime.now(UTC).isoformat(), "window": window,
              "assisted_cfo_hz_requested": assisted_cfo_hz, "variants": [],
              "limitations": ["Evidence-selected windows, not a blind survey",
                              "Host spectral conditioner and vendor C model, not executed RTL",
                              "No native 25 MS/s FPGA, radio, timing, lock, or RF identity qualification",
                              "Frame scrambling is not an independent RF negative control",
                              "Same-window saved PSS result is not asserted"],
              "hardware_qualified": False, "lock_proven": False}
    checkpoint(output, report)
    try:
        provenance, chunks = admit_capture(window)
        report["capture"] = provenance
        report["stage"] = "chunk_validation"
        checkpoint(output, report)
        samples = load_window(provenance, chunks)
        report["stage"] = "conditioning"
        checkpoint(output, report)
        conditioned = condition_capture25(samples, first_index=provenance["source_halo_start_index"])
        del samples
        report["conditioning"] = conditioned.metadata()
        report["conditioned_ci16"] = {
            **artifact(output, "conditioned-15msps.ci16", np.asarray(conditioned.samples_iq, dtype="<i2").tobytes()),
            "sample_rate_hz": CANONICAL_RATE, "sample_count": len(conditioned.samples_iq),
            "first_canonical_index": conditioned.first_canonical_index,
            "source_center_numerator_per_index": 5, "source_center_denominator": 3,
            "cfo_assistance_applied": False, "includes_supported_halo": True,
            "format": "ci16_le", "layout": "sample_receiver_iq, RX0 only"}
        start = provenance["source_start_index"]
        count = (provenance["source_stop_index"] - start) * 3 // 5
        model_input = select_model_input(conditioned, start, count)
        report["geometry"] = {"source_start_index": start, "canonical_start_index": start * 3 // 5,
                              "requested_candidate_scores": count, "source_halo_samples_each_side": HALO,
                              "blocks": fft_geometry(count)[0], "model_input_samples": len(model_input),
                              "required_complete_maps": 3, "zero_padding_allowed": False}
        source_paths = [Path(__file__), ROOT / "tools/starlink_capture25_condition.py",
                        ROOT / "tools/starlink_pss_acquisition_study.py", KERNEL]
        source_paths += sorted((ROOT / "tests/starlink_oracle").glob("*.py"))
        frozen = output / "frozen_sources"
        frozen.mkdir()
        report["source_artifacts"] = [artifact(frozen, str(path.relative_to(ROOT)).replace("/", "__"),
                                               path.read_bytes()) for path in source_paths]
        report["stage"] = "kernel_binding"
        checkpoint(output, report)
        directory = xfft_bitacc.prepare_installed_cmodel(output / "cmodel")
        report["cmodel"] = {"archive": str(xfft_bitacc.INSTALLED_CMODEL_ARCHIVE),
                            "archive_sha256": xfft_bitacc.INSTALLED_CMODEL_SHA256,
                            "data_bits": 18, "fraction_bits": 17,
                            "twiddle_bits": 16, "fft_samples": 512,
                            "arithmetic_only_not_realtime_core_protocol": True}
        coefficients = quantize_q15(projected_pss(CANONICAL_RATE, "upper"))
        with model_q17(directory) as model:
            kernel = check_kernel(model, coefficients)
            report["kernel"] = kernel
            cases = [("baseline", 0.0)]
            if assisted_cfo_hz is not None:
                cases.append(("assisted", assisted_cfo_hz))
            for name, cfo in cases:
                report["stage"] = name
                checkpoint(output, report)
                print(f"CAPTURE25_REPLAY stage={name} window={window} blocks={fft_geometry(count)[0]}", flush=True)
                report["variants"].append(replay_variant(
                    model_input, first_index=start * 3 // 5, score_count=count,
                    cfo_hz=cfo, model=model, coefficients=coefficients,
                    output=output, name=name, kernel=kernel,
                    conditioning_clipped_components=conditioned.clipped_components))
                checkpoint(output, report)
        qualified = all(item["numerical_qualification_pass"] for item in report["variants"])
        report.update(status="REPLAY_COMPLETE" if qualified else "REPLAY_COMPLETE_NUMERICAL_QUALIFICATION_FAILED",
                      numerical_qualification_pass=qualified,
                      stage="complete", completed_utc=datetime.now(UTC).isoformat())
        checkpoint(output, report)
        return 0 if qualified else 1
    except BaseException as error:
        report.update(status="FAILED_PARTIAL", error={"type": type(error).__name__, "message": str(error)},
                      completed_utc=datetime.now(UTC).isoformat())
        checkpoint(output, report)
        print(f"CAPTURE25_REPLAY_FAILED stage={report['stage']}: {error}", file=sys.stderr)
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window", required=True, choices=tuple(WINDOWS))
    parser.add_argument("--output", required=True, type=Path, help="new directory; parent must exist")
    parser.add_argument("--assisted-cfo-hz", type=float,
                        help="externally supplied diagnostic residual correction; baseline always runs first")
    args = parser.parse_args(argv)
    try:
        return run(args.window, args.output, args.assisted_cfo_hz)
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())

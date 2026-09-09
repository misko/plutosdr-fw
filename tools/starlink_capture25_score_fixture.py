#!/usr/bin/env python3
"""Produce three real recorded-data FFT blocks for the isolated RTL replay.

Selection is fixed at the positive replay's canonical origin +5364: the whole
447-score block boundary immediately before the predeclared +5500 selection
that spans saved GLRT timing evidence. No samples or score values are planted.
Both exact corrected CI16 and1341 expected scores must match the long replay.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import starlink_capture25_pss_replay as replay
from tools.generate_starlink_pss15_pipeline_vectors import _packed_hex_lines

OFFSET = (5500 // 447) * 447
SAMPLES = 1406
SCORES = 1341
GEOMETRY = {"samples_ci16": (1406, 8), "forward_q17": (1536, 9),
            "product_q17": (1536, 9), "inverse_q17": (1536, 9),
            "forward_exponents": (3, 2), "inverse_exponents": (3, 2), "scores_u8": (1341, 2)}


def read_bounded(path: Path, maximum: int, *, expected: int | None = None) -> bytes:
    size = path.stat().st_size
    if size > maximum or (expected is not None and size != expected):
        raise ValueError("artifact byte bound/expected size mismatch")
    with path.open("rb") as source:
        payload = source.read(maximum + 1)
    if len(payload) != size:
        raise ValueError("artifact size changed during read")
    return payload


def load_recorded_slice(report_path: Path, variant: str) -> tuple[np.ndarray, dict, bytes, bytes]:
    report_path = report_path.absolute()
    if report_path.resolve(strict=True) != report_path:
        raise ValueError("replay report aliases are not admitted")
    payload = read_bounded(report_path, 256 * 1024)
    report = replay.decode_json(payload)
    if (report["schema"] != replay.SCHEMA or report["status"] != "REPLAY_COMPLETE"
            or report["numerical_qualification_pass"] is not True
            or report["window"] != "positive"):
        raise ValueError("requires the numerically qualified positive recorded replay")
    capture = report["capture"]
    if (capture["manifest_sha256"] != replay.MANIFEST_SHA256
            or capture["serial"] != replay.SERIAL or capture["stream_id"] != replay.STREAM_ID
            or capture["source_start_index"] != 900_000_000
            or capture["source_stop_index"] != 908_000_000
            or capture["continuity_segment_index"] != 13):
        raise ValueError("recorded replay is not the admitted positive source interval")
    derivative = report["conditioned_ci16"]
    path = report_path.parent / "conditioned-15msps.ci16"
    if path.resolve(strict=True) != path or derivative["path"] != str(path):
        raise ValueError("derivative must be the exact local replay artifact, without aliases")
    if (derivative["format"] != "ci16_le" or derivative["sample_rate_hz"] != 15_000_000
            or derivative["cfo_assistance_applied"] is not False
            or derivative["source_center_numerator_per_index"] != 5
            or derivative["source_center_denominator"] != 3
            or report["conditioning"]["clipped_components"] != 0):
        raise ValueError("conditioned derivative format/coordinates/clipping mismatch")
    count = replay.integer(derivative["sample_count"], "derivative sample count", minimum=1)
    if count > 4_810_000 or derivative["bytes"] != count * 4 or path.stat().st_size != count * 4:
        raise ValueError("conditioned derivative byte geometry mismatch")
    raw = read_bounded(path, 4_810_000 * 4, expected=count * 4)
    if replay.sha256(raw) != derivative["sha256"]:
        raise ValueError("conditioned derivative digest mismatch")
    origin = replay.integer(derivative["first_canonical_index"], "derivative canonical origin")
    if (origin != report["conditioning"]["first_canonical_index"]
            or report["conditioning"]["canonical_stop_index"] != origin + count
            or report["geometry"]["canonical_start_index"] != 540_000_000):
        raise ValueError("replay canonical origin/support receipt mismatch")
    variants = [item for item in report["variants"] if item["name"] == variant]
    if len(variants) != 1 or variants[0]["numerical_qualification_pass"] is not True:
        raise ValueError("expected one numerically qualified selected replay variant")
    selected = variants[0]
    cfo = selected["assisted_cfo_hz"]
    if variant == "baseline" and cfo != 0:
        raise ValueError("baseline must have no CFO assistance")
    first = report["geometry"]["canonical_start_index"] + OFFSET
    begin = first - origin
    if begin < 0 or begin + SAMPLES > count:
        raise ValueError("recorded derivative does not cover all three unpadded FFT blocks")
    all_samples = np.frombuffer(raw, dtype="<i2").reshape(-1, 2)
    samples = all_samples[begin:begin + SAMPLES].copy()
    uncorrected_hash = replay.sha256(samples.tobytes())
    corrected, clips = replay.derotate_ci16(samples, first, cfo)
    if clips:
        raise ValueError(f"fixture CFO derotation clipped {clips} components")
    # Reconstruct the frozen long replay's exact full corrected input and bind
    # its hash before selecting this window. This detects any last-bit NCO
    # phase difference from restarting a floating oscillator on a short slice.
    long_first = report["geometry"]["canonical_start_index"]
    long_count = replay.integer(selected["model_input_samples"], "long model input count", minimum=SAMPLES)
    if (long_count != report["geometry"]["model_input_samples"]
            or selected["model_first_canonical_index"] != long_first
            or (long_count - 65) % 447 or OFFSET + SAMPLES > long_count):
        raise ValueError("long model whole-block geometry mismatch")
    long_begin = long_first - origin
    if long_begin < 0 or long_begin + long_count > count:
        raise ValueError("long model input exceeds the derivative support")
    long_corrected, long_clips = replay.derotate_ci16(
        all_samples[long_begin:long_begin + long_count], long_first, cfo)
    if long_clips or replay.sha256(long_corrected.tobytes()) != selected["model_input_ci16_sha256"]:
        raise ValueError("full corrected model-input hash/clipping differs from frozen replay")
    if not np.array_equal(corrected, long_corrected[OFFSET:OFFSET + SAMPLES]):
        raise ValueError("short-window CFO phase differs from exact full corrected CI16 slice")
    score_receipt = selected["scores"]
    score_path = report_path.parent / (variant + ".scores.u8")
    if score_receipt["path"] != str(score_path) or score_path.resolve(strict=True) != score_path:
        raise ValueError("score artifact must be the exact local replay path")
    score_count = replay.integer(selected["retained_score_count"], "retained scores", minimum=OFFSET + SCORES)
    if (score_count != report["geometry"]["requested_candidate_scores"]
            or score_count > 4_800_000 or score_receipt["bytes"] != score_count
            or score_path.stat().st_size != score_count):
        raise ValueError("frozen long score-file geometry mismatch")
    score_payload = read_bounded(score_path, 4_800_000, expected=score_count)
    if replay.sha256(score_payload) != score_receipt["sha256"]:
        raise ValueError("frozen full score-file digest mismatch")
    expected_scores = score_payload[OFFSET:OFFSET + SCORES]
    return corrected, {
        "schema": "starlink-capture25-recorded-score-fixture-provenance-v1",
        "source_replay_report_path": str(report_path),
        "source_replay_report_sha256": replay.sha256(payload),
        "source_manifest_sha256": capture["manifest_sha256"],
        "source_capture": capture,
        "source_conditioning": report["conditioning"],
        "source_derivative": derivative, "variant": variant,
        "assisted_cfo_hz": cfo, "externally_assisted_not_blind": variant == "assisted",
        "selection_offset_canonical_samples": OFFSET,
        "predeclared_glrt_selection_offset": 5500,
        "selection_reason": "floor(5500/447)*447=5364 preserves full-replay BFP blocks and contains savedGLRT epoch approximately+5996",
        "selection_evidence_not_inferred_from_these_1341_scores": True,
        "first_canonical_index": first, "canonical_stop_index": first + SAMPLES,
        "source_fft_and_fir_dependency_start_index": (5 * first - 240 + 2) // 3,
        "source_fft_and_fir_dependency_stop_index": (5 * (first + SAMPLES - 1) + 240) // 3 + 1,
        "uncorrected_slice_ci16_sha256": uncorrected_hash,
        "corrected_slice_ci16_sha256": replay.sha256(corrected.tobytes()),
        "conditioning_clipped_components": 0, "derotation_clipped_components": clips,
        "block_count": 3, "samples": SAMPLES, "scores": SCORES,
        "zero_padded_input_blocks": 0, "planted_samples_or_score_peaks": False,
        "full_corrected_model_input_sha256": selected["model_input_ci16_sha256"],
        "short_corrected_ci16_equals_full_replay_slice": True,
        "full_replay_scores": score_receipt,
        "expected_score_slice_sha256": replay.sha256(expected_scores),
        "long_replay_score_subset_equivalence_asserted": False,
        "block_alignment_note": "three complete blocks starting at full-replay block12; score equality separately required",
        "hardware_or_lock_qualified": False,
        "cmodel_archive": str(replay.xfft_bitacc.INSTALLED_CMODEL_ARCHIVE),
        "cmodel_archive_sha256": replay.xfft_bitacc.INSTALLED_CMODEL_SHA256,
    }, payload, expected_scores


def trace_vectors(samples: np.ndarray, first_index: int, model, kernel: dict) -> dict[str, list[str]]:
    if samples.shape != (SAMPLES, 2):
        raise ValueError("recorded fixture requires exactly1406 CI16 samples")
    if (replay.xfft_bitacc.XFFT_DATA_BITS, replay.xfft_bitacc.XFFT_FRACTION_BITS) != (18, 17):
        raise ValueError("trace requires an already-bound18-bit Q17 C model")
    coefficients = replay.quantize_q15(replay.projected_pss(15_000_000, "upper"))
    result = replay.xfft_bitacc.xfft_bitacc_match_scores(samples, coefficients, model,
                                                      first_sample_index=first_index)
    if result.kernel_sha256 != kernel["int32le_sha256"] or result.block_count != 3:
        raise ValueError("score-model kernel/block receipt mismatch")
    kernel_complex = replay.xfft_bitacc._fixed_to_complex(result.kernel_iq, 18)
    forward, product, inverse, forward_exponents, inverse_exponents = [], [], [], [], []
    for block in range(3):
        source = samples[block * 447:block * 447 + 512]
        if source.shape != (512, 2):
            raise ValueError("padded FFT blocks forbidden")
        values = (source[:, 0].astype(float) + 1j * source[:, 1]) / (1 << 15)
        ft, fe, fo = model.block_floating_transform(values, direction=1)
        prod = replay.xfft_bitacc._multiply_spectrum(ft, kernel_complex)
        inv, ie, io = model.block_floating_transform(prod, direction=0)
        if fo or io or not (0 <= fe <= 31 and 0 <= ie <= 31):
            raise ValueError("recorded trace overflow or invalid block exponent")
        forward.append(replay.xfft_bitacc._complex_to_fixed(ft, 18))
        product.append(replay.xfft_bitacc._complex_to_fixed(prod, 18))
        inverse.append(replay.xfft_bitacc._complex_to_fixed(inv, 18))
        forward_exponents.append(fe)
        inverse_exponents.append(ie)
    if (tuple(forward_exponents) != result.forward_block_exponents
            or tuple(inverse_exponents) != result.inverse_block_exponents
            or len(result.stream.scores) != SCORES or np.any(result.stream.scores > 255)):
        raise ValueError("trace and normalized-score model receipts disagree")
    return {"samples_ci16": _packed_hex_lines(samples, 16),
            "forward_q17": _packed_hex_lines(np.vstack(forward), 18),
            "product_q17": _packed_hex_lines(np.vstack(product), 18),
            "inverse_q17": _packed_hex_lines(np.vstack(inverse), 18),
            "forward_exponents": [f"{value:02x}" for value in forward_exponents],
            "inverse_exponents": [f"{value:02x}" for value in inverse_exponents],
            "scores_u8": [f"{int(value):02x}" for value in result.stream.scores]}


def generate(report_path: Path, variant: str, output: Path) -> dict:
    if variant not in ("baseline", "assisted"):
        raise ValueError("variant must be baseline or assisted")
    output = output.absolute()
    if output.resolve(strict=False) != output or replay.CAPTURE in output.parents or output == replay.CAPTURE:
        raise ValueError("output cannot alias or write into the capture")
    if not output.parent.is_dir():
        raise ValueError("output parent must exist")
    output.mkdir(exist_ok=False)
    evidence = {"status": "RUNNING", "variant": variant, "hardware_or_lock_qualified": False}
    try:
        samples, evidence, report_payload, expected_scores = load_recorded_slice(report_path, variant)
        evidence["status"] = "RUNNING"
        replay.artifact(output, "source_replay_report.json", report_payload)
        directory = replay.xfft_bitacc.prepare_installed_cmodel(output / "cmodel")
        with replay.model_q17(directory) as model:
            coefficients = replay.quantize_q15(replay.projected_pss(15_000_000, "upper"))
            kernel = replay.check_kernel(model, coefficients)
            lines = trace_vectors(samples, evidence["first_canonical_index"], model, kernel)
        actual_scores = bytes(int(value, 16) for value in lines["scores_u8"])
        if actual_scores != expected_scores:
            raise ValueError("three-block expected scores differ from frozen full-replay1341-score slice")
        evidence["long_replay_score_subset_equivalence_asserted"] = True
        evidence["exact_score_slice_sha256"] = replay.sha256(actual_scores)
        evidence["kernel"] = kernel
        vectors = {}
        for name, rows in lines.items():
            expected_rows, width = GEOMETRY[name]
            if len(rows) != expected_rows or any(len(row) != width for row in rows):
                raise ValueError("generated recorded fixture geometry mismatch")
            receipt = replay.artifact(output, name + ".mem", ("\n".join(rows) + "\n").encode("ascii"))
            vectors[name] = {"rows": expected_rows, "hex_digits": width, "sha256": receipt["sha256"]}
        manifest = {"schema": "starlink-recorded-score-fixture-v1",
                    "source_kind": "conditioned-recorded-ci16", "input_rate_hz": 15_000_000,
                    "first_canonical_index": evidence["first_canonical_index"], "vectors": vectors}
        scores = np.array([int(value, 16) for value in lines["scores_u8"]], dtype=np.uint8)
        evidence["observed_score_summary"] = {"maximum": int(scores.max()), "minimum": int(scores.min()),
                                                "peak_relative_index": int(scores.argmax()),
                                                "nonzero_count": int(np.count_nonzero(scores))}
        frozen = output / "frozen_sources"
        frozen.mkdir()
        paths = [Path(__file__), Path(replay.__file__),
                 ROOT / "tools/generate_starlink_pss15_pipeline_vectors.py",
                 ROOT / "tools/starlink_capture25_condition.py", replay.KERNEL]
        paths += sorted((ROOT / "tests/starlink_oracle").glob("*.py"))
        evidence["source_artifacts"] = [replay.artifact(frozen, str(path.relative_to(ROOT)).replace("/", "__"),
                                                       path.read_bytes()) for path in paths]
        evidence["fixture_manifest"] = replay.artifact(output, "recorded_fixture.json",
            (json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())
        evidence.update(status="RECORDED_FIXTURE_GENERATED", completed_utc=datetime.now(UTC).isoformat())
    except BaseException as error:
        evidence.update(status="FAILED_PARTIAL", error={"type": type(error).__name__, "message": str(error)})
        (output / "fixture_provenance.json").write_text(json.dumps(evidence, indent=2, sort_keys=True,
                                                                   allow_nan=False) + "\n")
        raise
    (output / "fixture_provenance.json").write_text(json.dumps(evidence, indent=2, sort_keys=True,
                                                               allow_nan=False) + "\n")
    return evidence


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-report", required=True, type=Path)
    parser.add_argument("--variant", required=True, choices=("baseline", "assisted"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        evidence = generate(args.replay_report, args.variant, args.output)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print("RECORDED_SCORE_FIXTURE_GENERATED samples=1406 scores=1341 "
          f"variant={args.variant} maximum={evidence['observed_score_summary']['maximum']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

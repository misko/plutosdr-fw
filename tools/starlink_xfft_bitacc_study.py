#!/usr/bin/env python3
"""Qualify the finite-width 15 MS/s XFFT acquisition arithmetic offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.starlink_oracle import (
    INSTALLED_CMODEL_ARCHIVE,
    INSTALLED_CMODEL_SHA256,
    PSS_KERNEL_Q23_INT32LE_SHA256,
    SPECTRUM_PRODUCT_SHIFT,
    TEMPLATE_SCALING_SCHEDULE,
    XFFT_BITACC_SCHEMA,
    XFFT_DATA_BITS,
    XFFT_PHASE_FACTOR_BITS,
    XFFT_SAMPLES,
    XFFT_TARGET_CLOCK_MHZ,
    XFFT_TARGET_THROUGHPUT_MSPS,
    XFFT_VALID_OUTPUTS,
    AcquisitionConfig,
    XfftBitAccModel,
    fold_phase_map_tiles,
    overlap_save_fixed_match_scores,
    prepare_installed_cmodel,
    projected_pss,
    quantize_q15,
    search_phase_map_drift,
    xfft_bitacc_match_scores,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--oracle-report",
        action="append",
        required=True,
        type=Path,
        help="frozen acquisition-oracle JSON; repeat for each capture",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--cmodel-directory",
        type=Path,
        default=ROOT / "build" / "starlink-xfft-v9.1-cmodel",
    )
    parser.add_argument("--generated-at-utc")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def _generated_at_utc(value: str | None) -> str:
    if value is None:
        return datetime.now(UTC).isoformat()
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("generated-at-utc must include a time-zone offset")
    return parsed.astimezone(UTC).isoformat()


def _read_ci16(path: Path) -> np.ndarray:
    if path.suffix == ".zst":
        completed = subprocess.run(
            ["zstd", "--decompress", "--stdout", "--quiet", str(path)],
            check=True,
            stdout=subprocess.PIPE,
        )
        payload = completed.stdout
    else:
        payload = path.read_bytes()
    if len(payload) % 4:
        raise ValueError("CI16 payload size must be divisible by four")
    return np.frombuffer(payload, dtype="<i2").reshape(-1, 2).copy()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _reference_geometry(document: dict[str, Any]) -> dict[str, Any]:
    matching = [
        item
        for item in document["matched"]
        if item["phase_bin_samples"] == 1 and item["tile_frames"] == 64
    ]
    if len(matching) != 1:
        raise ValueError("oracle report must contain one 1-sample/64-frame result")
    return matching[0]


def _drift_bank(config: AcquisitionConfig) -> np.ndarray:
    ppm = np.arange(-3, 4, dtype=float) * 3.125
    per_frame = config.frame_samples * ppm * 1e-6
    return per_frame * config.tile_frames / config.phase_bin_samples


def _candidate_document(candidate: Any) -> dict[str, Any]:
    passes = candidate.peak_to_median >= 1.15 and candidate.robust_z >= 6.0
    return {
        "phase_bin": candidate.phase_bin,
        "phase_bin_start_sample": candidate.phase_bin_start_sample,
        "drift_bins_per_tile": candidate.drift_bins_per_tile,
        "estimated_frame_period_samples": candidate.estimated_frame_period_samples,
        "combined_score": candidate.combined_score,
        "combined_median": candidate.combined_median,
        "peak_to_median": candidate.peak_to_median,
        "robust_z": candidate.robust_z,
        "passes_existing_epoch_gates": passes,
    }


def _histogram(values: tuple[int, ...]) -> dict[str, int]:
    return {str(key): count for key, count in sorted(Counter(values).items())}


def _study_one(
    report_path: Path,
    model: XfftBitAccModel,
) -> dict[str, Any]:
    report_path = report_path.resolve(strict=True)
    try:
        report_name = str(report_path.relative_to(ROOT))
    except ValueError:
        report_name = str(report_path)
    oracle = json.loads(report_path.read_text())
    if oracle.get("schema") != "starlink-pss-acquisition-oracle-v1":
        raise ValueError(f"unsupported oracle report: {report_path}")
    source = Path(oracle["input"]["path"]).resolve(strict=True)
    observed_sha256 = _sha256(source)
    if observed_sha256 != oracle["input"]["compressed_sha256"]:
        raise ValueError(f"capture digest mismatch: {source}")
    samples = _read_ci16(source)
    if samples.shape[0] != oracle["input"]["sample_count"]:
        raise ValueError(f"capture sample-count mismatch: {source}")
    coefficients = quantize_q15(
        projected_pss(15_000_000, oracle["template"]["edge"])
    )

    finite = xfft_bitacc_match_scores(
        samples,
        coefficients,
        model,
        first_sample_index=oracle["input"]["first_sample_index"],
    )
    reference = overlap_save_fixed_match_scores(
        samples,
        coefficients,
        first_sample_index=oracle["input"]["first_sample_index"],
    )
    config = AcquisitionConfig()
    finite_maps = fold_phase_map_tiles(finite.stream, config)
    reference_maps = fold_phase_map_tiles(reference, config)
    finite_candidate = search_phase_map_drift(
        finite_maps, drift_bins_per_tile=_drift_bank(config)
    )
    reference_candidate = search_phase_map_drift(
        reference_maps, drift_bins_per_tile=_drift_bank(config)
    )

    score_delta = finite.stream.scores.astype(np.int16) - reference.scores.astype(
        np.int16
    )
    map_delta = finite_maps.maps.astype(np.int32) - reference_maps.maps.astype(
        np.int32
    )
    frozen_geometry = _reference_geometry(oracle)
    frozen_candidate = frozen_geometry["candidate"]
    finite_document = _candidate_document(finite_candidate)
    reference_document = _candidate_document(reference_candidate)
    decision_equal = (
        finite_document["phase_bin"] == reference_document["phase_bin"]
        and finite_document["drift_bins_per_tile"]
        == reference_document["drift_bins_per_tile"]
        and finite_document["passes_existing_epoch_gates"]
        == reference_document["passes_existing_epoch_gates"]
    )
    frozen_reproduced = (
        reference_document["phase_bin"] == frozen_candidate["phase_bin"]
        and reference_document["drift_bins_per_tile"]
        == frozen_candidate["drift_bins_per_tile"]
        and reference_document["combined_score"]
        == frozen_candidate["combined_score"]
        and math.isclose(
            reference_document["robust_z"],
            frozen_candidate["robust_z"],
            rel_tol=0,
            abs_tol=1e-12,
        )
    )
    gates = {
        "frozen_oracle_reproduced": frozen_reproduced,
        "maximum_score_error_at_most_one": int(np.max(np.abs(score_delta))) <= 1,
        "phase_cadence_and_classification_equal": decision_equal,
        "no_arithmetic_overflow": (
            finite.forward_overflow_blocks == 0
            and finite.inverse_overflow_blocks == 0
            and finite.product_overflow_blocks == 0
        ),
    }
    return {
        "oracle_report": report_name,
        "input": {
            "path": str(source),
            "compressed_sha256": observed_sha256,
            "sample_count": int(samples.shape[0]),
            "first_sample_index": oracle["input"]["first_sample_index"],
        },
        "template": {
            "edge": oracle["template"]["edge"],
            "coefficient_energy": finite.stream.coefficient_energy,
            "kernel_q23_int32le_sha256": finite.kernel_sha256,
        },
        "finite_width": {
            "score_count": int(finite.stream.scores.size),
            "block_count": finite.block_count,
            "forward_block_exponents": _histogram(
                finite.forward_block_exponents
            ),
            "inverse_block_exponents": _histogram(
                finite.inverse_block_exponents
            ),
            "forward_overflow_blocks": finite.forward_overflow_blocks,
            "inverse_overflow_blocks": finite.inverse_overflow_blocks,
            "product_overflow_blocks": finite.product_overflow_blocks,
            "candidate": finite_document,
        },
        "exact_integer_reference": {
            "candidate": reference_document,
            "maximum_fft_rounding_residual": reference.maximum_fft_rounding_residual,
        },
        "difference": {
            "score_equal_count": int(np.count_nonzero(score_delta == 0)),
            "score_error_count": int(np.count_nonzero(score_delta != 0)),
            "score_error_fraction": float(np.mean(score_delta != 0)),
            "score_delta_min": int(np.min(score_delta)),
            "score_delta_max": int(np.max(score_delta)),
            "score_delta_mean_absolute": float(np.mean(np.abs(score_delta))),
            "map_equal_count": int(np.count_nonzero(map_delta == 0)),
            "map_cell_count": int(map_delta.size),
            "map_delta_min": int(np.min(map_delta)),
            "map_delta_max": int(np.max(map_delta)),
            "phase_cadence_and_classification_equal": decision_equal,
        },
        "gates": gates,
        "passes": all(gates.values()),
    }


def main() -> None:
    args = _arguments()
    output = args.output.resolve(strict=False)
    if output.exists() and not args.force:
        raise FileExistsError(f"refusing to replace existing output: {output}")
    cmodel_directory = prepare_installed_cmodel(args.cmodel_directory)
    with XfftBitAccModel(cmodel_directory) as model:
        captures = [_study_one(path, model) for path in args.oracle_report]
    gates = {
        "every_capture_passes": all(item["passes"] for item in captures),
        "positive_and_negative_present": (
            any(
                item["exact_integer_reference"]["candidate"][
                    "passes_existing_epoch_gates"
                ]
                for item in captures
            )
            and any(
                not item["exact_integer_reference"]["candidate"][
                    "passes_existing_epoch_gates"
                ]
                for item in captures
            )
        ),
    }
    document = {
        "schema": XFFT_BITACC_SCHEMA,
        "analysis_kind": "offline-xilinx-xfft-finite-width-acquisition-study",
        "generated_at_utc": _generated_at_utc(args.generated_at_utc),
        "candidate_only": True,
        "hardware_qualified": False,
        "live_pss_qualified": False,
        "cmodel": {
            "vivado_version": "2022.2",
            "xfft_version": "9.1",
            "installed_archive": str(INSTALLED_CMODEL_ARCHIVE),
            "archive_sha256": INSTALLED_CMODEL_SHA256,
            "proprietary_files_retained_in_source": False,
        },
        "configuration": {
            "transform_samples": XFFT_SAMPLES,
            "valid_outputs_per_block": XFFT_VALID_OUTPUTS,
            "data_bits": XFFT_DATA_BITS,
            "phase_factor_bits": XFFT_PHASE_FACTOR_BITS,
            "scaling": "block_floating_point",
            "rounding": "convergent_ties_to_even",
            "template_scaling_schedule": list(TEMPLATE_SCALING_SCHEDULE),
            "spectrum_product_shift": SPECTRUM_PRODUCT_SHIFT,
            "output_ordering": "natural",
            "architecture": "radix_4_burst",
            "target_clock_mhz": XFFT_TARGET_CLOCK_MHZ,
            "target_throughput_msps": XFFT_TARGET_THROUGHPUT_MSPS,
            "pss_kernel_q23_int32le_sha256": PSS_KERNEL_Q23_INT32LE_SHA256,
        },
        "captures": captures,
        "gates": gates,
        "passes": all(gates.values()),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    if not document["passes"]:
        raise SystemExit("STARLINK_XFFT_BITACC_FAIL: one or more gates failed")
    print(
        "STARLINK_XFFT_BITACC_PASS "
        f"captures={len(captures)} data_bits={XFFT_DATA_BITS} "
        f"max_score_error={max(max(abs(item['difference']['score_delta_min']), abs(item['difference']['score_delta_max'])) for item in captures)}"
    )


if __name__ == "__main__":
    main()

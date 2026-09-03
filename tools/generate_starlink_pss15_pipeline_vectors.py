#!/usr/bin/env python3
"""Generate deterministic three-block vectors for the real XFFT RTL replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.starlink_oracle import (
    INSTALLED_CMODEL_ARCHIVE,
    XFFT_BITACC_SCHEMA,
    XFFT_SAMPLES,
    XFFT_VALID_OUTPUTS,
    XfftBitAccModel,
    prepare_installed_cmodel,
    projected_pss,
    quantize_q15,
    xfft_bitacc_match_scores,
)
from tests.starlink_oracle import xfft_bitacc as xfft_model
from tests.starlink_oracle.xfft_bitacc import (
    _complex_to_fixed,
    _fixed_to_complex,
    _multiply_spectrum,
)

SCHEMA = "starlink-pss15-generated-xfft-pipeline-vectors-v2"
DEFAULT_DATA_BITS = 18
SAMPLE_COUNT = 1406
BLOCK_COUNT = 3
SCORE_COUNT = BLOCK_COUNT * XFFT_VALID_OUTPUTS
FIRST_SAMPLE_INDEX = 1_000_000
PSS_STARTS = (100, 447, 1000)
RANDOM_SEED = 0x15F17E


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _packed_hex_lines(values: np.ndarray, component_bits: int) -> list[str]:
    mask = (1 << component_bits) - 1
    digits = (2 * component_bits + 3) // 4
    return [
        f"{((int(q) & mask) << component_bits) | (int(i) & mask):0{digits}x}"
        for i, q in values
    ]


def _write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def generate(
    output_directory: Path, *, data_bits: int = DEFAULT_DATA_BITS
) -> dict[str, object]:
    if data_bits < 17 or data_bits > 24:
        raise ValueError("data_bits must use the XFFT 24-bit AXI component slot")
    # The frozen v1 model exposes its width as module configuration. Keep the
    # arithmetic implementation unchanged while selecting the measured width
    # before either fixed or block-floating C-model state is constructed.
    xfft_model.XFFT_DATA_BITS = data_bits
    xfft_model.XFFT_FRACTION_BITS = data_bits - 1
    output_directory.mkdir(parents=True, exist_ok=True)
    coefficients = quantize_q15(projected_pss(15_000_000, "upper"))
    rng = np.random.default_rng(RANDOM_SEED)
    samples = rng.integers(-1200, 1201, size=(SAMPLE_COUNT, 2), dtype=np.int16)
    for start in PSS_STARTS:
        samples[start : start + coefficients.shape[0]] = coefficients

    with TemporaryDirectory(prefix="starlink-pss15-xfft-cmodel-") as model_temp:
        model_directory = prepare_installed_cmodel(Path(model_temp))
        with XfftBitAccModel(model_directory) as model:
            result = xfft_bitacc_match_scores(
                samples,
                coefficients,
                model,
                first_sample_index=FIRST_SAMPLE_INDEX,
            )
            kernel_complex = _fixed_to_complex(result.kernel_iq, data_bits)
            forward_blocks: list[np.ndarray] = []
            product_blocks: list[np.ndarray] = []
            inverse_blocks: list[np.ndarray] = []
            forward_exponents: list[int] = []
            inverse_exponents: list[int] = []
            for block_number in range(BLOCK_COUNT):
                block_start = block_number * XFFT_VALID_OUTPUTS
                source = samples[block_start : block_start + XFFT_SAMPLES]
                assert source.shape == (XFFT_SAMPLES, 2)
                input_complex = (source[:, 0] + 1j * source[:, 1]) / float(1 << 15)
                forward, forward_exponent, forward_overflow = (
                    model.block_floating_transform(input_complex, direction=1)
                )
                if forward_overflow:
                    raise RuntimeError(f"forward block {block_number} overflowed")
                forward_iq = _complex_to_fixed(forward, data_bits)
                product = _multiply_spectrum(forward, kernel_complex)
                product_iq = _complex_to_fixed(product, data_bits)
                inverse, inverse_exponent, inverse_overflow = (
                    model.block_floating_transform(product, direction=0)
                )
                if inverse_overflow:
                    raise RuntimeError(f"inverse block {block_number} overflowed")
                inverse_iq = _complex_to_fixed(inverse, data_bits)
                forward_blocks.append(forward_iq)
                product_blocks.append(product_iq)
                inverse_blocks.append(inverse_iq)
                forward_exponents.append(forward_exponent)
                inverse_exponents.append(inverse_exponent)

    if tuple(forward_exponents) != result.forward_block_exponents:
        raise RuntimeError("forward trace exponents disagree with score replay")
    if tuple(inverse_exponents) != result.inverse_block_exponents:
        raise RuntimeError("inverse trace exponents disagree with score replay")
    if result.stream.scores.shape != (SCORE_COUNT,):
        raise RuntimeError("unexpected score count")
    for start in PSS_STARTS:
        if int(result.stream.scores[start]) != 255:
            raise RuntimeError(f"injected PSS at {start} did not score 255")

    payloads = {
        "samples_ci16.mem": _packed_hex_lines(samples, 16),
        f"forward_q{data_bits-1}.mem": _packed_hex_lines(
            np.vstack(forward_blocks), data_bits
        ),
        f"product_q{data_bits-1}.mem": _packed_hex_lines(
            np.vstack(product_blocks), data_bits
        ),
        f"inverse_q{data_bits-1}.mem": _packed_hex_lines(
            np.vstack(inverse_blocks), data_bits
        ),
        "forward_exponents.mem": [f"{value:02x}" for value in forward_exponents],
        "inverse_exponents.mem": [f"{value:02x}" for value in inverse_exponents],
        "scores_u8.mem": [f"{int(value):02x}" for value in result.stream.scores],
    }
    for name, lines in payloads.items():
        _write_lines(output_directory / name, lines)

    files = {
        name: {
            "lines": len(lines),
            "sha256": _sha256(output_directory / name),
        }
        for name, lines in payloads.items()
    }
    evidence: dict[str, object] = {
        "schema": SCHEMA,
        "oracle_schema": XFFT_BITACC_SCHEMA,
        "sample_rate_hz": 15_000_000,
        "acquisition_clock_hz": 100_000_000,
        "sample_count": SAMPLE_COUNT,
        "block_count": BLOCK_COUNT,
        "fft_samples": XFFT_SAMPLES,
        "data_bits": data_bits,
        "valid_scores_per_block": XFFT_VALID_OUTPUTS,
        "score_count": SCORE_COUNT,
        "first_sample_index": FIRST_SAMPLE_INDEX,
        "pss_starts_relative": list(PSS_STARTS),
        "pss_starts_absolute": [FIRST_SAMPLE_INDEX + start for start in PSS_STARTS],
        "pss_scores": [int(result.stream.scores[start]) for start in PSS_STARTS],
        "forward_block_exponents": forward_exponents,
        "inverse_block_exponents": inverse_exponents,
        "score_minimum": int(result.stream.scores.min()),
        "score_maximum": int(result.stream.scores.max()),
        "nonzero_score_count": int(np.count_nonzero(result.stream.scores)),
        "random_seed": RANDOM_SEED,
        "installed_cmodel_archive": str(INSTALLED_CMODEL_ARCHIVE),
        "files": files,
    }
    evidence_path = output_directory / "pipeline_vectors.json"
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "STARLINK_PSS15_PIPELINE_VECTORS_PASS "
        f"samples={SAMPLE_COUNT} blocks={BLOCK_COUNT} scores={SCORE_COUNT} "
        f"forward_exponents={forward_exponents} "
        f"inverse_exponents={inverse_exponents} "
        f"nonzero_scores={evidence['nonzero_score_count']}"
    )
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--data-bits", type=int, default=DEFAULT_DATA_BITS)
    arguments = parser.parse_args()
    generate(arguments.output_directory.resolve(), data_bits=arguments.data_bits)


if __name__ == "__main__":
    main()

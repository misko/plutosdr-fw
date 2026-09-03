#!/usr/bin/env python3
"""Generate bit-exact 60 MS/s cascade-to-XFFT end-to-end replay vectors."""

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

from tests.starlink_oracle import (  # noqa: E402
    XFFT_BITACC_SCHEMA,
    XFFT_SAMPLES,
    XFFT_VALID_OUTPUTS,
    XfftBitAccModel,
    conditioned_pss_x4,
    ddc_x4_contract_sha256,
    prepare_installed_cmodel,
    projected_pss,
    quantize_q15,
    x4_ddc_ci16,
    xfft_bitacc_match_scores,
)
from tests.starlink_oracle import xfft_bitacc as xfft_model  # noqa: E402
from tests.starlink_oracle.xfft_bitacc import (  # noqa: E402
    _complex_to_fixed,
    _fixed_to_complex,
    _multiply_spectrum,
)


SCHEMA = "starlink-pss60-ddc-to-xfft-v1"
DATA_BITS = 18
SOURCE_SAMPLE_COUNT = 5666
ACQUISITION_SAMPLE_COUNT = 1406
BLOCK_COUNT = 3
SCORE_COUNT = BLOCK_COUNT * XFFT_VALID_OUTPUTS
FIRST_SOURCE_INDEX = 4_000_000
FIRST_ACQUISITION_INDEX = 1_000_006
PSS_SCORE_OFFSETS = (100, 447, 1000)
RANDOM_SEED = 0x60DDC


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


def generate(output_directory: Path) -> dict[str, object]:
    xfft_model.XFFT_DATA_BITS = DATA_BITS
    xfft_model.XFFT_FRACTION_BITS = DATA_BITS - 1
    output_directory.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(RANDOM_SEED)
    source_samples = rng.integers(
        -600, 601, size=(SOURCE_SAMPLE_COUNT, 2), dtype=np.int16
    )
    source_pss = quantize_q15(projected_pss(60_000_000, "upper"))
    source_pss_starts: list[int] = []
    for score_offset in PSS_SCORE_OFFSETS:
        source_start = 24 + 4 * score_offset
        source_pss_starts.append(source_start)
        source_samples[source_start : source_start + 264] = source_pss

    ddc = x4_ddc_ci16(
        source_samples,
        first_input_index=FIRST_SOURCE_INDEX,
        edge="upper",
    )
    if ddc.samples_iq.shape != (ACQUISITION_SAMPLE_COUNT, 2):
        raise RuntimeError("unexpected x4 DDC output geometry")
    if int(ddc.output_indexes[0]) != FIRST_ACQUISITION_INDEX:
        raise RuntimeError("unexpected first acquisition index")
    if not bool(ddc.output_gaps[0]) or np.count_nonzero(ddc.output_gaps) != 1:
        raise RuntimeError("unexpected x4 DDC gap contract")
    if ddc.discontinuities != 1 or ddc.saturation_events != 0:
        raise RuntimeError("clean x4 DDC replay was not clean")

    coefficients = quantize_q15(conditioned_pss_x4("upper"))
    with TemporaryDirectory(prefix="starlink-pss60-ddc-xfft-") as temporary:
        model_directory = prepare_installed_cmodel(Path(temporary))
        with XfftBitAccModel(model_directory) as model:
            result = xfft_bitacc_match_scores(
                ddc.samples_iq,
                coefficients,
                model,
                first_sample_index=FIRST_ACQUISITION_INDEX,
            )
            kernel_complex = _fixed_to_complex(result.kernel_iq, DATA_BITS)
            forward_blocks: list[np.ndarray] = []
            product_blocks: list[np.ndarray] = []
            inverse_blocks: list[np.ndarray] = []
            forward_exponents: list[int] = []
            inverse_exponents: list[int] = []
            for block_number in range(BLOCK_COUNT):
                block_start = block_number * XFFT_VALID_OUTPUTS
                source = ddc.samples_iq[block_start : block_start + XFFT_SAMPLES]
                if source.shape != (XFFT_SAMPLES, 2):
                    raise RuntimeError("incomplete replay FFT block")
                source_complex = (source[:, 0] + 1j * source[:, 1]) / float(
                    1 << 15
                )
                forward, forward_exponent, forward_overflow = (
                    model.block_floating_transform(source_complex, direction=1)
                )
                if forward_overflow:
                    raise RuntimeError(f"forward block {block_number} overflowed")
                forward_iq = _complex_to_fixed(forward, DATA_BITS)
                product = _multiply_spectrum(forward, kernel_complex)
                product_iq = _complex_to_fixed(product, DATA_BITS)
                inverse, inverse_exponent, inverse_overflow = (
                    model.block_floating_transform(product, direction=0)
                )
                if inverse_overflow:
                    raise RuntimeError(f"inverse block {block_number} overflowed")
                inverse_iq = _complex_to_fixed(inverse, DATA_BITS)
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
    for offset in PSS_SCORE_OFFSETS:
        if int(result.stream.scores[offset]) != 255:
            raise RuntimeError(f"PSS control at score {offset} was not full scale")

    payloads = {
        "source_ci16.mem": _packed_hex_lines(source_samples, 16),
        "ddc_ci16.mem": _packed_hex_lines(ddc.samples_iq, 16),
        "forward_q17.mem": _packed_hex_lines(np.vstack(forward_blocks), DATA_BITS),
        "product_q17.mem": _packed_hex_lines(np.vstack(product_blocks), DATA_BITS),
        "inverse_q17.mem": _packed_hex_lines(np.vstack(inverse_blocks), DATA_BITS),
        "forward_exponents.mem": [f"{value:02x}" for value in forward_exponents],
        "inverse_exponents.mem": [f"{value:02x}" for value in inverse_exponents],
        "scores_u8.mem": [f"{int(value):02x}" for value in result.stream.scores],
    }
    for name, lines in payloads.items():
        _write_lines(output_directory / name, lines)

    files = {
        name: {"lines": len(lines), "sha256": _sha256(output_directory / name)}
        for name, lines in payloads.items()
    }
    evidence: dict[str, object] = {
        "schema": SCHEMA,
        "oracle_schema": XFFT_BITACC_SCHEMA,
        "source_sample_rate_hz": 60_000_000,
        "acquisition_sample_rate_hz": 15_000_000,
        "acquisition_clock_hz": 100_000_000,
        "source_sample_count": SOURCE_SAMPLE_COUNT,
        "stage_60_to_30_sample_count": int(
            ddc.stage_60_to_30.samples_iq.shape[0]
        ),
        "acquisition_sample_count": ACQUISITION_SAMPLE_COUNT,
        "score_count": SCORE_COUNT,
        "block_count": BLOCK_COUNT,
        "first_source_index": FIRST_SOURCE_INDEX,
        "first_acquisition_index": FIRST_ACQUISITION_INDEX,
        "source_pss_starts_relative": source_pss_starts,
        "pss_score_offsets": list(PSS_SCORE_OFFSETS),
        "pss_scores": [int(result.stream.scores[o]) for o in PSS_SCORE_OFFSETS],
        "coefficient_energy": result.stream.coefficient_energy,
        "kernel_canonical_sha256": result.kernel_sha256,
        "ddc_x4_contract_sha256": ddc_x4_contract_sha256(),
        "ddc_discontinuities": ddc.discontinuities,
        "ddc_saturation_events": ddc.saturation_events,
        "forward_block_exponents": forward_exponents,
        "inverse_block_exponents": inverse_exponents,
        "score_minimum": int(result.stream.scores.min()),
        "score_maximum": int(result.stream.scores.max()),
        "nonzero_score_count": int(np.count_nonzero(result.stream.scores)),
        "random_seed": RANDOM_SEED,
        "files": files,
    }
    (output_directory / "ddc_xfft_vectors.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "STARLINK_PSS60_DDC_XFFT_VECTORS_PASS "
        f"source={SOURCE_SAMPLE_COUNT} stage30={evidence['stage_60_to_30_sample_count']} "
        f"acquisition={ACQUISITION_SAMPLE_COUNT} scores={SCORE_COUNT} "
        f"pss255=3 kernel={result.kernel_sha256}"
    )
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_directory", type=Path)
    arguments = parser.parse_args()
    generate(arguments.output_directory.resolve())


if __name__ == "__main__":
    main()

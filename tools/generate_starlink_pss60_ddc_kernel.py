#!/usr/bin/env python3
"""Generate the immutable 18-bit XFFT kernel for the 60->15 MS/s cascade."""

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
    XfftBitAccModel,
    conditioned_pss_x4,
    ddc_x4_contract_sha256,
    prepare_installed_cmodel,
    quantize_q15,
)
from tests.starlink_oracle import xfft_bitacc as xfft_model  # noqa: E402
from tests.starlink_oracle.waveforms import complex64_sha256  # noqa: E402
from tests.starlink_oracle.xfft_bitacc import _template_kernel  # noqa: E402


SCHEMA = "starlink-pss60-x4-ddc-kernel-v1"
DATA_BITS = 18
EDGE = "upper"


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def generate(output_directory: Path) -> dict[str, object]:
    output_directory.mkdir(parents=True, exist_ok=True)
    template = conditioned_pss_x4(EDGE)
    coefficients = quantize_q15(template)
    coefficients_wide = np.asarray(coefficients, dtype=np.int64)
    coefficient_energy = int(
        np.sum(
            coefficients_wide[:, 0] * coefficients_wide[:, 0]
            + coefficients_wide[:, 1] * coefficients_wide[:, 1],
            dtype=np.int64,
        )
    )

    xfft_model.XFFT_DATA_BITS = DATA_BITS
    xfft_model.XFFT_FRACTION_BITS = DATA_BITS - 1
    with TemporaryDirectory(prefix="starlink-pss60-ddc-kernel-") as temporary:
        model_directory = prepare_installed_cmodel(Path(temporary))
        with XfftBitAccModel(model_directory) as model:
            kernel = _template_kernel(coefficients_wide, model)

    mask = (1 << DATA_BITS) - 1
    digits = (2 * DATA_BITS + 3) // 4
    lines = [
        f"{((int(q) & mask) << DATA_BITS) | (int(i) & mask):0{digits}x}"
        for i, q in kernel
    ]
    memory_payload = ("\n".join(lines) + "\n").encode("ascii")
    canonical_payload = np.asarray(kernel, dtype="<i4").tobytes(order="C")
    coefficient_payload = np.asarray(coefficients, dtype="<i2").tobytes(
        order="C"
    )

    memory_path = output_directory / "upper_edge_pss60_x4_ddc_kernel_q17.mem"
    memory_path.write_bytes(memory_payload)
    evidence: dict[str, object] = {
        "schema": SCHEMA,
        "input_sample_rate_hz": 60_000_000,
        "acquisition_sample_rate_hz": 15_000_000,
        "edge": EDGE,
        "data_bits": DATA_BITS,
        "kernel_words": int(kernel.shape[0]),
        "template_samples": int(coefficients.shape[0]),
        "coefficient_energy": coefficient_energy,
        "ddc_x4_contract_sha256": ddc_x4_contract_sha256(),
        "conditioned_template_complex64_sha256": complex64_sha256(template),
        "coefficient_ci16_sha256": _sha256_bytes(coefficient_payload),
        "kernel_canonical_sha256": _sha256_bytes(canonical_payload),
        "kernel_memory_sha256": _sha256_bytes(memory_payload),
    }
    (output_directory / "upper_edge_pss60_x4_ddc_kernel_q17.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "STARLINK_PSS60_DDC_KERNEL_PASS "
        f"words={kernel.shape[0]} energy={coefficient_energy} "
        f"canonical_sha256={evidence['kernel_canonical_sha256']}"
    )
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_directory", type=Path)
    arguments = parser.parse_args()
    generate(arguments.output_directory.resolve())


if __name__ == "__main__":
    main()

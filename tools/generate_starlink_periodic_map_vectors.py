#!/usr/bin/env python3
"""Compact 447-period arithmetic/geometry stress oracle; not an RF fixture.

Independent integer product/energy/normalization/map arithmetic surrounds the
installed bit-accurate FFT C model. Existing goldens are bootstrap inputs only.
No global width configuration or pre-existing file is changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.starlink_oracle import projected_pss, quantize_q15
from tests.starlink_oracle.xfft_bitacc import (
    INSTALLED_CMODEL_ARCHIVE,
    XfftBitAccModel,
    _Generics,
    prepare_installed_cmodel,
)

PERIOD, FFT, TAPS, ENERGY = 447, 512, 66, 1073742825
SCHEMA = "starlink-periodic-bank-map-v1"
KERNEL = ROOT / "hdl/library/starlink_pss_acquisition/tb/upper_edge_pss_kernel_q17.mem"
GOLDENS = {
    "samples_ci16": (1406, 8),
    "forward_q17": (1536, 9),
    "product_q17": (1536, 9),
    "inverse_q17": (1536, 9),
    "forward_exponents": (3, 2),
    "inverse_exponents": (3, 2),
    "scores_u8": (1341, 2),
}
GOLDEN_SHA256 = {
    "samples_ci16": "4abe27ba953cf49f84d9979966625a2436ad59359b616321e881b42dd4c84723",
    "forward_q17": "d934a8ecd0888c294fc0abfbdbe7c439bff7097ea169b937638c4b7000479bfd",
    "product_q17": "b316522a68529a73d3d8e4121badea61e24621c93a97365e894f5bd416bcecb7",
    "inverse_q17": "c8c5b4e28ab621d0b1d5c1dc288f6e66495b3319d348442ce5d7b8f6ea8025a1",
    "forward_exponents": "18ac6df6a1ae3f19e5153524b33f336a60eabdd6dbd182d46c43450302e4b52f",
    "inverse_exponents": "899b7a2486fd3759c6e4905110fc4d86ffdb6ec884da2a7f2aca4acdfd363dff",
    "scores_u8": "c22f751a2a82244268dd9ea4989c4ff3b5364c172526e80886c5da3d1959e45d",
}


class Model18(XfftBitAccModel):
    def _create_state(self, *, block_floating):
        state = self._library.xilinx_ip_xfft_v9_1_create_state(
            _Generics(9, 1, 0, 0, 18, 16, 1, int(block_floating), 1)
        )
        if not state:
            raise RuntimeError("C model refused frozen 18-bit generics")
        return state


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def round_even(numerator, denominator):
    """Signed integer division, exact ties to even, no float arithmetic."""
    if denominator <= 0:
        raise ValueError("positive denominator required")
    quotient, remainder = divmod(numerator, denominator)
    return quotient + int(
        2 * remainder > denominator or (2 * remainder == denominator and quotient % 2)
    )


def normalize(numerator, denominator):
    if numerator <= 0 or denominator <= 0:
        return 0
    if numerator >= denominator:
        return 255
    return round_even(numerator * 255, denominator)


def saturating_numerator(power, shift):
    if not 0 <= power < 1 << 36 or not 0 <= shift < 128:
        raise ValueError("requires unsigned36 correlation power and unsigned7 shift")
    raw = power << shift
    return min(raw, (1 << 69) - 1), int(raw >= 1 << 69)


def unpack(words, bits):
    mask = (1 << bits) - 1

    def signed(value):
        return value - (1 << bits) if value & (1 << (bits - 1)) else value

    return np.array(
        [[signed(w & mask), signed((w >> bits) & mask)] for w in words], dtype=np.int64
    )


def pack(values, bits):
    mask = (1 << bits) - 1
    return [((int(q) & mask) << bits) | (int(i) & mask) for i, q in values]


def fixed18(values):
    scaled = np.column_stack((values.real, values.imag)) * (1 << 17)
    rounded = np.rint(scaled).astype(np.int64)
    if (
        not np.array_equal(scaled, rounded)
        or np.any(rounded < -(1 << 17))
        or np.any(rounded >= (1 << 17))
    ):
        raise ArithmeticError("C model returned non-Q17 or overflowing word")
    return rounded


def complex_fixed(values, fraction_bits):
    return (values[:, 0] + 1j * values[:, 1]) / (1 << fraction_bits)


def derive_kernel(model):
    coefficients = quantize_q15(projected_pss(15_000_000, "upper")).astype(np.int64)
    if coefficients.shape != (TAPS, 2) or int(np.sum(coefficients**2)) != ENERGY:
        raise ArithmeticError("frozen coefficient support/energy changed")
    padded = np.zeros(FFT, dtype=np.complex128)
    padded[:TAPS] = np.conj(complex_fixed(coefficients, 15)[::-1])
    transformed, _, overflow = model.fixed_transform(
        padded, direction=1, schedule=(2, 0, 0, 0, 0)
    )
    if overflow:
        raise ArithmeticError("derived kernel overflow")
    kernel = fixed18(transformed)
    serialized = "".join(f"{word:09x}\n" for word in pack(kernel, 18)).encode("ascii")
    if serialized != KERNEL.read_bytes():
        raise ArithmeticError(
            "independently derived kernel does not byte-match frozen kernel"
        )
    return kernel


def block_oracle(source, kernel, model):
    if source.shape != (FFT, 2):
        raise ValueError("exactly 512 CI16 samples required")
    forward, ef, overflow = model.block_floating_transform(
        complex_fixed(source, 15), direction=1
    )
    if overflow:
        raise ArithmeticError("forward overflow")
    forward = fixed18(forward)
    product = np.array(
        [
            [
                round_even(int(fi) * int(ki) - int(fq) * int(kq), 1 << 18),
                round_even(int(fi) * int(kq) + int(fq) * int(ki), 1 << 18),
            ]
            for (fi, fq), (ki, kq) in zip(forward, kernel, strict=True)
        ],
        dtype=np.int64,
    )
    if np.any(product < -(1 << 17)) or np.any(product >= (1 << 17)):
        raise ArithmeticError("spectrum product overflow")
    inverse, ei, overflow = model.block_floating_transform(
        complex_fixed(product, 17), direction=0
    )
    if overflow:
        raise ArithmeticError("inverse overflow")
    inverse = fixed18(inverse)
    energies = [
        sum(int(i) ** 2 + int(q) ** 2 for i, q in source[p : p + TAPS])
        for p in range(PERIOD)
    ]
    shift = 2 * (7 + ef + ei)
    prepared = [
        saturating_numerator(int(i) ** 2 + int(q) ** 2, shift)
        for i, q in inverse[TAPS - 1 :]
    ]
    numerators = [n for n, _ in prepared]
    denominators = [energy * ENERGY for energy in energies]
    return {
        "forward_q17": pack(forward, 18),
        "product_q17": pack(product, 18),
        "inverse_q17": pack(inverse, 18),
        "forward_exponents": [ef],
        "inverse_exponents": [ei],
        "energies_u38": energies,
        "numerators_u69": numerators,
        "denominators_u69": denominators,
        "saturated_u1": [sat for _, sat in prepared],
        "power_shift_u7": [shift],
        "scores_u8": [
            normalize(n, d) for n, d in zip(numerators, denominators, strict=True)
        ],
    }


def map_words(scores, bins, frames):
    if (
        len(scores) != PERIOD
        or bins not in (343, 20000)
        or frames != {343: 2, 20000: 64}[bins]
    ):
        raise ValueError("only frozen smoke/production geometry is admitted")
    return [
        sum(scores[(phase + frame * bins) % PERIOD] for frame in range(frames))
        for phase in range(bins)
    ]


def support(bins, frames):
    selected = bins * frames
    blocks = (selected + PERIOD - 1) // PERIOD
    return {
        "selected_scores": selected,
        "blocks": blocks,
        "full_block_scores": blocks * PERIOD,
        "fft_source_samples": (blocks - 1) * PERIOD + FFT,
        "direct_tap_support_samples": selected + TAPS - 1,
        "potential_tail_scores": blocks * PERIOD - selected,
        "last_block_selected": (selected - 1) % PERIOD + 1,
    }


def load_original(directory):
    result = {}
    for name, (rows, width) in GOLDENS.items():
        data = (directory / f"{name}.mem").read_text(encoding="ascii").splitlines()
        if len(data) != rows or any(
            len(row) != width or any(c not in "0123456789abcdefABCDEF" for c in row)
            for row in data
        ):
            raise ValueError(f"malformed original golden {name}")
        if digest(directory / f"{name}.mem") != GOLDEN_SHA256[name]:
            raise ValueError(f"immutable original golden SHA256 mismatch: {name}")
        result[name] = [int(row, 16) for row in data]
    return result


def generate(output, original):
    if output.exists() or output.is_symlink():
        raise FileExistsError("refusing to overwrite periodic evidence")
    originals = load_original(original)
    source = unpack(originals["samples_ci16"], 16)
    output.mkdir(parents=True)
    with TemporaryDirectory(prefix="cmodel-", dir=output) as temporary:
        model_dir = prepare_installed_cmodel(Path(temporary))
        library_hashes = {
            path.name: digest(path) for path in sorted(model_dir.iterdir())
        }
        with Model18(model_dir) as model:
            kernel = derive_kernel(model)
            # Bootstrap is not a new expected-value generation: original files
            # remain immutable and every original intermediate/score is compared.
            for block in range(3):
                trace = block_oracle(
                    source[block * PERIOD : block * PERIOD + FFT], kernel, model
                )
                for name in GOLDENS:
                    if name == "samples_ci16":
                        continue
                    count = len(trace[name])
                    if (
                        trace[name]
                        != originals[name][block * count : (block + 1) * count]
                    ):
                        raise ArithmeticError(
                            f"original golden bootstrap mismatch: {name} block {block}"
                        )
            periodic = source[:PERIOD]
            trace = block_oracle(periodic[np.arange(FFT) % PERIOD], kernel, model)
    trace["period_ci16"] = pack(periodic, 16)
    trace["map_smoke_u16"] = map_words(trace["scores_u8"], 343, 2)
    trace["map_production_u16"] = map_words(trace["scores_u8"], 20000, 64)
    widths = {
        "period_ci16": 8,
        "forward_q17": 9,
        "product_q17": 9,
        "inverse_q17": 9,
        "forward_exponents": 2,
        "inverse_exponents": 2,
        "energies_u38": 10,
        "numerators_u69": 18,
        "denominators_u69": 18,
        "saturated_u1": 1,
        "power_shift_u7": 2,
        "scores_u8": 2,
        "map_smoke_u16": 4,
        "map_production_u16": 4,
    }
    files = {}
    for name, values in trace.items():
        path = output / f"{name}.mem"
        path.write_text(
            "".join(f"{value:0{widths[name]}x}\n" for value in values), encoding="ascii"
        )
        files[path.name] = {
            "rows": len(values),
            "hex_width": widths[name],
            "sha256": digest(path),
        }
    oracle_sources = [
        ROOT / "tests/starlink_oracle" / name
        for name in (
            "__init__.py",
            "xfft_bitacc.py",
            "fixed.py",
            "waveforms.py",
            "numerology.py",
            "acquisition.py",
            "ddc.py",
            "search.py",
        )
    ]
    inputs = (
        [
            Path(__file__),
            KERNEL,
            INSTALLED_CMODEL_ARCHIVE,
        ]
        + oracle_sources
        + [original / f"{name}.mem" for name in GOLDENS]
    )
    # Compact byte-for-byte provenance; no extracted proprietary C-model
    # binaries, expanded production IQ, or derived replacement kernel.
    for directory, sources in [
        ("original_goldens", [original / f"{name}.mem" for name in GOLDENS]),
        ("oracle_sources", [Path(__file__)] + oracle_sources),
    ]:
        target = output / directory
        target.mkdir()
        for source_path in sources:
            shutil.copy2(source_path, target / source_path.name)
    receipt = {
        "schema": SCHEMA,
        "scope": "periodic_synthetic_geometry_arithmetic_not_RF_accuracy",
        "period": PERIOD,
        "fft": FFT,
        "taps": TAPS,
        "data_bits": 18,
        "coefficient_energy": ENERGY,
        "kernel_byte_match": True,
        "original_golden_sha256": GOLDEN_SHA256,
        "bootstrap": {
            "original_blocks": 3,
            "forward_product_inverse_words_each": 1536,
            "scores": 1341,
        },
        "cmodel_library_sha256": library_hashes,
        "numpy_version": np.__version__,
        "python_version": sys.version,
        "inputs": {str(path): digest(path) for path in inputs},
        "files": files,
        "smoke": support(343, 2),
        "production": support(20000, 64),
        "map_equation": "map[p] = sum(score[(p + frame*bins) % 447], frame=0..frames-1)",
        "recovery_scope": "smoke: full fresh map then447 partial abort; production:447 fresh scores then partial abort only",
    }
    (output / "periodic_vectors.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            {
                "schema": SCHEMA,
                "output": str(output),
                "bootstrap": receipt["bootstrap"],
                "production": receipt["production"],
                "files": len(files),
            }
        )
    )
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("original", type=Path)
    arguments = parser.parse_args()
    generate(arguments.output, arguments.original)

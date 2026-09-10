"""Frozen 30-upper common-source OFFLINE cohort, never an RTL/RF admission.

The original raw CI16 drives three independent numerical consumers: native
132-tap TRACK_ONE; integer x2 conditioning plus an explicit 18-bit FFT C model;
and the independently indexed pilot filter. No existing golden is rewritten.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import re
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from tools.generate_starlink_periodic_map_vectors import (
    Model18,
    complex_fixed,
    fixed18,
    normalize,
    pack,
    round_even,
    saturating_numerator,
)

from .ddc import FIR_Q15, conditioned_pss, ddc_contract_sha256, x2_ddc_ci16
from .fixed import fixed_correlate_ci16, quantize_q15
from .pilot_ddc import PilotDdcOracle, coefficients, mixer_lut
from .waveforms import complex64_sha256, projected_pss
from .xfft_bitacc import INSTALLED_CMODEL_ARCHIVE, prepare_installed_cmodel

ROOT = Path(__file__).resolve().parents[2]
ACQ = ROOT / "hdl/library/starlink_pss_acquisition"
KERNEL = ACQ / "tb/upper_edge_pss30_x2_ddc_kernel_q17.mem"
KERNEL_SHA = "23996c80f79f112ea7739049050ad8cb2c85a8067792889bf2a774886ac2ce24"
KERNEL_CANONICAL_SHA = (
    "926a6477ded55f163a888945ec35ccf4fa55614beea62339fc19f266721d6b8f"
)
COARSE_EH = 1073744004
SCHEMA = "starlink-high-rate-common-source-offline-v1"
COHORT = "30-upper-132tap-canonical520-v1"
FIRST = (1 << 33) - 16
PRE_FIRST = FIRST - 768
RAW_FIRST = 2 * PRE_FIRST - 7
CENTER = 2 * (FIRST + 520)
REQUEST, GENERATION, VISIT = 0x30000520, 0x30000001, 0x30000052
SEED = 0x300052020260910
CONTRACT = {
    "cohort": COHORT,
    "source_rate_msps": 30,
    "edge": "upper",
    "raw_count": 8205,
    "canonical_count": 4096,
    "preroll_canonical": 768,
    "raw_first": RAW_FIRST,
    "canonical_first": PRE_FIRST,
    "coarse_first": FIRST,
    "decimation": 2,
    "raw_halo": 7,
    "source_packing": "Q16:I16",
    "coefficient_packing": "I16:Q16",
    "fft_bits": 18,
    "fft_length": 512,
    "coarse_taps": 66,
    "stride": 447,
    "blocks": 7,
    "scores": 3129,
    "pilot_supported": 512,
    "native_taps": 132,
    "native_capture": 260,
    "native_raw_lags": [-64, 64],
    "native_qualified_lags": [-60, 60],
    "native_tuples": 121,
    "native_center": CENTER,
    "native_minimum_lead": 128,
    "native_latest_planned_accept_sample": 2 * FIRST + 256,
    "native_expected_lag": 0,
    "request_id": REQUEST,
    "coefficient_generation": GENERATION,
    "visit_id": VISIT,
    "kernel_sha256": KERNEL_SHA,
    "coarse_Eh": COARSE_EH,
    "source_cfo_hz": 0,
    "applied_correction_hz": 0,
    "residual_cfo_hz": 0,
    "fixed_acquisition_mixer_hz": -7_500_000,
    "fixed_pilot_mixer_hz": -2_812_500,
    "noise_rng": "NumPy PCG64 explicit int64 draw [-400,400], then CI16",
    "seed": SEED,
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("ascii")


def mem(values, width: int) -> bytes:
    values = [int(value) for value in values]
    if any(not 0 <= value < 1 << (width * 4) for value in values):
        raise ValueError("memory value exceeds declared wire width")
    return "".join(f"{value:0{width}x}\n" for value in values).encode("ascii")


def read_mem(payload: bytes, rows: int, width: int) -> list[int]:
    lines = payload.decode("ascii").splitlines()
    if len(lines) != rows or any(
        re.fullmatch(rf"[0-9a-f]{{{width}}}", s) is None for s in lines
    ):
        raise ValueError("malformed memory geometry/packing")
    return [int(s, 16) for s in lines]


def require_contract(value: dict) -> None:
    # JSON equality alone aliases True/1 and 30/30.0: reject those too.
    if json_bytes(value) != json_bytes(CONTRACT):
        raise ValueError("unadmitted cohort/rate/edge/halo/phase/packing contract")


def raw_support(first: int, count: int) -> tuple[int, int]:
    if type(first) is not int or type(count) is not int or first < 4 or count <= 0:
        raise ValueError("positive phase-aligned canonical support required")
    return 2 * first - 7, 2 * (first + count - 1) + 7 + 1


def admission_lead(current: int) -> int:
    """Scheduler subtracts the NEXT source index, not the admission sample."""
    if type(current) is not int or not 0 <= current < (1 << 64) - 1:
        raise ValueError("source admission index must fit uint64 without wrap")
    lead = CENTER - 64 - (current + 1)
    if lead < 128 or lead >= 1 << 63:
        raise ValueError("native command would be late/insufficient lead")
    return lead


def source_fixture() -> tuple[np.ndarray, np.ndarray]:
    source = (
        np.random.Generator(np.random.PCG64(SEED))
        .integers(-400, 401, size=(8205, 2), dtype=np.int64)
        .astype(np.int16)
    )
    native = quantize_q15(projected_pss(30_000_000, "upper"))
    if native.shape != (132, 2):
        raise ValueError("native rate projection must have 132 taps, not coarse66")
    offset = CENTER - RAW_FIRST
    source[offset : offset + 132] = (
        native  # Declared exact PSS replacement, no noise inside it.
    )
    # Asymmetric, nonperiodic identity probes, outside the native PSS/capture.
    for index, iq in {
        0: (901, -307),
        14: (-811, 203),
        63: (129, 703),
        7011: (-617, -211),
        8204: (313, -907),
    }.items():
        source[index] = iq
    return source, native


def rounded_ci16(values: np.ndarray, shift: int) -> tuple[np.ndarray, int]:
    rounded = np.array(
        [[round_even(int(x), 1 << shift) for x in row] for row in values],
        dtype=np.int64,
    )
    saturation = int(np.count_nonzero((rounded < -32768) | (rounded > 32767)))
    return np.clip(rounded, -32768, 32767).astype(np.int16), saturation


def conditioner_trace(source: np.ndarray, first: int = RAW_FIRST) -> tuple[dict, dict]:
    if source.shape != (8205, 2) or first != RAW_FIRST:
        raise ValueError("wrong source halo/phase/length")
    # Independent all-sample quadrant rotation and valid convolution, then
    # exact ties-to-even conversion; cross-check the existing streaming oracle.
    phase = (np.arange(8205, dtype=np.int64) + first) % 4
    mixed = source.astype(np.int64).copy()
    for p, columns, signs in [
        (0, [0, 1], [1, 1]),
        (1, [1, 0], [1, -1]),
        (2, [0, 1], [-1, -1]),
        (3, [1, 0], [-1, 1]),
    ]:
        mixed[phase == p] = source[phase == p][:, columns].astype(np.int64) * signs
    sums = np.column_stack(
        [np.convolve(mixed[:, lane], FIR_Q15, "valid")[::2] for lane in range(2)]
    )
    canonical, clips = rounded_ci16(sums, 15)
    reference = x2_ddc_ci16(source, first_input_index=first, edge="upper")
    indexes = np.arange(4096, dtype=np.uint64) + np.uint64(PRE_FIRST)
    if (
        not np.array_equal(canonical, reference.samples_iq)
        or not np.array_equal(indexes, reference.output_indexes)
        or np.any(reference.output_gaps)
        or reference.discontinuities
        or clips != reference.saturation_events
        or clips
    ):
        raise ArithmeticError(
            "conditioner independent arithmetic/index/health mismatch"
        )
    files = {
        "ddc_mixed_s17.mem": mem(pack(mixed, 17), 9),
        "ddc_sums_s40.mem": mem(pack(sums, 40), 20),
        "canonical_ci16.mem": mem(pack(canonical, 16), 8),
        "canonical_index_u64.mem": mem(indexes, 16),
        "canonical_raw_center_u64.mem": mem(indexes * 2, 16),
        "canonical_raw_support_first_u64.mem": mem(indexes * 2 - 7, 16),
        "canonical_raw_support_last_u64.mem": mem(indexes * 2 + 7, 16),
    }
    return files, {
        "samples": canonical,
        "saturation_events": clips,
        "accepted": reference.accepted_samples,
        "contract_sha256": ddc_contract_sha256(),
    }


def conditioned_kernel(model) -> tuple[np.ndarray, np.ndarray]:
    template = conditioned_pss("upper")
    coefficients_q15 = quantize_q15(template).astype(np.int64)
    if (
        coefficients_q15.shape != (66, 2)
        or int(np.sum(coefficients_q15**2)) != COARSE_EH
    ):
        raise ArithmeticError("conditioned30 coefficient support/Eh mismatch")
    padded = np.zeros(512, dtype=np.complex128)
    padded[:66] = np.conj(complex_fixed(coefficients_q15, 15)[::-1])
    transformed, _, overflow = model.fixed_transform(
        padded, direction=1, schedule=(2, 0, 0, 0, 0)
    )
    kernel = fixed18(transformed)
    if (
        overflow
        or mem(pack(kernel, 18), 9) != KERNEL.read_bytes()
        or digest(KERNEL.read_bytes()) != KERNEL_SHA
        or digest(kernel.astype("<i4").tobytes()) != KERNEL_CANONICAL_SHA
    ):
        raise ArithmeticError(
            "independent conditioned30 kernel must byte-match frozen file"
        )
    return kernel, coefficients_q15


def coarse_block(source: np.ndarray, kernel: np.ndarray, model) -> dict:
    if source.shape != (512, 2):
        raise ValueError("incomplete coarse block")
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
    if np.any(product < -(1 << 17)) or np.any(product >= 1 << 17):
        raise ArithmeticError("spectrum product overflow")
    inverse, ei, overflow = model.block_floating_transform(
        complex_fixed(product, 17), direction=0
    )
    if overflow:
        raise ArithmeticError("inverse overflow")
    inverse = fixed18(inverse)
    ex = [
        sum(int(i) ** 2 + int(q) ** 2 for i, q in source[p : p + 66])
        for p in range(447)
    ]
    if any(not 0 < e < 1 << 38 for e in ex):
        raise ArithmeticError("coarse energy is zero/out of bounds")
    shift = 2 * (7 + ef + ei)
    prepared = [
        saturating_numerator(int(i) ** 2 + int(q) ** 2, shift) for i, q in inverse[65:]
    ]
    numerators, saturated = map(list, zip(*prepared, strict=True))
    denominators = [e * COARSE_EH for e in ex]
    return {
        "forward_q17": pack(forward, 18),
        "product_q17": pack(product, 18),
        "inverse_q17": pack(inverse, 18),
        "forward_exponents": [ef],
        "inverse_exponents": [ei],
        "energies_u38": ex,
        "numerators_u69": numerators,
        "denominators_u69": denominators,
        "saturated_u1": saturated,
        "power_shift_u7": [shift],
        "scores_u8": [
            normalize(n, d) for n, d in zip(numerators, denominators, strict=True)
        ],
    }


def pilot_trace(canonical: np.ndarray) -> tuple[dict, dict]:
    indexes = np.arange(4096, dtype=np.uint64) + np.uint64(PRE_FIRST)
    rotation = mixer_lut()[((indexes % 64).astype(np.int64) * 12) % 64]
    raw = canonical.astype(np.int64)
    rotated = np.column_stack(
        (
            raw[:, 0] * rotation[:, 0] - raw[:, 1] * rotation[:, 1],
            raw[:, 0] * rotation[:, 1] + raw[:, 1] * rotation[:, 0],
        )
    )
    mixed, s0 = rounded_ci16(rotated, 16)
    sums = np.column_stack(
        [np.convolve(mixed[:, j], coefficients(31))[:4096] for j in range(2)]
    )
    half, s1 = rounded_ci16(sums[indexes % 2 == 0], 17)
    half_indexes = indexes[indexes % 2 == 0]
    sums = np.column_stack(
        [np.convolve(half[:, j], coefficients(255))[: len(half)] for j in range(2)]
    )
    output, s2 = rounded_ci16(sums[half_indexes % 6 == 0], 17)
    newest = half_indexes[half_indexes % 6 == 0]
    valid = newest - PRE_FIRST >= 538
    reference = PilotDdcOracle("upper").process(canonical, first_index=PRE_FIRST)
    if (
        not np.array_equal(output, reference.samples_iq)
        or not np.array_equal(newest, reference.accepted_input_indexes)
        or not np.array_equal(valid, reference.support_valid)
        or s0 + s1 + s2 != reference.saturation_events
        or reference.saturation_events
    ):
        raise ArithmeticError(
            "independent pilot stages differ from streaming integer oracle"
        )
    selected = output[valid][:512]
    selected_indexes = newest[valid][:512]
    if len(selected) != 512:
        raise ValueError("incomplete supported pilot fixture")
    first, last = int(selected_indexes[0]), int(selected_indexes[-1])
    support = {
        "first_newest_canonical": first,
        "last_newest_canonical": last,
        "canonical_centers": [first - 269, last - 269],
        "raw_centers": [2 * (first - 269), 2 * (last - 269)],
        "raw_support_half_open": [2 * (first - 538) - 7, 2 * last + 8],
        "unsupported_before_first": int(np.count_nonzero(~valid)),
        "full_offline_emitted": len(output),
        "supported_selected": 512,
        "full_offline_saturation_events": [s0, s1, s2],
        "phase": "newest canonical absolute index modulo6=0, step6",
        "scope": "all offline filter outputs; hardware limit512 admission/drain counts not predicted",
    }
    files = {
        "pilot_mixed_ci16.mem": mem(pack(mixed, 16), 8),
        "pilot_half_ci16.mem": mem(pack(half, 16), 8),
        "pilot_half_index_u64.mem": mem(half_indexes, 16),
        "pilot_all_ci16.mem": mem(pack(output, 16), 8),
        "pilot_all_index_u64.mem": mem(newest, 16),
        "pilot_all_support_u1.mem": mem(valid, 1),
        "pilot_expected_ci16.mem": mem(pack(selected, 16), 8),
        "pilot_expected_index_u64.mem": mem(selected_indexes, 16),
        "pilot_expected.ci16": selected.astype("<i2").tobytes(),
    }
    return files, support


def tuple_legal(row) -> bool:
    # Hardware bounds are unchanged at high rates, but support is 132 taps.
    return (
        row.tap_count == 132
        and 0 < row.sample_energy < 1 << 38
        and 0 < row.coefficient_energy < 1 << 31
        and row.saturation_events == 0
        and -(1 << 38) <= row.real < 1 << 38
        and -(1 << 38) <= row.imag < 1 << 38
    )


def native_trace(source: np.ndarray, native: np.ndarray) -> tuple[dict, dict]:
    first = CENTER - 64
    capture = source[first - RAW_FIRST : first - RAW_FIRST + 260]
    if capture.shape != (260, 2) or native.shape != (132, 2):
        raise ValueError("native132 tap/capture260 support required")
    rows = {
        lag: fixed_correlate_ci16(capture[lag + 64 : lag + 196], native)
        for lag in range(-64, 65)
    }
    qualified = list(range(-60, 61))
    if any(not tuple_legal(rows[lag]) for lag in qualified):
        raise ArithmeticError("rate30 native qualified tuple failed hardware legality")
    winner = -60
    for lag in range(-59, 61):
        candidate, retained = rows[lag], rows[winner]
        if (
            candidate.correlation_power * retained.sample_energy
            > retained.correlation_power * candidate.sample_energy
        ):
            winner = lag
    result = rows[winner]
    if winner != 0 or result.correlation_power != result.normalization_product:
        raise ArithmeticError("predeclared exact native PSS winner/score did not hold")
    values = [
        0x31535350,
        0x1A010001,
        REQUEST,
        CENTER,
        CENTER >> 32,
        CENTER,
        CENTER >> 32,
        winner,
        CENTER + winner,
        (CENTER + winner) >> 32,
        GENERATION,
        result.real,
        result.real >> 32,
        result.imag,
        result.imag >> 32,
        result.sample_energy,
        result.sample_energy >> 32,
        result.coefficient_energy,
        result.coefficient_energy >> 32,
        result.saturation_events,
        result.correlation_power,
        result.correlation_power >> 32,
        result.correlation_power >> 64,
        result.sample_energy,
        result.sample_energy >> 32,
        result.sample_energy >> 64,
    ]
    files = {
        "native_capture_ci16.mem": mem(pack(capture, 16), 8),
        "native_coefficients_q15.mem": mem(
            [((int(i) & 65535) << 16) | (int(q) & 65535) for i, q in native], 8
        ),
        "native_expected_packet.mem": mem([v & 0xFFFFFFFF for v in values], 8),
        "native_lags_s32.mem": mem([lag & 0xFFFFFFFF for lag in qualified], 8),
        "native_start_u64.mem": mem([CENTER + lag for lag in qualified], 16),
    }
    for name, field, bits in [
        ("real_s48", "real", 48),
        ("imag_s48", "imag", 48),
        ("ex_u48", "sample_energy", 48),
        ("eh_u48", "coefficient_energy", 48),
        ("power_u96", "correlation_power", 96),
        ("saturation_u12", "saturation_events", 12),
    ]:
        files[f"native_{name}.mem"] = mem(
            [getattr(rows[lag], field) & ((1 << bits) - 1) for lag in qualified],
            bits // 4,
        )
    inventory = [
        {
            "lag": lag,
            "start_index": CENTER + lag,
            "real": r.real,
            "imag": r.imag,
            "Ex": r.sample_energy,
            "Eh": r.coefficient_energy,
            "power": r.correlation_power,
            "tap_count": r.tap_count,
            "saturation": r.saturation_events,
            "qualified": lag in qualified,
            "tuple_legal": tuple_legal(r),
        }
        for lag, r in rows.items()
    ]
    files["native_all_raw_tuples.json"] = json_bytes(inventory)
    return files, {
        "winner_lag": winner,
        "winner_power": result.correlation_power,
        "coefficient_energy": result.coefficient_energy,
        "capture_half_open": [first, first + 260],
        "qualified": 121,
        "raw": 129,
        "taps": 132,
        "packet_words": 26,
        "max_abs_C": max(max(abs(rows[k].real), abs(rows[k].imag)) for k in qualified),
        "max_Ex": max(rows[k].sample_energy for k in qualified),
        "tuple_bounds": "C signed39; Ex unsigned38 positive; Eh unsigned31 positive; saturation0; taps132",
        "planned_lead_at_latest_accept": admission_lead(
            CONTRACT["native_latest_planned_accept_sample"]
        ),
        "lead_scope": "offline arithmetic eligibility only; no AXI/CDC deadline or acceptance measured",
        "tie_rule": "strict Pcandidate*Exwinner > Pwinner*Excandidate; earliest lag on tie",
    }


def source_paths() -> list[Path]:
    # Exact local import closure, independent of unrelated pytest imports.
    imported = {
        Path(__file__).with_name(name + ".py")
        for name in (
            "__init__",
            "acquisition",
            "ddc",
            "fixed",
            "high_rate_paired",
            "numerology",
            "pilot_ddc",
            "search",
            "waveforms",
            "xfft_bitacc",
        )
    }
    paths = imported | {
        Path(__file__).resolve(),
        ROOT / "tests/__init__.py",
        ROOT / "tools/generate_starlink_high_rate_paired.py",
        ROOT / "tools/generate_starlink_periodic_map_vectors.py",
        ROOT / "tests/test_starlink_high_rate_paired.py",
        KERNEL,
        KERNEL.with_suffix(".json"),
    }
    for directory, names in {
        "starlink_pss_acquisition": [
            "starlink_pss_x2_ddc.v",
            "starlink_pilot_ddc.v",
            "starlink_pilot_fir3.v",
            "starlink_pilot_halfband2.v",
            "pilot_halfband2_q17.mem",
            "pilot_fir3_q17.mem",
            "pilot_mixer_q16.mem",
            "starlink_pss_iq_to_score_bank_owned.v",
            "starlink_pss_fft_bank_owned_slice.v",
            "starlink_pss_spectrum_product.v",
            "starlink_pss_candidate_score_path.v",
        ],
        "axi_starlink_pss_acquisition": [
            "axi_starlink_pss_acquisition.v",
            "axi_starlink_pss_phase_map_sync.v",
        ],
        "axi_starlink_pss_tracker": ["axi_starlink_pss_tracker.v"],
        "starlink_pss_raw_correlator": [
            "starlink_pss_candidate_scheduler.v",
            "starlink_pss_sliding_correlator.v",
            "starlink_pss_exact_reducer.v",
            "starlink_pss_exact_track_reducer.v",
            "starlink_pss_reduced_tracking_core.v",
            "starlink_pss_result_store.v",
        ],
        "axi_starlink_pilot_capture": [
            "axi_starlink_pilot_capture.v",
            "CAPTURE_ABI.md",
        ],
    }.items():
        paths.update(ROOT / "hdl/library" / directory / name for name in names)
    # Freeze the unchanged complete coarse/native runtime, not only cited
    # declarations; the offline gate does not execute these Verilog files.
    for directory in (ACQ, ROOT / "hdl/library/starlink_pss_raw_correlator"):
        paths.update(directory.glob("*.v"))
    return sorted(paths)


def numerical_environment() -> dict:
    """Fingerprint interpreter, complete NumPy RECORD and numeric extensions.

    No third-party binaries are copied into the portable cohort.
    """
    names = (
        "numpy",
        "numpy._core._multiarray_umath",
        "numpy.fft._pocketfft_umath",
        "numpy.random._pcg64",
        "numpy.random._generator",
        "numpy.random.bit_generator",
        "numpy.random._common",
        "numpy.linalg._umath_linalg",
    )
    modules = {
        name: digest(Path(importlib.import_module(name).__file__).read_bytes())
        for name in names
    }
    record = importlib.metadata.distribution("numpy").read_text("RECORD")
    if record is None:
        raise ValueError("installed NumPy lacks its dependency RECORD")
    return {
        "python_version": sys.version,
        "python_executable_sha256": digest(Path(sys.executable).read_bytes()),
        "numpy_version": np.__version__,
        "numpy_RECORD_sha256": digest(record.encode()),
        "numeric_module_sha256": modules,
    }


def derive(model_directory: Path) -> tuple[dict, dict[str, bytes]]:
    require_contract(CONTRACT)
    source, native = source_fixture()
    files, ddc = conditioner_trace(source)
    canonical = ddc.pop("samples")
    files["source_ci16.mem"] = mem(pack(source, 16), 8)
    files["source_index_u64.mem"] = mem(
        np.arange(8205, dtype=np.uint64) + np.uint64(RAW_FIRST), 16
    )
    with Model18(model_directory) as model:
        kernel, coarse_coefficients = conditioned_kernel(model)
        combined = {}
        for block in range(7):
            trace = coarse_block(
                canonical[768 + block * 447 : 768 + block * 447 + 512], kernel, model
            )
            for name, values in trace.items():
                combined.setdefault(name, []).extend(values)
    widths = {
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
    }
    files.update(
        {f"{name}.mem": mem(values, widths[name]) for name, values in combined.items()}
    )
    files["conditioned_kernel_q17.mem"] = mem(pack(kernel, 18), 9)
    files["conditioned_coefficients_q15.mem"] = mem(pack(coarse_coefficients, 16), 8)
    files["score_index_u64.mem"] = mem(range(FIRST, FIRST + 3129), 16)
    files["block_start_u64.mem"] = mem([FIRST + b * 447 for b in range(7)], 16)
    # Every complete overlap input with signed18 payload and ZERO pad to24,
    # matching the unchanged input-guard wire ABI, not sign-extension of pads.
    inputs = np.concatenate(
        [canonical[768 + b * 447 : 768 + b * 447 + 512] for b in range(7)]
    )
    input_q17 = inputs.astype(np.int64) * 4
    files["fft_input_q17.mem"] = mem(pack(input_q17, 18), 9)
    files["fft_input_axi48.mem"] = mem(
        [((int(q) & 0x3FFFF) << 24) | (int(i) & 0x3FFFF) for i, q in input_q17], 12
    )
    files["fft_input_index_u64.mem"] = mem(
        [
            FIRST + block * 447 + position
            for block in range(7)
            for position in range(512)
        ],
        16,
    )
    files["fft_position_u9.mem"] = mem(list(range(512)) * 7, 3)
    scores = combined["scores_u8"]
    for bins in (343, 447):
        files[f"map_{bins}x2_u16.mem"] = mem(
            [scores[p] + scores[p + bins] for p in range(bins)], 4
        )
    pilot_files, pilot = pilot_trace(canonical)
    native_files, native_evidence = native_trace(source, native)
    files.update(pilot_files)
    files.update(native_files)
    native_start, native_end = native_evidence["capture_half_open"]
    pilot_start, pilot_end = pilot["raw_support_half_open"]
    coarse_support = raw_support(FIRST, 959)
    if not (
        pilot_start <= min(native_start, coarse_support[0])
        and pilot_end >= max(native_end, coarse_support[1])
    ):
        raise ValueError("selected pilot lacks common native/map source support")
    sources = {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in source_paths()}
    info = {
        "schema": SCHEMA,
        "contract": CONTRACT,
        "source_sha256": sources,
        "scope": "offline common-source arithmetic; no RTL, bank/STOP admission, causal handoff, RF accuracy or deployment",
        "rounding": {
            "source_coefficients": "clip(rint(projected complex64 *32768), CI16)",
            "x2": "absolute quadrant mixer signed17; FIR_Q15; signed ties-even >>15 then CI16 saturation",
            "fft": "Cmodel9.1 512 radix4 natural 18-bit data/16-bit phase convergent BFP",
            "kernel": "conditioned30 Q15 reversed conjugate; fixed FFT schedule2,0,0,0,0",
            "product": "integer complex product; signed ties-even >>18; require signed18",
            "score": "u69 saturating P<<(2*(7+Ef+Ei)); denominator Ex*conditionedEh; clamp255 ties-even",
            "pilot": "Q16 mixer, Q17 HB31/2 FIR255/3; ties-even CI16 saturation each stage",
            "native": "signed48 per-tap saturating direct complex sum and energies; exact unsigned power",
        },
        "source_support": {
            "raw_half_open": list(raw_support(PRE_FIRST, 4096)),
            "raw_preroll_count": 1549,
            "canonical_half_open": [PRE_FIRST, PRE_FIRST + 4096],
            "prime_beats_not_in_fixture": 2,
            "post_fixture_continuation_not_supplied": True,
            "native_pss_half_open": [CENTER, CENTER + 132],
            "source_pss_replacement_offset": CENTER - RAW_FIRST,
            "controls": "nonperiodic seeded noise and asymmetric identity probes; no detection threshold claim",
        },
        "coarse": {
            "blocks": 7,
            "words_per_stage": 3584,
            "scores": 3129,
            "all_blocks_canonical_support": [FIRST, FIRST + 3194],
            "all_blocks_raw_support": list(raw_support(FIRST, 3194)),
            "two_block_raw_support": list(coarse_support),
            "coefficient_energy": COARSE_EH,
            "kernel_byte_match": True,
            "forward_exponents": combined["forward_exponents"],
            "inverse_exponents": combined["inverse_exponents"],
            "normalization_saturations": sum(combined["saturated_u1"]),
            "score_at_projected_control": scores[520],
            "remaining_canonical_after_last_complete_block": 134,
        },
        "ddc": ddc,
        "pilot": pilot,
        "native": native_evidence,
        "template_sha256": {
            "native30_complex64": complex64_sha256(projected_pss(30_000_000, "upper")),
            "conditioned30_complex64": complex64_sha256(conditioned_pss("upper")),
        },
        "cmodel_archive_sha256": digest(INSTALLED_CMODEL_ARCHIVE.read_bytes()),
        "cmodel_library_sha256": {
            p.name: digest(p.read_bytes()) for p in sorted(model_directory.iterdir())
        },
        "numpy_version": np.__version__,
        "numerical_environment": numerical_environment(),
        "files": {
            name: {
                "bytes": len(payload),
                "sha256": digest(payload),
                **(
                    {
                        "rows": len(payload.splitlines()),
                        "hex_width": len(payload.splitlines()[0]),
                    }
                    if name.endswith(".mem")
                    else {}
                ),
            }
            for name, payload in sorted(files.items())
        },
    }
    return info, files


def generate(output: Path) -> dict:
    if output.exists() or output.is_symlink():
        raise FileExistsError("refusing to overwrite high-rate cohort/evidence")
    # All arithmetic and admission succeeds before allocating the cohort.
    with TemporaryDirectory(prefix="high-rate-cmodel-", dir=output.parent) as temporary:
        model_dir = prepare_installed_cmodel(Path(temporary))
        info, files = derive(model_dir)
    output.mkdir()
    for name, payload in files.items():
        (output / name).write_bytes(payload)
    for relative, sha in info["source_sha256"].items():
        target = output / "source_snapshot" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
        if digest(target.read_bytes()) != sha:
            raise RuntimeError("source changed while freezing provenance")
    (output / "cohort.json").write_bytes(json_bytes(info))
    return info


def verify(output: Path) -> dict:
    recorded = json.loads((output / "cohort.json").read_bytes())
    require_contract(recorded["contract"])
    with TemporaryDirectory(prefix="high-rate-verify-", dir=output.parent) as temporary:
        model_dir = prepare_installed_cmodel(Path(temporary))
        expected, files = derive(model_dir)
    if json_bytes(recorded) != json_bytes(expected):
        raise ValueError("cohort receipt differs from independent recomputation")
    names = {p.name for p in output.iterdir()}
    if names != set(files) | {"cohort.json", "source_snapshot"}:
        raise ValueError("unexpected/missing cohort artifact")
    for name, payload in files.items():
        if (output / name).is_symlink() or (output / name).read_bytes() != payload:
            raise ValueError(f"independent golden mismatch: {name}")
    snapshots = {
        str(p.relative_to(output / "source_snapshot")): p
        for p in (output / "source_snapshot").rglob("*")
        if p.is_file()
    }
    if snapshots.keys() != expected["source_sha256"].keys():
        raise ValueError("source snapshot inventory mismatch")
    for name, sha in expected["source_sha256"].items():
        if snapshots[name].is_symlink() or digest(snapshots[name].read_bytes()) != sha:
            raise ValueError(f"source snapshot hash mismatch: {name}")
    return expected

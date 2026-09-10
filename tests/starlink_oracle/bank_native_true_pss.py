"""New synthetic520 cohort, independently regenerated before any RTL run.

Only numeric[520:586] differs from the original fixture. This static injected
PSS is not causal acquisition or RF evidence. The legacy447/520 oracle stays
unchanged. Verification recomputes all vectors, not just their manifest hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from . import xfft_bitacc as fft
from .bank_native_paired import FIRST, digest, read_words
from .fixed import fixed_correlate_ci16, quantize_q15
from .pilot_ddc import PilotDdcOracle
from .waveforms import complex64_sha256, projected_pss

PROFILE = "520-pss"
FIXTURE = "bank-native-original-overlay-520-pss-v1"
REQUEST = 0x15005201
GENERATION = 0x15000002
CENTER = FIRST + 520
ENERGY = 1073742825
ORIGINAL_SCORE_SHA256 = {
    "samples_ci16.mem": "4abe27ba953cf49f84d9979966625a2436ad59359b616321e881b42dd4c84723",
    "forward_q17.mem": "d934a8ecd0888c294fc0abfbdbe7c439bff7097ea169b937638c4b7000479bfd",
    "product_q17.mem": "b316522a68529a73d3d8e4121badea61e24621c93a97365e894f5bd416bcecb7",
    "inverse_q17.mem": "c8c5b4e28ab621d0b1d5c1dc288f6e66495b3319d348442ce5d7b8f6ea8025a1",
    "forward_exponents.mem": "18ac6df6a1ae3f19e5153524b33f336a60eabdd6dbd182d46c43450302e4b52f",
    "inverse_exponents.mem": "899b7a2486fd3759c6e4905110fc4d86ffdb6ec884da2a7f2aca4acdfd363dff",
    "scores_u8.mem": "c22f751a2a82244268dd9ea4989c4ff3b5364c172526e80886c5da3d1959e45d",
    "upper_edge_pss_kernel_q17.mem": "694d0d9b8dd55368bcaaedec37a7cda3a837d491d592ede60eec57a9821fc99a",
}
ORIGINAL_PILOT_SHA256 = {
    "paired_source_ci16.mem": "fa238de86b2afaba96dab8013b7c175001429898aa74498443b1d1fe134cbe0c",
    "paired_pilot_ci16.mem": "f3c7e34d2dd597f48fcfadbbc1e7efaca790e385c0d93263b642d6906f93ac23",
    "paired_pilot_expected.ci16": "9ca24563bda3a3df6a0f780f3eb976eaac044d97ce752277b3781ba95942d1bd",
    "paired_pilot_newest.mem": "9a863a0b9ae5a71d469cb7a79d3d4424df31e1a40d3236eb5a08471c1ed8c65f",
    "paired_metadata.mem": "41401bd4a40ae9661980268dd02f9843146898866b951f49bea71492325b7b40",
}
PYTHON_DEPENDENCIES = (
    "tests/__init__.py", "tests/starlink_oracle/__init__.py",
    "tests/starlink_oracle/acquisition.py", "tests/starlink_oracle/bank_native_paired.py",
    "tests/starlink_oracle/ddc.py", "tests/starlink_oracle/fixed.py",
    "tests/starlink_oracle/numerology.py", "tests/starlink_oracle/search.py",
    "tests/starlink_oracle/waveforms.py", "tests/starlink_oracle/xfft_bitacc.py",
    "tests/starlink_oracle/bank_native_true_pss.py", "tests/starlink_oracle/pilot_ddc.py",
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def words(values, width: int) -> bytes:
    return "".join(f"{int(value):0{width}x}\n" for value in values).encode("ascii")


def packed(values, bits: int) -> bytes:
    mask = (1 << bits) - 1
    return words(((int(i) & mask) | ((int(q) & mask) << bits) for i, q in values),
                 (2 * bits + 3) // 4)


def json_bytes(value) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def original_source() -> tuple[np.ndarray, np.ndarray]:
    coefficients = quantize_q15(projected_pss(15_000_000, "upper"))
    numeric = np.random.default_rng(0x15F17E).integers(-1200, 1201, (1406, 2), dtype=np.int16)
    for start in (100, 447, 1000):
        numeric[start:start + 66] = coefficients
    source = np.empty((4096, 2), dtype=np.int16)
    source[:768] = (37, -19)
    source[768:2174] = numeric
    tail = np.arange(4096 - 2174)
    source[2174:] = np.column_stack((tail * 19 % 97 - 48, tail * 13 % 89 - 44))
    if (sha(packed(numeric, 16)) != ORIGINAL_SCORE_SHA256["samples_ci16.mem"] or
            sha(packed(source, 16)) != ORIGINAL_PILOT_SHA256["paired_source_ci16.mem"]):
        raise ValueError("original source reconstruction identity changed")
    return source, coefficients


class Model18(fft.XfftBitAccModel):
    """Explicit reviewed18-bit generic set; never mutate base model globals."""

    def _create_state(self, *, block_floating):
        state = self._library.xilinx_ip_xfft_v9_1_create_state(
            fft._Generics(9, 1, 0, 0, 18, 16, 1, int(block_floating), 1))
        if not state:
            raise RuntimeError("C model refused frozen18-bit generics")
        return state


def round_even(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise ValueError("positive denominator required")
    quotient, remainder = divmod(numerator, denominator)
    return quotient + int(2 * remainder > denominator or
                          (2 * remainder == denominator and quotient % 2))


def normalize(power: int, shift: int, denominator: int) -> tuple[int, int, int]:
    if not 0 <= power < 1 << 36 or not 0 <= shift < 128:
        raise ValueError("normalization requires unsigned36 power and unsigned7 shift")
    raw = power << shift
    numerator = min(raw, (1 << 69) - 1)
    score = (0 if numerator <= 0 or denominator <= 0 else
             255 if numerator >= denominator else round_even(numerator * 255, denominator))
    return score, numerator, int(raw >= 1 << 69)


def fixed18(value: np.ndarray) -> np.ndarray:
    fixed = fft._complex_to_fixed(value, 18)
    if not np.array_equal(fft._fixed_to_complex(fixed, 18), value):
        raise ValueError("C model output is not exactly Q17")
    return fixed


def spectrum_product(forward: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    # Exactly the reviewed shift18 (Q17 plus one safety bit), signed ties-even.
    product = np.asarray([[round_even(int(fi) * int(ki) - int(fq) * int(kq), 1 << 18),
                           round_even(int(fi) * int(kq) + int(fq) * int(ki), 1 << 18)]
                          for (fi, fq), (ki, kq) in zip(forward, kernel, strict=True)])
    if np.any(product < -(1 << 17)) or np.any(product >= 1 << 17):
        raise ValueError("spectrum product overflow")
    return product


def coarse_vectors(numeric: np.ndarray, coefficients: np.ndarray) -> tuple[dict[str, bytes], dict]:
    """Each nonperiodic block separately; actual C FFT plus integer arithmetic.

    Model18/rounding/69-bit preparation follow the reviewed production-map
    generator; no import from its separate worktree and no periodic extension.
    """
    if numeric.shape != (1406, 2) or coefficients.shape != (66, 2):
        raise ValueError("exact1406 source and66 coefficient words required")
    if sum(int(i)**2 + int(q)**2 for i, q in coefficients) != ENERGY:
        raise ValueError("immutable66-tap energy changed")
    stages = {name: [] for name in ("forward", "product", "inverse")}
    forward_exponents, inverse_exponents = [], []
    scores, energies, numerators, denominators, saturated = [], [], [], [], []
    with TemporaryDirectory(prefix="starlink-true-pss-cmodel-") as temporary:
        directory = fft.prepare_installed_cmodel(Path(temporary))
        libraries = {path.name: digest(path) for path in sorted(directory.iterdir())}
        with Model18(directory) as model:
            padded = np.zeros(512, dtype=np.complex128)
            padded[:66] = np.conj(fft._fixed_to_complex(coefficients[::-1], 16))
            kernel, _, overflow = model.fixed_transform(padded, direction=1, schedule=(2, 0, 0, 0, 0))
            if overflow:
                raise ValueError("template FFT overflow")
            kernel = fixed18(kernel)
            for block in range(3):
                source = numeric[block * 447:block * 447 + 512]
                forward, fe, fo = model.block_floating_transform(
                    fft._fixed_to_complex(source, 16), direction=1)
                forward = fixed18(forward)
                product = spectrum_product(forward, kernel)
                inverse, ie, io = model.block_floating_transform(
                    fft._fixed_to_complex(product, 18), direction=0)
                inverse = fixed18(inverse)
                if fo or io:
                    raise ValueError("C-model overflow is not a healthy fixture")
                for name, value in (("forward", forward), ("product", product), ("inverse", inverse)):
                    stages[name].append(value)
                forward_exponents.append(fe)
                inverse_exponents.append(ie)
                for position in range(447):
                    energy = sum(int(i)**2 + int(q)**2 for i, q in source[position:position + 66])
                    i, q = map(int, inverse[position + 65])
                    score, numerator, saturation = normalize(i*i + q*q, 2 * (7 + fe + ie), energy * ENERGY)
                    energies.append(energy)
                    numerators.append(numerator)
                    denominators.append(energy * ENERGY)
                    saturated.append(saturation)
                    scores.append(score)
    payloads = {f"{name}_q17.mem": packed(np.vstack(blocks), 18) for name, blocks in stages.items()}
    payloads.update({"samples_ci16.mem": packed(numeric, 16),
                     "forward_exponents.mem": words(forward_exponents, 2),
                     "inverse_exponents.mem": words(inverse_exponents, 2),
                     "scores_u8.mem": words(scores, 2),
                     "upper_edge_pss_kernel_q17.mem": packed(kernel, 18),
                     "energies_u38.mem": words(energies, 10),
                     "numerators_u69.mem": words(numerators, 18),
                     "denominators_u69.mem": words(denominators, 18),
                     "saturated_u1.mem": words(saturated, 1)})
    if sha(payloads["upper_edge_pss_kernel_q17.mem"]) != ORIGINAL_SCORE_SHA256["upper_edge_pss_kernel_q17.mem"]:
        raise ValueError("immutable18-bit kernel identity changed")
    return payloads, {"forward_exponents": forward_exponents,
                      "inverse_exponents": inverse_exponents, "block_count": 3,
                      "score_count": 1341, "data_bits": 18, "fraction_bits": 17,
                      "cmodel_archive_sha256": fft.INSTALLED_CMODEL_SHA256,
                      "cmodel_library_sha256": libraries, "spectrum_product_shift": 18,
                      "power_shifts": [2 * (7 + fe + ie) for fe, ie in zip(forward_exponents, inverse_exponents, strict=True)],
                      "numerator_saturation_events": sum(saturated),
                      "oracle_schema": fft.XFFT_BITACC_SCHEMA, "overflow_events": 0}


def pilot_vectors(source: np.ndarray) -> tuple[dict[str, bytes], dict]:
    result = PilotDdcOracle("upper").process(source, first_index=FIRST - 768)
    pilot = result.samples_iq[result.support_valid][:512]
    indexes = result.accepted_input_indexes[result.support_valid][:512]
    if result.saturation_events or len(pilot) != 512:
        raise ValueError("pilot must have512 fully supported unsaturated words")
    unsupported = int((~result.support_valid).sum())
    metadata = [FIRST, FIRST - 768, int(indexes[0]), int(indexes[-1]), unsupported,
                unsupported + 512, int(indexes[0]) - 269, int(indexes[-1]) - 269,
                int(indexes[0]) - 538, int(indexes[-1]) + 1]
    if not metadata[6] <= FIRST < FIRST + 959 <= metadata[7] + 1:
        raise ValueError("pilot center support does not enclose full FFT input envelope")
    return {"paired_source_ci16.mem": packed(source, 16),
            "paired_pilot_ci16.mem": packed(pilot, 16),
            "paired_pilot_expected.ci16": pilot.astype("<i2").tobytes(),
            "paired_pilot_newest.mem": words(indexes, 16),
            "paired_metadata.mem": words(metadata, 16)}, {
                "selected_map_geometry": "447x2", "source_count": 4096, "preroll": 768,
                "pilot_count": 512, "pilot_bytes": 2048, "saturation_events": 0,
                "map_candidate_interval": [FIRST, FIRST + 894],
                "map_full_fft_inputs": [FIRST, FIRST + 959],
                "pilot_center_bounds": [metadata[6], metadata[7] + 1],
                "pilot_raw_input_support": [metadata[8], metadata[9]]}


def native_vectors(source: np.ndarray, coefficients: np.ndarray) -> tuple[dict[str, bytes], dict]:
    capture = source[768 + 488:768 + 618]
    rows = {lag: fixed_correlate_ci16(capture[lag + 32:lag + 98], coefficients)
            for lag in range(-32, 33)}
    for lag in range(-30, 31):
        row = rows[lag]
        if not (0 < row.sample_energy < 1 << 38 and 0 < row.coefficient_energy < 1 << 31 and
                -(1 << 38) <= row.real < 1 << 38 and -(1 << 38) <= row.imag < 1 << 38 and
                row.saturation_events == 0):
            raise ValueError(f"qualified native tuple {lag} violates DSP tuple_score_legal")
    winner = -30
    for lag in range(-29, 31):
        candidate, retained = rows[lag], rows[winner]
        if candidate.correlation_power * retained.sample_energy > retained.correlation_power * candidate.sample_energy:
            winner = lag
    row = rows[winner]
    if (winner, row.real, row.imag, row.sample_energy, row.coefficient_energy) != (0, ENERGY, 0, ENERGY, ENERGY):
        raise ValueError("true-PSS source does not have the required exact zero-lag winner")
    power, energy = row.correlation_power, row.sample_energy
    values = [0x31535350, 0x1A010001, REQUEST, CENTER, CENTER >> 32,
              CENTER, CENTER >> 32, winner, CENTER + winner, (CENTER + winner) >> 32,
              GENERATION, row.real, row.real >> 32, row.imag, row.imag >> 32,
              energy, energy >> 32, row.coefficient_energy, row.coefficient_energy >> 32,
              row.saturation_events, power, power >> 32, power >> 64,
              energy, energy >> 32, energy >> 64]
    return {"native_coefficients_q15.mem": words(
        ((int(i) & 65535) << 16 | (int(q) & 65535) for i, q in coefficients), 8),
        "native_expected_packet.mem": words((value & 0xFFFFFFFF for value in values), 8)}, {
            "request_id": REQUEST, "coefficient_generation": GENERATION,
            "center_index": CENTER, "capture_bounds": [CENTER - 32, CENTER + 98],
            "source_rate_hz": 15_000_000, "tap_count": 66, "packet_words": 26,
            "raw_lags": [-32, 32], "qualified_lags": [-30, 30], "winner_lag": winner,
            "winner_real": row.real, "winner_imag": row.imag, "winner_Ex": energy,
            "winner_Eh": row.coefficient_energy, "winner_power": power,
            "coefficient_cfo_hz": 0, "tuple_score_legal_checked": 61,
            "tie_rule": "strict P_candidate*Ex_retained > P_retained*Ex_candidate; earliest lag wins",
            "accumulator_rule": "signed48 saturation after each complete complex tap",
            "template_complex64_sha256": complex64_sha256(projected_pss(15_000_000, "upper")),
            "coefficient_ci16le_sha256": sha(coefficients.astype("<i2").tobytes()),
            "qualified_tuples": [{"lag": lag, "real": rows[lag].real, "imag": rows[lag].imag,
                                  "Ex": rows[lag].sample_energy, "Eh": rows[lag].coefficient_energy,
                                  "saturation_events": rows[lag].saturation_events, "legal": True}
                                 for lag in range(-30, 31)]}


def derive() -> tuple[dict[str, bytes], dict]:
    source, coefficients = original_source()
    source[768 + 520:768 + 586] = coefficients
    numeric = source[768:2174]
    coarse, coarse_manifest = coarse_vectors(numeric, coefficients)
    pilot, pilot_manifest = pilot_vectors(source)
    native, native_manifest = native_vectors(source, coefficients)
    scores = [int(row, 16) for row in coarse["scores_u8.mem"].splitlines()]
    if any(scores[start] != 255 for start in (100, 447, 520, 1000)):
        raise ValueError("original or new injected PSS no longer scores255")
    coarse["paired_map_u32.mem"] = words((scores[k] + scores[k + 447] for k in range(447)), 8)
    payloads = {}
    for directory, files, manifest, name in (
            ("score", coarse, coarse_manifest, "pipeline_vectors.json"),
            ("pilot", pilot, pilot_manifest, "paired_oracle.json"),
            ("native", native, native_manifest, "native_oracle.json")):
        manifest.update({"fixture_id": FIXTURE, "profile": PROFILE,
                         "scope": "offline synthetic static PSS, NOT causal acquisition or RF/physical evidence",
                         "source_sha256": sha(pilot["paired_source_ci16.mem"]),
                         "generated_sha256": {key: sha(value) for key, value in sorted(files.items())}})
        payloads.update({f"{directory}/{key}": value for key, value in files.items()})
        payloads[f"{directory}/{name}"] = json_bytes(manifest)
    root = Path(__file__).resolve().parents[2]
    cohort = {"schema": FIXTURE, "profile": PROFILE,
              "original_score_sha256": ORIGINAL_SCORE_SHA256, "original_pilot_sha256": ORIGINAL_PILOT_SHA256,
              "only_modified_numeric_interval": [520, 586], "only_modified_paired_interval": [1288, 1354],
              "preserved_original_controls": [100, 447, 1000],
              "python_runtime_sha256": {name: digest(root / name) for name in PYTHON_DEPENDENCIES},
              "generated_sha256": {name: sha(value) for name, value in sorted(payloads.items())},
              "native_admission": {"minimum_lead": 64, "deadline_offset": 128,
                                   "lead_at_deadline": 359, "capture_offsets": [488, 618]},
              "actual_rtl_simulation_qualified": False, "physical_or_RF_qualified": False}
    payloads["fixture.json"] = json_bytes(cohort)
    return payloads, cohort


def generate(original_score: Path, original_pilot: Path, output: Path) -> dict:
    if output.exists() or output.is_symlink():
        raise ValueError("refusing to overwrite true-PSS evidence")
    for directory, hashes in ((original_score, ORIGINAL_SCORE_SHA256), (original_pilot, ORIGINAL_PILOT_SHA256)):
        for name, expected in hashes.items():
            if digest(directory / name) != expected:
                raise ValueError(f"original cohort identity mismatch: {name}")
    payloads, manifest = derive()
    output.mkdir(parents=True)
    for name, data in payloads.items():
        path = output / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(data)
    return manifest


def verify(score: Path, pilot: Path, native: Path) -> dict:
    score, pilot, native = (path.resolve() for path in (score, pilot, native))
    if (score.name, pilot.name, native.name) != ("score", "pilot", "native") or not score.parent == pilot.parent == native.parent:
        raise ValueError("true-PSS inputs must belong to one explicit score/pilot/native cohort")
    root = score.parent
    payloads, manifest = derive()
    actual = {str(path.relative_to(root)) for path in root.rglob("*") if not path.is_dir()}
    directories = {str(path.relative_to(root)) for path in root.rglob("*") if path.is_dir()}
    if (actual != set(payloads) or directories != {"score", "pilot", "native"} or
            any(path.is_symlink() for path in root.rglob("*"))):
        raise ValueError("true-PSS cohort inventory mismatch")
    for name, expected in payloads.items():
        if (root / name).read_bytes() != expected:
            raise ValueError(f"independently recomputed true-PSS golden mismatch: {name}")
    # Explicit dimensions additionally document the exact ABI/packing contract.
    read_words(native / "native_expected_packet.mem", 26, 8)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("generate")
    create.add_argument("original_score", type=Path)
    create.add_argument("original_pilot", type=Path)
    create.add_argument("output", type=Path)
    check = commands.add_parser("verify")
    check.add_argument("score", type=Path)
    check.add_argument("pilot", type=Path)
    check.add_argument("native", type=Path)
    args = parser.parse_args()
    if args.command == "generate":
        generate(args.original_score, args.original_pilot, args.output)
    else:
        verify(args.score, args.pilot, args.native)
    print("BANK_NATIVE_TRUE_PSS_ORACLE_VERIFIED source=4096 blocks=3 scores=1341 map_words=447 pilot_bytes=2048 packet_words=26 profile=520-pss winner_lag=0")

"""Independent fixed60 common-source cohort. No30 mutation or RTL admission."""

from __future__ import annotations

import ast
import json
import shutil
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

from .ddc import FIR_Q15, conditioned_pss_x4, ddc_x4_contract_sha256, x4_ddc_ci16
from .fixed import fixed_correlate_ci16, quantize_q15
from .high_rate60_recipe import APPROVED_SUPPORT, APPROVED_SUPPORT_COMMIT, recipe
from .high_rate60_support import native_lead, native_support, pilot_support, raw_support

# Only these parameter-independent serialization/rounding/environment helpers
# are reused. Never call30 conditioner/coarse/native/pilot functions or mutate
# their globals. In particular, no30 coefficient denominator is reusable.
from .high_rate_paired import (
    digest,
    json_bytes,
    mem,
    numerical_environment,
    rounded_ci16,
)
from .pilot_ddc import PilotDdcOracle, coefficients, mixer_lut
from .waveforms import complex64_sha256, projected_pss
from .xfft_bitacc import INSTALLED_CMODEL_ARCHIVE, prepare_installed_cmodel

ROOT = Path(__file__).resolve().parents[2]
ACQ = ROOT / "hdl/library/starlink_pss_acquisition"
KERNEL = ACQ / "tb/upper_edge_pss60_x4_ddc_kernel_q17.mem"
CONTRACT = recipe()
SUPPORT = CONTRACT["support"]
RAW_FIRST, RAW_STOP = SUPPORT["raw_half_open"]
FIRST, PRE_FIRST, CENTER = SUPPORT["coarse_first"], SUPPORT["canonical_first"], SUPPORT["native_center"]
RECIPE_SOURCE_SHA = "bd39c5fdf850dc6ec1ecbbf6476ac6a8e2990ce1be7455e98a0fc5294647f4c4"


def require_contract(value):
    if json_bytes(value) != json_bytes(recipe()):
        raise ValueError("unadmitted60 recipe/rate/identity/packing/support")
    if digest(Path(__file__).with_name("high_rate60_recipe.py").read_bytes()) != RECIPE_SOURCE_SHA:
        raise ValueError("pre-evaluation recipe source changed")
    for name, expected in APPROVED_SUPPORT.items():
        if digest((ROOT / name).read_bytes()) != expected:
            raise ValueError("approved parent support source changed")


def source_fixture():
    require_contract(CONTRACT)
    source = np.random.Generator(np.random.PCG64(CONTRACT["seed"])).integers(
        -400, 401, size=(SUPPORT["raw_count"], 2), dtype=np.int64).astype(np.int16)
    native = quantize_q15(projected_pss(60_000_000, "upper"))
    if native.shape != (264, 2):
        raise ValueError("native60 requires264 taps, not132/66")
    offset = CENTER - RAW_FIRST
    source[offset:offset + 264] = native
    capture_first, capture_stop = native_support(CENTER)
    for index, iq in CONTRACT["identity_probes_offset_iq"].items():
        index = int(index)
        if capture_first <= RAW_FIRST + index < capture_stop:
            raise ValueError("identity probe overlaps frozen native capture")
        source[index] = iq
    return source, native


def conditioner_stage(source, first):
    """Independent integer convolution, retaining this stage's own rounding."""
    if source.dtype != np.int16 or source.ndim != 2 or source.shape[1] != 2 or first % 2 != 1:
        raise ValueError("phase-aligned CI16 stage required")
    indexes = np.arange(len(source), dtype=np.int64) + first
    mixed = np.empty(source.shape, dtype=np.int64)
    for phase, columns, signs in [(0, [0, 1], [1, 1]), (1, [1, 0], [1, -1]),
                                  (2, [0, 1], [-1, -1]), (3, [1, 0], [-1, 1])]:
        selected = indexes % 4 == phase
        mixed[selected] = source[selected][:, columns].astype(np.int64) * signs
    sums = np.column_stack([np.convolve(mixed[:, lane], FIR_Q15, "valid")[::2] for lane in range(2)])
    values, clips = rounded_ci16(sums, 15)
    centers = np.arange(len(values), dtype=np.uint64) + np.uint64((first + 7) // 2)
    return mixed, sums, values, centers, clips


def conditioner_trace(source, first=RAW_FIRST):
    if source.shape != (16423, 2) or source.dtype != np.int16 or first != RAW_FIRST:
        raise ValueError("wrong60 source halo/phase/length/packing")
    files, evidence = {}, []
    values, stage_first = source, first
    stages = []
    for name in ["ddc60_to30", "ddc30_to15"]:
        mixed, sums, output, indexes, clips = conditioner_stage(values, stage_first)
        files.update({name + "_mixed_s17.mem": mem(pack(mixed, 17), 9),
                      name + "_sums_s40.mem": mem(pack(sums, 40), 20),
                      name + "_ci16.mem": mem(pack(output, 16), 8),
                      name + "_index_u64.mem": mem(indexes, 16)})
        evidence.append({"name": name, "accepted": len(values), "emitted": len(output),
                         "first_input": stage_first, "first_output": int(indexes[0]), "saturation_events": clips})
        stages.append((output, indexes, clips))
        values, stage_first = output, int(indexes[0])
    reference = x4_ddc_ci16(source, first_input_index=first, edge="upper")
    for actual, expected in zip(stages, [reference.stage_60_to_30, reference.stage_30_to_15], strict=True):
        output, indexes, clips = actual
        if (not np.array_equal(output, expected.samples_iq) or not np.array_equal(indexes, expected.output_indexes)
                or clips != expected.saturation_events or clips or expected.discontinuities or np.any(expected.output_gaps)):
            raise ArithmeticError("separately rounded60 conditioner stage mismatch/health")
    if values.shape != (4096, 2) or stages[0][0].shape != (8205, 2) or stage_first != PRE_FIRST:
        raise ArithmeticError("60 cascade stage support mismatch")
    indexes = stages[-1][1]
    files.update({"canonical_ci16.mem": mem(pack(values, 16), 8), "canonical_index_u64.mem": mem(indexes, 16),
                  "canonical_raw_center_u64.mem": mem(indexes * 4, 16),
                  "canonical_raw_support_first_u64.mem": mem(indexes * 4 - 21, 16),
                  "canonical_raw_support_last_u64.mem": mem(indexes * 4 + 21, 16)})
    return files, values, {"stages": evidence, "contract_sha256": ddc_x4_contract_sha256()}


def conditioned_kernel(model):
    template = conditioned_pss_x4("upper")
    coefficients_q15 = quantize_q15(template).astype(np.int64)
    if coefficients_q15.shape != (66, 2) or int(np.sum(coefficients_q15 ** 2)) != CONTRACT["coarse_Eh"]:
        raise ArithmeticError("conditioned60 coefficient support/Eh mismatch")
    padded = np.zeros(512, dtype=np.complex128)
    padded[:66] = np.conj(complex_fixed(coefficients_q15, 15)[::-1])
    transformed, _, overflow = model.fixed_transform(padded, direction=1, schedule=(2, 0, 0, 0, 0))
    kernel = fixed18(transformed)
    if (overflow or mem(pack(kernel, 18), 9) != KERNEL.read_bytes()
            or digest(KERNEL.read_bytes()) != CONTRACT["kernel_memory_sha256"]
            or digest(kernel.astype("<i4").tobytes()) != CONTRACT["kernel_canonical_sha256"]):
        raise ArithmeticError("independent60 kernel must byte-match existing kernel")
    return kernel, coefficients_q15


def coarse_block(source, kernel, model, *, coefficient_energy):
    if source.shape != (512, 2) or coefficient_energy != CONTRACT["coarse_Eh"]:
        raise ValueError("complete512 block and explicit conditioned60 denominator required")
    forward, ef, overflow = model.block_floating_transform(complex_fixed(source, 15), direction=1)
    if overflow:
        raise ArithmeticError("forward overflow")
    forward = fixed18(forward)
    product = np.array([[round_even(int(fi) * int(ki) - int(fq) * int(kq), 1 << 18),
                         round_even(int(fi) * int(kq) + int(fq) * int(ki), 1 << 18)]
                        for (fi, fq), (ki, kq) in zip(forward, kernel, strict=True)], dtype=np.int64)
    if np.any(product < -(1 << 17)) or np.any(product >= 1 << 17):
        raise ArithmeticError("product overflow")
    inverse, ei, overflow = model.block_floating_transform(complex_fixed(product, 17), direction=0)
    if overflow:
        raise ArithmeticError("inverse overflow")
    inverse = fixed18(inverse)
    energy = [sum(int(i) ** 2 + int(q) ** 2 for i, q in source[p:p + 66]) for p in range(447)]
    if any(not 0 < e < 1 << 38 for e in energy):
        raise ArithmeticError("coarse energy bounds")
    shift = 2 * (7 + ef + ei)
    prepared = [saturating_numerator(int(i) ** 2 + int(q) ** 2, shift) for i, q in inverse[65:]]
    numerators, saturated = map(list, zip(*prepared, strict=True))
    denominators = [e * coefficient_energy for e in energy]
    return {"forward_q17": pack(forward, 18), "product_q17": pack(product, 18), "inverse_q17": pack(inverse, 18),
            "forward_exponents": [ef], "inverse_exponents": [ei], "energies_u38": energy,
            "numerators_u69": numerators, "denominators_u69": denominators, "saturated_u1": saturated,
            "power_shift_u7": [shift], "scores_u8": [normalize(n, d) for n, d in zip(numerators, denominators, strict=True)]}


def pilot_trace(canonical):
    if canonical.shape != (4096, 2) or canonical.dtype != np.int16:
        raise ValueError("complete canonical CI16 pilot input required")
    indexes = np.arange(4096, dtype=np.uint64) + np.uint64(PRE_FIRST)
    rotation = mixer_lut()[((indexes % 64).astype(np.int64) * 12) % 64]
    raw = canonical.astype(np.int64)
    rotated = np.column_stack((raw[:, 0] * rotation[:, 0] - raw[:, 1] * rotation[:, 1],
                               raw[:, 0] * rotation[:, 1] + raw[:, 1] * rotation[:, 0]))
    mixed, s0 = rounded_ci16(rotated, 16)
    sums = np.column_stack([np.convolve(mixed[:, lane], coefficients(31))[:4096] for lane in range(2)])
    half, s1 = rounded_ci16(sums[indexes % 2 == 0], 17)
    half_indexes = indexes[indexes % 2 == 0]
    sums = np.column_stack([np.convolve(half[:, lane], coefficients(255))[:len(half)] for lane in range(2)])
    output, s2 = rounded_ci16(sums[half_indexes % 6 == 0], 17)
    newest = half_indexes[half_indexes % 6 == 0]
    valid = newest - PRE_FIRST >= 538
    reference = PilotDdcOracle("upper").process(canonical, first_index=PRE_FIRST)
    if (not np.array_equal(output, reference.samples_iq) or not np.array_equal(newest, reference.accepted_input_indexes)
            or not np.array_equal(valid, reference.support_valid) or s0 + s1 + s2 != reference.saturation_events or s0 + s1 + s2):
        raise ArithmeticError("independent pilot stage/index/health mismatch")
    selected, selected_indexes = output[valid][:512], newest[valid][:512]
    if len(selected) != 512 or list(map(int, selected_indexes[[0, -1]])) != SUPPORT["pilot_newest_canonical"]:
        raise ValueError("pilot support differs from approved60 recipe")
    supports = [pilot_support(int(index)) for index in selected_indexes]
    files = {"pilot_mixed_ci16.mem": mem(pack(mixed, 16), 8), "pilot_half_ci16.mem": mem(pack(half, 16), 8),
             "pilot_half_index_u64.mem": mem(half_indexes, 16), "pilot_all_ci16.mem": mem(pack(output, 16), 8),
             "pilot_all_index_u64.mem": mem(newest, 16), "pilot_all_support_u1.mem": mem(valid, 1),
             "pilot_expected_ci16.mem": mem(pack(selected, 16), 8), "pilot_expected_index_u64.mem": mem(selected_indexes, 16),
             "pilot_raw_support_first_u64.mem": mem([s[0] for s in supports], 16),
             "pilot_raw_support_last_u64.mem": mem([s[1] - 1 for s in supports], 16),
             "pilot_expected.ci16": selected.astype("<i2").tobytes()}
    return files, {"supported_selected": 512, "full_offline_emitted": len(output),
                   "unsupported_before_first": int(np.count_nonzero(~valid)), "saturation_events": [s0, s1, s2],
                   "raw_support_half_open": [supports[0][0], supports[-1][1]], "raw_step": 24,
                   "scope": "independent offline filter, not a prediction of hardware auto-stop/drain counts"}


def integer_tuple(samples, coefficients_q15):
    """Python-integer per-tap sums, independently cross-checked below."""
    if samples.shape != (264, 2) or coefficients_q15.shape != (264, 2):
        raise ValueError("native60 tuple must have264 taps, not coarse66")
    accumulators, saturation = [0, 0, 0, 0], 0
    for (i, q), (hi, hq) in zip(samples.tolist(), coefficients_q15.tolist(), strict=True):
        for n, term in enumerate([i * hi + q * hq, q * hi - i * hq, i * i + q * q, hi * hi + hq * hq]):
            value = accumulators[n] + term
            clipped = min(max(value, -(1 << 47)), (1 << 47) - 1)
            saturation += int(clipped != value)
            accumulators[n] = clipped
    real, imag, ex, eh = accumulators
    return {"real": real, "imag": imag, "Ex": ex, "Eh": eh, "power": real * real + imag * imag,
            "tap_count": 264, "saturation": saturation}


def tuple_legal(row):
    return (row["tap_count"] == 264 and 0 < row["Ex"] < 1 << 38 and 0 < row["Eh"] < 1 << 31
            and row["saturation"] == 0 and -(1 << 38) <= row["real"] < 1 << 38
            and -(1 << 38) <= row["imag"] < 1 << 38)


def select_winner(rows):
    candidates = [r for r in rows if r["qualified"] and tuple_legal(r)]
    if len(candidates) != 241 or [r["lag"] for r in candidates] != list(range(-120, 121)):
        raise ValueError("native60 requires complete241 legal qualified tuples")
    winner = candidates[0]
    for candidate in candidates[1:]:
        if candidate["power"] * winner["Ex"] > winner["power"] * candidate["Ex"]:
            winner = candidate
    return winner


def native_trace(source, native):
    first, stop = native_support(CENTER)
    capture = source[first - RAW_FIRST:stop - RAW_FIRST]
    if source.shape != (16423, 2) or capture.shape != (520, 2) or native.shape != (264, 2):
        raise ValueError("native60 original source/capture520/taps264 required")
    rows = []
    for lag in range(-128, 129):
        samples = capture[lag + 128:lag + 392]
        row = integer_tuple(samples, native)
        reference = fixed_correlate_ci16(samples, native)
        if row != {"real": reference.real, "imag": reference.imag, "Ex": reference.sample_energy,
                   "Eh": reference.coefficient_energy, "power": reference.correlation_power,
                   "tap_count": reference.tap_count, "saturation": reference.saturation_events}:
            raise ArithmeticError("independent native integer tuple differs from fixed contract")
        row.update({"lag": lag, "start_index": CENTER + lag, "qualified": -120 <= lag <= 120,
                    "tuple_legal": tuple_legal(row)})
        rows.append(row)
    winner = select_winner(rows)
    if winner["lag"] != 0 or winner["power"] != winner["Ex"] * winner["Eh"]:
        raise ArithmeticError("predeclared native60 exact-replacement winner failed")
    values = [0x31535350, 0x1A010001, CONTRACT["request_id"], CENTER, CENTER >> 32, CENTER, CENTER >> 32,
              winner["lag"], winner["start_index"], winner["start_index"] >> 32, CONTRACT["coefficient_generation"],
              winner["real"], winner["real"] >> 32, winner["imag"], winner["imag"] >> 32,
              winner["Ex"], winner["Ex"] >> 32, winner["Eh"], winner["Eh"] >> 32, winner["saturation"],
              winner["power"], winner["power"] >> 32, winner["power"] >> 64, winner["Ex"], winner["Ex"] >> 32, winner["Ex"] >> 64]
    files = {"native_capture_ci16.mem": mem(pack(capture, 16), 8),
             "native_coefficients_q15.mem": mem([((int(i) & 65535) << 16) | (int(q) & 65535) for i, q in native], 8),
             "native_all_raw_tuples.json": json_bytes(rows), "native_expected_packet.mem": mem([v & 0xffffffff for v in values], 8)}
    qualified = [r for r in rows if r["qualified"]]
    for population, prefix in [(rows, "native_raw"), (qualified, "native")]:
        for field, suffix, bits, width in [("lag", "lags_s32", 32, 8), ("start_index", "start_u64", 64, 16),
                                          ("real", "real_s48", 48, 12), ("imag", "imag_s48", 48, 12),
                                          ("Ex", "ex_u48", 48, 12), ("Eh", "eh_u48", 48, 12),
                                          ("power", "power_u96", 96, 24), ("saturation", "saturation_u12", 12, 3),
                                          ("qualified", "qualified_u1", 1, 1)]:
            files[prefix + "_" + suffix + ".mem"] = mem([int(r[field]) & ((1 << bits) - 1) for r in population], width)
    return files, {"raw": 257, "qualified": 241, "taps": 264, "capture_half_open": [first, stop],
                   "winner_lag": winner["lag"], "coefficient_energy": winner["Eh"], "winner_power": winner["power"],
                   "packet_words": 26, "max_Ex": max(r["Ex"] for r in qualified),
                   "max_abs_C": max(max(abs(r["real"]), abs(r["imag"])) for r in qualified),
                   "tuple_bounds": "C signed39; Ex unsigned38 positive; Eh unsigned31 positive; saturation0; taps264",
                   "minimum_lead": native_lead(CENTER, first - 257),
                   "lead_scope": "arithmetic eligibility only; no actual command, service bound or source tail"}


def python_import_closure():
    pending = {"tests/starlink_oracle/high_rate60_paired.py", "tools/generate_starlink_high_rate60_paired.py",
               "tests/test_starlink_high_rate60_paired.py", "tests/test_starlink_high_rate60_support.py"}
    edges = {}
    while pending:
        name = pending.pop()
        if name in edges:
            continue
        dependencies = set()
        for node in ast.walk(ast.parse((ROOT / name).read_text())):
            modules = []
            if isinstance(node, ast.Import):
                modules = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom):
                parent = name.removesuffix(".py").split("/")[:-1]
                modules = ([".".join(parent[:len(parent) - node.level + 1] + [node.module or ""]).rstrip(".")]
                           if node.level else [node.module or ""])
            for module in modules:
                if module.split(".")[0] not in {"tests", "tools"}:
                    continue
                dependency = module.replace(".", "/") + ".py"
                if not (ROOT / dependency).is_file():
                    dependency = module.replace(".", "/") + "/__init__.py"
                if not (ROOT / dependency).is_file():
                    raise ValueError(f"unresolved local Python import {name}: {module}")
                dependencies.add(dependency)
        edges[name] = sorted(dependencies)
        pending.update(dependencies)
    return dict(sorted(edges.items()))


def source_paths():
    paths = {ROOT / name for name in python_import_closure()}
    paths.update({ROOT / "tests/__init__.py", KERNEL, KERNEL.with_suffix(".json"),
                  ROOT / "docs/starlink-high-rate60-recipe-before-evaluation-20260910.md"})
    # Read-only numerical-contract provenance, never simulation admission.
    for directory in [ACQ, ROOT / "hdl/library/starlink_pss_raw_correlator"]:
        paths.update(directory.glob("*.v"))
    for name in ["pilot_halfband2_q17.mem", "pilot_fir3_q17.mem", "pilot_mixer_q16.mem"]:
        paths.add(ACQ / name)
    for name in ["axi_starlink_pss_acquisition/axi_starlink_pss_acquisition.v",
                 "axi_starlink_pss_acquisition/axi_starlink_pss_phase_map_sync.v",
                 "axi_starlink_pss_tracker/axi_starlink_pss_tracker.v",
                 "axi_starlink_pilot_capture/axi_starlink_pilot_capture.v", "axi_starlink_pilot_capture/CAPTURE_ABI.md"]:
        paths.add(ROOT / "hdl/library" / name)
    return sorted(paths)


def source_hashes():
    return {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in source_paths()}


def derive(model_directory):
    require_contract(CONTRACT)
    source, native = source_fixture()
    files, canonical, ddc = conditioner_trace(source)
    files.update({"source_ci16.mem": mem(pack(source, 16), 8), "source_index_u64.mem": mem(range(RAW_FIRST, RAW_STOP), 16)})
    with Model18(model_directory) as model:
        kernel, coefficients_q15 = conditioned_kernel(model)
        combined = {}
        for block in range(7):
            trace = coarse_block(canonical[768 + block * 447:768 + block * 447 + 512], kernel, model,
                                 coefficient_energy=CONTRACT["coarse_Eh"])
            for name, values in trace.items():
                combined.setdefault(name, []).extend(values)
    widths = {"forward_q17": 9, "product_q17": 9, "inverse_q17": 9, "forward_exponents": 2,
              "inverse_exponents": 2, "energies_u38": 10, "numerators_u69": 18, "denominators_u69": 18,
              "saturated_u1": 1, "power_shift_u7": 2, "scores_u8": 2}
    files.update({name + ".mem": mem(values, widths[name]) for name, values in combined.items()})
    inputs = np.concatenate([canonical[768 + b * 447:768 + b * 447 + 512] for b in range(7)]).astype(np.int64) * 4
    files.update({"conditioned_kernel_q17.mem": mem(pack(kernel, 18), 9),
                  "conditioned_coefficients_q15.mem": mem(pack(coefficients_q15, 16), 8),
                  "score_index_u64.mem": mem(range(FIRST, FIRST + 3129), 16),
                  "block_start_u64.mem": mem([FIRST + b * 447 for b in range(7)], 16),
                  "fft_input_q17.mem": mem(pack(inputs, 18), 9),
                  "fft_input_axi48.mem": mem([((int(q) & 0x3ffff) << 24) | (int(i) & 0x3ffff) for i, q in inputs], 12),
                  "fft_input_index_u64.mem": mem([FIRST + b * 447 + p for b in range(7) for p in range(512)], 16),
                  "fft_position_u9.mem": mem(list(range(512)) * 7, 3)})
    scores = combined["scores_u8"]
    for bins in [343, 447]:
        files[f"map_{bins}x2_u16.mem"] = mem([scores[p] + scores[p + bins] for p in range(bins)], 4)
    pilot_files, pilot = pilot_trace(canonical)
    native_files, native_evidence = native_trace(source, native)
    files.update(pilot_files)
    files.update(native_files)
    coarse_start, coarse_stop = raw_support(FIRST, 959)
    if not (pilot["raw_support_half_open"][0] <= min(coarse_start, native_evidence["capture_half_open"][0])
            and pilot["raw_support_half_open"][1] >= max(coarse_stop, native_evidence["capture_half_open"][1])):
        raise ValueError("pilot512 lacks common native/map raw support")
    info = {"schema": "starlink-high-rate60-common-source-offline-v1", "contract": recipe(),
            "source_sha256": source_hashes(), "python_import_edges": python_import_closure(),
            "approved_support_commit": APPROVED_SUPPORT_COMMIT, "approved_support_sha256": APPROVED_SUPPORT,
            "scope": "offline common-source arithmetic only; no runtime profile, RTL run, service bound, tail or RF claim",
            "ddc": ddc, "pilot": pilot, "native": native_evidence,
            "source_support": {"raw_half_open": [RAW_FIRST, RAW_STOP], "raw_preroll_count": raw_support(PRE_FIRST, 768)[1] - RAW_FIRST,
                               "canonical_half_open": [PRE_FIRST, PRE_FIRST + 4096], "native_pss_half_open": CONTRACT["native_pss_half_open"],
                               "source_pss_replacement_offset": CENTER - RAW_FIRST, "source_tail_supplied": False},
            "coarse": {"blocks": 7, "words_per_stage": 3584, "scores": 3129, "coefficient_energy": CONTRACT["coarse_Eh"],
                       "kernel_byte_match": True, "all_blocks_canonical_support": [FIRST, FIRST + 3194],
                       "all_blocks_raw_support": list(raw_support(FIRST, 3194)), "two_block_raw_support": [coarse_start, coarse_stop],
                       "forward_exponents": combined["forward_exponents"], "inverse_exponents": combined["inverse_exponents"],
                       "normalization_saturations": sum(combined["saturated_u1"]), "score_at_projected_control": scores[520],
                       "remaining_canonical_after_last_complete_block": 134},
            "template_sha256": {"native60_complex64": complex64_sha256(projected_pss(60_000_000, "upper")),
                                "conditioned60_complex64": complex64_sha256(conditioned_pss_x4("upper"))},
            "rounding": {"source_coefficients": "clip(rint(projected complex64*32768), CI16)",
                         "conditioner": CONTRACT["acquisition_rounding"],
                         "fft": "explicitModel18 Cmodel9.1 length512 radix4 natural data18 phase16 convergent BFP; no global mutation",
                         "kernel": CONTRACT["kernel_source"], "product": "exact signed integer complex products, ties-even >>18, signed18 bounds",
                         "score": "Ex over66CI16; u69 sat power<<(2*(7+Ef+Ei)); denominator Ex*1073765335; normalized255 ties-even",
                         "pilot": "Q16 mixer/Q17 HB31/FIR255; separately rounded CI16 at all3 stages",
                         "native": "264 direct complex tap products, each accumulator signed48 saturating, exact unsigned96 power"},
            "cmodel_archive_sha256": digest(INSTALLED_CMODEL_ARCHIVE.read_bytes()),
            "cmodel_library_sha256": {p.name: digest(p.read_bytes()) for p in sorted(model_directory.iterdir())},
            "numerical_environment": numerical_environment(),
            "files": {name: {"bytes": len(data), "sha256": digest(data),
                             **({"rows": len(data.splitlines()), "hex_width": len(data.splitlines()[0])} if name.endswith(".mem") else {})}
                      for name, data in sorted(files.items())}}
    return info, files


def generate(output):
    if output.exists() or output.is_symlink():
        raise FileExistsError("refusing to overwrite60 cohort/attempt")
    require_contract(CONTRACT)
    before = source_hashes()
    output.mkdir()
    (output / "recipe-before.json").write_bytes(json_bytes(recipe()))
    (output / "source-before.json").write_bytes(json_bytes(before))
    (output / "environment-before.json").write_bytes(json_bytes(numerical_environment()))
    for name, expected in before.items():
        target = output / "source_snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
        if digest(target.read_bytes()) != expected:
            raise ValueError("source copy changed before evaluation")
    try:
        with TemporaryDirectory(prefix="high-rate60-cmodel-", dir=output.parent) as temporary:
            info, files = derive(prepare_installed_cmodel(Path(temporary)))
        if info["source_sha256"] != before or info["numerical_environment"] != json.loads((output / "environment-before.json").read_bytes()):
            raise ValueError("source/environment changed during evaluation")
        for name, data in files.items():
            (output / name).write_bytes(data)
        (output / "cohort.json").write_bytes(json_bytes(info))
    except Exception as error:
        (output / "evaluation-failure.json").write_bytes(json_bytes({"type": type(error).__name__, "error": str(error)}))
        raise
    finally:
        (output / "source-after.json").write_bytes(json_bytes(source_hashes()))
    if source_hashes() != before:
        raise ValueError("source changed during evaluation")
    return info


def verify(output):
    recorded = json.loads((output / "cohort.json").read_bytes())
    require_contract(recorded["contract"])
    with TemporaryDirectory(prefix="high-rate60-rederive-", dir=output.parent) as temporary:
        expected, files = derive(prepare_installed_cmodel(Path(temporary)))
    if json_bytes(recorded) != json_bytes(expected):
        raise ValueError("60 cohort receipt differs from independent rederivation")
    receipts = {"cohort.json", "source_snapshot", "recipe-before.json", "source-before.json", "source-after.json", "environment-before.json"}
    if {p.name for p in output.iterdir()} != set(files) | receipts:
        raise ValueError("unexpected/missing60 cohort artifact")
    for name, data in files.items():
        if (output / name).is_symlink() or (output / name).read_bytes() != data:
            raise ValueError("independent60 golden mismatch: " + name)
    for name, data in {"recipe-before.json": recipe(), "source-before.json": expected["source_sha256"],
                       "source-after.json": expected["source_sha256"], "environment-before.json": expected["numerical_environment"]}.items():
        if (output / name).read_bytes() != json_bytes(data):
            raise ValueError("pre/post evaluation receipt changed: " + name)
    snapshots = {str(p.relative_to(output / "source_snapshot")): p for p in (output / "source_snapshot").rglob("*") if p.is_file()}
    if snapshots.keys() != expected["source_sha256"].keys():
        raise ValueError("source snapshot inventory mismatch")
    for name, expected_hash in expected["source_sha256"].items():
        if snapshots[name].is_symlink() or digest(snapshots[name].read_bytes()) != expected_hash:
            raise ValueError("source snapshot mismatch: " + name)
    return expected

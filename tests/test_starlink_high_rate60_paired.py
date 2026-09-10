"""Offline60 numerical checks; no actualRTL, admission or source-tail budget."""

import copy
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from tests.starlink_oracle import high_rate60_paired as oracle
from tests.starlink_oracle import xfft_bitacc
from tests.starlink_oracle.ddc import FIR_Q15, _round_shift_q15, x4_ddc_ci16
from tests.starlink_oracle.high_rate60_recipe import APPROVED_SUPPORT, recipe
from tests.starlink_oracle.high_rate60_support import native_support, raw_support
from tests.starlink_oracle.high_rate_paired import read_mem
from tools.generate_starlink_periodic_map_vectors import (
    Model18,
    complex_fixed,
    fixed18,
    normalize,
    pack,
    round_even,
    saturating_numerator,
    unpack,
)


@pytest.fixture(scope="module")
def cohort(tmp_path_factory):
    output = tmp_path_factory.mktemp("high_rate60_cohort") / "cohort"
    before = (xfft_bitacc.XFFT_DATA_BITS, xfft_bitacc.XFFT_FRACTION_BITS)
    info = oracle.generate(output)
    assert before == (xfft_bitacc.XFFT_DATA_BITS, xfft_bitacc.XFFT_FRACTION_BITS) == (24, 23)
    return output, info


def test_approved_support_and_preevaluation_recipe_bytes_unchanged():
    oracle.require_contract(recipe())
    assert all(oracle.digest((oracle.ROOT / name).read_bytes()) == expected for name, expected in APPROVED_SUPPORT.items())
    assert oracle.digest(Path(oracle.__file__).with_name("high_rate60_recipe.py").read_bytes()) == oracle.RECIPE_SOURCE_SHA


@pytest.mark.parametrize("field", sorted(oracle.CONTRACT))
def test_every_top_recipe_mutant_rejected(field):
    changed = copy.deepcopy(recipe())
    value = changed[field]
    changed[field] = value + 1 if type(value) is int else "MUTANT"
    with pytest.raises(ValueError, match="unadmitted60"):
        oracle.require_contract(changed)


@pytest.mark.parametrize("field", sorted(oracle.SUPPORT))
def test_every_approved_support_field_mutant_rejected(field):
    changed = copy.deepcopy(recipe())
    value = changed["support"][field]
    changed["support"][field] = value + 1 if type(value) is int else "MUTANT"
    with pytest.raises(ValueError, match="unadmitted60"):
        oracle.require_contract(changed)


@pytest.mark.parametrize("field,value", [("source_rate_msps", 30), ("source_rate_msps", 60.0),
                                        ("fft_bits", True), ("edge", "lower"), ("coarse_Eh", 1073744004)])
def test_no_rate_type_energy_alias(field, value):
    changed = recipe()
    changed[field] = value
    with pytest.raises(ValueError):
        oracle.require_contract(changed)


def test_source_recipe_exact_rng_overlay_probes_and_native_support():
    source, native = oracle.source_fixture()
    expected = np.random.Generator(np.random.PCG64(0x600052020260910)).integers(
        -400, 401, size=(16423, 2), dtype=np.int64).astype(np.int16)
    overlay = oracle.CENTER - oracle.RAW_FIRST
    expected[overlay:overlay + 264] = native
    for offset, values in recipe()["identity_probes_offset_iq"].items():
        expected[int(offset)] = values
    np.testing.assert_array_equal(source, expected)
    assert overlay == 5173
    assert native_support(oracle.CENTER) == (34359740256, 34359740776)
    assert raw_support(oracle.PRE_FIRST, 768)[1] - oracle.RAW_FIRST == 3111
    assert not recipe()["source_tail_or_service_budget_frozen"]


@pytest.mark.parametrize("count,phase", [(16384, 0), (16422, 0), (16424, 0), (16423, 1), (16423, -1)])
def test_missing_or_wrong_halo_phase_rejected(count, phase):
    source, _ = oracle.source_fixture()
    with pytest.raises(ValueError, match="halo/phase"):
        oracle.conditioner_trace(np.resize(source, (count, 2)), oracle.RAW_FIRST + phase)


def test_missing_raw_boundary_loses_exact_canonical_output():
    source, _ = oracle.source_fixture()
    truncated = x4_ddc_ci16(source[1:], first_input_index=oracle.RAW_FIRST + 1)
    assert len(truncated.samples_iq) == 4095
    assert truncated.output_indexes[0] == oracle.PRE_FIRST + 1


def test_rounding_each_x2_stage_is_not_single_flattened_round():
    source, _ = oracle.source_fixture()
    _, sums, _, indexes, _ = oracle.conditioner_stage(source, oracle.RAW_FIRST)
    # Retain stage1's unrounded Q15 numerator through stage2: deliberately
    # wrong one-round cascade, used only as a sensitivity/control mutation.
    mixed = np.empty(sums.shape, dtype=np.int64)
    for phase, columns, signs in [(0, [0, 1], [1, 1]), (1, [1, 0], [1, -1]),
                                  (2, [0, 1], [-1, -1]), (3, [1, 0], [-1, 1])]:
        mask = indexes % 4 == phase
        mixed[mask] = sums[mask][:, columns] * signs
    final_sums = np.column_stack([np.convolve(mixed[:, lane], FIR_Q15, "valid")[::2] for lane in range(2)])
    assert np.max(np.abs(final_sums)) < 2 ** 53
    wrong = np.clip(np.rint(final_sums / (1 << 30)), -32768, 32767).astype(np.int16)
    _, actual, _ = oracle.conditioner_trace(source)
    assert np.count_nonzero(wrong != actual) > 0


@pytest.mark.parametrize("value", [-(1 << 31), -1073758208, -49152, -16384, -1, 0, 1, 16384, 49152,
                                   1073709056, 1073725440, (1 << 31) - 1])
def test_each_conditioner_rounding_boundary_matches_independent_integer_contract(value):
    result, clips = oracle.rounded_ci16(np.array([[value, value]], dtype=np.int64), 15)
    expected = _round_shift_q15(value)
    assert int(result[0, 0]) == expected[0]
    assert clips == 2 * expected[1]


def test_second_derivation_exact_all_files_and_original_default_width(cohort):
    output, info = cohort
    assert oracle.verify(output) == info
    assert (xfft_bitacc.XFFT_DATA_BITS, xfft_bitacc.XFFT_FRACTION_BITS) == (24, 23)
    assert info["ddc"]["stages"][0]["emitted"] == 8205
    assert info["ddc"]["stages"][1]["emitted"] == 4096
    assert info["coarse"]["coefficient_energy"] == 1073765335
    assert info["native"]["raw"] == 257 and info["native"]["qualified"] == 241
    assert info["pilot"]["raw_step"] == 24
    assert "conditioned60" in info["rounding"]["kernel"] or "conditioned_pss_x4" in info["rounding"]["kernel"]
    with pytest.raises(FileExistsError, match="overwrite"):
        oracle.generate(output)


def words(output, name, rows, width):
    return read_mem((output / name).read_bytes(), rows, width)


def test_every_coarse_input_index_energy_denominator_and_map(cohort):
    output, info = cohort
    canonical = unpack(words(output, "canonical_ci16.mem", 4096, 8), 16)
    packed = words(output, "fft_input_axi48.mem", 3584, 12)
    indexes = words(output, "fft_input_index_u64.mem", 3584, 16)
    energies = words(output, "energies_u38.mem", 3129, 10)
    denominators = words(output, "denominators_u69.mem", 3129, 18)
    for block in range(7):
        samples = canonical[768 + block * 447:768 + block * 447 + 512]
        for p, (i, q) in enumerate(samples):
            assert packed[block * 512 + p] == ((int(q * 4) & 0x3ffff) << 24) | (int(i * 4) & 0x3ffff)
            assert indexes[block * 512 + p] == oracle.FIRST + block * 447 + p
        for p in range(447):
            ex = int(np.sum(samples[p:p + 66] ** 2, dtype=np.int64))
            assert energies[block * 447 + p] == ex
            assert denominators[block * 447 + p] == ex * 1073765335
            assert denominators[block * 447 + p] != ex * 1073744004
    numerators = words(output, "numerators_u69.mem", 3129, 18)
    scores = words(output, "scores_u8.mem", 3129, 2)
    assert scores == [normalize(n, d) for n, d in zip(numerators, denominators, strict=True)]
    for bins in [343, 447]:
        assert words(output, f"map_{bins}x2_u16.mem", bins, 4) == [scores[p] + scores[p + bins] for p in range(bins)]
    assert info["coarse"]["normalization_saturations"] == sum(words(output, "saturated_u1.mem", 3129, 1))


def test_kernel_identity_and_wrong30_denominator_never_reused(cohort, tmp_path):
    output, _ = cohort
    assert (output / "conditioned_kernel_q17.mem").read_bytes() == oracle.KERNEL.read_bytes()
    assert (output / "conditioned_kernel_q17.mem").read_bytes() != oracle.KERNEL.with_name("upper_edge_pss30_x2_ddc_kernel_q17.mem").read_bytes()
    with pytest.raises(ValueError, match="conditioned60 denominator"):
        oracle.coarse_block(np.zeros((512, 2)), np.zeros((512, 2)), None, coefficient_energy=1073744004)


def test_all3584_fft_words_and_bfp_exponents_with_independent_vector_product(cohort, tmp_path):
    output, _ = cohort
    canonical = unpack(words(output, "canonical_ci16.mem", 4096, 8), 16)
    kernel = unpack(words(output, "conditioned_kernel_q17.mem", 512, 9), 18)
    expected = {name: words(output, name + "_q17.mem", 3584, 9) for name in ["forward", "product", "inverse"]}
    ef = words(output, "forward_exponents.mem", 7, 2)
    ei = words(output, "inverse_exponents.mem", 7, 2)
    numerators = words(output, "numerators_u69.mem", 3129, 18)
    saturated = words(output, "saturated_u1.mem", 3129, 1)
    shifts = words(output, "power_shift_u7.mem", 7, 2)
    directory = oracle.prepare_installed_cmodel(tmp_path)
    with Model18(directory) as model:
        for block in range(7):
            samples = canonical[768 + block * 447:768 + block * 447 + 512]
            transformed, exp_f, overflow = model.block_floating_transform(complex_fixed(samples, 15), direction=1)
            f = fixed18(transformed)
            assert not overflow and exp_f == ef[block]
            assert pack(f, 18) == expected["forward"][block * 512:(block + 1) * 512]
            sums = np.column_stack((f[:, 0] * kernel[:, 0] - f[:, 1] * kernel[:, 1],
                                    f[:, 0] * kernel[:, 1] + f[:, 1] * kernel[:, 0]))
            assert np.max(np.abs(sums)) < 2 ** 53
            product = np.rint(sums / (1 << 18)).astype(np.int64)
            assert pack(product, 18) == expected["product"][block * 512:(block + 1) * 512]
            transformed, exp_i, overflow = model.block_floating_transform(complex_fixed(product, 17), direction=0)
            inverse = fixed18(transformed)
            assert not overflow and exp_i == ei[block]
            assert pack(inverse, 18) == expected["inverse"][block * 512:(block + 1) * 512]
            shift = 2 * (7 + exp_f + exp_i)
            assert shifts[block] == shift
            for p, (i, q) in enumerate(inverse[65:]):
                power = int(i) ** 2 + int(q) ** 2
                actual = power << shift
                assert numerators[block * 447 + p] == min(actual, (1 << 69) - 1)
                assert saturated[block * 447 + p] == (actual >= 1 << 69)
    assert (xfft_bitacc.XFFT_DATA_BITS, xfft_bitacc.XFFT_FRACTION_BITS) == (24, 23)


def test_native257_all_tuples_and_packet_independent_direct_integer_sum(cohort):
    output, _ = cohort
    raw = json.loads((output / "native_all_raw_tuples.json").read_bytes())
    capture = unpack(words(output, "native_capture_ci16.mem", 520, 8), 16)
    # Native coefficient ABI has reversed component packing relative to IQ.
    coefficients_q15 = unpack(words(output, "native_coefficients_q15.mem", 264, 8), 16)[:, ::-1]
    assert [r["lag"] for r in raw] == list(range(-128, 129))
    assert sum(r["qualified"] for r in raw) == 241
    for row in raw:
        start = row["lag"] + 128
        samples = capture[start:start + 264]
        real = int(np.sum(samples[:, 0] * coefficients_q15[:, 0] + samples[:, 1] * coefficients_q15[:, 1]))
        imag = int(np.sum(samples[:, 1] * coefficients_q15[:, 0] - samples[:, 0] * coefficients_q15[:, 1]))
        ex, eh = int(np.sum(samples ** 2)), int(np.sum(coefficients_q15 ** 2))
        assert (row["real"], row["imag"], row["Ex"], row["Eh"], row["power"]) == (real, imag, ex, eh, real ** 2 + imag ** 2)
        assert row["start_index"] == oracle.CENTER + row["lag"] and row["tap_count"] == 264 and row["saturation"] == 0
    winner = oracle.select_winner(raw)
    assert winner["lag"] == 0 and winner["Ex"] == winner["Eh"] == winner["real"] and winner["imag"] == 0
    packet = words(output, "native_expected_packet.mem", 26, 8)
    assert packet[:3] == [0x31535350, 0x1a010001, 0x60000520]
    assert packet[3] | packet[4] << 32 == oracle.CENTER
    assert packet[10] == 0x60000001
    assert packet[20] | packet[21] << 32 | packet[22] << 64 == winner["power"]
    # Independently assemble all26 public words, including zero fields and
    # signed/high words. This is not a partial header/argmax check.
    expected_packet = [0x31535350, 0x1a010001, 0x60000520]
    for value in [oracle.CENTER, oracle.CENTER]:
        expected_packet.extend([value & 0xffffffff, value >> 32])
    expected_packet.extend([0, oracle.CENTER & 0xffffffff, oracle.CENTER >> 32, 0x60000001])
    for value in [winner["real"], winner["imag"], winner["Ex"], winner["Eh"]]:
        expected_packet.extend([value & 0xffffffff, (value >> 32) & 0xffffffff])
    expected_packet.append(0)
    for value in [winner["power"], winner["Ex"]]:
        expected_packet.extend([(value >> offset) & 0xffffffff for offset in [0, 32, 64]])
    assert packet == expected_packet


def test_native_tie_legality_and_wrong66_or132_geometry(cohort):
    output, _ = cohort
    rows = json.loads((output / "native_all_raw_tuples.json").read_bytes())
    tied = copy.deepcopy(rows)
    for row in tied:
        row["power"], row["Ex"] = 1, 1
    assert oracle.select_winner(tied)["lag"] == -120
    for taps in [66, 132]:
        changed = copy.deepcopy(rows)
        changed[128]["tap_count"] = taps
        with pytest.raises(ValueError, match="complete241"):
            oracle.select_winner(changed)
        with pytest.raises(ValueError, match="264 taps"):
            oracle.integer_tuple(np.zeros((taps, 2), dtype=np.int16), np.zeros((taps, 2), dtype=np.int16))


@pytest.mark.parametrize("name", ["source_ci16.mem", "source_index_u64.mem", "canonical_ci16.mem", "ddc60_to30_ci16.mem",
                                 "ddc30_to15_sums_s40.mem", "conditioned_kernel_q17.mem", "fft_input_axi48.mem",
                                 "fft_input_index_u64.mem", "denominators_u69.mem", "native_coefficients_q15.mem",
                                 "native_raw_real_s48.mem", "native_expected_packet.mem", "pilot_expected.ci16",
                                 "pilot_raw_support_first_u64.mem"])
def test_full_rederive_rejects_mutated_golden(cohort, tmp_path, name):
    output = tmp_path / "mutant"
    shutil.copytree(cohort[0], output)
    path = output / name
    data = bytearray(path.read_bytes())
    data[0] ^= 1
    path.write_bytes(data)
    with pytest.raises(ValueError, match="golden mismatch"):
        oracle.verify(output)


@pytest.mark.parametrize("name", ["source-before.json", "source-after.json", "environment-before.json", "recipe-before.json"])
def test_before_after_receipt_mutants_rejected(cohort, tmp_path, name):
    output = tmp_path / "mutant"
    shutil.copytree(cohort[0], output)
    (output / name).write_text("{}\n")
    with pytest.raises(ValueError, match="receipt changed"):
        oracle.verify(output)


@pytest.mark.parametrize("mutation", ["actual30_kernel", "coefficient_component_swap", "source_component_swap", "coarse66_native_capture"])
def test_rate_packing_and_native_geometry_substitution_mutants(cohort, tmp_path, mutation):
    output = tmp_path / "mutant"
    shutil.copytree(cohort[0], output)
    if mutation == "actual30_kernel":
        shutil.copyfile(oracle.KERNEL.with_name("upper_edge_pss30_x2_ddc_kernel_q17.mem"), output / "conditioned_kernel_q17.mem")
    elif mutation == "coarse66_native_capture":
        source = output / "native_capture_ci16.mem"
        source.write_bytes(b"".join(source.read_bytes().splitlines(keepends=True)[:66]))
    else:
        name = "native_coefficients_q15.mem" if mutation == "coefficient_component_swap" else "source_ci16.mem"
        source = output / name
        source.write_text("".join(word[4:] + word[:4] + "\n" for word in source.read_text().splitlines()))
    with pytest.raises(ValueError, match="golden mismatch"):
        oracle.verify(output)


def test_source_and_import_closure_bound_to_snapshot(cohort, tmp_path):
    output, info = cohort
    assert info["python_import_edges"] == oracle.python_import_closure()
    assert set(info["python_import_edges"]) <= info["source_sha256"].keys()
    changed = tmp_path / "source_mutant"
    shutil.copytree(output, changed)
    source = changed / "source_snapshot/tests/starlink_oracle/high_rate60_recipe.py"
    source.write_text(source.read_text() + "\n# MUTANT\n")
    with pytest.raises(ValueError, match="snapshot mismatch"):
        oracle.verify(changed)


@pytest.mark.parametrize("n,d", [(-3, 2), (-1, 2), (1, 2), (3, 2), (5, 2)])
def test_signed_nearest_even_is_not_truncation(n, d):
    assert round_even(n, d) == round(n / d)


def test_score_shift_saturation_boundaries():
    assert saturating_numerator(1, 68) == (1 << 68, 0)
    assert saturating_numerator(1, 69) == ((1 << 69) - 1, 1)
    assert saturating_numerator(0, 127) == (0, 0)
    with pytest.raises(ValueError):
        saturating_numerator(1, 128)

"""Synthetic520 offline arithmetic/integrity/admission tests, never RTL evidence."""

import importlib
import json
import re
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import pytest

from tests.starlink_oracle import bank_native_paired as old
from tests.starlink_oracle import bank_native_true_pss as oracle
from tests.starlink_oracle import xfft_bitacc as fft
from tests.test_starlink_bank_native_paired import CHECKS, ROOT, RUNNER, probe, verifier


def write_payloads(root, payloads):
    root.mkdir()
    for name, data in payloads.items():
        path = root / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(data)


@pytest.fixture(scope="module")
def original(tmp_path_factory):
    root = tmp_path_factory.mktemp("true-pss-original")
    source, coefficients = oracle.original_source()
    score, _ = oracle.coarse_vectors(source[768:2174], coefficients)
    pilot, metadata = oracle.pilot_vectors(source)
    pilot["paired_oracle.json"] = oracle.json_bytes(metadata)
    write_payloads(root / "score", score)
    write_payloads(root / "pilot", pilot)
    old.generate(root / "pilot", root / "native", anchor=520)
    return root


@pytest.fixture(scope="module")
def cohort(tmp_path_factory, original):
    destination = tmp_path_factory.mktemp("true-pss") / "cohort"
    oracle.generate(original / "score", original / "pilot", destination)
    return destination


def test_original_cmodel_bootstrap_and_global_width_unchanged(original):
    for name, expected in oracle.ORIGINAL_SCORE_SHA256.items():
        assert old.digest(original / "score" / name) == expected
    for name, expected in oracle.ORIGINAL_PILOT_SHA256.items():
        assert old.digest(original / "pilot" / name) == expected
    assert (fft.XFFT_DATA_BITS, fft.XFFT_FRACTION_BITS) == (24, 23)


def test_exact_only66word_source_overlay_and_preserved_controls(cohort, original):
    original_source = old.read_words(original / "pilot/paired_source_ci16.mem", 4096, 8)
    source = old.read_words(cohort / "pilot/paired_source_ci16.mem", 4096, 8)
    numeric = old.read_words(cohort / "score/samples_ci16.mem", 1406, 8)
    assert source[:1288] == original_source[:1288] and source[1354:] == original_source[1354:]
    assert sum(a != b for a, b in zip(source, original_source, strict=True)) == 66
    assert source[768:2174] == numeric
    coefficients = old.read_words(cohort / "native/native_coefficients_q15.mem", 66, 8)
    swapped = [(value & 65535) << 16 | value >> 16 for value in coefficients]
    for start in (100, 447, 520, 1000):
        assert numeric[start:start + 66] == swapped
    assert coefficients != swapped  # Missing publicAXI lowI/highQ swap fails.
    assert (cohort / "native/native_coefficients_q15.mem").read_bytes() == (original / "native/native_coefficients_q15.mem").read_bytes()


def test_all61_tuples_independent_python_int_fraction_and_all26_words(cohort):
    def signed16(value):
        return value - 65536 if value & 32768 else value

    source = [(signed16(w & 65535), signed16(w >> 16)) for w in
              old.read_words(cohort / "pilot/paired_source_ci16.mem", 4096, 8)]
    coefficients = [(signed16(w >> 16), signed16(w & 65535)) for w in
                    old.read_words(cohort / "native/native_coefficients_q15.mem", 66, 8)]
    manifest = json.loads((cohort / "native/native_oracle.json").read_text())
    ratios = {}
    for expected in manifest["qualified_tuples"]:
        lag = expected["lag"]
        re_sum = im_sum = ex = eh = 0
        for (i, q), (ci, cq) in zip(source[1288 + lag:1354 + lag], coefficients, strict=True):
            re_sum += i * ci + q * cq
            im_sum += q * ci - i * cq
            ex += i * i + q * q
            eh += ci * ci + cq * cq
            assert all(-(1 << 47) <= value < 1 << 47 for value in (re_sum, im_sum, ex, eh))
        assert 0 < ex < 1 << 38 and 0 < eh < 1 << 31
        assert -(1 << 38) <= re_sum < 1 << 38 and -(1 << 38) <= im_sum < 1 << 38
        assert expected == {"lag": lag, "real": re_sum, "imag": im_sum, "Ex": ex, "Eh": eh,
                            "saturation_events": 0, "legal": True}
        ratios[lag] = Fraction(re_sum * re_sum + im_sum * im_sum, ex * eh)
    assert len(ratios) == 61 and max(ratios, key=ratios.get) == 0 and ratios[0] == 1
    energy = 1073742825
    center = old.FIRST + 520
    expected = [0x31535350, 0x1A010001, 0x15005201, center & 0xFFFFFFFF, center >> 32,
                center & 0xFFFFFFFF, center >> 32, 0, center & 0xFFFFFFFF, center >> 32,
                0x15000002, energy, 0, 0, 0, energy, 0, energy, 0, 0,
                energy**2 & 0xFFFFFFFF, energy**2 >> 32, 0, energy, 0, 0]
    assert old.read_words(cohort / "native/native_expected_packet.mem", 26, 8) == expected
    assert manifest["capture_bounds"] == [8589935064, 8589935194]
    assert manifest["request_id"] != old.PROFILES[520][0]
    assert manifest["coefficient_generation"] != old.GENERATION


def test_each_nonperiodic_block_and_exact_map_pilot(cohort, original):
    manifest = json.loads((cohort / "score/pipeline_vectors.json").read_text())
    assert manifest["forward_exponents"] == [5, 5, 4]
    assert manifest["inverse_exponents"] == [3, 3, 4]
    assert manifest["power_shifts"] == [30] * 3
    assert manifest["spectrum_product_shift"] == 18
    assert manifest["numerator_saturation_events"] == 0
    for name in ("forward_q17.mem", "product_q17.mem", "inverse_q17.mem"):
        before = old.read_words(original / "score" / name, 1536, 9)
        after = old.read_words(cohort / "score" / name, 1536, 9)
        assert before[:512] == after[:512] and before[1024:] == after[1024:]
        assert before[512:1024] != after[512:1024]
        assert after[:512] != after[512:1024] != after[1024:]
    scores = old.read_words(cohort / "score/scores_u8.mem", 1341, 2)
    assert [scores[index] for index in (100, 447, 520, 1000)] == [255] * 4
    assert old.read_words(cohort / "score/paired_map_u32.mem", 447, 8) == [scores[k] + scores[k + 447] for k in range(447)]
    binary = (cohort / "pilot/paired_pilot_expected.ci16").read_bytes()
    assert len(binary) == 2048 and binary != (original / "pilot/paired_pilot_expected.ci16").read_bytes()
    assert binary == b"".join(word.to_bytes(4, "little") for word in old.read_words(cohort / "pilot/paired_pilot_ci16.mem", 512, 8))
    for name in ("paired_metadata.mem", "paired_pilot_newest.mem"):
        assert (cohort / "pilot" / name).read_bytes() == (original / "pilot" / name).read_bytes()
    assert oracle.verify(cohort / "score", cohort / "pilot", cohort / "native")["actual_rtl_simulation_qualified"] is False


def test_every_product_energy_inverse_scale_and_score_from_independent_integers(cohort):
    def unpack(name, rows, bits):
        packed = old.read_words(cohort / "score" / name, rows, (2 * bits + 3) // 4)
        def signed(value):
            return value - (1 << bits) if value & (1 << (bits - 1)) else value
        return [(signed(w & ((1 << bits) - 1)), signed(w >> bits)) for w in packed]

    source = unpack("samples_ci16.mem", 1406, 16)
    forward = unpack("forward_q17.mem", 1536, 18)
    product = unpack("product_q17.mem", 1536, 18)
    kernel = unpack("upper_edge_pss_kernel_q17.mem", 512, 18)
    inverse = unpack("inverse_q17.mem", 1536, 18)
    for position, ((fi, fq), (pi, pq)) in enumerate(zip(forward, product, strict=True)):
        ki, kq = kernel[position % 512]
        # Fraction.__round__ is independent exact signed ties-even arithmetic.
        assert (pi, pq) == (round(Fraction(fi * ki - fq * kq, 1 << 18)),
                            round(Fraction(fi * kq + fq * ki, 1 << 18)))
    energies = old.read_words(cohort / "score/energies_u38.mem", 1341, 10)
    numerators = old.read_words(cohort / "score/numerators_u69.mem", 1341, 18)
    denominators = old.read_words(cohort / "score/denominators_u69.mem", 1341, 18)
    scores = old.read_words(cohort / "score/scores_u8.mem", 1341, 2)
    forward_exp = old.read_words(cohort / "score/forward_exponents.mem", 3, 2)
    inverse_exp = old.read_words(cohort / "score/inverse_exponents.mem", 3, 2)
    for position in range(1341):
        block, local = divmod(position, 447)
        re_value, im_value = inverse[block * 512 + local + 65]
        energy = sum(i*i + q*q for i, q in source[position:position + 66])
        numerator = min((re_value**2 + im_value**2) << (2 * (7 + forward_exp[block] + inverse_exp[block])), (1 << 69) - 1)
        denominator = energy * 1073742825
        assert energies[position] == energy
        assert numerators[position] == numerator
        assert denominators[position] == denominator
        assert scores[position] == min(255, round(Fraction(255 * numerator, denominator)))


@pytest.mark.parametrize("numerator,denominator,expected", [(1, 2, 0), (3, 2, 2), (-1, 2, 0), (-3, 2, -2), (5, 2, 2), (-5, 2, -2)])
def test_signed_ties_even(numerator, denominator, expected):
    assert oracle.round_even(numerator, denominator) == expected


def test_69bit_saturation_and_score_ties():
    assert oracle.normalize(1, 69, 1 << 68) == (255, (1 << 69) - 1, 1)
    assert oracle.normalize(1, 68, 1 << 68) == (255, 1 << 68, 0)
    assert oracle.normalize(1, 0, 510) == (0, 1, 0)
    assert oracle.normalize(3, 0, 510) == (2, 3, 0)
    assert oracle.normalize(0, 0, 0) == (0, 0, 0)
    with pytest.raises(ValueError):
        oracle.normalize(1 << 36, 0, 1)


@pytest.mark.parametrize("field,value", [("sample_energy", 0), ("coefficient_energy", 0),
                                        ("sample_energy", 1 << 38), ("coefficient_energy", 1 << 31),
                                        ("real", 1 << 38), ("imag", -(1 << 38) - 1),
                                        ("saturation_events", 1)])
def test_nonwinning_illegal_tuple_rejected(monkeypatch, field, value):
    from dataclasses import replace
    source, coefficients = oracle.original_source()
    source[1288:1354] = coefficients
    original = oracle.fixed_correlate_ci16
    calls = 0

    def mutate(*arguments):
        nonlocal calls
        calls += 1
        result = original(*arguments)
        return replace(result, **{field: value}) if calls == 3 else result

    monkeypatch.setattr(oracle, "fixed_correlate_ci16", mutate)
    with pytest.raises(ValueError, match="tuple -30 violates"):
        oracle.native_vectors(source, coefficients)


@pytest.mark.parametrize("name", ["score/samples_ci16.mem", "score/forward_q17.mem", "score/product_q17.mem",
                                 "score/inverse_q17.mem", "score/forward_exponents.mem", "score/inverse_exponents.mem",
                                 "score/scores_u8.mem", "score/paired_map_u32.mem", "pilot/paired_source_ci16.mem",
                                 "pilot/paired_pilot_expected.ci16", "native/native_expected_packet.mem",
                                 "native/native_coefficients_q15.mem", "fixture.json"])
def test_rehashed_wrong_golden_rejected(cohort, tmp_path, name):
    target = tmp_path / "cohort"
    shutil.copytree(cohort, target)
    path = target / name
    data = bytearray(path.read_bytes()); data[0] ^= 1
    path.write_bytes(data)
    # A self-consistent hash receipt cannot bless corrupted or stale arithmetic.
    if name != "fixture.json":
        manifest = json.loads((target / "fixture.json").read_text())
        manifest["generated_sha256"][name] = old.digest(path)
        (target / "fixture.json").write_bytes(oracle.json_bytes(manifest))
    with pytest.raises(ValueError, match="golden mismatch"):
        oracle.verify(target / "score", target / "pilot", target / "native")


@pytest.mark.parametrize("name", ["forward_q17.mem", "product_q17.mem", "inverse_q17.mem",
                                 "forward_exponents.mem", "inverse_exponents.mem", "scores_u8.mem"])
def test_old_goldens_cannot_qualify_new_source(cohort, original, tmp_path, name):
    target = tmp_path / "cohort"; shutil.copytree(cohort, target)
    shutil.copyfile(original / "score" / name, target / "score" / name)
    with pytest.raises(ValueError, match="golden mismatch"):
        oracle.verify(target / "score", target / "pilot", target / "native")


@pytest.mark.parametrize("mutation", ["missing", "extra", "empty_directory", "symlink", "cohort"])
def test_exact_inventory_and_cohort(cohort, tmp_path, mutation):
    target = tmp_path / "cohort"; shutil.copytree(cohort, target)
    if mutation == "missing":
        (target / "score/inverse_q17.mem").unlink()
    elif mutation == "extra":
        (target / "extra").write_text("not frozen")
    elif mutation == "empty_directory":
        (target / "unfrozen").mkdir()
    elif mutation == "symlink":
        path = target / "score/inverse_q17.mem"; path.unlink()
        path.symlink_to(cohort / "score/inverse_q17.mem")
    with pytest.raises(ValueError, match="inventory|cohort"):
        oracle.verify(target / "score", cohort / "pilot" if mutation == "cohort" else target / "pilot", target / "native")


def test_whole_coefficient_packing_swap_cannot_be_relabelled(cohort, tmp_path):
    target = tmp_path / "cohort"; shutil.copytree(cohort, target)
    path = target / "native/native_coefficients_q15.mem"
    values = old.read_words(path, 66, 8)
    path.write_bytes(oracle.words(((word & 65535) << 16 | word >> 16 for word in values), 8))
    receipt = json.loads((target / "fixture.json").read_text())
    receipt["generated_sha256"]["native/native_coefficients_q15.mem"] = old.digest(path)
    (target / "fixture.json").write_bytes(oracle.json_bytes(receipt))
    with pytest.raises(ValueError, match="native_coefficients_q15"):
        oracle.verify(target / "score", target / "pilot", target / "native")


def test_no_overwrite_and_wrong_original_source(original, cohort, tmp_path):
    with pytest.raises(ValueError, match="overwrite"):
        oracle.generate(original / "score", original / "pilot", cohort)
    with pytest.raises(ValueError, match="original cohort"):
        oracle.generate(cohort / "score", original / "pilot", tmp_path / "out")
    assert not (tmp_path / "out").exists()
    with pytest.raises(ValueError):
        old.verify(cohort / "pilot", original / "native", anchor=520)


@pytest.mark.parametrize("clock", [175, 200])
def test_real_tcl_admission_and_complete_preproject_freeze(cohort, tmp_path, clock):
    output = tmp_path / "run"
    result = probe([output, cohort / "score", cohort / "pilot", cohort / "native", clock, "520-pss"])
    assert result.returncode == 2 and result.stderr.strip() == "ADMITTED", result.stderr
    frozen = output / "frozen_sources"
    for path in cohort.rglob("*"):
        if path.is_file():
            assert (frozen / path.name).read_bytes() == path.read_bytes()
    scope = (output / "scope.txt").read_text()
    assert "native_anchor=520-pss native_expected_lag=0" in scope
    assert "score_fixture_unchanged=false fixture=bank-native-original-overlay-520-pss-v1" in scope
    assert (frozen / Path(__file__).name).read_bytes() == Path(__file__).read_bytes()
    mapping = (frozen / "python_runtime_inventory.txt").read_text().splitlines()
    assert len(mapping) == 12
    assert {line.split()[0] for line in mapping} == set(oracle.PYTHON_DEPENDENCIES)
    for line in mapping:
        relative, encoded = line.split()
        assert (frozen / encoded).read_bytes() == (ROOT / relative).read_bytes()
        assert encoded in scope  # pre-project source hash inventory


def test_true_profile_relative_paths(cohort, tmp_path):
    target = tmp_path / "cohort"; shutil.copytree(cohort, target)
    result = probe(["run", "cohort/score", "cohort/pilot", "cohort/native", 175, "520-pss"], cwd=tmp_path)
    assert result.returncode == 2 and result.stderr.strip() == "ADMITTED", result.stderr


@pytest.mark.parametrize("profile", [447, 520, "520-pss"])
def test_no_implicit_source_profile_fallback(cohort, original, tmp_path, profile):
    source = original if profile == "520-pss" else cohort
    result = probe([tmp_path / "out", source / "score", source / "pilot", source / "native", 175, profile])
    assert result.returncode == 2 and "independent native oracle rejected" in result.stderr
    assert not (tmp_path / "out").exists()


def test_full_runtime_dependency_closure_without_policy_imports():
    program = """import importlib,json,pathlib,sys
root=pathlib.Path.cwd().resolve()
importlib.import_module('tests.starlink_oracle.bank_native_true_pss')
print(json.dumps(sorted({str(pathlib.Path(m.__file__).resolve().relative_to(root))
 for n,m in sys.modules.items() if n == 'tests' or n.startswith('tests.')})))
"""
    result = subprocess.run([sys.executable, "-c", program], cwd=ROOT, text=True, capture_output=True, check=True, timeout=15)
    assert set(json.loads(result.stdout)) == set(oracle.PYTHON_DEPENDENCIES)
    source = RUNNER.read_text()
    base = re.findall(r"set native_python_relatives \{([^}]+)\}", source)
    added = re.findall(r"lappend native_python_relatives ([^\n]+)", source)
    assert len(base) == len(added) == 1
    assert set((base[0] + added[0]).split()) == set(oracle.PYTHON_DEPENDENCIES)
    assert importlib.import_module("tests.starlink_oracle.bank_native_paired").PROFILES == {447: (0x15004470, 0), 520: (0x15005200, -17)}


@pytest.mark.parametrize("mutation", [None, "old_packet", "missing_profile", "duplicate_profile", "wrong_profile",
                                     "zero_overlap", "late_FAIL", "late_FAULT", "late_Fatal", "late_ERROR"])
def test_actual_postprocessor_strict_profile_and_late_failure(cohort, original, tmp_path, mutation):
    packet = old.read_words(cohort / "native/native_expected_packet.mem", 26, 8)
    (tmp_path / "native_expected_packet.mem").write_bytes((cohort / "native/native_expected_packet.mem").read_bytes())
    if mutation == "old_packet":
        packet = old.read_words(original / "native/native_expected_packet.mem", 26, 8)
    lines = [f"BANK_NATIVE_PACKET_WORD pass={n // 26} word={n % 26} data={packet[n % 26]:08x}" for n in range(52)]
    profile = "BANK_NATIVE_TRUE_PSS_PASS profile=520-pss request=15005201 generation=15000002 winner_lag=0 source_overlay=520:586 SYNTHETIC_STATIC_NOT_CAUSAL"
    lines += ["BANK_NATIVE_ADMISSION index=8589934602 capture_start=8589935064 lead=461 deadline=8589934704",
              "BANK_NATIVE_OVERLAP capture_fft_fast_cycles=319 compute_coarse_pilot_accepts=842",
              "BANK_NATIVE_EXACT_PASS packets=1 public_reads=52 capture_words=130 taps=66 qualified_lags=61 retained_across_stop=1 injection=0 timestamp_equals_index=1",
              profile,
              "BANK_NATIVE_PAIRED_PASS source_msps=15 fast_mhz=175 anchor=520 source_words=4096 scores=894 map_words=447 pilot_bytes=2048 STATIC_ANCHOR_NOT_CAUSAL_NO_RF_PHYSICAL"]
    if mutation == "missing_profile":
        lines.remove(profile)
    elif mutation == "duplicate_profile":
        lines.append(profile)
    elif mutation == "wrong_profile":
        lines[-2] = profile.replace("15005201", "15005200")
    elif mutation == "zero_overlap":
        lines[53] = lines[53].replace("fast_cycles=319", "fast_cycles=0")
    elif mutation and mutation.startswith("late_"):
        lines.append(mutation[5:] + ": after apparent terminal PASS")
    result = verifier(tmp_path, "\n".join(lines) + "\n", anchor="520-pss")
    assert (result.returncode == 0) == (mutation is None), result.stderr


def test_strict_overlap_stop_and_default_gates_remain():
    checks = CHECKS.read_text()
    assert "parameter integer NATIVE_OFFSET = 447;" in checks
    assert "parameter integer NATIVE_TRUE_PSS = 0;" in checks
    assert "native_capture_fft_overlap < 1" in checks
    assert "native_compute_overlap < 1" in checks
    assert "native_retained_at_stop != 1" in checks

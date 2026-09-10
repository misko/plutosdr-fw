"""Bounded smoke oracle/runner policy tests; no RTL arithmetic pass implied."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from tests.starlink_oracle import bank_native_paired as oracle
from tests.starlink_oracle.fixed import quantize_q15
from tests.starlink_oracle.waveforms import projected_pss
from tests.test_starlink_paired_realtime_psma_stop_policy import (
    GEOMETRY,
    generate_pilot_vectors,
)

ROOT = Path(__file__).resolve().parents[1]
ACQ = ROOT / "hdl/library/starlink_pss_acquisition"
RUNNER = ACQ / "simulate_bank_native_paired.tcl"
HELPER = ACQ / "prepare_bank_native_paired.tcl"
OLD_BENCH = ACQ / "tb/tb_starlink_pss_paired_realtime_psma_stop.sv"
CHECKS = ACQ / "tb/bank_native_paired_checks.svh"


@pytest.fixture
def vectors(tmp_path):
    score, pilot, native = [tmp_path / name for name in ("score", "pilot", "native")]
    score.mkdir()
    for name, (rows, width) in GEOMETRY.items():
        (score / f"{name}.mem").write_text(("0" * width + "\n") * rows)
    coefficients = quantize_q15(projected_pss(15_000_000, "upper"))
    # Same deterministic native input contract as the immutable 15-rate fixture;
    # the other zero-filled files remain policy-only stand-ins, never RTL goldens.
    samples = np.random.default_rng(0x15F17E).integers(-1200, 1201, size=(1406, 2), dtype=np.int16)
    for start in (100, 447, 1000):
        samples[start:start + 66] = coefficients
    words = [f"{(int(q) & 65535) << 16 | (int(i) & 65535):08x}" for i, q in samples]
    (score / "samples_ci16.mem").write_text("\n".join(words) + "\n")
    generate_pilot_vectors(score, pilot)
    oracle.generate(pilot, native)
    return score, pilot, native


def tcl(script, *, cwd=None):
    return subprocess.run(["tclsh"], input=script, text=True, capture_output=True,
                          timeout=20, check=False, cwd=cwd, env={**os.environ,
                          "STARLINK_NATIVE_PYTHON": sys.executable,
                          "PATH": f"{Path(sys.executable).parent}:{os.environ['PATH']}"})


def probe(arguments, *, cwd=None):
    return tcl('proc version {args} {return 2022.2}\nproc set_param {args} {}\n'
               'proc create_project {args} {error ADMITTED}\n'
               + "set argv [list " + " ".join(f"{{{arg}}}" for arg in arguments) + "]\n"
               + f"set argc [llength $argv]\nif {{[catch {{source {{{RUNNER}}}}} e]}} "
               + '{puts stderr $e; exit 2}\n', cwd=cwd)


def test_exact_packet_and_packing(vectors):
    _, pilot, native = vectors
    receipt = oracle.verify(pilot, native)
    assert receipt["qualified_tuple_legality"]["checked"] == 61
    assert receipt["winner_lag"] == 0
    expected = oracle.read_words(native / "native_expected_packet.mem", 26, 8)
    energy = 1073742825
    assert expected == [0x31535350, 0x1A010001, oracle.REQUEST,
                        oracle.CENTER & 0xFFFFFFFF, oracle.CENTER >> 32,
                        oracle.CENTER & 0xFFFFFFFF, oracle.CENTER >> 32, 0,
                        oracle.CENTER & 0xFFFFFFFF, oracle.CENTER >> 32, oracle.GENERATION,
                        energy, 0, 0, 0, energy, 0, energy, 0, 0,
                        energy**2 & 0xFFFFFFFF, energy**2 >> 32, 0, energy, 0, 0]
    coefficients = quantize_q15(projected_pss(15_000_000, "upper"))
    words = oracle.read_words(native / "native_coefficients_q15.mem", 66, 8)
    raw = oracle.read_words(pilot / "paired_source_ci16.mem", 4096, 8)[1215:1281]
    assert [(w & 65535) << 16 | w >> 16 for w in words] == raw
    assert words != raw  # Deliberate missing AXI swap is detectable.
    assert np.any(coefficients[:, 0] != coefficients[:, 1])


@pytest.mark.parametrize("mutation", ["source", "packet", "coefficients", "missing", "extra", "receipt"])
def test_oracle_rejects_mutation(vectors, mutation):
    _, pilot, native = vectors
    if mutation == "extra":
        (native / "extra").write_text("x")
    elif mutation == "missing":
        (native / "native_expected_packet.mem").unlink()
    elif mutation == "receipt":
        path = native / "native_oracle.json"
        data = json.loads(path.read_text()); data["winner_lag"] = 1
        path.write_text(json.dumps(data))
    else:
        path = {"source": pilot / "paired_source_ci16.mem",
                "packet": native / "native_expected_packet.mem",
                "coefficients": native / "native_coefficients_q15.mem"}[mutation]
        lines = path.read_text().splitlines()
        lines[1215 if mutation == "source" else 0] = "ffffffff"
        path.write_text("\n".join(lines) + "\n")
    with pytest.raises((ValueError, FileNotFoundError)):
        oracle.verify(pilot, native)


def test_no_overwrite(vectors):
    _, pilot, native = vectors
    with pytest.raises(ValueError, match="overwrite"):
        oracle.generate(pilot, native)


@pytest.mark.parametrize("anchor", [447, 520])
@pytest.mark.parametrize("clock", [175, 200])
def test_real_runner_admits_and_freezes(vectors, tmp_path, clock, anchor):
    score, pilot, native = vectors
    if anchor == 520:
        native = tmp_path / "native520"
        oracle.generate(pilot, native, anchor=anchor)
    output = tmp_path / "run"
    result = probe([output, score, pilot, native, clock, anchor])
    assert result.returncode == 2 and result.stderr.strip() == "ADMITTED", result.stderr
    frozen = output / "frozen_sources"
    assert (frozen / OLD_BENCH.name).read_bytes() == OLD_BENCH.read_bytes()
    bench = (frozen / "tb_starlink_bank_native_paired.sv").read_text()
    assert "forever #(500.0 / 15) sample_clk" in bench
    assert "USE_DSP_REDUCER(1)" in bench and "ENABLE_INJECTION(0)" in bench
    assert "run_native_command();" in bench and "verify_native_terminal();" in bench
    assert (frozen / "native_expected_packet.mem").read_bytes() == (native / "native_expected_packet.mem").read_bytes()
    assert "sample_clock_MHz=15" in (output / "scope.txt").read_text()
    assert f"native_anchor={anchor}" in (output / "scope.txt").read_text()
    assert "starlink_pss_exact_track_reducer.v" in (output / "scope.txt").read_text()
    assert (frozen / Path(__file__).name).read_bytes() == Path(__file__).read_bytes()
    manifest = (frozen / "python_runtime_inventory.txt").read_text().splitlines()
    assert len(manifest) == 10
    for line in manifest:
        relative, encoded = line.split()
        assert encoded == "python_runtime__" + relative.replace("/", "__")
        assert (frozen / encoded).read_bytes() == (ROOT / relative).read_bytes()


def test_all_relative_paths_keep_callers_coordinates(vectors, tmp_path):
    score, pilot, native = vectors
    output = tmp_path / "relative-output"
    result = probe([output.name, score.name, pilot.name, native.name, 175], cwd=tmp_path)
    assert result.returncode == 2 and result.stderr.strip() == "ADMITTED", result.stderr
    frozen = output / "frozen_sources"
    assert (frozen / "native_expected_packet.mem").read_bytes() == (native / "native_expected_packet.mem").read_bytes()
    assert (frozen / "paired_source_ci16.mem").read_bytes() == (pilot / "paired_source_ci16.mem").read_bytes()
    assert (frozen / "samples_ci16.mem").read_bytes() == (score / "samples_ci16.mem").read_bytes()
    assert (frozen / HELPER.name).read_bytes() == HELPER.read_bytes()
    assert (frozen / Path(__file__).name).read_bytes() == Path(__file__).read_bytes()


@pytest.mark.parametrize("clock", ["150", "30", "175.0", "1;exit"])
def test_clock_rejected_before_allocation(tmp_path, clock):
    result = probe([tmp_path / "out", "missing", "missing", "missing", clock])
    assert "clock must" in result.stderr and not (tmp_path / "out").exists()


@pytest.mark.parametrize("mutation", ["missing", "duplicate"])
def test_bench_anchor_fail_closed(tmp_path, mutation):
    bench = OLD_BENCH.read_text()
    anchor = "    repeat (500) @(negedge clk);"
    bench = bench.replace(anchor, "" if mutation == "missing" else anchor + anchor)
    path = tmp_path / "bench.sv"; path.write_text(bench)
    result = tcl(f"source {{{HELPER}}}\nset f [open {{{path}}}]; set b [read $f]; close $f\n"
                 'if {[catch {prepare_native_paired_bench $b {}} e]} {puts stderr $e; exit 2}\n')
    assert result.returncode == 2 and "anchor missing or duplicated" in result.stderr


def verifier(tmp_path, log, *, anchor=447):
    # Execute the exact production postprocessor procedure, not a Python copy.
    source = RUNNER.read_text()
    procedure = source[source.index("proc native_verify_outputs"):source.rindex("eval $native_runner")]
    directory = tmp_path / "sim"; directory.mkdir()
    (directory / "simulate.log").write_text(log)
    return tcl(f"source {{{ACQ / 'verify_realtime_probe_result.tcl'}}}\n{procedure}\n"
               f"if {{[catch {{native_verify_outputs {{{directory}}} {{{tmp_path}}} 175 {anchor}}} e]}} "
               '{puts stderr $e; exit 2}\n')


@pytest.mark.parametrize("bad", ["FAIL late", "FAULT late", "Fatal: late", "ERROR: late",
                                 "BANK_NATIVE_PAIRED_FAIL late", "BANK_NATIVE_FAULT late"])
def test_late_failure_rejected_even_after_pass(tmp_path, bad):
    result = verifier(tmp_path, "BANK_NATIVE_PAIRED_PASS placeholder\n" + bad + "\n")
    assert result.returncode == 2 and "contains failure evidence" in result.stderr


@pytest.mark.parametrize("mutation", [None, "word", "order", "missing", "duplicate", "clock", "lead", "overlap",
                                     "late_error", "late_receipt_suffix"])
@pytest.mark.parametrize("anchor", [447, 520])
def test_exact_terminal_receipt_policy(vectors, tmp_path, mutation, anchor):
    _, pilot, native = vectors
    if anchor == 520:
        native = tmp_path / "native520"
        oracle.generate(pilot, native, anchor=anchor)
    packet = oracle.read_words(native / "native_expected_packet.mem", 26, 8)
    (tmp_path / "native_expected_packet.mem").write_bytes((native / "native_expected_packet.mem").read_bytes())
    exact = ("BANK_NATIVE_EXACT_PASS packets=1 public_reads=52 capture_words=130 taps=66 qualified_lags=61 "
             "retained_across_stop=1 injection=0 timestamp_equals_index=1")
    terminal = (f"BANK_NATIVE_PAIRED_PASS source_msps=15 fast_mhz=175 anchor={anchor} source_words=4096 scores=894 "
                "map_words=447 pilot_bytes=2048 STATIC_ANCHOR_NOT_CAUSAL_NO_RF_PHYSICAL")
    lines = [f"BANK_NATIVE_PACKET_WORD pass={n // 26} word={n % 26} data={packet[n % 26]:08x}"
             for n in range(52)]
    start, lead = oracle.FIRST + anchor - 32, anchor - 73
    lines += [f"BANK_NATIVE_ADMISSION index=8589934616 capture_start={start} lead={lead} deadline=8589934704",
              "BANK_NATIVE_OVERLAP capture_fft_fast_cycles=30 compute_coarse_pilot_accepts=30", exact, terminal]
    if mutation == "word":
        lines[0] = lines[0].replace("31535350", "31535351")
    elif mutation == "order":
        lines[0], lines[1] = lines[1], lines[0]
    elif mutation == "missing":
        lines.pop()
    elif mutation == "duplicate":
        lines.append(terminal)
    elif mutation == "clock":
        lines[-1] = terminal.replace("175", "200")
    elif mutation == "lead":
        lines[52] = lines[52].replace(f"lead={lead}", f"lead={lead - 1}")
    elif mutation == "overlap":
        lines[53] = lines[53].replace("fast_cycles=30", "fast_cycles=0")
    elif mutation == "late_error":
        lines.append("BANK_NATIVE_FAULT after apparent terminal")
    elif mutation == "late_receipt_suffix":
        lines.append("PAIRED_LATE_FAULT_PASS actual_invalid_release=1 "
                     "failed_joint_health=1 terminal_coordinates_retained=1 pilot_bytes_preserved=1 ERROR: hidden")
    result = verifier(tmp_path, "\n".join(lines) + "\n", anchor=anchor)
    assert (result.returncode == 0) == (mutation is None), result.stderr


@pytest.mark.parametrize("field,value", [("sample_energy", 0), ("coefficient_energy", 0),
                                        ("sample_energy", 1 << 38), ("coefficient_energy", 1 << 31),
                                        ("real", 1 << 38), ("imag", -(1 << 38) - 1),
                                        ("saturation_events", 1)])
def test_nonwinning_illegal_tuple_rejected(vectors, monkeypatch, field, value):
    from dataclasses import replace
    _, pilot, _ = vectors
    original = oracle.fixed_correlate_ci16
    calls = 0

    def changed(*arguments):
        nonlocal calls
        result = original(*arguments)
        calls += 1
        return replace(result, **{field: value}) if calls == 3 else result  # lag−30, not winner0

    monkeypatch.setattr(oracle, "fixed_correlate_ci16", changed)
    with pytest.raises(ValueError, match="tuple -30 violates"):
        oracle.derive(pilot)


def test_profile520_all26_words_and_original_control_identity(vectors, tmp_path):
    _, pilot, old_native = vectors
    destination = tmp_path / "native520"
    before = {p.name: p.read_bytes() for p in pilot.iterdir()}
    receipt = oracle.generate(pilot, destination, anchor=520)
    assert receipt == oracle.verify(pilot, destination, anchor=520)
    assert receipt["capture_bounds"] == [8589935064, 8589935194]
    assert receipt["winner_lag"] == -17 and receipt["qualified_tuple_legality"]["checked"] == 61
    expected = """31535350 1a010001 15005200 000001f8 00000002 000001f8 00000002 ffffffef
    000001e7 00000002 15000001 089673ea 00000000 fe57dea9 ffffffff 0c330538 00000000
    400003e9 00000000 00000000 1f3b9d75 004c7e59 00000000 0c330538 00000000 00000000"""
    assert oracle.read_words(destination / "native_expected_packet.mem", 26, 8) == [int(w, 16) for w in expected.split()]
    assert (destination / "native_coefficients_q15.mem").read_bytes() == (old_native / "native_coefficients_q15.mem").read_bytes()
    assert before == {p.name: p.read_bytes() for p in pilot.iterdir()}
    with pytest.raises(ValueError, match="golden mismatch"):
        oracle.verify(pilot, destination)  # No implicit profile inference/fallback.


@pytest.mark.parametrize("anchor", ["519", "520.0", "1000", "520;exit"])
def test_unknown_profile_rejected_before_allocation(tmp_path, anchor):
    result = probe([tmp_path / "out", "missing", "missing", "missing", 175, anchor])
    assert "anchor must" in result.stderr and not (tmp_path / "out").exists()


def test_wrong_profile_oracle_rejected_before_allocation(vectors, tmp_path):
    score, pilot, native = vectors
    result = probe([tmp_path / "out", score, pilot, native, 175, 520])
    assert "independent native oracle rejected" in result.stderr and not (tmp_path / "out").exists()


def test_deterministic_python_inventory_matches_loaded_import_closure():
    source = RUNNER.read_text()
    match = re.findall(r"set native_python_relatives \{([^}]+)\}", source)
    assert len(match) == 1
    declared = set(match[0].split())
    program = """import importlib,json,pathlib,sys
root=pathlib.Path.cwd().resolve()
importlib.import_module('tests.starlink_oracle.bank_native_paired')
print(json.dumps(sorted({str(pathlib.Path(m.__file__).resolve().relative_to(root))
 for n,m in sys.modules.items() if n == 'tests' or n.startswith('tests.')})))
"""
    result = subprocess.run([sys.executable, "-c", program], cwd=ROOT, text=True,
                            capture_output=True, check=True, timeout=15)
    assert declared == set(json.loads(result.stdout))
    encoded = {"python_runtime__" + relative.replace("/", "__") for relative in declared}
    assert len(encoded) == len(declared) == 10
    assert {"tests/__init__.py", "tests/starlink_oracle/__init__.py"} <= declared

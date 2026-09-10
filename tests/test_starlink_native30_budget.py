"""Bounded real native30-only completion evidence, never an actual FFT run."""

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.native30_budget import budget

ROOT = Path(__file__).resolve().parents[1]
HDL = ROOT / "hdl/library"
COHORT = ROOT / "build/high-rate-offline-v5/cohort"
COHORT_SHA = "ba3046d56a6eb1cf2792070cf63f8d7ffb44958f0ef9f4999907b2b2a49bdb4d"
NATIVE_SOURCES = [
    *[f"starlink_pss_raw_correlator/{name}.v" for name in [
        "starlink_pss_async_fifo", "starlink_sat_add48", "starlink_pss_candidate_scheduler",
        "starlink_pss_capture_bridge", "starlink_pss_sliding_correlator", "starlink_pss_tracking_core",
        "starlink_pss_exact_reducer", "starlink_pss_exact_track_reducer", "starlink_pss_result_store",
        "starlink_pss_reduced_tracking_core",
    ]],
    "common/ad_mem.v", "common/up_axi.v", "axi_starlink_pss_tracker/axi_starlink_pss_tracker.v",
    "axi_starlink_pss_tracker/starlink_pss_injection_mux.v",
]


def prepare_native_files(directory):
    receipt_bytes = (COHORT / "cohort.json").read_bytes()
    assert hashlib.sha256(receipt_bytes).hexdigest() == COHORT_SHA
    receipt = json.loads(receipt_bytes)
    for name in ["source_ci16.mem", "native_coefficients_q15.mem", "native_capture_ci16.mem",
                 "native_expected_packet.mem", "native_all_raw_tuples.json"]:
        payload = (COHORT / name).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == receipt["files"][name]["sha256"]
        shutil.copyfile(COHORT / name, directory / name)
    rows = json.loads((directory / "native_all_raw_tuples.json").read_bytes())
    assert [row["lag"] for row in rows] == list(range(-64, 65))
    assert sum(row["qualified"] for row in rows) == 121
    for field, filename, bits, width in [
        ("lag", "lag", 8, 2), ("start_index", "index", 64, 16),
        ("real", "real", 48, 12), ("imag", "imag", 48, 12),
        ("Ex", "ex", 48, 12), ("Eh", "eh", 48, 12),
        ("power", "power", 96, 24), ("saturation", "saturation", 9, 3),
        ("qualified", "qualified", 1, 1),
    ]:
        # Serialization of existing independent rows only; no new arithmetic
        # or replacement of original51 files is performed here.
        (directory / f"native_raw_{filename}.mem").write_text("".join(
            f"{int(row[field]) & ((1 << bits) - 1):0{width}x}\n" for row in rows))
    return rows


def test_native30_predeclared_bound_arithmetic():
    result = budget()
    assert result["engine_derived_cycles"] == 22404
    assert result["margin_engine_tenths"] == 37400


@pytest.mark.parametrize("early", [0, 1])
def test_actual_native30_bound_and_post_capture_source_off(tmp_path, early):
    expected = prepare_native_files(tmp_path)
    (tmp_path / "budget-before-evaluation.json").write_text(json.dumps(budget(), sort_keys=True, indent=2))
    bench_dir = HDL / "starlink_pss_acquisition/tb"
    source_paths = [HDL / path for path in NATIVE_SOURCES] + [
        bench_dir / "tb_starlink_native30_budget.sv", bench_dir / "bank_native30_checks.svh",
        bench_dir / "high_rate_paired_axi.svh",
    ]
    frozen = tmp_path / "frozen_sources"
    frozen.mkdir()
    for source in source_paths:
        shutil.copyfile(source, frozen / source.name)
    (tmp_path / "sources-before.json").write_text(json.dumps({
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source_paths
    }, sort_keys=True, indent=2))
    fixture_names = [path.name for path in tmp_path.iterdir() if path.suffix in {".mem", ".json"}]
    before_fixtures = {name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() for name in fixture_names}
    (tmp_path / "fixture-before.json").write_text(json.dumps(before_fixtures, sort_keys=True, indent=2))
    compiled = subprocess.run([
        "iverilog", "-g2012", "-Wall", "-I", str(frozen), "-s", "tb_starlink_native30_budget",
        f"-Ptb_starlink_native30_budget.EARLY_OFF={early}", "-o", str(tmp_path / "native.vvp"),
        *[str(frozen / path.name) for path in source_paths if path.suffix in {".v", ".sv"}],
    ], capture_output=True, text=True, timeout=30, check=False)
    (tmp_path / "compile.log").write_text(compiled.stdout + compiled.stderr)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    result = subprocess.run(["vvp", str(tmp_path / "native.vvp")], cwd=tmp_path,
                            capture_output=True, text=True, timeout=30, check=False)
    (tmp_path / "simulation.log").write_text(result.stdout + result.stderr)
    source_after = {str(path.relative_to(ROOT)): hashlib.sha256((frozen / path.name).read_bytes()).hexdigest()
                    for path in source_paths}
    (tmp_path / "sources-after.json").write_text(json.dumps(source_after, sort_keys=True, indent=2))
    assert source_after == json.loads((tmp_path / "sources-before.json").read_text())
    after_fixtures = {name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() for name in fixture_names}
    (tmp_path / "fixture-after.json").write_text(json.dumps(after_fixtures, sort_keys=True, indent=2))
    assert after_fixtures == before_fixtures
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FAIL" not in result.stdout and "FATAL:" not in result.stdout
    assert result.stdout.count("NATIVE30_ONLY_PASS") == 1
    assert result.stdout.count("NATIVE30_BUDGET_PASS") == 1
    assert result.stdout.count("NATIVE30_SOURCE_OFF_PASS") == 1
    packet_rows = re.findall(r"^NATIVE30_PACKET_WORD pass=(\d+) word=(\d+) data=([0-9a-f]{8})$",
                             result.stdout, re.MULTILINE)
    packet = (COHORT / "native_expected_packet.mem").read_text().splitlines()
    assert packet_rows == [(str(p), str(n), packet[n]) for p in range(2) for n in range(26)]
    raw_rows = (tmp_path / "native30_actual_raw_tuples.txt").read_text().splitlines()
    assert len(raw_rows) == len(expected) == 129
    for actual, original in zip(raw_rows, expected, strict=True):
        words = actual.split()
        assert len(words) == 9
        assert int(words[0]) == original["lag"]
        for field, word, bits in zip(["start_index", "real", "imag", "Ex", "Eh", "power", "saturation"],
                                     words[1:8], [64, 48, 48, 48, 48, 96, 9], strict=True):
            assert int(word, 16) == original[field] & ((1 << bits) - 1)
        assert int(words[8]) == int(original["qualified"])

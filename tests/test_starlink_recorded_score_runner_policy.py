"""Recorded-score runner admission/verdict tests; actual Vivado replay is separate."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ACQ = ROOT / "hdl/library/starlink_pss_acquisition"
RUNNER = ACQ / "simulate_recorded_iq_to_score_shared.tcl"
BENCH = ACQ / "tb/tb_starlink_pss_recorded_iq_to_score_shared.sv"
GEOMETRY = {
    "samples_ci16": (1406, 8), "forward_q17": (1536, 9),
    "product_q17": (1536, 9), "inverse_q17": (1536, 9),
    "forward_exponents": (3, 2), "inverse_exponents": (3, 2), "scores_u8": (1341, 2),
}
FIRST = (1 << 33) + 417


def test_generic_origin_avoids_vivado_apostrophe_shell_quoting():
    source = RUNNER.read_text()
    assert 'set_property generic "FIRST_SAMPLE_INDEX=$first_index"' in source
    assert "FIRST_SAMPLE_INDEX=64'h" not in source
    assert '"{first:016x}"' in source
    assert "parameter [63:0] FIRST_SAMPLE_INDEX" in BENCH.read_text()


VERDICTS = [
    f"RECORDED_SCORE_ORIGIN first_canonical_index={FIRST:016x} sample_count=1406",
    "RECORDED_SCORE_FAULT_RECOVERY_PASS injected_checker_fault=1 explicit_recovery=1",
    "RECORDED_SCORE_FFT_RESET_PASS sticky_quarantine=1 explicit_recovery=1",
    ("RECORDED_SCORE_REPLAY_PASS samples=1406 blocks=3 forward=1536 product=1536 inverse=1536 "
     "scores=1341 exact_metadata=1 score_stalls=1 NO_PSS_DETECTION_OR_CAPACITY_CLAIM"),
    f"RECORDED_SCORE_COUNTS first_canonical_index={FIRST:016x} stalled_cycles=19 max_fifo=23",
]


def probe(arguments, version="2022.2"):
    script = f"proc version {{args}} {{return {{{version}}}}}\n"
    script += 'proc create_project {args} {error "ADMITTED"}\n'
    script += "set argv [list " + " ".join(f"{{{arg}}}" for arg in arguments) + "]\n"
    script += "set argc [llength $argv]\n"
    script += f"if {{[catch {{source {{{RUNNER}}}}} message]}} {{puts stderr $message; exit 2}}\n"
    return subprocess.run(["tclsh"], input=script, capture_output=True,
                          check=False, text=True, timeout=15)


@pytest.fixture
def vectors(tmp_path):
    directory = tmp_path / "vectors"
    directory.mkdir()
    document = {"schema": "starlink-recorded-score-fixture-v1",
                "source_kind": "conditioned-recorded-ci16", "input_rate_hz": 15000000,
                "first_canonical_index": FIRST, "vectors": {}}
    for name, (rows, width) in GEOMETRY.items():
        path = directory / f"{name}.mem"
        path.write_text(("0" * width + "\n") * rows)
        document["vectors"][name] = {"rows": rows, "hex_digits": width,
                                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (directory / "recorded_fixture.json").write_text(json.dumps(document))
    return directory


def rewrite_manifest(directory, edit):
    path = directory / "recorded_fixture.json"
    document = json.loads(path.read_text())
    edit(document)
    path.write_text(json.dumps(document))


@pytest.mark.parametrize("count", [0, 1, 3])
def test_wrong_arity_has_no_output(tmp_path, count):
    output = tmp_path / "out"
    result = probe([output, "missing_vectors", "extra"][:count])
    assert result.returncode == 2 and "expected NEW_OUTPUT" in result.stderr
    assert not output.exists()


def test_wrong_tool_has_no_output(tmp_path):
    output = tmp_path / "out"
    result = probe([output, "missing_vectors"], version="2023.1")
    assert result.returncode == 2 and "requires Vivado 2022.2" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("kind", ["file", "directory", "dangling_symlink"])
def test_existing_output_is_untouched(tmp_path, kind):
    output = tmp_path / "out"
    if kind == "directory":
        output.mkdir()
        retained = output / "retained"
        retained.write_text("untouched")
    elif kind == "file":
        output.write_text("untouched")
    else:
        output.symlink_to(tmp_path / "missing")
    result = probe([output, "missing_vectors"])
    assert result.returncode == 2 and "refusing to overwrite" in result.stderr
    if kind == "directory":
        assert retained.read_text() == "untouched"
    elif kind == "file":
        assert output.read_text() == "untouched"
    else:
        assert output.is_symlink()


@pytest.mark.parametrize("key,value", [
    ("schema", "synthetic"), ("source_kind", "planted-pss"), ("input_rate_hz", 25000000),
    ("input_rate_hz", True), ("first_canonical_index", True), ("first_canonical_index", -1),
    ("first_canonical_index", 1.0), ("first_canonical_index", 1 << 64),
    ("first_canonical_index", (1 << 64) - 1405), ("unknown", 1),
])
def test_bad_manifest_fields_fail_before_output(tmp_path, vectors, key, value):
    rewrite_manifest(vectors, lambda document: document.__setitem__(key, value))
    output = tmp_path / "out"
    result = probe([output, vectors])
    assert result.returncode == 2 and "ADMITTED" not in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("kind", ["missing", "malformed", "oversize", "duplicate"])
def test_bad_manifest_file_fail_before_output(tmp_path, vectors, kind):
    path = vectors / "recorded_fixture.json"
    if kind == "missing":
        path.unlink()
    elif kind == "malformed":
        path.write_text("{invalid}")
    elif kind == "oversize":
        path.write_text(" " * 16385)
    else:
        path.write_text(path.read_text().replace('"first_canonical_index":',
                                               '"first_canonical_index": 0, "first_canonical_index":'))
    output = tmp_path / "out"
    result = probe([output, vectors])
    assert result.returncode == 2 and "ADMITTED" not in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("name", GEOMETRY)
@pytest.mark.parametrize("kind", ["missing", "wrong_hash", "short", "nonhex"])
def test_bad_vectors_fail_before_output(tmp_path, vectors, name, kind):
    path = vectors / f"{name}.mem"
    if kind == "missing":
        path.unlink()
    elif kind == "wrong_hash":
        path.write_text(path.read_text().replace("0", "1", 1))
    else:
        data = path.read_text()
        path.write_text(data.rsplit("\n", 2)[0] + "\n" if kind == "short"
                        else data.replace("0", "g", 1))
        rewrite_manifest(vectors, lambda document: document["vectors"][name].__setitem__(
            "sha256", hashlib.sha256(path.read_bytes()).hexdigest()))
    output = tmp_path / "out"
    result = probe([output, vectors])
    assert result.returncode == 2 and "recorded vector" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("name", ["forward_exponents", "inverse_exponents"])
def test_five_bit_exponents_cannot_be_silently_truncated(tmp_path, vectors, name):
    path = vectors / f"{name}.mem"
    path.write_text("20\n00\n00\n")
    rewrite_manifest(vectors, lambda document: document["vectors"][name].__setitem__(
        "sha256", hashlib.sha256(path.read_bytes()).hexdigest()))
    output = tmp_path / "out"
    result = probe([output, vectors])
    assert result.returncode == 2 and "five-bit" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("key,value", [("rows", True), ("rows", 1405), ("hex_digits", 9),
                                      ("sha256", "g" * 64), ("sha256", 0), ("extra", 1)])
def test_invalid_vector_receipts_are_rejected_before_output(tmp_path, vectors, key, value):
    rewrite_manifest(vectors, lambda document: document["vectors"]["samples_ci16"].__setitem__(key, value))
    output = tmp_path / "out"
    result = probe([output, vectors])
    assert result.returncode == 2 and "ADMITTED" not in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("first", [0, FIRST, (1 << 64) - 1406])
def test_full_fixture_origin_and_runtime_frozen_before_project(tmp_path, vectors, first):
    rewrite_manifest(vectors, lambda document: document.__setitem__("first_canonical_index", first))
    output = tmp_path / "out"
    result = probe([output, vectors])
    assert result.returncode == 2 and "ADMITTED" in result.stderr, result.stderr
    frozen = output / "frozen_sources"
    for path in [RUNNER, BENCH, Path(__file__), *vectors.iterdir(),
                 ACQ / "starlink_pss_realtime_result_guard.v",
                 ACQ / "create_shared_realtime_xfft_ip.tcl"]:
        assert (frozen / path.name).read_bytes() == path.read_bytes()
    assert f"first_canonical_index={first} first_canonical_index_hex={first:016x}" in (
        output / "scope.txt").read_text()


def verify_log(path, first=FIRST):
    script = f"set argc 0\ncatch {{source {{{RUNNER}}}}}\n"
    script += f"source {{{ACQ / 'verify_realtime_probe_result.tcl'}}}\n"
    script += f"if {{[catch {{pss_verify_recorded_output {{{path}}} {first:016x}}} message]}} "
    script += "{puts stderr $message; exit 2}\n"
    return subprocess.run(["tclsh"], input=script, text=True, capture_output=True,
                          check=False, timeout=10)


@pytest.mark.parametrize("failure", [None, "missing_origin", "wrong_origin", "missing_count", "duplicate",
                                     "missing_verdict", "fatal", "fail"])
def test_terminal_verifier_requires_exact_origin_verdict_and_no_failure(tmp_path, failure):
    lines = list(VERDICTS)
    if failure == "missing_origin":
        lines.pop(0)
    elif failure == "wrong_origin":
        lines[0] = lines[0].replace(f"{FIRST:016x}", "00000000000f4240")
    elif failure == "missing_count":
        lines.pop()
    elif failure == "duplicate":
        lines.append(lines[-1])
    elif failure == "missing_verdict":
        lines.pop(3)
    elif failure == "fatal":
        lines.append("Fatal: injected checker regression")
    elif failure == "fail":
        lines.append("RECORDED_SCORE_FAIL numeric mismatch")
    path = tmp_path / "simulate.log"
    path.write_text("\n".join(lines) + "\n")
    result = verify_log(path)
    assert result.returncode == (0 if failure is None else 2), result.stdout + result.stderr


def test_source_policy_preserves_actual_core_clocks_and_no_planted_detection():
    source, bench = RUNNER.read_text(), BENCH.read_text()
    assert "pss_create_shared_realtime_xfft_ip $wrapper_path" in source
    assert "source [file join $source_dir create_shared_realtime_xfft_ip.tcl]" in source
    assert "FIRST_SAMPLE_INDEX=$first_index" in source
    assert ".USE_REALTIME_XFFT(1)" in bench and "#2.5 fft_clk" in bench and "#5 clk" in bench
    for forbidden in ("expected_scores[100]", "pss255", "64'd1000000", "full-scale PSS controls"):
        assert forbidden not in bench
    assert "expected_zero[score_count]" in bench
    assert "stalled_cycles == 0" in bench and "!score_valid ||" in bench
    for forbidden in ("launch_runs", "set_false_path", "set_max_delay", "set_clock_groups"):
        assert forbidden not in source
    helper = (ACQ / "create_shared_realtime_xfft_ip.tcl").read_text()
    assert "C_THROTTLE_SCHEME 0" in helper and "C_INPUT_WIDTH 18" in helper
    assert "C_ARCH 1" in helper and "C_HAS_BFP 1" in helper and "C_NFFT_MAX 9" in helper

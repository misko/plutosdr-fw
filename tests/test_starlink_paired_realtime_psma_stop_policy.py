"""Paired-shell runner admission and independent pilot fixtures, no radio I/O.

The CLI only generates new, bounded test vectors. It never changes old score
goldens. The pilot oracle is independent integer filtering, not captured RTL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from tests.starlink_oracle.pilot_ddc import PilotDdcOracle

ROOT = Path(__file__).resolve().parents[1]
ACQ = ROOT / "hdl/library/starlink_pss_acquisition"
RUNNER = ACQ / "simulate_paired_realtime_psma_stop.tcl"
BENCH = ACQ / "tb/tb_starlink_pss_paired_realtime_psma_stop.sv"
FIRST = (1 << 33) - 16
PREROLL = 768
SOURCE_COUNT = 4096
PILOT_COUNT = 512
GEOMETRY = {
    "samples_ci16": (1406, 8), "forward_q17": (1536, 9),
    "product_q17": (1536, 9), "inverse_q17": (1536, 9),
    "forward_exponents": (3, 2), "inverse_exponents": (3, 2),
    "scores_u8": (1341, 2),
}
PILOT_GEOMETRY = {
    "paired_source_ci16": (SOURCE_COUNT, 8),
    "paired_pilot_ci16": (PILOT_COUNT, 8),
    "paired_pilot_newest": (PILOT_COUNT, 16),
    "paired_metadata": (10, 16),
}


def _words(path: Path, rows: int, width: int) -> list[int]:
    text = path.read_text().splitlines()
    if len(text) != rows or any(len(row) != width or any(
            char not in "0123456789abcdefABCDEF" for char in row) for row in text):
        raise ValueError(f"invalid frozen vector geometry: {path.name}")
    return [int(row, 16) for row in text]


def generate_pilot_vectors(score_vectors: Path, output: Path, *, geometry: str = "447x2") -> dict:
    """Keep the seven score inputs immutable; add prehistory and a known tail."""
    if geometry not in ("447x2", "343x2"):
        raise ValueError("geometry must be literal447x2 or343x2")
    map_bins = 343 if geometry == "343x2" else 447
    if output.exists() or output.is_symlink():
        raise ValueError("refusing to overwrite pilot evidence")
    original = {name: _words(score_vectors / f"{name}.mem", rows, width)
                for name, (rows, width) in GEOMETRY.items()}
    packed = np.asarray(original["samples_ci16"], dtype=np.uint32)
    numeric = np.column_stack((packed & 65535, packed >> 16)).astype(np.uint16).view(np.int16)
    source = np.empty((SOURCE_COUNT, 2), dtype=np.int16)
    source[:PREROLL] = (37, -19)
    source[PREROLL:PREROLL + len(numeric)] = numeric
    tail = np.arange(SOURCE_COUNT - PREROLL - len(numeric))
    source[PREROLL + len(numeric):] = np.column_stack((tail * 19 % 97 - 48,
                                                     tail * 13 % 89 - 44))
    oracle = PilotDdcOracle("upper").process(source, first_index=FIRST - PREROLL)
    if oracle.saturation_events:
        raise ValueError("paired pilot fixture saturates; do not relabel it healthy")
    indexes = oracle.accepted_input_indexes[oracle.support_valid][:PILOT_COUNT]
    pilot = oracle.samples_iq[oracle.support_valid][:PILOT_COUNT]
    if len(pilot) != PILOT_COUNT:
        raise ValueError("insufficient fully supported pilot samples")
    unsupported = int((~oracle.support_valid).sum())
    metadata = [FIRST, FIRST - PREROLL, int(indexes[0]), int(indexes[-1]),
                unsupported, unsupported + PILOT_COUNT,
                int(indexes[0]) - 269, int(indexes[-1]) - 269,
                int(indexes[0]) - 538, int(indexes[-1]) + 1]
    # Exact two-block BFP processing support, not merely66-tap ideal support.
    if not metadata[6] <= FIRST < FIRST + 959 <= metadata[7] + 1:
        raise ValueError("pilot center lattice does not enclose the selected map envelope")
    output.mkdir()
    for name, values in (("paired_source_ci16", source), ("paired_pilot_ci16", pilot)):
        words = [(int(i) & 65535) | ((int(q) & 65535) << 16) for i, q in values]
        (output / f"{name}.mem").write_text("".join(f"{word:08x}\n" for word in words))
    (output / "paired_pilot_newest.mem").write_text("".join(f"{int(i):016x}\n" for i in indexes))
    (output / "paired_metadata.mem").write_text("".join(f"{i:016x}\n" for i in metadata))
    (output / "paired_pilot_expected.ci16").write_bytes(pilot.astype("<i2").tobytes())
    manifest = {
        "schema": "paired-realtime-psma-stop-pilot-oracle-v1",
        "digital_boundary": "signed16 CI16 acquisition-shell input, NOT physical AD9361 format",
        "source_count": SOURCE_COUNT, "preroll": PREROLL, "pilot_count": PILOT_COUNT,
        "first_map_index": FIRST, "pilot_first_input_index": FIRST - PREROLL,
        "selected_map_geometry": geometry,
        "map_candidate_interval": [FIRST, FIRST + 2 * map_bins],
        "selected_score_prefix": 2 * map_bins,
        "selected_tile_end_residue": 2 * map_bins % 447,
        "map_full_fft_inputs": [FIRST, FIRST + 959],
        "pilot_center_bounds": [metadata[6], metadata[7] + 1],
        "pilot_raw_input_support": [metadata[8], metadata[9]],
        "saturation_events": 0,
        "source_rate_hz": 15_000_000, "pilot_rate_hz": 2_500_000,
        "production_geometry_or_duration_qualified": False,
        "score_vector_sha256": {name: hashlib.sha256(
            (score_vectors / f"{name}.mem").read_bytes()).hexdigest() for name in GEOMETRY},
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "integer_oracle_sha256": hashlib.sha256(
            (ROOT / "tests/starlink_oracle/pilot_ddc.py").read_bytes()).hexdigest(),
        "generated_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in sorted(output.iterdir())},
    }
    (output / "paired_oracle.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def probe(arguments, version="2022.2"):
    script = f"proc version {{args}} {{return {{{version}}}}}\n"
    script += 'proc create_project {args} {error "ADMITTED"}\n'
    script += "set argv [list " + " ".join(f"{{{arg}}}" for arg in arguments) + "]\n"
    script += "set argc [llength $argv]\n"
    script += f"if {{[catch {{source {{{RUNNER}}}}} message]}} {{puts stderr $message; exit 2}}\n"
    return subprocess.run(["tclsh"], input=script, capture_output=True,
                          check=False, text=True, timeout=10)


@pytest.fixture
def vectors(tmp_path):
    scores, pilot = tmp_path / "scores", tmp_path / "pilot"
    scores.mkdir()
    for name, (rows, width) in GEOMETRY.items():
        (scores / f"{name}.mem").write_text(("0" * width + "\n") * rows)
    generate_pilot_vectors(scores, pilot)
    return scores, pilot


def test_independent_generator_preserves_scores_and_reproduces_bytes(vectors, tmp_path):
    scores, pilot = vectors
    second = tmp_path / "second"
    before = {path.name: path.read_bytes() for path in scores.iterdir()}
    manifest = generate_pilot_vectors(scores, second)
    assert before == {path.name: path.read_bytes() for path in scores.iterdir()}
    for path in pilot.iterdir():
        assert path.read_bytes() == (second / path.name).read_bytes()
    assert manifest["map_full_fft_inputs"] == [FIRST, FIRST + 959]
    assert manifest["pilot_raw_input_support"][0] <= FIRST
    assert manifest["pilot_center_bounds"][1] > FIRST + 959
    assert (pilot / "paired_pilot_expected.ci16").stat().st_size == 2048


def test_generator_does_not_overwrite(vectors):
    scores, pilot = vectors
    with pytest.raises(ValueError, match="overwrite"):
        generate_pilot_vectors(scores, pilot)


@pytest.mark.parametrize("count", [0, 1, 2, 5])
def test_wrong_arity_has_no_side_effect(tmp_path, count):
    output = tmp_path / "out"
    result = probe([output, tmp_path / "scores", tmp_path / "pilot", "extra", "extra"][:count])
    assert result.returncode == 2 and "expected NEW_OUTPUT" in result.stderr
    assert not output.exists()


def test_wrong_tool_has_no_side_effect(tmp_path):
    output = tmp_path / "out"
    result = probe([output, "scores", "pilot"], "2023.1")
    assert result.returncode == 2 and "requires Vivado 2022.2" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("kind", ["file", "directory", "symlink"])
def test_existing_output_is_untouched(tmp_path, kind):
    output = tmp_path / "out"
    if kind == "file":
        retained = output
    else:
        destination = tmp_path / "destination" if kind == "symlink" else output
        destination.mkdir()
        retained = destination / "retained"
        if kind == "symlink":
            output.symlink_to(destination, target_is_directory=True)
    retained.write_text("untouched")
    result = probe([output, "scores", "pilot"])
    assert result.returncode == 2 and "refusing to overwrite" in result.stderr
    assert retained.read_text() == "untouched"


@pytest.mark.parametrize("name", [*GEOMETRY, *PILOT_GEOMETRY])
@pytest.mark.parametrize("bad", ["missing", "short", "nonhex"])
def test_bad_vectors_fail_before_allocation(tmp_path, vectors, name, bad):
    scores, pilot = vectors
    path = (scores if name in GEOMETRY else pilot) / f"{name}.mem"
    if bad == "missing":
        path.unlink()
    elif bad == "short":
        path.write_text("\n".join(path.read_text().splitlines()[:-1]) + "\n")
    else:
        path.write_text(path.read_text().replace("0", "g", 1))
    output = tmp_path / "out"
    result = probe([output, scores, pilot])
    assert result.returncode == 2 and "vector" in result.stderr
    assert not output.exists()


def test_full_sources_frozen_before_project_creation(tmp_path, vectors):
    scores, pilot = vectors
    output = tmp_path / "out"
    result = probe([output, scores, pilot])
    assert result.returncode == 2 and "ADMITTED" in result.stderr
    frozen = output / "frozen_sources"
    for path in (RUNNER, BENCH, Path(__file__), ROOT / "tests/starlink_oracle/pilot_ddc.py",
                 ACQ / "starlink_pss_realtime_result_guard.v",
                 ACQ.parent / "axi_starlink_pss_acquisition/axi_starlink_pss_acquisition.v",
                 ACQ.parent / "axi_starlink_pilot_capture/axi_starlink_pilot_capture.v"):
        assert (frozen / path.name).read_bytes() == path.read_bytes()
    assert (frozen / "paired_pilot_expected.ci16").read_bytes() == (
        pilot / "paired_pilot_expected.ci16").read_bytes()


@pytest.mark.parametrize("name,row", [("paired_source_ci16", 768),
                                     ("paired_metadata", 6),
                                     ("paired_pilot_newest", 511)])
def test_valid_hex_cannot_change_common_source_or_coordinate_contract(tmp_path, vectors, name, row):
    scores, pilot = vectors
    path = pilot / f"{name}.mem"
    rows = path.read_text().splitlines()
    rows[row] = f"{int(rows[row], 16) + 1:0{len(rows[row])}x}"
    path.write_text("\n".join(rows) + "\n")
    output = tmp_path / "out"
    result = probe([output, scores, pilot])
    assert result.returncode == 2 and "vector" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("name", ["paired_pilot_expected.ci16", "paired_oracle.json"])
def test_missing_binary_or_receipt_cannot_allocate_evidence(tmp_path, vectors, name):
    scores, pilot = vectors
    (pilot / name).unlink()
    output = tmp_path / "out"
    result = probe([output, scores, pilot])
    assert result.returncode == 2 and "oracle vector receipt" in result.stderr
    assert not output.exists()


def test_runner_does_not_weaken_runtime_or_physical_gates():
    source = RUNNER.read_text()
    assert "pss_create_shared_realtime_xfft_ip" in source
    assert "require_realtime_probe_pass" in source
    assert "PAIRED_PILOT_WORD 512" in source
    assert "$actual_pilot_bytes ne $expected_pilot_bytes" in source
    for forbidden in ("launch_runs", "create_clock", "set_false_path", "set_max_delay"):
        assert forbidden not in source
    bench = BENCH.read_text()
    assert "parameter integer MAP_BINS = 447" in bench
    assert "defparam dut.acquisition.PHASE_BINS = MAP_BINS" in bench
    assert "defparam dut.phase_map_control.PHASE_BINS = MAP_BINS" in bench
    assert ('set_property generic "MAP_BINS=$map_bins '
            'USE_BANK_OWNED_XFFT=$use_bank_owned_xfft FAST_MHZ=$fast_mhz"') in source
    assert "NO_ADC_DMA_IIO_FINE_PRODUCTION_OR_PHYSICAL_CLAIM" in bench
    assert "defparam dut.acquisition.USE_BANK_OWNED_XFFT = USE_BANK_OWNED_XFFT" in bench
    assert "parameter integer USE_BANK_OWNED_XFFT = 0" in bench


@pytest.mark.parametrize("map_bins", [447, 343])
@pytest.mark.parametrize("bank_owned,fast_mhz", [(0, 200), (1, 175), (1, 200)])
@pytest.mark.parametrize("failure", [None, "PAIRED_REALTIME_PSMA_STOP_FAIL mismatch",
                                    "  paired_realtime_psma_stop_fail mismatch"])
def test_verifier_accepts_negative_case_pass_marker_but_rejects_actual_failure(
        tmp_path, failure, map_bins, bank_owned, fast_mhz):
    result = _verify_receipt(tmp_path, map_bins, bank_owned, fast_mhz, failure=failure)
    if failure:
        assert result.returncode == 2 and "contains FAIL evidence" in result.stderr
    else:
        assert result.returncode == 0, result.stdout + result.stderr


def _verify_receipt(tmp_path, map_bins, bank_owned, fast_mhz, *, failure=None, mutation=None):
    markers = [
        ("PAIRED_PREROLL_PASS real_shell=1 real_cdc=1 real_canonical=1 samples=768 "
         "empty_ticket=1 explicit_configuration_pause=1"),
        (f"PAIRED_MAP_PILOT_PASS exact_scores={map_bins * 2} exact_map_words={map_bins} exact_pilot_words=512 "
         "exact_bytes=2048 shared_support_envelope=959 pilot_after_stop=1 healthy_snapshot=1"),
        ("PAIRED_LATE_FAULT_PASS actual_invalid_release=1 failed_joint_health=1 "
         "terminal_coordinates_retained=1 pilot_bytes_preserved=1"),
        (f"PAIRED_REALTIME_PSMA_STOP_PASS source_words=4096 pilot_words=512 map_words={map_bins} "
         "NO_ADC_DMA_IIO_FINE_PRODUCTION_OR_PHYSICAL_CLAIM"),
    ]
    log = markers + [f"PAIRED_PILOT_WORD ordinal={n}" for n in range(512)]
    if map_bins == 343:
        log += ["PAIRED_STOP_TAIL map_bins=343",
                ("PAIRED_RESIDUE_PASS selected_scores=686 map_words=343 residue=239 "
                 "post_fence_tail_not_map_admission=1")]
    if bank_owned and mutation != "missing_bank":
        receipt_clock = 200 if mutation == "wrong_clock" and fast_mhz == 175 else fast_mhz
        if mutation == "wrong_clock" and fast_mhz == 200:
            receipt_clock = 175
        bank_marker = (f"PAIRED_BANK_PASS map_bins={map_bins} selected_scores={map_bins * 2} "
                       f"exact_pilot_bytes=2048 fast_mhz={receipt_clock} "
                       "TEST_ONLY_SELECTOR_NOT_RECEIVER")
        log += [bank_marker] * (2 if mutation == "duplicate_bank" else 1)
    if failure:
        log.insert(0, failure)
    (tmp_path / "simulate.log").write_text("\n".join(log) + "\n")
    binary = tmp_path / "paired_pilot_actual.ci16"
    binary.write_bytes(bytes(2047) + bytes([1 if mutation == "pilot_byte" else 0]))
    expected = tmp_path / "independent_expected.ci16"
    expected.write_bytes(bytes(2048))
    procedure = RUNNER.read_text().split("# Actual digital CI16 shell/CDC", 1)[0]
    script = f"source {{{ACQ / 'verify_realtime_probe_result.tcl'}}}\n" + procedure
    script += (f"pss_verify_paired_outputs {{{tmp_path}}} {{{expected}}} "
               f"{map_bins} {bank_owned} {fast_mhz}\n")
    # Tcl stdin does not fail its process merely because a top-level command
    # errors; wrap the actual verifier to make the subprocess result meaningful.
    script = "if {[catch {\n" + script + "} reason]} {puts stderr $reason; exit 2}\n"
    return subprocess.run(["tclsh"], input=script, capture_output=True,
                          check=False, text=True, timeout=10)


@pytest.mark.parametrize("map_bins", [447, 343])
@pytest.mark.parametrize("fast_mhz", [175, 200])
@pytest.mark.parametrize("mutation", ["missing_bank", "wrong_clock", "duplicate_bank", "pilot_byte"])
def test_bank_verifier_requires_exact_receipt_and_independent_bytes(tmp_path, map_bins, fast_mhz, mutation):
    result = _verify_receipt(tmp_path, map_bins, 1, fast_mhz, mutation=mutation)
    assert result.returncode == 2, result.stdout + result.stderr
    if mutation == "pilot_byte":
        assert "bytes differ from independent oracle" in result.stderr


@pytest.mark.parametrize("bank_owned,fast_mhz", [(0, 175), (2, 200), (1, 180), ("auto", 175)])
def test_verifier_rejects_unsupported_engine_clock(tmp_path, bank_owned, fast_mhz):
    result = _verify_receipt(tmp_path, 447, bank_owned, fast_mhz)
    assert result.returncode == 2 and "invalid paired verifier engine/clock" in result.stderr


@pytest.mark.parametrize("selector,clock", [("0", "200"), ("01", "175"), ("auto", "175"),
                                          ("1", "180"), ("1", "175.0"), ("1", "")])
def test_invalid_bank_selector_fails_before_sources_or_output(tmp_path, selector, clock):
    output = tmp_path / "out"
    result = probe([output, "missing_scores", "missing_pilot", "447x2", selector, clock])
    assert result.returncode == 2 and "paired bank probe requires" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("geometry", ["447x2", "343x2"])
@pytest.mark.parametrize("fast_mhz", [175, 200])
def test_bank_probe_freezes_both_engines_and_explicit_scope(tmp_path, vectors, geometry, fast_mhz):
    scores, pilot = vectors
    if geometry == "343x2":
        pilot = tmp_path / "residue"
        generate_pilot_vectors(scores, pilot, geometry=geometry)
    output = tmp_path / "out"
    result = probe([output, scores, pilot, geometry, "1", fast_mhz])
    assert result.returncode == 2 and "ADMITTED" in result.stderr
    for name in ("starlink_pss_iq_to_score_bank_owned.v", "starlink_pss_fft_bank_owned_slice.v",
                 "starlink_pss_iq_to_score_shared.v"):
        assert (output / "frozen_sources" / name).read_bytes() == (ACQ / name).read_bytes()
    scope = (output / "scope.txt").read_text()
    assert f"fast_clock_MHz={fast_mhz}" in scope
    assert "use_bank_owned_xfft=1" in scope
    assert "bank_selector_is_test_only_child_defparam_not_AXI_receiver_profile=true" in scope


@pytest.mark.parametrize("geometry", ["", "343", "343X2", "343x3", "447x64", "343x2 ", "auto"])
def test_invalid_selector_fails_before_sources_or_output(tmp_path, geometry):
    output = tmp_path / "out"
    result = probe([output, "missing_scores", "missing_pilot", geometry])
    assert result.returncode == 2 and "paired geometry" in result.stderr
    assert not output.exists()
    with pytest.raises(ValueError, match="geometry"):
        generate_pilot_vectors(tmp_path / "missing", output, geometry=geometry)
    assert not output.exists()


@pytest.mark.parametrize("geometry", [None, "447x2", "343x2"])
def test_selected_geometry_is_frozen_before_project(tmp_path, vectors, geometry):
    scores, pilot = vectors
    if geometry == "343x2":
        pilot = tmp_path / "residue"
        generate_pilot_vectors(scores, pilot, geometry=geometry)
    output = tmp_path / "out"
    arguments = [output, scores, pilot] + ([] if geometry is None else [geometry])
    result = probe(arguments)
    assert result.returncode == 2 and "ADMITTED" in result.stderr
    bins = 343 if geometry == "343x2" else 447
    scope = (output / "scope.txt").read_text()
    assert f"test_only_geometry={bins}x2 " in scope
    assert f"selected_score_prefix={bins * 2} fft_stride=447 tile_end_residue={bins * 2 % 447}" in scope
    assert (output / "frozen_sources" / BENCH.name).read_bytes() == BENCH.read_bytes()


def test_residue_rejects_default_oracle_receipt(tmp_path, vectors):
    scores, pilot = vectors
    output = tmp_path / "out"
    result = probe([output, scores, pilot, "343x2"])
    assert result.returncode == 2 and "receipt geometry" in result.stderr
    assert not output.exists()


def test_residue_oracle_preserves_actual_source_pilot_and_score_bytes(tmp_path, vectors):
    scores, default = vectors
    residue = tmp_path / "residue"
    manifest = generate_pilot_vectors(scores, residue, geometry="343x2")
    assert manifest["selected_map_geometry"] == "343x2"
    assert manifest["map_candidate_interval"] == [FIRST, FIRST + 686]
    assert manifest["selected_tile_end_residue"] == 1_280_000 % 447 == 239
    assert manifest["map_full_fft_inputs"] == [FIRST, FIRST + 959]
    for name in [*(f"{name}.mem" for name in PILOT_GEOMETRY), "paired_pilot_expected.ci16"]:
        assert (residue / name).read_bytes() == (default / name).read_bytes()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--score-vectors", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--geometry", choices=("447x2", "343x2"), default="447x2")
    args = parser.parse_args()
    print(json.dumps(generate_pilot_vectors(args.score_vectors, args.output,
                                          geometry=args.geometry), sort_keys=True))

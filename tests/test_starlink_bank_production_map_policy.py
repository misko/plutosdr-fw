"""Bounded oracle/admission/terminal policy checks, not actual-IP substitutes."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from tools import generate_starlink_periodic_map_vectors as oracle

ROOT = Path(__file__).resolve().parents[1]
ACQ = ROOT / "hdl/library/starlink_pss_acquisition"
RUNNER = ACQ / "simulate_bank_production_map.tcl"
BENCH = ACQ / "tb/tb_starlink_pss_bank_production_map.sv"
GEOMETRY = {
    "period_ci16": (447, 8),
    "forward_q17": (512, 9),
    "product_q17": (512, 9),
    "inverse_q17": (512, 9),
    "forward_exponents": (1, 2),
    "inverse_exponents": (1, 2),
    "scores_u8": (447, 2),
    "energies_u38": (447, 10),
    "numerators_u69": (447, 18),
    "denominators_u69": (447, 18),
    "saturated_u1": (447, 1),
    "power_shift_u7": (1, 2),
    "map_smoke_u16": (343, 4),
    "map_production_u16": (20000, 4),
}


def probe(arguments, version="2022.2"):
    script = f"proc version {{args}} {{return {{{version}}}}}\n"
    script += (
        'proc set_param {args} {}\nproc create_project {args} {error "ADMITTED"}\n'
    )
    script += "set argv [list " + " ".join(f"{{{arg}}}" for arg in arguments) + "]\n"
    script += "set argc [llength $argv]\n"
    script += f"if {{[catch {{source {{{RUNNER}}}}} message]}} {{puts stderr $message; exit 2}}\n"
    return subprocess.run(
        ["tclsh"], input=script, capture_output=True, text=True, check=False, timeout=15
    )


def fake_vectors(path):
    """Self-consistent zeros exercise runner admission only, never numeric truth."""
    path.mkdir()
    files = {}
    for name, (rows, width) in GEOMETRY.items():
        target = path / f"{name}.mem"
        target.write_text(("0" * width + "\n") * rows)
        files[target.name] = {
            "rows": rows,
            "hex_width": width,
            "sha256": oracle.digest(target),
        }
    receipt = {
        "schema": oracle.SCHEMA,
        "kernel_byte_match": True,
        "bootstrap": {
            "original_blocks": 3,
            "forward_product_inverse_words_each": 1536,
            "scores": 1341,
        },
        "production": oracle.support(20000, 64),
        "files": files,
        "inputs": {
            str(p): oracle.digest(p) for p in [oracle.KERNEL, Path(oracle.__file__)]
        },
    }
    (path / "periodic_vectors.json").write_text(json.dumps(receipt))


@pytest.mark.parametrize(
    "n,den,expected",
    [
        (1, 2, 0),
        (3, 2, 2),
        (5, 2, 2),
        (-1, 2, 0),
        (-3, 2, -2),
        (-5, 2, -2),
        (7, 4, 2),
        (-7, 4, -2),
        (131071 * 131071, 1 << 18, 65535),
    ],
)
def test_signed_product_rounding(n, den, expected):
    assert oracle.round_even(n, den) == expected


@pytest.mark.parametrize(
    "num,den,expected",
    [
        (0, 0, 0),
        (1, 0, 0),
        (0, 100, 0),
        (1, 1, 255),
        (1000, 1, 255),
        (1, 2, 128),
        (1, 510, 0),
        (3, 510, 2),
        ((1 << 69) - 1, (1 << 69) - 1, 255),
    ],
)
def test_ratio_edges_and_ties(num, den, expected):
    assert oracle.normalize(num, den) == expected


@pytest.mark.parametrize(
    "power,shift,expected,saturated",
    [
        (0, 127, 0, 0),
        (1, 68, 1 << 68, 0),
        (1, 69, (1 << 69) - 1, 1),
        (1, 70, (1 << 69) - 1, 1),
        ((1 << 36) - 1, 33, ((1 << 36) - 1) << 33, 0),
        ((1 << 36) - 1, 34, (1 << 69) - 1, 1),
        (1, 127, (1 << 69) - 1, 1),
    ],
)
def test_69bit_saturation_shift_boundary(power, shift, expected, saturated):
    assert oracle.saturating_numerator(power, shift) == (expected, saturated)


@pytest.mark.parametrize("power,shift", [(-1, 0), (1 << 36, 0), (1, -1), (1, 128)])
def test_rejects_unrepresentable_power_shift(power, shift):
    with pytest.raises(ValueError):
        oracle.saturating_numerator(power, shift)


@pytest.mark.parametrize("bins,frames", [(343, 2), (20000, 64)])
def test_compact_map_matches_independent_sequential_accumulation(bins, frames):
    scores = [(p * 17 + p * p) % 256 for p in range(447)]
    sequential = [0] * bins
    for index in range(bins * frames):
        sequential[index % bins] += scores[index % 447]
    assert oracle.map_words(scores, bins, frames) == sequential
    contract = oracle.support(bins, frames)
    assert contract["last_block_selected"] == 239
    assert contract["potential_tail_scores"] == 208
    assert (
        contract["fft_source_samples"] - contract["direct_tap_support_samples"] == 208
    )
    assert max(sequential) <= 64 * 255


def test_full_frozen_support():
    assert oracle.support(20000, 64) == {
        "selected_scores": 1280000,
        "blocks": 2864,
        "full_block_scores": 1280208,
        "fft_source_samples": 1280273,
        "direct_tap_support_samples": 1280065,
        "potential_tail_scores": 208,
        "last_block_selected": 239,
    }


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["output"],
        ["output", "vector"],
        ["output", "vector", "Smoke"],
        ["output", "vector", "smoke", "extra"],
        ["output", "vector", "production", "extra", "extra"],
    ],
)
def test_wrong_admission_arguments(args):
    result = probe(args)
    assert result.returncode == 2 and (
        "expected NEW_OUTPUT" in result.stderr or "literal smoke" in result.stderr
    )


def test_wrong_version_and_existing_output_are_nonmutating(tmp_path):
    output = tmp_path / "retained"
    output.write_text("retained")
    assert (
        "requires Vivado 2022.2" in probe([output, "unused", "smoke"], "2023.1").stderr
    )
    assert "refusing to overwrite" in probe([output, "unused", "smoke"]).stderr
    assert output.read_text() == "retained"


@pytest.mark.parametrize("name", GEOMETRY)
@pytest.mark.parametrize("bad", ["missing", "short", "long", "nonhex", "width"])
def test_bad_vector_is_rejected_before_allocation(tmp_path, name, bad):
    vectors, output = tmp_path / "vectors", tmp_path / "new output"
    fake_vectors(vectors)
    target = vectors / f"{name}.mem"
    rows, width = GEOMETRY[name]
    if bad == "missing":
        target.unlink()
    else:
        data = ["0" * width] * rows
        if bad == "short":
            data.pop()
        elif bad == "long":
            data.append(data[-1])
        elif bad == "nonhex":
            data[0] = "g" * width
        else:
            data[0] += "0"
        target.write_text("\n".join(data) + "\n")
    result = probe([output, vectors, "smoke"])
    assert result.returncode == 2 and "vector" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    "name,bad",
    [
        ("saturated_u1", "2"),
        ("forward_exponents", "20"),
        ("power_shift_u7", "80"),
        ("energies_u38", "4000000000"),
        ("numerators_u69", "200000000000000000"),
    ],
)
def test_storage_range_admission(tmp_path, name, bad):
    vectors, output = tmp_path / "vectors", tmp_path / "new output"
    fake_vectors(vectors)
    target = vectors / f"{name}.mem"
    rows = target.read_text().splitlines()
    rows[0] = bad
    target.write_text("\n".join(rows) + "\n")
    result = probe([output, vectors, "smoke"])
    assert "out-of-range" in result.stderr and not output.exists()


def test_receipt_hash_mismatch_and_review_gate(tmp_path):
    vectors, output = tmp_path / "vectors", tmp_path / "new output"
    fake_vectors(vectors)
    result = probe([output, vectors, "production"])
    assert (
        "production requires REVIEWED_SOURCE_SHA256=" in result.stderr
        and not output.exists()
    )
    (vectors / "scores_u8.mem").write_text("01\n" * 447)
    result = probe([output, vectors, "smoke"])
    assert "vector hash mismatch" in result.stderr and not output.exists()


def test_smoke_snapshots_inputs_before_compilation(tmp_path):
    vectors, output = tmp_path / "vectors", tmp_path / "new output"
    fake_vectors(vectors)
    result = probe([output, vectors, "smoke"])
    assert "ADMITTED" in result.stderr, result.stderr
    for source in [
        RUNNER,
        BENCH,
        Path(__file__),
        oracle.KERNEL,
        ACQ / "starlink_pss_phase_map.v",
        ACQ / "starlink_pss_fft_bank_owned_slice.v",
    ]:
        assert (
            output / "frozen_sources" / source.name
        ).read_bytes() == source.read_bytes()
    assert "source_signature=" in (output / "scope.txt").read_text()


def evidence_lines(production):
    bins, frames, count = (20000, 64, 1) if production else (343, 2, 2)
    selected = bins * frames
    s = oracle.support(bins, frames)
    words = s["blocks"] * 512
    lines = [
        f"BANK_PRODUCTION_MAP_COMPLETE epoch={epoch} bins={bins} frames={frames} selected={selected} residue=239 fft_support={s['fft_source_samples']} source_at_stop={s['fft_source_samples'] + 100} potential_tail=208 visible_scores={selected} visible_tail=0 forward_input={words} inverse_input={words} forward={words} product={words} inverse={words} energies={selected} ratios={selected} retained_source=1000 map_words={bins} elapsed_ns=1000.001"
        for epoch in range(1, count + 1)
    ]
    if production:
        lines += [
            f"BANK_PRODUCTION_MAP_PROGRESS selected_prefix={n * 200000} time_ns=1000.001"
            for n in range(1, 7)
        ]
    lines += [
        f"BANK_PRODUCTION_MAP_PARTIAL fresh_scores=447 accepted=447 aborts=1 failed=1 historical_generation={count} reason=10 full_production_map_recovery=0",
        f"BANK_PRODUCTION_MAP_TOTAL exact_scores={selected * count + 447} admitted_scores={selected * count + 447} visible_tail_scores=0 exact_source={count * s['fft_source_samples'] + 1000} exact_forward_input={words * count + 512} exact_inverse_input={words * count + 512} exact_forward={words * count + 512} exact_product={words * count + 512} exact_inverse={words * count + 512} exact_energies={selected * count + 447} exact_ratios={selected * count + 447} exact_map_words={count * bins} terminals={count + 1}",
        f"BANK_PRODUCTION_MAP_PASS production={production} complete_maps={count} fresh_partial=447 actual_core=1 slow_mhz=100 fft_mhz=175 PERIODIC_GEOMETRY_ARITHMETIC_NOT_RF_OR_PHYSICAL_TIMING",
    ]
    return lines


@pytest.mark.parametrize("production", [0, 1])
@pytest.mark.parametrize(
    "mutation",
    [
        "none",
        "missing",
        "duplicate",
        "wrong_epoch",
        "wrong_support",
        "wrong_map",
        "wrong_total",
        "short_inverse",
        "missing_field",
        "duplicate_field",
        "fail",
        "fatal",
        "error",
        "duplicate_pass",
        "wrong_partial",
        "trailing_fail",
    ],
)
def test_terminal_policy(tmp_path, production, mutation):
    lines = evidence_lines(production)
    if mutation == "missing":
        lines.pop(0)
    elif mutation == "duplicate":
        lines.insert(1, lines[0])
    elif mutation == "wrong_epoch":
        lines[0] = lines[0].replace("epoch=1", "epoch=2")
    elif mutation == "wrong_support":
        lines[0] = lines[0].replace("fft_support=", "fft_support=1")
    elif mutation == "wrong_map":
        lines[0] = lines[0].replace("map_words=", "map_words=1")
    elif mutation == "wrong_total":
        lines[-2] = lines[-2].replace("exact_scores=", "exact_scores=1")
    elif mutation == "short_inverse":
        lines[0] = (
            lines[0].replace("inverse=", "inverse=0 ").split("inverse=0")[0]
            + "inverse=0"
        )
    elif mutation == "missing_field":
        lines[0] = lines[0].rsplit(" ", 1)[0]
    elif mutation == "duplicate_field":
        lines[0] += " bins=343"
    elif mutation in {"fail", "trailing_fail"}:
        lines.append("  bank_production_map_fail late numeric mismatch")
    elif mutation in {"fatal", "error"}:
        lines.append(f"{mutation}: simulator failed")
    elif mutation == "duplicate_pass":
        lines.append(lines[-1])
    elif mutation == "wrong_partial":
        lines[-3] = lines[-3].replace("reason=10", "reason=0")
    log = tmp_path / "simulate.log"
    log.write_text("\n".join(lines) + "\n")
    script = f"source {{{ACQ / 'verify_realtime_probe_result.tcl'}}}\nsource {{{ACQ / 'verify_bank_production_map_result.tcl'}}}\n"
    script += f"if {{[catch {{require_bank_production_map_pass {{{log}}} {production}}} message]}} {{puts stderr $message; exit 2}}\n"
    result = subprocess.run(
        ["tclsh"], input=script, capture_output=True, text=True, check=False, timeout=10
    )
    assert (result.returncode == 0) == (mutation == "none"), result.stderr


def test_additive_scope_and_unwaived_prefix_contract():
    bench, runner = BENCH.read_text(), RUNNER.read_text()
    assert "force " not in bench and "launch_runs" not in runner
    for marker in [
        "always @(posedge fft_clk)",
        "if (score_valid) begin",
        "input_sample_energy!==energies",
        "output_numerator!==numerators",
        "read_all_release();",
        "partial_recovery();",
    ]:
        assert marker in bench
    assert "xsim.simulate.custom_tcl" in runner
    assert (ACQ / "run_bank_map_no_waves.tcl").read_text().endswith("run all\n")
    assert "frozen production default drift" in runner
    assert (
        oracle.digest(oracle.KERNEL)
        == "694d0d9b8dd55368bcaaedec37a7cda3a837d491d592ede60eec57a9821fc99a"
    )
    assert len(oracle.GOLDEN_SHA256) == 7


def test_original_sha_pins_reject_self_consistent_replacement(tmp_path):
    for name, (rows, width) in oracle.GOLDENS.items():
        (tmp_path / f"{name}.mem").write_text(("0" * width + "\n") * rows)
    with pytest.raises(ValueError, match="immutable original golden SHA256"):
        oracle.load_original(tmp_path)


def test_no_overwrite_even_before_original_loading(tmp_path):
    retained = tmp_path / "retained"
    retained.write_text("retained")
    before = hashlib.sha256(retained.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        oracle.generate(retained, tmp_path / "missing")
    assert oracle.digest(retained) == before

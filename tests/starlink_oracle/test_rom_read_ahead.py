"""Independent old-source ROM comparison, not FFT or physical qualification."""

import json
import random
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ACQ = ROOT / "hdl/library/starlink_pss_acquisition"
RECIPE = json.loads(Path(__file__).with_name("rom_prefetch_delta.json").read_text())
NEW = "starlink_pss_kernel_rom_read_ahead"


def original():
    return subprocess.check_output(
        ["git", "-C", str(ROOT / "hdl"), "show", RECIPE["base"] +
         ":library/starlink_pss_acquisition/starlink_pss_kernel_rom.v"], text=True
    )


def candidate():
    return (ACQ / (NEW + ".v")).read_text()


def test_exact_additive_source_recipe_and_untouched_original():
    old = original()
    assert old == (ACQ / "starlink_pss_kernel_rom.v").read_text()
    for before, after in RECIPE["edits"]:
        assert old.count(before) == 1
        old = old.replace(before, after, 1)
    assert old == candidate()


def run(tmp_path, width=18, balanced=1, scratch=1, mutated=None, bench=None):
    rng = random.Random(0x7E571EAF)
    words = [rng.getrandbits(2*width) for _ in range(512)]
    (tmp_path / "kernel.mem").write_text(
        "".join(f"{v:0{(2*width+3)//4}x}\n" for v in words)
    )
    (tmp_path / "original.v").write_text(original().replace(
        "module starlink_pss_kernel_rom #(", "module original_kernel #(", 1))
    (tmp_path / "candidate.v").write_text(candidate() if mutated is None else mutated)
    (tmp_path / "bench.sv").write_text(
        (ACQ / "tb/tb_starlink_pss_rom_read_ahead.sv").read_text()
        if bench is None else bench
    )
    compile_result = subprocess.run(
        ["iverilog", "-g2012", "-Wall", "-s", "tb_starlink_pss_rom_read_ahead",
         f"-Ptb_starlink_pss_rom_read_ahead.WIDTH={width}",
         f"-Ptb_starlink_pss_rom_read_ahead.BALANCED={balanced}",
         f"-Ptb_starlink_pss_rom_read_ahead.SCRATCH={scratch}",
         "-o", "simulation", "original.v", "candidate.v", "bench.sv"],
        cwd=tmp_path, capture_output=True, text=True, timeout=20,
    )
    (tmp_path / "compile.log").write_text(compile_result.stdout + compile_result.stderr)
    assert compile_result.returncode == 0, compile_result.stderr
    assert "error:" not in compile_result.stderr.lower()
    result = subprocess.run(["vvp", "simulation"], cwd=tmp_path,
                            capture_output=True, text=True, timeout=30)
    log = result.stdout + result.stderr
    (tmp_path / "simulation.log").write_text(log)
    return result.returncode, log


@pytest.mark.parametrize("width", [2, 18, 24])
@pytest.mark.parametrize("balanced", [0, 1])
@pytest.mark.parametrize("scratch", [0, 1])
def test_full_unconditional_shadow_known_unknown_stall_fault_reset(
    tmp_path, width, balanced, scratch
):
    code, log = run(tmp_path, width, balanced, scratch)
    assert code == 0 and log.count("ROM_READ_AHEAD_OFFLINE_PASS") == 1, log
    assert "healthy=3 faults=64 unknown_metadata=2" in log


@pytest.mark.parametrize("before,after", [
    ("if (use_speculative)\n          retained_word", "if (1'b0)\n          retained_word"),
    ("use_speculative ? speculative_word : retained_word", "speculative_word"),
    ("use_speculative ? speculative_word : retained_word", "retained_word"),
    ("if (input_ready)\n        speculative_word", "if (input_valid)\n        speculative_word"),
    ("speculative_word <= kernel_memory[input_bin_index]", "speculative_word <= kernel_memory[input_bin_index ^ 9'd1]"),
    ("retained_word <= 0;", "retained_word <= 1;"),
    ("if (protocol_error_now)\n            use_speculative", "if (protocol_error_now !== 1'b0)\n            use_speculative"),
    ("output_valid <= 1'b1;", "output_valid <= 1'b0;"),
    ("protocol_fault <= 1'b1;", "protocol_fault <= 1'b0;"),
])
def test_semantic_mutants_reject(tmp_path, before, after):
    source = candidate()
    assert source.count(before) == 1
    code, log = run(tmp_path, mutated=source.replace(before, after, 1))
    assert code != 0 and ("MISMATCH" in log or "coefficient" in log), log


@pytest.mark.parametrize("value", ["-1", "2", "32'bx", "32'bz"])
def test_invalid_unknown_option_rejects_at_time_zero(tmp_path, value):
    bench = (ACQ / "tb/tb_starlink_pss_rom_read_ahead.sv").read_text()
    bench = bench.replace(".PRIVATE_ROM_READ_AHEAD(1)", f".PRIVATE_ROM_READ_AHEAD({value})", 1)
    code, log = run(tmp_path, bench=bench)
    assert code != 0 and "PRIVATE_ROM_READ_AHEAD must be zero or one" in log, log
    assert "Time: 0 " in log

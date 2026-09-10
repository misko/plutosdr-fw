"""No-latency clipping refactor against frozen RTL and sign-magnitude math."""

import hashlib
import random
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HDL = ROOT / "hdl"
RTL = HDL / "library/starlink_pss_acquisition"
BASE = "b49553c16319f59ad8d7b44fd24c494f96eba142"
NAME = "starlink_pss_spectrum_product.v"


def golden_source():
    return subprocess.run(
        ["git", "show", f"{BASE}:library/starlink_pss_acquisition/{NAME}"],
        cwd=HDL, check=True, capture_output=True, text=True,
    ).stdout


def reference(value, width):
    # Independent sign-magnitude nearest/even, not the candidate's floor-bit
    # boundary predicates. Python integers cannot silently overflow.
    quotient, remainder = divmod(abs(value), 1 << width)
    half = 1 << (width - 1)
    quotient += remainder > half or (remainder == half and quotient % 2)
    rounded = -quotient if value < 0 else quotient
    clipped = max(-half, min(half - 1, rounded))
    return (int(clipped != rounded) << width) | (clipped & ((1 << width) - 1))


def vectors(width):
    limit = 1 << (2 * width)
    if width <= 6:
        return range(-limit, limit)  # Every possible signed sum bit pattern.
    scale = 1 << width
    half = scale >> 1
    lo, hi = -limit, limit - 1
    quotients = set(range(-12, 13))
    for boundary in (-scale, -half, half - 1, scale - 1):
        quotients.update(range(boundary - 4, boundary + 5))
    for bit in range(width + 1):
        for sign in (-1, 1):
            quotients.update(sign * (1 << bit) + delta for delta in (-1, 0, 1))
    # All quotient buckets at native18, selected representative remainders.
    if width == 18:
        quotients.update(range(-scale, scale))
    values = [q * scale + r for q in sorted(quotients)
              for r in (0, 1, half - 1, half, half + 1, scale - 1)
              if lo <= q * scale + r <= hi]
    rng = random.Random(0xB0A0 + width)
    values.extend(rng.randint(lo, hi) for _ in range(16000))
    return values


def compile_and_run(tmp_path, width, source):
    assert shutil.which("iverilog") and shutil.which("vvp")
    (tmp_path / NAME).write_text(source)
    frozen = re.sub(r"\bstarlink_pss_spectrum_product\b",
                    "starlink_pss_spectrum_product_b495_golden", golden_source())
    (tmp_path / "golden.v").write_text(frozen)
    bench = RTL / "tb/tb_starlink_spectrum_round_boundary.sv"
    shutil.copyfile(bench, tmp_path / bench.name)
    shutil.copyfile(__file__, tmp_path / "frozen_test.py")
    inputs = [tmp_path / name for name in (NAME, "golden.v", bench.name, "frozen_test.py")]
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    (tmp_path / "input_sources.sha256").write_text(
        "".join(f"{sha}  {name}\n" for name, sha in sorted(hashes.items())))
    values = vectors(width)
    with (tmp_path / "vectors.mem").open("w") as stream:
        for value in values:
            stream.write(f"{value & ((1 << (2 * width + 1)) - 1):x} "
                         f"{reference(value, width):x}\n")
    result = subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", "tb_starlink_spectrum_round_boundary",
        f"-Ptb_starlink_spectrum_round_boundary.D={width}", "-o", "test.vvp",
        NAME, "golden.v", bench.name,
    ], cwd=tmp_path, capture_output=True, text=True, timeout=60, check=False)
    (tmp_path / "compile.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stderr
    result = subprocess.run(["vvp", "test.vvp", "+VECTORS=vectors.mem"],
                            cwd=tmp_path, capture_output=True, text=True, timeout=180,
                            check=False)
    (tmp_path / "simulate.log").write_text(result.stdout + result.stderr)
    assert hashes == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    return result, len(values)


def test_entire_original_body_and_state_restore_exactly():
    text = (RTL / NAME).read_text()
    text = text.replace("parameter integer DATA_WIDTH = 24,\n"
                        "  parameter integer BOUNDARY_ROUND_SAT = 0",
                        "parameter integer DATA_WIDTH = 24")
    text, count = re.subn(r"  // BEGIN BOUNDARY_ROUND_SAT:.*?  // END BOUNDARY_ROUND_SAT\n",
                         "  assign rounded_real = round_and_saturate(sum_real);\n"
                         "  assign rounded_imag = round_and_saturate(sum_imag);\n",
                         text, flags=re.DOTALL)
    assert count == 1
    text, count = re.subn(r"\n  // BEGIN BOUNDARY_ROUND_FUNCTION\n.*?"
                         r"  // END BOUNDARY_ROUND_FUNCTION\n", "", text, flags=re.DOTALL)
    assert count == 1
    assert text == golden_source()


@pytest.mark.parametrize("width", [2, 3, 4, 5, 6, 8, 12, 16, 18, 24])
def test_math_and_whole_elastic_pipeline(tmp_path, width):
    result, count = compile_and_run(tmp_path, width, (RTL / NAME).read_text())
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("ROUND_BOUNDARY_PASS") == 1
    assert f"width={width} vectors={count} cycles=6000" in result.stdout


@pytest.mark.parametrize("old,new", [
    ("|| quotient[0]", "|| 1'b1"),  # Ties-away instead of even.
    ("(low_ones && increment)", "1'b0"),  # Miss positive boundary overflow.
    ("!(low_ones && increment)", "1'b1"),  # Miss rescued negative boundary.
    ("payload = quotient[DATA_WIDTH-1:0] + increment;",
     "payload = quotient[DATA_WIDTH-1:0];"),
])
def test_wrong_rounding_mutants_are_rejected(tmp_path, old, new):
    source = (RTL / NAME).read_text()
    assert old in source
    result, _ = compile_and_run(tmp_path, 4, source.replace(old, new, 1))
    assert result.returncode != 0
    assert "ROUND_BOUNDARY_MISMATCH" in result.stdout


@pytest.mark.parametrize("value", ["-1", "2", "32'bx", "32'bz"])
def test_invalid_option_fails_closed(tmp_path, value):
    (tmp_path / "invalid.sv").write_text(
        "module invalid; starlink_pss_spectrum_product #(" 
        f".BOUNDARY_ROUND_SAT({value})) dut(); initial #1 $finish; endmodule\n")
    result = subprocess.run(["iverilog", "-g2012", "-s", "invalid", "-o", "test.vvp",
                             str(RTL / NAME), "invalid.sv"], cwd=tmp_path,
                            capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 0, result.stderr
    result = subprocess.run(["vvp", "test.vvp"], cwd=tmp_path,
                            capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode != 0
    assert "BOUNDARY_ROUND_SAT must be zero or one" in result.stdout


def test_default_one_bit_width_still_elaborates(tmp_path):
    # The old standalone module allowed D=1. The new opt-in rejects it, but
    # merely adding a default-off function must not break old elaboration.
    (tmp_path / "one.sv").write_text(
        "module one; starlink_pss_spectrum_product #(.DATA_WIDTH(1)) dut(); "
        "initial begin if(dut.round_and_saturate(3'b010) !== 2'b10) "
        "$fatal(1,\"legacy D1\"); #1 $display(\"DEFAULT_D1_PASS\"); $finish; end endmodule\n")
    result = subprocess.run(["iverilog", "-g2012", "-s", "one", "-o", "test.vvp",
                             str(RTL / NAME), "one.sv"], cwd=tmp_path,
                            capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 0, result.stderr
    result = subprocess.run(["vvp", "test.vvp"], cwd=tmp_path,
                            capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "DEFAULT_D1_PASS" in result.stdout

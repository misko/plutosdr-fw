"""Isolated operand boundary; independent accepted-token math, no FFT/physical."""
import hashlib
import random
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HDL = ROOT / "hdl"
RTL = HDL / "library/starlink_pss_acquisition"
CORE = RTL / "starlink_pss_spectrum_product.v"
WRAPPER = RTL / "starlink_pss_spectrum_product_operand_register.v"
BENCH = RTL / "tb/tb_starlink_spectrum_operand_register.sv"
CORE_SHA = "4f9046d0efc395d68caa9b63911fcf5c18ab335b1f2707ad19d3794e0cc2329b"


def rounded(value, width):
    # Sign-magnitude arbitrary precision, independent of RTL floor-bit logic.
    magnitude, rem = divmod(abs(value), 1 << width)
    half = 1 << (width - 1)
    magnitude += rem > half or (rem == half and magnitude % 2)
    result = -magnitude if value < 0 else magnitude
    clipped = max(-half, min(half - 1, result))
    return clipped, int(clipped != result)


def packed_vectors(width):
    rng = random.Random(0xB0A0 + width)
    half = 1 << (width - 1)
    result = []
    for token in range(1024):
        operands = [rng.randrange(-half, half) for _ in range(4)]
        if token % 17 == 0:
            operands = [-half] * 4
        a, b, c, d = operands
        real, ro = rounded(a * c - b * d, width)
        imag, io = rounded(a * d + b * c, width)
        metadata = [(token & 511, 9), (token % 32, 5), (int(token % 17 == 0), 1),
                    ((0xABCDE00000000000 | (token << 19) | rng.randrange(1 << 19)), 64)]
        fields = [(word, width) for word in operands] + metadata + [(real, width), (imag, width), (ro | io, 1)]
        packed = 0
        for word, bits in fields:
            packed = (packed << bits) | (word & ((1 << bits) - 1))
        result.append(f"{packed:0{(6*width+83)//4}x}\n")
    return "".join(result)


def run_case(path, width, boundary, wrapper=None):
    source = WRAPPER.read_text() if wrapper is None else wrapper
    for name, payload in [(CORE.name, CORE.read_text()), (WRAPPER.name, source),
                          (BENCH.name, BENCH.read_text()), ("frozen_test.py", Path(__file__).read_text()),
                          ("vectors.mem", packed_vectors(width))]:
        (path / name).write_text(payload)
    files = sorted(path.iterdir())
    hashes = {file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in files}
    (path / "sources.sha256").write_text("".join(f"{digest}  {name}\n" for name, digest in hashes.items()))
    command = ["iverilog", "-g2012", "-Wall", "-s", "tb_starlink_spectrum_operand_register",
               f"-Ptb_starlink_spectrum_operand_register.D={width}", f"-Ptb_starlink_spectrum_operand_register.B={boundary}",
               "-o", "test.vvp", CORE.name, WRAPPER.name, BENCH.name]
    compiled = subprocess.run(command, cwd=path, text=True, capture_output=True, check=False, timeout=30)
    (path / "compile.log").write_text(compiled.stdout + compiled.stderr)
    assert compiled.returncode == 0, compiled.stderr
    result = subprocess.run(["vvp", "test.vvp", "+VECTORS=vectors.mem"], cwd=path,
                            text=True, capture_output=True, check=False, timeout=30)
    (path / "simulate.log").write_text(result.stdout + result.stderr)
    assert hashes == {file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in files}
    return result


def test_core_unmodified_default_parameters_and_forwarding():
    assert hashlib.sha256(CORE.read_bytes()).hexdigest() == CORE_SHA
    pinned = subprocess.run(["git", "show", "ce9c863ab00228378831dbdb395db1c49554e90b:library/starlink_pss_acquisition/starlink_pss_spectrum_product.v"],
                            cwd=HDL, text=True, capture_output=True, check=True).stdout
    assert CORE.read_text() == pinned
    wrapper = WRAPPER.read_text()
    assert "parameter integer REGISTER_OPERANDS = 0" in wrapper
    assert "parameter integer BOUNDARY_ROUND_SAT = 0" in wrapper
    assert ".BOUNDARY_ROUND_SAT(BOUNDARY_ROUND_SAT)" in wrapper
    assert "reg [4*DATA_WIDTH+79-1:0] payload;" in wrapper
    assert "assign input_ready = core_ready;" in wrapper
    assert "assign core_valid = input_valid;" in wrapper


@pytest.mark.parametrize("width,boundary", [(1, 0), (2, 0), (2, 1), (8, 0), (8, 1), (18, 0), (18, 1), (24, 0), (24, 1)])
def test_exact_math_metadata_latency_and_elastic_ownership(tmp_path, width, boundary):
    result = run_case(tmp_path, width, boundary)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("OPERAND_BOUNDARY_PASS") == 1
    assert result.stdout.count("OPERAND_MODE_PASS") == 2
    assert "registered=0 no_stall_elapsed_clocks=2" in result.stdout
    assert "registered=1 no_stall_elapsed_clocks=3" in result.stdout
    assert not re.search(r"FAIL|MISMATCH|Fatal|ERROR", result.stdout)


@pytest.mark.parametrize("old,new", [
    ("wire ready = !valid || core_ready;", "wire ready = !valid && core_ready;"),
    ("assign core_valid = valid;", "assign core_valid = input_valid;"),
    ("payload <= {input_i, input_q, kernel_i, kernel_q,", "payload <= {input_i, input_q, input_i, input_q,"),
    ("input_block_start_index};", "64'd0};"),
    ("valid <= 1'b0;", "valid <= valid;"),
    ("end else if (ready) begin", "end else begin"),
])
def test_operand_and_ownership_mutations_fail(tmp_path, old, new):
    source = WRAPPER.read_text()
    assert old in source
    result = run_case(tmp_path, 18, 0, source.replace(old, new, 1))
    assert result.returncode != 0 and "OPERAND_" in result.stdout


@pytest.mark.parametrize("parameter", ["REGISTER_OPERANDS", "BOUNDARY_ROUND_SAT"])
@pytest.mark.parametrize("value", ["-1", "2", "32'bx", "32'bz"])
def test_invalid_options_fail_closed(tmp_path, parameter, value):
    (tmp_path / "invalid.sv").write_text(
        f"module invalid; starlink_pss_spectrum_product_operand_register #(.{parameter}({value})) dut(); initial #1 $finish; endmodule\n")
    compiled = subprocess.run(["iverilog", "-g2012", "-s", "invalid", "-o", "bad.vvp", str(CORE), str(WRAPPER), "invalid.sv"],
                              cwd=tmp_path, text=True, capture_output=True, check=False, timeout=15)
    assert compiled.returncode == 0, compiled.stderr
    result = subprocess.run(["vvp", "bad.vvp"], cwd=tmp_path, text=True, capture_output=True, check=False, timeout=15)
    assert result.returncode != 0 and f"{parameter} must be zero or one" in result.stdout


def test_boundary_round_option_preserves_width_guard(tmp_path):
    (tmp_path / "invalid.sv").write_text(
        "module invalid; starlink_pss_spectrum_product_operand_register #(.DATA_WIDTH(1),.REGISTER_OPERANDS(1),.BOUNDARY_ROUND_SAT(1)) dut(); initial #1 $finish; endmodule\n")
    subprocess.run(["iverilog", "-g2012", "-s", "invalid", "-o", "bad.vvp", str(CORE), str(WRAPPER), "invalid.sv"],
                   cwd=tmp_path, capture_output=True, check=True, timeout=15)
    result = subprocess.run(["vvp", "bad.vvp"], cwd=tmp_path, text=True, capture_output=True, check=False, timeout=15)
    assert result.returncode != 0 and "BOUNDARY_ROUND_SAT requires DATA_WIDTH >= 2" in result.stdout


@pytest.mark.parametrize("boundary", [0, 1])
def test_omitted_default_and_actual_arithmetic_parameter_forwarding(tmp_path, boundary):
    (tmp_path / "defaults.sv").write_text(
        "module defaults; starlink_pss_spectrum_product_operand_register legacy();\n"
        f"starlink_pss_spectrum_product_operand_register #(.DATA_WIDTH(18),.BOUNDARY_ROUND_SAT({boundary})) forwarded();\n"
        "initial begin if(legacy.REGISTER_OPERANDS !== 0 || legacy.BOUNDARY_ROUND_SAT !== 0 || legacy.DATA_WIDTH !== 24) "
        "$fatal(1,\"bad omitted default\");\n"
        f"if(forwarded.arithmetic.BOUNDARY_ROUND_SAT !== {boundary} || forwarded.arithmetic.DATA_WIDTH !== 18) "
        "$fatal(1,\"bad actual forwarded parameter\");\n"
        "#1 $display(\"OPERAND_DEFAULT_PARAMETERS_PASS\"); $finish; end endmodule\n")
    subprocess.run(["iverilog", "-g2012", "-s", "defaults", "-o", "defaults.vvp", str(CORE), str(WRAPPER), "defaults.sv"],
                   cwd=tmp_path, capture_output=True, check=True, timeout=15)
    result = subprocess.run(["vvp", "defaults.vvp"], cwd=tmp_path, text=True, capture_output=True, check=False, timeout=15)
    assert result.returncode == 0 and "OPERAND_DEFAULT_PARAMETERS_PASS" in result.stdout


@pytest.mark.parametrize("width", [0, -1])
def test_nonpositive_width_never_admitted(tmp_path, width):
    (tmp_path / "invalid.sv").write_text(
        f"module invalid; starlink_pss_spectrum_product_operand_register #(.DATA_WIDTH({width})) dut(); initial #1 $finish; endmodule\n")
    compiled = subprocess.run(["iverilog", "-g2012", "-s", "invalid", "-o", "bad.vvp", str(CORE), str(WRAPPER), "invalid.sv"],
                              cwd=tmp_path, text=True, capture_output=True, check=False, timeout=15)
    # Invalid replication widths can be rejected during elaboration before the
    # wrapper's time-zero parameter guard. Neither outcome admits a design.
    if compiled.returncode == 0:
        result = subprocess.run(["vvp", "bad.vvp"], cwd=tmp_path, text=True, capture_output=True, check=False, timeout=15)
        assert result.returncode != 0 and "DATA_WIDTH must be a positive integer" in result.stdout
    else:
        assert "negative" in compiled.stderr or "Concatenation repeat" in compiled.stderr

"""Additive arithmetic port, independent token math and offline bank ownership."""
import hashlib
import itertools
import json
import random
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HDL = ROOT / "hdl"
ACQ = HDL / "library/starlink_pss_acquisition"
BASE = "dec20d6371f2d77b6e09c4bcdda2f3d7f8715776"
ROUND_BASE = "f7345ab655a21374f46d2bda89854f40295fca24"
CORE = "starlink_pss_spectrum_product_bank_arithmetic"
WRAPPER = "starlink_pss_spectrum_product_operand_register"
TOP = "starlink_pss_fft_bank_owned_arithmetic_probe"
LEGACY = "starlink_pss_spectrum_product"


def frozen(name, pin=BASE):
    return subprocess.run(["git", "-C", str(HDL), "show", f"{pin}:library/starlink_pss_acquisition/{name}"],
                          capture_output=True, text=True, check=True, timeout=15).stdout


def once(source, old, new):
    assert source.count(old) == 1, old
    return source.replace(old, new, 1)


def round_blocks():
    source = frozen(f"{LEGACY}.v", ROUND_BASE)
    return [source[source.index(f"  // BEGIN {name}"):source.index(f"  // END {name}") + len(f"  // END {name}")]
            for name in ("BOUNDARY_ROUND_SAT", "BOUNDARY_ROUND_FUNCTION")]


def test_exact_additive_round_port_retains_entire_dec20_sequential_behavior():
    source = (ACQ / f"{CORE}.v").read_text()
    source = once(source, f"module {CORE} #(", f"module {LEGACY} #(")
    source = once(source, "  parameter integer PRIVATE_PAYLOAD_BUBBLES = 0,\n  parameter integer BOUNDARY_ROUND_SAT = 0",
                  "  parameter integer PRIVATE_PAYLOAD_BUBBLES = 0")
    selection, function = round_blocks()
    source = once(source, selection, "  assign rounded_real = round_and_saturate(sum_real);\n  assign rounded_imag = round_and_saturate(sum_imag);")
    source = once(source, function + "\n\n", "")
    assert source == frozen(f"{LEGACY}.v")


def test_original_bank_core_bench_and_all_control_modules_byte_unchanged():
    for name in ("starlink_pss_fft_bank_owned_slice", LEGACY, "starlink_pss_realtime_input_guard",
                 "starlink_pss_realtime_result_guard", "starlink_pss_block_mailbox",
                 "starlink_pss_forward_kernel_join", "starlink_pss_kernel_rom"):
        assert (ACQ / f"{name}.v").read_text() == frozen(f"{name}.v")
    name = "tb/tb_starlink_pss_fft_bank_owned_slice.sv"
    assert (ACQ / name).read_text() == frozen(name)


def test_exact_derived_top_inverse_and_held_fault_bindings():
    source = (ACQ / f"{TOP}.v").read_text()
    source = once(source, f"module {TOP} #(", "module starlink_pss_fft_bank_owned_slice #(")
    source = once(source, "  parameter integer REGISTERED_SCHEDULING = 0,\n  parameter integer BOUNDARY_ROUND_SAT = 0,\n  parameter integer REGISTER_OPERANDS = 0",
                  "  parameter integer REGISTERED_SCHEDULING = 0")
    source = once(source, f"  {WRAPPER} #(.DATA_WIDTH(18),\n    .BOUNDARY_ROUND_SAT(BOUNDARY_ROUND_SAT), .REGISTER_OPERANDS(REGISTER_OPERANDS),\n    .PRIVATE_PAYLOAD_BUBBLES(REGISTERED_SCHEDULING)) product (",
                  f"  {LEGACY} #(.DATA_WIDTH(18),\n    .PRIVATE_PAYLOAD_BUBBLES(REGISTERED_SCHEDULING)) product (")
    assert source == frozen("starlink_pss_fft_bank_owned_slice.v")
    assert ".output_overflow(product_overflow), .overflow_pulse()" in source
    assert source.count("product_overflow || product_bank_fault") == 2
    wrapper = (ACQ / f"{WRAPPER}.v").read_text()
    assert f"  {CORE} #(" in wrapper
    assert ".PRIVATE_PAYLOAD_BUBBLES(PRIVATE_PAYLOAD_BUBBLES)" in wrapper


def rounded(value, width):
    magnitude, rem = divmod(abs(value), 1 << width)
    half = 1 << (width - 1)
    magnitude += rem > half or (rem == half and magnitude % 2)
    result = -magnitude if value < 0 else magnitude
    clipped = max(-half, min(half - 1, result))
    return clipped, int(clipped != result)


def vectors(width):
    rng = random.Random(0xB0A0 + width)
    half = 1 << (width - 1)
    rows = []
    for token in range(1024):
        operands = [rng.randrange(-half, half) for _ in range(4)]
        if token % 17 == 0:
            operands = [-half] * 4
        a, b, c, d = operands
        real, ro = rounded(a * c - b * d, width)
        imag, io = rounded(a * d + b * c, width)
        fields = ([(word, width) for word in operands] + [(token & 511, 9), (token % 32, 5),
                  (int(token % 17 == 0), 1), (0xABCDE00000000000 | (token << 19) | rng.randrange(1 << 19), 64)] +
                  [(real, width), (imag, width), (ro | io, 1)])
        packed = 0
        for word, bits in fields:
            packed = (packed << bits) | (word & ((1 << bits) - 1))
        rows.append(f"{packed:0{(6*width+83)//4}x}\n")
    return "".join(rows)


def run_sv(directory, top, files, parameters=(), extra=None, overrides=None):
    payloads = {path.name: path.read_bytes() for path in files}
    assert len(payloads) == len(files)
    if overrides:
        assert overrides.keys() <= payloads.keys()
        payloads.update({name: value.encode() for name, value in overrides.items()})
    payloads["frozen_test.py"] = Path(__file__).read_bytes()
    payloads["tests_init.py.txt"] = (ROOT / "tests/__init__.py").read_bytes()
    payloads["round_reference.v.txt"] = frozen(f"{LEGACY}.v", ROUND_BASE).encode()
    # Freeze the repository Python modules actually imported by this collected
    # suite, including package __init__ and transitive oracle imports. Installed
    # Python/pytest/third-party binaries remain outside this source inventory.
    python_sources = {}
    for module in tuple(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if not filename:
            continue
        path = Path(filename).resolve()
        if path.suffix != ".py" or ROOT not in path.parents:
            continue
        relative = path.relative_to(ROOT).as_posix()
        name = "python__" + relative.replace("/", "__")
        if name in python_sources:
            assert python_sources[name] == relative
            continue
        assert name not in payloads
        python_sources[name] = relative
        payloads[name] = path.read_bytes()
    assert "tests/test_starlink_bank_arithmetic_offline.py" in python_sources.values()
    payloads["python_sources.json"] = (json.dumps(python_sources, sort_keys=True, indent=2) + "\n").encode()
    if extra:
        assert not payloads.keys() & extra.keys()
        payloads.update({name: value.encode() for name, value in extra.items()})
    for name, payload in payloads.items():
        (directory / name).write_bytes(payload)
    hashes = {name: hashlib.sha256(payload).hexdigest() for name, payload in payloads.items()}
    (directory / "sources.sha256").write_text("".join(f"{digest}  {name}\n" for name, digest in sorted(hashes.items())))
    compiled = subprocess.run(["env", "-u", "LD_LIBRARY_PATH", "iverilog", "-g2012", "-Wall", "-s", top,
        *[f"-P{top}.{p}" for p in parameters], "-o", "test.vvp", *[path.name for path in files]],
        cwd=directory, capture_output=True, text=True, check=False, timeout=30)
    (directory / "compile.log").write_text(compiled.stdout + compiled.stderr)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    result = subprocess.run(["env", "-u", "LD_LIBRARY_PATH", "vvp", "test.vvp", "+VECTORS=vectors.mem"],
        cwd=directory, capture_output=True, text=True, check=False, timeout=60)
    (directory / "simulate.log").write_text(result.stdout + result.stderr)
    actual = {p.name for p in directory.iterdir()} - {"sources.sha256", "compile.log", "simulate.log", "test.vvp"}
    assert actual == hashes.keys()
    assert hashes == {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in hashes}
    return result


@pytest.mark.parametrize("boundary,private", list(itertools.product((0, 1), repeat=2)))
@pytest.mark.parametrize("width", [2, 18, 24])
def test_all_eight_options_exact_math_latency_bubbles_stalls_reset_flush(tmp_path, boundary, private, width):
    files = [ACQ / f"{name}.v" for name in (LEGACY, CORE, WRAPPER)] + [ACQ / "tb/tb_starlink_bank_operand_register.sv"]
    result = run_sv(tmp_path, "tb_starlink_bank_operand_register", files,
                    [f"D={width}", f"B={boundary}", f"P={private}"], {"vectors.mem": vectors(width)})
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("OPERAND_BOUNDARY_PASS") == 1
    assert result.stdout.count("OPERAND_MODE_PASS") == 2
    assert f"OPERAND_PRIVATE_BUBBLES_PASS enabled={private}" in result.stdout
    assert "registered=0 no_stall_elapsed_clocks=2" in result.stdout
    assert "registered=1 no_stall_elapsed_clocks=3" in result.stdout
    assert not re.search(r"FAIL|MISMATCH|FATAL|ERROR", result.stdout, re.IGNORECASE)


def bank_files():
    names = (TOP, CORE, WRAPPER, "starlink_pss_realtime_input_guard", "starlink_pss_realtime_result_guard",
             "starlink_pss_block_mailbox", "starlink_pss_forward_kernel_join", "starlink_pss_kernel_rom")
    return [ACQ / f"{name}.v" for name in names] + [ACQ / "tb/starlink_pss_offline_xfft_interface.sv",
        ACQ / "tb/tb_starlink_bank_arithmetic_ownership.sv",
        ACQ / "tb/starlink_pss_realtime_result_guard_ce6a885e_golden.v",
        ACQ / "tb/starlink_pss_forward_retirement_shadow.sv"]


@pytest.mark.parametrize("registered,boundary,scheduling", list(itertools.product((0, 1), repeat=3)))
def test_offline_bank_healthy_two_blocks_actual_bindings_and_prefetch(tmp_path, registered, boundary, scheduling):
    kernel = frozen("evidence/forward-retirement-v1/actual/frozen_sources/upper_edge_pss_kernel_q17.mem")
    result = run_sv(tmp_path, "tb_starlink_bank_arithmetic_ownership", bank_files(),
        [f"R={registered}", f"B={boundary}", f"S={scheduling}", "CASE=0"], {"upper_edge_pss_kernel_q17.mem": kernel})
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("BANK_ARITHMETIC_OWNERSHIP_PASS") == 1
    assert "outputs=1024" in result.stdout and "synthetic_interface_not_fft=1" in result.stdout
    assert not re.search(r"FAIL|MISMATCH|FATAL|ERROR", result.stdout, re.IGNORECASE)


@pytest.mark.parametrize("registered", [0, 1])
@pytest.mark.parametrize("case", range(1, 12))
def test_offline_bank_current_late_faults_and_common_epoch_recovery(tmp_path, registered, case):
    kernel = frozen("evidence/forward-retirement-v1/actual/frozen_sources/upper_edge_pss_kernel_q17.mem")
    result = run_sv(tmp_path, "tb_starlink_bank_arithmetic_ownership", bank_files(),
        [f"R={registered}", "B=1", "S=1", f"CASE={case}"], {"upper_edge_pss_kernel_q17.mem": kernel})
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("BANK_ARITHMETIC_OWNERSHIP_PASS") == 1
    assert "outputs=512" in result.stdout and "synthetic_interface_not_fft=1" in result.stdout
    assert not re.search(r"FAIL|MISMATCH|FATAL|ERROR", result.stdout, re.IGNORECASE)


@pytest.mark.parametrize("mutation", ["external_held_to_pulse", "completed_held_to_pulse", "commit_veto", "ack_veto"])
def test_missing_held_fault_and_late_publication_veto_mutations_rejected(tmp_path, mutation):
    source = (ACQ / f"{TOP}.v").read_text()
    if mutation.endswith("held_to_pulse"):
        label = "external_fault_now" if mutation.startswith("external") else "completed_input_fault_now"
        start = source.index(f"  wire {label} =")
        end = source.index(";", start) + 1
        block = source[start:end]
        changed = once(block, "product_overflow", "product.overflow_pulse")
        source = once(source, block, changed)
        case = 2
        reason = "BANK_OFFLINE_HELD_CAUSE_LOST_WHEN_PULSE_CLEARED"
    elif mutation == "commit_veto":
        source = once(source, "wire product_commit_authorized = forward_committed && !external_fault_now && !result_fault;",
                      "wire product_commit_authorized = forward_committed && !result_fault;")
        case = 3
        reason = "BANK_OFFLINE_LATE_FORWARD_EVENT_VETO"
    else:
        source = once(source, "    !external_fault_now && !result_fault;", "    !result_fault;")
        case = 4
        reason = "BANK_OFFLINE_LATE_FORWARD_EVENT_VETO"
    kernel = frozen("evidence/forward-retirement-v1/actual/frozen_sources/upper_edge_pss_kernel_q17.mem")
    result = run_sv(tmp_path, "tb_starlink_bank_arithmetic_ownership", bank_files(),
        ["R=1", "B=1", "S=1", f"CASE={case}"], {"upper_edge_pss_kernel_q17.mem": kernel}, {f"{TOP}.v": source})
    assert result.returncode != 0 and reason in result.stdout, result.stdout + result.stderr
    assert "BANK_ARITHMETIC_OWNERSHIP_PASS" not in result.stdout


@pytest.mark.parametrize("old,new,reason", [
    ("end else if (ready) begin", "end else begin", "OPERAND_PRIVATE_BUBBLE_OWNERSHIP_MISMATCH"),
    ("payload[78:0] <= {input_bin_index", "payload[78:0] <= {9'd0", "OPERAND_"),
    ("{input_i, input_q, kernel_i, kernel_q};", "{input_i, input_q, input_i, input_q};", "OPERAND_"),
    ("valid <= input_valid;", "valid <= PRIVATE_PAYLOAD_BUBBLES || input_valid;", "OPERAND_"),
])
def test_operand_occupied_metadata_numeric_and_invalid_token_mutations_rejected(tmp_path, old, new, reason):
    source = once((ACQ / f"{WRAPPER}.v").read_text(), old, new)
    files = [ACQ / f"{name}.v" for name in (LEGACY, CORE, WRAPPER)] + [ACQ / "tb/tb_starlink_bank_operand_register.sv"]
    result = run_sv(tmp_path, "tb_starlink_bank_operand_register", files,
        ["D=18", "B=1", "P=1"], {"vectors.mem": vectors(18)}, {f"{WRAPPER}.v": source})
    assert result.returncode != 0 and reason in result.stdout, result.stdout + result.stderr
    assert "OPERAND_BOUNDARY_PASS" not in result.stdout


@pytest.mark.parametrize("parameter", ["REGISTER_OPERANDS", "BOUNDARY_ROUND_SAT", "PRIVATE_PAYLOAD_BUBBLES"])
@pytest.mark.parametrize("value", ["-1", "2", "32'bx", "32'bz"])
def test_new_options_reject_invalid_binary_and_unknown_values(tmp_path, parameter, value):
    probe = tmp_path / "invalid.sv"
    probe.write_text(f"module invalid; {WRAPPER} #(.{parameter}({value})) dut(); initial #1 $finish(0); endmodule\n")
    result = run_sv(tmp_path, "invalid", [ACQ / f"{CORE}.v", ACQ / f"{WRAPPER}.v", probe])
    assert result.returncode != 0 and f"{parameter} must be zero or one" in result.stdout

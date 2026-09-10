"""Offline-only monitor seam, genuine corruption rejection, and transport veto."""
import itertools
import json
import re
import subprocess
from pathlib import Path

import pytest

from tests import test_starlink_bank_arithmetic_actual_policy as policy
from tests import test_starlink_bank_arithmetic_offline as offline
from tests.starlink_oracle import bank_arithmetic_actual as study

FAILURE_PIN = "5e4c2ad291ac682308ea65b2a48758b2d445b75c"


def failed_source(relative):
    return subprocess.run(["git", "-C", str(study.ROOT / "hdl"), "show",
        f"{FAILURE_PIN}:library/starlink_pss_acquisition/{relative}"],
        capture_output=True, text=True, check=True, timeout=15).stdout


def test_exactly_six_references_changed_no_fault_checker_stimulus_or_runtime_change():
    name = "tb/" + study.NEW_BENCH + ".sv"
    old = failed_source(name)
    expected = old
    for field in study.PRODUCT_MONITOR_FIELDS:
        anchor = "dut.product." + field
        # All two occurrences are in product_outputs, not external fault stimuli.
        assert expected.count(anchor) == 2
        expected = expected.replace(anchor, "dut.product.arithmetic." + field)
    assert (study.ACQ / name).read_text() == expected
    assert study.adapt_bench(expected, inverse=True) == study.original("tb/" + study.OLD_BENCH + ".sv")
    for name in [*(item + ".v" for item in study.RTL),
                 "tb/" + study.NEW_SHADOW + ".sv", "tb/" + study.OLD_SHADOW + ".sv",
                 "tb/starlink_pss_bank_arithmetic_actual_checks.svh"]:
        assert (study.ACQ / name).read_text() == failed_source(name)
    runner = (study.ACQ / "simulate_bank_arithmetic_actual.tcl").read_text()
    extra = "set_property xsim.simulate.custom_tcl [file join $source_dir simulate_bank_arithmetic_diagnostics.tcl] [get_filesets sim_1]\n"
    assert study.once(runner, extra, "") == failed_source("simulate_bank_arithmetic_actual.tcl")
    for literal in ("force dut.product_overflow=1", "force dut.product_position=9'd19",
                    "force dut.product_start=64'hdeadbeef"):
        # Preserve spacing as the original source spells each force.
        assert re.sub(r"\s+", "", literal) in re.sub(r"\s+", "", expected)


@pytest.mark.parametrize("field", ["output_bin_index", "output_block_start_index", "output_overflow"])
def test_transport_assignment_mutation_cannot_hide_behind_register_rebind(field):
    payloads = {name: (study.ACQ / name).read_bytes() for name in study.PRODUCT_BOUNDARY_HASHES}
    name = "starlink_pss_spectrum_product_operand_register.v"
    source = payloads[name].decode()
    source = study.once(source, f".{field}({field})", f".{field}(changed_transport)")
    source = source.replace("  initial begin", "  wire [63:0] changed_transport;\n"
        f"  assign {field} = changed_transport ^ 1'b1;\n  initial begin", 1)
    payloads[name] = source.encode()
    with pytest.raises(ValueError, match="monitor/transport source boundary"):
        study.verify_product_monitor_boundary(payloads)


@pytest.mark.parametrize("field", ["output_bin_index", "output_block_start_index", "output_overflow",
                                   "input_ready", "output_i", "output_q"])
def test_missing_rebind_or_extra_rebind_fails_exact_inverse(field):
    source = (study.ACQ / "tb" / (study.NEW_BENCH + ".sv")).read_text()
    if field in study.PRODUCT_MONITOR_FIELDS:
        source = source.replace("dut.product.arithmetic." + field, "dut.product." + field, 1)
    else:
        source = source.replace("dut.product." + field, "dut.product.arithmetic." + field, 1)
    with pytest.raises(ValueError, match="strict adaptation anchor"):
        study.adapt_bench(source, inverse=True)


def monitor_unit_bench():
    source = policy.shadow_bench()
    before = ("wire [118:0] product_outputs={p_ready,p_valid,p_i,p_q,p_position,p_exponent,\n"
              "    p_last,p_start,p_overflow,p_overflow_pulse};")
    after = ("wire [118:0] product_outputs={product.input_ready,product.output_valid,product.output_i,product.output_q,\n"
             "    product.arithmetic.output_bin_index,product.output_block_exponent,product.output_last,\n"
             "    product.arithmetic.output_block_start_index,product.arithmetic.output_overflow,product.overflow_pulse};")
    return study.once(source, before, after)


def run_monitor_unit(directory, option, boundary, mutation=None):
    names = ["starlink_pss_forward_kernel_join", "starlink_pss_kernel_rom",
             "starlink_pss_spectrum_product_operand_register", "starlink_pss_spectrum_product_bank_arithmetic"]
    files = [study.ACQ / (name + ".v") for name in names]
    files += [study.ACQ / "tb" / name for name in study.TB
              if "golden" in name or name in (study.NEW_SHADOW + ".sv", study.OLD_SHADOW + ".sv")]
    for path in files:
        (directory / path.name).write_bytes(path.read_bytes())
    (directory / "test.sv").write_text(monitor_unit_bench())
    if mutation:
        core = directory / "starlink_pss_spectrum_product_bank_arithmetic.v"
        source = core.read_text()
        old, new = {
            "position": ("output_bin_index <= sum_bin_index;", "output_bin_index <= sum_bin_index ^ 9'b1;"),
            "start": ("output_block_start_index <= sum_block_start_index;", "output_block_start_index <= sum_block_start_index ^ 64'b1;"),
            "overflow": ("output_overflow <= rounded_real[DATA_WIDTH] ||\n                             rounded_imag[DATA_WIDTH];",
                         "output_overflow <= !(rounded_real[DATA_WIDTH] || rounded_imag[DATA_WIDTH]);"),
            "i": ("output_i <= rounded_real[DATA_WIDTH-1:0];", "output_i <= rounded_real[DATA_WIDTH-1:0] ^ 18'b1;"),
            "q": ("output_q <= rounded_imag[DATA_WIDTH-1:0];", "output_q <= rounded_imag[DATA_WIDTH-1:0] ^ 18'b1;"),
        }[mutation]
        core.write_text(study.once(source, old, new))
    (directory / "upper_edge_pss_kernel_q17.mem").write_bytes((policy.VECTORS / "upper_edge_pss_kernel_q17.mem").read_bytes())
    (directory / "monitor_policy.py").write_bytes(Path(__file__).read_bytes())
    (directory / "actual_helper.py").write_bytes(Path(study.__file__).read_bytes())
    before = {path.name: study.sha(path) for path in directory.iterdir()}
    (directory / "sources.json").write_text(json.dumps(before, indent=2) + "\n")
    result = subprocess.run(["env", "-u", "LD_LIBRARY_PATH", "iverilog", "-g2012", "-s", "tb_arithmetic_shadow",
        f"-Ptb_arithmetic_shadow.O={option}", f"-Ptb_arithmetic_shadow.B={boundary}",
        "-Ptb_arithmetic_shadow.JOIN_BUBBLES=1", "-Ptb_arithmetic_shadow.PRODUCT_BUBBLES=1",
        "-Ptb_arithmetic_shadow.BALANCED_ROM=1", "-o", "test.vvp", "test.sv", *[path.name for path in files]],
        cwd=directory, capture_output=True, text=True, check=False, timeout=30)
    (directory / "compile.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run(["env", "-u", "LD_LIBRARY_PATH", "vvp", "test.vvp"], cwd=directory,
                            capture_output=True, text=True, check=False, timeout=30)
    (directory / "simulate.log").write_text(result.stdout + result.stderr)
    assert before == {name: study.sha(directory / name) for name in before}
    return result


@pytest.mark.parametrize("option,boundary", list(itertools.product((0, 1), repeat=2)))
def test_full_119bit_rebound_monitor_retains_healthy_stall_reset_flush(tmp_path, option, boundary):
    result = run_monitor_unit(tmp_path, option, boundary)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("PAYLOAD_BUBBLES_PASS") == 1
    assert not re.search(r"FATAL|FAIL|MISMATCH|ERROR", result.stdout, re.IGNORECASE)


@pytest.mark.parametrize("option", (0, 1))
@pytest.mark.parametrize("mutation", ("overflow", "position", "start", "i", "q"))
def test_genuine_arithmetic_register_corruption_still_fails_full_monitor(tmp_path, option, mutation):
    result = run_monitor_unit(tmp_path, option, option, mutation)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "PAYLOAD_PRODUCT_OUTPUT_MISMATCH" in result.stdout
    assert "PAYLOAD_BUBBLES_PASS" not in result.stdout


@pytest.mark.parametrize("option", (0, 1))
@pytest.mark.parametrize("case", (2, 5, 8))
def test_unchanged_real_bank_guard_mailbox_sees_held_overflow_and_external_metadata(tmp_path, option, case):
    # This existing transactor is explicitly NOT FFT. It exercises the real
    # bank guard/mailbox raw-current and held-fault veto and reset recovery.
    kernel = offline.frozen("evidence/forward-retirement-v1/actual/frozen_sources/upper_edge_pss_kernel_q17.mem")
    result = offline.run_sv(tmp_path, "tb_starlink_bank_arithmetic_ownership", offline.bank_files(),
        [f"R={option}", "B=1", "S=1", f"CASE={case}"], {"upper_edge_pss_kernel_q17.mem": kernel})
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("BANK_ARITHMETIC_OWNERSHIP_PASS") == 1
    assert "synthetic_interface_not_fft=1" in result.stdout
    assert not re.search(r"FATAL|FAIL|MISMATCH|ERROR", result.stdout, re.IGNORECASE)


def diagnostic_objects(option):
    root = f"/\\tb_starlink_pss_bank_arithmetic_actual(FAST_MHZ=175,B={option},O={option}) "
    reference = "unchanged_reference.reference" if option == 0 else "extra_token_reference.reference"
    objects = []
    for shadow in ("payload_shadow", "forward_chain_shadow"):
        objects.append(f"{root}/{shadow}/product_outputs")
        base = f"{root}/{shadow}/\\{reference} "
        objects.extend(base + "/" + name for name in (
            "product_outputs", "p_ready", "p_valid", "p_i", "p_q", "p_position", "p_exponent", "p_last",
            "p_start", "p_overflow", "p_overflow_pulse", "resetn", "flush", "product_enable", "output_ready"))
        if option:
            objects.extend(base + "/" + name for name in ("available", "occupied"))
    objects.extend(root + suffix for suffix in ("/dut/product/output_overflow", "/dut/product/arithmetic/output_overflow",
        "/dut/product_overflow", "/dut/product_position", "/dut/product_start", "/dut/external_fault_now"))
    return objects


def mock_diagnostics(tmp_path, option, mutation=None):
    objects = diagnostic_objects(option)
    if mutation == "missing":
        objects = [path for path in objects if not path.endswith("/dut/product/arithmetic/output_overflow")]
    elif mutation == "duplicate":
        objects += [objects[-2].rsplit("/", 1)[0] + "/product_overflow"]
    source = ("set fixture_objects [list " + " ".join("{" + path + "}" for path in objects) + "]\n"
        "proc current_wave_config {} {return default}\n"
        "proc get_objects {args} {return $::fixture_objects}\n"
        "proc log_wave {objects} {set ::logged $objects}\n"
        "proc run {args} {if {$args ne {all}} {error MOCK_WRONG_RUNTIME}; puts MOCK_RUN_ALL_ONLY}\n")
    custom = study.ACQ / "simulate_bank_arithmetic_diagnostics.tcl"
    script = tmp_path / "mock-diagnostics-NOT-simulator.tcl"
    script.write_text(source + f"source {{{custom}}}\n")
    result = subprocess.run(["tclsh", str(script)], cwd=tmp_path, capture_output=True, text=True, timeout=15, check=False)
    (tmp_path / "mock-diagnostics.log").write_text(result.stdout + result.stderr)
    return result, script


@pytest.mark.parametrize("option", (0, 1))
def test_frozen_diagnostic_Tcl_inventory_runall_and_nonoverwrite(tmp_path, option):
    result, script = mock_diagnostics(tmp_path, option)
    assert result.returncode == 0, result.stdout + result.stderr
    inventory = tmp_path / "arithmetic_diagnostic_signals.txt"
    assert inventory.read_text().splitlines() == diagnostic_objects(option)
    assert "MOCK_RUN_ALL_ONLY" in result.stdout
    assert study.require_wave_diagnostics(result.stdout, inventory.read_text())["comparison_width"] == 119
    before = inventory.read_bytes()
    again = subprocess.run(["tclsh", str(script)], cwd=tmp_path, capture_output=True, text=True, timeout=15, check=False)
    (tmp_path / "mock-diagnostics-repeat.log").write_text(again.stdout + again.stderr)
    assert again.returncode != 0 and "file already exists" in again.stderr
    assert "MOCK_RUN_ALL_ONLY" not in again.stdout and inventory.read_bytes() == before


@pytest.mark.parametrize("mutation", ("missing", "duplicate"))
def test_diagnostic_scope_missing_duplicate_rejected_before_runall(tmp_path, mutation):
    result, _ = mock_diagnostics(tmp_path, 1, mutation)
    assert result.returncode != 0 and "ARITHMETIC_WAVE_DIAGNOSTIC_INVENTORY_MISMATCH" in result.stderr
    assert "MOCK_RUN_ALL_ONLY" not in result.stdout
    assert not (tmp_path / "arithmetic_diagnostic_signals.txt").exists()


@pytest.mark.parametrize("mutation", ("missing_marker", "duplicate_marker", "too_many", "missing_path", "duplicate_path"))
def test_diagnostic_result_receipt_rejects_partial_inventory(mutation):
    objects = diagnostic_objects(1)
    log = f"ARITHMETIC_WAVE_DIAGNOSTICS_ENABLED objects={len(objects)} monitors=4 references=2 wrapper=1 inner=1 transport=1\n"
    inventory = "\n".join(objects) + "\n"
    if mutation == "missing_marker":
        log = ""
    elif mutation == "duplicate_marker":
        log += log
    elif mutation == "too_many":
        log = log.replace(f"objects={len(objects)}", "objects=257")
    elif mutation == "missing_path":
        inventory = "\n".join(objects[:-1]) + "\n"
    else:
        inventory = "\n".join(objects[:-1] + [objects[0]]) + "\n"
    with pytest.raises(ValueError, match="diagnostic"):
        study.require_wave_diagnostics(log, inventory)


def test_new_diagnostics_policy_and_source_closure_are_frozen(tmp_path):
    result = study.freeze(tmp_path / "prepared", policy.VECTORS, 175, 1, 1, 1)
    assert "simulate_bank_arithmetic_diagnostics.tcl" in result["source_sha256"]
    assert "tests/test_starlink_bank_arithmetic_monitor_boundary.py" in result["python_import_sources"]
    source = tmp_path / "prepared/frozen_sources"
    name = "starlink_pss_spectrum_product_operand_register.v"
    (source / name).write_bytes((source / name).read_bytes() + b"\n// altered transport cohort\n")
    result["source_sha256"][name] = study.sha(source / name)
    (tmp_path / "prepared/manifest.json").write_text(json.dumps(result))
    with pytest.raises(ValueError, match="monitor/transport source boundary"):
        study.verify_freeze(tmp_path / "prepared")


@pytest.mark.parametrize("option,kind", list(itertools.product((0, 1), range(3))))
def test_recorded_same_source_Xsim_force_vectors_prove_exact_rebound_fields(option, kind):
    # Receipt analysis only, NOT a new Xsim run. Preserve the observed Icarus
    # difference rather than claiming its force semantics match vendor Xsim.
    path = study.ROOT / "reports/experiments/20260910-bank-arithmetic-force-diagnosis-v1.json"
    evidence = json.loads(path.read_text())
    assert evidence["all_actual_runs_remain_failed"]
    assert evidence["actual_bank_internal_vector_available"] is False
    for name, expected in study.PRODUCT_BOUNDARY_HASHES.items():
        assert evidence["standalone_sources"][name] == expected
    rows = evidence["observed_vectors"][str(option)]
    xsim = rows["xsim"][kind]
    icarus = rows["icarus_identical_source"][kind]
    expected = (2, 0x53 << 72, (0x2000e0000 ^ 0xdeadbeef) << 2)[kind]
    assert int(xsim["wrapper_xor"], 16) == expected
    assert int(xsim["old_xor"], 16) == int(xsim["inner_xor"], 16) == 0
    masks = ((1 << 1), ((1 << 9) - 1) << 72, ((1 << 64) - 1) << 2)
    wrapper = int(xsim["wrapper_monitor"], 16)
    before = int(xsim["before_wrapper"], 16)
    rebound = (wrapper & ~masks[kind]) | (before & masks[kind])
    assert rebound == int(xsim["old_monitor"], 16)
    assert all(int(icarus[name], 16) == expected for name in ("old_xor", "wrapper_xor", "inner_xor"))

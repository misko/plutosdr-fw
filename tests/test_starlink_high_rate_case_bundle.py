"""Case input closure and Tcl admission only; no actual FFT/Vivado invocation."""

import json
import os
import subprocess
import sys

import pytest

from tests.starlink_oracle.high_rate_cases import BASE, ROOT
from tests.starlink_oracle.high_rate_harness import encoded, sha
from tests.test_starlink_high_rate_case_result import specimen
from tools.prepare_starlink_high_rate_cases import (
    ACQ,
    ADDITIVE,
    freeze,
    verify,
    verify_simulation,
)

RUNNER = ROOT / ACQ / "simulate_high_rate_bank_native_cases.tcl"


@pytest.fixture(scope="session")
def native_probe(tmp_path_factory):
    from tests.test_starlink_high_rate_cases import (
        test_actual_late_native_only_zero_capture_result,
    )
    output = tmp_path_factory.mktemp("native_only_probe_NOT_FFT")
    test_actual_late_native_only_zero_capture_result(output)
    return output


@pytest.fixture
def bundle(tmp_path, native_probe):
    output = tmp_path / "prepared"
    freeze("late447", BASE, output, native_probe)
    return output


@pytest.mark.parametrize("case", ["healthy343", "late447"])
def test_bundle_closure_original95_plus_exact_additive_no_overwrite(tmp_path, native_probe, case):
    output = tmp_path / "prepared"
    r = freeze(case, BASE, output, native_probe)
    assert verify(output) == r
    assert len(r["source_sha256"]) == 95 + len(ADDITIVE)
    assert len(r["python_dependency_edges"]) == 12
    assert {"tests/starlink_oracle/high_rate_harness.py", "tests/starlink_oracle/native30_budget.py",
            "tests/test_starlink_high_rate_harness.py", "tests/test_starlink_native30_budget.py",
            "tools/prepare_starlink_high_rate_harness.py"} <= r["python_dependency_edges"].keys()
    assert (output / "base/bundle.json").read_bytes() == (BASE / "bundle.json").read_bytes()
    with pytest.raises(ValueError, match="overwrite"):
        freeze(case, BASE, output, native_probe)


@pytest.mark.parametrize("case", ["healthy447", "healthy60", "late343", "343", ""])
def test_no_alternate_contract(tmp_path, native_probe, case):
    with pytest.raises(ValueError, match="only healthy343 or late447"):
        freeze(case, BASE, tmp_path / "prepared", native_probe)


def probe(arguments, prelude="", env=None):
    script = 'proc version {args} {return 2022.2}\n' + prelude
    script += "\nset argv [list " + " ".join(f"{{{x}}}" for x in arguments) + "]\n"
    script += f"set argc [llength $argv]\nif {{[catch {{source {{{RUNNER}}}}} message]}} {{puts stderr $message; exit 2}}\n"
    return subprocess.run(["tclsh"], input=script, capture_output=True, text=True, timeout=30, check=False, env=env)


ENTRY = """
  proc set_param {name value} {if {$name ne "general.maxThreads" || $value ne "2"} {error BAD_THREAD_BOUND}}
  proc create_project {args} {error POLICY_ONLY_ADMITTED_NO_IP}
  proc close_project {args} {}
"""


def test_runner_admission_original_error_after_integrity_no_actual_ip(bundle, tmp_path):
    output = tmp_path / "run"
    result = probe([output, bundle, sys.executable], ENTRY)
    (tmp_path / "runner.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 2 and result.stderr.strip() == "POLICY_ONLY_ADMITTED_NO_IP"
    assert "integrity_exit=0" in (output / "after_integrity.txt").read_text()
    assert "run_tcl_exit=1" in (output / "run_status.txt").read_text()
    assert not (output / "terminal_receipt.json").exists()
    assert verify(output / "inputs") == verify(bundle)


def test_runner_subprocess_sanitized_parent_environment_preserved(bundle, tmp_path):
    output = tmp_path / "run"
    prelude = """
      proc set_param {args} {}
      proc create_project {args} {
        foreach name {PYTHONHOME PYTHONPATH LD_LIBRARY_PATH} {
          if {$::env($name) ne "/nonexistent/contaminated-vendor-python"} {error PARENT_ENV_MUTATED}
        }
        error POLICY_ONLY_PARENT_ENV_PRESERVED
      }
      proc close_project {args} {}
    """
    environment = {**os.environ, **dict.fromkeys(["PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH"], "/nonexistent/contaminated-vendor-python")}
    result = probe([output, bundle, sys.executable], prelude, env=environment)
    (tmp_path / "runner.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 2 and result.stderr.strip() == "POLICY_ONLY_PARENT_ENV_PRESERVED"
    assert "integrity_exit=0" in (output / "after_integrity.txt").read_text()


@pytest.mark.parametrize("extra", ["30", "60", "343x2", "200"])
def test_runner_rejects_extra_rate_geometry_clock(bundle, tmp_path, extra):
    result = probe([tmp_path / "run", bundle, sys.executable, extra])
    assert result.returncode == 2 and "no alternate rate/geometry/clock" in result.stderr
    assert not (tmp_path / "run").exists()


def test_runner_rejects_overwrite(bundle, tmp_path):
    output = tmp_path / "run"
    output.mkdir()
    result = probe([output, bundle, sys.executable])
    assert result.returncode == 2 and "refusing to overwrite" in result.stderr
    assert not list(output.iterdir())


@pytest.mark.parametrize("mutation", ["source", "signature", "closure", "runner", "base", "case", "inverse", "dependency", "dependency_receipt"])
def test_runner_rejects_mutated_source_identity_or_case_before_project(bundle, tmp_path, mutation):
    path = bundle / "bundle.json"
    receipt = json.loads(path.read_text())
    name = ACQ + "simulate_high_rate_bank_native_cases.tcl"
    if mutation in {"source", "runner"}:
        source = bundle / "source_snapshot" / name
        source.write_text(source.read_text() + "\n# MUTANT\n")
        if mutation == "runner":
            receipt["files"]["source_snapshot/" + name] = sha(source.read_bytes())
            receipt["source_sha256"][name] = sha(source.read_bytes())
    elif mutation == "signature":
        receipt["source_sha256"][name] = "0" * 64
    elif mutation == "closure":
        receipt["source_sha256"].pop(name)
    elif mutation == "base":
        source = bundle / "base/source_snapshot" / ACQ / "starlink_pss_x2_ddc.v"
        source.write_text(source.read_text() + "\n// MUTANT\n")
        receipt["files"][str(source.relative_to(bundle))] = sha(source.read_bytes())
    elif mutation == "case":
        receipt["contract"]["selected"] += 1
    elif mutation == "dependency":
        name = "tests/test_starlink_high_rate_cases.py"
        source = bundle / "source_snapshot" / name
        source.write_text(source.read_text() + "\nimport tests.not_in_frozen_closure\n")
        receipt["files"]["source_snapshot/" + name] = sha(source.read_bytes())
        receipt["source_sha256"][name] = sha(source.read_bytes())
    elif mutation == "dependency_receipt":
        receipt["python_dependency_edges"].pop("tests/starlink_oracle/high_rate_harness.py")
    else:
        source = bundle / "generated/tb_starlink_high_rate30_case.sv"
        source.write_text(source.read_text().replace("always #5 clk=!clk;", "always #6 clk=!clk;"))
        receipt["files"][str(source.relative_to(bundle))] = sha(source.read_bytes())
    receipt["source_signature"] = sha(encoded(receipt["source_sha256"]))
    path.write_bytes(encoded(receipt))
    result = probe([tmp_path / "run", bundle, sys.executable], ENTRY)
    assert result.returncode == 2
    assert not (tmp_path / "run").exists()
    if mutation == "runner":
        assert "runner differs" in result.stderr


@pytest.mark.parametrize("damage", [False, True])
def test_runner_stub_launch_error_kept_with_post_source_integrity(bundle, tmp_path, damage):
    output = tmp_path / "run"
    prelude = """
      proc set_param {args} {}
      proc create_project {args} {
        proc pss_create_shared_realtime_xfft_ip {path} {
          file mkdir [file dirname $path]
          set f [open $path w]; puts $f POLICY_ONLY_NOT_VENDOR_IP; close $f
        }
      }
      proc set_property {args} {}
      proc current_project {args} {return POLICY_ONLY}
      proc get_filesets {args} {return POLICY_ONLY}
      proc get_files {args} {return POLICY_ONLY}
      proc add_files {args} {}
      proc close_project {args} {}
      proc launch_simulation {args} {
    """
    if damage:
        prelude += """
        global source_root
        set f [open [file join $source_root tests starlink_oracle native30_budget.py] a]
        puts $f MUTATED_DURING_STUB_LAUNCH; close $f
        """
    prelude += "error POLICY_ONLY_ORIGINAL_LAUNCH_ERROR\n}\n"
    result = probe([output, bundle, sys.executable], prelude)
    (tmp_path / "runner.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 2 and result.stderr.strip() == "POLICY_ONLY_ORIGINAL_LAUNCH_ERROR"
    assert f"integrity_exit={int(damage)}" in (output / "after_integrity.txt").read_text()
    assert "POLICY_ONLY_ORIGINAL_LAUNCH_ERROR" in (output / "run_status.txt").read_text()
    assert not (output / "terminal_receipt.json").exists()


@pytest.mark.parametrize("name", ["native_all_raw_tuples.json", "native_expected_packet.mem", "pilot_expected_ci16.mem",
                                 "pilot_expected_index_u64.mem", "pilot_expected.ci16"])
def test_actual_expected_oracle_cannot_be_replaced_by_self_consistent_copy(bundle, tmp_path, name):
    d = tmp_path / "PARSER_ONLY"
    specimen(d, "late447")
    assert verify_simulation(bundle, d)["outcome"] == "expected-late-rejection"
    path = d / name
    path.write_bytes(path.read_bytes() + b"1")
    with pytest.raises(ValueError, match="oracle differs"):
        verify_simulation(bundle, d)

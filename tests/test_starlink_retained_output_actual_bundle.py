"""One-shot preparation/runner admission using Tcl stubs, never Vivado."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from tests.starlink_oracle import retained_output_actual as a
from tests.starlink_oracle import retained_output_actual_bundle as b

BASE_PYTHON = Path('/home/mouse9911/.local/share/uv/python/cpython-3.11.16-linux-x86_64-gnu/bin/python3.11')


@pytest.mark.parametrize("mutation", ["none", "missing_property", "wildcard_scope", "wrong_language", "omit_bench", "generated_in_list"])
def test_exact_language_selection_fragment(tmp_path, mutation):
    """Execute only the frozen runner's compile-plan fragment using Tcl stubs."""
    runner = (a.ROOT / b.RUNNER).read_text()
    begin = "  foreach name $compiled_names {\n"
    end = "  foreach name $vector_names {"
    assert runner.count(begin) == runner.count(end) == 1
    fragment = runner[runner.index(begin):runner.index(end)]
    property_line = "    set_property file_type SystemVerilog [get_files -of_objects [get_filesets sim_1] $compiled_file]\n"
    assert fragment.count(property_line) == 1
    names = ["runtime.v", "witness.sv", "bench.sv"]
    if mutation == "missing_property":
        fragment = fragment.replace(property_line, "")
    elif mutation == "wildcard_scope":
        fragment = fragment.replace("[get_files -of_objects [get_filesets sim_1] $compiled_file]", "[get_files *]")
    elif mutation == "wrong_language":
        fragment = fragment.replace("file_type SystemVerilog", "file_type Verilog")
    elif mutation == "omit_bench":
        names.pop()
    elif mutation == "generated_in_list":
        names.append("generated_fft.vhd")
    script = tmp_path / "language_fragment.tcl"
    script.write_text('''# OFFLINE COMPILE-PLAN STUB; NO VIVADO OR COMPILATION.
set inputs /frozen/inputs
set sv_files {}
proc add_files args {}
proc get_filesets args {return sim_1}
proc get_files args {return [lindex $args end]}
proc set_property {name value selected} {
  global sv_files
  if {$name ne "file_type" || $value ne "SystemVerilog" || [file extension $selected] ni {.v .sv}} {error WRONG_LANGUAGE_OR_SCOPE}
  lappend sv_files $selected
}
set compiled_names {''' + " ".join(names) + "}\n" + fragment + '''
if {$sv_files ne {/frozen/inputs/runtime.v /frozen/inputs/witness.sv /frozen/inputs/bench.sv}} {error COMPILE_PLAN_INVENTORY}
puts OFFLINE_EXACT_LANGUAGE_FRAGMENT_PASS
''')
    run = subprocess.run(["tclsh", str(script)], capture_output=True, text=True, timeout=10)
    (tmp_path / "fragment.log").write_text(run.stdout + run.stderr)
    assert (run.returncode == 0) == (mutation == "none"), run.stdout + run.stderr
    if mutation == "none":
        assert run.stdout.strip() == "OFFLINE_EXACT_LANGUAGE_FRAGMENT_PASS"


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    p = tmp_path_factory.mktemp("retained_actual_bundle") / "bundle"
    result = b.prepare(p)
    assert result["actual_execution"] is False
    return p, result["manifest_sha256"]


def test_exact_bundle_source_closure(prepared):
    path, expected = prepared
    result = b.verify(path, expected, live=True)
    assert result["sources"] == 80
    assert result["files"] == 83
    manifest = json.loads((path / "manifest.json").read_text())
    assert manifest['kind'] == 'retained-output-actual-v2-causal-frame'
    assert len(manifest["vectors"]) == 8
    assert not any("scripted_fft_ports" in p for p in manifest["compiled"])
    assert (path / "bench.sv").read_text() == a.actual_bench()


def test_no_overwrite_or_implicit_staging(prepared, tmp_path):
    path, expected = prepared
    with pytest.raises(ValueError, match="overwrite"):
        b.prepare(path)
    with pytest.raises(ValueError, match="flag"):
        b.stage(path, tmp_path / "run", expected)
    out = tmp_path / "run"
    b.stage(path, out, expected, authorize=True)
    with pytest.raises(ValueError, match="restart"):
        b.stage(path, out, expected, authorize=True)
    assert b.after(path, out, expected)["copied"]["manifest_sha256"] == expected
    with pytest.raises(ValueError, match="overwrite"):
        b.after(path, out, expected)


@pytest.mark.parametrize("kind", ["sha", "missing", "extra", "source", "recipe", "abi", "profile", "bench", "link", "float_length", "legacy_kind"])
def test_bundle_mutants(prepared, tmp_path, kind):
    source, digest = prepared
    p = tmp_path / "bundle"
    shutil.copytree(source, p)
    if kind == "sha":
        digest = "0"*64
    elif kind == "missing":
        (p / "profile.tcl").unlink()
    elif kind == "extra":
        (p / "undeclared.txt").write_text("extra")
    elif kind == "link":
        (p / "alias").symlink_to(p / "bench.sv")
    elif kind in ("float_length", "legacy_kind"):
        m = json.loads((p / "manifest.json").read_text())
        if kind == "float_length":
            key = next(iter(m["files"]))
            m["files"][key]["bytes"] = float(m["files"][key]["bytes"])
        else:
            m['kind'] = 'retained-output-actual-v1'
        (p / "manifest.json").write_bytes(b.encoded(m))
        digest = a.sha(p / "manifest.json")
    else:
        name = {"source": "source_snapshot/" + b.EXTRAS[0], "recipe": "source_snapshot/tests/starlink_oracle/retained_output_actual_recipe.json",
                "abi": "source_snapshot/tests/starlink_oracle/retained_output_actual_abi.json", "profile": "profile.tcl", "bench": "bench.sv"}[kind]
        target = p / name
        target.write_bytes(target.read_bytes() + b"\nMUTATED\n")
    with pytest.raises(ValueError):
        b.verify(p, digest)


def test_canonical_boolean_integer_alias_is_not_equal():
    assert b.encoded({"bytes": False}) != b.encoded({"bytes": 0})
    assert b.encoded({"bytes": 1.0}) != b.encoded({"bytes": 1})


def test_source_signature_must_join_snapshot(prepared, tmp_path):
    source, _ = prepared
    p = tmp_path / "bundle";shutil.copytree(source, p)
    m = json.loads((p / "manifest.json").read_text())
    first = next(iter(m["sources"]))
    m["sources"][first] = {"sha256": "0"*64, "bytes": 1}
    m["source_signature"] = hashlib.sha256(b.encoded(m["sources"])).hexdigest()
    (p / "manifest.json").write_bytes(b.encoded(m))
    with pytest.raises(ValueError, match="joined"):
        b.verify(p, a.sha(p / "manifest.json"))


@pytest.mark.parametrize("kind", ["parent", "link"])
def test_unsafe_output_paths(prepared, tmp_path, kind):
    path, expected = prepared
    if kind == "parent":
        bad = tmp_path / "not-used/../run"
    else:
        (tmp_path / "alias").symlink_to(tmp_path, target_is_directory=True)
        bad = tmp_path / "alias/run"
    with pytest.raises(ValueError):
        b.stage(path, bad, expected, authorize=True)


def test_base_stdlib_cli_from_root(prepared):
    path, expected = prepared
    cli = path / "source_snapshot/tools/prepare_starlink_retained_output_actual.py"
    assert BASE_PYTHON.is_file() and not BASE_PYTHON.is_symlink()
    env = os.environ.copy()
    for key in ("PYTHONHOME", "PYTHONPATH", "PYTHONOPTIMIZE", "LD_LIBRARY_PATH"):
        env.pop(key, None)
    run = subprocess.run([str(BASE_PYTHON), "-B", str(cli), "verify", str(path), "--expected", expected], cwd="/", env=env, capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stdout+run.stderr
    assert json.loads(run.stdout)["manifest_sha256"] == expected


def test_optimized_standalone_cli_rejects(prepared):
    path, expected = prepared
    cli = path / "source_snapshot/tools/prepare_starlink_retained_output_actual.py"
    env = os.environ.copy()
    for key in ("PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH"):
        env.pop(key, None)
    env["PYTHONOPTIMIZE"] = "1"
    run = subprocess.run([str(BASE_PYTHON), "-B", str(cli), "verify", str(path), "--expected", expected],
                         cwd="/", env=env, capture_output=True, text=True, timeout=30)
    assert run.returncode != 0 and "unoptimized frozen interpreter required" in run.stderr


@pytest.mark.parametrize("stage", ["create", "launch", "launch_mutation"])
def test_runner_stubs_preserve_failure_and_after_integrity(prepared, tmp_path, stage):
    bundle, expected = prepared
    runner = bundle / "source_snapshot" / b.RUNNER
    output = tmp_path / "actual_not_executed"
    factory = (a.REF / "create_shared_realtime_xfft_ip.tcl").read_text()
    generics = re.search(r"set required_generics \{(.*?)\n  \}", factory, re.S).group(1)
    mutation = f'set f [open {{{output}/inputs/bench.sv}} a];puts $f MUTATED;close $f;' if stage == "launch_mutation" else ""
    script = tmp_path / "offline_stubs.tcl"
    manifest = json.loads((bundle / "manifest.json").read_text())
    expected_sv = [str(output / "inputs" / name) for name in manifest["compiled"] + ["bench.sv"]]
    expected_sv_tcl = " ".join("{" + name + "}" for name in expected_sv)
    language_receipt = tmp_path / "offline_language_selection.txt"
    script.write_text(f'''# OFFLINE TCL STUBS: NO VIVADO/FFT/IP EXECUTION.
proc version args {{return 2022.2}}
proc set_param {{name value}} {{if {{$name ne "general.maxThreads" || $value != 2}} {{error THREADS}}}}
proc create_project args {{ {'error EXPECTED_OFFLINE_CREATE_FAILURE' if stage == 'create' else 'return'} }}
set sv_files {{}}
set added_files {{}}
proc set_property args {{
  global sv_files added_files
  if {{[lindex $args 0] eq "file_type" && [lindex $args 1] eq "SystemVerilog"}} {{
    set selected [lindex $args 2]
    if {{$selected ni $added_files || [file extension $selected] ni {{.v .sv}}}} {{error BAD_LANGUAGE_SELECTION}}
    lappend sv_files $selected
  }}
}}
proc current_project args {{return OFFLINE}}
set created 0
proc get_ips args {{global created;if {{$created}} {{return OFFLINE}};return {{}}}}
proc create_ip args {{global created;set created 1}}
proc generate_target args {{
  upvar 1 wrapper_path wrapper
  file mkdir [file dirname $wrapper]
  set f [open $wrapper {{WRONLY CREAT EXCL}}]
  puts $f "ENTITY starlink_pss_fft512_bfp18_rt_candidate IS"
  puts $f "END starlink_pss_fft512_bfp18_rt_candidate;"
  foreach {{key value}} {{{generics}}} {{puts $f "$key => $value,"}}
  close $f
}}
proc add_files args {{global added_files;lappend added_files [lindex $args end]}}
proc get_filesets args {{return OFFLINE}}
proc get_files args {{return [lindex $args end]}}
proc launch_simulation args {{
  global sv_files
  if {{$sv_files ne [list {expected_sv_tcl}]}} {{error INCOMPLETE_OR_EXCESS_LANGUAGE_SELECTION}}
  set f [open {{{language_receipt}}} {{WRONLY CREAT EXCL}}]
  puts $f "OFFLINE_STUB_EXACT_SYSTEMVERILOG_COMPILE_PLAN_NOT_VENDOR"
  foreach name $sv_files {{puts $f $name}}
  close $f
  {mutation}error EXPECTED_OFFLINE_LAUNCH_FAILURE
}}
set argc 4
set argv [list {{{bundle}}} {{{BASE_PYTHON}}} {expected} {{{output}}}]
source {{{runner}}}
''')
    env = os.environ.copy()
    env.update(PYTHONHOME="/deliberately-missing-home", PYTHONPATH="/deliberately-missing-path", PYTHONOPTIMIZE="2", LD_LIBRARY_PATH="/deliberately-missing-libraries")
    run = subprocess.run(["tclsh", str(script)], env=env, capture_output=True, text=True, timeout=30)
    (tmp_path / "stub.log").write_text(run.stdout+run.stderr)
    assert run.returncode != 0
    assert "EXPECTED_OFFLINE_" in run.stderr
    outcome = (output / "run_outcome.txt").read_text()
    assert "run_status=1" in outcome
    assert f"after_status={1 if stage == 'launch_mutation' else 0}" in outcome
    assert "ip_status=0" in outcome
    assert (output / "before.json").is_file()
    assert not (output / "results.json").exists()
    assert (output / "generated_ip_after.txt").is_file()
    if stage != "create":
        assert (output / "generated_ip_before.txt").read_bytes() == (output / "generated_ip_after.txt").read_bytes()
        assert language_receipt.read_text().splitlines() == ["OFFLINE_STUB_EXACT_SYSTEMVERILOG_COMPILE_PLAN_NOT_VENDOR", *expected_sv]
        assert len(expected_sv) == len(set(expected_sv)) == 27
        assert all(Path(name).suffix in (".v", ".sv") for name in expected_sv)
    else:
        assert not language_receipt.exists()
    if stage != "launch_mutation":
        assert (output / "after.json").is_file()


@pytest.mark.parametrize("fault", ["wrong_runner", "wrong_version", "symlink_python", "wrong_python"])
def test_runner_early_admission_rejects(prepared, tmp_path, fault):
    bundle, expected = prepared
    runner = bundle / "source_snapshot" / b.RUNNER
    python = BASE_PYTHON
    version = "2022.2"
    if fault == "wrong_runner":
        copied = tmp_path / "runner.tcl";shutil.copyfile(runner, copied);runner = copied
    elif fault == "wrong_version":
        version = "2023.1"
    elif fault == "wrong_python":
        python = Path("/usr/bin/true")
    else:
        python = tmp_path / "python";python.symlink_to(BASE_PYTHON)
    output = tmp_path / "absent"
    driver = tmp_path / "driver.tcl"
    driver.write_text(f'proc version args {{return {version}}}\nset argc 4\nset argv [list {{{bundle}}} {{{python}}} {expected} {{{output}}}]\nsource {{{runner}}}\n')
    run = subprocess.run(["tclsh", str(driver)], capture_output=True, text=True, timeout=30)
    assert run.returncode != 0 and not output.exists()

"""Bundle/runner policy only. Tcl stubs never call Vivado or an FFT model."""

import json
import os
import shutil
import subprocess
import sys

import pytest

from tests.starlink_oracle.high_rate60_bundle import (
    ADDITIVE,
    CLI,
    ROOT,
    RUNNER,
    TOP,
    base_pins,
    freeze,
    inventory,
    verify_bundle,
)
from tests.starlink_oracle.native60_budget import COHORT, encoded, sha


@pytest.fixture(scope="session")
def bundle(tmp_path_factory):
    p = tmp_path_factory.mktemp("paired60_offline_bundle")/"bundle"
    freeze(COHORT,p)
    return p


def test_exact_bundle_source_import_closure_original69_and_native91(bundle):
    r = verify_bundle(bundle,sha((bundle/"bundle.json").read_bytes()))
    assert r["actual_execution"] is False
    assert set(base_pins(ROOT)) | set(ADDITIVE) <= r["source_sha256"].keys()
    assert set(r["python_import_edges"]) <= r["source_sha256"].keys()
    assert {"tests/starlink_oracle/native60_budget.py", "tests/test_starlink_native60_budget.py",
            "tests/starlink_oracle/high_rate60_harness_result.py"} <= r["python_import_edges"].keys()
    for name,digest in r["source_sha256"].items():
        assert r["files"]["source_snapshot/"+name] == digest == sha((ROOT/name).read_bytes())
    with pytest.raises(ValueError,match="overwrite"):
        freeze(COHORT,bundle)


@pytest.mark.parametrize("name", ["cohort/source_ci16.mem", "cohort/native_raw_power_u96.mem",
    "vectors/paired_source_ci16.mem", "vectors/paired_source_index_u64.mem", "vectors/harness.json",
    "source_snapshot/"+TOP, "source_snapshot/"+RUNNER, "source_snapshot/"+CLI,
    "source_snapshot/hdl/library/axi_starlink_pss_acquisition/axi_starlink_pss_acquisition.v",
    "source_snapshot/tests/starlink_oracle/native60_budget.py"])
def test_mutable_source_numerical_bundle_rejected(bundle,tmp_path,name):
    output=tmp_path/"mutant"
    shutil.copytree(bundle,output)
    p=output/name
    p.write_bytes(p.read_bytes()+b"\n")
    with pytest.raises(ValueError):
        verify_bundle(output)


@pytest.mark.parametrize("kind", ["disconnected", "omit", "imports", "profile", "actual", "recipe_bool", "symlink", "extra", "native_pin_lie"])
def test_manifest_self_consistency_not_admission(bundle,tmp_path,kind):
    output=tmp_path/"mutant"
    shutil.copytree(bundle,output)
    p=output/"bundle.json"
    r=json.loads(p.read_bytes())
    if kind=="disconnected":
        r["source_sha256"][TOP]="0"*64
        r["source_signature"]=sha(encoded(r["source_sha256"]))
    elif kind=="omit":
        r["source_sha256"].pop(TOP)
        r["source_signature"]=sha(encoded(r["source_sha256"]))
    elif kind=="imports":
        r["python_import_edges"].pop("tests/starlink_oracle/native60_budget.py")
    elif kind=="profile":
        r["profile"]="30-upper-bank175-native132-pil1"
    elif kind=="actual":
        r["actual_execution"]=True
    elif kind=="recipe_bool":
        r["recipe"]["added_tail_count"]=False
    elif kind=="symlink":
        (output/"link").symlink_to("vectors")
    elif kind=="extra":
        (output/"extra").write_text("not admitted")
    else:
        name="tests/starlink_oracle/high_rate60_native_source_pins.json"
        pinfile=output/"source_snapshot"/name
        pins=json.loads(pinfile.read_bytes())
        key="hdl/library/starlink_pss_acquisition/starlink_pss_spectrum_product.v"
        altered=output/"source_snapshot"/key
        altered.write_bytes(altered.read_bytes()+b"\n")
        pins["source_sha256"][key]=sha(altered.read_bytes())
        pinfile.write_bytes(encoded(pins))
        r["source_sha256"][key]=sha(altered.read_bytes())
        r["source_sha256"][name]=sha(pinfile.read_bytes())
        r["source_signature"]=sha(encoded(r["source_sha256"]))
        r["files"]=inventory(output)
        r["files"].pop("bundle.json")
    p.write_bytes(encoded(r))
    with pytest.raises(ValueError):
        verify_bundle(output)


def run_stub(tmp_path,bundle,mode="create_fail",extra=(),runner=None,contaminated=False,expected=None):
    """An explicit Tcl command stub, NOT a Vivado process or simulator receipt."""
    runner=runner or ROOT/RUNNER
    output=tmp_path/"run"
    digest=expected or sha((bundle/"bundle.json").read_bytes())
    stub=tmp_path/"OFFLINE_TCL_STUB.tcl"
    stub.write_text('''proc version {args} {return "2022.2"}
proc set_param {name value} {
  if {$name ne "general.maxThreads" || $value != 2} {error "wrong thread policy"}
  set ::threads_checked 1
}
proc create_project {args} {
  if {$::threads_checked != 1} {error "threads not constrained before project"}
  if {$::stub_mode eq "mutate_fail"} {
    set p [file join $::source_root hdl library starlink_pss_acquisition starlink_pss_spectrum_product.v]
    set f [open $p a]; puts $f "// OFFLINE_STUB_SOURCE_MUTATION"; close $f
  }
  if {$::stub_mode ne "launch_fail"} {error "OFFLINE_CREATE_STUB_FAILURE_NO_VENDOR"}
  proc pss_create_shared_realtime_xfft_ip {path} {
    file mkdir [file dirname $path]
    set f [open $path w]; puts $f "OFFLINE_STUB_NOT_VENDOR_IP"; close $f
  }
}
proc current_project {} {return offline_stub}
proc set_property {args} {}
proc add_files {args} {}
proc get_filesets {args} {return sim_1}
proc get_files {args} {return offline_memory}
proc launch_simulation {args} {error "OFFLINE_LAUNCH_STUB_FAILURE_NO_SIMULATION"}
proc close_project {} {}
set threads_checked 0
set stub_mode [lindex $argv 0]
set runner [lindex $argv 1]
set argv [lrange $argv 2 end]
set argc [llength $argv]
if {[catch {source $runner} message options]} {
  puts stderr $message
  exit 1
}
error "OFFLINE_STUB_MUST_NOT_REACH_ACTUAL_SUCCESS"
''')
    command=["tclsh",str(stub),mode,str(runner),str(output),str(bundle),sys.executable,digest,*extra]
    env=os.environ.copy()
    if contaminated:
        env.update(PYTHONHOME="/invalid/offline-python-home",PYTHONPATH="/invalid/offline-python-path",LD_LIBRARY_PATH="/invalid/offline-library-path")
    r=subprocess.run(command,capture_output=True,text=True,timeout=30,check=False,env=env)
    (tmp_path/"offline-stub.log").write_text(r.stdout+r.stderr)
    (tmp_path/"offline-stub-status.json").write_bytes(encoded({"command":command,"exit":r.returncode,
        "actual_vendor":False,"actual_simulation":False,"synthetic_policy_only":True}))
    return r,output


@pytest.mark.parametrize("mode", ["create_fail","launch_fail","mutate_fail"])
def test_failure_retains_original_and_after_integrity_never_terminal(tmp_path,bundle,mode):
    before=inventory(bundle)
    r,output=run_stub(tmp_path,bundle,mode)
    assert r.returncode==1
    assert "OFFLINE_" in r.stderr and "STUB_FAILURE" in r.stderr
    assert (output/"before_integrity.txt").is_file()
    after=(output/"after_integrity.txt").read_text()
    assert f"integrity_exit={int(mode=='mutate_fail')}" in after
    assert "run_tcl_exit=1" in (output/"run_status.txt").read_text()
    assert not (output/"terminal_receipt.json").exists()
    assert inventory(bundle)==before


def test_subprocess_environment_sanitized_without_touching_parent(tmp_path,bundle):
    r,output=run_stub(tmp_path,bundle,contaminated=True)
    assert r.returncode==1 and "OFFLINE_CREATE_STUB_FAILURE_NO_VENDOR" in r.stderr
    assert "integrity_exit=0" in (output/"after_integrity.txt").read_text()


@pytest.mark.parametrize("kind",["extra_rate","wrong_sha","existing","runner_mismatch","source_mutation"])
def test_runner_admission_before_project(tmp_path,bundle,kind):
    extra=()
    runner=None
    expected=None
    target=bundle
    if kind=="extra_rate":
        extra=("30",)
    elif kind=="wrong_sha":
        expected="0"*64
    elif kind=="existing":
        (tmp_path/"run").mkdir()
        (tmp_path/"run/keep").write_text("unchanged")
    elif kind=="runner_mismatch":
        runner=tmp_path/"runner.tcl"
        runner.write_bytes((ROOT/RUNNER).read_bytes()+b"\n")
    else:
        target=tmp_path/"mutated_bundle"
        shutil.copytree(bundle,target)
        p=target/"source_snapshot"/TOP
        p.write_bytes(p.read_bytes()+b"\n")
    r,output=run_stub(tmp_path,target,extra=extra,runner=runner,expected=expected)
    assert r.returncode==1 and "OFFLINE_CREATE_STUB" not in r.stderr
    assert not (output/"before_integrity.txt").exists()
    if kind=="existing":
        assert (output/"keep").read_text()=="unchanged"

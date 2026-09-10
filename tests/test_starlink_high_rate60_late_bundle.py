"""Late bundle/runner admission: Tcl stubs only, never vendor or service."""

import json
import shutil

import pytest

from tests.starlink_oracle.high_rate60_bundle import inventory
from tests.starlink_oracle.high_rate60_late import ROOT, TOP, verify_results
from tests.starlink_oracle.high_rate60_late_bundle import (
    ADDITIVE,
    freeze,
    verify_bundle,
)
from tests.starlink_oracle.native60_budget import encoded, sha
from tests.test_starlink_high_rate60_bundle import run_stub
from tests.test_starlink_high_rate60_late_result import late_specimen

HEALTHY=ROOT/"build/high-rate60-harness-prelaunch-v1"
ENTRY="case/simulate_high_rate60_bank_native_late.tcl"


@pytest.fixture(scope="session")
def bundle(tmp_path_factory):
    p=tmp_path_factory.mktemp("late60_bundle")/"bundle"
    freeze(HEALTHY,p)
    return p


def test_exact_healthy108_69_and_additive_source_import_closure(bundle,tmp_path):
    r=verify_bundle(bundle,sha((bundle/"bundle.json").read_bytes()))
    healthy=json.loads((HEALTHY/"bundle.json").read_bytes())
    assert set(ADDITIVE) <= r["source_sha256"].keys()
    assert {n:r["source_sha256"][n] for n in healthy["source_sha256"]} == healthy["source_sha256"]
    assert inventory(bundle/"healthy") == inventory(HEALTHY)
    assert "tests/test_starlink_high_rate60_harness_result.py" in r["python_import_edges"]
    assert "tests/starlink_oracle/high_rate60_late_result.py" in r["python_import_edges"]
    for name,digest in r["source_sha256"].items():
        assert r["files"]["source_snapshot/"+name] == digest == sha((ROOT/name).read_bytes())
    with pytest.raises(ValueError,match="overwrite"): freeze(HEALTHY,bundle)
    specimen=late_specimen(tmp_path/"PARSER_ONLY_NO_SERVICE")
    assert verify_results(specimen,bundle)["result"] == "HIGH_RATE60_LATE_SIMULATION_VERIFIED"


@pytest.mark.parametrize("name",["healthy/cohort/source_ci16.mem","healthy/cohort/conditioned_kernel_q17.mem",
    "healthy/vectors/map_447x2_u16.mem","healthy/vectors/pilot_expected.ci16","healthy/vectors/native_expected_packet.mem",
    "source_snapshot/"+TOP,"source_snapshot/tests/starlink_oracle/high_rate60_harness_result.py",
    "source_snapshot/hdl/library/axi_starlink_pss_acquisition/axi_starlink_pss_acquisition.v",
    "case/native60_late_context.svh","case/tb_starlink_pss_60_bank_native_late.sv",
    "case/high_rate60_late_context.py","case/native60_late_registers.mem",ENTRY])
def test_original_or_derived_source_or_oracle_changed(bundle,tmp_path,name):
    output=tmp_path/"mutant"; shutil.copytree(bundle,output)
    p=output/name; p.write_bytes(p.read_bytes()+b"\n")
    with pytest.raises(ValueError): verify_bundle(output)


@pytest.mark.parametrize("kind",["disconnected","omit","imports","profile","actual","recipe_float","extra","symlink","self_consistent_inverse"])
def test_self_consistent_inventory_is_not_admission(bundle,tmp_path,kind):
    output=tmp_path/"mutant"; shutil.copytree(bundle,output)
    p=output/"bundle.json"; r=json.loads(p.read_bytes())
    if kind=="disconnected": r["source_sha256"][TOP]="0"*64
    elif kind=="omit": r["source_sha256"].pop(TOP)
    elif kind=="imports": r["python_import_edges"].pop("tests/starlink_oracle/high_rate60_late_result.py")
    elif kind=="profile": r["profile"]="healthy60"
    elif kind=="actual": r["actual_execution"]=True
    elif kind=="recipe_float": r["recipe"]["native_taps"]=264.0
    elif kind=="extra": (output/"extra").write_text("not admitted")
    elif kind=="symlink": (output/"link").symlink_to("healthy")
    else:
        altered=output/"case/tb_starlink_pss_60_bank_native_late.sv"
        altered.write_text(altered.read_text().replace("native_capture_count!=0","native_capture_count!=520"))
        r["files"]=inventory(output); r["files"].pop("bundle.json")
    r["source_signature"]=sha(encoded(r["source_sha256"])); p.write_bytes(encoded(r))
    with pytest.raises(ValueError): verify_bundle(output)


@pytest.mark.parametrize("mode",["create_fail","launch_fail","mutate_fail"])
def test_original_failure_and_post_integrity_retained_no_terminal(bundle,tmp_path,mode):
    before=inventory(bundle)
    run,output=run_stub(tmp_path,bundle,mode,runner=bundle/ENTRY)
    assert run.returncode==1 and "STUB_FAILURE" in run.stderr
    assert f"integrity_exit={int(mode=='mutate_fail')}" in (output/"after_integrity.txt").read_text()
    assert "run_tcl_exit=1" in (output/"run_status.txt").read_text()
    assert not (output/"terminal_receipt.json").exists()
    assert before==inventory(bundle)


def test_child_environment_only_sanitized(bundle,tmp_path):
    run,output=run_stub(tmp_path,bundle,runner=bundle/ENTRY,contaminated=True)
    assert run.returncode==1 and "OFFLINE_CREATE_STUB_FAILURE_NO_VENDOR" in run.stderr
    assert "integrity_exit=0" in (output/"after_integrity.txt").read_text()


@pytest.mark.parametrize("kind",["alternate_rate","wrong_sha","existing","runner_mismatch","source_mutation"])
def test_runner_admission_before_project(bundle,tmp_path,kind):
    target=bundle; runner=bundle/ENTRY; expected=None; extra=()
    if kind=="alternate_rate": extra=("30",)
    elif kind=="wrong_sha": expected="0"*64
    elif kind=="existing":
        (tmp_path/"run").mkdir(); (tmp_path/"run/keep").write_text("unchanged")
    elif kind=="runner_mismatch":
        runner=tmp_path/"runner.tcl"; runner.write_bytes((bundle/ENTRY).read_bytes()+b"\n")
    else:
        target=tmp_path/"mutant"; shutil.copytree(bundle,target)
        p=target/"source_snapshot"/TOP; p.write_bytes(p.read_bytes()+b"\n")
    run,output=run_stub(tmp_path,target,runner=runner,expected=expected,extra=extra)
    assert run.returncode==1 and "OFFLINE_CREATE_STUB" not in run.stderr
    assert not (output/"before_integrity.txt").exists()
    if kind=="existing": assert (output/"keep").read_text()=="unchanged"


def test_source_parent_symlink_cannot_write_or_overwrite(tmp_path):
    real=tmp_path/"protected"; real.mkdir(); (tmp_path/"alias").symlink_to(real,target_is_directory=True)
    with pytest.raises(ValueError,match="symlink"): freeze(HEALTHY,tmp_path/"alias/bundle")
    assert not list(real.iterdir())

"""Late60 offline contract/strict-inverse/compile-only tests. No service run."""

import json
import shutil
import subprocess

import pytest

from tests.starlink_oracle.high_rate60_late import (
    LOGIC,
    NATIVE,
    PARSER,
    ROOT,
    RUNNER,
    TB,
    TOP,
    adapted_sources,
    check_recipe,
    inverse,
    registers,
)
from tests.starlink_oracle.high_rate60_late_bundle import check_logic
from tests.starlink_oracle.native60_budget import encoded, sha
from tests.test_starlink_high_rate60_harness import INERT_FFT

HEALTHY = ROOT/"build/high-rate60-harness-prelaunch-v1"


def receipt():
    return json.loads((HEALTHY/"bundle.json").read_bytes())


def test_frozen_recipe_bounds_signed_lead_register_abi():
    r = check_recipe()
    assert r["command_derived_control_cycles"] == 8*24+8+32 == 232
    assert r["command_raw_window_width"]*100 >= r["command_limit_control_cycles"]*60
    assert r["command_signed_lead_closed"] == [-193,-33]
    assert dict(registers())[0x8c] == dict(registers())[0x90] == 1
    assert dict(registers())[0x60] == 1073758594 and 0x54 not in dict(registers())


@pytest.mark.parametrize("key",list(check_recipe()))
def test_recipe_every_field_frozen(key):
    r=check_recipe(); r[key]="MUTATED"
    with pytest.raises(ValueError):
        check_recipe(r)


@pytest.mark.parametrize("key",[k for k,v in check_recipe().items() if type(v) is int])
def test_recipe_type_alias_rejected(key):
    r=check_recipe(); r[key]=float(r[key])
    with pytest.raises(ValueError):
        check_recipe(r)


def test_complete_source_inverse_and_unchanged_healthy108():
    healthy=receipt()
    derived=adapted_sources(ROOT,healthy)
    inverses=json.loads(derived["inverse.json"])
    for target,r in inverses.items():
        assert inverse(derived[target],r) == (ROOT/r["original_path"]).read_text()
    assert {r["original_path"] for r in inverses.values()} == {TOP,NATIVE,PARSER,RUNNER}
    for name,digest in healthy["source_sha256"].items():
        assert sha((ROOT/name).read_bytes()) == digest
    top=derived["tb_starlink_pss_60_bank_native_late.sv"]
    assert 'wire native_done=late_observation_done;' in top
    assert 'native_released!==0' in top and 'native_packet_reads!=0' in top
    assert 'capture=0 busy=0' in top and 'capture=520 busy=1' not in top
    assert 'capture_actual_fft=%0d' in top and 'fft_after_reject=%0d' in top
    assert 'wait(native_drain_cycle>=0)' not in top
    assert 'write_reg(2, 8\'h58' not in derived['native60_late_context.svh']


@pytest.mark.parametrize("target",["tb_starlink_pss_60_bank_native_late.sv","native60_late_context.svh",
    "high_rate60_late_context.py","simulate_high_rate60_bank_native_late.tcl"])
@pytest.mark.parametrize("kind",["append","edit","missing"])
def test_any_derived_source_mutation_fails_complete_inverse(target,kind):
    out=adapted_sources(ROOT,receipt()); r=json.loads(out["inverse.json"])[target]; text=out[target]
    text={"append":text+"\n","edit":"M"+text[1:],"missing":text[:-1]}[kind]
    with pytest.raises(ValueError):
        inverse(text,r)


@pytest.mark.parametrize("name",[TOP,NATIVE,PARSER,RUNNER])
def test_healthy_parent_mutation_rejected_before_derivation(tmp_path,name):
    for path in [TOP,NATIVE,PARSER,RUNNER]:
        p=tmp_path/path; p.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(ROOT/path,p)
    p=tmp_path/name; p.write_bytes(p.read_bytes()+b"\n")
    with pytest.raises(ValueError,match="healthy original changed"):
        adapted_sources(tmp_path,receipt())


@pytest.mark.parametrize("before",["STATE_COEFFICIENT_COPY_FINISH","native_engine_idle!==1",
    "native.result_word_read,native.result_release","native.rejected_count!==late_handshakes",
    "cycles-native_trigger_cycle>256","cycles-begin_cycle>512","cycles-begin_cycle>1328",
    "cycles-source_off_cycle>2048","late_register_reads!=62","continuous_source}!==3'b111",
    "core_input_ready===1'b1","next_inverse===1'b0","pilot.ddc.accept===1'b1"])
def test_clock_state_capture_rejection_monitor_source_mutants(tmp_path,before):
    p=tmp_path/LOGIC; p.parent.mkdir(parents=True); p.write_text((ROOT/LOGIC).read_text().replace(before,"MUTATED",1))
    with pytest.raises(ValueError):
        check_logic(tmp_path)


def test_late_whole_composition_compile_only_never_vvp(tmp_path):
    healthy=receipt(); derived=adapted_sources(ROOT,healthy)
    snapshot=tmp_path/"source_snapshot"
    names=[name for name in healthy["source_sha256"] if name.endswith((".v",".svh"))]
    for name in [*names,LOGIC]:
        p=snapshot/name; p.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(ROOT/name,p)
    case=tmp_path/"case"; case.mkdir()
    for name,text in derived.items():
        (case/name).write_text(text)
    stub=snapshot/"inert_fft.v"; stub.write_text(INERT_FFT)
    files=lambda: {str(p.relative_to(tmp_path)):sha(p.read_bytes()) for base in [snapshot,case]
                   for p in base.rglob("*") if p.is_file()}
    before=files(); (tmp_path/"source-before.json").write_bytes(encoded(before))
    command=["iverilog","-g2012","-Wall","-I",str(case),"-I",str(snapshot/TB),"-s","tb_starlink_pss_60_bank_native_late",
             "-o",str(tmp_path/"compile-only.vvp"),*[str(snapshot/n) for n in names if n.endswith(".v")],
             str(case/"tb_starlink_pss_60_bank_native_late.sv"),str(stub)]
    run=subprocess.run(command,capture_output=True,text=True,timeout=60,check=False)
    (tmp_path/"compile.log").write_text(run.stdout+run.stderr)
    after=files(); (tmp_path/"source-after.json").write_bytes(encoded(after))
    (tmp_path/"compile-status.json").write_bytes(encoded({"command":command,"exit":run.returncode,
        "diagnostics":len((run.stdout+run.stderr).splitlines()),"vvp_invoked":False,"service_executed":False}))
    assert before == after
    assert run.returncode == 0,run.stdout+run.stderr
    assert not (tmp_path/"simulate.log").exists()

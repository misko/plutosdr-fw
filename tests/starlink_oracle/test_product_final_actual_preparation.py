"""Offline actual-harness admission and observer witnesses, NOT vendor proof."""
import hashlib
import json
import re
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.test_exact_control import STUB

ROOT = Path(__file__).resolve().parents[2]
ACQ = ROOT / "hdl/library/starlink_pss_acquisition"
HELPER = ACQ / "prepare_product_final_fence_actual.py"
H = runpy.run_path(str(HELPER))
ORIGINAL = Path("/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/rom-relocated-actual-v2.CWJkzwEi/rom-actual-prepared-v1")


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    target = tmp_path_factory.mktemp("product-final-preparation") / "prepared"
    assert H["prepare"](ORIGINAL, target) == dict(H["SETTINGS"], PRODUCER_LOCAL_FINAL_FENCE=1)
    return target


def copy_prepared(prepared, tmp_path):
    return Path(shutil.copytree(prepared, tmp_path / "copy"))


def rehash(path):
    meta = json.loads((path / "fence-preparation.json").read_text())
    meta["source_sha256"] = {p.name: H["sha"](p) for p in (path / "frozen_sources").iterdir()}
    (path / "fence-preparation.json").write_text(json.dumps(meta))
    files = sorted(p for p in path.rglob("*") if p.is_file() and p != path / "SHA256SUMS")
    (path / "SHA256SUMS").write_text("".join(f"{H['sha'](p)}  {p.relative_to(path)}\n" for p in files))


def test_full_inherited_bytes_stimulus_observers_and_runtime_inverse(prepared):
    source = prepared / "frozen_sources"
    for name, pairs in ((H["TOP"], H["BENCH_EDITS"]), (H["RUNNER"], H["RUNNER_EDITS"])):
        assert H["edits"]((source / name).read_text(), pairs, True).encode() == (ORIGINAL / "frozen_sources" / name).read_bytes()
    original = json.loads((ORIGINAL / "preparation.json").read_text())
    assert (prepared / "preparation.json").read_bytes() == (ORIGINAL / "preparation.json").read_bytes()
    for name in original["source_sha256"]:
        if name not in (H["TOP"], H["RUNNER"]):
            assert (source / name).read_bytes() == (ORIGINAL / "frozen_sources" / name).read_bytes()
    for name, record in json.loads((source / H["RECIPE"]).read_text())["modules"].items():
        assert H["edits"]((source / (name + ".v")).read_text(), record["edits"], True) == (source / (record["original"] + ".v")).read_text()


def test_exact_217_product_constituents_and_only_status_exception(prepared):
    source = prepared / "frozen_sources"
    original = runpy.run_path(str(source / "prepare_exact_control_actual.py"))
    fields = original["FIELDS"]
    assert len(fields) == len(set(fields)) == 217
    bank = [f for f in fields if f.startswith("dut.product_bank.")]
    assert bank == ["dut.product_bank." + f for f in (
        "request_toggle", "acknowledge_toggle", "request_sync", "acknowledge_sync",
        "metadata_in_hold", "metadata_out_hold", "write_position", "reading", "read_all_loaded",
        "read_address", "read_output_position", "read_payload", "read_valid", "input_ready",
        "input_fault", "input_framing_fault_now", "output_valid", "output_ready")]
    wrapper = [f for f in fields if f.startswith("dut.product_bank_")]
    assert wrapper == ["dut.product_bank_" + f for f in (
        "valid", "read_ready", "data", "position", "last", "metadata", "ready", "fault", "framing_fault_now")]
    text = (source / H["TOP"]).read_text()
    body = re.search(r"wire exact_other_public_equal = \(\{(.*?)\} ===", text, re.DOTALL)[1]
    assert [x.strip() for x in body.split(",")] == [f for f in fields if f != "dut.core_status_data"]
    assert "wire exact_status_payload_equal = exact_both_status_invalid ||\n    (dut.core_status_data === exact_reference.dut.core_status_data);" in text
    assert "wire exact_protocol_equal = exact_other_public_equal && exact_status_payload_equal;" in text
    assert '.actual_public(exact_protocol_equal), .reference_public(1\'b1)' in text


@pytest.mark.parametrize("name", ["starlink_pss_exact_control_actual_compare.sv",
    "tb_starlink_pss_exact_control_reference.sv", "starlink_pss_fault_cdc_actual_observer.svh",
    "prepare_exact_control_status_qualified.py", "forward_q17.mem", "starlink_pss_block_mailbox.v",
    "starlink_pss_product_fence_mailbox.v", H["OBSERVER"], H["BINDING"], H["RECIPE"]])
def test_rehashed_old_or_new_source_mutations_reject(prepared, tmp_path, name):
    target = copy_prepared(prepared, tmp_path)
    path = target / "frozen_sources" / name
    path.write_text(path.read_text() + "\n// rehashed mutation\n")
    rehash(target)
    with pytest.raises(ValueError):
        H["verify_prepared"](target)


@pytest.mark.parametrize("change", ["missing", "duplicate", "zero_mismatch", "top_binding", "weak_old_observer"])
def test_bindings_and_old_observer_cannot_be_rehashed_away(prepared, tmp_path, change):
    target = copy_prepared(prepared, tmp_path)
    settings = target / "settings.tcl"
    top = target / "frozen_sources" / H["TOP"]
    if change == "missing":
        settings.write_text(settings.read_text().replace(" PRODUCER_LOCAL_FINAL_FENCE=1", ""))
    elif change == "duplicate":
        settings.write_text(settings.read_text().replace("PRODUCER_LOCAL_FINAL_FENCE=1", "REGISTERED_SCHEDULING=1"))
    elif change == "zero_mismatch":
        settings.write_text(settings.read_text().replace("PRODUCER_LOCAL_FINAL_FENCE=1", "PRODUCER_LOCAL_FINAL_FENCE=0"))
    elif change == "top_binding":
        top.write_text(top.read_text().replace(".PRODUCER_LOCAL_FINAL_FENCE(PRODUCER_LOCAL_FINAL_FENCE)", ".PRODUCER_LOCAL_FINAL_FENCE(0)"))
    else:
        top.write_text(top.read_text().replace(".actual_public(exact_protocol_equal)", ".actual_public(1'b1)"))
    rehash(target)
    with pytest.raises(ValueError):
        H["verify_prepared"](target)


def test_no_overwrite_symlink_and_wrong_origin(tmp_path, prepared):
    with pytest.raises(FileExistsError):
        H["prepare"](ORIGINAL, prepared)
    alias = tmp_path / "alias"
    alias.symlink_to(prepared, target_is_directory=True)
    with pytest.raises(ValueError, match="aliased"):
        H["verify_prepared"](alias)
    with pytest.raises(ValueError, match="aliased"):
        H["prepare"](ORIGINAL, alias / "new")
    with pytest.raises(ValueError, match="wrong original inventory"):
        H["verify_origin"](prepared)


@pytest.mark.parametrize("name", ["process-exit.txt", "after-integrity-exit.txt", "after-ip-exit.txt", "receipt-exit.txt"])
def test_failed_or_empty_original_status_cannot_admit(tmp_path, name):
    original = tmp_path / "rom-actual-prepared-v1"
    original.mkdir()
    for relative in H["inventory"](ORIGINAL, H["ORIGIN_INVENTORY"]) | {"SHA256SUMS"}:
        target = original / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ORIGINAL / relative, target)
    owner = tmp_path / "rom-actual-owner-v1"
    owner.mkdir()
    for status in ("process-exit.txt", "after-integrity-exit.txt", "after-ip-exit.txt", "receipt-exit.txt"):
        (owner / status).write_text("" if status == name else "0\n")
    with pytest.raises(ValueError, match="original ROM actual failed"):
        H["verify_origin"](original)


def test_source_symlink_missing_and_inventory_duplicate_reject(prepared, tmp_path):
    target = copy_prepared(prepared, tmp_path)
    source = target / "frozen_sources" / H["OBSERVER"]
    saved = source.with_suffix(".saved")
    source.rename(saved)
    source.symlink_to(saved)
    with pytest.raises(ValueError, match="aliased"):
        H["verify_prepared"](target)
    source.unlink()  # only the just-created test symlink, not the saved source
    with pytest.raises(FileNotFoundError):
        H["verify_prepared"](target)
    saved.rename(source)
    manifest = target / "SHA256SUMS"
    manifest.write_text(manifest.read_text()+manifest.read_text().splitlines()[0]+"\n")
    with pytest.raises(ValueError, match="unsafe duplicate"):
        H["verify_prepared"](target)


@pytest.mark.parametrize("enabled", [0, 1])
def test_full_actual_harness_elaborates_with_explicit_option_only(tmp_path, prepared, enabled):
    target = copy_prepared(prepared, tmp_path)
    meta = json.loads((target / "fence-preparation.json").read_text())
    meta["settings"][H["KNOB"]] = enabled
    (target / "fence-preparation.json").write_text(json.dumps(meta))
    settings = target / "settings.tcl"
    settings.write_text(settings.read_text().replace("PRODUCER_LOCAL_FINAL_FENCE=1", f"PRODUCER_LOCAL_FINAL_FENCE={enabled}"))
    rehash(target)
    assert H["verify_prepared"](target)[H["KNOB"]] == enabled
    source = target / "frozen_sources"
    (tmp_path / "stub.v").write_text(STUB)
    name = H["TOP"].removesuffix(".sv")
    files = sorted(str(p) for p in source.iterdir() if p.suffix in (".sv", ".v"))
    command = ["iverilog", "-g2012", "-tnull", "-s", name, "-I", str(source)]
    command += [f"-P{name}.{k}={v}" for k, v in meta["settings"].items()]
    result = subprocess.run(command + files + [str(tmp_path / "stub.v")], capture_output=True, text=True, check=False, timeout=40)
    (tmp_path / "elaborate.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stderr
    assert not (target / "project").exists()  # compile only, never vvp/vendor


FIXTURE = r"""`timescale 1ns/1fs
module fixture;
  reg clk=0;always #3 clk=~clk;
  reg in_running=0,input_accept=0,input_framing_valid=1;
  reg [8:0] write_position=0;
  reg old_authorized=0,new_authorized=0,forward_committed=1;
  reg slot_open=0,checked_complete=1,inverse_phase=0,guard_phase=0;
  reg input_fault_now=0,duplicate_start=0,handoff_fault_now=0;
  reg request_toggle=0,reading=0,read_valid=0;
  wire acknowledge_stage1=request_toggle;
  reg public_ready=1,public_valid=0,fast_running=1,current_fault=0,core_resetn=1,output_ready=0;
  starlink_pss_product_final_actual_observer monitor(.*,
    .pre_checks(),.post_checks(),.sampled(),.authorized(),.vetoed(),.unknown_authorization(),
    .malformed_final(),.nonsampled_differences(),.closed_samples(),.reset_samples(),
    .inverse_owned(),.owned_stalls(),.current_fault_edges(),.private_reset_samples(),.public_overlap());
  // Independent literal OLD mailbox request recurrence, not the new fence.
  always @(posedge clk)
    if (!in_running) request_toggle<=0;
    else if (input_accept) begin
      if (!input_framing_valid) begin end
      else if (write_position==511) begin
        if (old_authorized) request_toggle<=!request_toggle;
      end
    end
  function automatic reg four(input integer n);
    case(n) 0:four=0;1:four=1;2:four=1'bx;3:four=1'bz;endcase
  endfunction
  task tick;begin @(posedge clk);#0.002;end endtask
  initial begin
    tick();@(negedge clk);
    // CASE_BODY
    $display("PRODUCT_FINAL_OBSERVER_FIXTURE_PASS sampled=%0d unknown=%0d overlap=%0d",monitor.sampled,monitor.unknown_authorization,monitor.public_overlap);
    $finish;
  end
endmodule
"""


def observer_run(tmp_path, body, mutation=None):
    observer = (ACQ / "tb" / H["OBSERVER"]).read_text()
    if mutation:
        assert observer.count(mutation[0]) == 1
        observer = observer.replace(*mutation)
    (tmp_path / "observer.sv").write_text(observer)
    (tmp_path / "fixture.sv").write_text(FIXTURE.replace("// CASE_BODY", body))
    result = subprocess.run(["iverilog", "-g2012", "-s", "fixture", "-o", "sim.vvp", "observer.sv", "fixture.sv"], cwd=tmp_path, capture_output=True, text=True, check=False, timeout=15)
    (tmp_path / "compile.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stderr
    result = subprocess.run(["vvp", "sim.vvp"], cwd=tmp_path, capture_output=True, text=True, check=False, timeout=15)
    log = result.stdout + result.stderr
    (tmp_path / "simulate.log").write_text(log)
    return result.returncode, log


def test_observer_literal_four_state_branch_all_1024_combinations(tmp_path):
    body = """for(integer a=0;a<4;a=a+1) for(integer b=0;b<4;b=b+1)
      for(integer c=0;c<4;c=c+1) for(integer d=0;d<4;d=d+1) for(integer e=0;e<4;e=e+1) begin
        @(negedge clk);in_running=four(a);input_accept=four(b);input_framing_valid=four(c);
        case(d) 0:write_position=0;1:write_position=511;2:write_position='x;3:write_position='z;endcase
        old_authorized=four(e);new_authorized=four(e);public_valid=1;tick();
      end
      if(monitor.sampled!=36 || monitor.unknown_authorization!=18 || monitor.public_overlap<1024)
        $fatal(1,"FOUR_STATE_BRANCH_COUNT_MISMATCH");"""
    code, log = observer_run(tmp_path, body)
    assert code == 0 and "sampled=36 unknown=18" in log, log


@pytest.mark.parametrize("kind", ["sampled", "x_framing", "ownership", "phase", "publication"])
def test_observer_bad_boundary_and_weakened_observer_mutants(tmp_path, kind):
    body = "in_running=1;input_accept=1;input_framing_valid=1;write_position=511;old_authorized=0;new_authorized=0;"
    if kind in ("sampled", "x_framing"):
        body += "new_authorized=1;" + ("input_framing_valid=1'bx;" if kind == "x_framing" else "")
        marker = "PRODUCT_FINAL_ACTUAL_SAMPLED_AUTHORIZATION_MISMATCH"
        mutation = ("if (new_authorized !== old_authorized)", "if (1'b0)")
    elif kind == "ownership":
        body += "reading=1;"
        marker = "PRODUCT_FINAL_ACTUAL_INTERNAL_OWNERSHIP_BROKEN"
        mutation = ("if (request_toggle !== acknowledge_stage1 || reading !== 1'b0 || read_valid !== 1'b0)", "if (1'b0)")
    elif kind == "phase":
        body += "slot_open=1;inverse_phase=1;guard_phase=1;checked_complete=0;"
        marker = "PRODUCT_FINAL_ACTUAL_CLOSED_INPUT_PHASE_BROKEN"
        mutation = ("if (forward_committed === 1'b1) begin", "if (1'b0) begin")
    else:
        body += "force request_toggle=1;"
        # Reset on this edge must clear toggle even if publication is not sampled.
        body += "in_running=0;"
        marker = "PRODUCT_FINAL_ACTUAL_OLD_PUBLICATION_TRANSITION_MISMATCH"
        mutation = ("if (request_toggle !== expected_toggle)", "if (1'b0)")
    body += "tick();"
    good = tmp_path / "original";good.mkdir()
    code, log = observer_run(good, body)
    assert code != 0 and marker in log, log
    mutant = tmp_path / "mutant";mutant.mkdir()
    code, log = observer_run(mutant, body, mutation)
    # The unchanged required-fatal acceptance would reject this escape.
    assert code == 0 and marker not in log and "FIXTURE_PASS" in log, log


def test_no_authorization_mask_for_unqualified_final_or_nonsampled_count(tmp_path):
    body = """in_running=1;input_accept=0;old_authorized=0;new_authorized=1;
      forward_committed=0;tick();@(negedge clk);
      if(monitor.nonsampled_differences!=1) $fatal(1,"PRIVATE_DIFFERENCE_NOT_COUNTED");
      input_accept=1;write_position=511;tick();"""
    code, log = observer_run(tmp_path, body)
    assert code != 0 and "PRODUCT_FINAL_ACTUAL_SAMPLED_AUTHORIZATION_MISMATCH" in log, log


def test_receipt_requires_exact_settings_accounting_and_coverage(tmp_path):
    line = "PRODUCT_FINAL_FENCE_ACTUAL_PASS enabled=1 pre=99 post=99 sampled=7 authorized=5 vetoed=1 unknown=1 malformed=0 nonsampled_private=0 closed=6 resets=1 inverse_owned=1 owned_stalls=1 current_faults=2 private_reset=1 public_overlap=0 source=real_controller old_public_shadow=unchanged_dec20 qualified_status_only=1"
    for index, (value, passed) in enumerate([(line, True), (line+"\n"+line, False), (line.replace("enabled=1", "enabled=0"), False),
            (line.replace("post=99", "post=98"), False), (line.replace("sampled=7", "sampled=8"), False),
            (line.replace("closed=6", "closed=0"), False), (line.replace("current_faults=2", "current_faults=1"), False),
            (line.replace("private_reset=1", "private_reset=0"), False), (line.replace("unknown=1", "unknown=x"), False)]):
        path = tmp_path / f"receipt-{index}.txt";path.write_text(value+"\n")
        program = H["TCL_RECEIPT"] + "\nset f [open [lindex $argv 0]];set log [read $f];close $f\nputs [product_final_verify_receipt $log 1]\n"
        result = subprocess.run(["tclsh", "/dev/stdin", str(path)], input=program, capture_output=True, text=True, check=False, timeout=5)
        (tmp_path / f"receipt-{index}.log").write_text(result.stdout+result.stderr)
        assert (result.returncode == 0) == passed


def test_frozen_cli_from_root_and_new_helper_source_hash(prepared, tmp_path):
    helper = prepared / "frozen_sources" / H["SELF"]
    assert hashlib.sha256(helper.read_bytes()).digest() == hashlib.sha256(HELPER.read_bytes()).digest()
    result = subprocess.run(["/home/mouse9911/gits/pluto-plus-utils/.venv/bin/python", "-B", str(helper), "--verify-prepared", str(prepared)], cwd="/", capture_output=True, text=True, check=False, timeout=20)
    (tmp_path / "frozen-cli.log").write_text(result.stdout+result.stderr)
    assert result.returncode == 0, result.stderr

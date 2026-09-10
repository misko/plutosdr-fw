"""Readback-only boundary tests and strict original-assertion inverse.

SV executions below use a public-input stub containing NO native engine. They
test the new observation/check code, not corrected native60 service or CDC RTL.
"""

import json
import subprocess

import pytest

from tests.starlink_oracle import native60_budget as nb
from tests.starlink_oracle.native60_readback_contract import contract, limits
from tests.test_starlink_native60_budget import (
    bundle as bundle,  # noqa: PLC0414 - explicit shared pytest fixture export
)


def snapshot():
    return {"count": 1, "capture_cycle": 15602, "return_cycle": 15613,
        "captured_index": 34359738559, "live_at_capture": 34359738560, "public_index": 34359738559,
        "retained_index": 34359738559, "live_at_return": 34359738567, "capture_lag": 1, "return_lag": 8,
        "maximum_capture_lag": 2, "maximum_return_lag": 31, "maximum_return_cycles": 48}


def test_parameter_derived_lag_and_return_limits():
    assert limits() == {"capture_lag": 2, "return_cycles": 48, "return_lag": 31}
    nb.verify_snapshot(snapshot(), 15600, 15680)
    at_bound = snapshot()
    at_bound.update(capture_lag=2, live_at_capture=34359738561, return_lag=31,
                    live_at_return=34359738590, return_cycle=15650)
    nb.verify_snapshot(at_bound, 15600, 15680)


@pytest.mark.parametrize("key,value", [("count", 0), ("count", 2), ("capture_cycle", 15599),
    ("return_cycle", 15651), ("public_index", 34359738560), ("public_index", 38654705855),
    ("retained_index", 34359738558), ("captured_index", 34359738561),
    ("live_at_capture", 34359738562), ("live_at_return", 34359738591),
    ("capture_lag", 3), ("return_lag", 32), ("maximum_capture_lag", 3),
    ("maximum_return_lag", 32), ("maximum_return_cycles", 49), ("count", True), ("public_index", -1)])
def test_missing_duplicate_wrong_high_half_future_stale_snapshot(key, value):
    s = snapshot()
    s[key] = value
    with pytest.raises(ValueError):
        nb.verify_snapshot(s, 15600, 15680)


@pytest.mark.parametrize("key", list(contract()))
def test_readback_contract_type_strict_and_fixed(bundle, tmp_path, key):
    import shutil
    out = tmp_path/"altered"
    shutil.copytree(bundle, out)
    p = out/"bundle.json"
    r = json.loads(p.read_text())
    v = r["readback_contract"][key]
    r["readback_contract"][key] = int(v) if isinstance(v, bool) else float(v) if isinstance(v, int) else "mutant"
    p.write_bytes(nb.encoded(r))
    with pytest.raises(ValueError, match="readback"):
        nb.verify(out)


def test_narrow_inverse_restores_full_original_benches_and_recipe():
    old = nb.ROOT/"build/native60-budget-prelaunch-v1/source_snapshot"
    original_checks, new_checks = [(p/nb.CHECKS).read_text() for p in [old, nb.ROOT]]
    original = "    if (current_index < 64'd34359738560 || current_index > 64'd34359738720)\n      fail(\"native60 public current-index snapshot outside admission window\");\n"
    replacement = "    check_native_snapshot(current_index);\n"
    assert original_checks.count(original) == new_checks.count(replacement) == 1
    assert new_checks.replace(replacement, original) == original_checks
    old_top, new_top = [(p/nb.TOP).read_text() for p in [old, nb.ROOT]]
    included = '  `include "native60_readback_checks.svh"\n'
    assert new_top.count(included) == 1 and new_top.replace(included, "") == old_top
    name = "tests/starlink_oracle/native60_budget_recipe.py"
    assert (nb.ROOT/name).read_bytes() == (old/name).read_bytes()
    assert nb.sha((nb.ROOT/name).read_bytes()) == "5f4bb5cefd59492f34d45e7b60e24fa00c0bd6b8950e1be71bfb6ab09b555423"
    original_manifest = nb.check_cohort(nb.COHORT)
    for name, digest in original_manifest["source_sha256"].items():
        assert nb.sha((nb.ROOT/name).read_bytes()) == digest


def test_result_verifier_requires_new_observed_snapshot():
    # Signature-only protection for no hierarchy writes/extra transactions.
    code = (nb.ROOT/nb.TB/"native60_readback_checks.svh").read_text()
    assert "native.up_rreq && !native.register_read_pending" in code
    assert "!native.result_read_pending && !native.telemetry_read_pending" in code
    assert "native.up_raddr == 6'h06" in code
    assert "native_index_witness = native.current_sample_index;" in code
    assert "public_index !== native_index_witness" in code
    assert "native.current_index_snapshot !== native_index_witness" in code
    assert "read_reg(" not in code and "write_reg(" not in code and "force " not in code


@pytest.mark.parametrize("mode", ["healthy", "at_bound", "missing", "duplicate", "pending", "x_request",
    "x_pending", "x_address", "x_value", "future", "stale_capture", "wrong_low", "wrong_high",
    "changed_retained", "stale_return", "timeout"])
def test_readback_observer_public_input_boundary_no_native_engine(tmp_path, mode):
    include = nb.ROOT/nb.TB/"native60_readback_checks.svh"
    value = "64'd34359738559"
    if mode == "x_value":
        value = "64'hxxxxxxxxxxxxxxxx"
    elif mode == "future":
        value = "64'd34359738561"
    elif mode == "stale_capture":
        value = "64'd34359738557"
    elif mode == "at_bound":
        value = "64'd34359738558"
    request = "1'bx" if mode == "x_request" else "1'b0" if mode == "missing" else "1'b1"
    pending = "1'bx" if mode == "x_pending" else "1'b1" if mode == "pending" else "1'b0"
    address = "6'bxxxxxx" if mode == "x_address" else "6'h06"
    public = "64'd34359738560" if mode == "wrong_low" else "64'h00000009000000bf" if mode == "wrong_high" else value
    finish = "snapshot_value=64'd34359738558;" if mode == "changed_retained" else ""
    if mode == "stale_return":
        finish += "sample_index=64'd34359738591;"
    if mode == "at_bound":
        finish += "sample_index=64'd34359738589;"
    waits = 49 if mode == "timeout" else 2
    source = f"""`timescale 1ns/1fs
module boundary_inputs(input up_rreq,register_read_pending,result_read_pending,telemetry_read_pending,
 input [5:0] up_raddr,input [63:0] current_sample_index,current_index_snapshot); endmodule
module micro;
 reg clk=0; always #5 clk=!clk;
 reg resetn=1,native_configured=1,native_command_issued=0,source_enable=1,sample_strobe=1;
 localparam [63:0] RAW_FIRST=64'd34359735211;
 integer cycles=0,native_trigger_cycle=0; always @(posedge clk) cycles=cycles+1;
 reg [63:0] sample_index=64'd34359738560,value={value},snapshot_value={value};
 reg request=0,pending=0; reg [5:0] address=6'h06;
 boundary_inputs native(request,pending,1'b0,1'b0,address,value,snapshot_value);
 task automatic fail(input string message); $display("EXPECTED_BOUNDARY_REJECT %s",message); $fatal(1,"%s",message); endtask
 `include "{include}"
 initial begin
  @(negedge clk); request={request}; pending={pending}; address={address};
  @(negedge clk); request=0;
  {"@(negedge clk); request=1; @(negedge clk); request=0;" if mode == "duplicate" else ""}
  repeat({waits}) @(negedge clk);
  {finish}
  check_native_snapshot({public});
  $display("NATIVE60_READBACK_BOUNDARY_ONLY_PASS no_native_engine=1"); $finish;
 end
 initial begin #10000; $fatal(1,"boundary watchdog"); end
endmodule
"""
    p = tmp_path/"readback_public_boundary_NO_NATIVE.sv"
    p.write_text(source)
    compiled = subprocess.run(["iverilog", "-g2012", "-s", "micro", "-o", str(tmp_path/"micro.vvp"), str(p)],
                              capture_output=True, text=True, timeout=30, check=False)
    assert compiled.returncode == 0, compiled.stderr
    result = subprocess.run(["vvp", str(tmp_path/"micro.vvp")], capture_output=True, text=True, timeout=30, check=False)
    (tmp_path/"boundary_only.log").write_text(result.stdout+result.stderr)
    if mode in {"healthy", "at_bound"}:
        assert result.returncode == 0 and "BOUNDARY_ONLY_PASS no_native_engine=1" in result.stdout
    else:
        assert result.returncode != 0 and "EXPECTED_BOUNDARY_REJECT" in result.stdout

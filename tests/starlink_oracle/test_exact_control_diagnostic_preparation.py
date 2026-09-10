"""Observation-only diagnostic preparation; no actual FFT execution."""

import importlib.util
import json
import re
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.test_exact_control import STUB

ACQ = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"
SPEC = importlib.util.spec_from_file_location(
    "diagnostic_prepare", ACQ / "prepare_exact_control_diagnostic.py"
)
DIAG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DIAG)
ORIGINAL = ACQ / "evidence/exact-control-actual-preparation-v1/matrix/r0-d0-s0"
FIELDS = json.loads((ORIGINAL / "preparation.json").read_text())["compared_fields"]


def test_diagnostic_full_inverse_and_pair_elaboration_only(tmp_path):
    prepared = tmp_path / "prepared"
    DIAG.prepare(ORIGINAL, prepared)
    source = prepared / "frozen_sources"
    subprocess.run(
        ["sha256sum", "-c", "SHA256SUMS", "--quiet"],
        cwd=prepared,
        check=True,
        timeout=10,
    )
    for old in (ORIGINAL / "frozen_sources").iterdir():
        new = (source / old.name).read_text()
        if old.name == DIAG.OBSERVER:
            new = DIAG.once(new, DIAG.NEW_BRANCH, DIAG.OLD_BRANCH)
        elif old.name == f"{DIAG.TOP}.sv":
            new = DIAG.once(new, DIAG.diagnostic_task(FIELDS), "")
        assert new.encode() == old.read_bytes(), old.name
    assert (prepared / "settings.tcl").read_bytes() == (
        ORIGINAL / "settings.tcl"
    ).read_bytes()
    task = DIAG.diagnostic_task(FIELDS)
    assert task.count("if (") == 217
    assert task.count("EXACT_DIAGNOSTIC_FIELD name=") == 217
    assert "$fatal" not in task and "#" not in task and "@" not in task
    assert "force " not in task and "wait(" not in task and " <= " not in task
    stub = tmp_path / "compile_only_stub.v"
    stub.write_text(STUB)
    executable = tmp_path / "diagnostic_pair_not_run.vvp"
    result = subprocess.run(
        [
            "iverilog",
            "-g2012",
            "-Wall",
            "-I",
            str(source),
            "-s",
            DIAG.TOP,
            f"-P{DIAG.TOP}.FAST_MHZ=175",
            f"-P{DIAG.TOP}.EXACT_EXTRA_EPOCHS=1",
            "-o",
            str(executable),
            *map(str, sorted(source.glob("*.v"))),
            *map(str, sorted(source.glob("*.sv"))),
            str(stub),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    (tmp_path / "elaboration.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    # Full pair compiles; do NOT execute either actual bench with the stub.
    compiled = executable.read_text()
    driver = re.search(r'\.net "exact_public_equal", 0 0, (\S+);', compiled)
    assert driver is not None
    comparison = re.search(
        rf"^{re.escape(driver.group(1))} \.cmp/eeq (\d+),", compiled, re.MULTILINE
    )
    assert comparison is not None and int(comparison.group(1)) == 2168
    with pytest.raises(FileExistsError):
        DIAG.prepare(ORIGINAL, prepared)


@pytest.mark.parametrize("mutation", ["healthy", "all", "status", "empty_boolean"])
def test_same_fatal_prints_exact_named_fourstate_observations_without_fft(
    tmp_path, mutation
):
    # Independent fixture: only the diagnostic task and unchanged observer,
    # not the FFT islands/stimulus. All fields use70-bit standalone registers
    # so bit69, X and Z are exercised in the printed values without assuming
    # that arbitrary raw fault combinations are reachable receiver states.
    actual = {name: f"a[{index}]" for index, name in enumerate(FIELDS)}
    reference = {name: f"b[{index}]" for index, name in enumerate(FIELDS)}
    task = DIAG.diagnostic_task(FIELDS, actual, reference)
    context = """reg[7:0] injected_status=5; integer test_kind=11,fast_cycle=29,slow_cycle=17,epoch=11;
reg clk=0,fft_clk=0,resetn=1,fft_resetn=1;
"""
    status_index = FIELDS.index("dut.core_status_data")
    stimulus = {
        "healthy": "",
        "empty_boolean": "force_equal_low=1;",
        "status": f"a[{status_index}]=70'b1<<69;",
        "all": """for(i=0;i<217;i=i+1) begin
  a[i]=70'b1<<69;
  if(i%3==1) a[i][68]=1'bx;
  if(i%3==2) a[i][0]=1'bz;
end""",
    }[mutation]
    bench = f"""`timescale 1ns/1fs
module diagnostic_reference; {context.replace("injected_status=5", "injected_status=9")} endmodule
module {DIAG.TOP};
{context}
always #3 clk=!clk;
diagnostic_reference exact_reference();
reg[69:0] a[0:216],b[0:216]; reg force_equal_low=0;
wire[216:0] matched;
genvar g; generate for(g=0;g<217;g=g+1) begin
assign matched[g]=(a[g]===b[g]); end endgenerate
wire equal_all=(&matched)&&!force_equal_low;
wire exact_public_equal=equal_all;
wire[31:0] checks,active_checks,consumed,differences,final_faults,stalls,resets;
starlink_pss_exact_control_actual_compare #(.WIDTH(1)) monitor(
.clk(clk),.actual_public(equal_all),.reference_public(1'b1),
.actual_consume(1'b0),.reference_consume(1'b0),.actual_scratch(64'b0),.reference_scratch(64'b0),
.active_job(1'b0),.final_slot(1'b0),.current_fault(1'b0),.owned_bank(1'b0),.stalled_bank(1'b0),.running(1'b0),
.checks(checks),.active_checks(active_checks),.consumed_identities(consumed),.private_differences(differences),
.final_fault_edges(final_faults),.owned_stall_edges(stalls),.reset_owned_edges(resets));
{task}
integer i;
initial begin
for(i=0;i<217;i=i+1) begin a[i]=0;b[i]=0;end
#7; {stimulus}
#20;$display("DIAGNOSTIC_HEALTHY_FIXTURE_PASS no_fft=1");$finish;
end
endmodule
"""
    source = tmp_path / "diagnostic_fixture.sv"
    source.write_text(bench)
    observer = tmp_path / DIAG.OBSERVER
    observer.write_text(
        DIAG.once(
            (ORIGINAL / "frozen_sources" / DIAG.OBSERVER).read_text(),
            DIAG.OLD_BRANCH,
            DIAG.NEW_BRANCH,
        )
    )
    executable = tmp_path / "diagnostic_fixture.vvp"
    subprocess.run(
        [
            "iverilog",
            "-g2012",
            "-s",
            DIAG.TOP,
            "-o",
            str(executable),
            str(observer),
            str(source),
        ],
        check=True,
        timeout=10,
    )
    result = subprocess.run(
        ["vvp", str(executable)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    log = result.stdout + result.stderr
    (tmp_path / "simulate.log").write_text(log)
    if mutation == "healthy":
        assert result.returncode == 0 and "DIAGNOSTIC_HEALTHY_FIXTURE_PASS" in log
        assert "EXACT_DIAGNOSTIC" not in log
        return
    assert result.returncode != 0
    assert "EXACT_ACTUAL_PUBLIC_REASON_OWNERSHIP_MISMATCH actual=0 old=1" in log
    assert "EXACT_DIAGNOSTIC_CONTEXT time=9002000 fields=217" in log
    names = re.findall(r"EXACT_DIAGNOSTIC_FIELD name=(\S+)", log)
    expected = {
        "all": FIELDS,
        "status": ["dut.core_status_data"],
        "empty_boolean": [],
    }[mutation]
    assert names == expected
    assert (
        "EXACT_DIAGNOSTIC_CONTEXT injected_status candidate_hex=05 reference_hex=09"
        in log
    )
    fresh = 1 if mutation == "empty_boolean" else 0
    assert (
        f"EXACT_DIAGNOSTIC_TERMINAL mismatches={len(expected)} original_equal=0 fresh_equal={fresh}"
        in log
    )
    for line in log.splitlines():
        if line.startswith("EXACT_DIAGNOSTIC_FIELD"):
            assert "candidate_width=70 reference_width=70" in line
            name = re.search(r"name=(\S+)", line).group(1)
            bits = list("1" + "0" * 69)
            index = FIELDS.index(name)
            if mutation == "all" and index % 3 == 1:
                bits[1] = "x"
            if mutation == "all" and index % 3 == 2:
                bits[-1] = "z"
            assert f"candidate_fourstate={''.join(bits)}" in line
            assert "reference_fourstate=" + "0" * 70 in line
            assert "reference_hex=" + "0" * 18 in line
            if "x" not in bits and "z" not in bits:
                assert f"candidate_hex={1 << 69:018x}" in line
    assert log.index("EXACT_DIAGNOSTIC_CONTEXT") < log.index(
        "EXACT_ACTUAL_PUBLIC_REASON_OWNERSHIP_MISMATCH"
    )


def test_diagnostic_rejects_wrong_original_inventory_and_never_launches(tmp_path):
    wrong = tmp_path / "wrong"
    wrong.mkdir()
    (wrong / "SHA256SUMS").write_text("wrong\n")
    with pytest.raises(ValueError, match="authorized original"):
        DIAG.prepare(wrong, tmp_path / "must_not_exist")
    assert not (tmp_path / "must_not_exist").exists()
    helper = (ACQ / "prepare_exact_control_diagnostic.py").read_text()
    assert "launch_simulation" not in helper and '"vivado"' not in helper

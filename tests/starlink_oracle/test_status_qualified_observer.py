"""Separate observer contract: offline predicates/real guards, never actual FFT."""

import importlib.util
import json
import re
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.test_exact_control import STUB
from tests.starlink_oracle.test_exact_control_diagnostic_preparation import DIAG

ACQ = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"
SPEC = importlib.util.spec_from_file_location(
    "status_prepare", ACQ / "prepare_exact_control_status_qualified.py"
)
PREP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREP)
ORIGINAL = ACQ / "evidence/exact-control-diagnostic-preparation-v1/prepared"
# This immutable prepared freeze, unlike the actual archive, retains its
# original SHA256SUMS filename for the preparer's exact provenance gate.
FIELDS = json.loads((ORIGINAL / "preparation.json").read_text())["compared_fields"]


def run(tmp_path, source, extras=(), arguments=()):
    bench = tmp_path / "fixture.sv"
    bench.write_text(source)
    executable = tmp_path / "fixture.vvp"
    compile_result = subprocess.run(
        [
            "iverilog",
            "-g2012",
            "-Wall",
            "-s",
            PREP.TOP,
            "-o",
            str(executable),
            str(bench),
            *map(str, extras),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    (tmp_path / "compile.log").write_text(compile_result.stdout + compile_result.stderr)
    assert compile_result.returncode == 0, compile_result.stdout + compile_result.stderr
    result = subprocess.run(
        ["vvp", str(executable), *arguments],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    (tmp_path / "simulate.log").write_text(result.stdout + result.stderr)
    return result.returncode, result.stdout + result.stderr, executable


def test_whole_inverse_every_original_file_runner_stimulus_raw217_and_real_width(
    tmp_path,
):
    prepared = tmp_path / "prepared"
    PREP.prepare(ORIGINAL, prepared)
    subprocess.run(
        ["sha256sum", "-c", "SHA256SUMS", "--quiet"], cwd=prepared, check=True
    )
    source = prepared / "frozen_sources"
    for old in (ORIGINAL / "frozen_sources").iterdir():
        text = (source / old.name).read_text()
        if old.name == PREP.OBSERVER:
            text = PREP.once(text, PREP.ACCOUNT_CALL, "")
        elif old.name == f"{PREP.TOP}.sv":
            text = PREP.once(text, PREP.qualification(FIELDS), "")
            text = PREP.once(text, PREP.accounting(), "")
            text = PREP.once(text, PREP.FINISH_CALL, "")
            text = PREP.once(text, PREP.NEW_CONNECTION, PREP.OLD_CONNECTION)
        assert text.encode() == old.read_bytes(), old.name
    for name in ("settings.tcl", "original-SHA256SUMS"):
        assert (prepared / name).read_bytes() == (ORIGINAL / name).read_bytes()
    stub = tmp_path / "never_executed_stub.v"
    stub.write_text(STUB)
    executable = tmp_path / "full_pair_compile_only.vvp"
    result = subprocess.run(
        [
            "iverilog",
            "-g2012",
            "-Wall",
            "-I",
            str(source),
            "-s",
            PREP.TOP,
            f"-P{PREP.TOP}.FAST_MHZ=175",
            f"-P{PREP.TOP}.EXACT_EXTRA_EPOCHS=1",
            "-o",
            str(executable),
            *map(str, sorted(source.glob("*.v"))),
            *map(str, sorted(source.glob("*.sv"))),
            str(stub),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    (tmp_path / "full_pair_compile.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    compiled = executable.read_text()
    for signal, width in (
        ("exact_public_equal", 2168),
        ("exact_other_public_equal", 2160),
    ):
        net = re.search(rf'\.net "{signal}", 0 0, (\S+);', compiled)
        compare = re.search(
            rf"^{re.escape(net.group(1))} \.cmp/eeq (\d+),", compiled, re.MULTILINE
        )
        assert int(compare.group(1)) == width
    assert (source / "simulate_exact_control_prepared.tcl").read_bytes() == (
        ORIGINAL / "frozen_sources/simulate_exact_control_prepared.tcl"
    ).read_bytes()
    with pytest.raises(FileExistsError):
        PREP.prepare(ORIGINAL, prepared)


def mapped_predicate(mutation=None):
    other = [f for f in FIELDS if f != PREP.STATUS]
    a = {f: f"a[{other.index(f)}]" for f in other}
    b = {f: f"b[{other.index(f)}]" for f in other}
    a[PREP.STATUS], b[PREP.STATUS] = "ad", "bd"
    a[PREP.VALID], b[PREP.VALID] = "av", "bv"
    predicate = PREP.qualification(FIELDS, a, b)
    if mutation == "low5":
        predicate = predicate.replace("(ad === bd)", "(ad[4:0] === bd[4:0])")
    elif mutation and mutation.startswith("omit_bit"):
        bit = int(mutation.removeprefix("omit_bit"))
        mask = 255 ^ (1 << bit)
        predicate = predicate.replace(
            "(ad === bd)", f"((ad & 8'd{mask}) === (bd & 8'd{mask}))"
        )
    elif mutation == "unknown_invalid":
        predicate = predicate.replace("=== 1'b0", "!== 1'b1")
    elif mutation == "either_invalid":
        predicate = predicate.replace(
            "(av === 1'b0) && (bv === 1'b0)", "(av === 1'b0) || (bv === 1'b0)"
        )
    elif mutation == "omit_other":
        predicate = predicate.replace("a[0]", "b[0]")
    raw = (
        "wire exact_public_equal = ({"
        + ",".join(a[f] for f in FIELDS)
        + "} === {"
        + ",".join(b[f] for f in FIELDS)
        + "});\n"
    )
    return predicate, raw, a, b


MATRIX = r"""
reg values[0:3]; integer i,j,k,m,n,rows=0; reg expected;
task verify;
  #0.01;
  // Independent truth table: unequal valids never match, exactly00 alone
  // exempts payload, equal11/XX/ZZ still require the complete8-bit value.
  if(i!=j) expected=0;
  else if(i==0) expected=1;
  else expected=(ad===bd);
  if(exact_protocol_equal!==expected)
    $fatal(1,"STATUS_PREDICATE_MATRIX_MISMATCH i=%0d j=%0d bit=%0d kind=%0d",i,j,k,m);
  rows=rows+1;
endtask
initial begin
values[0]=0;values[1]=1;values[2]=1'bx;values[3]=1'bz;
for(n=0;n<216;n=n+1) begin a[n]=0;b[n]=0;end
for(i=0;i<4;i=i+1) for(j=0;j<4;j=j+1) begin
  av=values[i];bv=values[j];ad=8'h05;bd=8'h05;verify();
  for(k=0;k<8;k=k+1) for(m=0;m<3;m=m+1) begin
    ad=8'h05;bd=8'h05;
    case(m) 0:ad[k]=!bd[k];1:ad[k]=1'bx;2:ad[k]=1'bz;endcase
    verify();
  end
end
av=0;bv=0;ad=8'bxx100101;bd=8'h05;
for(n=0;n<216;n=n+1) begin
  // The valid field has its own scalar driver, swept explicitly above.
  if(n!=VALID_INDEX) begin
    for(m=0;m<3;m=m+1) begin
      a[n]=0; case(m) 0:a[n][69]=1;1:a[n][69]=1'bx;2:a[n][69]=1'bz;endcase
      #0.01;if(exact_protocol_equal!==0)$fatal(1,"STATUS_OTHER_FIELD_ESCAPE index=%0d",n);
      rows=rows+1;
    end
    a[n]=0;
  end
end
$display("STATUS_QUALIFIED_PREDICATE_PASS rows=%0d valid_pairs=16 data_bit_kinds=24 other_nonvalid_fields=215 no_fft=1",rows);
$finish;
end
"""


@pytest.mark.parametrize(
    "mutation",
    [
        None,
        "low5",
        "omit_bit5",
        "omit_bit6",
        "omit_bit7",
        "unknown_invalid",
        "omit_other",
    ],
)
def test_full_fourstate_valid_payload_and_other_field_truth_table_and_mutants(
    tmp_path, mutation
):
    predicate, raw, _, _ = mapped_predicate(mutation)
    index = [f for f in FIELDS if f != PREP.STATUS].index(PREP.VALID)
    source = f"""`timescale 1ns/1ps
module {PREP.TOP};
reg[69:0] a[0:215],b[0:215];reg[7:0]ad,bd;reg av,bv;
{raw}{predicate}
{MATRIX.replace("VALID_INDEX", str(index))}
endmodule
"""
    rc, log, _ = run(tmp_path, source)
    if mutation:
        assert rc != 0 and (
            "STATUS_PREDICATE_MATRIX_MISMATCH" in log
            or "STATUS_OTHER_FIELD_ESCAPE" in log
        ), log
        assert "STATUS_QUALIFIED_PREDICATE_PASS" not in log
    else:
        assert rc == 0 and "STATUS_QUALIFIED_PREDICATE_PASS rows=1045" in log, log


def observer_fixture():
    predicate, raw, a, b = mapped_predicate()
    context = "reg[7:0]injected_status=5;integer test_kind=11,fast_cycle=0,slow_cycle=0,epoch=11;reg clk=0,fft_clk=0,resetn=1,fft_resetn=1;"
    return f"""`timescale 1ns/1fs
module fixture_reference;{context} endmodule
module {PREP.TOP};
{context}
always #3 clk=!clk;
fixture_reference exact_reference();
reg[69:0]a[0:215],b[0:215];reg[7:0]ad=5,bd=5;reg av=0,bv=0;
{raw}{predicate}
wire[31:0]exact_checks,ac,cons,priv,ff,st,rs;
starlink_pss_exact_control_actual_compare #(.WIDTH(1)) monitor(
.clk(clk),.actual_public(exact_protocol_equal),.reference_public(1'b1),
.actual_consume(1'b0),.reference_consume(1'b0),.actual_scratch(64'b0),.reference_scratch(64'b0),
.active_job(1'b0),.final_slot(1'b0),.current_fault(1'b0),.owned_bank(1'b0),.stalled_bank(1'b0),.running(1'b0),
.checks(exact_checks),.active_checks(ac),.consumed_identities(cons),.private_differences(priv),
.final_fault_edges(ff),.owned_stall_edges(st),.reset_owned_edges(rs));
{DIAG.diagnostic_task(FIELDS, a, b)}
{PREP.accounting("ad", "bd", "av", "bv")}
integer n,field=-1;
initial begin
for(n=0;n<216;n=n+1)begin a[n]=0;b[n]=0;end
if($value$plusargs("FIELD=%d",field))begin end
#7;ad=8'bxx100101;
if(field>=0)begin
 if(field=={[f for f in FIELDS if f != PREP.STATUS].index(PREP.VALID)})av=1;
 else a[field][69]=1;
end
#13; exact_status_finish();
$display("STATUS_QUALIFIED_FIXTURE_PASS no_fft=1");$finish;
end
endmodule
"""


def test_same_time_invalid_logs_accounting_and_all216_other_fields_still_fatal(
    tmp_path,
):
    observer = tmp_path / PREP.OBSERVER
    observer.write_text(
        PREP.once(
            (ORIGINAL / "frozen_sources" / PREP.OBSERVER).read_text(),
            "    checks = checks + 1;",
            PREP.ACCOUNT_CALL + "    checks = checks + 1;",
        )
    )
    rc, log, executable = run(tmp_path, observer_fixture(), [observer])
    assert rc == 0 and "STATUS_QUALIFIED_FIXTURE_PASS" in log, log
    rows = re.findall(r"^EXACT_STATUS_INVALID_ONLY.*$", log, re.MULTILINE)
    assert len(rows) == 4
    for row in rows:
        assert "candidate_valid=0 reference_valid=0" in row
        assert "candidate_fourstate=xx100101 reference_fourstate=00000101" in row
        assert "raw_equal=0 protocol_equal=1" in row
    assert "samples=6 raw_equal=2 invalid_only=4 original_raw_contract_pass=0" in log
    assert PREP.verify_observation_receipt(log, 6) == {
        "samples": 6,
        "raw_equal": 2,
        "invalid_only": 4,
    }
    for bad in (
        log.replace("candidate_valid=0", "candidate_valid=x", 1),
        log.replace("reference_valid=0", "reference_valid=z", 1),
        log.replace("invalid_only=4", "invalid_only=3"),
        log.replace("raw_equal=2 invalid_only=4", "raw_equal=3 invalid_only=3"),
        log.replace("scope=only_both_valid_exactly_zero_payload", "scope=raw217"),
        log.replace("original_raw_contract_pass=0", "original_raw_contract_pass=1"),
        log
        + re.search(r"^EXACT_STATUS_QUALIFIED_OBSERVER.*$", log, re.MULTILINE)[0]
        + "\n",
    ):
        with pytest.raises(ValueError):
            PREP.verify_observation_receipt(bad, 6)
    with pytest.raises(ValueError):
        PREP.verify_observation_receipt(log, 7)
    other = [f for f in FIELDS if f != PREP.STATUS]
    failures = []
    for field, name in enumerate(other):
        result = subprocess.run(
            ["vvp", str(executable), f"+FIELD={field}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        text = result.stdout + result.stderr
        failures.append(text)
        assert result.returncode != 0, name
        assert f"EXACT_DIAGNOSTIC_FIELD name={name} " in text
        assert "EXACT_ACTUAL_PUBLIC_REASON_OWNERSHIP_MISMATCH" in text
        assert "time=9002000 fields=217" in text
        assert "STATUS_QUALIFIED_FIXTURE_PASS" not in text
    (tmp_path / "all216_rejections.log").write_text("\n".join(failures))


@pytest.mark.parametrize("mutation", ["drop_count", "force_false_raw", "bypass_other"])
def test_accounting_mutants_cannot_hide_failed_or_unlogged_comparisons(
    tmp_path, mutation
):
    observer = tmp_path / PREP.OBSERVER
    observer.write_text(
        PREP.once(
            (ORIGINAL / "frozen_sources" / PREP.OBSERVER).read_text(),
            "    checks = checks + 1;",
            PREP.ACCOUNT_CALL + "    checks = checks + 1;",
        )
    )
    source = observer_fixture()
    if mutation == "drop_count":
        source = PREP.once(
            source,
            "exact_invalid_status_only = exact_invalid_status_only + 1;",
            "exact_invalid_status_only = exact_invalid_status_only;",
        )
        marker = "STATUS_QUALIFIED_ACCOUNTING_INCOMPLETE"
    elif mutation == "force_false_raw":
        source = PREP.once(
            source,
            "#7;ad=8'bxx100101;",
            "#1;force exact_public_equal=0;#6;ad=8'bxx100101;",
        )
        marker = "STATUS_INVALID_ONLY_CLASSIFICATION_FAILED"
    else:
        source = PREP.once(
            source,
            "#7;ad=8'bxx100101;",
            "#7;ad=8'bxx100101;force exact_protocol_equal=1;a[0]=1;",
        )
        marker = "STATUS_INVALID_ONLY_CLASSIFICATION_FAILED"
    rc, log, _ = run(tmp_path, source, [observer])
    assert rc != 0 and marker in log, log
    assert "STATUS_QUALIFIED_FIXTURE_PASS" not in log


def test_bad_inventory_rejected_no_actual_launch(tmp_path):
    wrong = tmp_path / "wrong"
    wrong.mkdir()
    (wrong / "SHA256SUMS").write_text("wrong\n")
    with pytest.raises(ValueError, match="authorized strict"):
        PREP.prepare(wrong, tmp_path / "absent")
    assert not (tmp_path / "absent").exists()
    text = (ACQ / "prepare_exact_control_status_qualified.py").read_text()
    assert "launch_simulation" not in text and '"vivado"' not in text


@pytest.mark.parametrize(
    "mode,mutation",
    [
        (0, None),
        (1, None),
        (0, "reserved"),
        (1, "reserved"),
        (0, "exponent"),
        (1, "final_veto"),
        (0, "ack_veto"),
        (1, "ack_veto"),
        (0, "output_status_reason"),
        (1, "output_status_reason"),
    ],
)
def test_real_current_and_independent_frozen_guard_reasons_states_and_publication(
    tmp_path, mode, mutation
):
    name = "starlink_pss_realtime_result_guard.v"
    original = (ORIGINAL / "frozen_sources" / name).read_text()
    assert (ACQ / name).read_text() == original
    source = original
    if mutation == "reserved":
        source = PREP.once(source, "core_status_tdata[7:5] != 0", "1'b0")
    elif mutation == "exponent":
        source = PREP.once(
            source,
            "(exponent_seen && core_status_tdata[4:0] != output_exponent)",
            "1'b0",
        )
    elif mutation == "final_veto":
        source = PREP.once(
            source,
            "  wire completed_final_fault_now = completed_input_fault_now || mailbox_input_fault ||\n"
            "    !output_bank_reserved || core_event_frame_started || core_status_tvalid ||\n",
            "  wire completed_final_fault_now = completed_input_fault_now || mailbox_input_fault ||\n"
            "    !output_bank_reserved || core_event_frame_started || 1'b0 ||\n",
        )
    elif mutation == "ack_veto":
        source = PREP.once(
            source,
            "if (awaiting_ack && mailbox_input_ready && !protocol_fault && !idle_fault_now)",
            "if (awaiting_ack && mailbox_input_ready && !protocol_fault)",
        )
    elif mutation == "output_status_reason":
        expression = (
            "(core_status_tvalid && core_output_tuser[20:16] != core_status_tdata[4:0])"
        )
        assert source.count(expression) == 2
        source = source.replace(expression, "1'b0")
    candidate = tmp_path / name
    candidate.write_text(source)
    frozen = (
        ORIGINAL / "frozen_sources/starlink_pss_realtime_result_guard_dec20d63_golden.v"
    )
    assert (
        frozen.read_text().replace(
            "starlink_pss_realtime_result_guard_dec20d63_golden #(",
            "starlink_pss_realtime_result_guard #(",
        )
        == original
    )
    bench = (ACQ / "tb/tb_starlink_pss_status_qualified_guard.sv").read_text()
    bench = PREP.once(
        bench, "parameter integer MODE=0;", f"parameter integer MODE={mode};"
    )
    rc, log, _ = run(tmp_path, bench, [candidate, frozen])
    if mutation:
        assert rc != 0 and "STATUS_GUARD_TRACE_MISMATCH" in log, log
        assert "STATUS_REAL_GUARD_PASS" not in log
    else:
        assert (
            rc == 0
            and f"STATUS_REAL_GUARD_PASS mode={mode} rows=72 phases=6 invalid_payload_rows=6 known_reserved_reasons=24"
            in log
        ), log
        assert "phase_witnesses=77 coincident_output_rows=3 ready_ack_rows=2" in log

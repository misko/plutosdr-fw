"""Expired native event-oracle/runner policy only; no actual175/200 simulation."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.starlink_oracle import bank_native_expired as oracle
from tests.starlink_oracle import bank_native_true_pss as healthy
from tests.test_starlink_bank_native_paired import ACQ, ROOT, tcl
from tests.test_starlink_bank_native_true_pss import write_payloads

RUNNER = ACQ / "simulate_bank_native_expired.tcl"
HELPER = ACQ / "prepare_bank_native_expired.tcl"
CHECKS = ACQ / "tb/bank_native_expired_checks.svh"


@pytest.fixture(scope="module")
def inputs(tmp_path_factory):
    root = tmp_path_factory.mktemp("expired-policy")
    cohort = root / "cohort"
    payloads, _ = healthy.derive()
    write_payloads(cohort, payloads)
    assert healthy.digest(cohort / "fixture.json") == oracle.FIXTURE_SHA256
    contract = root / "expired"
    oracle.generate(cohort / "score", cohort / "pilot", cohort / "native", contract)
    return cohort, contract


def probe(arguments, *, cwd=None):
    return tcl('proc version {args} {return 2022.2}\nproc set_param {args} {}\n'
               'proc create_project {args} {error ADMITTED}\n'
               + "set argv [list " + " ".join(f"{{{arg}}}" for arg in arguments) + "]\n"
               + f"set argc [llength $argv]\nif {{[catch {{source {{{RUNNER}}}}} e]}} "
               + '{puts stderr $e; exit 2}\n', cwd=cwd)


def test_expected_events_and_exact_public_register_abi(inputs):
    cohort, contract = inputs
    result = oracle.verify(cohort / "score", cohort / "pilot", cohort / "native", contract)
    registers = oracle.public_registers()
    assert len(registers) == 31 and len({address for address, _ in registers}) == 31
    assert dict(registers)[0x8C] == dict(registers)[0x90] == 1
    assert all(dict(registers)[address] == 0 for address in range(0x84, 0xE4, 4) if address not in (0x8C, 0x90))
    assert dict(registers)[0x5C] == 0x1A000000 and 0x54 not in dict(registers)
    assert result["public_submit_source_offset_bounds_inclusive"] == [620, 624]
    assert result["scheduler_handshake_source_offset_bounds_inclusive"] == [620, 640]
    assert result["request_id"] == 0x15005202 and result["coefficient_generation"] == 0x15000002
    assert result["expected_admitted"] == result["expected_result_packets"] == result["expected_IRQ"] == 0
    assert result["actual_RTL_qualified"] is False
    scheduler = (ROOT / "hdl/library/starlink_pss_raw_correlator/starlink_pss_candidate_scheduler.v").read_text()
    priority = scheduler[scheduler.index("if (command_handshake) begin"):]
    assert priority.index("if (command_duplicate)") < priority.index("else if (command_overlap)") < priority.index("else if (command_late)")
    late_branch = priority.split("else if (command_late) begin", 1)[1].split("end else begin", 1)[0]
    assert "o_rejected_count <= increment_saturating_32(o_rejected_count)" in late_branch
    assert "o_late_count <= increment_saturating_32(o_late_count)" in late_branch
    assert not any(name in late_branch for name in ("o_admitted_count", "candidate_pending", "o_capture_abort", "o_aborted_count"))
    assert "command_lead[63] || (command_lead < MINIMUM_LEAD_SAMPLES)" in scheduler
    store = (ROOT / "hdl/library/starlink_pss_raw_correlator/starlink_pss_result_store.v").read_text()
    assert "o_control_result_available && i_control_word_read &&" in store
    wrapper = (ROOT / "hdl/library/axi_starlink_pss_tracker/axi_starlink_pss_tracker.v").read_text()
    assert "assign irq = result_available;" in wrapper
    for name, address in (("REJECTED", 0x8C), ("LATE", 0x90), ("RESULT_STATUS", 0x5C)):
        assert re.search(rf"REG_{name} = 6'h{address//4:02x}; // 0x{address:02x}", wrapper)


@pytest.mark.parametrize("mutation", ["rejected", "late", "packet", "request", "inventory", "extra", "dependency", "packing"])
def test_contract_or_source_mutation_rejected(inputs, tmp_path, mutation):
    original, contract = inputs
    cohort = tmp_path / "cohort"; shutil.copytree(original, cohort)
    target = tmp_path / "expired"; shutil.copytree(contract, target)
    if mutation == "inventory":
        (target / oracle.FILES[0]).unlink()
    elif mutation == "extra":
        (target / "extra").write_text("unfrozen")
    elif mutation == "packing":
        path = cohort / "native/native_coefficients_q15.mem"
        values = healthy.read_words(path, 66, 8)
        path.write_bytes(healthy.words(((word & 65535) << 16 | word >> 16 for word in values), 8))
    else:
        path = target / oracle.FILES[1]
        manifest = json.loads(path.read_text())
        key = {"rejected": "expected_rejected", "late": "expected_late", "packet": "expected_result_packets",
               "request": "request_id", "dependency": "python_runtime_sha256"}[mutation]
        manifest[key] = {} if mutation == "dependency" else manifest[key] ^ 1
        path.write_bytes(healthy.json_bytes(manifest))
    with pytest.raises((ValueError, FileNotFoundError)):
        oracle.verify(cohort / "score", cohort / "pilot", cohort / "native", target)


def test_corrupted_counter_words_rehashed_still_rejected(inputs, tmp_path):
    cohort, contract = inputs
    target = tmp_path / "expired"; shutil.copytree(contract, target)
    path = target / oracle.FILES[0]
    values = path.read_text().splitlines(); values[11] = "00000000"
    path.write_text("\n".join(values) + "\n")  # Rejected1 changed to0.
    manifest = json.loads((target / oracle.FILES[1]).read_text())
    manifest["generated_sha256"][oracle.FILES[0]] = healthy.digest(path)
    (target / oracle.FILES[1]).write_bytes(healthy.json_bytes(manifest))
    with pytest.raises(ValueError, match="independent contract"):
        oracle.verify(cohort / "score", cohort / "pilot", cohort / "native", target)


def test_no_overwrite(inputs):
    cohort, contract = inputs
    with pytest.raises(ValueError, match="overwrite"):
        oracle.generate(cohort / "score", cohort / "pilot", cohort / "native", contract)


@pytest.mark.parametrize("clock", [175, 200])
def test_real_tcl_admission_full_source_freeze(inputs, tmp_path, clock):
    cohort, contract = inputs
    output = tmp_path / "run"
    result = probe([output, cohort / "score", cohort / "pilot", cohort / "native", contract, clock, oracle.PROFILE])
    assert result.returncode == 2 and result.stderr.strip() == "ADMITTED", result.stderr
    frozen = output / "frozen_sources"
    for path in cohort.rglob("*"):
        if path.is_file():
            assert (frozen / path.name).read_bytes() == path.read_bytes()
    for path in (RUNNER, HELPER, CHECKS, Path(__file__), *(contract / name for name in oracle.FILES)):
        assert (frozen / path.name).read_bytes() == path.read_bytes()
    assert (frozen / "simulate_bank_native_paired.tcl").read_bytes() == (ACQ / "simulate_bank_native_paired.tcl").read_bytes()
    inventory = (frozen / "python_runtime_inventory.txt").read_text().splitlines()
    assert len(inventory) == 13
    assert {line.split()[0] for line in inventory} == set(oracle.PYTHON_DEPENDENCIES)
    scope = (output / "scope.txt").read_text()
    for line in inventory:
        relative, encoded = line.split()
        assert (frozen / encoded).read_bytes() == (ROOT / relative).read_bytes()
        assert encoded in scope
    assert "native_event_profile=520-pss-expired native_packets_expected=0" in scope
    bench = (frozen / "tb_starlink_bank_native_expired.sv").read_text()
    assert "forever #(500.0 / 15) sample_clk" in bench and ".ENABLE_INJECTION(0)" in bench
    assert "expired_snapshot(1)" in bench and "expired_snapshot(2)" in bench
    assert 'readmemh("native_expected_packet.mem"' not in bench
    assert "BANK_NATIVE_EXACT_PASS" not in bench


def test_all_relative_paths_preserved(inputs, tmp_path):
    cohort, contract = inputs
    shutil.copytree(cohort, tmp_path / "cohort"); shutil.copytree(contract, tmp_path / "contract")
    result = probe(["out", "cohort/score", "cohort/pilot", "cohort/native", "contract", 175, oracle.PROFILE], cwd=tmp_path)
    assert result.returncode == 2 and result.stderr.strip() == "ADMITTED", result.stderr


@pytest.mark.parametrize("clock,profile", [(150, oracle.PROFILE), ("175.0", oracle.PROFILE), (175, "520-pss"), (200, "gap"), (200, "reset")])
def test_unknown_profiles_rejected_before_allocation(tmp_path, clock, profile):
    result = probe([tmp_path / "out", "missing", "missing", "missing", "missing", clock, profile])
    assert "requires literal" in result.stderr and not (tmp_path / "out").exists()


@pytest.mark.parametrize("mutation", ["missing", "duplicate"])
def test_adaptation_single_anchor_fail_closed(tmp_path, mutation):
    source = (ACQ / "simulate_bank_native_paired.tcl").read_text()
    anchor = "set project_name bank_native_paired"
    source = source.replace(anchor, "" if mutation == "missing" else anchor + "\n" + anchor)
    path = tmp_path / "runner"; path.write_text(source)
    result = tcl(f"source {{{HELPER}}}\nset f [open {{{path}}}]; set s [read $f]; close $f\n"
                 'if {[catch {prepare_expired_native_runner $s} e]} {puts stderr $e; exit 2}\n')
    assert result.returncode == 2 and "anchor missing or duplicated" in result.stderr


def test_exact_13module_runtime_import_closure():
    program = """import importlib,json,pathlib,sys
root=pathlib.Path.cwd().resolve()
importlib.import_module('tests.starlink_oracle.bank_native_expired')
print(json.dumps(sorted({str(pathlib.Path(m.__file__).resolve().relative_to(root))
 for n,m in sys.modules.items() if n == 'tests' or n.startswith('tests.')})))
"""
    result = subprocess.run([sys.executable, "-c", program], cwd=ROOT, text=True, capture_output=True, check=True, timeout=15)
    assert set(json.loads(result.stdout)) == set(oracle.PYTHON_DEPENDENCIES)


def valid_log(clock=175):
    rows = [f"BANK_EXPIRED_REGISTER generation={generation} ordinal={n} address={address:02x} value={value:08x}"
            for generation in (1, 2) for n, (address, value) in enumerate(oracle.public_registers())]
    rows += [f"BANK_EXPIRED_EMPTY generation={generation} result_status=1a000000 available=0 irq=0 packet_data_reads=0" for generation in (1, 2)]
    rows += ["BANK_EXPIRED_PUBLIC_SUBMIT index=8589935196 request=15005202 center=8589935096",
             "BANK_EXPIRED_REJECT index=8589935201 start=8589935064 lead_hex=ffffffffffffff76 late=1 duplicate=0 overlap=0 request=15005202",
             "BANK_EXPIRED_CONCURRENCY fft_run_fast_cycles=70 first_fast_after_reject=1 pilot_input_accepts=5",
             "BANK_EXPIRED_EXACT_PASS public_submits=1 wrapper_handshakes=1 fifo_accepts=1 sample_handshakes=1 rejected=1 late=1 admitted=0 capture_words=0 completed=0 packets=0 irq=0 public_register_reads=62 empty_across_stop=1",
             f"BANK_NATIVE_EXPIRED_PASS source_msps=15 fast_mhz={clock} profile=520-pss-expired source_words=4096 scores=894 map_words=447 pilot_bytes=2048 NATIVE_REQUEST_REJECTED_COARSE_PILOT_HEALTHY_NOT_CAUSAL"]
    return rows


@pytest.mark.parametrize("mutation", [None, "missing", "duplicate", "register", "order", "empty_irq", "healthy_packet",
                                     "clock", "request", "handshake_early", "handshake_late", "lead", "duplicate_predicate",
                                     "zero_fft", "zero_pilot", "no_first_fast", "late_FAIL", "late_FAULT", "late_Fatal", "late_ERROR", "false_exemption"])
def test_exact_negative_postprocessor(inputs, tmp_path, mutation):
    _, contract = inputs
    rows = valid_log()
    if mutation == "missing": rows.pop()
    elif mutation == "duplicate": rows.append(rows[-1])
    elif mutation == "register": rows[5] = rows[5].replace("value=00000001", "value=00000000")
    elif mutation == "order": rows[0], rows[1] = rows[1], rows[0]
    elif mutation == "empty_irq": rows[62] = rows[62].replace("irq=0", "irq=1")
    elif mutation == "healthy_packet": rows.append("BANK_NATIVE_PACKET_WORD pass=0 word=0 data=31535350")
    elif mutation == "clock": rows[-1] = rows[-1].replace("fast_mhz=175", "fast_mhz=200")
    elif mutation == "request": rows[64] = rows[64].replace("15005202", "15005201")
    elif mutation == "handshake_early": rows[65] = rows[65].replace("index=8589935201", "index=8589935195")
    elif mutation == "handshake_late": rows[65] = rows[65].replace("index=8589935201", "index=8589935217")
    elif mutation == "lead": rows[65] = rows[65].replace("ffffffffffffff76", "0000000000000040")
    elif mutation == "duplicate_predicate": rows[65] = rows[65].replace("duplicate=0", "duplicate=1")
    elif mutation == "zero_fft": rows[66] = rows[66].replace("fast_cycles=70", "fast_cycles=0")
    elif mutation == "zero_pilot": rows[66] = rows[66].replace("accepts=5", "accepts=0")
    elif mutation == "no_first_fast": rows[66] = rows[66].replace("first_fast_after_reject=1", "first_fast_after_reject=0")
    elif mutation and mutation.startswith("late_"): rows.append(mutation[5:] + ": after apparent PASS")
    elif mutation == "false_exemption": rows.append("PAIRED_LATE_FAULT_PASS actual_invalid_release=1 failed_joint_health=1 terminal_coordinates_retained=1 pilot_bytes_preserved=1 ERROR: hidden")
    (tmp_path / "simulate.log").write_text("\n".join(rows) + "\n")
    result = tcl(f"source {{{HELPER}}}\nsource {{{ACQ / 'verify_realtime_probe_result.tcl'}}}\n"
                 f"if {{[catch {{expired_verify_outputs {{{tmp_path}}} {{{contract}}} 175 520-pss}} e]}} "
                 '{puts stderr $e; exit 2}\n')
    assert (result.returncode == 0) == (mutation is None), result.stderr


def test_no_unavailable_packet_read_or_runtime_force():
    checks = CHECKS.read_text()
    assert not re.search(r"\b(force|release)\s+native[.]", checks)
    assert not re.search(r"(?:read|write)_reg\(2,\s*8'h(?:54|58)", checks)
    assert "native.result_word_read !== 0" in checks
    assert "native.rejected_count !== expired_sample_handshakes" in checks
    assert "native.late_count !== expired_sample_handshakes" in checks
    assert "#0.001; // Observe the scheduler's same-edge NBA branch" in checks
    assert "expired_fast_handshake_witness != 1" in checks
    assert "expired_pilot_accepts < 1" in checks


COEFFICIENT_STATES = {
    "STATE_IDLE": 0, "STATE_COEFFICIENT_ENERGY": 1,
    "STATE_COEFFICIENT_CHECK": 2, "STATE_COEFFICIENT_COPY": 3,
    "STATE_COEFFICIENT_COPY_FINISH": 9, "STATE_COEFFICIENT_ENERGY_FLUSH": 10,
}


def configuration_guard():
    return re.search(r"  task automatic native_configuration_guard;.*?  endtask",
                     CHECKS.read_text(), re.DOTALL).group()


def test_configuration_names_match_actual_rtl_and_all_other_guards_unconditional():
    rtl = (ROOT / "hdl/library/starlink_pss_raw_correlator/starlink_pss_sliding_correlator.v").read_text()
    states = {name: int(value) for name, value in re.findall(
        r"localparam \[3:0\] (STATE_\w+)\s*= 4'd(\d+);", rtl)}
    guard = configuration_guard()
    assert {name: states[name] for name in set(re.findall(r"STATE_\w+", guard))} == COEFFICIENT_STATES
    assert "assign o_busy = (state != STATE_IDLE);" in rtl
    assert "else if (i_coefficient_commit && o_coefficient_commit_ready) begin\n            state <= STATE_COEFFICIENT_ENERGY;" in rtl
    checks = CHECKS.read_text()
    task = checks.split("task automatic native_empty;", 1)[1].split("endtask", 1)[0]
    condition = task.split("if (", 1)[1].split(") begin", 1)[0]
    expected = ["native_injected", "native_irq", "native.result_available", "native.result_word_read",
                "native.result_release", "native.candidate_command_overrun_count",
                "native.coefficient_write_overrun_count", "native.queue_overrun_count",
                "native.engine_consumed_count", "native.correlator_bound_error_count",
                "native.reducer_processed_job_count", "native.reducer_emitted_result_count",
                "native.reducer_invalid_tuple_count", "native.reducer_bound_error_count",
                "native.reducer_protocol_error_count", "native.result_published_count",
                "native.result_overrun_count", "native.result_consumed_count"]
    assert condition.split() == " || ".join(f"{name} !== 0" for name in expected).split()
    assert task.index("native_configuration_guard();") > task.index('fail("expired request unexpectedly')
    for anchor, end in (("if (`EN_SCHED.command_handshake) begin", "expired_sample_handshakes ="),
                        ("if (native.up_wreq", "expired_public_submits =")):
        event = checks.split(anchor, 1)[1].split(end, 1)[0]
        for name in ("native_configured", "source_enable", "sample_strobe"):
            assert f"{name} !== 1'b1" in event


@pytest.mark.parametrize("mutation", [None, "extra_state", "busy_off", "unknown_config", "unknown_state",
                                     "unknown_source", "unknown_strobe", "postcommit_state", "postcommit_busy"])
def test_executed_configuration_guard_four_state_matrix(tmp_path, mutation):
    """Execute the exact extracted test task; no receiver/vendor clocks run."""
    task = configuration_guard()
    replacements = {
        "extra_state": ("STATE_COEFFICIENT_COPY_FINISH:", "STATE_COEFFICIENT_COPY_FINISH,\n        `EN_RAW.i_sliding_correlator.STATE_SAMPLE_ENERGY:"),
        "busy_off": ("`EN_RAW.correlator_busy !== 1'b1", "1'b0"),
        "unknown_config": ("native_configured === 1'b0", "native_configured !== 1'b1"),
        "unknown_state": ("case (", "casez ("),
        "unknown_source": ("source_enable !== 1'b0", "source_enable != 1'b0"),
        "unknown_strobe": ("sample_strobe !== 1'b0", "sample_strobe != 1'b0"),
        "postcommit_state": ("`EN_RAW.i_sliding_correlator.state !== `EN_RAW.i_sliding_correlator.STATE_IDLE", "1'b0"),
        "postcommit_busy": ("`EN_RAW.correlator_busy !== 1'b0)\n        fail(\"expired configured", "1'b0)\n        fail(\"expired configured"),
    }
    if mutation:
        old, new = replacements[mutation]
        assert task.count(old) == 1
        task = task.replace(old, new)
    task = task.replace("`EN_RAW.i_sliding_correlator.", "").replace("`EN_RAW.correlator_busy", "busy")
    rtl = (ROOT / "hdl/library/starlink_pss_raw_correlator/starlink_pss_sliding_correlator.v").read_text()
    definitions = "\n".join(re.findall(r"  localparam \[3:0\] STATE_\w+\s*= 4'd\d+;", rtl))
    program = """module guard_matrix;
reg native_configured, source_enable, sample_strobe, busy;
reg [3:0] state;
reg choices [0:3];
integer c, s, b, e, v, failures, total;
reg expected;
task automatic fail(input [1023:0] message); failures = failures + 1; endtask
""" + definitions + "\n" + task + """
initial begin
  choices[0]=0; choices[1]=1; choices[2]=1'bx; choices[3]=1'bz; total=0;
  for(c=0;c<4;c=c+1) for(s=0;s<18;s=s+1) for(b=0;b<4;b=b+1)
    for(e=0;e<4;e=e+1) for(v=0;v<4;v=v+1) begin
      native_configured=choices[c]; busy=choices[b]; source_enable=choices[e]; sample_strobe=choices[v];
      if(s==16) state=4'bxxxx; else if(s==17) state=4'bzzzz; else state=s;
      expected=((c==0 && e==0 && v==0 && (s==0 || s==1 || s==2 || s==3 || s==9 || s==10) && b==(s==0 ? 0:1)) ||
                (c==1 && s==0 && b==0));
      failures=0; native_configuration_guard();
      if((failures==0) !== expected) $fatal(1,"CONFIG_GUARD_MATRIX_MISMATCH c=%0d s=%0d b=%0d e=%0d v=%0d",c,s,b,e,v);
      total=total+1;
    end
  if(total != 4608) $fatal(1,"bad matrix inventory");
  $display("CONFIG_GUARD_MATRIX_PASS cases=4608 exact_task=1 product_simulation=0"); $finish;
end
endmodule
"""
    source = tmp_path / "guard.sv"; source.write_text(program)
    binary = tmp_path / "guard.vvp"
    subprocess.run(["iverilog", "-g2012", "-s", "guard_matrix", "-o", str(binary), str(source)],
                   text=True, capture_output=True, check=True, timeout=15)
    result = subprocess.run(["vvp", str(binary)], text=True, capture_output=True, check=False, timeout=15)
    assert (result.returncode == 0) == (mutation is None), result.stdout + result.stderr
    assert ("CONFIG_GUARD_MATRIX_PASS cases=4608" in result.stdout) == (mutation is None)


def compose_expired(bench, checks, tmp_path):
    original = tmp_path / "input.sv"; original.write_text(bench)
    include = tmp_path / "checks.svh"; include.write_text(checks)
    return tcl(f"source {{{HELPER}}}\nset f [open {{{original}}}]; set b [read $f]; close $f\n"
               f"set f [open {{{include}}}]; set c [read $f]; close $f\n"
               'if {[catch {prepare_expired_paired_bench $b $c} e]} {puts stderr $e; exit 2} else {puts -nonewline $e}\n')


def test_negative_declaration_order_inverse_and_offline_compile(inputs, tmp_path):
    cohort, contract = inputs
    run = tmp_path / "run"
    result = probe([run, cohort / "score", cohort / "pilot", cohort / "native", contract, 175, oracle.PROFILE])
    assert result.returncode == 2 and result.stderr.strip() == "ADMITTED"
    frozen = run / "frozen_sources"
    bench_path = frozen / "tb_starlink_bank_native_expired.sv"
    bench = bench_path.read_text()
    declaration = "  reg source_enable = 0;"
    assert bench.count(declaration) == 1 and bench.index(declaration) < bench.index(".sample_enable(source_enable)")
    # Reverse only declaration relocation and module rename. The original
    # healthy composition with the same negative checks stays byte-identical.
    inverse = bench.replace(declaration + "\n  reg sample_strobe = 0;", "  reg sample_strobe = 0;")
    inverse = inverse.replace("  localparam [31:0] NATIVE_GENERATION = 32'h15000002;\n\n",
                              "  localparam [31:0] NATIVE_GENERATION = 32'h15000002;\n" + declaration + "\n")
    inverse = inverse.replace("module tb_starlink_bank_native_expired #(", "module tb_starlink_bank_native_paired #(")
    base_path = ACQ / "tb/tb_starlink_pss_paired_realtime_psma_stop.sv"
    legacy = tcl(f"source {{{ACQ / 'prepare_bank_native_paired.tcl'}}}\n"
                 f"set f [open {{{base_path}}}]; set b [read $f]; close $f\n"
                 f"set f [open {{{CHECKS}}}]; set c [read $f]; close $f\n"
                 'puts -nonewline [prepare_native_paired_bench $b $c]\n')
    assert legacy.returncode == 0 and inverse == legacy.stdout
    command = ["iverilog", "-g2012", "-Wimplicit", "-i", "-tnull", "-s", "tb_starlink_bank_native_expired",
               "-Ptb_starlink_bank_native_expired.MAP_BINS=447", "-Ptb_starlink_bank_native_expired.USE_BANK_OWNED_XFFT=1",
               "-Ptb_starlink_bank_native_expired.FAST_MHZ=175", *map(str, sorted(frozen.glob("*.v"))), str(bench_path)]
    compiled = subprocess.run(command, text=True, capture_output=True, check=False, timeout=30)
    assert compiled.returncode == 0, compiled.stderr
    assert "source_enable" not in compiled.stderr, compiled.stderr
    # Compile/elaboration-only; -i ignores the absent generated FFT.


@pytest.mark.parametrize("anchor", ["  reg source_enable = 0;", "  reg sample_strobe = 0;"])
@pytest.mark.parametrize("mutation", ["missing", "duplicate"])
def test_negative_declaration_single_anchor_fail_closed(tmp_path, anchor, mutation):
    base = (ACQ / "tb/tb_starlink_pss_paired_realtime_psma_stop.sv").read_text()
    checks = CHECKS.read_text()
    if anchor in checks:
        checks = checks.replace(anchor, "" if mutation == "missing" else anchor + "\n" + anchor)
    else:
        base = base.replace(anchor, "" if mutation == "missing" else anchor + "\n" + anchor)
    result = compose_expired(base, checks, tmp_path)
    assert result.returncode == 2 and "anchor missing or duplicated" in result.stderr

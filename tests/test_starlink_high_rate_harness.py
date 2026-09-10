"""Offline harness admission/policy and actual non-FFT module probes only."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.starlink_oracle.high_rate_harness import (
    COHORT_SHA,
    PROFILE,
    TERMINAL,
    continuation,
    fixture_payloads,
    prepare_vectors,
    sha,
    verify_native_results,
    verify_results,
    verify_vectors,
)
from tests.test_starlink_native30_budget import NATIVE_SOURCES
from tools.prepare_starlink_high_rate_harness import freeze, verify_bundle

ROOT = Path(__file__).resolve().parents[1]
HDL = ROOT / "hdl/library"
ACQ = HDL / "starlink_pss_acquisition"
COHORT = ROOT / "build/high-rate-offline-v5/cohort"


def run_compile(tmp_path, top, sources, extra=()):
    frozen = tmp_path / "source_snapshot"
    frozen.mkdir()
    for path in [*sources, *map(Path, extra), *ACQ.glob("tb/*native30*.svh"), ACQ / "tb/high_rate_paired_axi.svh"]:
        shutil.copyfile(path, frozen / path.name)
    (tmp_path / "source-before.json").write_text(json.dumps({
        path.name: sha(path.read_bytes()) for path in frozen.iterdir()
    }, sort_keys=True, indent=2))
    command = ["iverilog", "-g2012", "-Wall", "-I", str(frozen), "-s", top, "-o", str(tmp_path / "test.vvp")]
    result = subprocess.run(command + [str(frozen / path.name) for path in [*sources, *map(Path, extra)]],
                            capture_output=True, text=True, timeout=30, check=False)
    (tmp_path / "compile.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    after = {path.name: sha(path.read_bytes()) for path in frozen.iterdir()}
    (tmp_path / "source-after-compile.json").write_text(json.dumps(after, sort_keys=True, indent=2))
    assert after == json.loads((tmp_path / "source-before.json").read_text())


def test_extension_admitted_only_after_native_bound(tmp_path):
    directory = tmp_path / "vectors"
    result = prepare_vectors(COHORT, directory)
    assert verify_vectors(COHORT, directory) == result
    assert len(result["original51"]) == 51 and len(result["files"]) == 63
    assert result["budget"]["engine_derived_cycles"] == 22404
    assert result["budget"]["margin_engine_tenths"] == 37400
    assert result["original_cohort_sha256"] == COHORT_SHA
    assert result["profile"] == PROFILE
    original = (COHORT / "source_ci16.mem").read_text().splitlines()
    combined = (directory / "paired_source_ci16.mem").read_text().splitlines()
    assert combined[:2] == ["00000001", "00000002"]
    assert combined[2:8207] == original
    assert combined[8207:] == [f"{n:08x}" for n in continuation()]
    with pytest.raises(ValueError, match="overwrite"):
        prepare_vectors(COHORT, directory)


@pytest.mark.parametrize("name", [
    "paired_source_ci16.mem", "paired_source_index_u64.mem", "continuation_ci16.mem",
    "canonical_ci16.mem", "canonical_raw_support_first_u64.mem", "fft_input_axi48.mem",
    "conditioned_kernel_q17.mem", "native_raw_qualified.mem", "native_raw_index.mem",
    "native_raw_real.mem", "pilot_expected.ci16",
])
def test_rejects_source_halo_phase_packing_kernel_and_tuple_mutants(tmp_path, name):
    output = tmp_path / "vectors"
    prepare_vectors(COHORT, output)
    path = output / name
    changed = bytearray(path.read_bytes())
    changed[0] ^= 1
    path.write_bytes(changed)
    with pytest.raises(ValueError, match="fixture mismatch"):
        verify_vectors(COHORT, output)


@pytest.mark.parametrize("field,value", [
    ("profile", "60-upper-bank175-native264"), ("raw_first", 17179867610),
    ("original_raw_preroll_count", 1548), ("coarse_admitted", 893),
    ("coarse_visible_max", 1342), ("continuation_seed", 1), ("all_source_count", 12304),
])
def test_rejects_modified_admission_receipt(tmp_path, field, value):
    output = tmp_path / "vectors"
    result = prepare_vectors(COHORT, output)
    result[field] = value
    (output / "harness.json").write_text(json.dumps(result))
    with pytest.raises(ValueError, match="receipt mismatch"):
        verify_vectors(COHORT, output)


def test_all_original_runtime_except_approved_stage_a_is_unchanged():
    receipt = json.loads((COHORT / "cohort.json").read_bytes())
    approved = {
        "hdl/library/axi_starlink_pss_acquisition/axi_starlink_pss_acquisition.v":
            "2ce3a4943b43af7120500ba5064bedf0e7b1338517cc1d41b7ea30a33b0951d0",
        "hdl/library/axi_starlink_pss_acquisition/axi_starlink_pss_phase_map_sync.v":
            "8911f045cb0811b9aabb008f8954f8c00f19bae7ba596996ec1e3c6b61f6bd4a",
    }
    for name, digest in receipt["source_sha256"].items():
        if name.endswith(".v"):
            assert sha((ROOT / name).read_bytes()) == approved.get(name, digest), name


def test_real_native30_and_conditioner_pilot_auto_stop_prefix(tmp_path):
    prepare_vectors(COHORT, tmp_path / "vectors")
    for source in (tmp_path / "vectors").iterdir():
        shutil.copyfile(source, tmp_path / source.name)
    for name in ["pilot_mixer_q16.mem", "pilot_halfband2_q17.mem", "pilot_fir3_q17.mem"]:
        shutil.copyfile(ACQ / name, tmp_path / name)
    sources = [HDL / name for name in NATIVE_SOURCES] + [ACQ / f"{name}.v" for name in [
        "starlink_pss_sample_cdc", "starlink_pss_x2_ddc", "starlink_pilot_ddc", "starlink_pilot_halfband2", "starlink_pilot_fir3",
    ]] + [HDL / "axi_starlink_pilot_capture/axi_starlink_pilot_capture.v",
          HDL / "axi_starlink_pss_phase_map/starlink_pss_axi_lite.v",
          ACQ / "tb/tb_starlink_native30_conditioner_prefix.sv"]
    run_compile(tmp_path, "tb_starlink_native30_conditioner_prefix", sources)
    result = subprocess.run(["vvp", str(tmp_path / "test.vvp")], cwd=tmp_path,
                            capture_output=True, text=True, timeout=30, check=False)
    (tmp_path / "simulation.log").write_text(result.stdout + result.stderr)
    after = {path.name: sha(path.read_bytes()) for path in (tmp_path / "source_snapshot").iterdir()}
    (tmp_path / "source-after-simulation.json").write_text(json.dumps(after, sort_keys=True, indent=2))
    assert after == json.loads((tmp_path / "source-before.json").read_text())
    verify_vectors(COHORT, tmp_path / "vectors")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FAIL" not in result.stdout and "ERROR" not in result.stdout and "FATAL" not in result.stdout
    assert result.stdout.count("NATIVE30_CONDITIONER_PREFIX_PASS") == 1
    verify_native_results(tmp_path, result.stdout)
    assert (tmp_path / "paired_pilot_actual.ci16").read_bytes() == (COHORT / "pilot_expected.ci16").read_bytes()


def test_full_top_elaboration_only_with_fail_fast_inert_fft(tmp_path):
    # Inert interface is forbidden from running a transform. Compile-only
    # checks the real whole runtime closure and every hierarchical witness.
    stub = tmp_path / "inert_fft.v"
    stub.write_text("""module starlink_pss_fft512_bfp18_rt_candidate(
      input aclk,aresetn,input [7:0] s_axis_config_tdata,input s_axis_config_tvalid,
      output s_axis_config_tready,input [47:0] s_axis_data_tdata,input s_axis_data_tvalid,
      output s_axis_data_tready,input s_axis_data_tlast,output [47:0] m_axis_data_tdata,
      output [23:0] m_axis_data_tuser,output m_axis_data_tvalid,m_axis_data_tlast,
      output [7:0] m_axis_status_tdata,output m_axis_status_tvalid,
      output event_frame_started,event_tlast_unexpected,event_tlast_missing,event_data_in_channel_halt);
      assign s_axis_config_tready=0; assign s_axis_data_tready=0;
      assign m_axis_data_tdata=0; assign m_axis_data_tuser=0; assign m_axis_data_tvalid=0;
      assign m_axis_data_tlast=0; assign m_axis_status_tdata=0; assign m_axis_status_tvalid=0;
      assign event_frame_started=0; assign event_tlast_unexpected=0;
      assign event_tlast_missing=0; assign event_data_in_channel_halt=0;
      always @(posedge aclk) if (aresetn && (s_axis_config_tvalid || s_axis_data_tvalid))
        $fatal(1,"INERT_FFT_IS_ELABORATION_ONLY_NOT_A_NUMERICAL_MODEL");
    endmodule\n""")
    receipt = json.loads((COHORT / "cohort.json").read_bytes())
    sources = [ROOT / name for name in receipt["source_sha256"] if name.endswith(".v")]
    sources += [HDL / name for name in NATIVE_SOURCES if HDL / name not in sources]
    sources += [HDL / "axi_starlink_pss_phase_map/starlink_pss_axi_lite.v"]
    sources += [ACQ / "tb/tb_starlink_pss_30_bank_native_paired.sv"]
    run_compile(tmp_path, "tb_starlink_pss_30_bank_native_paired", sources, [str(stub)])
    assert not (tmp_path / "simulation.log").exists()  # Deliberately never vvp.


def test_old51_payload_identity_not_replaced_by_extension():
    payloads, result = fixture_payloads(COHORT)
    assert all(sha(payloads[name]) == digest for name, digest in result["original51"].items())


def parser_only_specimen(directory):
    """Construct parser coverage, explicitly NOT a simulation result."""
    directory.mkdir()
    payloads, _ = fixture_payloads(COHORT)
    for name, data in payloads.items():
        (directory / name).write_bytes(data)
    raw = json.loads(payloads["native_all_raw_tuples.json"])
    (directory / "native30_actual_raw_tuples.txt").write_text("".join(
        f"{r['lag']} {r['start_index']:016x} {r['real'] & ((1<<48)-1):012x} {r['imag'] & ((1<<48)-1):012x} "
        f"{r['Ex']:012x} {r['Eh']:012x} {r['power']:024x} {r['saturation']:03x} {int(r['qualified'])}\n"
        for r in raw))
    (directory / "paired_pilot_actual.ci16").write_bytes(payloads["pilot_expected.ci16"])
    packet = payloads["native_expected_packet.mem"].decode().splitlines()
    pilot = payloads["pilot_expected_ci16.mem"].decode().splitlines()
    indexes = payloads["pilot_expected_index_u64.mem"].decode().splitlines()
    snapshot = []
    for value in [int(indexes[0], 16), int(indexes[-1], 16), 512, 512, 90, 0, 3617, 602]:
        snapshot.extend([value & 0xffffffff, value >> 32])
    snapshot.extend([0, 0x100, 0, 24, 0x30000052, 2, 0, 0, 0, 0])
    lines = [
        "PARSER_ONLY_SPECIMEN_NOT_SIMULATION_EVIDENCE",
        "HIGH_RATE30_PREROLL_PASS disabled_prime=2 original_raw=1549 canonical=768 public_psma=00010007 caps=000007ff native_taps=132",
        "NATIVE30_ADMISSION index=17179869201 capture_start=17179870128 lead=926 deadline=17179869408",
        "HIGH_RATE30_STOP selected=894 visible=894 source=4000 canonical=1900 pilot=200 native_capture=260 native_busy=1",
        "NATIVE30_BUDGET_PASS capture_end_cycle=13000 publish_cycle=32911 release_cycle=33700 engine_cycles=19911 post_capture_cycles=20700 maximum_axi_cycles=7 raw=129 qualified=121 capture=260 packet_reads=52",
        "HIGH_RATE30_RETENTION_PASS map_retained_through_native_release=1 native_result_released=1 map_words=447 source=9000",
        "HIGH_RATE30_PREFIX source=12303 ingress=12303 enabled_raw=7250 canonical=3618 pilot_accepted=3617 pilot_mixed=3617 pilot_half=1808 pilot_all=602 forward_input=1536 forward=1536 product=1536 inverse_input=1024 inverse=1024 prepare=894 ratio=894 visible_scores=894 admitted_scores=894",
        "HIGH_RATE30_OVERLAP capture_actual_fft=20 compute_coarse_pilot=300 compute_after_stop=10000 bank_quiet_fast_cycles=50000 source_at_stop=4000 source_at_native_release=9000 source_at_map_release=9040",
        "HIGH_RATE30_PIL1_SNAPSHOT generation=1 raw_words=" + "".join(f" {word:08x}" for word in snapshot),
        *[f"NATIVE30_PACKET_WORD pass={p} word={n} data={packet[n]}" for p in range(2) for n in range(26)],
        *[f"HIGH_RATE30_PILOT_WORD ordinal={n} newest={indexes[n]} word={pilot[n]}" for n in range(512)],
        TERMINAL,
    ]
    log = "\n".join(lines) + "\n"
    (directory / "simulate.log").write_text(log)
    return log


def test_parser_only_healthy_specimen(tmp_path):
    directory = tmp_path / "parser_only"
    parser_only_specimen(directory)
    assert verify_results(directory)["result"] == "HIGH_RATE30_SIMULATION_VERIFIED"


@pytest.mark.parametrize("prefix", [
    "HIGH_RATE30_PASS", "HIGH_RATE30_PREROLL_PASS", "HIGH_RATE30_PREFIX", "HIGH_RATE30_OVERLAP",
    "HIGH_RATE30_STOP", "HIGH_RATE30_RETENTION_PASS", "NATIVE30_BUDGET_PASS", "NATIVE30_ADMISSION",
    "HIGH_RATE30_PIL1_SNAPSHOT", "NATIVE30_PACKET_WORD", "HIGH_RATE30_PILOT_WORD",
])
@pytest.mark.parametrize("mutation", ["missing", "duplicate"])
def test_parser_rejects_every_missing_duplicate_receipt(tmp_path, prefix, mutation):
    directory = tmp_path / "parser_only"
    log = parser_only_specimen(directory)
    line = next(line for line in log.splitlines() if line.startswith(prefix + " "))
    changed = log.replace(line + "\n", "", 1) if mutation == "missing" else log + line + "\n"
    (directory / "simulate.log").write_text(changed)
    with pytest.raises(ValueError):
        verify_results(directory)


@pytest.mark.parametrize("before,after", [
    ("source=12303 ingress=12303", "source=12302 ingress=12303"),
    ("enabled_raw=7250", "enabled_raw=8206"), ("canonical=3618", "canonical=4096"),
    ("visible_scores=894", "visible_scores=1342"), ("admitted_scores=894", "admitted_scores=895"),
    ("forward_input=1536", "forward_input=1023"), ("inverse=1024", "inverse=3585"),
    ("capture_actual_fft=20", "capture_actual_fft=0"),
    ("compute_after_stop=10000", "compute_after_stop=0"),
    ("bank_quiet_fast_cycles=50000", "bank_quiet_fast_cycles=31"),
    ("source_at_map_release=9040", "source_at_map_release=12303"),
    ("post_capture_cycles=20700", "post_capture_cycles=28001"),
    ("engine_cycles=19911", "engine_cycles=24001"),
    ("maximum_axi_cycles=7", "maximum_axi_cycles=25"),
    ("capture_start=17179870128", "capture_start=17179870129"),
    ("lead=926", "lead=127"), ("native_result_released=1", "native_result_released=0"),
    ("pilot_all=602", "pilot_all=601"), ("pilot=200", "pilot=512"),
    ("generation=1 raw_words=", "generation=2 raw_words="),
])
def test_parser_rejects_coordinate_budget_source_pilot_native_mutants(tmp_path, before, after):
    directory = tmp_path / "parser_only"
    log = parser_only_specimen(directory)
    assert before in log
    (directory / "simulate.log").write_text(log.replace(before, after))
    with pytest.raises(ValueError):
        verify_results(directory)


@pytest.mark.parametrize("fault", ["ERROR: vendor failed", "FATAL: XFFT", "HIGH_RATE30_FAIL bad tuple", "NATIVE30_BUDGET_FAIL expiry"])
def test_parser_rejects_failure_even_with_healthy_terminal(tmp_path, fault):
    directory = tmp_path / "parser_only"
    log = parser_only_specimen(directory)
    (directory / "simulate.log").write_text(log + fault + "\n")
    with pytest.raises(ValueError, match="failure evidence"):
        verify_results(directory)


@pytest.mark.parametrize("name", ["native30_actual_raw_tuples.txt", "paired_pilot_actual.ci16"])
def test_parser_rejects_changed_actual_raw_tuple_or_binary(tmp_path, name):
    directory = tmp_path / "parser_only"
    parser_only_specimen(directory)
    data = bytearray((directory / name).read_bytes())
    data[0] ^= 1
    (directory / name).write_bytes(data)
    with pytest.raises(ValueError):
        verify_results(directory)


@pytest.mark.parametrize("value", ["32'bx", "32'bz", "32'h00000001"])
def test_exact_new_health_task_rejects_unknown_counter_boundary(tmp_path, value):
    # Isolated ASSERTION test: the actual new task body is copied verbatim,
    # and its observation boundary is directly driven. No hierarchy force and
    # no claim of a live hardware fault or functioning FFT/PIL/native system.
    bench = (ACQ / "tb/tb_starlink_pss_30_bank_native_paired.sv").read_text()
    first = bench.index("  task automatic healthy;")
    last = bench.index("  endtask", first) + len("  endtask")
    task = bench[first:last]
    names = [
        "detector_health_flags", "ddc_discontinuity_count", "ddc_saturation_event_count",
        "discontinuity_abort_count", "discarded_score_count", "map_counter_fault", "map_overrun_count",
        "score_protocol_error_count", "map_arithmetic_overflow_count", "map_read_error_count", "map_release_error_count",
        "ingress_overflow_sticky", "ingress_dropped_sample_count",
    ]
    assert all(task.count("dut." + name) == 1 for name in names)
    declarations = "\n".join(f"wire [31:0] {name} = {'counter' if name == 'ddc_discontinuity_count' else '0'};" for name in names)
    source = f"""`timescale 1ns/1ps
      module observation(input [31:0] counter);
        {declarations}
        control_observation phase_map_control();
      endmodule
      module control_observation;
        wire [31:0] bridge_read_error_count=0,bridge_release_error_count=0,snapshot_request_overrun_count=0;
      endmodule
      module pilot_observation;
        wire [31:0] faults=0,ddc_fault=0,ddc_clips=0;
      endmodule
      module assertion_probe;
        reg [31:0] counter=0;
        wire canonical_flush=0,pilot_irq=0;
        observation dut(counter); pilot_observation pilot();
        task automatic fail(input string message);
          $display("ASSERTION_BOUNDARY_REJECT %s",message); $fatal(1,"expected rejection");
        endtask
        {task}
        initial begin #1; healthy(); counter={value}; #1; healthy();
          $display("ASSERTION_BOUNDARY_UNEXPECTED_ACCEPT"); $finish; end
      endmodule\n"""
    path = tmp_path / "assertion.sv"
    path.write_text(source)
    compiled = subprocess.run(["iverilog", "-g2012", "-s", "assertion_probe", "-o", str(tmp_path / "probe.vvp"), str(path)],
                              capture_output=True, text=True, timeout=30, check=False)
    assert compiled.returncode == 0, compiled.stderr
    result = subprocess.run(["vvp", str(tmp_path / "probe.vvp")], capture_output=True, text=True, timeout=30, check=False)
    (tmp_path / "assertion.log").write_text(result.stdout + result.stderr)
    assert result.returncode != 0 and "ASSERTION_BOUNDARY_REJECT" in result.stdout
    assert "ASSERTION_BOUNDARY_UNEXPECTED_ACCEPT" not in result.stdout


@pytest.fixture
def bundle(tmp_path):
    output = tmp_path / "prepared"
    freeze(COHORT, output, ROOT / "build/native30-budget-v1")
    verify_bundle(output)
    return output


def runner_probe(arguments, prelude="", env=None):
    # Tcl stubs are only command-policy tests. No Vivado binary is executed.
    script = 'proc version {args} {return 2022.2}\n' + prelude
    script += "\nset argv [list " + " ".join(f"{{{x}}}" for x in arguments) + "]\n"
    script += f"set argc [llength $argv]\nif {{[catch {{source {{{ACQ / 'simulate_high_rate_bank_native_paired.tcl'}}}}} message]}} {{puts stderr $message; exit 2}}\n"
    return subprocess.run(["tclsh"], input=script, capture_output=True, text=True, timeout=30, check=False, env=env)


def test_runner_admission_stops_before_actual_ip_with_after_integrity(bundle, tmp_path):
    output = tmp_path / "run"
    result = runner_probe([output, bundle, sys.executable], """
      proc set_param {name value} {if {$name ne "general.maxThreads" || $value ne "2"} {error BAD_THREAD_BOUND}}
      proc create_project {args} {error POLICY_ONLY_ADMITTED_NO_IP}
      proc close_project {args} {}
    """)
    (tmp_path / "runner.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 2 and result.stderr.strip() == "POLICY_ONLY_ADMITTED_NO_IP"
    assert "integrity_exit=0" in (output / "after_integrity.txt").read_text()
    assert "run_tcl_exit=1" in (output / "run_status.txt").read_text()
    assert not (output / "terminal_receipt.json").exists()
    assert verify_bundle(output / "inputs") == verify_bundle(bundle)


def test_runner_sanitizes_python_subprocess_without_mutating_parent(bundle, tmp_path):
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
    result = runner_probe([output, bundle, sys.executable], prelude, env=environment)
    assert result.returncode == 2 and result.stderr.strip() == "POLICY_ONLY_PARENT_ENV_PRESERVED"
    assert "integrity_exit=0" in (output / "after_integrity.txt").read_text()


@pytest.mark.parametrize("extra", ["30", "60", "343x2", "200"])
def test_runner_has_no_alternate_rate_geometry_or_clock_entry(bundle, tmp_path, extra):
    output = tmp_path / "run"
    result = runner_probe([output, bundle, sys.executable, extra])
    assert result.returncode == 2 and "no alternate rate/geometry" in result.stderr
    assert not output.exists()


def test_runner_no_overwrite(bundle, tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    result = runner_probe([output, bundle, sys.executable])
    assert result.returncode == 2 and "refusing to overwrite" in result.stderr
    assert not list(output.iterdir())


@pytest.mark.parametrize("mutation", ["source", "signature", "closure", "runner"])
def test_bundle_and_runner_reject_before_project_mutations(bundle, tmp_path, mutation):
    path = bundle / "bundle.json"
    receipt = json.loads(path.read_text())
    name = "hdl/library/starlink_pss_acquisition/simulate_high_rate_bank_native_paired.tcl"
    if mutation in {"source", "runner"}:
        source = bundle / "source_snapshot" / name
        source.write_text(source.read_text() + "\n# MUTANT\n")
        if mutation == "runner":
            # Self-consistent altered bundle must still fail entry-byte match.
            receipt["files"]["source_snapshot/" + name] = sha(source.read_bytes())
            receipt["source_sha256"][name] = sha(source.read_bytes())
    elif mutation == "signature":
        receipt["source_sha256"][name] = "0" * 64
    else:
        receipt["source_sha256"].pop(name)
    if mutation != "source":
        from tests.starlink_oracle.high_rate_harness import encoded
        receipt["source_signature"] = sha(encoded(receipt["source_sha256"]))
        path.write_bytes(encoded(receipt))
    result = runner_probe([tmp_path / "run", bundle, sys.executable])
    assert result.returncode == 2
    assert not (tmp_path / "run").exists()
    if mutation == "runner":
        assert "runner differs" in result.stderr


@pytest.mark.parametrize("damage", [False, True])
def test_runner_launch_failure_preserves_error_and_post_source_receipt(bundle, tmp_path, damage):
    # Minimal command stubs reach launch and deliberately fail. No numeric PASS
    # is synthesized and neither generate_target nor a vendor process runs.
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
    result = runner_probe([output, bundle, sys.executable], prelude)
    (tmp_path / "runner.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 2 and result.stderr.strip() == "POLICY_ONLY_ORIGINAL_LAUNCH_ERROR"
    assert f"integrity_exit={int(damage)}" in (output / "after_integrity.txt").read_text()
    assert "POLICY_ONLY_ORIGINAL_LAUNCH_ERROR" in (output / "run_status.txt").read_text()
    assert not (output / "terminal_receipt.json").exists()

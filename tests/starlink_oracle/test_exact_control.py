"""Two default-off exact-control experiments; no vendor FFT or physical run."""
import itertools
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.exact_control_contract import BASE, restore_exact_control

HDL = Path(__file__).resolve().parents[2] / "hdl"
ACQ = HDL / "library/starlink_pss_acquisition"
TB = ACQ / "tb"
KINDS = ("fft_bank_owned_slice", "realtime_input_guard", "realtime_result_guard",
         "block_mailbox", "forward_kernel_join", "kernel_rom", "spectrum_product")


def frozen(relative):
    return subprocess.run(["git", "-C", str(HDL), "show",
        f"{BASE}:library/starlink_pss_acquisition/{relative}"], capture_output=True,
        text=True, check=True, timeout=10).stdout


def test_literal_seven_module_inverse_and_actual_stimulus_unchanged():
    for kind in KINDS:
        name = f"starlink_pss_{kind}.v"
        source = (ACQ / name).read_text()
        assert restore_exact_control(source, kind) == frozen(name)
    name = "tb/tb_starlink_pss_fft_bank_owned_slice.sv"
    assert (ACQ / name).read_text() == frozen(name)


STUB = """module starlink_pss_fft512_bfp18_rt_candidate (
input aclk, aresetn, input [7:0] s_axis_config_tdata, input s_axis_config_tvalid,
output s_axis_config_tready, input [47:0] s_axis_data_tdata, input s_axis_data_tvalid,
output s_axis_data_tready, input s_axis_data_tlast,
output [47:0] m_axis_data_tdata, output [23:0] m_axis_data_tuser,
output m_axis_data_tvalid, m_axis_data_tlast, output [7:0] m_axis_status_tdata,
output m_axis_status_tvalid, event_frame_started, event_tlast_unexpected,
event_tlast_missing, event_data_in_channel_halt);
assign s_axis_config_tready=1; assign s_axis_data_tready=1;
assign m_axis_data_tdata=0; assign m_axis_data_tuser=0; assign m_axis_data_tvalid=0;
assign m_axis_data_tlast=0; assign m_axis_status_tdata=0; assign m_axis_status_tvalid=0;
assign event_frame_started=0; assign event_tlast_unexpected=0;
assign event_tlast_missing=0; assign event_data_in_channel_halt=0;
endmodule
"""


def run(tmp_path, top, parameters, mutation=None, bench_source=None):
    sources = []
    for kind in KINDS:
        name = f"starlink_pss_{kind}"
        current = (ACQ / f"{name}.v").read_text()
        if mutation and mutation[0] == kind:
            _, before, after = mutation
            assert current.count(before) == 1, before
            current = current.replace(before, after, 1)
        path = tmp_path / f"{name}.v"
        path.write_text(current)
        sources.append(path)
        # Independent full old bodies: no candidate predicate shared with the
        # golden wrapper, guards, ROM, banks or arithmetic.
        reference = frozen(f"{name}.v")
        for rename in KINDS:
            reference = reference.replace(f"starlink_pss_{rename}",
                                          f"starlink_pss_{rename}_dec20d63_golden")
        path = tmp_path / f"{name}_dec20d63_golden.v"
        path.write_text(reference)
        sources.append(path)
    stub = tmp_path / "quiescent_fft_stub.v"
    stub.write_text(STUB)
    sources.append(stub)
    bench = tmp_path / f"{top}.sv"
    if bench_source is None:
        shutil.copyfile(TB / bench.name, bench)
    else:
        bench.write_text(bench_source)
    sources.append(bench)
    shutil.copyfile(ACQ / "evidence/forward-retirement-physical-v1/synthesis/frozen_sources/upper_edge_pss_kernel_q17.mem",
                    tmp_path / "upper_edge_pss_kernel_q17.mem")
    executable = tmp_path / "simulation.vvp"
    result = subprocess.run(["iverilog", "-g2012", "-Wall", "-s", top,
        *[f"-P{top}.{item}" for item in parameters], "-o", str(executable), *map(str, sources)],
        cwd=tmp_path, capture_output=True, text=True, timeout=30, check=False)
    (tmp_path / "compile.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run(["vvp", str(executable)], cwd=tmp_path,
        capture_output=True, text=True, timeout=90, check=False)
    log = result.stdout + result.stderr
    (tmp_path / "simulate.log").write_text(log)
    return result.returncode, log


@pytest.mark.parametrize("distributed,scratch,registered", list(itertools.product((0, 1), repeat=3)))
def test_all_options_whole_frozen_wrapper_exhaustive_causes_reasons_resets_and_x(
        tmp_path, distributed, scratch, registered):
    rc, log = run(tmp_path, "tb_starlink_pss_exact_fault_ledger", [
        f"DISTRIBUTED={distributed}", f"SCRATCH={scratch}", f"REGISTERED={registered}"])
    assert rc == 0 and "EXACT_LEDGER_PASS" in log, log
    assert "masks=4096 x_rows=156" in log and "quiescent_stub_not_fft=1" in log


@pytest.mark.parametrize("scratch,balanced", list(itertools.product((0, 1), repeat=2)))
def test_full_rom_public_state_all64bit_corruptions_wrap_stalls_bubbles_reset(tmp_path, scratch, balanced):
    rc, log = run(tmp_path, "tb_starlink_pss_next_start_scratch", [
        f"SCRATCH={scratch}", f"BALANCED={balanced}"])
    assert rc == 0 and "NEXT_SCRATCH_PASS" in log, log
    assert "bit_rows=128" in log and "frozen_all_public_and_other_state=1" in log


@pytest.mark.parametrize("cause", range(12))
def test_every_omitted_distributed_cause_is_rejected(tmp_path, cause):
    change = ("fft_bank_owned_slice", "else if (causes_now[cause_index])",
              f"else if (cause_index != {cause} && causes_now[cause_index])")
    rc, log = run(tmp_path, "tb_starlink_pss_exact_fault_ledger", ["DISTRIBUTED=1"], change)
    assert rc != 0 and "EXACT_LEDGER_MISMATCH" in log, log


@pytest.mark.parametrize("mutation", ["not_sticky", "wrong_reset", "x_or"])
def test_bad_recurrence_reset_and_four_state_mutants_are_rejected(tmp_path, mutation):
    before = "else if (causes_now[cause_index]) cause_sticky[cause_index] <= 1;"
    if mutation == "not_sticky":
        # Preserve unknown startup; target loss of stickiness in an initialized
        # running epoch, rather than its earlier uninitialized fence mismatch.
        after = before + "\n        else if (fast_running === 1'b1) cause_sticky[cause_index] <= 0;"
    elif mutation == "wrong_reset":
        before = "if (!fast_running) cause_sticky[cause_index] <= 0;"
        after = "if (!fast_running) cause_sticky[cause_index] <= 1;"
    else:
        after = "else cause_sticky[cause_index] <= cause_sticky[cause_index] | causes_now[cause_index];"
    rc, log = run(tmp_path, "tb_starlink_pss_exact_fault_ledger", ["DISTRIBUTED=1"],
                  ("fft_bank_owned_slice", before, after))
    assert rc != 0 and "EXACT_LEDGER_MISMATCH" in log, log


@pytest.mark.parametrize("mutation", ["overwrite_start", "overwrite_stall", "omit_bit63", "wrong_stride"])
def test_unsafe_scratch_overwrite_truncation_and_stride_mutants_are_rejected(tmp_path, mutation):
    before = "if (PRIVATE_NEXT_START_SCRATCH && input_ready && expected_bin_index == 9'd511)"
    expected = "NEXT_SCRATCH_CONSUMED_IDENTITY_MISMATCH"
    if mutation == "overwrite_start":
        after = "if (PRIVATE_NEXT_START_SCRATCH && input_ready)"
    elif mutation == "overwrite_stall":
        after = "if (PRIVATE_NEXT_START_SCRATCH && expected_bin_index == 9'd511)"
        expected = "NEXT_SCRATCH_OCCUPIED_HOLD_MISMATCH"
    else:
        before = "expected_next_block_start <= input_block_start_index + VALID_RESULTS_PER_BLOCK;"
        after = "expected_next_block_start <= " + (
            "{1'b0,input_block_start_index[62:0]} + VALID_RESULTS_PER_BLOCK;" if mutation == "omit_bit63"
            else "input_block_start_index + 448;")
    rc, log = run(tmp_path, "tb_starlink_pss_next_start_scratch", ["SCRATCH=1", "BALANCED=1"],
                  ("kernel_rom", before, after))
    assert rc != 0 and expected in log, log


@pytest.mark.parametrize("kind,parameter", [
    ("fft_bank_owned_slice", "DISTRIBUTED_FAST_FAULT"),
    ("fft_bank_owned_slice", "PRIVATE_NEXT_START_SCRATCH"),
    ("forward_kernel_join", "PRIVATE_NEXT_START_SCRATCH"),
    ("kernel_rom", "PRIVATE_NEXT_START_SCRATCH"),
])
@pytest.mark.parametrize("invalid", [-1, 2, "32'bx", "32'bz"])
def test_each_public_parameter_entry_rejects_invalid_values(tmp_path, kind, parameter, invalid):
    # Make child entries valid to establish EACH selected entry's own guard,
    # rather than accidentally relying on a child's parameter check.
    child = {"fft_bank_owned_slice": "defparam dut.joiner.PRIVATE_NEXT_START_SCRATCH=0;",
             "forward_kernel_join": "defparam dut.kernel_rom.PRIVATE_NEXT_START_SCRATCH=0;",
             "kernel_rom": ""}[kind]
    file_parameter = "ROM_FILE" if kind == "kernel_rom" else "KERNEL_ROM_FILE"
    bench = f'''module invalid_knob;
starlink_pss_{kind} #(.{parameter}({invalid}), .{file_parameter}("upper_edge_pss_kernel_q17.mem")) dut ();
{child}
initial begin #10; $fatal(1,"INVALID_KNOB_WAS_ACCEPTED"); end
endmodule
'''
    rc, log = run(tmp_path, "invalid_knob", [], bench_source=bench)
    assert rc != 0 and f"{parameter} must be zero or one" in log, log
    assert "INVALID_KNOB_WAS_ACCEPTED" not in log

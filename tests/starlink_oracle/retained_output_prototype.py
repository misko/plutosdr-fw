"""Source-frozen, non-vendor retained-reader control prototype tooling."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RTL = ROOT / "hdl/library/starlink_pss_acquisition/retained_output"
BASELINE = RTL / "baseline"
PINS = {
    "starlink_pss_block_mailbox.v": "e85122eb6689ff49b31aa5a0c200e2666786629055b4f45856fe79fb829dbb55",
    "starlink_pss_fft_bank_owned_local_admission_probe.v": "0cb54617eb6757e1d6c719d97b0fd5002ec7f6105c8c4b50c41eba67d4306235",
    "starlink_pss_forward_kernel_join.v": "87e40b3cc9025502c05d2afbd6b0d9658618cd7204d4fd8ddc3f0ba74e68843a",
    "starlink_pss_kernel_rom.v": "0b4ee87d93d61c6fa12ee9992aa517a3a8be568835075531d9af4453f4ec80e5",
    "starlink_pss_realtime_input_guard.v": "eb1f968a30ae0371421cfb0766c7f8bf0c23411e730717cd0d4924be0604109e",
    "starlink_pss_realtime_input_guard_local_admission.v": "55438743eede0d346cec67351e079eb6ae21da437d4088a131a2a258b43ff233",
    "starlink_pss_realtime_result_guard.v": "09ab35339d55ddf88e813830322d21574d0794c489c9749f68113e9da7807be2",
    "starlink_pss_spectrum_product_bank_arithmetic.v": "515d29534dab921601c37564ad8a9957eed9befb9dff2e1c8c5f1f79fc6b5f70",
    "starlink_pss_spectrum_product_operand_register.v": "dead8e465b4bd982cebcab0c4a4e7eb4f3b20c038938f74c7663a79e0779893d",
    "forward_exponents.mem": "18ac6df6a1ae3f19e5153524b33f336a60eabdd6dbd182d46c43450302e4b52f",
    "forward_q17.mem": "d934a8ecd0888c294fc0abfbdbe7c439bff7097ea169b937638c4b7000479bfd",
    "inverse_exponents.mem": "899b7a2486fd3759c6e4905110fc4d86ffdb6ec884da2a7f2aca4acdfd363dff",
    "inverse_q17.mem": "c8c5b4e28ab621d0b1d5c1dc288f6e66495b3319d348442ce5d7b8f6ea8025a1",
    "product_q17.mem": "b316522a68529a73d3d8e4121badea61e24621c93a97365e894f5bd416bcecb7",
    "samples_ci16.mem": "4abe27ba953cf49f84d9979966625a2436ad59359b616321e881b42dd4c84723",
    "scores_u8.mem": "c22f751a2a82244268dd9ea4989c4ff3b5364c172526e80886c5da3d1959e45d",
    "upper_edge_pss_kernel_q17.mem": "694d0d9b8dd55368bcaaedec37a7cda3a837d491d592ede60eec57a9821fc99a",
}


def verify_baseline() -> None:
    for name, expected in PINS.items():
        if hashlib.sha256((BASELINE / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"immutable baseline changed: {name}")


def inverse_view(text: str, kind: str) -> str:
    """Literal whole-body inverse. No regex deletion or broad projection."""
    if kind == "guard":
        old = "starlink_pss_realtime_result_guard"
        new = "starlink_pss_result_guard_owner_view"
        added_ports = ",\n  output wire owner_active, owner_awaiting_ack, owner_fault_now, owner_ack_accept"
        anchor = "  output reg [7:0] fault_reasons"
        added = """  // BEGIN RETAINED OWNER OBSERVATIONS: no state or control changes.
  assign owner_active = active;
  assign owner_awaiting_ack = awaiting_ack;
  assign owner_fault_now = fault_now;
  assign owner_ack_accept = awaiting_ack && mailbox_input_ready && !protocol_fault && !idle_fault_now;
  // END RETAINED OWNER OBSERVATIONS
"""
    elif kind == "mailbox":
        old = "starlink_pss_block_mailbox"
        new = "starlink_pss_mailbox_owner_view"
        added_ports = ",\n  output wire owner_request, owner_ack_sync,\n  output wire writer_reset_idle, reader_reset_idle"
        anchor = "  output wire [METADATA_WIDTH-1:0] output_metadata"
        added = """  // BEGIN RETAINED MAILBOX OBSERVATIONS: no state or control changes.
  assign owner_request = request_toggle;
  assign owner_ack_sync = acknowledge_sync[1];
  assign writer_reset_idle = request_toggle === 1'b0 && acknowledge_sync === 2'b0 &&
    write_position === {ADDRESS_WIDTH{1'b0}} && input_fault === 1'b0;
  assign reader_reset_idle = acknowledge_toggle === 1'b0 && request_sync === 2'b0 &&
    reading === 1'b0 && read_all_loaded === 1'b0 &&
    read_address === {ADDRESS_WIDTH{1'b0}} && read_valid === 1'b0;
  // END RETAINED MAILBOX OBSERVATIONS
"""
    else:
        raise ValueError("view kind")
    for needle in (f"module {new}", anchor + added_ports, added):
        if text.count(needle) != 1:
            raise ValueError(f"strict {kind} inverse boundary")
    restored = text.replace(f"module {new}", f"module {old}", 1).replace(
        anchor + added_ports, anchor, 1
    ).replace(added, "", 1)
    if restored != (BASELINE / f"{old}.v").read_text():
        raise ValueError(f"strict {kind} whole-body mismatch")
    return restored


def run_sv(directory: Path, text: str, sources: list[Path], *, parameters=(), expected_failure=None) -> str:
    """Icarus only, bounded process, complete diagnostics preserved per attempt."""
    directory.mkdir(parents=True, exist_ok=False)
    bench = directory / "test.sv"
    bench.write_text(text)
    compile_command = ["iverilog", "-g2012", "-s", "tb", "-o", str(directory / "sim.vvp")]
    compile_command += list(parameters) + [str(bench)] + [str(path) for path in sources]
    compiled = subprocess.run(compile_command, capture_output=True, text=True, timeout=30)
    (directory / "compile.log").write_text(compiled.stdout + compiled.stderr)
    if compiled.returncode:
        raise AssertionError(f"compile exit {compiled.returncode}: {compiled.stderr}")
    result = subprocess.run(["vvp", str(directory / "sim.vvp")], cwd=BASELINE,
                            capture_output=True, text=True, timeout=30)
    (directory / "simulation.log").write_text(result.stdout + result.stderr)
    (directory / "exit.txt").write_text(f"compile={compiled.returncode}\nsimulation={result.returncode}\n")
    if expected_failure is not None:
        if result.returncode == 0 or expected_failure not in result.stdout or "OFFLINE_PASS" in result.stdout:
            raise AssertionError(f"missing expected failure: {result.stdout}{result.stderr}")
        return result.stdout
    if result.returncode or "OFFLINE_PASS" not in result.stdout:
        raise AssertionError(f"offline exit {result.returncode}: {result.stdout}{result.stderr}")
    return result.stdout


def composition_sources() -> list[Path]:
    verify_baseline()
    return sorted(BASELINE.glob("*.v")) + sorted(RTL.glob("*.v")) + [
        RTL / "tb/scripted_fft_ports.sv", RTL / "tb/retained_clock_witness.sv"]


GUARD_STATE = (
    "active_private awaiting_ack descriptor input_count output_count input_complete_seen "
    "frame_seen status_seen exponent_seen status_exponent output_exponent age "
    "return_occupied return_last return_data return_position return_exponent commit_pulse fault_reasons"
).split()


def guard_equivalence_bench() -> str:
    """Unconditional outputs and all original state, using untouched adversarial stimulus."""
    source = (BASELINE / "starlink_pss_realtime_result_guard.v").read_text()
    ports = source[source.index(") (\n") + 4:source.index("\n);")]
    inputs = re.findall(r"input wire (?:\[[^]]+\] )?(\w+)", ports)
    outputs = re.findall(r"output (?:wire|reg) (?:\[[^]]+\] )?(\w+)", ports)
    assert len(inputs) == 25 and len(outputs) == 13
    connections = ",\n".join(f".{name}(stimulus.dut.{name})" for name in inputs)
    checks = "\n".join(
        f'if(shadow.{name} !== stimulus.dut.{name}) $fatal(1,"unconditional guard {name}");'
        for name in dict.fromkeys(outputs + GUARD_STATE)
    )
    return f"""`timescale 1ns/1ps
module tb;
  tb_starlink_pss_realtime_result_guard stimulus();
  starlink_pss_result_guard_owner_view #(.WATCHDOG_CYCLES(2048)) shadow({connections});
  integer comparisons=0;
  always @(posedge stimulus.clk or negedge stimulus.clk)begin
    #0.001;{checks}
    if({{shadow.owner_active,shadow.owner_awaiting_ack,shadow.owner_fault_now,shadow.owner_ack_accept}} !==
      {{stimulus.dut.active,stimulus.dut.awaiting_ack,stimulus.dut.fault_now,
      (stimulus.dut.awaiting_ack&&stimulus.dut.mailbox_input_ready&&!stimulus.dut.protocol_fault&&!stimulus.dut.idle_fault_now)}})
      $fatal(1,"guard added owner observations");
    comparisons=comparisons+1;
  end
  final begin
    if(stimulus.healthy!=23||stimulus.rejected!=37||stimulus.reset_cases!=12||comparisons<10000)
      $fatal(1,"unchanged adversarial inventory");
    $display("OFFLINE_PASS unconditional exact guard/state healthy23 rejected37 reset12 comparisons=%0d",comparisons);
  end
endmodule
"""


def composition_bench() -> str:
    """Read-only exact guard references on both actual owner input interfaces."""
    text = (RTL / "tb/tb_retained_composition.sv").read_text()
    if text.count("endmodule") != 1:
        raise ValueError("composition module boundary")
    source = (BASELINE / "starlink_pss_realtime_result_guard.v").read_text()
    ports = source[source.index(") (\n") + 4:source.index("\n);")]
    inputs = re.findall(r"input wire (?:\[[^]]+\] )?(\w+)", ports)
    outputs = re.findall(r"output (?:wire|reg) (?:\[[^]]+\] )?(\w+)", ports)
    assert len(inputs) == 25 and len(outputs) == 13
    extra = "\n  // Test-only unconditionally sampled baseline guards; no DUT feedback.\n"
    for owner in [0, 1]:
        actual = f"dut.retained.island.owners[{owner}].result_guard"
        shadow = f"baseline_guard_{owner}"
        connections = ",\n".join(f".{name}({actual}.{name})" for name in inputs)
        checks = "\n".join(
            f'if({shadow}.{name} !== {actual}.{name}) $fatal(1,"unconditional owner{owner} {name}");'
            for name in dict.fromkeys(outputs + GUARD_STATE)
        )
        extra += f"""  starlink_pss_realtime_result_guard #(.USE_COMPLETED_INPUT_FAULT(1),
    .USE_PREFLIGHT_REASON_ONLY(1),.USE_FORWARD_RETIREMENT(1)) {shadow}({connections});
  always @(posedge fft_clk or negedge fft_clk)begin #0.001;{checks} end
"""
    return text.replace("endmodule", extra + "endmodule")

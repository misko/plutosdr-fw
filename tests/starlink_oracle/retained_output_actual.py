"""Additive actual-harness derivation; preparation does not invoke vendor tools."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

from . import retained_output_prototype as original
from . import retained_completion_declaration as completion_declaration

ROOT = Path(__file__).resolve().parents[2]
RTL = ROOT / "hdl/library/starlink_pss_acquisition/retained_output_actual"
REF = RTL / "reference"
RECIPE = Path(__file__).with_name("retained_output_actual_recipe.json")
ABI = Path(__file__).with_name("retained_output_actual_abi.json")
REFERENCE_PINS = {
    "create_shared_realtime_xfft_ip.tcl": "0795ea7e6aa981d78080ac22fa4ba6355da59d6829ceb409dda07a54f7f9420d",
    "local_admission_original_guard.v": "c69e1c02cdca75780b3dd850497869899defd9a3348b66c522c4bf26902e5354",
    "starlink_pss_bank_arithmetic_shadow.sv": "c58e50c6853cd0519f018b4c362e70aabcf6d157a414f6b6748b49496aec01ad",
    "starlink_pss_forward_kernel_join_7ee87258_golden.v": "eb2e28fd92ccf7b28d0adf68da09ac761a55ca6fdddc507187680c3ef1d857da",
    "starlink_pss_forward_retirement_shadow.sv": "8ed19931be00db932b52d5bf57015168a185e31987db1af8924ba1c93774702b",
    "starlink_pss_kernel_rom_7ee87258_golden.v": "00e27e3a506c0a21510de18baba5c6d014fdb2a43ff352f1481438432e1d3c35",
    "starlink_pss_local_admission_actual_checks.svh": "4c8f2d7260072355808370cdc2eb448cfee17a916b127f6875aab2f6cdfe6a66",
    "starlink_pss_local_admission_actual_observer.sv": "a8057de409efcbf19680595c20ce5c2cc7ae7213ff459f7dd7ed162dc7b46551",
    "starlink_pss_payload_bubble_shadow.sv": "f151676631d6fdd1290e91a285063114010ab0c8103ecf754b2be618d11409a3",
    "starlink_pss_realtime_result_guard_ce6a885e_golden.v": "b406adf0af7bee95594a62b8929ae8743f60b17c9f55798f2977f485ee068e5f",
    "starlink_pss_spectrum_product_7ee87258_golden.v": "c79a1f2f4356c20cd615e963cebb28dbcca7b1cf809691165e2f30debc7f58c9",
    "tb_starlink_pss_local_admission_actual.sv": "a347cd6ec4bb3e888f0ce171aedb7c4a85cebea4932bc880f348a75ada5ae238",
}
TEMPLATE_SHA = "465ce7c6547e0c3ca9bed11ca352998924e23aab4b7c7b826e66bddd31b22e0d"
HELPER_SHA = "0066ae35105d57dfd3e7c924e036c4d518102853c6eb8ecde1c254ad9c2e3488"
RECIPE_SHA = "ba063c99010f1a43d64db52fb9fd86e040b499a0730d70714f74a507e5b3a94e"
ABI_SHA = "caea9439cf00e9aa49b979c475f6865a885138558b9c00a231472d9198d25983"
FROZEN46_SHA = "a4dfa8d603d1d7782b51106c6224a3dc6dfbc67d07e241abac8d7c390f83aeb8"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_originals() -> None:
    original.verify_baseline()
    pins = {REF / n: v for n, v in REFERENCE_PINS.items()}
    pins[original.RTL / "tb/tb_retained_composition.sv"] = TEMPLATE_SHA
    pins[Path(original.__file__)] = HELPER_SHA
    pins[RECIPE] = RECIPE_SHA
    pins[ABI] = ABI_SHA
    pins[REF / "frozen46.sha256"] = FROZEN46_SHA
    for path, expected in pins.items():
        if path.is_symlink() or sha(path) != expected:
            raise ValueError(f"original/source identity: {path.name}")
    lines = (REF / "frozen46.sha256").read_text().splitlines()
    if len(lines) != 46:
        raise ValueError("original46 source closure")
    for line in lines:
        expected, name = line.split(maxsplit=1)
        if not name.startswith("source/") or ".." in Path(name).parts:
            raise ValueError("original46 relative source path")
        path = ROOT / name.removeprefix("source/")
        actual_sha = sha(path)
        if name.removeprefix("source/") == completion_declaration.PATH:
            if expected != completion_declaration.ORIGINAL_SHA:
                raise ValueError("completion original source pin")
            restored = completion_declaration.inverse(path.read_text())
            actual_sha = hashlib.sha256(restored.encode()).hexdigest()
        if path.is_symlink() or actual_sha != expected:
            raise ValueError(f"original46 source changed: {name}")


def _block(text: str, begin: str, end: str) -> str:
    if text.count(begin) != 1 or text.count(end) != 1:
        raise ValueError("literal block boundary")
    return text[text.index(begin):text.index(end) + len(end)]


def bindings() -> str:
    """Literal unchanged reference bodies; named binding-only adapters."""
    verify_originals()
    old = (REF / "tb_starlink_pss_local_admission_actual.sv").read_text()
    payload = _block(old, "  // BEGIN PAYLOAD_BUBBLE_SHADOW", "  // END PAYLOAD_BUBBLE_SHADOW")
    forward = _block(old, "  // BEGIN FORWARD_RETIREMENT_SHADOW", "  // END FORWARD_RETIREMENT_SHADOW")
    start = forward.index("  starlink_pss_forward_retirement_shadow #")
    stop = forward.index("\n  );", start) + len("\n  );")
    old_instance = forward[start:stop]
    guard = "`D.owners[0].result_guard"
    inputs = "clk resetn job_valid job_descriptor input_bank_reserved output_bank_reserved certified_input_beat certified_input_complete final_fence_certified external_fault_now phase_input_fault_now completed_input_certified completed_input_fault_now preflight_fault_evidence_now core_event_frame_started core_output_tdata core_output_tuser core_output_tvalid core_output_tlast core_status_tdata core_status_tvalid mailbox_input_ready mailbox_input_fault".split()
    ports = [f".{p}({guard}.{p})" for p in inputs]
    public = "job_ready mailbox_input_valid mailbox_private_valid mailbox_commit_valid mailbox_input_data mailbox_input_position mailbox_input_last mailbox_input_metadata busy commit_pulse protocol_fault fault_reasons".split()
    ports += [".inverse_phase(1'b0)", f".forward_mailbox_fault({guard}.forward_mailbox_fault)",
              ".mailbox_current_fault_now(`D.output_bank_framing_fault_now)",
              ".actual_public({" + ",".join(f"{guard}.{p}" for p in public) + "})",
              ".actual_forward_valid(`D.forward_retirement_valid)", ".old_valid(forward_old_valid)",
              ".old_private_valid(forward_old_private)", ".checks(forward_checks)",
              ".forward_cycles(forward_cycles)", ".inverse_current_faults(forward_current)",
              ".sticky_forward_faults(forward_sticky)"]
    new_instance = "  starlink_pss_forward_retirement_shadow #(.ENABLED(1),.COMPLETED(1),.PREFLIGHT(1)) forward_shadow (\n    " + ",\n    ".join(ports) + "\n  );"
    adapted_forward = forward.replace(old_instance, new_instance, 1)
    # Named hierarchical binding substitutions only; reconstruct the entire old block.
    adapted_forward = adapted_forward.replace("dut.", "`D.")
    restored = adapted_forward.replace(new_instance, old_instance, 1).replace("`D.", "dut.")
    if restored != forward:
        raise ValueError("complete forward binding inverse")
    adapted_payload = payload.replace("dut.", "`D.")
    if adapted_payload.replace("`D.", "dut.") != payload:
        raise ValueError("complete arithmetic binding inverse")
    input_old = (REF / "starlink_pss_local_admission_actual_checks.svh").read_text()
    input_new = input_old.replace("dut.", "`D.")
    if input_new.replace("`D.", "dut.") != input_old:
        raise ValueError("complete input binding inverse")
    return "\n  localparam O=1,R=1,B=1,L=1,FAST_MHZ=175,QUICK_MUTATION=0,REGISTERED_SCHEDULING=1;\n" + adapted_payload + "\n" + adapted_forward + "\n" + input_new


def adaptations() -> list[tuple[str, str]]:
    source = original.composition_bench()
    fault = source[source.index("  initial if(FAULT_KIND!=0)begin : fault_stimulus"):source.index("  `undef D")]
    old_finish = ';$finish;\n  end\n  initial begin #9000000;'
    return [
        ("// OFFLINE_NOT_FFT: real unchanged arithmetic/mailboxes, scripted FFT ports.", "// Additive actual harness: real generated FFT required for actual qualification."),
        ("  parameter integer STALL=0;", "  integer STALL=0;"),
        ("  parameter integer RESET_SIDE=0,BLOCKS=3;", "  integer RESET_SIDE=0;localparam BLOCKS=3;"),
        ("  parameter real SLOW_PHASE=1.3;", "  localparam real SLOW_PHASE=1.3;"),
        ("  initial begin\n    $readmemh", "  task automatic run_context;begin\n    $readmemh"),
        ("`D.shared_xfft.input_count>=64", "actual_inputs>=64"),
        ("@(negedge clk);run_slow=0;", '@(negedge clk);run_slow=0;\n        $display("RACT_SLOW_PAUSE context=%0d slow=%0d fast=%0d time_fs=%0.0f",context_id,slow_edges,fast_cycles,$realtime*1000000.0);'),
        ("resume_edge=slow_edges;run_slow=1;wait(`D.fast_running);", 'resume_edge=slow_edges;run_slow=1;\n        $display("RACT_SLOW_RESUME context=%0d slow=%0d fast=%0d time_fs=%0.0f",context_id,slow_edges,fast_cycles,$realtime*1000000.0);\n        wait(`D.fast_running);'),
        (old_finish, ';\n  end endtask\n  initial begin #9000000;'),
        (fault, "  // Script-only injected-fault process absent in the seven approved contexts.\n"),
        ("SCRIPTED_NOT_FFT source=", "DERIVED_CONTEXT source="),
        ("  `undef D", bindings() + "\n" + (RTL / "witness.svh").read_text() + "\n" + (RTL / "context.svh").read_text() + "\n  `undef D"),
    ]


def actual_bench() -> str:
    verify_originals()
    text = original.composition_bench()
    for old, new in adaptations():
        if text.count(old) != 1:
            raise ValueError(f"actual literal adaptation: {old[:60]}")
        text = text.replace(old, new, 1)
    inverse_bench(text)
    return text


def inverse_bench(text: str) -> str:
    for old, new in reversed(adaptations()):
        if text.count(new) != 1:
            raise ValueError("actual complete-source inverse boundary")
        text = text.replace(new, old, 1)
    if text != original.composition_bench():
        raise ValueError("actual complete-source inverse mismatch")
    return text


def scripted_padding_adapter() -> str:
    """Offline only: documented output ABI, unchanged numerical/timing script."""
    old = (original.RTL / "tb/scripted_fft_ports.sv").read_text()
    before = "assign m_axis_data_tdata={6'b0,word_out[35:18],6'b0,word_out[17:0]};"
    after = "assign m_axis_data_tdata={{6{word_out[35]}},word_out[35:18],{6{word_out[17]}},word_out[17:0]};"
    if old.count(before) != 1:
        raise ValueError("script padding adapter boundary")
    new = old.replace(before, after, 1)
    if new.replace(after, before, 1) != old:
        raise ValueError("script padding adapter inverse")
    return new


def compiled_sources() -> list[Path]:
    return sorted(original.BASELINE.glob("*.v")) + sorted(original.RTL.glob("*.v")) + [
        original.RTL / "tb/retained_clock_witness.sv",
    ] + sorted(p for p in REF.iterdir() if p.suffix in (".v", ".sv") and not p.name.startswith("tb_"))


def offline(directory: Path, *, execute=False, bench: str | None = None) -> dict:
    """Bounded Icarus compile/script proof; never a vendor service measurement."""
    verify_originals()
    directory.mkdir(parents=True, exist_ok=False)
    for path in original.BASELINE.glob("*.mem"):
        (directory / path.name).write_bytes(path.read_bytes())
    top = directory / "bench.sv"
    top.write_text(actual_bench() if bench is None else bench)
    script = directory / "OFFLINE_NOT_FFT.sv"
    script.write_text(scripted_padding_adapter())
    command = ["iverilog", "-g2012", "-s", "tb", "-o", str(directory / "sim.vvp"), str(top), str(script), *map(str, compiled_sources())]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    (directory / "compile.log").write_text(result.stdout + result.stderr)
    status = {"compile": result.returncode, "service_executed": False, "kind": "OFFLINE_SCRIPT_NOT_FFT"}
    if result.returncode == 0 and execute:
        run = subprocess.run(["vvp", "sim.vvp"], cwd=directory, capture_output=True, text=True, timeout=60)
        (directory / "simulation.log").write_text(run.stdout + run.stderr)
        status["script_exit"] = run.returncode
    (directory / "status.json").write_text(json.dumps(status, sort_keys=True) + "\n")
    return status

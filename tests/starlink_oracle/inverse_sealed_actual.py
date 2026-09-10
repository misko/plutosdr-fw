"""Source-specific inverse sealed actual-FFT preparation; never launches Vivado."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACQ = ROOT / "hdl/library/starlink_pss_acquisition"
OLD_BENCH = "tb_starlink_pss_local_admission_actual"
BENCH = "tb_starlink_pss_inverse_sealed_actual"
CHECKS = "starlink_pss_inverse_sealed_actual_checks.svh"
RUNNER = "simulate_inverse_sealed_actual.tcl"
DIAGNOSTICS = "simulate_inverse_sealed_diagnostics.tcl"
PROFILE = "inverse_sealed_profile.tcl"
ACCEPTED_MANIFEST = "1717107b5be08b9ff72e7a224cbf20a1354ddd215270a7cd1923b62e12b5d858"
ACCEPTED_RESULTS = "4938eb536dce3adfd62cd185e2868727a9843fd4ed896d0b02b1638f19bbe292"
OLD_HELPER_SHA = "eb1dc68389c12f6d0832a421b0312d32a3f528807ea21292b113b555b585654b"
RECIPE_SHA = "5ed10cbb7a73bf38efc304273f5006b501220af828bb8927c0c1dda477450818"
RUNTIME = {
    "starlink_pss_fft_bank_owned_inverse_sealed_probe.v": "2f988a16bf02c0a0032fc86049d9169393d811929236a7891513b5395c178f01",
    "starlink_pss_inverse_sealed_issuer.v": "8ad9c2e7185e4077857c8cc9ee0c27a6df75be9534ffc0bdee686ec0b89c9e67",
    "starlink_pss_epoch_sealed_bank_cdc.v": "ea27c4e2062d360d541e3c27f869beb73bb90add3cf847194718e0047ae3b43e",
}
ADDITIONS = set(RUNTIME) | {
    "starlink_pss_epoch_sealed_bank.v", "accepted_local_manifest.json", "accepted_local_results.json",
    "inverse_sealed.py", "inverse_sealed_actual.py", "inverse_sealed_actual_timing.py",
    "test_inverse_sealed_actual_policy.py", CHECKS, BENCH + ".sv", RUNNER, DIAGNOSTICS, PROFILE,
}
WAVE_FIELDS = ("inverse_take", "inverse_certificate", "inverse_seal", "inverse_publication",
               "inverse_reader_ack", "inverse_release", "inverse_lease", "inverse_protocol_owned",
               "inverse_protocol_admit", "inverse_protocol_words", "inverse_protocol_start",
               "inverse_protocol_lease", "inverse_protocol_qualified", "inverse_protocol_final",
               "inverse_protocol_pub", "inverse_protocol_ack", "inverse_protocol_release",
               "inverse_protocol_ack_seen", "inverse_protocol_reuse_seen")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load(name, expected=None):
    path = Path(__file__).with_name(name + ".py")
    if expected is not None and digest(path.read_bytes()) != expected:
        raise ValueError("fixed standalone dependency changed: " + name)
    spec = importlib.util.spec_from_file_location("sealed_actual_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def old_helper():
    return load("local_admission_actual", OLD_HELPER_SHA)


def adapt(text, edits, inverse=False):
    for old, new in reversed(edits) if inverse else edits:
        if inverse:
            old, new = new, old
        if text.count(old) != 1:
            raise ValueError("nonunique inverse actual adaptation anchor: " + old[:100])
        text = text.replace(old, new, 1)
    return text


def bench_edits():
    return (
        (f"module {OLD_BENCH};", f"module {BENCH};"),
        ("  parameter integer L = 0;", "  parameter integer L = 0;\n  parameter integer E = 0;"),
        (("  starlink_pss_fft_bank_owned_local_admission_probe #(.REGISTERED_SCHEDULING(REGISTERED_SCHEDULING),\n"
          "    .BOUNDARY_ROUND_SAT(B), .REGISTER_OPERANDS(O), .LOCAL_FIRST_ADMISSION(L)) dut (.*);"),
         ("  starlink_pss_fft_bank_owned_inverse_sealed_probe #(.REGISTERED_SCHEDULING(REGISTERED_SCHEDULING),\n"
          "    .BOUNDARY_ROUND_SAT(B), .REGISTER_OPERANDS(O), .LOCAL_FIRST_ADMISSION(L), .SEALED_INVERSE_OUTPUT(E)) dut (.*);")),
        ("dut.output_bank.input_valid !== (dut.return_private_valid && dut.next_inverse)",
         ("dut.sealed_inverse_output.output_bank.guard_private_valid !== dut.return_private_valid ||\n"
          "        dut.sealed_inverse_output.output_bank.bank.input_valid !==\n"
          "          (dut.return_private_valid && dut.next_inverse && dut.sealed_inverse_output.output_bank.producer_reference)")),
        ("wire original_destination_ready = dut.next_inverse ? dut.output_bank_ready :",
         "wire original_destination_ready = dut.next_inverse ? dut.output_destination_ready :"),
        ("dut.result_destination_ready !== (dut.next_inverse ? dut.output_bank_ready : dut.forward_handoff_ack)",
         "dut.result_destination_ready !== (dut.next_inverse ? dut.output_destination_ready : dut.forward_handoff_ack)"),
        ("if (preflight_kind == 4 || preflight_kind == 6) force dut.output_bank_ready = 0;",
         "if (preflight_kind == 4 || preflight_kind == 6) force dut.inverse_destination_reserved = 0;"),
        ("release dut.held_lease; release dut.product_bank_ready; release dut.output_bank_ready;",
         "release dut.held_lease; release dut.product_bank_ready; release dut.inverse_destination_reserved;"),
        ('  `include "starlink_pss_local_admission_actual_checks.svh"',
         f'  `include "{CHECKS}"\n  `include "starlink_pss_local_admission_actual_checks.svh"'),
        ("    local_guard_observer.final_receipt();",
         "    inverse_protocol_final_receipt();\n    local_guard_observer.final_receipt();"),
    )


def runner_edits():
    return (
        ("[file join $source_dir local_admission_actual.py]", "[file join $source_dir inverse_sealed_actual.py]"),
        ("source [file join $source_dir profile.tcl]", f"source [file join $source_dir {PROFILE}]"),
        ('if {$R != 1 || $B != 1 || $O != 1 || $L ni {0 1} || $fast_mhz != 175} { error "undeclared local-admission matrix" }',
         'if {$R != 1 || $B != 1 || $O != 1 || $L != 1 || $E != 1 || $fast_mhz != 175} { error "undeclared inverse-sealed matrix" }'),
        ("frequency=$fast_mhz L=$L no_restart=true", "frequency=$fast_mhz L=$L E=$E no_restart=true"),
        (f"set_property top {OLD_BENCH}", f"set_property top {BENCH}"),
        ("[list FAST_MHZ=$fast_mhz R=$R B=$B O=$O L=$L]", "[list FAST_MHZ=$fast_mhz R=$R B=$B O=$O L=$L E=$E]"),
        ("simulate_local_admission_diagnostics.tcl", DIAGNOSTICS),
        ("LOCAL_ADMISSION_ACTUAL_CORE_VERIFIED_NO_SCORER_RTL_PHYSICAL_OR_RF_CLAIM",
         "INVERSE_SEALED_ACTUAL_CORE_VERIFIED_NO_SCORER_RTL_PHYSICAL_OR_RF_CLAIM"),
    )


def wave_roots():
    return (f"/{BENCH}", f"/\\{BENCH}(FAST_MHZ=175,B=1,O=1,L=1,E=1) ")


def diagnostic_edits():
    old = old_helper()
    return (("set local_allowed_roots [list " + " ".join("{" + root + "}" for root in old.allowed_wave_roots(1)) + "]",
             "set local_allowed_roots [list " + " ".join("{" + root + "}" for root in wave_roots()) + "]"),
            ("run all\n", wave_add() + "run all\n"))


def wave_add():
    return """# Additive exact root-local inverse ownership histories; no stimulus changes.
set inverse_objects {}
foreach leaf {FIELDS} {
  set matches {}
  foreach object [get_objects -r *] {
    if {$object eq "$local_root/$leaf"} { lappend matches $object }
  }
  if {[llength $matches] != 1} { error "INVERSE_PROTOCOL_WAVE_MISSING_OR_DUPLICATE $leaf" }
  lappend inverse_objects [lindex $matches 0]
}
log_wave $inverse_objects
set channel [open inverse_protocol_diagnostic_signals.txt {WRONLY CREAT EXCL}]
foreach object $inverse_objects { puts $channel $object }; close $channel
set channel [open inverse_protocol_diagnostic_receipt.txt {WRONLY CREAT EXCL}]
puts $channel "INVERSE_PROTOCOL_WAVE_DIAGNOSTICS_ENABLED objects=19"; close $channel
""".replace("FIELDS", " ".join(WAVE_FIELDS))


def profile(accepted):
    rtl = list(accepted["runtime_rtl"])
    rtl[0] = next(iter(RUNTIME))
    rtl.extend(list(RUNTIME)[1:])
    compiled = list(accepted["compiled"])
    compiled[compiled.index("starlink_pss_fft_bank_owned_local_admission_probe.v")] = rtl[0]
    compiled[compiled.index(OLD_BENCH + ".sv")] = BENCH + ".sv"
    compiled.extend(list(RUNTIME)[1:])
    base = old_helper().load("bank_arithmetic_actual")
    text = ("set fast_mhz 175\nset R 1\nset B 1\nset O 1\nset L 1\nset E 1\n"
            + "set compiled_names {" + " ".join(compiled) + "}\n"
            + "set vector_names {" + " ".join(base.VECTOR_HASHES) + "}\n")
    return rtl, compiled, text.encode()


def verify_payloads(payloads):
    old = old_helper()
    if digest(payloads["accepted_local_manifest.json"]) != ACCEPTED_MANIFEST or digest(payloads["accepted_local_results.json"]) != ACCEPTED_RESULTS:
        raise ValueError("accepted original actual history changed")
    accepted = json.loads(payloads["accepted_local_manifest.json"])
    original = set(accepted["source_sha256"])
    if set(payloads) != original | ADDITIONS or original & ADDITIONS:
        raise ValueError("complete original plus additive source inventory changed")
    if {name: digest(payloads[name]) for name in original} != accepted["source_sha256"]:
        raise ValueError("immutable accepted actual source changed")
    old.verify_payloads({name: payloads[name] for name in original}, 1)
    if {name: digest(payloads[name]) for name in RUNTIME} != RUNTIME:
        raise ValueError("reviewed inverse runtime source changed")
    recipe = load("inverse_sealed", RECIPE_SHA)
    if recipe.restore_top(payloads[next(iter(RUNTIME))].decode()) != payloads["starlink_pss_fft_bank_owned_local_admission_probe.v"].decode():
        raise ValueError("whole original top inverse changed")
    if recipe.restore_cdc(payloads["starlink_pss_epoch_sealed_bank_cdc.v"].decode()) != payloads["starlink_pss_epoch_sealed_bank.v"].decode():
        raise ValueError("whole fast-only bank inverse changed")
    for name, previous, edits in (
        (BENCH + ".sv", OLD_BENCH + ".sv", bench_edits()),
        (RUNNER, "simulate_local_admission_actual.tcl", runner_edits()),
        (DIAGNOSTICS, "simulate_local_admission_diagnostics.tcl", diagnostic_edits()),
    ):
        if adapt(payloads[name].decode(), edits, True) != payloads[previous].decode():
            raise ValueError("strict original actual source inverse changed: " + name)
    rtl, compiled, expected = profile(accepted)
    if payloads[PROFILE] != expected:
        raise ValueError("exact compiled source/parameter binding changed")
    old.load("bank_arithmetic_actual").reject_synthetic(payloads)
    return accepted, rtl, compiled


def freeze(output, original):
    old = old_helper()
    output, original = old.safe_path(output), old.safe_path(original)
    if output.exists():
        raise FileExistsError("refusing inverse actual preparation overwrite")
    old.verify(original, ACCEPTED_MANIFEST)
    source = old.safe_path(original / "frozen_sources")
    payloads = {entry.name: entry.read_bytes() for entry in source.iterdir()}
    payloads["accepted_local_manifest.json"] = old.safe_path(original / "manifest.json").read_bytes()
    payloads["accepted_local_results.json"] = old.safe_path(original / "results.json").read_bytes()
    for name in RUNTIME.keys() | {"starlink_pss_epoch_sealed_bank.v"}:
        payloads[name] = old.safe_path(ACQ / name).read_bytes()
    for name in ("inverse_sealed.py", "inverse_sealed_actual.py", "inverse_sealed_actual_timing.py", "test_inverse_sealed_actual_policy.py"):
        payloads[name] = old.safe_path(Path(__file__).with_name(name)).read_bytes()
    payloads[CHECKS] = old.safe_path(ACQ / "tb" / CHECKS).read_bytes()
    for name, previous, edits in (
        (BENCH + ".sv", OLD_BENCH + ".sv", bench_edits()),
        (RUNNER, "simulate_local_admission_actual.tcl", runner_edits()),
        (DIAGNOSTICS, "simulate_local_admission_diagnostics.tcl", diagnostic_edits()),
    ):
        payloads[name] = adapt(payloads[previous].decode(), edits).encode()
    accepted = json.loads(payloads["accepted_local_manifest.json"])
    payloads[PROFILE] = profile(accepted)[2]
    _, rtl, compiled = verify_payloads(payloads)
    base = old.load("bank_arithmetic_actual")
    manifest = {"schema": "inverse-sealed-actual-preparation-v1", "E": 1, "L": 1,
                "R": 1, "B": 1, "O": 1, "frequency": 175, "runtime_rtl": rtl, "compiled": compiled,
                "source_sha256": {name: digest(data) for name, data in sorted(payloads.items())},
                "python_runtime_closure": ["inverse_sealed_actual.py", "inverse_sealed_actual_timing.py", "inverse_sealed.py",
                                           "local_admission_actual.py", "local_admission.py", "bank_arithmetic_actual.py"],
                "old_bounds": base.OLD_BOUNDS, "absolute_pair_budget": 5215,
                "nominal_pair_planning_limit": 4557, "stalled_delta_limit": None,
                "historical_trace_sha256": old.HISTORICAL_CANDIDATE_CSV,
                "old_guard_width": 155, "old_arithmetic_width": 119,
                "event_cycles": {"forward": "fast", "product": "fast", "inverse": "slow"},
                "actual_run": False, "old_actual_automation": "PASS_original6473_not_rerun"}
    frozen = output / "frozen_sources"
    frozen.mkdir(parents=True, exist_ok=False)
    for name, data in payloads.items():
        with (frozen / name).open("xb") as stream:
            stream.write(data)
    with (output / "manifest.json").open("x") as stream:
        stream.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    verify(output)
    return manifest


def verify(output, expected=None):
    old = old_helper()
    output = old.safe_path(output)
    data = old.safe_path(output / "manifest.json").read_bytes()
    if expected is not None and digest(data) != expected:
        raise ValueError("authorized inverse manifest mismatch")
    manifest = json.loads(data)
    if any(type(manifest.get(key)) is not int for key in ("E", "L", "R", "B", "O", "frequency")):
        raise ValueError("literal integer actual profile required")
    source = old.safe_path(output / "frozen_sources")
    entries = list(source.iterdir())
    if any(not path.is_file() or path.is_symlink() for path in entries):
        raise ValueError("unsafe frozen inventory")
    payloads = {path.name: path.read_bytes() for path in entries}
    if {name: digest(value) for name, value in payloads.items()} != manifest["source_sha256"]:
        raise ValueError("complete frozen inventory/source mismatch")
    _, rtl, compiled = verify_payloads(payloads)
    exact = {"schema": "inverse-sealed-actual-preparation-v1", "E": 1, "L": 1, "R": 1, "B": 1, "O": 1,
             "frequency": 175, "runtime_rtl": rtl, "compiled": compiled, "old_bounds": old.load("bank_arithmetic_actual").OLD_BOUNDS,
             "absolute_pair_budget": 5215, "nominal_pair_planning_limit": 4557, "stalled_delta_limit": None,
             "historical_trace_sha256": old.HISTORICAL_CANDIDATE_CSV, "old_guard_width": 155, "old_arithmetic_width": 119,
             "event_cycles": {"forward": "fast", "product": "fast", "inverse": "slow"},
             "actual_run": False, "old_actual_automation": "PASS_original6473_not_rerun",
             "python_runtime_closure": ["inverse_sealed_actual.py", "inverse_sealed_actual_timing.py", "inverse_sealed.py",
                                        "local_admission_actual.py", "local_admission.py", "bank_arithmetic_actual.py"]}
    if set(manifest) != set(exact) | {"source_sha256"} or any(manifest.get(key) != value for key, value in exact.items()):
        raise ValueError("fixed scope/clock/budget contract changed")
    old.load("bank_arithmetic_actual").verify_vectors(source)
    return manifest


def results(output, expected):
    old = old_helper()
    output = old.safe_path(output)
    manifest = verify(output, expected)
    source = output / "frozen_sources"
    started = "actual_fft=true R=1 B=1 O=1 frequency=175 L=1 E=1 no_restart=true\n"
    if (output / "launch_started.txt").read_text() != started:
        raise ValueError("wrong actual source/parameter launch binding")
    before = (output / "generated_ip_before.txt").read_text()
    match = re.fullmatch(r"([0-9a-f]{64})  ([^\n]+)\n", before)
    if not match or before != (output / "generated_ip_after.txt").read_text():
        raise ValueError("generated IP pre/post identity")
    wrapper = old.safe_path(match[2])
    if output not in wrapper.parents or digest(wrapper.read_bytes()) != match[1]:
        raise ValueError("generated IP live source identity")
    sim = output / "project/fft_bank_arithmetic_actual.sim/sim_1/behav/xsim"
    log = (sim / "simulate.log").read_text()
    base = old.load("bank_arithmetic_actual")
    receipts = base.require_terminal(log, manifest)
    guard = old.require_guard_terminal(log, 1)
    protocol_terminal = require_protocol_terminal(log)
    arithmetic_inventory = (sim / "arithmetic_diagnostic_signals.txt").read_text()
    arithmetic_wave = base.require_closed_wave_receipt(
        (sim / "arithmetic_diagnostic_receipt.txt").read_text(), arithmetic_inventory)
    paths = arithmetic_inventory.splitlines()
    roots = {"/" + path.split("/")[1] for path in paths}
    if len(roots) != 1 or not roots.issubset(wave_roots()):
        raise ValueError("wrong arithmetic diagnostic actual profile/root")
    root = roots.pop()
    for stem, fields, receipt in (
        ("local_guard", ["local_guard_observer/" + name for name in old.WAVE_FIELDS],
         "LOCAL_GUARD_WAVE_DIAGNOSTICS_ENABLED objects=14 width=155\n"),
        ("inverse_protocol", WAVE_FIELDS, "INVERSE_PROTOCOL_WAVE_DIAGNOSTICS_ENABLED objects=19\n"),
    ):
        if (sim / (stem + "_diagnostic_receipt.txt")).read_text() != receipt or (sim / (stem + "_diagnostic_signals.txt")).read_text().splitlines() != [f"{root}/{field}" for field in fields]:
            raise ValueError("exact diagnostic inventory/closed receipt: " + stem)
    events = base.verify_events(sim / "bank_arithmetic_events.csv", source)
    timing = load("inverse_sealed_actual_timing", manifest["source_sha256"]["inverse_sealed_actual_timing.py"])
    jobs = timing.parse_trace(sim / "fft_bank_owned_trace.csv")
    intervals = timing.verify_jobs(jobs, True)
    ledger = timing.verify_event_cycles(sim / "bank_arithmetic_events.csv", jobs)
    protocol = timing.verify_protocol(sim / "inverse_sealed_protocol.csv", jobs,
        base.words(source / "inverse_q17.mem", 1536),
        base.words(source / "forward_exponents.mem", 3), base.words(source / "inverse_exponents.mem", 3))
    log_jobs = [{key: int(value) for key, value in re.findall(r"(\w+)=(\d+)", line)}
                for line in re.findall(r"^BANK_JOB (.*)$", log, re.MULTILINE)]
    log_jobs = [job for job in log_jobs if job["epoch"] in (1, 2)]
    expected_jobs = [{"epoch": job["epoch"], "inverse": job["inverse"], "admit": job["admit"],
                      "config_delta": 3, "input_span": 513, "input_last_to_output_first": 781,
                      "commit_delta": job["commit"][0]} for job in jobs]
    if log_jobs != expected_jobs:
        raise ValueError("actual log/CSV full core-phase timing mismatch")
    return {"actual_run": True, "profile": "R1B1O1L1E1_175", "receipts": receipts,
            "guard": guard, "protocol_terminal": protocol_terminal, "protocol": protocol,
            "events": events, "event_time_ledgers": ledger, "pair_intervals": intervals,
            "arithmetic_wave_inventory_only_pending_recorded_history_review": arithmetic_wave,
            "trace_sha256": timing.digest(sim / "fft_bank_owned_trace.csv"),
            "protocol_sha256": timing.digest(sim / "inverse_sealed_protocol.csv"),
            "log_sha256": timing.digest(sim / "simulate.log"),
            "historical_trace_identity_required": False,
            "physical_RF_or_scorer_RTL_qualified": False}


def require_protocol_terminal(log):
    if re.search(r"FAIL|MISMATCH|FATAL|ERROR", log, re.IGNORECASE):
        raise ValueError("early/late failure overrides protocol PASS")
    matches = re.findall(r"^INVERSE_SEALED_ACTUAL_PASS (.*)$", log, re.MULTILINE)
    if len(matches) != 1 or not re.fullmatch(r"\w+=\d+(?: \w+=\d+)*", matches[0]):
        raise ValueError("missing/duplicate/malformed protocol terminal")
    pairs = re.findall(r"(\w+)=(\d+)", matches[0])
    row = {key: int(value) for key, value in pairs}
    exact = {"E": 1, "L": 1, "R": 1, "B": 1, "O": 1, "fast_mhz": 175,
             "takes": 19456, "publications": 38, "releases": 38,
             "owned_reservation_edges": 76, "public_commit_delta": 1813}
    if len(row) != len(pairs) or set(row) != set(exact) | {"current_veto_checks", "held_final_checks"} or any(row[key] != value for key, value in exact.items()) or min(row["current_veto_checks"], row["held_final_checks"]) <= 0:
        raise ValueError("incomplete exact protocol terminal")
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "verify", "results"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--original-actual", type=Path)
    parser.add_argument("--expected")
    args = parser.parse_args()
    if args.mode == "prepare":
        value = freeze(args.output, args.original_actual)
    elif args.mode == "verify":
        value = verify(args.output, args.expected)
    else:
        if not args.expected:
            parser.error("results requires exact authorized manifest hash")
        value = results(args.output, args.expected)
    print(json.dumps(value, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

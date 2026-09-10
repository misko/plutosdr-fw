"""Standalone, source-specific LOCAL_FIRST_ADMISSION actual preparation. No launch."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACQ = ROOT / "hdl/library/starlink_pss_acquisition"
OLD_BENCH = "tb_starlink_pss_bank_arithmetic_actual"
BENCH = "tb_starlink_pss_local_admission_actual"
CHECKS = "starlink_pss_local_admission_actual_checks.svh"
OBSERVER = "starlink_pss_local_admission_actual_observer.sv"
RUNNER = "simulate_local_admission_actual.tcl"
DIAGNOSTICS = "simulate_local_admission_diagnostics.tcl"
HISTORY = "6376f1fb2508f357933d4cb9cd9949d8da452d155a47084701aa29fb99df1954"
HISTORICAL_CANDIDATE_CSV = "e7127798f315772b95aff63b75fffcd9cf5d1af8ca3c96e878bae4b39e443d71"
HISTORY_FILES = {
    "history_manifest.json": HISTORY,
    "history_run_outcome.txt": "f42eff39aeeb9632c4ec7064e453146b958047d5a96c219821f66c2f0ef63af3",
    "history_posthoc_assessment.json": "a1e7eebc49fba088327109643d9beb120276eb2f6f230a885d5a9438e048da0f",
}
FIXED = {
    "bank_arithmetic_actual.py": "de13f13c54531a9e13fe872cc5b4be82ab917487c448f25ee744b0b555cca07d",
    "local_admission.py": "8b413b323dd55f347bbed4babef74a1faba7754672c01f9122231b82aa9a51ef",
    "simulate_bank_arithmetic_actual.tcl": "684f8e788f7a3550d85ccc30eb32a56b7b72a4c8067c2aa59513d416bd177eb9",
    "simulate_bank_arithmetic_diagnostics.tcl": "7efe69d2f3896c50ee97bce6b52bd70493ba757b2e0e16c80aaf5b6d1f7748c6",
    "starlink_pss_realtime_input_guard_local_admission.v": "55438743eede0d346cec67351e079eb6ae21da437d4088a131a2a258b43ff233",
    "starlink_pss_fft_bank_owned_local_admission_probe.v": "0cb54617eb6757e1d6c719d97b0fd5002ec7f6105c8c4b50c41eba67d4306235",
}
WAVE_FIELDS = ("actual_view", "original_view", "default_view", "clk", "resetn", "job_start",
               "job_descriptor", "input_enable", "input_valid", "input_position", "input_metadata",
               "pre_checks", "post_checks", "reset_checks")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load(name):
    path = Path(__file__).with_name(name + ".py")
    if digest(path.read_bytes()) != FIXED[path.name]:
        raise ValueError("fixed standalone helper source changed")
    spec = importlib.util.spec_from_file_location("local_actual_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def edits_bench():
    return (
        (f"module {OLD_BENCH};", f"module {BENCH};"),
        ("  parameter integer R = 1, B = 0, O = 0;", "  parameter integer R = 1, B = 0, O = 0;\n  parameter integer L = 0;"),
        ("  starlink_pss_fft_bank_owned_arithmetic_probe #(.REGISTERED_SCHEDULING(REGISTERED_SCHEDULING),\n    .BOUNDARY_ROUND_SAT(B), .REGISTER_OPERANDS(O)) dut (.*);",
         "  starlink_pss_fft_bank_owned_local_admission_probe #(.REGISTERED_SCHEDULING(REGISTERED_SCHEDULING),\n    .BOUNDARY_ROUND_SAT(B), .REGISTER_OPERANDS(O), .LOCAL_FIRST_ADMISSION(L)) dut (.*);"),
        ('  `include "starlink_pss_bank_arithmetic_actual_checks.svh"',
         f'  `include "{CHECKS}"\n  `include "starlink_pss_bank_arithmetic_actual_checks.svh"'),
        ("    arithmetic_final_receipt();", "    local_guard_observer.final_receipt();\n    arithmetic_final_receipt();"),
    )


def edits_runner():
    return (
        ('if {$argc != 2} { error "expected PREPARED_OUTPUT ABSOLUTE_PYTHON" }',
         'if {$argc != 3} { error "expected PREPARED_OUTPUT ABSOLUTE_PYTHON EXPECTED_MANIFEST_SHA" }\nset expected_manifest [lindex $argv 2]'),
        ("bank_arithmetic_actual.py", "local_admission_actual.py"),
        ("verify $output_dir >", "verify $output_dir --expected $expected_manifest >"),
        ('if {$R != 1 || [list $B $O] ni {{0 0} {1 1}} || $fast_mhz ni {175 200}} { error "undeclared matrix" }',
         'if {$R != 1 || $B != 1 || $O != 1 || $L ni {0 1} || $fast_mhz != 175} { error "undeclared local-admission matrix" }'),
        ('frequency=$fast_mhz no_restart=true"', 'frequency=$fast_mhz L=$L no_restart=true"'),
        (f"set_property top {OLD_BENCH}", f"set_property top {BENCH}"),
        ("[list FAST_MHZ=$fast_mhz R=$R B=$B O=$O]", "[list FAST_MHZ=$fast_mhz R=$R B=$B O=$O L=$L]"),
        ("simulate_bank_arithmetic_diagnostics.tcl", DIAGNOSTICS),
        ("results $output_dir]", "results $output_dir --expected $expected_manifest]"),
        ("BANK_ARITHMETIC_ACTUAL_CORE_VERIFIED_NO_SCORER_RTL_PHYSICAL_OR_RF_CLAIM",
         "LOCAL_ADMISSION_ACTUAL_CORE_VERIFIED_NO_SCORER_RTL_PHYSICAL_OR_RF_CLAIM"),
    )


WAVE_ADD = """# Extra observer recording, independent of existing arithmetic diagnostics.
set local_objects {}
foreach leaf {FIELDS} {
  set object [get_objects /TOP/local_guard_observer/$leaf]
  if {[llength $object] != 1} { error "LOCAL_GUARD_WAVE_PATH_MISSING $leaf" }
  lappend local_objects {*}$object
}
log_wave $local_objects
set channel [open local_guard_diagnostic_signals.txt {WRONLY CREAT EXCL}]
foreach object $local_objects { puts $channel $object }; close $channel
set channel [open local_guard_diagnostic_receipt.txt {WRONLY CREAT EXCL}]
puts $channel "LOCAL_GUARD_WAVE_DIAGNOSTICS_ENABLED objects=14 width=155"; close $channel
""".replace("FIELDS", " ".join(WAVE_FIELDS)).replace("TOP", BENCH)


def adapt(source, edits, inverse=False):
    for old, new in reversed(edits) if inverse else edits:
        if inverse:
            old, new = new, old
        # The same preflight/postflight invocation is intentionally changed twice.
        expected = 2 if old.startswith("verify $output_dir ") else 1
        if source.count(old) != expected:
            raise ValueError("nonunique strict local actual adaptation anchor")
        source = source.replace(old, new)
    return source


def profile(base, option):
    rtl = [name + ".v" for name in base.RTL]
    rtl[0] = "starlink_pss_fft_bank_owned_local_admission_probe.v"
    rtl[1] = "starlink_pss_realtime_input_guard_local_admission.v"
    # Original guard is still required by the untouched old input shadow.
    compiled = rtl + ["starlink_pss_realtime_input_guard.v", "local_admission_original_guard.v", OBSERVER]
    compiled += [BENCH + ".sv" if name == OLD_BENCH + ".sv" else name
                 for name in base.TB if not name.endswith(".svh")]
    text = (f"set fast_mhz 175\nset R 1\nset B 1\nset O 1\nset L {option}\n"
            + "set compiled_names {" + " ".join(compiled) + "}\n"
            + "set vector_names {" + " ".join(base.VECTOR_HASHES) + "}\n")
    return rtl, compiled, text.encode()


def verify_payloads(payloads, option):
    base, recipe = load("bank_arithmetic_actual"), load("local_admission")
    required = {name + ".v" for name in base.RTL} | set(base.TB) | set(base.VECTOR_HASHES)
    required |= set(FIXED) | set(HISTORY_FILES) | {
        CHECKS, OBSERVER, RUNNER, DIAGNOSTICS, BENCH + ".sv", "local_admission_actual.py",
        "test_starlink_local_admission_actual_policy.py", "local_admission_original_guard.v",
        "profile.tcl", "create_shared_realtime_xfft_ip.tcl", base.OLD_BENCH + ".sv.reference",
    }
    if set(payloads) != required:
        raise ValueError("complete declared frozen source closure changed")
    for name, expected in FIXED.items() | HISTORY_FILES.items():
        if digest(payloads[name]) != expected:
            raise ValueError("fixed source/history identity changed: " + name)
    history = json.loads(payloads["history_manifest.json"])
    for name, expected in history["source_sha256"].items():
        if name in payloads and name not in FIXED and name != "profile.tcl" and digest(payloads[name]) != expected:
            raise ValueError("unchanged original actual source changed: " + name)
    old_bench = payloads[OLD_BENCH + ".sv"].decode()
    if adapt(payloads[BENCH + ".sv"].decode(), edits_bench(), True) != old_bench:
        raise ValueError("old actual stimulus/check inverse changed")
    if base.adapt_bench(old_bench, True) != payloads[base.OLD_BENCH + ".sv.reference"].decode():
        raise ValueError("original dec20 stimulus/check inverse changed")
    for name, old, edits in (
        (recipe.GUARD, recipe.OLD_GUARD, recipe.guard_edits()),
        (recipe.TOP, recipe.OLD_TOP, recipe.top_edits()),
    ):
        if recipe.apply(payloads[name + ".v"].decode(), edits, True) != payloads[old + ".v"].decode():
            raise ValueError("runtime local-admission inverse changed")
    renamed = payloads[recipe.OLD_GUARD + ".v"].replace(
        b"module starlink_pss_realtime_input_guard #(", b"module local_admission_original_guard #(", 1)
    if payloads["local_admission_original_guard.v"] != renamed:
        raise ValueError("observer is not literal original guard")
    if adapt(payloads[RUNNER].decode(), edits_runner(), True) != payloads["simulate_bank_arithmetic_actual.tcl"].decode():
        raise ValueError("runner inverse changed")
    if adapt(payloads[DIAGNOSTICS].decode(), (("run all\n", WAVE_ADD + "run all\n"),), True) != payloads["simulate_bank_arithmetic_diagnostics.tcl"].decode():
        raise ValueError("wave-only diagnostics inverse changed")
    rtl, compiled, expected_profile = profile(base, option)
    if payloads["profile.tcl"] != expected_profile:
        raise ValueError("actual source closure/parameter profile changed")
    base.reject_synthetic(payloads)
    return rtl, compiled


def freeze(output, old_actual, option):
    output, old_actual = Path(output).resolve(), Path(old_actual).resolve()
    if type(option) is not int or option not in (0, 1):
        raise ValueError("only L0/L1 fixed R1/B1/O1 175 MHz preparations")
    if output.exists():
        raise FileExistsError("refusing local preparation overwrite")
    base, recipe = load("bank_arithmetic_actual"), load("local_admission")
    base.verify_adaptations()
    if digest((old_actual / "manifest.json").read_bytes()) != HISTORY:
        raise ValueError("not the fixed original v3 candidate source history")
    old_manifest = json.loads((old_actual / "manifest.json").read_text())
    old_source = old_actual / "frozen_sources"
    found = {p.name: digest(p.read_bytes()) for p in old_source.iterdir() if p.is_file() and not p.is_symlink()}
    if found != old_manifest["source_sha256"] or len(found) != len(list(old_source.iterdir())):
        raise ValueError("original historical source inventory changed")
    # Only explicit dependencies are loaded; no package __init__ or mutable import scan.
    names = [name + ".v" for name in base.RTL] + base.TB
    payloads = {name: (old_source / name).read_bytes() for name in names}
    payloads.update({name: (old_source / name).read_bytes() for name in base.VECTOR_HASHES})
    for name in ("create_shared_realtime_xfft_ip.tcl", base.OLD_BENCH + ".sv.reference"):
        payloads[name] = (old_source / name).read_bytes()
    for name in (recipe.TOP + ".v", recipe.GUARD + ".v", "simulate_bank_arithmetic_actual.tcl", "simulate_bank_arithmetic_diagnostics.tcl"):
        payloads[name] = (ACQ / name).read_bytes()
    for name in (CHECKS, OBSERVER):
        payloads[name] = (ACQ / "tb" / name).read_bytes()
    for name in ("bank_arithmetic_actual.py", "local_admission.py", "local_admission_actual.py"):
        payloads[name] = Path(__file__).with_name(name).read_bytes()
    payloads["test_starlink_local_admission_actual_policy.py"] = (ROOT / "tests/test_starlink_local_admission_actual_policy.py").read_bytes()
    payloads[BENCH + ".sv"] = adapt(payloads[OLD_BENCH + ".sv"].decode(), edits_bench()).encode()
    payloads[RUNNER] = adapt(payloads["simulate_bank_arithmetic_actual.tcl"].decode(), edits_runner()).encode()
    payloads[DIAGNOSTICS] = adapt(payloads["simulate_bank_arithmetic_diagnostics.tcl"].decode(), (("run all\n", WAVE_ADD + "run all\n"),)).encode()
    payloads["local_admission_original_guard.v"] = payloads[recipe.OLD_GUARD + ".v"].replace(
        b"module starlink_pss_realtime_input_guard #(", b"module local_admission_original_guard #(", 1)
    payloads["profile.tcl"] = profile(base, option)[2]
    payloads["history_manifest.json"] = (old_actual / "manifest.json").read_bytes()
    payloads["history_run_outcome.txt"] = (old_actual / "run_outcome.txt").read_bytes()
    payloads["history_posthoc_assessment.json"] = (ACQ / "build/bank-arithmetic-monitor-actual-assessment-v1.OsPugx/posthoc_assessment.json").read_bytes()
    rtl, compiled = verify_payloads(payloads, option)
    manifest = {"schema": "local-admission-actual-preparation-v1", "L": option,
                "R": 1, "B": 1, "O": 1, "frequency": 175, "runtime_rtl": rtl, "compiled": compiled,
                "source_sha256": {name: digest(data) for name, data in sorted(payloads.items())},
                "python_runtime_closure": ["local_admission_actual.py", "local_admission.py", "bank_arithmetic_actual.py"],
                "old_bounds": base.OLD_BOUNDS, "core_timing": base.CORE_TIMING,
                "historical_R1B1O1_complete_trace_sha256": HISTORICAL_CANDIDATE_CSV,
                "original_history": "automation_FAIL_diagnostic_log_source_only_separate_posthoc_functional_qualification",
                "guard_comparison_width": 155, "no_observer_masks": True,
                "actual_run": False, "no_vendor_execution_during_preparation": True}
    source = output / "frozen_sources"
    source.mkdir(parents=True, exist_ok=False)
    for name, data in payloads.items():
        with (source / name).open("xb") as stream:
            stream.write(data)
    with (output / "manifest.json").open("x") as stream:
        stream.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    verify(output)
    return manifest


def verify(output, expected=None):
    output = Path(output).resolve()
    manifest_bytes = (output / "manifest.json").read_bytes()
    if expected is not None and digest(manifest_bytes) != expected:
        raise ValueError("unexpected authorized manifest identity")
    manifest = json.loads(manifest_bytes)
    source = output / "frozen_sources"
    entries = list(source.iterdir())
    if any(not p.is_file() or p.is_symlink() for p in entries):
        raise ValueError("unsafe frozen source inventory")
    payloads = {p.name: p.read_bytes() for p in entries}
    if {name: digest(data) for name, data in payloads.items()} != manifest["source_sha256"]:
        raise ValueError("frozen source inventory/hash changed")
    if (manifest.get("schema"), manifest.get("R"), manifest.get("B"), manifest.get("O"), manifest.get("frequency")) != ("local-admission-actual-preparation-v1", 1, 1, 1, 175) or type(manifest.get("L")) is not int or manifest["L"] not in (0, 1):
        raise ValueError("undeclared actual profile")
    rtl, compiled = verify_payloads(payloads, manifest["L"])
    base = load("bank_arithmetic_actual")
    if manifest["runtime_rtl"] != rtl or manifest["compiled"] != compiled or manifest["old_bounds"] != base.OLD_BOUNDS or manifest["core_timing"] != base.CORE_TIMING or manifest["historical_R1B1O1_complete_trace_sha256"] != HISTORICAL_CANDIDATE_CSV:
        raise ValueError("immutable source/latency contract changed")
    if manifest.get("guard_comparison_width") != 155 or manifest.get("no_observer_masks") is not True or manifest.get("actual_run") is not False or manifest.get("no_vendor_execution_during_preparation") is not True or manifest.get("python_runtime_closure") != ["local_admission_actual.py", "local_admission.py", "bank_arithmetic_actual.py"] or manifest.get("original_history") != "automation_FAIL_diagnostic_log_source_only_separate_posthoc_functional_qualification":
        raise ValueError("preparation/observer/history scope changed")
    base.verify_vectors(source)
    return manifest


def require_guard_terminal(log, option):
    if re.search(r"FAIL|MISMATCH|FATAL|ERROR", log, re.IGNORECASE):
        raise ValueError("early/late failure vetoes guard PASS")
    matches = re.findall(r"^LOCAL_ADMISSION_ACTUAL_PASS (.*)$", log, re.MULTILINE)
    if len(matches) != 1 or not re.fullmatch(r"\w+=\d+(?: \w+=\d+)*", matches[0]):
        raise ValueError("missing/duplicate/malformed guard terminal")
    pairs = re.findall(r"(\w+)=(\d+)", matches[0])
    row = {k: int(v) for k, v in pairs}
    exact = {"L": option, "R": 1, "B": 1, "O": 1, "width": 155, "full_unconditional_state_outputs": 1,
             "original_guard_literal": 1, "default_omitted": 1, "added_latency": 0}
    positive = {"pre_checks", "post_checks", "reset_checks", "forward_starts", "inverse_starts",
                "current_faults", "sticky_faults", "completed_checks", "closed_prefetch", "duplicate_checks"}
    if len(pairs) != len(row) or set(row) != set(exact) | positive or any(row[k] != v for k, v in exact.items()) or any(row[k] <= 0 for k in positive) or min(row["pre_checks"], row["post_checks"]) < 1024 or min(row["forward_starts"], row["inverse_starts"]) < 38:
        raise ValueError("incomplete guard comparison/binding contract")
    return row


def require_guard_wave(receipt, inventory):
    paths = inventory.splitlines()
    expected = [f"/{BENCH}/local_guard_observer/{name}" for name in WAVE_FIELDS]
    if receipt != "LOCAL_GUARD_WAVE_DIAGNOSTICS_ENABLED objects=14 width=155\n" or paths != expected:
        raise ValueError("guard waveform path/closed receipt mismatch")
    return paths


def results(output, expected):
    output = Path(output).resolve()
    manifest = verify(output, expected)
    base = load("bank_arithmetic_actual")
    start = f"actual_fft=true R=1 B=1 O=1 frequency=175 L={manifest['L']} no_restart=true\n"
    if (output / "launch_started.txt").read_text() != start:
        raise ValueError("wrong actual launch binding")
    before = (output / "generated_ip_before.txt").read_text()
    match = re.fullmatch(r"([0-9a-f]{64})  ([^\n]+)\n", before)
    if not match or before != (output / "generated_ip_after.txt").read_text():
        raise ValueError("generated IP before/after mismatch")
    wrapper = Path(match[2]).resolve()
    if output not in wrapper.parents or base.sha(wrapper) != match[1]:
        raise ValueError("generated IP live source mismatch")
    sim = output / "project/fft_bank_arithmetic_actual.sim/sim_1/behav/xsim"
    log = (sim / "simulate.log").read_text()
    receipts = base.require_terminal(log, manifest)
    guard = require_guard_terminal(log, manifest["L"])
    base.require_closed_wave_receipt((sim / "arithmetic_diagnostic_receipt.txt").read_text(), (sim / "arithmetic_diagnostic_signals.txt").read_text())
    paths = require_guard_wave((sim / "local_guard_diagnostic_receipt.txt").read_text(), (sim / "local_guard_diagnostic_signals.txt").read_text())
    trace = base.sha(sim / "fft_bank_owned_trace.csv")
    if trace != HISTORICAL_CANDIDATE_CSV:
        raise ValueError("full historical R1B1O1 trace changed; no latency retiming allowed")
    jobs = [{k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", line)}
            for line in re.findall(r"^BANK_JOB (.*)$", log, re.MULTILINE)]
    jobs = [job for job in jobs if job["epoch"] in (1, 2)]
    if len(jobs) != 76 or any(any(job.get(k) != v for k, v in base.CORE_TIMING.items()) for job in jobs):
        raise ValueError("original real-core cycles changed")
    events = base.verify_events(sim / "bank_arithmetic_events.csv", output / "frozen_sources")
    return {"actual_run": True, "L": manifest["L"], "receipts": receipts, "guard": guard,
            "guard_wave_inventory_only_pending_recorded_history_review": paths,
            "events": events, "trace_sha256": trace, "log_sha256": base.sha(sim / "simulate.log"),
            "physical_RF_or_scorer_RTL_qualified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "verify", "results"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--original-actual", type=Path)
    parser.add_argument("--L", type=int, default=0)
    parser.add_argument("--expected")
    args = parser.parse_args()
    if args.mode == "prepare":
        value = freeze(args.output, args.original_actual, args.L)
    elif args.mode == "verify":
        value = verify(args.output, args.expected)
    else:
        if args.expected is None:
            parser.error("results requires explicit expected manifest identity")
        value = results(args.output, args.expected)
    print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

"""Offline source/clock preparation policy; no vendor tool is launched."""

import copy
import csv
import importlib.util
import json
import os
import shutil
import subprocess
from bisect import bisect_right
from pathlib import Path

import pytest

HERE = Path(__file__).parent


def module(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


PREP = module("inverse_sealed_actual")
TIMING = module("inverse_sealed_actual_timing")
ORIGINAL = PREP.ACQ / "build/local-admission-actual-R1B1O1-L1-175-prepared-v4"
SIM = ORIGINAL / "project/fft_bank_arithmetic_actual.sim/sim_1/behav/xsim"


@pytest.fixture(scope="module")
def history():
    path = SIM / "fft_bank_owned_trace.csv"
    assert TIMING.digest(path) == TIMING.HISTORICAL_TRACE
    jobs = TIMING.parse_trace(path)
    yield jobs
    assert TIMING.digest(path) == TIMING.HISTORICAL_TRACE


def test_all_original_jobs_and_mixed_domain_event_times(history):
    intervals = TIMING.verify_jobs(history, False)
    assert {n: intervals[1].count(n) for n in set(intervals[1])} == {4548: 24, 4549: 7}
    assert {n: intervals[2].count(n) for n in set(intervals[2])} == {4821: 3, 4822: 2}
    ledger = TIMING.verify_event_cycles(SIM / "bank_arithmetic_events.csv", history)
    assert {key: row["count"] for key, row in ledger.items()} == {
        f"{epoch}_{kind}": blocks * 512
        for epoch, blocks in ((1, 32), (2, 6))
        for kind in ("forward", "product", "inverse")
    }
    assert ledger["1_inverse"]["first"] == 2622
    assert ledger["1_forward"]["first"] == 2244


@pytest.mark.parametrize("field,value", [("status", [1298]), ("status", [1301]),
    ("raw", list(range(1299, 1811))), ("input", list(range(5, 517))),
    ("commit", []), ("commit", [1813]), ("config", [4])])
def test_generated_core_baseline_phase_mutations_rejected(history, field, value):
    jobs = copy.deepcopy(history)
    jobs[1][field] = value
    with pytest.raises(ValueError, match="service|publication"):
        TIMING.verify_jobs(jobs, False)


def test_candidate_publication_change_is_not_old_whole_trace_equivalence(history):
    with pytest.raises(ValueError, match="publication"):
        TIMING.verify_jobs(history, True)
    jobs = copy.deepcopy(history)
    for job in jobs:
        if job["inverse"]:
            job["commit"] = [1813]
    TIMING.verify_jobs(jobs, True)
    # A candidate publication shift may not borrow old absolute slow timestamps.
    with pytest.raises(ValueError, match="absolute event timestamp"):
        TIMING.verify_event_cycles(SIM / "bank_arithmetic_events.csv", jobs)


@pytest.mark.parametrize("stream", ["forward", "product", "inverse"])
def test_each_original_stream_timestamp_shift_is_rejected(history, tmp_path, stream):
    path = tmp_path / "changed.csv"
    with (SIM / "bank_arithmetic_events.csv").open() as source, path.open("w") as output:
        reader = csv.DictReader(source)
        writer = csv.DictWriter(output, fieldnames=reader.fieldnames)
        writer.writeheader()
        changed = False
        for row in reader:
            if not changed and row["stream"] == stream:
                row["cycle"] = str(int(row["cycle"]) + 1)
                changed = True
            writer.writerow(row)
    with pytest.raises(ValueError, match="absolute event timestamp"):
        TIMING.verify_event_cycles(path, history)


def test_periodic_ready_phase_shift_is_not_blanket_eight_fast_clocks():
    # Independent integer ready enumeration, same literal schedule as old bench.
    def accepted(first):
        return [cycle for cycle in range(first, first + 800) if cycle % 17 < 13][:512]
    assert accepted(8)[-1] == 675 and accepted(10)[-1] == 681
    assert (681 - 675) * 10 * 175 > 8 * 1000


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    root = tmp_path_factory.mktemp("actual_preparation") / "bundle"
    manifest = PREP.freeze(root, ORIGINAL)
    assert not (root / "project").exists() and not (root / "launch_started.txt").exists()
    return root, manifest


def test_exact_original_source_closure_and_default_off_new_binding(prepared):
    root, manifest = prepared
    assert len(manifest["runtime_rtl"]) == 10
    assert len(manifest["compiled"]) == 21
    assert PREP.verify(root, PREP.digest((root / "manifest.json").read_bytes())) == manifest
    source = root / "frozen_sources"
    accepted = json.loads((source / "accepted_local_manifest.json").read_text())
    assert len(accepted["source_sha256"]) == 49
    for name, expected in accepted["source_sha256"].items():
        assert PREP.digest((source / name).read_bytes()) == expected
    assert "parameter integer E = 0;" in (source / (PREP.BENCH + ".sv")).read_text()
    assert ".SEALED_INVERSE_OUTPUT(E)" in (source / (PREP.BENCH + ".sv")).read_text()
    assert "set E 1\n" in (source / PREP.PROFILE).read_text()


def test_no_original_fault_or_check_changes_outside_declared_inverse(prepared):
    source = prepared[0] / "frozen_sources"
    for name, previous, edits in (
        (PREP.BENCH + ".sv", PREP.OLD_BENCH + ".sv", PREP.bench_edits()),
        (PREP.RUNNER, "simulate_local_admission_actual.tcl", PREP.runner_edits()),
        (PREP.DIAGNOSTICS, "simulate_local_admission_diagnostics.tcl", PREP.diagnostic_edits()),
    ):
        assert PREP.adapt((source / name).read_text(), edits, True) == (source / previous).read_text()
    text = (source / (PREP.BENCH + ".sv")).read_text()
    assert "force dut.inverse_destination_reserved = 0" in text
    assert "force dut.output_bank_ready = 0" not in text
    assert "preflight_matrix_cases != 84" in text
    assert "timeout < 25000" in text and "repeat (24) tick();" in text


def test_results_fail_closed_without_any_execution(prepared):
    root, _ = prepared
    with pytest.raises(FileNotFoundError, match="launch_started"):
        PREP.results(root, PREP.digest((root / "manifest.json").read_bytes()))
    assert not (root / "results.json").exists()


def test_frozen_standalone_verify_from_unrelated_cwd(prepared):
    root, _ = prepared
    python = Path("/home/mouse9911/gits/pluto-plus-utils/.venv/bin/python")
    result = subprocess.run(["env", "-u", "LD_LIBRARY_PATH", "-u", "PYTHONHOME", "-u", "PYTHONPATH",
        str(python), "-B", str(root / "frozen_sources/inverse_sealed_actual.py"), "verify", str(root),
        "--expected", PREP.digest((root / "manifest.json").read_bytes())],
        cwd="/", capture_output=True, text=True, check=False, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == prepared[1]


def test_complete_derived_bench_elaboration_only_vendor_module_absent(prepared, tmp_path):
    root, manifest = prepared
    source = root / "frozen_sources"
    output = tmp_path / "syntax_only.vvp"
    command = ["iverilog", "-g2012", "-i", "-s", PREP.BENCH, "-I", str(source), "-o", str(output)]
    command += [f"-P{PREP.BENCH}.{key}={value}" for key, value in
                {"FAST_MHZ": 175, "R": 1, "B": 1, "O": 1, "L": 1, "E": 1}.items()]
    command += [str(source / name) for name in manifest["compiled"]]
    environment = {key: value for key, value in os.environ.items()
                   if key not in ("LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH")}
    result = subprocess.run(command, env=environment, capture_output=True, text=True, check=False, timeout=30)
    (tmp_path / "command.json").write_text(json.dumps(command, indent=2))
    (tmp_path / "elaboration.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stderr
    assert output.is_file()
    # Never execute this -i artifact: vendor FFT is absent. Actual compiled
    # closure cannot contain any behavioral replacement, even for syntax.
    for name in manifest["compiled"]:
        assert "module starlink_pss_fft512_bfp18_rt_candidate" not in (source / name).read_text()
    (tmp_path / "scope.txt").write_text("ELABORATION_ONLY_VENDOR_FFT_ABSENT_NO_SIMULATION\n")


@pytest.mark.parametrize("key,value", [("E", 0), ("L", 0), ("R", 0), ("B", 0), ("O", 0),
    ("E", True), ("E", 1.0), ("frequency", 200), ("absolute_pair_budget", 5216),
    ("nominal_pair_planning_limit", 4558), ("stalled_delta_limit", 8)])
def test_no_profile_or_budget_widening(prepared, tmp_path, key, value):
    target = tmp_path / "copy"
    shutil.copytree(prepared[0], target)
    manifest = json.loads((target / "manifest.json").read_text())
    manifest[key] = value
    (target / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        PREP.verify(target)


@pytest.mark.parametrize("kind", ["missing", "extra", "source", "symlink", "wrong_expected"])
def test_fail_closed_source_inventory(prepared, tmp_path, kind):
    target = tmp_path / "copy"
    shutil.copytree(prepared[0], target)
    source = target / "frozen_sources"
    if kind == "missing":
        (source / PREP.CHECKS).rename(target / "retained_missing_source")
    elif kind == "extra":
        (source / "undeclared.txt").write_text("extra")
    elif kind == "source":
        (source / PREP.CHECKS).write_text("changed")
    elif kind == "symlink":
        path = source / PREP.CHECKS
        path.rename(target / "retained_source")
        path.symlink_to(target / "retained_source")
    expected = "0" * 64 if kind == "wrong_expected" else None
    with pytest.raises(ValueError):
        PREP.verify(target, expected)


def test_existing_or_alias_output_is_not_modified(prepared, tmp_path):
    before = PREP.digest((prepared[0] / "manifest.json").read_bytes())
    with pytest.raises(FileExistsError):
        PREP.freeze(prepared[0], ORIGINAL)
    assert PREP.digest((prepared[0] / "manifest.json").read_bytes()) == before
    for target in (prepared[0], tmp_path / "absent"):
        alias = tmp_path / ("alias_" + target.name)
        alias.symlink_to(target, target_is_directory=True)
        with pytest.raises(ValueError, match="symlink"):
            PREP.freeze(alias / "new", ORIGINAL)


PROTOCOL_MARKER = ("INVERSE_SEALED_ACTUAL_PASS E=1 L=1 R=1 B=1 O=1 fast_mhz=175 takes=19456 "
                   "publications=38 releases=38 owned_reservation_edges=76 public_commit_delta=1813 "
                   "current_veto_checks=3 held_final_checks=7\n")


@pytest.mark.parametrize("change", ["missing", "duplicate", "late_error", "early_fatal", "takes", "unknown", "duplicate_field"])
def test_protocol_terminal_rejects_incomplete_or_late_failure(change):
    log = PROTOCOL_MARKER
    if change == "missing":
        log = ""
    elif change == "duplicate":
        log += log
    elif change == "late_error":
        log += "ERROR late failure\n"
    elif change == "early_fatal":
        log = "Fatal early failure\n" + log
    elif change == "takes":
        log = log.replace("takes=19456", "takes=19455")
    elif change == "unknown":
        log = log.replace("releases=38", "releases=x")
    else:
        log = log.replace("E=1", "E=1 E=1")
    with pytest.raises(ValueError):
        PREP.require_protocol_terminal(log)


@pytest.mark.parametrize("behavior", ["launch", "mutation", "postmutation", "environment"])
def test_mocked_runner_always_checks_after_failure_and_never_publishes_success(prepared, tmp_path, behavior):
    output = tmp_path / "copy"
    shutil.copytree(prepared[0], output)
    source = output / "frozen_sources"
    wrapper = next((ORIGINAL / "project").glob("*.gen/sources_1/ip/*/synth/*.vhd"))
    text = """proc version {args} {return 2022.2}
proc set_param {args} {}
proc create_project {name directory args} {file mkdir $directory}
proc current_project {args} {return mocked}
proc set_property {args} {}
proc get_ips {args} {return {}}
proc create_ip {args} {}
proc add_files {args} {}
proc get_filesets {args} {return sim_1}
proc get_files {args} {return {}}
proc close_sim {args} {}
proc close_project {args} {}
"""
    text += f"proc generate_target {{args}} {{file mkdir [file dirname $::wrapper]; file copy {{{wrapper}}} $::wrapper}}\n"
    text += "proc launch_simulation {args} {\n"
    if behavior == "mutation":
        text += "set c [open [file join $::source_dir starlink_pss_kernel_rom.v] a]; puts $c MUTATED; close $c\n"
    if behavior == "environment":
        text += "foreach name {PYTHONHOME PYTHONPATH LD_LIBRARY_PATH} {if {$::env($name) ne {/invalid-vendor}} {error PARENT_ENV_CHANGED}}\n"
    text += "}\n" if behavior == "postmutation" else "error OFFLINE_LAUNCH_STOP\n}\n"
    if behavior == "postmutation":
        text += """rename exec real_exec
proc exec {args} {
  if {[lsearch -exact $args results] >= 0} {return MOCK_RESULT_NOT_ACTUAL}
  return [uplevel 1 [linsert $args 0 real_exec]]
}
proc close_project {args} {
  set c [open [file join $::source_dir starlink_pss_kernel_rom.v] a]; puts $c MUTATED; close $c
}
"""
    expected = PREP.digest((output / "manifest.json").read_bytes())
    python = "/home/mouse9911/gits/pluto-plus-utils/.venv/bin/python"
    text += f"set argc 3\nset argv [list {{{output}}} {{{python}}} {expected}]\nsource {{{source / PREP.RUNNER}}}\n"
    mock = tmp_path / "mock_NOT_VENDOR.tcl"
    mock.write_text(text)
    environment = {key: value for key, value in os.environ.items()
                   if key not in ("LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH")}
    if behavior == "environment":
        environment.update(dict.fromkeys(("LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH"), "/invalid-vendor"))
    result = subprocess.run(["tclsh", str(mock)], cwd="/", env=environment,
        capture_output=True, text=True, check=False, timeout=30)
    (tmp_path / "mock.log").write_text(result.stdout + result.stderr)
    assert result.returncode != 0
    outcome = (output / "run_outcome.txt").read_text()
    assert f"run_status={0 if behavior == 'postmutation' else 1}" in outcome
    assert f"after_status={1 if behavior in ('mutation', 'postmutation') else 0}" in outcome
    assert not (output / "results.json").exists()
    assert "INVERSE_SEALED_ACTUAL_CORE_VERIFIED" not in result.stdout
    if behavior != "postmutation":
        assert "OFFLINE_LAUNCH_STOP" in result.stderr


@pytest.fixture(scope="module")
def protocol_model_fixture(history, tmp_path_factory):
    """Input-oracle/clock model only; deliberately not a candidate FFT receipt.

    Old admitted jobs supply immutable identities. Publication/reader clocks
    below are synthetic expectations, never relabeled actual execution.
    """
    source = ORIGINAL / "frozen_sources"
    words = [int(line, 16) for line in (source / "inverse_q17.mem").read_text().splitlines()]
    ef = [int(line, 16) for line in (source / "forward_exponents.mem").read_text().splitlines()]
    ei = [int(line, 16) for line in (source / "inverse_exponents.mem").read_text().splitlines()]
    rows = []
    slow_negative_edges = [11300000 + cycle * 10000000 for cycle in range(200000)]
    for job in history:
        if not job["inverse"]:
            continue
        epoch, start, admit = job["epoch"], job["start"], job["admit"]
        block = (start - 0x200000000 - 65536 * epoch) // 447
        fixture = block % 3
        metadata = (1 << 74) + start * 1024 + ef[fixture] * 32 + ei[fixture]
        publication = admit + 1813
        # Explicit event-time enumeration, not calls into TIMING.read_cycles
        # or reader_ack_cycle. Both domains retain their actual origins.
        slow = 0
        while 6300000 + slow * 10000000 <= 2857143 + 5714286 * publication:
            slow += 1
        slow += 4
        accepted = []
        while len(accepted) < 512:
            if epoch == 1 or slow % 17 < 13:
                accepted.append(slow)
            slow += 1
        fast = publication
        while 2857143 + 5714286 * fast <= 6300000 + (accepted[-1] + 1) * 10000000:
            fast += 1
        ack = fast + 2
        schedule = [("ADMIT", admit, 0)]
        for position in range(512):
            if position == 511:
                schedule.append(("QUALIFY", admit + 1810, position))
            schedule.append(("TAKE", admit + 1299 + position, position))
        schedule += [("CERT", admit + 1811, 511), ("SEAL", admit + 1812, 511),
                     ("PUB", publication, 511), ("ACK", ack, 511), ("REL", ack + 1, 511), ("REUSE", ack + 2, 511)]
        for event, fast, position in schedule:
            time_fs = 2857143 + 5714286 * fast
            assert time_fs < slow_negative_edges[-1]
            slow_counter = bisect_right(slow_negative_edges, time_fs)
            rows.append({"event": event, "epoch": epoch, "fast_cycle": fast, "slow_cycle": slow_counter,
                         "start": start, "lease": block % 4, "position": position,
                         "data": "0" if event == "ADMIT" else f"{words[fixture * 512 + position]:09x}",
                         "metadata": "0" if event == "ADMIT" else f"{metadata:019x}"})
    root = tmp_path_factory.mktemp("protocol_model_NOT_ACTUAL")
    path = root / "synthetic_protocol.csv"
    with path.open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    (root / "scope.txt").write_text("SYNTHETIC_PROTOCOL_ORACLE_ONLY_NO_ACTUAL_FFT_OR_SERVICE_QUALIFICATION\n")
    return path, rows, words, ef, ei


def test_complete_synthetic_protocol_model_receipt_is_explicitly_not_actual(protocol_model_fixture, history):
    path, _, words, ef, ei = protocol_model_fixture
    assert TIMING.verify_protocol(path, history, words, ef, ei) == {
        "lifetimes": 38, "takes": 19456, "ordered_protocol_events": 19760,
        "qualification_to_publication": 3, "ack_to_release": 1,
    }


@pytest.mark.parametrize("mutation", ["terminal_only", "truncate", "duplicate", "drop_final", "lease", "metadata74",
    "position", "data", "qualification", "seal", "publication", "early_ack", "domain_swap"])
def test_protocol_model_rejects_specific_missing_or_changed_event(protocol_model_fixture, history, tmp_path, mutation):
    _, source_rows, words, ef, ei = protocol_model_fixture
    rows = copy.deepcopy(source_rows)
    if mutation == "terminal_only":
        rows = []
    elif mutation == "truncate":
        rows.pop()
    elif mutation == "duplicate":
        rows.insert(1, rows[1])
    elif mutation == "drop_final":
        rows = [row for row in rows if not (row["event"] == "TAKE" and row["position"] == 511)]
    else:
        wanted = {"qualification": "QUALIFY", "seal": "SEAL", "publication": "PUB", "early_ack": "ACK"}.get(mutation, "TAKE")
        row = next(row for row in rows if row["event"] == wanted)
        if mutation == "lease":
            row["lease"] ^= 1
        elif mutation == "metadata74":
            row["metadata"] = f"{int(row['metadata'], 16) ^ (1 << 74):019x}"
        elif mutation == "data":
            row["data"] = f"{int(row['data'], 16) ^ 1:09x}"
        elif mutation == "position":
            row["position"] += 1
        elif mutation == "domain_swap":
            row["fast_cycle"], row["slow_cycle"] = row["slow_cycle"], row["fast_cycle"]
        else:
            row["fast_cycle"] -= 1
    path = tmp_path / "mutated_model_NOT_ACTUAL.csv"
    with path.open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=source_rows[0])
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError):
        TIMING.verify_protocol(path, history, words, ef, ei)


@pytest.mark.parametrize("case", ["plain", "escaped", "missing", "duplicate", "mixed_root"])
def test_exact_diagnostic_enumeration_reaches_only_unchanged_run_all(prepared, tmp_path, case):
    source = prepared[0] / "frozen_sources"
    root = PREP.wave_roots()[int(case != "plain")]
    old_paths = (SIM / "arithmetic_diagnostic_signals.txt").read_text().splitlines()
    old_paths += (SIM / "local_guard_diagnostic_signals.txt").read_text().splitlines()
    objects = [root + "/" + path.split("/", 2)[2] for path in old_paths]
    inverse = [root + "/" + leaf for leaf in PREP.WAVE_FIELDS]
    if case == "missing":
        inverse.pop()
    elif case == "duplicate":
        inverse.append(inverse[-1])
    elif case == "mixed_root":
        inverse[-1] = PREP.wave_roots()[0] + "/" + PREP.WAVE_FIELDS[-1]
    objects += inverse
    body = "set objects [list " + " ".join("{" + item + "}" for item in objects) + "]\n"
    body += """proc current_wave_config {} {return existing}
proc get_objects {args} {return $::objects}
proc log_wave {args} {lappend ::logged $args}
proc run {args} {error OFFLINE_UNCHANGED_RUN_ALL_REACHED}
"""
    body += f"source {{{source / PREP.DIAGNOSTICS}}}\n"
    script = tmp_path / "diagnostic_mock_NOT_VENDOR.tcl"
    script.write_text(body)
    result = subprocess.run(["tclsh", str(script)], cwd=tmp_path, capture_output=True,
                            text=True, check=False, timeout=15)
    (tmp_path / "diagnostic_mock.log").write_text(result.stdout + result.stderr)
    assert result.returncode != 0  # The unchanged run-all is an explicit trap.
    if case in ("plain", "escaped"):
        assert "OFFLINE_UNCHANGED_RUN_ALL_REACHED" in result.stderr
        assert (tmp_path / "inverse_protocol_diagnostic_signals.txt").read_text().splitlines() == inverse
        assert (tmp_path / "inverse_protocol_diagnostic_receipt.txt").read_text() == "INVERSE_PROTOCOL_WAVE_DIAGNOSTICS_ENABLED objects=19\n"
    else:
        assert "INVERSE_PROTOCOL_WAVE_MISSING_OR_DUPLICATE" in result.stderr
        assert "OFFLINE_UNCHANGED_RUN_ALL_REACHED" not in result.stderr
        assert not (tmp_path / "inverse_protocol_diagnostic_receipt.txt").exists()

"""Offline source-specific actual admission/result negatives, never vendor."""
import csv
import json
import re
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.test_checked_product_read import clean_env
from tests.starlink_oracle.test_prepare_checked_product_actual import ACQ, ORIGIN

RUN = runpy.run_path(str(ACQ / "prepare_checked_product_actual_run.py"))
RESULT = runpy.run_path(str(ACQ / "checked_product_actual_result.py"))
OFFLINE = Path("/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/checked-product-actual-gate-v1.zA7kZBTI/pytest/enabled_actual0/prepared")


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    root = tmp_path_factory.mktemp("checked_run")
    output = root / "prepared"
    result = RUN["prepare"](OFFLINE, output)
    (root / "receipt.json").write_text(json.dumps(result, indent=2))
    shutil.copyfile(Path(__file__), root / Path(__file__).name)
    return output


def test_exact_runner_inverse_and_runtime_closure(prepared):
    original = (ORIGIN / RUN["RUNNER"]).read_text()
    body, edits = RUN["runner"](original)
    assert len(edits) == 6 and body == (prepared / RUN["RUNNER"]).read_text()
    for old, new in reversed(edits):
        assert body.count(new) == 1
        body = body.replace(new, old, 1)
    assert body == original
    assert RUN["verify_prepared"](prepared) == RUN["SETTINGS"]
    assert not (prepared / "project").exists()
    assert "puts [fault_cdc_verify_receipt" not in (prepared / RUN["RUNNER"]).read_text()
    assert "proc fault_cdc_verify_receipt" in (prepared / RUN["RUNNER"]).read_text()


@pytest.mark.parametrize("key", list(RUN["SETTINGS"]))
@pytest.mark.parametrize("mutation", ["missing", "duplicate", "wrong"])
def test_every_explicit_setting_fail_closed(prepared, tmp_path, key, mutation):
    output = tmp_path / "copy"
    shutil.copytree(prepared, output)
    path = output / "settings.tcl"
    token = f"{key}={RUN['SETTINGS'][key]}"
    replacement = {"missing": "", "duplicate": token + " " + token, "wrong": f"{key}=2"}[mutation]
    path.write_text(path.read_text().replace(token, replacement))
    with pytest.raises(ValueError, match="setting"):
        RUN["verify_prepared"](output)


@pytest.mark.parametrize("name", [RUN["RUNNER"], "frozen_sources/starlink_pss_fft_bank_owned_checked_product.v",
    "frozen_sources/starlink_pss_checked_product_actual_observer.svh", "frozen_sources/inverse_q17.mem",
    "frozen_sources/create_shared_realtime_xfft_ip.tcl", "frozen_sources/starlink_pss_fault_cdc_actual_observer.svh",
    "frozen_sources/starlink_pss_rom_actual_observer.svh", "checked-passing-P1-top.sv"])
def test_rehashed_source_changes_rejected(prepared, tmp_path, name):
    output = tmp_path / "copy"
    shutil.copytree(prepared, output)
    path = output / name
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError):
        RUN["verify_prepared"](output)


def test_no_overwrite_alias_actor_or_old_preparation(prepared, tmp_path):
    with pytest.raises(FileExistsError):
        RUN["prepare"](OFFLINE, prepared)
    with pytest.raises(ValueError):
        RUN["read_offline"](ORIGIN)
    link = tmp_path / "alias"
    link.symlink_to(prepared, target_is_directory=True)
    with pytest.raises(ValueError):
        RUN["verify_prepared"](link)
    output = tmp_path / "copy"
    shutil.copytree(prepared, output)
    (output / "frozen_sources/actor.v").write_text("module actor;endmodule\n")
    with pytest.raises(ValueError, match="unexpected"):
        RUN["verify_prepared"](output)


def test_portable_cli_and_no_actor_result_admission(prepared):
    result = subprocess.run(["/home/mouse9911/gits/pluto-plus-utils/.venv/bin/python", "-B",
        str(prepared / RUN["SELF"]), "--verify-prepared", str(prepared)], cwd="/", env=clean_env(),
        capture_output=True, text=True, timeout=15, check=False)
    assert result.returncode == 0 and json.loads(result.stdout) == RUN["SETTINGS"], result.stderr
    with pytest.raises(FileNotFoundError):
        RESULT["verify_result"](prepared)


def synthetic_terminals():
    # Parser fixture ONLY. These edited strings are never written as a vendor
    # result or combined with fake IP artifacts. Old actual itself must reject.
    old = (ORIGIN / "project/exact_control_actual.sim/sim_1/behav/xsim/simulate.log").read_text()
    markers = ["FFT_BANK_OWNED_SLICE_PASS", "COMPLETED_INPUT_ACTUAL_CORE_EQ_PASS",
        "RAW_READY_CERTIFIED_ACK_PASS", "REGISTERED_SCHEDULING_PASS", "PREFLIGHT_REASON_SPLIT_PASS",
        "HELD_PHASE_INPUT_PASS", "BALANCED_IDENTITY_ACTUAL_PASS", "HELD_PREFLIGHT_ACTUAL_PASS",
        "PAYLOAD_BUBBLES_ACTUAL_PASS", "FORWARD_RETIREMENT_ACTUAL_PASS", "EXACT_CONTROL_EXTRA_EPOCHS_PASS",
        "FAULT_CDC_ACTUAL_PASS", "ROM_READ_AHEAD_ACTUAL_PASS"]
    rows = [re.search(r"^" + name + r"[^\n]*$", old, re.MULTILINE)[0] for name in markers]
    replacements = {"COMPLETED_INPUT_ACTUAL_CORE_EQ_PASS": "CHECKED_PORT_FED_GUARD_PASS",
        "RAW_READY_CERTIFIED_ACK_PASS": "CHECKED_CAPACITY_ACTUAL_ACK_PASS",
        "HELD_PHASE_INPUT_PASS": "CHECKED_INPUT_PHASE_PASS", "BALANCED_IDENTITY_ACTUAL_PASS": "CHECKED_SOURCE_IDENTITY_ACTUAL_PASS",
        "HELD_PREFLIGHT_ACTUAL_PASS": "CHECKED_PREFLIGHT_ACTUAL_PASS"}
    for old_marker, new_marker in replacements.items():
        rows = [x.replace(old_marker, new_marker) for x in rows]
    rows = [re.sub(r"raw_ready_differences=\d+", "raw_ready_differences=0", x) for x in rows]
    owner = dict.fromkeys(RESULT["OWNER_COUNTS"], 1)
    owner.update(jobs=44, publications=44, seals=44, acks=44, starts=44, releases=44,
        products=22528, core_takes=22528, raw_takes=22528, raw_offers=22534, raw_bad_offers=6)
    row = "CHECKED_PRODUCT_ACTUAL_PASS enabled=1 " + " ".join(f"{key}={owner[key]}" for key in RESULT["OWNER_COUNTS"])
    rows.append(row + " source=actual_ports_and_independent_origin changed_latency=1 raw217_claim=0")
    return "Time resolution is 1 fs\n" + "\n".join(rows) + "\n"


def test_synthetic_terminal_parser_only(prepared):
    owner, rows = RESULT["verify_terminals"](synthetic_terminals(), prepared / "frozen_sources")
    assert owner["jobs"] == 44 and len(rows) == 10


@pytest.mark.parametrize("old,new", [
    ("", "\nFATAL_ERROR: Simulation kernel crashed\n"),
    ("", "\nSegmentation fault (core dumped)\n"),
    ("", "\nCHECKED_OBSERVER_ACTOR_END actor_only=1\n"),
    ("", "\nEXACT_CONTROL_ACTUAL_PASS registered=1\n"),
    ("raw217_claim=0", "raw217_claim=1"), ("raw_bad_offers=6", "raw_bad_offers=0"),
    ("matrix_cases=84", "matrix_cases=83"), ("active_fault_cases=12", "active_fault_cases=11"),
    ("final_faults=2 held_final_stalls=3", "final_faults=1 held_final_stalls=3"),
    ("one_sided_resets=2 healthy_recoveries=4", "one_sided_resets=2 healthy_recoveries=3"),
    ("nominal_max_forward_interval_cycles=4548", "nominal_max_forward_interval_cycles=5216"),
    ("private_reset_edges=164648", "private_reset_edges=0"),
    ("final_fault_edges=115", "final_fault_edges=0"),
    ("pre=1 post=1", "pre=1 post=0"),
])
def test_failure_scope_and_exact_terminal_negatives(prepared, old, new):
    log = synthetic_terminals()
    assert not old or old in log
    altered = log + new if not old else log.replace(old, new)
    with pytest.raises(ValueError):
        RESULT["verify_terminals"](altered, prepared / "frozen_sources")


def cycle_fixture(path, gap=20):
    rows, cycle = [], 0
    for epoch, blocks in ((1, 32), (2, 6)):
        for _ in range(blocks):
            for tick in range(gap):
                row = ["0"]*24
                row[0:5] = [str(cycle), str(epoch), str(epoch-1), "1", "6"]
                row[21] = "1"
                if tick in (0, 1):
                    row[6], row[8] = "1", str(tick)
                elif tick == gap-1:
                    row[4], row[8] = "2", "0"
                else:
                    row[8] = "1"
                rows.append(row)
                cycle += 1
    with (path / "fft_bank_owned_trace.csv").open("w") as stream:
        stream.write(RESULT["TRACE_HEADER"] + "\n")
        csv.writer(stream, lineterminator="\n").writerows(rows[:-1])
    with (path / "exact_control_extra_trace.csv").open("w") as stream:
        csv.writer(stream, lineterminator="\n").writerows(rows[-1:])
    return {"pre": cycle}


def test_complete_cycle_service_parser_synthetic_only(tmp_path):
    owner = cycle_fixture(tmp_path)
    streams, service = RESULT["verify_cycles"](tmp_path, owner)
    assert list(map(len, service.values())) == [32, 6] and len(streams) == 2


@pytest.mark.parametrize("mutation", ["truncate", "gap", "fault", "missing_last", "owner_count"])
def test_trace_completeness_and_service_negatives(tmp_path, mutation):
    owner = cycle_fixture(tmp_path)
    path = tmp_path / "fft_bank_owned_trace.csv"
    body = path.read_text()
    if mutation == "truncate":
        path.write_text(body[:-1])
    elif mutation == "gap":
        path.write_text(body.replace("0,1,0,1,6", "9,1,0,1,6", 1))
    elif mutation == "fault":
        lines = body.splitlines()
        row = lines[3].split(","); row[22] = "1"; lines[3] = ",".join(row)
        path.write_text("\n".join(lines) + "\n")
    elif mutation == "missing_last":
        (tmp_path / "exact_control_extra_trace.csv").write_text("0,0\n")
    else:
        owner["pre"] += 1
    with pytest.raises(ValueError):
        RESULT["verify_cycles"](tmp_path, owner)


def test_absolute_service5215_boundary(tmp_path):
    owner = cycle_fixture(tmp_path, 5215)
    streams, service = RESULT["verify_cycles"](tmp_path, owner)
    assert max(streams[0]["forward_interval_cycles"][1]) == 5215
    assert max(service[1]) == 5214
    owner = cycle_fixture(tmp_path, 5216)
    with pytest.raises(ValueError, match="5215"):
        RESULT["verify_cycles"](tmp_path, owner)


def ledger_fixture(path, source):
    data = [int(x, 16) for x in (source / "product_q17.mem").read_text().splitlines()][:512]
    exponent = int((source / "forward_exponents.mem").read_text().splitlines()[0], 16)
    metadata = (1 << 69) | (((1 << 33) + 65536) << 5) | exponent
    rows = [[n, 1, 1, n, f"{word:x}", f"{metadata:x}", "2"] for n, word in enumerate(data)]
    rows += [[515, 1, 2, 0, "0", f"{metadata:x}", "2"], [525, 1, 3, 0, "0", f"{metadata:x}", "2"]]
    rows += [[530+n, 1, 4, n, f"{word:x}", f"{metadata:x}", "2"] for n, word in enumerate(data)]
    target = path / "checked_product_ownership_trace.csv"
    with target.open("w") as stream:
        stream.write("cycle,epoch,event,position,data,metadata,lease\n")
        csv.writer(stream, lineterminator="\n").writerows(rows)
    return {"products": 512, "publications": 1, "acks": 1, "core_takes": 512}, rows


def test_ledger_full512_numerical_tokens_synthetic_only(prepared, tmp_path):
    owner, _ = ledger_fixture(tmp_path, prepared / "frozen_sources")
    assert RESULT["verify_ledger"](tmp_path, prepared / "frozen_sources", owner)["rows"] == 1026


@pytest.mark.parametrize("mutation", ["product", "core", "ordinal", "lease", "metadata", "no_ack", "count", "truncate"])
def test_same_token_numeric_origin_and_ledger_negatives(prepared, tmp_path, mutation):
    owner, rows = ledger_fixture(tmp_path, prepared / "frozen_sources")
    if mutation in ("product", "core"):
        rows[37 if mutation == "product" else 514+37][4] = "ffffff"
    elif mutation == "ordinal":
        rows[514+37][3] = 7
    elif mutation == "lease":
        rows[514+37][6] = "1"
    elif mutation == "metadata":
        rows[513][5] = "123"
    elif mutation == "no_ack":
        del rows[513]
    elif mutation == "count":
        owner["core_takes"] = 511
    path = tmp_path / "checked_product_ownership_trace.csv"
    with path.open("w") as stream:
        stream.write("cycle,epoch,event,position,data,metadata,lease\n")
        csv.writer(stream, lineterminator="\n").writerows(rows)
    if mutation == "truncate":
        path.write_bytes(path.read_bytes()[:-1])
    with pytest.raises(ValueError):
        RESULT["verify_ledger"](tmp_path, prepared / "frozen_sources", owner)


@pytest.mark.parametrize("mode", ["pre_create", "wrong_readback", "correct_readback"])
def test_mocked_tcl_stops_before_vendor_and_sanitizes_child(prepared, tmp_path, mode):
    # Tcl command interception is explicitly mock-only. It creates no project,
    # does not source/execute the real IP factory, and never launches simulation.
    program = r'''
set argc 1
set argv [list [lindex $argv 0]]
proc version {arg} {return "2022.2"}
proc set_param {args} {}
proc current_project {} {return "mock_project"}
proc get_filesets {args} {return "mock_fileset"}
proc get_files {args} {return "mock_files"}
proc add_files {args} {}
proc set_property {key value target} {if {$key eq "generic"} {set ::mock_generic $value}}
proc get_property {key target} {
  if {$::mode eq "wrong_readback"} {return [concat $::mock_generic CHECKED_PRODUCT_BANK=0]}
  return $::mock_generic
}
proc create_project {args} {
  puts "MOCK_CREATE_PROJECT_REACHED"
  if {$::mode eq "pre_create"} {error "INTENTIONAL_PRE_CREATE_STOP"}
}
proc launch_simulation {args} {puts "MOCK_LAUNCH_BOUNDARY_REACHED";error "INTENTIONAL_BEFORE_VENDOR_STOP"}
rename source original_source
proc source {name} {
  if {[file tail $name] eq "create_shared_realtime_xfft_ip.tcl"} {
    proc ::pss_create_shared_realtime_xfft_ip {wrapper} {puts "MOCK_FACTORY_NOT_EXECUTED"}
    return
  }
  uplevel 1 [list original_source $name]
}
set mode MODE_VALUE
set status [catch {source [file join [lindex $argv 0] frozen_sources simulate_exact_control_prepared.tcl]} message]
puts "MOCK_STATUS=$status MESSAGE=$message"
puts "PARENT_ENV=$env(PYTHONHOME),$env(PYTHONPATH),$env(LD_LIBRARY_PATH)"
'''.replace("MODE_VALUE", mode)
    driver = tmp_path / "mock.tcl"
    driver.write_text(program)
    env = clean_env()
    env.update(PYTHONHOME="/poison-python-home", PYTHONPATH="/poison-python-path", LD_LIBRARY_PATH="/poison-loader")
    result = subprocess.run(["tclsh", str(driver), str(prepared)], env=env, capture_output=True,
        text=True, timeout=30, check=False)
    (tmp_path / "mock.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0 and "MOCK_CREATE_PROJECT_REACHED" in result.stdout, result.stdout + result.stderr
    assert "PARENT_ENV=/poison-python-home,/poison-python-path,/poison-loader" in result.stdout
    assert not (prepared / "project").exists()
    expected = {"pre_create": "INTENTIONAL_PRE_CREATE_STOP", "wrong_readback": "generic readback mismatch",
                "correct_readback": "INTENTIONAL_BEFORE_VENDOR_STOP"}[mode]
    assert expected in result.stdout and "MOCK_STATUS=1" in result.stdout, result.stdout
    assert ("MOCK_LAUNCH_BOUNDARY_REACHED" in result.stdout) == (mode == "correct_readback")

"""Explicit phase-input contract: exact delta and general-caller public traces.

The enabled trace supplies the complete general fault tuple, not the service's
smaller producer predicate. Actual service/premise evidence is separate.
"""
import hashlib
import os
import re
import subprocess
from pathlib import Path

import pytest

HDL = Path(os.environ.get("STARLINK_PSS_TEST_HDL", Path(__file__).resolve().parents[2] / "hdl"))
ACQ = HDL / "library/starlink_pss_acquisition"
BASE = "af96c48ed34a58d54c548b4a2dc414aeff593c39"


def tokens(source):
    return re.sub(r"\s+", "", re.sub(r"//[^\n]*", "", source))


def frozen(name):
    result = subprocess.run(["git", "-C", str(HDL), "show", f"{BASE}:library/starlink_pss_acquisition/{name}.v"],
                            text=True, capture_output=True, timeout=10, check=True)
    return tokens(result.stdout)


def replace_once(source, old, new):
    assert source.count(old) == 1
    return source.replace(old, new, 1)


def test_entire_guard_delta_preserves_full_faults_and_publication_checks():
    name = "starlink_pss_realtime_result_guard"
    baseline = frozen(name)
    candidate = tokens((ACQ / f"{name}.v").read_text())
    for fragment in [",parameterintegerUSE_PHASE_INPUT_FAULT=0", "inputwirephase_input_fault_now,",
                     ('if(USE_PHASE_INPUT_FAULT!=0&&USE_PHASE_INPUT_FAULT!=1)'
                      '$fatal(1,"USE_PHASE_INPUT_FAULTmustbezeroorone");'),
                     ("wirephase_input_fault=USE_PHASE_INPUT_FAULT?phase_input_fault_now:"
                      "(external_fault_now||certified_input_beat||certified_input_complete);")]:
        candidate = replace_once(candidate, fragment, "")
    old_idle = re.search(r"wireidle_fault_now=.*?;", baseline).group()
    new_idle = "wireidle_fault_now=phase_input_fault||mailbox_input_fault||core_event_frame_started||core_status_tvalid||core_output_tvalid;"
    candidate = replace_once(candidate, new_idle, old_idle)
    old_final = re.search(r"wirefinal_fault_now=.*?;", baseline).group()
    new_final = "wirefinal_fault_now=phase_input_fault||mailbox_input_fault||!output_bank_reserved||core_event_frame_started||core_status_tvalid||core_output_tvalid||watchdog_error;"
    candidate = replace_once(candidate, new_final, old_final)
    candidate = replace_once(candidate,
        "wirefinal_commit=resetn&&active&&!protocol_fault&&return_valid&&return_last&&final_qualified&&!final_fault_now&&mailbox_input_ready;",
        "wirefinal_commit=mailbox_accept&&return_last;")
    assert candidate == baseline


def test_entire_service_delta_is_only_explicit_phase_contract_and_exact_fence():
    name = "starlink_pss_shared_realtime_xfft_service"
    baseline = frozen(name)
    candidate = tokens((ACQ / f"{name}.v").read_text())
    for fragment in ["wirephase_input_fault_now=(core_aresetn&&input_job_start)||input_guard_fault||input_fault_fast_sync[1]||vendor_fault_now||fast_fault;",
                     "#(.USE_PHASE_INPUT_FAULT(1))", ".phase_input_fault_now(phase_input_fault_now),"]:
        candidate = replace_once(candidate, fragment, "")
    candidate = replace_once(candidate,
        "wirefinal_fence=checked_input_complete&&!input_guard_fault&&!(core_aresetn&&input_job_start);",
        "wirefinal_fence=checked_input_complete&&!input_guard_fault&&!input_fault_now;")
    assert candidate == baseline


@pytest.mark.parametrize("mode,mutation", [(0, 0), (1, 0), (1, 1), (2, 0)])
def test_public_guard_contract_with_explicit_full_tuple_adapter(tmp_path, mode, mutation):
    top = "tb_starlink_pss_realtime_occupancy"
    executable = tmp_path / "phase.vvp"
    # Test-only adapter: exactly the old public stimulus, with an explicitly
    # selected guard mode and a caller that summarizes the FULL input tuple.
    # Keep the committed bench directly usable with parameter-free netlists.
    bench_source = (ACQ / "tb" / f"{top}.sv").read_text()
    bench_source = replace_once(bench_source,
        "wire phase_input_fault_now = 1'bz;",
        "wire phase_input_fault_now = " + ("1'bz;" if mode == 0 else
        ("" if mutation else "external_fault_now || ") + "certified_input_beat || certified_input_complete;"))
    bench_source = replace_once(bench_source, "starlink_pss_realtime_result_guard dut (.*);",
        f"starlink_pss_realtime_result_guard #(.USE_PHASE_INPUT_FAULT({mode})) dut (.*);")
    bench = tmp_path / f"{top}.sv"
    bench.write_text(bench_source)
    compile_result = subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", top, "-o", str(executable),
        str(ACQ / "starlink_pss_realtime_result_guard.v"),
        str(ACQ / "tb/starlink_pss_realtime_result_guard_ff4229_golden.v"),
        str(bench),
    ], text=True, capture_output=True, timeout=30, check=False)
    assert compile_result.returncode == 0, compile_result.stdout + compile_result.stderr
    result = subprocess.run(["vvp", str(executable)], text=True, capture_output=True, timeout=60, check=False)
    (tmp_path / "phase.log").write_text(result.stdout + result.stderr)
    if mode == 2:
        assert result.returncode != 0 and "USE_PHASE_INPUT_FAULT must be zero or one" in result.stdout
    elif mutation:
        assert result.returncode != 0 and "OCCUPANCY_PUBLIC_MISMATCH" in result.stdout
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.count("OCCUPANCY_REACHABLE_PASS jobs=256 exact_words=131072 ack_fault_cases=254") == 1


@pytest.mark.parametrize("mode", [0, 1])
def test_actual_phase_mode_netlist_preserves_public_guard_contract(tmp_path, mode):
    measured = os.environ.get("STARLINK_PSS_PHASE_INPUT_NETLIST_DIR")
    if not measured:
        pytest.skip("explicit actual Vivado phase-mode measurement required")
    measured = Path(measured)
    scope = (measured / "scope.txt").read_text()
    assert "PHASE_INPUT_DEPENDENCY_MEASURED whole_receiver_and_timing_unqualified=1" in scope
    source_hash = hashlib.sha256((ACQ / "starlink_pss_realtime_result_guard.v").read_bytes()).hexdigest()
    assert f"source_sha256={source_hash}\n" in scope
    netlist = measured / f"mode{mode}_netlist.v"
    netlist_hash = hashlib.sha256(netlist.read_bytes()).hexdigest()
    assert f"mode{mode}_netlist_sha256={netlist_hash}\n" in scope
    top = "tb_starlink_pss_realtime_occupancy"
    bench = tmp_path / f"{top}.sv"
    source = (ACQ / "tb" / f"{top}.sv").read_text()
    if mode:
        source = replace_once(source, "wire phase_input_fault_now = 1'bz;",
            "wire phase_input_fault_now = external_fault_now || certified_input_beat || certified_input_complete;")
    bench.write_text(source)
    vendor = Path("/opt/Xilinx/Vivado/2022.2")
    environment = dict(os.environ, LD_LIBRARY_PATH=str(vendor / "lib/lnx64.o/SuSE"))
    commands = [
        [str(vendor / "bin/xvlog"), "--sv", str(netlist),
         str(ACQ / "tb/starlink_pss_realtime_result_guard_ff4229_golden.v"),
         str(bench), str(vendor / "data/verilog/src/glbl.v")],
        [str(vendor / "bin/xelab"), "--debug", "typical", "--relax", "--mt", "2",
         "-L", "unisims_ver", top, "glbl", "-s", "phase_snapshot"],
        [str(vendor / "bin/xsim"), "phase_snapshot", "-runall"],
    ]
    for index, command in enumerate(commands):
        result = subprocess.run(command, cwd=tmp_path, env=environment, capture_output=True,
                                text=True, timeout=120, check=False)
        (tmp_path / f"phase_netlist_{index}.log").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
    marker = ("OCCUPANCY_REACHABLE_PASS jobs=256 exact_words=131072 ack_fault_cases=254 "
              "healthy_ack_cases=2 public_golden=1 no_internal_deposits=1")
    assert result.stdout.splitlines().count(marker) == 1

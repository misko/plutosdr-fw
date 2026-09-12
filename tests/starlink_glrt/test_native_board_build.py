"""Invalid native board selections fail before creating a build or using tools."""
import hashlib
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("rate,flag", [("2500000", "--native-refinement"),
    ("25000000", "--native-refinement"), ("60000000", "--native"), ("60000001", "--native-refinement"),
    ("25000000", "--native-lean"), ("60000001", "--native-lean"),
    ("25000000", "--native-scheduled"), ("60000001", "--native-scheduled")])
def test_invalid_native_build_selection_creates_no_evidence_directory(tmp_path, rate, flag):
    repo = Path(__file__).resolve().parents[2]
    output = tmp_path/"board"
    result = subprocess.run(["bash", str(repo/"scripts/build_glrt_board.sh"), rate, str(output), flag],
        capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 2
    assert not output.exists()


def test_tracking_build_refuses_a_duplicate_window_netlist_before_checkout(tmp_path):
    repo = Path(__file__).resolve().parents[2]
    netlist = tmp_path/"local"; netlist.mkdir()
    names = ("starlink_glrt_local_control.dcp", "shared_window.txt")
    for name in names: (netlist/name).write_text("0\n")
    (netlist/"outputs.sha256").write_text("".join(
        f"{hashlib.sha256((netlist/name).read_bytes()).hexdigest()}  {name}\n" for name in names))
    (netlist/"source-hashes.txt").write_text(
        f"{hashlib.sha256((netlist/names[0]).read_bytes()).hexdigest()}  {netlist/names[0]}\n")
    output = tmp_path/"board"
    result = subprocess.run(["bash", str(repo/"scripts/build_glrt_board.sh"), "2500000", str(output),
        "--tracking", str(netlist)], capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 2 and "storage mode" in result.stderr and not output.exists()


@pytest.mark.parametrize("tracking,shared,local,accepted", [
    ("1", "1", "1", True), ("1", "0", "1", False), ("1", None, "1", False),
    ("1", "1", "0", False), ("2", "1", "1", False)])
def test_tracking_board_requires_shared_local_component(tmp_path, tracking, shared, local, accepted):
    repo = Path(__file__).resolve().parents[2]
    if shared is not None: (tmp_path/"shared_window.txt").write_text(shared+"\n")
    values = {"RATE_HZ": "2500000", "NATIVE_REFINEMENT": "0", "LEGACY_SCORER": "0",
        "NATIVE_SCHEDULE": "0", "LOCAL_SEARCH": local, "LOCAL_NETLIST": str(tmp_path), "TRACKING": tracking}
    bench = tmp_path/"tracking-selection.tcl"
    bench.write_text("\n".join([
        *(f"set ::env(STARLINK_GLRT_{key}) {{{value}}}" for key, value in values.items()),
        "proc unknown {args} { return {} }",
        'proc ad_ip_parameter {cell key value} { puts "$key=$value" }',
        f"source {{{repo/'hdl/projects/pluto/system_glrt_bd.tcl'}}}",
    ])+"\n")
    result = subprocess.run(["tclsh", str(bench)], capture_output=True, text=True, timeout=10, check=False)
    assert (result.returncode == 0) == accepted, result.stdout+result.stderr
    if accepted:
        assert "CONFIG.ENABLE_TRACKING=1" in result.stdout
        assert "native_direct_2500000_phase4_upper_interleaved.mem" in result.stdout


@pytest.mark.parametrize("rate,native,legacy,schedule,local,netlist,accepted", [
    ("2500000", "0", "0", "0", "1", "/pinned", True),
    ("60000000", "0", "0", "0", "1", "/pinned", False),
    ("2500000", "1", "0", "0", "1", "/pinned", False),
    ("2500000", "0", "1", "0", "1", "/pinned", False),
    ("2500000", "0", "0", "1", "1", "/pinned", False),
    ("2500000", "0", "0", "0", "2", "/pinned", False),
    ("2500000", "0", "0", "0", "1", "", False),
])
def test_local_board_profile_is_exclusive_and_requires_netlist(tmp_path, rate, native, legacy,
                                                              schedule, local, netlist, accepted):
    repo = Path(__file__).resolve().parents[2]
    bench = tmp_path / "local-selection.tcl"
    values = {"RATE_HZ": rate, "NATIVE_REFINEMENT": native, "LEGACY_SCORER": legacy,
              "NATIVE_SCHEDULE": schedule, "LOCAL_SEARCH": local, "LOCAL_NETLIST": netlist}
    bench.write_text("\n".join([
        *(f"set ::env(STARLINK_GLRT_{key}) {{{value}}}" for key, value in values.items()),
        "proc unknown {args} { return {} }",
        'proc ad_ip_parameter {cell key value} { puts "$key=$value" }',
        f"source {{{repo / 'hdl/projects/pluto/system_glrt_bd.tcl'}}}",
    ]) + "\n")
    result = subprocess.run(["tclsh", str(bench)], capture_output=True, text=True, timeout=10, check=False)
    assert (result.returncode == 0) == accepted, result.stdout + result.stderr
    if accepted:
        assert "CONFIG.ENABLE_LOCAL_SEARCH=1" in result.stdout
        assert "CONFIG.ENABLE_LEGACY_SCORER=0" in result.stdout


@pytest.mark.parametrize("rate,native,legacy,accepted", [
    ("60000000", "1", "0", True), ("60000000", "1", "1", True),
    ("2500000", "0", "1", True), ("60000000", "0", "0", False),
    ("25000000", "1", "0", False), ("60000000", "1", "2", False),
])
@pytest.mark.parametrize("schedule", ["0", "1", "2"])
def test_block_design_profile_selection(tmp_path, rate, native, legacy, accepted, schedule):
    # Execute the real selection/validation Tcl. Only Vivado's BD operations
    # are stubbed; the parameter values and rejected combinations are real.
    repo = Path(__file__).resolve().parents[2]
    bench = tmp_path / "selection.tcl"
    bench.write_text("\n".join([
        f"set ::env(STARLINK_GLRT_RATE_HZ) {rate}",
        f"set ::env(STARLINK_GLRT_NATIVE_REFINEMENT) {native}",
        f"set ::env(STARLINK_GLRT_LEGACY_SCORER) {legacy}",
        f"set ::env(STARLINK_GLRT_NATIVE_SCHEDULE) {schedule}",
        "proc unknown {args} { return {} }",
        'proc ad_ip_parameter {cell key value} { puts "$key=$value" }',
        f"source {{{repo / 'hdl/projects/pluto/system_glrt_bd.tcl'}}}",
    ]) + "\n")
    result = subprocess.run(["tclsh", str(bench)], capture_output=True, text=True, timeout=10, check=False)
    accepted = accepted and (schedule == "0" or
        (schedule == "1" and rate == "60000000" and native == "1" and legacy == "0"))
    assert (result.returncode == 0) == accepted, result.stdout + result.stderr
    if accepted:
        assert f"CONFIG.ENABLE_NATIVE_SCHEDULE={schedule}" in result.stdout
        assert f"CONFIG.ENABLE_LEGACY_SCORER={legacy}" in result.stdout
        assert ("CONFIG.ENABLE_NATIVE_REFINEMENT=1" in result.stdout) == (native == "1")


@pytest.mark.parametrize("scheduled", [None, "0", "1"])
def test_postroute_optimization_is_selected_only_for_scheduled_profile(tmp_path, scheduled):
    repo = Path(__file__).resolve().parents[2]
    project = repo / "hdl/projects/pluto/system_project.tcl"
    bench = tmp_path / "project.tcl"
    # Run the real project selection with external ADI/Vivado commands stubbed.
    # The emitted property must identify an existing executable hook, and the
    # hook must run physical optimization without adding timing exceptions.
    lines = [
        "set ::env(STARLINK_GLRT_RATE_HZ) 60000000",
        "set ::env(STARLINK_GLRT_NATIVE_REFINEMENT) 1",
        "unset -nocomplain ::env(STARLINK_GLRT_NATIVE_SCHEDULE)",
        "set ADI_USE_OOC_SYNTHESIS 0",
        f"set ad_hdl_dir {{{repo / 'hdl'}}}",
        "rename source real_source",
        "proc source {path} {}",
        "proc unknown {args} { return {} }",
        'proc set_property {name value args} { puts "$name=$value" }',
    ]
    if scheduled is not None:
        lines.append(f"set ::env(STARLINK_GLRT_NATIVE_SCHEDULE) {scheduled}")
    lines.append(f"real_source {{{project}}}")
    bench.write_text("\n".join(lines) + "\n")
    result = subprocess.run(["tclsh", str(bench)], cwd=project.parent,
        capture_output=True, text=True, timeout=10, check=True)
    key = "STEPS.POST_ROUTE_PHYS_OPT_DESIGN.TCL.POST="
    hooks = [line.removeprefix(key) for line in result.stdout.splitlines() if line.startswith(key)]
    assert len(hooks) == (1 if scheduled == "1" else 0)
    if hooks:
        hook = Path(hooks[0])
        assert hook.is_file()
        bench.write_text("\n".join([
            'proc report_timing_summary {args} {}',
            'proc phys_opt_design {args} { puts "optimize $args" }',
            f"source {{{hook}}}",
        ]) + "\n")
        result = subprocess.run(["tclsh", str(bench)], capture_output=True,
            text=True, timeout=10, check=True)
        assert result.stdout.strip() == "optimize -directive AlternateReplication"

"""Executable runner/IP admission checks; actual XFFT logs own numerical proof."""
import hashlib
from pathlib import Path
import re
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
ACQ = ROOT / "hdl/library/starlink_pss_acquisition"
RUNNER = ACQ / "simulate_iq_to_phase_map_xfft.tcl"
HELPER = ACQ / "create_shared_realtime_xfft_ip.tcl"
VECTORS = ("samples_ci16", "forward_q17", "product_q17", "inverse_q17",
           "forward_exponents", "inverse_exponents", "scores_u8")


def run_tcl(script):
    return subprocess.run(["tclsh"], input=script, text=True, capture_output=True, timeout=10)


def runner_probe(arguments, version="2022.2"):
    script = "proc version {args} {return {%s}}\n" % version
    script += 'proc create_project {args} {error "ADMITTED"}\n'
    script += "set argv [list " + " ".join(f"{{{arg}}}" for arg in arguments) + "]\n"
    script += "set argc [llength $argv]\n"
    script += f"if {{[catch {{source {{{RUNNER}}}}} message]}} {{puts stderr $message; exit 2}}\n"
    return run_tcl(script)


@pytest.mark.parametrize("selectors", [[], ["0"], ["1"], ["1", "0"], ["1", "1"]])
def test_valid_shared_modes_freeze_before_project_creation(tmp_path, selectors):
    output, vectors = tmp_path / "new evidence", tmp_path / "vectors"
    vectors.mkdir()
    for name in VECTORS:
        (vectors / f"{name}.mem").write_text("00\n")
    before = hashlib.sha256((ACQ / "starlink_pss_shared_xfft_service.v").read_bytes()).hexdigest()
    result = runner_probe([output, vectors, *selectors])
    assert result.returncode == 2 and "ADMITTED" in result.stderr
    frozen = output / "frozen_sources"
    assert frozen.exists() == bool(selectors and selectors[0] == "1")
    if frozen.exists():
        assert (frozen / "probe_runner.tcl").read_bytes() == RUNNER.read_bytes()
        names = ["starlink_pss_iq_to_score_shared.v", "starlink_pss_iq_to_phase_map.v",
                 "starlink_pss_shared_xfft_service.v", "verify_realtime_probe_result.tcl"]
        if selectors == ["1", "1"]:
            names += [HELPER.name, "starlink_pss_shared_realtime_xfft_service.v",
                      "starlink_pss_realtime_input_guard.v", "starlink_pss_realtime_result_guard.v"]
        for name in names:
            assert (frozen / name).read_bytes() == (ACQ / name).read_bytes()
        for name in VECTORS:
            assert (frozen / f"{name}.mem").read_bytes() == (vectors / f"{name}.mem").read_bytes()
    assert before == hashlib.sha256((ACQ / "starlink_pss_shared_xfft_service.v").read_bytes()).hexdigest()


@pytest.mark.parametrize("selectors", [["0", "1"], ["1", "2"], ["1", "true"],
                                      ["1", "1.0"], ["2"], ["1", "1", "extra"]])
def test_invalid_modes_do_not_allocate_output(tmp_path, selectors):
    output = tmp_path / "new evidence"
    result = runner_probe([output, tmp_path / "missing", *selectors])
    assert result.returncode == 2 and "ADMITTED" not in result.stderr
    assert not output.exists()


def test_wrong_tool_does_not_allocate_output(tmp_path):
    output = tmp_path / "new evidence"
    result = runner_probe([output, tmp_path / "missing", "1", "1"], "2023.1")
    assert result.returncode == 2 and "requires" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("missing", VECTORS)
def test_all_replay_vectors_required_before_allocation(tmp_path, missing):
    output, vectors = tmp_path / "new evidence", tmp_path / "vectors"
    vectors.mkdir()
    for name in VECTORS:
        if name != missing:
            (vectors / f"{name}.mem").write_text("00\n")
    result = runner_probe([output, vectors, "1", "1"])
    assert result.returncode == 2 and f"missing replay vector {missing}" in result.stderr
    assert not output.exists()


def test_realtime_never_overwrites_existing_evidence(tmp_path):
    output = tmp_path / "evidence"
    output.mkdir()
    retained = output / "retained"
    retained.write_text("keep")
    result = runner_probe([output, tmp_path / "missing", "1", "1"])
    assert "refusing to overwrite" in result.stderr and retained.read_text() == "keep"


def _generic_values():
    original = (ACQ / "simulate_shared_realtime_xfft_service.tcl").read_text()
    values = re.search(r"set required_generics \{(.*?)\}", original, re.S).group(1).split()
    return dict(zip(values[::2], values[1::2], strict=True))


def helper_probe(tmp_path, *, changed=None, forbidden=None, version="2022.2", existing=False):
    values = _generic_values()
    if changed:
        values[changed] = "999"
    module = "starlink_pss_fft512_bfp18_rt_candidate"
    wrapper = tmp_path / "wrapper.vhd"
    wrapper.write_text(f"ENTITY {module} IS\n{forbidden or ''}\nEND {module};\n" +
                       "\n".join(f"{name} => {value}," for name, value in values.items()))
    script = f"source {{{HELPER}}}\nset created 0\n"
    script += "proc version {args} {return {%s}}\n" % version
    script += ("proc get_ips {args} {if {[lindex $args 0] eq {-quiet}} "
               "{return {%s}}; return {%s}}\n") % (module if existing else "", module)
    script += 'proc create_ip {args} {incr ::created}\n'
    script += 'proc set_property {args} {set ::configuration [lindex $args 1]}\n'
    script += 'proc generate_target {args} {}\n'
    script += f"set failed [catch {{pss_create_shared_realtime_xfft_ip {{{wrapper}}}}} message]\n"
    script += 'puts "created=$created failed=$failed result=$message"\n'
    script += 'if {!$failed} {puts $::configuration}\n'
    return run_tcl(script)


def test_distinct_ip_helper_matches_actual_candidate_arithmetic(tmp_path):
    result = helper_probe(tmp_path)
    assert result.returncode == 0 and "created=1 failed=0" in result.stdout
    assert "result=starlink_pss_fft512_bfp18_rt_candidate" in result.stdout
    assert "CONFIG.throttle_scheme realtime" in result.stdout
    assert "CONFIG.target_clock_frequency 200" in result.stdout
    helper_values = re.search(r"set required_generics \{(.*?)\}", HELPER.read_text(), re.S).group(1).split()
    assert dict(zip(helper_values[::2], helper_values[1::2], strict=True)) == _generic_values()


@pytest.mark.parametrize("changed", tuple(_generic_values()))
def test_every_generated_generic_is_checked(tmp_path, changed):
    result = helper_probe(tmp_path, changed=changed)
    assert f"failed=1 result=unexpected generated realtime XFFT generic {changed}" in result.stdout


@pytest.mark.parametrize("forbidden", ["m_axis_data_tready", "m_axis_status_tready",
                                      "event_status_channel_halt", "event_data_out_channel_halt"])
def test_nonrealtime_ports_cannot_bind_realtime_service(tmp_path, forbidden):
    result = helper_probe(tmp_path, forbidden=forbidden)
    assert f"failed=1 result=unexpected realtime XFFT entity port {forbidden}" in result.stdout


@pytest.mark.parametrize("version,existing", [("2023.1", False), ("2022.2", True)])
def test_bad_tool_or_reused_ip_is_rejected_before_creation(tmp_path, version, existing):
    result = helper_probe(tmp_path, version=version, existing=existing)
    assert "created=0 failed=1" in result.stdout


def test_packaging_is_environment_independent_and_old_ip_unchanged():
    package = (ROOT / "hdl/library/axi_starlink_pss_acquisition/axi_starlink_pss_acquisition_ip.tcl").read_text()
    makefile = (ROOT / "hdl/library/axi_starlink_pss_acquisition/Makefile").read_text()
    assert "::env(STARLINK_PSS_REALTIME_XFFT)" not in package + HELPER.read_text()
    assert "CONFIG.throttle_scheme {nonrealtime}" in package
    assert "pss_create_shared_realtime_xfft_ip" in package
    for name in ("create_shared_realtime_xfft_ip.tcl", "starlink_pss_shared_realtime_xfft_service.v",
                 "starlink_pss_realtime_input_guard.v", "starlink_pss_realtime_result_guard.v"):
        assert name in package and name in makefile
    assert "USE_REALTIME_XFFT -of_objects" in package


def test_phase_terminal_verifies_numerics_and_fault_receipt_without_claiming_capacity():
    source = RUNNER.read_text()
    bench = (ACQ / "tb/tb_starlink_pss_iq_to_phase_map_xfft.sv").read_text()
    assert "require_realtime_probe_pass" in source
    assert "IQ_TO_PHASE_MAP_XFFT_PASS 1" in source
    assert "REALTIME_PHASE_MAP_FAULT_PASS" in source and "REALTIME_PHASE_MAP_PASS" in source
    assert "source_hashes=" in source and "CAPACITY_AND_PHYSICAL_UNQUALIFIED" in source
    assert "set_property generic" in source and "USE_REALTIME_XFFT=$use_realtime_xfft" in source
    assert "realtime_transform.transform_service.event_last_missing" in bench
    assert "nonrealtime_transform.transform_service.adapter.protocol_fault" in bench

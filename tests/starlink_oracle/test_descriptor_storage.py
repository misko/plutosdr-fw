"""Descriptor FIFO public equivalence; simulated clocks do not prove CDC timing."""

import hashlib
import re
import subprocess
from pathlib import Path

import pytest

HDL = Path(__file__).resolve().parents[2] / "hdl"
RAW = HDL / "library/starlink_pss_raw_correlator"
BASE = "c66bb2197dd55b63d23797463570d7c2696c9fa6"
BASE_SHA = "a07f1bf38da80b3a0f125351af439af5b58aae1ab783597ba15086d40f3cbc0d"
TOP = "tb_starlink_pss_descriptor_storage"


def run_probe(tmp_path, write_half, read_half, release_first, mutation=None):
    source = subprocess.run([
        "git", "-C", str(HDL), "show",
        f"{BASE}:library/starlink_pss_raw_correlator/starlink_pss_async_fifo.v",
    ], capture_output=True, check=True, timeout=10).stdout
    assert hashlib.sha256(source).hexdigest() == BASE_SHA
    golden = tmp_path / "golden.v"
    golden.write_text(source.decode().replace(
        "module starlink_pss_async_fifo #(", "module starlink_pss_async_fifo_golden #(", 1))
    candidate_text = (RAW / "starlink_pss_async_fifo.v").read_text()
    mutations = {
        "address": ("payload_memory[read_binary[ADDRESS_WIDTH-1:0]]",
                    "payload_memory[read_binary[ADDRESS_WIDTH-1:0] ^ 1'b1]"),
        "hold": ("if (read_handshake) begin", "if (read_handshake) begin read_data <= 0;"),
        "early": ("(read_gray != write_gray_read_sync_2)",
                  "(read_gray != write_gray_read_sync_1)"),
    }
    if mutation:
        before, after = mutations[mutation]
        assert candidate_text.count(before) == 1
        candidate_text = candidate_text.replace(before, after, 1)
    candidate = tmp_path / "candidate.v"
    candidate.write_text(candidate_text)
    executable = tmp_path / "descriptor.vvp"
    result = subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", TOP,
        f"-P{TOP}.WRITE_HALF={write_half}", f"-P{TOP}.READ_HALF={read_half}",
        f"-P{TOP}.RELEASE_READ_FIRST={release_first}", "-o", str(executable),
        str(candidate), str(golden), str(RAW / "tb" / f"{TOP}.sv"),
    ], capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    return subprocess.run(["vvp", str(executable)], cwd=tmp_path,
                          capture_output=True, text=True, timeout=30, check=False)


@pytest.mark.parametrize("write_half,read_half", [(7, 5), (5, 7), (3, 5)])
@pytest.mark.parametrize("release_first", [0, 1])
def test_descriptor_public_equivalence_and_queue_oracle(tmp_path, write_half, read_half, release_first):
    result = run_probe(tmp_path, write_half, read_half, release_first)
    output = result.stdout + result.stderr
    assert result.returncode == 0 and "FAIL" not in output and "ERROR" not in output, output
    assert output.count("DESCRIPTOR_STORAGE_PASS") == 1, output
    assert "writes=195 reads=192 reset_discard=3 consumed_hold=12" in output


@pytest.mark.parametrize("mutation", ["address", "hold", "early"])
def test_descriptor_corruptions_have_reachable_witnesses(tmp_path, mutation):
    result = run_probe(tmp_path, 7, 5, 0, mutation)
    output = result.stdout + result.stderr
    assert result.returncode != 0 and "DESCRIPTOR_EQUIVALENCE_" in output, output
    assert "DESCRIPTOR_STORAGE_PASS" not in output


def test_bridge_only_selects_storage_without_behavioral_changes():
    before = subprocess.run([
        "git", "-C", str(HDL), "show",
        f"{BASE}:library/starlink_pss_raw_correlator/starlink_pss_capture_bridge.v",
    ], capture_output=True, check=True, timeout=10).stdout
    assert hashlib.sha256(before).hexdigest() == (
        "3053208397ca9e6a7239d731754d929adfc0d872ce8d2479e9d101e1244aa1cc")
    candidate = (RAW / "starlink_pss_capture_bridge.v").read_text()

    def tokens(source):
        return re.sub(r"\s+", "", re.sub(r"//[^\n]*", "", source))

    candidate = tokens(candidate)
    selection = '.ADDRESS_WIDTH(2),.RAM_STYLE("block")'
    assert candidate.count(selection) == 1
    assert candidate.replace(selection, ".ADDRESS_WIDTH(2)", 1) == tokens(before.decode())


@pytest.mark.parametrize("memory,destination,expected", [
    ("payload_ram", "payload_d", "CUT"),
    ("payload_bram", "", "NONE"),
    ("", "", "NONE"),
    ("", "payload_d", "ERROR"),
])
def test_descriptor_constraint_never_broadens_an_empty_endpoint(memory, destination, expected):
    xdc = (HDL / "library/axi_starlink_pss_tracker/axi_starlink_pss_tracker_constr.xdc").read_text()
    section = xdc[xdc.index("# Legacy distributed capture-descriptor"):
                  xdc.index("# AXI-reset assertion into the reset synchronizers")]
    script = f"""
proc get_cells {{args}} {{
  if {{[string match *payload_memory_reg* [lindex $args end]]}} {{ return {{{memory}}} }}
  return {{{destination}}}
}}
proc get_pins {{args}} {{ return {{{destination}}} }}
proc set_false_path {{args}} {{ puts "CUT:$args" }}
if {{[catch {{
{section}
}} message]}} {{ puts stderr $message; exit 2 }}
"""
    result = subprocess.run(["tclsh"], input=script, capture_output=True, text=True,
                            timeout=10, check=False)
    if expected == "ERROR":
        assert result.returncode == 2 and "without their source memory" in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == (
            "CUT:-quiet -from payload_ram -to payload_d" if expected == "CUT" else "")

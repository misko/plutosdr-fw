"""Live extracted preflight RTL vs frozen expressions; explicitly no FFT model."""
import re
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.input_identity_contract import tokens
from tests.starlink_oracle.preflight_identity_contract import (
    restore_held_preflight_wrapper,
)

HDL = Path(__file__).resolve().parents[2] / "hdl"
ACQ = HDL / "library/starlink_pss_acquisition"
BASE = "447183b84250595be5324556f65145d130aca453"
NAME = "starlink_pss_fft_bank_owned_slice.v"
PORTS = '''input wire [3:0] state,
  input wire held_phase, next_inverse, fast_running, source_valid, product_bank_valid,
  input wire [35:0] source_data, product_bank_data,
  input wire [8:0] source_position, product_bank_position,
  input wire source_last, product_bank_last, source_consume_generation, product_consume_generation,
  input wire [69:0] source_metadata, product_bank_metadata, engine_metadata, expected_product_metadata,
  input wire held_lease, destination_reserved,
  input wire [5:0] preparation_age'''


def frozen():
    return subprocess.run(["git", "-C", str(HDL), "show",
        f"{BASE}:library/starlink_pss_acquisition/{NAME}"], capture_output=True, text=True,
        timeout=10, check=True).stdout


def test_entire_preflight_delta_preserves_all_other_rtl_and_default():
    assert restore_held_preflight_wrapper((ACQ / NAME).read_text()) == frozen()


def test_actual_preflight_shadow_is_independent_frozen_predicate():
    baseline = frozen()
    expected = baseline[baseline.index("  wire descriptor_header_valid"):
                        baseline.index("  wire job_valid")]
    names = {field: f"dut.{field}" for field in (
        "engine_metadata", "held_phase", "expected_product_metadata", "held_lease",
        "destination_reserved", "fast_running", "preparation_age")}
    names.update({f"selected_{field}": f"old_input_{field}" for field in (
        "valid", "position", "last", "metadata")})
    names.update({"selected_lease": "old_preflight_lease",
        "descriptor_header_valid": "old_descriptor_header_valid",
        "preparation_valid": "old_preparation_valid",
        "preflight_events_now": "old_preflight_events_now",
        "preparation_fault_now": "old_preflight_fault_now",
        "preparing": "(dut.state == dut.VERIFY_LEASE || dut.state == dut.ARM_JOB)"})
    expected = re.sub(r"\b[A-Za-z_][A-Za-z_0-9]*\b", lambda match: names.get(match[0], match[0]), expected)
    bench = (ACQ / "tb/tb_starlink_pss_fft_bank_owned_slice.sv").read_text()
    assert tokens(expected) in tokens(bench)
    assert ".external_fault_now(dut.external_fault_now || old_preflight_fault_now)" in bench
    assert "expected_epoch_preflight_reasons | old_preflight_events_now" in bench
    assert "force dut.selected_" not in bench


def extract(source, module_name):
    begin = source.index("  wire selected_phase =")
    end = source.index("  wire job_valid =", begin)
    states = re.search(r"localparam \[3:0\] RESET0=.*?;", source, re.DOTALL).group()
    return (f"module {module_name} #(parameter integer REGISTERED_SCHEDULING = 1) ({PORTS});\n"
            f"{states}\n{source[begin:end]}endmodule\n")


@pytest.mark.parametrize("mode,mutation", [(0, -1), (1, -1), (1, 0), (1, 1)])
def test_full_preflight_bits_headers_causes_and_omission_mutants(tmp_path, mode, mutation):
    source = (ACQ / NAME).read_text()
    if mutation >= 0:
        anchor = "assign leaf_equal[leaf] = lhs[3*leaf +: BITS] == rhs[3*leaf +: BITS];"
        assert source.count(anchor) == 1
        source = source.replace(anchor,
            f"assign leaf_equal[leaf] = comparison == {mutation} && leaf == 23 ? 1'b1 : "
            "lhs[3*leaf +: BITS] == rhs[3*leaf +: BITS];", 1)
    candidate = tmp_path / "live_extracted_predicate.v"
    reference = tmp_path / "frozen_447183b8_predicate.v"
    candidate.write_text(extract(source, "preflight_candidate"))
    reference.write_text(extract(frozen(), "preflight_reference"))
    top = "tb_starlink_pss_preflight_identity"
    executable = tmp_path / "predicate.vvp"
    result = subprocess.run(["iverilog", "-g2012", "-Wall", "-s", top,
        f"-P{top}.REGISTERED_MODE={mode}", "-o", str(executable), str(candidate), str(reference),
        str(ACQ / "tb" / f"{top}.sv")], capture_output=True, text=True, timeout=30, check=False)
    (tmp_path / "compile.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run(["vvp", str(executable)], capture_output=True, text=True,
                            timeout=30, check=False)
    log = result.stdout + result.stderr
    (tmp_path / "simulate.log").write_text(log)
    if mutation >= 0:
        witness = (f"PREFLIGHT_PREDICATE_MISMATCH family={mutation} phase={mutation} "
                   "bit=69 boundary=0 ready=0")
        assert result.returncode != 0 and witness in log, log
        assert "PREFLIGHT_PREDICATE_PASS" not in log
    else:
        assert result.returncode == 0, log
        assert (f"PREFLIGHT_PREDICATE_PASS registered={mode} bit_rows=2520 "
                "cause_rows=396 idle_rows=36") in log
        assert "both70bit_comparisons=1 phase_low5_header=1 extracted_live_rtl_no_fft=1" in log

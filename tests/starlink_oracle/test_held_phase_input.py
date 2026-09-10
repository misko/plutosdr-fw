"""The held-phase experiment changes only the active input tuple wiring."""
import subprocess
from pathlib import Path

from tests.starlink_oracle.preflight_identity_contract import (
    restore_held_preflight_wrapper,
)

HDL = Path(__file__).resolve().parents[2] / "hdl"
ACQ = HDL / "library/starlink_pss_acquisition"
BASELINE = "691966aed6d6ed52c7589a38b68d26cffee65dd4"


def test_held_phase_is_exact_tuple_only_delta():
    name = "starlink_pss_fft_bank_owned_slice.v"
    baseline = subprocess.run([
        "git", "-C", str(HDL), "show", f"{BASELINE}:library/starlink_pss_acquisition/{name}",
    ], text=True, capture_output=True, check=True, timeout=10).stdout
    candidate = restore_held_preflight_wrapper((ACQ / name).read_text())
    # The later comparator checkpoint is tested separately against d99c251e;
    # erase only its exact registered-only opt-in before this whole-body check.
    opt_in = ",\n    .BALANCED_IDENTITY_EQ(REGISTERED_SCHEDULING)"
    assert candidate.count(opt_in) == 1
    candidate = candidate.replace(opt_in, "", 1)
    start = candidate.index("  // Discovery/preflight may select by scheduler state.")
    end = candidate.index("  wire selected_lease", start)
    added = candidate[start:end]
    assert "wire guard_phase = REGISTERED_SCHEDULING ? held_phase : next_inverse;" in added
    for width, field in [("", "valid"), ("[35:0] ", "data"), ("[8:0] ", "position"),
                         ("", "last"), ("[69:0] ", "metadata")]:
        assert (f"wire {width}guard_{field} = guard_phase ? product_bank_{field} : "
                f"source_{field};") in added
    candidate = candidate[:start] + candidate[end:]
    for field in ("valid", "data", "position", "last", "metadata"):
        old, new = f".input_{field}(guard_{field})", f".input_{field}(selected_{field})"
        assert candidate.count(old) == 1
        candidate = candidate.replace(old, new)
    assert candidate == baseline


def test_old_mux_witness_is_frozen_baseline_expression():
    baseline = subprocess.run([
        "git", "-C", str(HDL), "show",
        f"{BASELINE}:library/starlink_pss_acquisition/starlink_pss_fft_bank_owned_slice.v",
    ], text=True, capture_output=True, check=True, timeout=10).stdout
    start = baseline.index("  wire selected_phase =")
    end = baseline.index(";", start) + 1
    expression = baseline[start:end].replace("selected_phase", "old_input_phase")
    for signal in ("state", "WAIT_BANK", "RESET0", "RESET1", "held_phase", "next_inverse"):
        expression = expression.replace(signal, f"dut.{signal}")
    assert expression in (ACQ / "tb/tb_starlink_pss_fft_bank_owned_slice.sv").read_text()

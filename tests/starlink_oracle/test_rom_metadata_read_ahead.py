"""All four word/metadata options against an independent frozen whole ROM."""

import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.rom_metadata_contract import BASE, EDITS, restore_metadata
from tests.starlink_oracle.test_rom_read_ahead import (
    ACQ,
    ROOT,
    candidate,
    original,
    run,
)

BENCH_PATH = "library/starlink_pss_acquisition/tb/tb_starlink_pss_rom_read_ahead.sv"
RTL_PATH = "library/starlink_pss_acquisition/starlink_pss_kernel_rom_read_ahead.v"


def frozen(path):
    return subprocess.check_output(
        ["git", "-C", str(ROOT / "hdl"), "show", BASE + ":" + path], text=True
    )


def replace_one(text, before, after):
    assert text.count(before) == 1
    return text.replace(before, after, 1)


def expanded_bench(extra=None):
    bench = frozen(BENCH_PATH)
    bench = replace_one(bench, ".PRIVATE_ROM_READ_AHEAD(1)) candidate",
                        ".PRIVATE_ROM_READ_AHEAD(1),"
                        ".PRIVATE_BLOCK_METADATA_READ_AHEAD(1)) candidate")
    bench = replace_one(bench, "`undef PORTS", """  starlink_pss_kernel_rom_read_ahead #(.ROM_FILE("kernel.mem"),.DATA_WIDTH(WIDTH),
    .BALANCED_BLOCK_IDENTITY_EQ(BALANCED),.PRIVATE_NEXT_START_SCRATCH(SCRATCH),
    .PRIVATE_ROM_READ_AHEAD(1),.PRIVATE_BLOCK_METADATA_READ_AHEAD(0)) word_only (`PORTS);
  starlink_pss_kernel_rom_read_ahead #(.ROM_FILE("kernel.mem"),.DATA_WIDTH(WIDTH),
    .BALANCED_BLOCK_IDENTITY_EQ(BALANCED),.PRIVATE_NEXT_START_SCRATCH(SCRATCH),
    .PRIVATE_ROM_READ_AHEAD(0),.PRIVATE_BLOCK_METADATA_READ_AHEAD(1)) metadata_only (`PORTS);
`undef PORTS""")
    bench = replace_one(bench, "  integer checks=0", """  wire [1023:0] word_view=`VIEW(word_only), metadata_view=`VIEW(metadata_only);
  integer checks=0""")
    bench = replace_one(bench, "old_view !== new_view)",
                        "old_view !== new_view || old_view !== word_view || old_view !== metadata_view)")
    bench = replace_one(bench, "  integer n, bit_index;", (
        (ACQ / "tb/starlink_pss_rom_metadata_cases.svh").read_text() if extra is None else extra
    ) + "\n  integer n, bit_index;")
    bench = replace_one(bench, "    // Deterministic unconstrained input stream",
                        "    metadata_extra_cases();\n"
                        "    // Deterministic unconstrained input stream")
    return bench


def test_whole_source_inverse_default_and_original_bench_unchanged():
    old = frozen(RTL_PATH)
    for before, after in EDITS:
        old = replace_one(old, before, after)
    assert old == candidate()
    assert restore_metadata(candidate()) == frozen(RTL_PATH)
    assert (ACQ / "starlink_pss_kernel_rom.v").read_text() == original()
    assert (ACQ / "tb/tb_starlink_pss_rom_read_ahead.sv").read_text() == frozen(BENCH_PATH)
    old_test = subprocess.check_output(
        ["git", "-C", str(ROOT), "show", ("80fbb1434eaa39dc37c560389b0b356e411afde4:"
         "tests/starlink_oracle/test_rom_read_ahead.py")], text=True
    )
    current = Path(__file__).with_name("test_rom_read_ahead.py").read_text()
    current = replace_one(current, "\nfrom tests.starlink_oracle.rom_metadata_contract import restore_metadata\n", "")
    current = replace_one(current, "assert old == restore_metadata(candidate())", "assert old == candidate()")
    assert current == old_test


@pytest.mark.parametrize("width", [2, 18, 24])
@pytest.mark.parametrize("balanced", [0, 1])
@pytest.mark.parametrize("scratch", [0, 1])
def test_all_four_options_full_frozen_state_and_old_stimulus(tmp_path, width, balanced, scratch):
    code, log = run(tmp_path, width, balanced, scratch, bench=expanded_bench())
    assert code == 0 and log.count("ROM_READ_AHEAD_OFFLINE_PASS") == 1, log
    assert log.count("ROM_READ_AHEAD_ACTIVE_BOUNDARIES_PASS") == 1
    assert "occupied_unknown_ready=2 flush_selector_zero=1 flush_selector_one=1" in log
    assert log.count("ROM_METADATA_EXTRA_PASS") == 1
    assert "bit_faults=69 unknown_first=2 invalid_bubbles=3 flush_zero=1 flush_one=1 wrap_blocks=2 malformed_first=2" in log
    assert log.count("ROM_METADATA_FOUR_STATE_PASS unknown_framing=2") == 1


@pytest.mark.parametrize("before,after", [
    ("if (metadata_selected)\n          retained_metadata", "if (1'b0)\n          retained_metadata"),
    ("metadata_selected ? speculative_metadata : retained_metadata", "speculative_metadata"),
    ("metadata_selected ? speculative_metadata : retained_metadata", "retained_metadata"),
    ("if (input_ready && at_block_start)", "if (!input_ready && at_block_start)"),
    ("speculative_metadata <= {input_block_start_index, input_block_exponent};",
     "speculative_metadata <= {input_block_start_index ^ 64'h8000000000000000, input_block_exponent};"),
    ("speculative_metadata <= {input_block_start_index, input_block_exponent};",
     "speculative_metadata <= {input_block_start_index, input_block_exponent ^ 5'h10};"),
    ("retained_metadata <= 0;", "retained_metadata <= 1;"),
    ("else if (at_block_start)\n            metadata_selected <= 1;", "else if (!at_block_start)\n            metadata_selected <= 1;"),
    ("if (protocol_error_now)\n            metadata_selected <= 0;\n          else if (at_block_start)",
     "if (1'b0)\n            metadata_selected <= 0;\n          else if (at_block_start)"),
    ("if (protocol_error_now)\n            metadata_selected <= 0;\n          else if (at_block_start)",
     "if (protocol_error_now !== 1'b0)\n            metadata_selected <= 0;\n          else if (at_block_start)"),
])
def test_metadata_semantic_mutants_and_literal_inverse_reject(tmp_path, before, after):
    changed = replace_one(candidate(), before, after)
    with pytest.raises(AssertionError):
        restore_metadata(changed)
    code, log = run(tmp_path, mutated=changed, bench=expanded_bench())
    assert code != 0 and ("MISMATCH" in log or "metadata" in log), log
    assert "ROM_READ_AHEAD_OFFLINE_PASS" not in log


@pytest.mark.parametrize("value", ["-1", "2", "32'bx", "32'bz"])
def test_metadata_invalid_parameter_rejects_time_zero(tmp_path, value):
    bench = frozen(BENCH_PATH)
    bench = replace_one(bench, ".PRIVATE_ROM_READ_AHEAD(1)) candidate",
                        f".PRIVATE_ROM_READ_AHEAD(1),.PRIVATE_BLOCK_METADATA_READ_AHEAD({value})) candidate")
    code, log = run(tmp_path, bench=bench)
    assert code != 0 and "PRIVATE_BLOCK_METADATA_READ_AHEAD must be zero or one" in log, log
    assert "Time: 0 " in log


def test_alternative_data_enable_retains_semantics_but_not_selected_cut(tmp_path):
    # This keeps the wide input_valid dependency. Treat it as an equivalent
    # positive control, not a semantic negative or evidence of the desired cut.
    changed = replace_one(candidate(), "if (input_ready && at_block_start)",
                          "if (input_accept && at_block_start)")
    bench = replace_one(frozen(BENCH_PATH), ".PRIVATE_ROM_READ_AHEAD(1)) candidate",
                        ".PRIVATE_ROM_READ_AHEAD(1),.PRIVATE_BLOCK_METADATA_READ_AHEAD(1)) candidate")
    code, log = run(tmp_path, mutated=changed, bench=bench)
    assert code == 0 and log.count("ROM_READ_AHEAD_OFFLINE_PASS") == 1, log


def test_broader_selector_public_equivalence_is_not_private_enable_compliance(tmp_path):
    # V2 retained an actual public-equivalence PASS for this proposed negative.
    # Re-exposing the still-held first tuple on interior accepts need not change
    # any old/public state, but violates the selected exact private write event.
    changed = replace_one(candidate(), "else if (at_block_start)\n            metadata_selected <= 1;",
                          "else\n            metadata_selected <= 1;")
    with pytest.raises(AssertionError):
        restore_metadata(changed)
    strict_dir = tmp_path / "private-contract"
    strict_dir.mkdir()
    code, log = run(strict_dir, mutated=changed, bench=expanded_bench())
    assert code != 0 and "metadata private selector must follow exact first-beat event" in log, log
    private_check = (
        "      if(candidate.private_block_metadata_read_ahead.metadata_selected!==(bin_number==0))\n"
        '        $fatal(1,"metadata private selector must follow exact first-beat event");\n'
    )
    # Remove ONLY this new private selector assertion, never old/current views.
    bench = replace_one(expanded_bench(), private_check, "")
    public_dir = tmp_path / "public-equivalence"
    public_dir.mkdir()
    code, log = run(public_dir, mutated=changed, bench=bench)
    assert code == 0 and log.count("ROM_READ_AHEAD_OFFLINE_PASS") == 1, log
    assert log.count("ROM_METADATA_EXTRA_PASS") == 1, log

"""Data-only enables and full ROM identities against immutable RTL and arithmetic."""
import itertools
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.input_identity_contract import tokens
from tests.starlink_oracle.payload_bubble_contract import (
    restore_payload_module,
    restore_payload_wrapper,
)

HDL = Path(__file__).resolve().parents[2] / "hdl"
ACQ = HDL / "library/starlink_pss_acquisition"
TB = ACQ / "tb"
BASE = "7ee87258be4cde11a6092d22ad76a085cfaecc76"
KINDS = ("forward_kernel_join", "kernel_rom", "spectrum_product")


def frozen(name):
    return subprocess.run(["git", "-C", str(HDL), "show",
        f"{BASE}:library/starlink_pss_acquisition/{name}"], capture_output=True, text=True,
        check=True, timeout=10).stdout


def test_exact_four_module_inverse_and_three_unmodified_frozen_mirrors():
    for kind in KINDS:
        name = f"starlink_pss_{kind}"
        baseline = frozen(f"{name}.v")
        mirror = (TB / f"{name}_7ee87258_golden.v").read_text()
        for module in KINDS:
            mirror = mirror.replace(f"starlink_pss_{module}_7ee87258_golden", f"starlink_pss_{module}")
        assert mirror == baseline
        assert restore_payload_module((ACQ / f"{name}.v").read_text(), kind) == tokens(baseline)
    name = "starlink_pss_fft_bank_owned_slice.v"
    assert restore_payload_wrapper((ACQ / name).read_text()) == frozen(name)


def test_actual_stimulus_and_all_previous_fences_remain_literal():
    name = "tb/tb_starlink_pss_fft_bank_owned_slice.sv"
    candidate = (ACQ / name).read_text()
    for addition in ("SHADOW", "RECEIPT"):
        pattern = rf"^  *// BEGIN PAYLOAD_BUBBLE_{addition}.*?^  *// END PAYLOAD_BUBBLE_{addition}\n"
        candidate, count = re.subn(pattern, "", candidate, flags=re.MULTILINE | re.DOTALL)
        assert count == 1
    assert candidate == frozen(name)
    mirror = (TB / "starlink_pss_payload_bubble_shadow.sv").read_text()
    assert "PRIVATE_PAYLOAD_BUBBLES" not in mirror and "BALANCED_BLOCK_IDENTITY_EQ" not in mirror
    assert "old_product" in mirror and "old_join" in mirror


def run(tmp_path, top, parameters, mutation=None):
    sources = []
    for kind in KINDS:
        source = (ACQ / f"starlink_pss_{kind}.v").read_text()
        if mutation and mutation[0] == kind:
            _, old, new = mutation
            assert source.count(old) == 1
            source = source.replace(old, new, 1)
        candidate = tmp_path / f"starlink_pss_{kind}.v"
        candidate.write_text(source)
        sources.extend([candidate, TB / f"starlink_pss_{kind}_7ee87258_golden.v"])
    sources.append(TB / "starlink_pss_payload_bubble_shadow.sv")
    sources.append(TB / ("tb_starlink_pss_rom_block_identity.sv" if "rom_block" in top else
                         "tb_starlink_pss_payload_bubbles.sv"))
    shutil.copyfile(ACQ / "evidence/held-preflight-v1/actual/frozen_sources/upper_edge_pss_kernel_q17.mem",
                    tmp_path / "upper_edge_pss_kernel_q17.mem")
    executable = tmp_path / "simulation.vvp"
    result = subprocess.run(["iverilog", "-g2012", "-Wall", "-s", top,
        *[f"-P{top}.{item}" for item in parameters], "-o", str(executable), *map(str, sources)],
        cwd=tmp_path, text=True, capture_output=True, timeout=30, check=False)
    (tmp_path / "compile.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run(["vvp", str(executable)], cwd=tmp_path, text=True,
                            capture_output=True, timeout=45, check=False)
    log = result.stdout + result.stderr
    (tmp_path / "simulate.log").write_text(log)
    return result.returncode, log


@pytest.mark.parametrize("join,product,balanced", list(itertools.product((0, 1), repeat=3)))
def test_all_eight_independent_options_frozen_chain_occupied_stalls_reset_wrap(tmp_path, join, product, balanced):
    rc, log = run(tmp_path, "tb_starlink_pss_payload_bubbles",
                  [f"JOIN_BUBBLES={join}", f"PRODUCT_BUBBLES={product}", f"BALANCED_ROM={balanced}"])
    assert rc == 0, log
    assert f"PAYLOAD_BUBBLES_PASS join={join} product={product} balanced={balanced}" in log
    assert "full_stall_reset_flush_wrap=1" in log


@pytest.mark.parametrize("mode", [0, 1])
def test_product_every_output_bit_and_independent_signed_ties_clipping_unknown_bubbles(tmp_path, mode):
    rc, log = run(tmp_path, "tb_starlink_pss_product_bubbles", [f"BUBBLES={mode}"])
    assert rc == 0 and f"PRODUCT_BUBBLES_PASS mode={mode}" in log, log
    assert "independent_round_even_and_boundary=1" in log


@pytest.mark.parametrize("mode,omitted", [(0, -1), (1, -1), (1, 0), (1, 1)])
def test_both_full64bit_comparisons_history_and_bit63_omission_witnesses(tmp_path, mode, omitted):
    mutation = None
    if omitted >= 0:
        old = "assign leaf_equal[leaf] = input_block_start_index[3*leaf +: BITS] == rhs[3*leaf +: BITS];"
        mutation = ("kernel_rom", old,
            (f"assign leaf_equal[leaf] = comparison == {omitted} && leaf == 21 ? 1'b1 : "
             "input_block_start_index[3*leaf +: BITS] == rhs[3*leaf +: BITS];"))
    rc, log = run(tmp_path, "tb_starlink_pss_rom_block_identity", [f"BALANCED_MODE={mode}"], mutation)
    if omitted >= 0:
        assert rc != 0 and f"ROM_IDENTITY_MISMATCH comparison={omitted} bit=63 stall=0" in log, log
        assert "ROM_IDENTITY_PASS" not in log
    else:
        assert rc == 0 and f"ROM_IDENTITY_PASS balanced={mode} bit_rows=256" in log, log


@pytest.mark.parametrize("mutation", ["join_overwrite", "product_overwrite", "invalid_token"])
def test_illegal_occupied_overwrites_and_invalid_numeric_token_rejected(tmp_path, mutation):
    if mutation == "join_overwrite":
        change = ("forward_kernel_join", "PRIVATE_PAYLOAD_BUBBLES ? input_ready : input_accept",
                  "PRIVATE_PAYLOAD_BUBBLES ? 1'b1 : input_accept")
        top, parameters, expected = "tb_starlink_pss_payload_bubbles", ["JOIN_BUBBLES=1"], "PAYLOAD_JOIN_OCCUPIED_MISMATCH"
    elif mutation == "product_overwrite":
        anchor = "      if (product_stage_ready) begin"
        change = ("spectrum_product", anchor, '''      if (PRIVATE_PAYLOAD_BUBBLES) begin
        product_ii <= input_i * kernel_i; product_qq <= input_q * kernel_q;
        product_iq <= input_i * kernel_q; product_qi <= input_q * kernel_i;
      end
''' + anchor)
        top, parameters, expected = "tb_starlink_pss_product_bubbles", ["BUBBLES=1"], "PRODUCT_OCCUPIED_MISMATCH"
    else:
        change = ("spectrum_product", "product_valid <= input_valid;",
                  "product_valid <= PRIVATE_PAYLOAD_BUBBLES || input_valid;")
        top, parameters, expected = "tb_starlink_pss_product_bubbles", ["BUBBLES=1"], "PRODUCT_INVALID_TOKEN_MISMATCH"
    rc, log = run(tmp_path, top, parameters, change)
    assert rc != 0 and expected in log, log
    assert "BUBBLES_PASS" not in log

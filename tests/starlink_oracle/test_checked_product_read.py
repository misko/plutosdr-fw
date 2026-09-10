"""Offline checked-read queue; no actual vendor FFT or physical execution."""
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ACQ = ROOT / "hdl/library/starlink_pss_acquisition"
RTL = ACQ / "starlink_pss_checked_product_read.v"
TB = ACQ / "tb/tb_starlink_pss_checked_product_read.sv"


def clean_env():
    return {k: v for k, v in os.environ.items()
            if k not in {"PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH"}}


def compile_case(path, mutation=None, extra=None):
    path.mkdir()
    for source in (RTL, TB, Path(__file__)):
        shutil.copyfile(source, path / source.name)
    if mutation:
        source = (path / RTL.name).read_text()
        assert source.count(mutation[0]) == 1
        (path / RTL.name).write_text(source.replace(*mutation))
    if extra:
        (path / "extra.sv").write_text(extra)
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in path.iterdir() if p.is_file()}
    (path / "sources.json").write_text(json.dumps(hashes, indent=2) + "\n")
    command = ["iverilog", "-g2012", "-Wall", "-s",
               "extra" if extra else "tb_starlink_pss_checked_product_read",
               "-o", "sim.vvp", RTL.name, "extra.sv" if extra else TB.name]
    result = subprocess.run(command, cwd=path, env=clean_env(), text=True,
                            capture_output=True, timeout=30, check=False)
    (path / "compile.log").write_text(result.stdout + result.stderr)
    (path / "compile.json").write_text(json.dumps({"command": command, "exit": result.returncode}))
    assert result.returncode == 0 and not re.search(r"(?im)^.*error:", result.stderr), result.stderr
    return path


@pytest.fixture(scope="module")
def compiled(tmp_path_factory):
    return compile_case(tmp_path_factory.mktemp("read_queue") / "original")


def execute(path, kind=0, bit=0, target=37):
    command = ["vvp", "sim.vvp", f"+CASE={kind}", f"+BIT={bit}", f"+TARGET={target}"]
    result = subprocess.run(command, cwd=path, env=clean_env(), text=True,
                            capture_output=True, timeout=30, check=False)
    log = result.stdout + result.stderr
    key = f"case-{kind}-bit-{bit}-target-{target}"
    (path / f"{key}.log").write_text(log)
    (path / f"{key}.json").write_text(json.dumps({"command": command, "exit": result.returncode}))
    return result.returncode, log


def test_three_slot_512_contiguous_eight_leases(compiled):
    code, log = execute(compiled)
    assert code == 0 and log.count("CHECKED_READ_PASS") == 1, log
    assert log.count("sent=512 received=512 span=511 holes=0") == 8
    assert "jobs=8" in log


def test_queue_drained_then_bad_token_never_reuses_prior_good(compiled):
    code, log = execute(compiled, 8, 74)
    assert code == 0 and "CHECKED_READ_NEGATIVE_PASS" in log, log


@pytest.mark.parametrize("bit", range(75))
@pytest.mark.parametrize("target", [0, 37, 511])
def test_every_raw_metadata_bit_before_core_consumption(compiled, bit, target):
    code, log = execute(compiled, 1, bit, target)
    assert code == 0 and log.count("CHECKED_READ_NEGATIVE_PASS") == 1, log
    row = re.search(r"sent=(\d+) received=(\d+) reasons=([0-9a-f]+)", log)
    assert row and int(row[2]) <= target and int(row[3], 16) & 4


@pytest.mark.parametrize("bit", range(75))
def test_every_stalled_offered_metadata_bit_is_observed(compiled, bit):
    code, log = execute(compiled, 3, bit)
    assert code == 0 and "CHECKED_READ_NEGATIVE_PASS" in log, log


@pytest.mark.parametrize("kind,bit", [(2, b) for b in range(4)] +
                         [(5, b) for b in range(8)] + [(7, 0)])
def test_framing_lease_unknown_current_cause_and_stale_verdict(compiled, kind, bit):
    code, log = execute(compiled, kind, bit)
    assert code == 0 and "CHECKED_READ_NEGATIVE_PASS" in log, log


@pytest.mark.parametrize("kind", [4, 6])
def test_stalls_and_final_prefetch_not_release(compiled, kind):
    code, log = execute(compiled, kind)
    assert code == 0 and "CHECKED_READ_PASS" in log, log


@pytest.mark.parametrize("mutation,kind,marker", [
    (("occupied[head] && good[head]", "occupied[head]"), 8, "UNCHECKED_TOKEN_ESCAPED"),
    (("(count<3 || core_take)", "(count<4 || core_take)"), 3, "QUEUE_CREDIT_OVERFLOW"),
    (("assign errors_now[6] = tag_bad || head_bad || count>3", "assign errors_now[6] = head_bad || count>3"), 7, "EXPECTED_CHECKED_READ_FAULT_MISSING"),
    (("consumer_complete && consumed==512", "consumed==512"), 0, "MISSING_REAL_GUARD_CERTIFICATE_BYPASSED"),
    (("observed_now = enabled && owned && raw_valid === 1'b1", "observed_now = private_take"), 3, "EXPECTED_CHECKED_READ_FAULT_MISSING"),
    (("raw_metadata[3*i +: 3] === descriptor[3*i +: 3]", "i==24 || raw_metadata[3*i +: 3] === descriptor[3*i +: 3]"), 1, "UNCHECKED_TOKEN_ESCAPED"),
])
def test_executed_missing_check_credit_and_release_mutants(tmp_path, mutation, kind, marker):
    path = compile_case(tmp_path / "mutant", mutation)
    code, log = execute(path, kind, 74)
    assert code != 0 and marker in log, log


@pytest.mark.parametrize("value", ["-1", "2", "32'bx", "32'bz"])
def test_invalid_option_rejected_at_zero(tmp_path, value):
    path = compile_case(tmp_path / "invalid", extra=f"""module extra;
starlink_pss_checked_product_read #(.CHECKED_PRODUCT_READ({value})) dut();
endmodule
""")
    code, log = execute(path)
    assert code != 0 and "CHECKED_PRODUCT_READ must be zero or one" in log


def test_pinned_bank_dependency_and_old_runtime_literal_unchanged():
    assert hashlib.sha256((ACQ / "starlink_pss_epoch_sealed_bank.v").read_bytes()).hexdigest() == \
        "d9c2382f9087ccd2088fa5a5d3fed5c6fe885359d6d4c367ed2ea81ce099d9f6"
    for name in ("starlink_pss_fft_bank_owned_product_fence.v", "starlink_pss_product_fence_mailbox.v",
                 "starlink_pss_realtime_input_guard.v", "starlink_pss_realtime_result_guard.v",
                 "starlink_pss_forward_kernel_join_read_ahead.v", "starlink_pss_kernel_rom_read_ahead.v",
                 "starlink_pss_spectrum_product.v", "starlink_pss_block_mailbox.v"):
        old = subprocess.check_output(["git", "-C", str(ROOT / "hdl"), "show",
            "c144694706b0582668606b6224462c0e8850148d:library/starlink_pss_acquisition/" + name])
        assert (ACQ / name).read_bytes() == old

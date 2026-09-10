"""New343/late cases: offline derivation and bounded actual native-only probe."""

import copy
import shutil
import subprocess

import pytest

from tests.starlink_oracle.high_rate_case_result import verify_late
from tests.starlink_oracle.high_rate_cases import (
    PINS,
    ROOT,
    TB,
    derive_case,
    inverse,
    prepare_case,
    verify_case,
)
from tests.starlink_oracle.high_rate_harness import encoded, sha
from tests.starlink_oracle.high_rate_late_contract import validate_contract
from tests.test_starlink_native30_budget import NATIVE_SOURCES, prepare_native_files


@pytest.mark.parametrize("case", ["healthy343", "late447"])
def test_case_exact_inverse_and_no_original_change(tmp_path, case):
    before = {name: sha((ROOT / TB / name).read_bytes()) for name in PINS}
    output = tmp_path / "case"
    receipt = prepare_case(case, output)
    assert verify_case(case, output) == receipt
    assert before == PINS == {name: sha((ROOT / TB / name).read_bytes()) for name in PINS}
    with pytest.raises(ValueError, match="overwrite"):
        prepare_case(case, output)


def test_343_geometry_support_is_not_447_acceptance_relaxation():
    generated, receipt = derive_case("healthy343")
    assert receipt["contract"]["selected"] == 686
    assert 686 % 447 == 239 and 894 - 686 == 208
    assert receipt["contract"]["inverse_min"] == 512 + 65 + 239 == 816
    assert "map_343x2_u16.mem" in generated["bank_native30_case_fft_checks.svh"]
    assert "score_phase!==score_count%343" in generated["bank_native30_case_fft_checks.svh"]
    assert "score_count>=894" in generated["bank_native30_case_fft_checks.svh"]
    assert "native_capture_count!=260" in generated["tb_starlink_high_rate30_case.sv"]


@pytest.mark.parametrize("case", ["healthy343", "late447"])
@pytest.mark.parametrize("mutation", ["unchanged", "changed", "offset", "new_hash", "old_hash"])
def test_strict_inverse_rejects_mutation(tmp_path, case, mutation):
    generated, receipt = derive_case(case)
    name = "tb_starlink_high_rate30_case.sv"
    candidate = generated[name]
    rule = copy.deepcopy(receipt["strict_inverse"][name])
    if mutation == "unchanged":
        candidate = candidate.replace("always #5 clk=!clk;", "always #6 clk=!clk;")
    elif mutation == "changed":
        candidate = candidate.replace("module tb_starlink_high_rate30_case;", "module MUTANT;")
    elif mutation == "offset":
        rule["edits"][0]["offset"] += 1
    else:
        rule[mutation.replace("_hash", "_sha256")] = "0" * 64
    with pytest.raises(ValueError):
        inverse(candidate, rule)


@pytest.mark.parametrize("case", ["healthy343", "late447"])
def test_changed_case_contract_rejected(tmp_path, case):
    output = tmp_path / "case"
    receipt = prepare_case(case, output)
    receipt["contract"]["selected"] += 1
    (output / "case.json").write_bytes(encoded(receipt))
    with pytest.raises(ValueError, match="contract"):
        verify_case(case, output)


@pytest.mark.parametrize("case", ["healthy447", "healthy60", "late343", "343", ""])
def test_no_unreviewed_case_entry(tmp_path, case):
    with pytest.raises(ValueError, match="only healthy343 or late447"):
        prepare_case(case, tmp_path / "case")


def test_late_coordinate_budget_frozen_before_probe():
    c = validate_contract()
    assert c["actual_handshake_raw_closed"] == [17179870160, 17179870240]
    assert c["actual_signed_lead_closed"] == [-113, -33]
    assert c["derived_command_cycle_budget"] == 232
    assert c["derived_command_cycle_budget"] <= c["command_control_cycle_limit"] == 256
    c["actual_handshake_raw_closed"][0] += 1
    assert validate_contract()["actual_handshake_raw_closed"] == [17179870160, 17179870240]


def test_actual_late_native_only_zero_capture_result(tmp_path):
    # Freeze the contract, every source and original oracle BEFORE invocation.
    prepared = tmp_path / "case"
    prepare_case("late447", prepared)
    (tmp_path / "contract-before.json").write_bytes(encoded(validate_contract()))
    prepare_native_files(tmp_path)
    fixture_before = {path.name: sha(path.read_bytes()) for path in tmp_path.iterdir()
                      if path.suffix in {".mem", ".json"} and path.name != "contract-before.json"}
    (tmp_path / "fixtures-before.json").write_bytes(encoded(fixture_before))
    sources = [ROOT / "hdl/library" / name for name in NATIVE_SOURCES]
    source_dir = tmp_path / "source_snapshot"
    source_dir.mkdir()
    for source in sources:
        shutil.copyfile(source, source_dir / source.name)
    for name in ["bank_native30_late_logic.svh", "high_rate_paired_axi.svh"]:
        shutil.copyfile(ROOT / TB / name, source_dir / name)
    for path in prepared.iterdir():
        if path.suffix in {".sv", ".svh"}:
            shutil.copyfile(path, source_dir / path.name)
    before = {path.name: sha(path.read_bytes()) for path in source_dir.iterdir()}
    (tmp_path / "source-before.json").write_bytes(encoded(before))
    command = ["iverilog", "-g2012", "-Wall", "-I", str(source_dir), "-s", "tb_starlink_native30_late_probe",
               "-o", str(tmp_path / "late.vvp"), *[str(source_dir / path.name) for path in sources],
               str(source_dir / "tb_starlink_native30_late_probe.sv")]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    (tmp_path / "compile.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run(["vvp", str(tmp_path / "late.vvp")], cwd=tmp_path,
                            capture_output=True, text=True, timeout=30, check=False)
    (tmp_path / "simulation.log").write_text(result.stdout + result.stderr)
    after = {path.name: sha(path.read_bytes()) for path in source_dir.iterdir()}
    (tmp_path / "source-after.json").write_bytes(encoded(after))
    assert before == after
    assert (tmp_path / "contract-before.json").read_bytes() == encoded(validate_contract())
    fixture_after = {name: sha((tmp_path / name).read_bytes()) for name in fixture_before}
    (tmp_path / "fixtures-after.json").write_bytes(encoded(fixture_after))
    assert fixture_after == fixture_before
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FAIL" not in result.stdout and "ERROR" not in result.stdout and "FATAL" not in result.stdout
    assert result.stdout.count("NATIVE30_LATE_CONFIG_READY") == 1
    assert result.stdout.count("NATIVE30_LATE_HANDSHAKE") == 1
    assert result.stdout.count("NATIVE30_LATE_REJECT_PASS") == 1
    assert result.stdout.count("NATIVE30_LATE_ONLY_PASS") == 1
    assert "NATIVE30_PACKET_WORD" not in result.stdout
    assert (tmp_path / "native30_actual_raw_tuples.txt").stat().st_size == 0
    assert verify_case("late447", prepared)["late_contract"] == validate_contract()
    assert verify_late(tmp_path, result.stdout, native_only=True)["index"] in range(17179870160, 17179870241)


@pytest.mark.parametrize("case", ["healthy343", "late447"])
def test_whole_derived_top_compile_only_never_executes_fft(tmp_path, case):
    from tests.test_starlink_high_rate_harness import (
        test_full_top_elaboration_only_with_fail_fast_inert_fft,
    )
    baseline = tmp_path / "original447"
    baseline.mkdir()
    test_full_top_elaboration_only_with_fail_fast_inert_fft(baseline)
    generated = tmp_path / "generated"
    prepare_case(case, generated)
    frozen = baseline / "source_snapshot"
    shutil.copyfile(ROOT / TB / "bank_native30_late_logic.svh", frozen / "bank_native30_late_logic.svh")
    sources = sorted(frozen.glob("*.v"))
    command = ["iverilog", "-g2012", "-Wall", "-I", str(generated), "-I", str(frozen),
               "-s", "tb_starlink_high_rate30_case", "-o", str(tmp_path / "compile-only.vvp"),
               *map(str, sources), str(generated / "tb_starlink_high_rate30_case.sv")]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    (tmp_path / "compile-only.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (tmp_path / "simulate.log").exists()  # Deliberately no vvp.
    verify_case(case, generated)

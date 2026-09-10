"""Settings-only freeze and actual hierarchy elaboration; NEVER run FFT stimulus."""

import importlib.util
import json
import re
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.test_exact_control import STUB

ACQ = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"
SPEC = importlib.util.spec_from_file_location(
    "combined_prepare", ACQ / "prepare_exact_control_combined.py"
)
PREPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARE)
ORIGINAL = ACQ / "evidence/extra-edge-offline-v1/prepared"
TOP = "tb_starlink_pss_fft_bank_owned_slice"


def test_all_source_bytes_and_settings_provenance_only_inverse(tmp_path):
    output = tmp_path / "prepared"
    PREPARE.prepare(ORIGINAL, output)
    subprocess.run(["sha256sum", "-c", "SHA256SUMS", "--quiet"], cwd=output, check=True)
    old = json.loads((ORIGINAL / "preparation.json").read_text())
    new = json.loads((output / "preparation.json").read_text())
    assert new["settings"] == PREPARE.SETTINGS
    assert new["source_sha256"] == old["source_sha256"]
    assert {p.name for p in (output / "frozen_sources").iterdir()} == set(
        old["source_sha256"]
    )
    for name in old["source_sha256"]:
        assert (output / "frozen_sources" / name).read_bytes() == (
            ORIGINAL / "frozen_sources" / name
        ).read_bytes(), name
    # Whole metadata inverse permits only explicit option selection/provenance.
    new["settings"], new["scope"] = old["settings"], old["scope"]
    for key in (
        "combined_origin_inventory_sha256",
        "combined_origin_path",
        "combined_preparer_sha256",
    ):
        del new[key]
    assert new == old
    assert (output / "settings.tcl").read_text() == (
        "set exact_generics {REGISTERED_SCHEDULING=1 DISTRIBUTED_FAST_FAULT=1 "
        "PRIVATE_NEXT_START_SCRATCH=1 EXACT_EXTRA_EPOCHS=1 FAST_MHZ=175 QUICK_MUTATION=0}\n"
    )
    for path in ORIGINAL.iterdir():
        if path.is_file() and path.name not in {
            "settings.tcl",
            "preparation.json",
            "SHA256SUMS",
        }:
            assert (output / path.name).read_bytes() == path.read_bytes()
    runner = (output / "frozen_sources/simulate_exact_control_prepared.tcl").read_text()
    assert "25ab9d06ca0e03f280540cda625a7826b3c4cbaa6322ce3266c59e1fbad94122" in runner
    observer = (
        output / "frozen_sources/prepare_exact_control_status_qualified.py"
    ).read_text()
    assert "samples != expected_checks" in observer
    assert "original_raw_contract_pass=0" in observer
    with pytest.raises(FileExistsError):
        PREPARE.prepare(ORIGINAL, output)


def compiled_scope(text, instance, module, parent=None):
    chunks = re.split(r"(?=^S_\S+ \.scope )", text, flags=re.MULTILINE)
    rows = []
    for chunk in chunks:
        header = chunk.splitlines()[0]
        match = re.match(
            rf'^(S_\S+) \.scope module, "{re.escape(instance)}" "{re.escape(module)}" ',
            header,
        )
        if match and (parent is None or header.endswith(f", {parent};")):
            params = {
                key: int(bits, 2)
                for key, bits in re.findall(
                    r'\.param/l "(\w+)"[^\n]*\+C4<([01]+)>;', chunk
                )
            }
            rows.append((match[1], params))
    assert len(rows) == 1, (instance, module, parent, rows)
    return rows[0]


def test_actual_elaboration_candidate111_reference_registered_dec20_only(tmp_path):
    output = tmp_path / "prepared"
    PREPARE.prepare(ORIGINAL, output)
    source = output / "frozen_sources"
    stub = tmp_path / "compile_only_stub.v"
    stub.write_text(STUB)
    executable = tmp_path / "combined_elaborated_NEVER_RUN.vvp"
    result = subprocess.run(
        [
            "iverilog",
            "-g2012",
            "-Wall",
            "-I",
            str(source),
            "-s",
            TOP,
            *[f"-P{TOP}.{key}={value}" for key, value in PREPARE.SETTINGS.items()],
            "-o",
            str(executable),
            *map(str, sorted(source.glob("*.v"))),
            *map(str, sorted(source.glob("*.sv"))),
            str(stub),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    (tmp_path / "compile.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    compiled = executable.read_text()
    top_id, top = compiled_scope(compiled, TOP, TOP)
    candidate_id, candidate = compiled_scope(
        compiled, "dut", "starlink_pss_fft_bank_owned_slice", top_id
    )
    reference_id, reference = compiled_scope(
        compiled, "exact_reference", "tb_starlink_pss_exact_control_reference", top_id
    )
    _, reference_dut = compiled_scope(
        compiled,
        "dut",
        "starlink_pss_fft_bank_owned_slice_dec20d63_golden",
        reference_id,
    )
    assert {key: top[key] for key in PREPARE.SETTINGS} == PREPARE.SETTINGS
    for key in (
        "REGISTERED_SCHEDULING",
        "DISTRIBUTED_FAST_FAULT",
        "PRIVATE_NEXT_START_SCRATCH",
    ):
        assert candidate[key] == 1
    assert {
        key: reference[key]
        for key in (
            "REGISTERED_SCHEDULING",
            "EXACT_EXTRA_EPOCHS",
            "FAST_MHZ",
            "QUICK_MUTATION",
        )
    } == {
        "REGISTERED_SCHEDULING": 1,
        "EXACT_EXTRA_EPOCHS": 1,
        "FAST_MHZ": 175,
        "QUICK_MUTATION": 0,
    }
    assert reference_dut["REGISTERED_SCHEDULING"] == 1
    # Dec20 has neither D/S parameter nor the candidate's implementations.
    assert "DISTRIBUTED_FAST_FAULT" not in reference_dut
    assert "PRIVATE_NEXT_START_SCRATCH" not in reference_dut
    join_id, join = compiled_scope(
        compiled, "joiner", "starlink_pss_forward_kernel_join", candidate_id
    )
    _, rom = compiled_scope(compiled, "kernel_rom", "starlink_pss_kernel_rom", join_id)
    assert join["PRIVATE_NEXT_START_SCRATCH"] == rom["PRIVATE_NEXT_START_SCRATCH"] == 1
    (tmp_path / "compiled-bindings.json").write_text(
        json.dumps(
            {
                "scope": "actual_hierarchy_elaboration_ONLY_stub_NEVER_EXECUTED",
                "top": top,
                "candidate": candidate,
                "reference_bench": reference,
                "reference_dec20": reference_dut,
                "candidate_joiner": join,
                "candidate_rom": rom,
            },
            indent=2,
        )
        + "\n"
    )


def test_unreviewed_input_rejected_no_actual_launch(tmp_path):
    wrong = tmp_path / "wrong"
    wrong.mkdir()
    (wrong / "SHA256SUMS").write_text("wrong\n")
    with pytest.raises(ValueError, match="passing phase-aligned"):
        PREPARE.prepare(wrong, tmp_path / "absent")
    assert not (tmp_path / "absent").exists()
    helper = (ACQ / "prepare_exact_control_combined.py").read_text()
    assert "launch_simulation" not in helper and '"vivado"' not in helper

"""Source-specific v2 preparation/receipt tests, no vendor execution."""
import csv
import json
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.test_checked_product_read import clean_env
from tests.starlink_oracle.test_checked_product_drain_witness import ACQ, PREPARED

M = runpy.run_path(str(ACQ / "prepare_checked_product_drain_actual.py"))


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    output = tmp_path_factory.mktemp("drain_preparation") / "prepared"
    assert M["prepare"](PREPARED, output) == M["SETTINGS"]
    return output


def test_entire_original84_inverse_and_standalone_cli(prepared, tmp_path):
    original = M["rows"]((PREPARED / "SHA256SUMS").read_bytes())
    transformer = runpy.run_path(str(prepared / M["TRANSFORM"]))["transform"]
    changed = []
    for name, digest in original.items():
        old, new = (PREPARED / name).read_bytes(), (prepared / name).read_bytes()
        assert M["sha"](old) == digest
        if new != old:
            changed.append(name)
        if name == M["TOP"]:
            assert transformer(new.decode(), True).encode() == old
        elif name == M["RUNNER"]:
            assert M["runner"](new.decode(), True).encode() == old
        else:
            assert new == old
    assert set(changed) == {M["TOP"], M["RUNNER"]}
    assert len((prepared / "SHA256SUMS").read_text().splitlines()) == 89
    assert not (prepared / "project").exists()
    run = subprocess.run(["/home/mouse9911/gits/pluto-plus-utils/.venv/bin/python", "-B",
        str(prepared / M["SELF"]), "--verify-prepared", str(prepared)],
        cwd="/", env=clean_env(), capture_output=True, text=True, timeout=20)
    (tmp_path / "verify-stdout.log").write_text(run.stdout)
    (tmp_path / "verify-stderr.log").write_text(run.stderr)
    assert run.returncode == 0 and json.loads(run.stdout) == M["SETTINGS"]


@pytest.mark.parametrize("name", [
    M["TOP"], M["RUNNER"], "checked_product_actual_result.py", M["TRANSFORM"], M["TEST"],
    "frozen_sources/starlink_pss_fft_bank_owned_checked_product.v",
    "frozen_sources/starlink_pss_checked_product_actual_observer.svh",
    "frozen_sources/inverse_q17.mem", "frozen_sources/create_shared_realtime_xfft_ip.tcl",
    "drain-original-SHA256SUMS", "settings.tcl",
])
def test_rehashed_changed_inherited_policy_or_runtime_rejected(prepared, tmp_path, name):
    copy = tmp_path / "copy"
    shutil.copytree(prepared, copy)
    path = copy / name
    path.write_bytes(path.read_bytes() + b"\n")
    # A refreshed outer manifest is not authority to change inherited content.
    (copy / "SHA256SUMS").write_text("".join(f"{M['sha'](p.read_bytes())}  {p.relative_to(copy)}\n"
        for p in sorted(copy.rglob("*")) if p.is_file() and p.name != "SHA256SUMS"))
    with pytest.raises(ValueError):
        M["verify_prepared"](copy)


@pytest.mark.parametrize("mutation", ["wait", "ready", "parser", "runner", "old_source"])
def test_exact_mutated_source_inverses_fail(prepared, tmp_path, mutation):
    copy = tmp_path / "copy"
    shutil.copytree(prepared, copy)
    name, before, after = {
        "wait": (M["TOP"], "if (!QUICK_MUTATION) checked_profile_drain(32);", ""),
        "ready": (M["TOP"], "dut.output_bank_ready === 1'b1", "1'b1"),
        "parser": ("checked_product_actual_result.py", "len(services[1]) != 32", "len(services[1]) != 31"),
        "runner": (M["RUNNER"], "prepare_checked_product_drain_actual.py", "prepare_checked_product_actual_run.py"),
        "old_source": (M["TOP"], '"outputs/final real ACK failed to drain"', '"changed"'),
    }[mutation]
    path = copy / name
    assert before in path.read_text()
    path.write_text(path.read_text().replace(before, after, 1))
    with pytest.raises(ValueError):
        M["verify_prepared"](copy)


@pytest.fixture
def receipts(tmp_path):
    # Only marker-to-row unit data; intentionally not a full actual result.
    simulation = tmp_path / "simulation"
    simulation.mkdir()
    records = []
    for epoch, forward, drain in ((1, 100, 200), (2, 300, 410)):
        for cycle in (forward, drain):
            row = ["0"] * 24
            row[0:5] = [str(cycle), str(epoch), str(epoch-1), "1", "2"]
            row[6] = str(int(cycle == forward))
            row[21] = "1"
            records.append(row)
    with (simulation / "fft_bank_owned_trace.csv").open("w") as out:
        writer = csv.writer(out)
        writer.writerow(["UNIT_MARKER_TEST_NOT_FULL_TRACE"])
        writer.writerows(records)
    markers = ["CHECKED_PROFILE_DRAIN_WITNESS profile=0 count=32 forward=100 drain=200 service=100",
               "CHECKED_PROFILE_DRAIN_WITNESS profile=1 count=6 forward=300 drain=410 service=110"]
    (simulation / "simulate.log").write_text("\n".join(markers) + "\n")
    return simulation, {"service_cycles": {1: [100] * 32, 2: [110] * 6}}


def test_two_exact_drain_marker_rows(receipts):
    simulation, result = receipts
    assert M["verify_drain_receipts"](simulation, result)["markers"] == [(0, 32, 100, 200, 100), (1, 6, 300, 410, 110)]


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "bare", "count", "order", "cycle", "origin", "service", "budget", "other_profile"])
def test_missing_or_false_marker_rejected(receipts, mutation):
    simulation, result = receipts
    log = simulation / "simulate.log"
    lines = log.read_text().splitlines()
    if mutation == "missing":
        lines.pop()
    elif mutation == "duplicate":
        lines.append(lines[0])
    elif mutation == "bare":
        lines[0] = "CHECKED_PROFILE_DRAIN_WITNESS PASS"
    elif mutation == "order":
        lines.reverse()
    else:
        old, new = {"count": ("count=32", "count=6"), "cycle": ("drain=200", "drain=201"),
            "origin": ("forward=100", "forward=99"), "service": ("service=100", "service=99"),
            "budget": ("service=100", "service=5216"), "other_profile": ("profile=0", "profile=1")}[mutation]
        lines[0] = lines[0].replace(old, new)
    log.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError):
        M["verify_drain_receipts"](simulation, result)


@pytest.mark.parametrize("column,value", [(1, "2"), (2, "1"), (3, "0"), (3, "x"), (4, "7"),
    (8, "1"), (16, "1"), (21, "0"), (21, "z"), (22, "1")])
def test_reset_or_non_drained_csv_never_matches_receipt(receipts, column, value):
    simulation, result = receipts
    path = simulation / "fft_bank_owned_trace.csv"
    rows = list(csv.reader(path.read_text().splitlines()))
    rows[2][column] = value
    with path.open("w") as out:
        csv.writer(out).writerows(rows)
    with pytest.raises(ValueError, match="disagrees"):
        M["verify_drain_receipts"](simulation, result)


def test_unchanged_full_gate_must_pass_before_added_receipt(tmp_path, monkeypatch):
    function = M["verify_result"]
    monkeypatch.setitem(function.__globals__, "verify_prepared", lambda path: None)
    def rejected(path):
        raise ValueError("ORIGINAL_32_6_5215_GATE_REJECTED")
    monkeypatch.setattr(function.__globals__["runpy"], "run_path", lambda path: {"verify_result": rejected})
    monkeypatch.setitem(function.__globals__, "verify_drain_receipts", lambda *args: pytest.fail("new receipt bypassed original gate"))
    with pytest.raises(ValueError, match="ORIGINAL_32_6_5215"):
        function(tmp_path)


@pytest.mark.parametrize("kind", ["existing", "symlink"])
def test_no_overwrite_or_alias(tmp_path, kind):
    output = tmp_path / "candidate"
    if kind == "existing":
        output.mkdir()
    else:
        output.symlink_to(tmp_path / "absent")
    with pytest.raises((ValueError, FileExistsError)):
        M["prepare"](PREPARED, output)

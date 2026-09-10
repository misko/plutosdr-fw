"""Additive independent receipt/graph gates; stable136-test cut unchanged."""

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
FW = HERE.parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


BENCHES = load("test_inverse_sealed")
MODEL = load("inverse_sealed_events")


def freeze_python_scope(path):
    """Record the actual imported repository closure, including package imports.

    Framework/site-package binaries are not copied. Tool/version provenance is
    separate from the complete repository Python import/source inventory.
    """
    path.mkdir()
    sources = {
        Path(__file__),
        HERE / "inverse_sealed_events.py",
        HERE / "inverse_sealed.py",
        HERE / "test_inverse_sealed.py",
    }
    for module in tuple(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if (
            filename
            and Path(filename).suffix == ".py"
            and Path(filename).is_relative_to(FW)
        ):
            sources.add(Path(filename))
    inventory = {}
    for source in sorted(sources):
        name = source.relative_to(FW).as_posix().replace("/", "__")
        shutil.copyfile(source, path / name)
        inventory[name] = {
            "source": str(source),
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        }
    (path / "inventory.json").write_text(
        json.dumps(inventory, sort_keys=True, indent=2)
    )
    return inventory


def verify_python_scope(path, inventory):
    assert {p.name for p in path.iterdir()} == set(inventory) | {"inventory.json"}
    assert json.loads((path / "inventory.json").read_text()) == inventory
    for name, entry in inventory.items():
        assert hashlib.sha256((path / name).read_bytes()).hexdigest() == entry["sha256"]
        assert (
            hashlib.sha256(Path(entry["source"]).read_bytes()).hexdigest()
            == entry["sha256"]
        )


PROFILES = (
    [(case, 0, 0) for case in range(7)]
    + [(case, bit, 0) for case in [7, 8, 9] for bit in [0, 5, 36, 69, 72, 73, 74]]
    + [(10, phase, side) for phase in range(7) for side in [0, 1]]
    + [(11, 0, 0), (12, 0, 0)]
)


@pytest.fixture(scope="module")
def logs(tmp_path_factory):
    root = tmp_path_factory.mktemp("accepted_events")
    scope = root / "python_scope"
    inventory = freeze_python_scope(scope)
    result = {}
    try:
        for case, bit, side in PROFILES:
            path = root / f"case{case}_bit{bit}_side{side}"
            result[case, bit, side] = BENCHES.run_guard(path, case, bit=bit, side=side)
    finally:
        verify_python_scope(scope, inventory)
    return result


@pytest.mark.parametrize("profile", PROFILES)
def test_independent_nonzero_event_and_bounded_negative_inventory(logs, profile):
    case, bit, side = profile
    MODEL.verify_guard_events(logs[profile], case, bit=bit, side=side)


@pytest.mark.parametrize("case", range(13))
def test_terminal_only_and_truncated_negative_receipts_rejected(logs, case):
    original = logs[case, 0, 0]
    terminal = original.splitlines()[-1] + "\n"
    for changed in (terminal, "\n".join(original.splitlines()[:2]) + "\n" + terminal):
        with pytest.raises(ValueError):
            MODEL.verify_guard_events(changed, case)


@pytest.mark.parametrize(
    "mutation",
    [
        "epoch",
        "lease",
        "ordinal",
        "data",
        "metadata",
        "last_take",
        "cert",
        "pub",
        "ack",
        "release",
        "duplicate",
        "late_error",
        "phase",
        "unknown",
    ],
)
def test_healthy_receipt_mutations(logs, mutation):
    text = logs[0, 0, 0]
    lines = text.splitlines()
    take = next(i for i, line in enumerate(lines) if line.startswith("TAKE "))
    if mutation in ("epoch", "lease", "ordinal", "data", "metadata"):
        fields = lines[take].split()
        index, value = {
            "epoch": (2, "2"),
            "lease": (7, "lease=1"),
            "ordinal": (4, "1"),
            "data": (5, "0"),
            "metadata": (6, "0"),
        }[mutation]
        fields[index] = value
        lines[take] = " ".join(fields)
    elif mutation in ("last_take", "cert", "pub", "ack", "release"):
        prefix = {
            "last_take": "TAKE ",
            "cert": "CERT ",
            "pub": "PUB ",
            "ack": "ACK ",
            "release": "RELEASE ",
        }[mutation]
        index = next(i for i, line in enumerate(lines) if line.startswith(prefix))
        lines.pop(index)
    elif mutation == "duplicate":
        lines.insert(take, lines[take])
    elif mutation == "late_error":
        lines.insert(-1, "ERROR: late failure followed by terminal")
    elif mutation == "phase":
        lines[-1] = lines[-1].replace("phase_ps=0", "phase_ps=1")
    else:
        lines.insert(-1, "UNRECOGNIZED_SUCCESS_MARKER")
    with pytest.raises(ValueError):
        MODEL.verify_guard_events("\n".join(lines) + "\n", 0)


@pytest.mark.parametrize(
    "case,prefix",
    [
        (2, "CAUSE "),
        (3, "CAUSE "),
        (4, "S1 "),
        (5, "ACK "),
        (6, "PENDING_REQUEST"),
        (7, "METADATA_REJECT"),
        (10, "RESET_STAGE"),
        (11, "FIRST_FINAL"),
    ],
)
def test_negative_case_required_observation_not_just_zero_completed(logs, case, prefix):
    text = (
        "\n".join(
            line
            for line in logs[case, 0, 0].splitlines()
            if not line.startswith(prefix)
        )
        + "\n"
    )
    with pytest.raises(ValueError):
        MODEL.verify_guard_events(text, case)


def compile_graph(path, scope_name, mutant):
    path.mkdir()
    sources = (
        BENCHES.SOURCES
        if scope_name == "top"
        else [
            BENCHES.ACQ / "tb/tb_starlink_inverse_sealed_guard.sv",
            *[
                BENCHES.ACQ / (name + ".v")
                for name in (
                    "starlink_pss_realtime_result_guard",
                    "starlink_pss_block_mailbox",
                    "starlink_pss_epoch_sealed_bank_cdc",
                    "starlink_pss_inverse_sealed_issuer",
                )
            ],
        ]
    )
    for source in sources:
        shutil.copyfile(source, path / source.name)
    if mutant:
        source = path / "starlink_pss_inverse_sealed_issuer.v"
        before = source.read_text()
        old = "{2'b0, bad_admission_q, unowned_offer"
        assert before.count(old) == 1
        source.write_text(before.replace(old, "{2'b0, bad_admission, unowned_offer"))
    hashes = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in path.iterdir()
    }
    (path / "sources.json").write_text(json.dumps(hashes, indent=2, sort_keys=True))
    bench = BENCHES.BENCH if scope_name == "top" else "tb_starlink_inverse_sealed_guard"
    command = [
        "iverilog",
        "-g2012",
        "-s",
        bench,
        "-o",
        "graph.simv",
        *[p.name for p in sources],
    ]
    result = subprocess.run(
        command,
        cwd=path,
        env=BENCHES.env(),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    (path / "compile.log").write_text(result.stdout + result.stderr)
    (path / "command.json").write_text(
        json.dumps({"command": command, "exit": result.returncode})
    )
    assert hashes == {
        name: hashlib.sha256((path / name).read_bytes()).hexdigest() for name in hashes
    }
    assert result.returncode == 0, result.stderr
    return (path / "graph.simv").read_text()


@pytest.mark.parametrize("scope_name", ["guard", "top"])
@pytest.mark.parametrize("mutant", [False, True])
def test_complete_elaborated_comb_graph_and_deliberate_feedback(
    tmp_path, scope_name, mutant
):
    inventory = freeze_python_scope(tmp_path / "python_scope")
    try:
        graph = compile_graph(tmp_path / "run", scope_name, mutant)
        if mutant:
            with pytest.raises(ValueError, match="combinational cycle") as caught:
                MODEL.continuous_graph(graph)
            (tmp_path / "graph.json").write_text(
                json.dumps({"expected_rejection": str(caught.value)})
            )
        else:
            (tmp_path / "graph.json").write_text(
                json.dumps(MODEL.continuous_graph(graph), indent=2)
            )
    finally:
        verify_python_scope(tmp_path / "python_scope", inventory)


@pytest.mark.parametrize("mutation", ["missing", "extra", "modified", "inventory"])
def test_pre_run_python_dependency_inventory_is_exact(tmp_path, mutation):
    scope = tmp_path / "scope"
    inventory = freeze_python_scope(scope)
    if mutation == "missing":
        (scope / next(iter(inventory))).unlink()
    elif mutation == "extra":
        (scope / "unexpected.py").write_text("unexpected\n")
    elif mutation == "modified":
        (scope / next(iter(inventory))).write_text("changed\n")
    else:
        (scope / "inventory.json").write_text("{}")
    with pytest.raises(AssertionError):
        verify_python_scope(scope, inventory)


def test_whole_source_inverse_rejects_each_runtime_anchor_drift():
    for old, new, derive, restore in [
        (
            "starlink_pss_epoch_sealed_bank.v",
            "starlink_pss_epoch_sealed_bank_cdc.v",
            BENCHES.RECIPE.derive_cdc,
            BENCHES.RECIPE.restore_cdc,
        ),
        (
            "starlink_pss_fft_bank_owned_local_admission_probe.v",
            BENCHES.TOP + ".v",
            BENCHES.RECIPE.derive_top,
            BENCHES.RECIPE.restore_top,
        ),
    ]:
        with pytest.raises(ValueError):
            derive((BENCHES.ACQ / old).read_text() + "// different source\n")
        with pytest.raises(ValueError):
            restore((BENCHES.ACQ / new).read_text() + "// changed derived source\n")


def test_actual_release_opportunity_missing_current_veto_mutant(tmp_path):
    mutant = (
        "starlink_pss_epoch_sealed_bank_cdc.v",
        "assign lease_release = release_take && !release_bad && local_current_clean;",
        "assign lease_release = lease_release_valid && published_q && reader_epoch_idle && acknowledge_sync[1] == request_toggle;",
    )
    result = BENCHES.run_guard(tmp_path / "run", 12, mutant=mutant)
    assert result.returncode != 0
    assert "RELEASE_EDGE_CURRENT_FAULT_NOT_VETOED" in result.stdout


@pytest.mark.parametrize("value", ["2", "-1", "32'bx", "32'bz"])
@pytest.mark.parametrize("module", ["top", "bank"])
def test_case_inequality_parameter_guards_reject_invalid_and_unknown(
    tmp_path, module, value
):
    mutant = None
    if module == "top":
        bench = BENCHES.BENCH
        parameters = {"E": value}
        sources = BENCHES.SOURCES + [BENCHES.KERNEL]
        expected = "SEALED_INVERSE_OUTPUT must be zero or one"
        if "'" in value:
            parameters = {}
            mutant = (bench + ".sv", "CASE=0, E=1;", f"CASE=0, E={value};")
    else:
        bench = "starlink_pss_epoch_sealed_bank_cdc"
        parameters = {"SEALED_PUBLICATION": value}
        sources = [
            BENCHES.ACQ / (name + ".v")
            for name in (bench, "starlink_pss_block_mailbox")
        ]
        expected = "SEALED_PUBLICATION must be zero or one"
        if "'" in value:
            parameters = {}
            mutant = (
                bench + ".v",
                "parameter integer SEALED_PUBLICATION = 0",
                f"parameter integer SEALED_PUBLICATION = {value}",
            )
    # Icarus -P rejects X/Z strings but can still exit0 and use the default;
    # compile a literal declaration instead and retain the actual guard fatal.
    result = BENCHES.run_compiled(tmp_path / "run", bench, parameters, sources, mutant)
    assert result.returncode != 0 and expected in result.stdout


def test_iverilog_exit_zero_with_parameter_error_does_not_launch(tmp_path, monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            "",
            "<command line>: error: invalid digit in binary value specified for defparam\n",
        )

    monkeypatch.setattr(BENCHES.subprocess, "run", fake_run)
    with pytest.raises(AssertionError, match="invalid digit"):
        BENCHES.run_compiled(
            tmp_path / "run",
            "starlink_pss_block_mailbox",
            {},
            [BENCHES.ACQ / "starlink_pss_block_mailbox.v"],
        )
    assert len(calls) == 1 and calls[0][0] == "iverilog"

"""Pure admission, result, and archive checks for the radio-local operator."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
from types import ModuleType

import pytest


@pytest.fixture(scope="module")
def operator():
    prior = sys.modules.get("qualify_glrt_cpu_live20")
    sys.modules["qualify_glrt_cpu_live20"] = ModuleType("qualify_glrt_cpu_live20")
    try:
        root = Path(__file__).resolve().parents[2]
        spec = importlib.util.spec_from_file_location("radio_local_operator",
            root / "scripts/qualify_glrt_cpu_radio_local20.py")
        value = importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
        yield value
    finally:
        if prior is None: sys.modules.pop("qualify_glrt_cpu_live20", None)
        else: sys.modules["qualify_glrt_cpu_live20"] = prior


def parent(operator, *, count=4, started=0, result=0, complete=0, selection="none", selected=None, **changes):
    value = {"scope":"bounded_arm_scout_sparse_followup", "rate":operator.RATE,
        "result":result, "rf_sample_limit":count*operator.SCOUT_SAMPLES + started*operator.FOLLOWUP_SAMPLES,
        "followup_started":started, "track_complete":complete, "selection":selection,
        "selected_index":selected}
    value.update(changes)
    return (json.dumps(value, separators=(",", ":")) + "\n").encode()


def archive(visits, *, extra=None):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as tar:
        files = {"evidence/visits.txt":b"plan\n"}
        for number in visits:
            for name in ("stdout.json", "stderr.txt", "capture.txt", "worker.jsonl"):
                files[f"evidence/visit-{number}/{name}"] = b"x\n"
        if extra: files[extra] = b"x"
        for name, data in files.items():
            info = tarfile.TarInfo(name);info.size = len(data);info.mode = 0o600
            tar.addfile(info, io.BytesIO(data))
    return output.getvalue()


def test_cycle_has_reviewed_distinct_los_and_explicit_worst_case(operator):
    ordered = [1440312500,1940312500,1190312500,1690312500]
    assert operator.validate_los(ordered) == tuple(ordered)
    assert operator.maximum_source_seconds(4) == pytest.approx(335.1773184)
    for values in ([],[1440312500],[1440312500]*2,[1709687500],list(operator.UPPER_EDGE_LOS)+[1190312500]):
        with pytest.raises(ValueError): operator.validate_los(values)


def test_outputs_are_new_and_confined_to_ssd_then_raid(operator,tmp_path):
    output=Path('/srv/postgres-nvme/codex-radio20-authority/unit-new-output')
    raid=Path('/srv/bulk/leo/unit-new-output')
    assert operator.validate_outputs(output,raid)==(output,raid)
    for bad in ((tmp_path/'ssd',raid),(output,tmp_path/'raid'),(output,output)):
        with pytest.raises(ValueError): operator.validate_outputs(*bad)


def test_dry_run_is_explicitly_non_rf_and_contains_reviewable_next_action(operator):
    los=(1440312500,1940312500,1190312500,1690312500)
    plan=operator.dry_run_plan(los,operator.EXPECTED,Path('/srv/postgres-nvme/x'),Path('/srv/bulk/leo/x'))
    assert plan['rf_collection'] is False and plan['serial']==operator.SERIAL
    assert plan['maximum_source_seconds']==pytest.approx(335.1773184)
    assert plan['next_action'].endswith('explicit RF authorization')


def test_parent_distinguishes_negative_activity_loss_and_completed_track(operator):
    assert operator.decode_parent(parent(operator),operator.RATE,4,0)["selection"] == "none"
    loss = parent(operator,started=1,result=1,selection="retained_activity",selected=0)
    assert not operator.decode_parent(loss,operator.RATE,4,1)["track_complete"]
    done = parent(operator,started=1,result=0,complete=1,selection="retained_activity",selected=1)
    assert operator.decode_parent(done,operator.RATE,4,0)["track_complete"]
    native = parent(operator,started=1,result=3,selection="native_handoff",selected=3)
    assert operator.decode_parent(native,operator.RATE,4,1)["result"] == 3


@pytest.mark.parametrize("raw,exit_code", [
    (b"{}\n",0), (b"{}\n{}\n",0),
    (None,0),
])
def test_parent_rejects_ambiguous_or_inconsistent_status(operator,raw,exit_code):
    raw = raw if raw is not None else parent(operator,started=1,result=0,complete=0,selection="retained_activity",selected=0)
    with pytest.raises((ValueError,KeyError)): operator.decode_parent(raw,operator.RATE,4,exit_code)
    with pytest.raises(ValueError):
        operator.decode_parent(parent(operator,rf_sample_limit=1),operator.RATE,4,0)


def test_archive_requires_exact_executed_scouts_and_followup(operator,tmp_path):
    negative = operator.decode_parent(parent(operator,count=2),operator.RATE,2,0)
    assert operator.extract_evidence(archive({0,1}),tmp_path/"negative",negative,2) == 9
    triggered = operator.decode_parent(parent(operator,started=1,result=1,selection="retained_activity",selected=1),operator.RATE,4,1)
    assert operator.extract_evidence(archive({0,1,4}),tmp_path/"triggered",triggered,4) == 13
    for damaged in (archive({0}),archive({0,1},extra="outside"),archive({0,1},extra="evidence/visit-9/stdout.json")):
        with pytest.raises(ValueError): operator.extract_evidence(damaged,tmp_path/("bad"+str(len(damaged))),negative,2)


def test_manifest_is_sorted_and_recomputable(operator,tmp_path):
    (tmp_path/"b").write_bytes(b"b");(tmp_path/"a").write_bytes(b"a")
    data = operator.manifest(tmp_path)
    assert [row.split("  ")[1] for row in data.decode().splitlines()] == ["a","b"]
    assert operator.manifest(tmp_path) == data

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


def continuity_parent(operator, *, count=4, rounds=3, segments=2, visits=10,
                      result=1, complete=0, selection="retained_activity", selected=1, **changes):
    scouts=visits-segments
    value={"scope":"bounded_arm_scout_segmented_followup","rate":operator.RATE,
        "result":result,"rf_sample_limit":scouts*operator.SCOUT_SAMPLES+segments*operator.SEGMENT_SAMPLES,
        "scan_rounds":rounds,"segments_started":segments,"visits_executed":visits,
        "track_complete":complete,"selection":selection,"selected_index":selected}
    value.update(changes)
    return (json.dumps(value,separators=(",",":"))+"\n").encode()


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
    assert operator.maximum_source_seconds(4,operator.CONTINUITY30_PROFILE) == pytest.approx(268.2519552)
    assert operator.maximum_source_seconds(4,operator.WAIT_PRIOR_CONTINUITY30_PROFILE) == pytest.approx(630.6398208)
    assert operator.maximum_source_seconds(4,operator.WAIT100_PROFILE) == pytest.approx(778.0958208)
    assert operator.maximum_source_seconds(2,operator.WAIT40_100_PROFILE) == pytest.approx(1100.218368)
    with pytest.raises(ValueError): operator.validate_los(ordered,operator.WAIT40_100_PROFILE)
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
    assert plan['next_action']=='repeat without --dry-run'


@pytest.mark.parametrize('profile',["sparse10-after-scout16","sparse30-after-scout16","sparse100-after-scout16",
    "continuity30-after-scout16","continuity30-ranked-after-scout16","continuity30-fresh-after-scout1",
    "continuity30-prior-after-scout1","continuity30-prior-wait12-after-scout1",
    "sparse100-wait12-after-scout1","sparse100-wait40-after-scout1"])
def test_dry_run_retains_the_selected_tracking_horizon(operator,profile):
    plan=operator.dry_run_plan((1440312500,1940312500),operator.EXPECTED,
        Path('/srv/postgres-nvme/x'),Path('/srv/bulk/leo/x'),profile)
    assert profile in operator.PROFILES and plan['profile']==profile


def test_parent_distinguishes_negative_activity_loss_and_completed_track(operator):
    assert operator.decode_parent(parent(operator),operator.RATE,4,0)["selection"] == "none"
    loss = parent(operator,started=1,result=1,selection="retained_activity",selected=0)
    assert not operator.decode_parent(loss,operator.RATE,4,1)["track_complete"]
    done = parent(operator,started=1,result=0,complete=1,selection="retained_activity",selected=1)
    assert operator.decode_parent(done,operator.RATE,4,0)["track_complete"]
    native = parent(operator,started=1,result=3,selection="native_handoff",selected=3)
    assert operator.decode_parent(native,operator.RATE,4,1)["result"] == 3
    failed = parent(operator,started=1,result=-4,selection="retained_activity",selected=2)
    assert operator.decode_parent(failed,operator.RATE,4,1)["result"] == -4


def test_continuity_parent_retains_round_segment_and_sample_accounting(operator):
    row=operator.decode_parent(continuity_parent(operator),operator.RATE,4,1,operator.CONTINUITY30_PROFILE)
    assert row["scan_rounds"]==3 and row["segments_started"]==2 and not row["track_complete"]
    complete=continuity_parent(operator,rounds=2,segments=2,visits=7,result=0,complete=1)
    assert operator.decode_parent(complete,operator.RATE,4,0,operator.CONTINUITY30_PROFILE)["track_complete"]
    empty=continuity_parent(operator,rounds=3,segments=0,visits=12,result=0,selection="none",selected=None)
    assert not operator.decode_parent(empty,operator.RATE,4,0,operator.CONTINUITY30_PROFILE)["track_complete"]
    with pytest.raises(ValueError):
        operator.decode_parent(continuity_parent(operator,rf_sample_limit=1),operator.RATE,4,1,
                               operator.CONTINUITY30_PROFILE)
    ranked=continuity_parent(operator,scope="bounded_arm_scout_ranked_segmented_followup",
        activity_selection="strongest_complete_scan")
    assert operator.decode_parent(ranked,operator.RATE,4,1,
        operator.RANKED_CONTINUITY30_PROFILE)["activity_selection"]=="strongest_complete_scan"
    fresh=continuity_parent(operator,scope="bounded_arm_scout_fresh_segmented_followup",
        activity_selection="strongest_one_attempt_scan")
    assert operator.decode_parent(fresh,operator.RATE,4,1,
        operator.FRESH_CONTINUITY30_PROFILE)["activity_selection"]=="strongest_one_attempt_scan"
    prior=continuity_parent(operator,scope="bounded_arm_scout_prior_segmented_followup",
        activity_selection="strongest_one_attempt_scan_prior_reacquire")
    assert operator.decode_parent(prior,operator.RATE,4,1,
        operator.PRIOR_CONTINUITY30_PROFILE)["activity_selection"]=="strongest_one_attempt_scan_prior_reacquire"
    wait=continuity_parent(operator,rounds=12,segments=0,visits=48,result=0,
        selection="none",selected=None,scope="bounded_arm_scout_prior_wait_segmented_followup",
        activity_selection="strongest_one_attempt_scan_prior_reacquire_wait12")
    assert operator.decode_parent(wait,operator.RATE,4,0,
        operator.WAIT_PRIOR_CONTINUITY30_PROFILE)["scan_rounds"]==12
    wait100=continuity_parent(operator,rounds=1,segments=1,visits=5,result=0,complete=1,
        scope="bounded_arm_scout_wait100_followup",
        rf_sample_limit=4*operator.SCOUT_SAMPLES+operator.FOLLOWUP_RF_SAMPLES,
        activity_selection="strongest_one_attempt_scan_power50_wait12_track100")
    assert operator.decode_parent(wait100,operator.RATE,4,0,
        operator.WAIT100_PROFILE)["track_complete"]==1
    wait40=continuity_parent(operator,rounds=40,segments=0,visits=80,result=0,
        selection="none",selected=None,scope="bounded_arm_scout_wait100_followup",
        activity_selection="strongest_one_attempt_scan_power50_wait40_track100")
    assert operator.decode_parent(wait40,operator.RATE,2,0,
        operator.WAIT40_100_PROFILE)["scan_rounds"]==40
    for damaged in (
        continuity_parent(operator,rounds=13,segments=0,visits=52,result=0,selection="none",selected=None,
            scope="bounded_arm_scout_prior_wait_segmented_followup",
            activity_selection="strongest_one_attempt_scan_prior_reacquire_wait12"),
        continuity_parent(operator,rounds=4,segments=4,visits=8,result=1,
            scope="bounded_arm_scout_prior_wait_segmented_followup",
            activity_selection="strongest_one_attempt_scan_prior_reacquire_wait12"),
    ):
        with pytest.raises(ValueError):
            operator.decode_parent(damaged,operator.RATE,4,1,operator.WAIT_PRIOR_CONTINUITY30_PROFILE)


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


def test_continuity_archive_requires_every_contiguous_segment_visit(operator,tmp_path):
    row=operator.decode_parent(continuity_parent(operator),operator.RATE,4,1,operator.CONTINUITY30_PROFILE)
    assert operator.extract_evidence(archive(set(range(10))),tmp_path/"continuity",row,4)==41
    with pytest.raises(ValueError):
        operator.extract_evidence(archive(set(range(9))),tmp_path/"missing",row,4)


def test_manifest_is_sorted_and_recomputable(operator,tmp_path):
    (tmp_path/"b").write_bytes(b"b");(tmp_path/"a").write_bytes(b"a")
    data = operator.manifest(tmp_path)
    assert [row.split("  ")[1] for row in data.decode().splitlines()] == ["a","b"]
    assert operator.manifest(tmp_path) == data

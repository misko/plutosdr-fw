from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.starlink_pss_hardware_probe_v12 as probe


def _snapshot(*, discarded: int = 0, aborts: int = 0, **updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": "starlink-pss-acqctl.snapshot.v1",
        "fault_free_epoch": discarded == 0 and aborts == 0,
        "ready_mask": 0,
        "health_flags": "0x00000000",
        "discarded_scores": discarded,
        "discontinuity_aborts": aborts,
    }
    value.update({field: 0 for field in probe._NON_CLEANUP_ZERO_FIELDS})
    value.update(updates)
    return value


def _candidate(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": "starlink-pss-acqctl.candidate.v1",
        "fault_free_epoch": True,
        "continuity_ok": True,
        "final_health_flags": "0x00000000",
        "ddc_counters_before": {
            "accepted": 10,
            "emitted": 5,
            "discontinuity": 0,
            "saturation": 0,
        },
        "ddc_counters_after": {
            "accepted": 20,
            "emitted": 10,
            "discontinuity": 0,
            "saturation": 0,
        },
    }
    value.update(updates)
    return value


def test_v12_accepts_and_classifies_exact_cleanup_only_pair() -> None:
    result = probe._cleanup_only_contract(
        _snapshot(), _candidate(), _snapshot(discarded=1, aborts=1)
    )
    assert result == {
        "schema": "starlink-pss-probe.cleanup-verification.v1",
        "classification": "controller_disable_flush_only",
        "raw_fault_free_epoch": False,
        "discarded_scores_delta": 1,
        "discontinuity_aborts_delta": 1,
        "non_cleanup_faults_zero": True,
        "candidate_observation_fault_free": True,
    }


@pytest.mark.parametrize(
    ("updates", "match"),
    [
        ({"scheduler_gaps": 1}, "real fault"),
        ({"discarded_scores": 2, "fault_free_epoch": False}, "bounded shutdown"),
        ({"health_flags": "0x00000001"}, "not clean before shutdown"),
    ],
)
def test_v12_rejects_real_or_unbounded_post_cleanup_faults(
    updates: dict[str, object], match: str
) -> None:
    with pytest.raises(probe.ProbeError, match=match):
        probe._cleanup_only_contract(_snapshot(), _candidate(), _snapshot(**updates))


def test_v12_rejects_ddc_fault_during_candidate() -> None:
    candidate = _candidate()
    candidate["ddc_counters_after"] = {
        "accepted": 20,
        "emitted": 10,
        "discontinuity": 1,
        "saturation": 0,
    }
    with pytest.raises(probe.ProbeError, match="DDC fault"):
        probe._cleanup_only_contract(_snapshot(), candidate, _snapshot())


def test_v12_inherited_measure_sees_admitted_flag_but_receipt_keeps_raw(monkeypatch) -> None:
    responses = iter((_snapshot(), _candidate(), _snapshot(discarded=1, aborts=1)))
    monkeypatch.setattr(probe.probe_v1, "_remote_json", lambda *a, **k: next(responses))

    def inherited(*_args: object) -> dict[str, object]:
        before = probe.probe_v1._remote_json()
        probe.probe_v1._remote_json()
        after = probe.probe_v1._remote_json()
        assert before["fault_free_epoch"] is True
        assert after["fault_free_epoch"] is True
        return {"snapshot_after": after}

    monkeypatch.setattr(probe, "_DEPENDENCY_SAFE_MEASURE", inherited)
    measurement = probe._measure({}, object(), object(), object(), object(), object())
    assert measurement["snapshot_after"]["fault_free_epoch"] is False
    assert measurement["controller_cleanup"]["classification"] == (
        "controller_disable_flush_only"
    )


def test_v12_execute_scopes_measurement_override(monkeypatch) -> None:
    original = probe.probe_v5._measure
    observed: list[object] = []

    def execute(_args: object) -> dict[str, bool]:
        observed.append(probe.probe_v5._measure)
        return {"ok": True}

    monkeypatch.setattr(probe.probe_v11, "execute_plan", execute)
    assert probe.execute_plan(SimpleNamespace()) == {"ok": True}
    assert observed == [probe._measure]
    assert probe.probe_v5._measure is original


def test_v12_probe_manifest_is_offline_dnm_and_byte_exact() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = root / "manifests/starlink-pss-hardware-probe-dnm-v12-source.yaml"
    values = {
        key.strip(): value.strip().strip('"')
        for line in manifest.read_text().splitlines()
        if line and not line.startswith("#") and ":" in line
        for key, value in (line.split(":", 1),)
    }
    assert values["schema_version"] == "12"
    assert values["do_not_merge"] == "true"
    assert values["persistent_flash_eligible"] == "false"
    assert values["hardware_accessed"] == "false"
    assert values["cleanup_contract"] == "controller_disable_flush_only"
    assert values["cleanup_raw_snapshot_retained"] == "true"
    for prefix in (
        "probe_script",
        "probe_test",
        "inherited_v11_probe_script",
        "inherited_v11_manifest",
        "candidate_source",
        "plan",
    ):
        member = root / values[f"{prefix}_path"]
        assert member.is_file()
        assert hashlib.sha256(member.read_bytes()).hexdigest() == values[
            f"{prefix}_sha256"
        ]

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifests/starlink-pss-m2-probe-dnm-v3-source.yaml"


def _values() -> dict[str, str]:
    return {
        key.strip(): value.strip().strip('"')
        for line in MANIFEST.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and ":" in line
        for key, value in (line.split(":", 1),)
    }


def test_m2_v3_manifest_is_dnm_and_adds_a_full_period_of_warmup() -> None:
    values = _values()

    assert values["schema"] == "plutosdr-fw.starlink-pss-m2-probe-source"
    assert values["schema_version"] == "3"
    assert values["supersedes_manifest"] == (
        "starlink-pss-m2-probe-dnm-v2-source.yaml"
    )
    assert values["source_change"] == "one-period-deterministic-pipeline-warmup"
    assert values["do_not_merge"] == "true"
    assert values["merge_target"] == "none"
    assert values["persistent_flash_eligible"] == "false"
    assert values["hardware_accessed"] == "false"
    assert values["supported_sample_rate_msps"] == "15"
    assert values["pipeline_warmup_samples"] == "20000"
    assert values["pipeline_warmup_periods"] == "1"
    assert values["fpga_image_changed"] == "false"
    assert values["rf_configuration_changed"] == "false"


def test_m2_v3_manifest_binds_the_exact_corrected_sources() -> None:
    values = _values()

    for prefix in (
        "host_probe",
        "manifest_test",
        "controller",
        "qualification_library",
        "qualification_header",
        "qualification_test",
        "fixture_vector",
        "score_vector",
        "candidate_source_manifest",
    ):
        member = ROOT / values[f"{prefix}_path"]
        assert member.is_file()
        assert hashlib.sha256(member.read_bytes()).hexdigest() == values[
            f"{prefix}_sha256"
        ]

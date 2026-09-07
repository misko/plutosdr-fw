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


def test_m2_v3_manifest_preserves_the_warmup_probe_sources() -> None:
    values = _values()

    assert values["host_probe_sha256"] == (
        "0f9a1819ec1f19e99b2a9e1fa72581cf86ef807a2aedbabeddd03a8c39e9be92"
    )
    assert values["manifest_test_sha256"] == (
        "6c65a444c02d7d36d3cba82679219a7a57311f0930f719846585ea8df596a259"
    )
    assert values["controller_sha256"] == (
        "f7b26e2b68d4dfa7afe471d55fb34c82696f6a719a2b0a64bd35594de5b57029"
    )
    assert values["qualification_library_sha256"] == (
        "17e855ebbd8db30bd5ead4b36662412f3009aed9fef37447902b43343fe13de0"
    )
    assert values["qualification_header_sha256"] == (
        "d11374b11e1ab8485cb259ff64fde704e45a3c50d7b6ab5def82eae0c0bd78b9"
    )
    assert values["qualification_test_sha256"] == (
        "3efa1e96e64f0c38f636292d2022838beef0d98a464d55e06a509b3f32a67e8a"
    )
    for prefix in (
        "fixture_vector",
        "score_vector",
        "candidate_source_manifest",
    ):
        member = ROOT / values[f"{prefix}_path"]
        assert member.is_file()
        assert hashlib.sha256(member.read_bytes()).hexdigest() == values[
            f"{prefix}_sha256"
        ]


def test_m2_v4_manifest_binds_the_exact_timing_signature_sources() -> None:
    values = {
        key.strip(): value.strip().strip('"')
        for line in (
            ROOT / "manifests/starlink-pss-m2-probe-dnm-v4-source.yaml"
        ).read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and ":" in line
        for key, value in (line.split(":", 1),)
    }

    assert values["schema_version"] == "4"
    assert values["supersedes_manifest"] == (
        "starlink-pss-m2-probe-dnm-v3-source.yaml"
    )
    assert values["source_change"] == "block-cadence-aware-timing-signature"
    assert values["full_map_exactness_claimed"] == "false"
    assert values["timing_signature_peak_value"] == "16320"
    assert values["timing_signature_runner_up_value"] == "7424"
    for prefix in (
        "host_probe",
        "host_test",
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

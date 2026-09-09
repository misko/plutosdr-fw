"""Small synthetic contract tests, not evidence from the named RF capture."""

from __future__ import annotations

import json

import numpy as np
import pytest

from tools import starlink_capture25_score_fixture as fixture


@pytest.fixture
def source(tmp_path):
    values = np.random.default_rng(25).integers(-1000, 1000, (8000, 2), dtype=np.int16)
    path = tmp_path / "conditioned-15msps.ci16"
    path.write_bytes(values.tobytes())
    report = {"schema": fixture.replay.SCHEMA, "status": "REPLAY_COMPLETE",
              "numerical_qualification_pass": True, "window": "positive",
              "capture": {"manifest_sha256": fixture.replay.MANIFEST_SHA256,
                          "serial": fixture.replay.SERIAL, "stream_id": fixture.replay.STREAM_ID,
                          "source_start_index": 900000000, "source_stop_index": 908000000,
                          "continuity_segment_index": 13},
              "conditioned_ci16": {"path": str(path), "format": "ci16_le", "sample_rate_hz": 15000000,
                                   "cfo_assistance_applied": False, "source_center_numerator_per_index": 5,
                                   "source_center_denominator": 3, "sample_count": len(values),
                                   "bytes": len(values) * 4, "sha256": fixture.replay.sha256(values.tobytes()),
                                   "first_canonical_index": 540000000},
              "conditioning": {"clipped_components": 0, "first_canonical_index": 540000000,
                               "canonical_stop_index": 540008000},
              "geometry": {"canonical_start_index": 540000000, "model_input_samples": 7664,
                           "requested_candidate_scores": 7599},
              "variants": [{"name": "baseline", "numerical_qualification_pass": True, "assisted_cfo_hz": 0},
                           {"name": "assisted", "numerical_qualification_pass": True,
                            "assisted_cfo_hz": 285798.94603620283}]}
    for variant in report["variants"]:
        corrected, clips = fixture.replay.derotate_ci16(values[:7664], 540000000,
                                                        variant["assisted_cfo_hz"])
        assert clips == 0
        score_bytes = (np.arange(7599) % 255).astype(np.uint8).tobytes()
        score_path = tmp_path / (variant["name"] + ".scores.u8")
        score_path.write_bytes(score_bytes)
        variant.update(model_input_samples=7664, model_first_canonical_index=540000000,
                       model_input_ci16_sha256=fixture.replay.sha256(corrected.tobytes()),
                       retained_score_count=7599,
                       scores={"path": str(score_path), "bytes": 7599,
                               "sha256": fixture.replay.sha256(score_bytes)})
    report_path = tmp_path / "report.json"

    def save():
        report_path.write_text(json.dumps(report))

    save()
    return report_path, report, values, save


@pytest.mark.parametrize("variant", ["baseline", "assisted"])
def test_fixed_evidence_selected_slice_and_absolute_cfo(source, variant):
    path, _report, values, _save = source
    actual, evidence, payload, expected_scores = fixture.load_recorded_slice(path, variant)
    expected = values[5364:6770]
    if variant == "assisted":
        expected, clips = fixture.replay.derotate_ci16(expected, 540005364, 285798.94603620283)
        assert clips == 0
    np.testing.assert_array_equal(actual, expected)
    assert evidence["first_canonical_index"] == 540005364
    assert len(expected_scores) == 1341
    assert evidence["short_corrected_ci16_equals_full_replay_slice"]
    assert evidence["source_replay_report_sha256"] == fixture.replay.sha256(payload)
    assert evidence["planted_samples_or_score_peaks"] is False
    assert evidence["long_replay_score_subset_equivalence_asserted"] is False


@pytest.mark.parametrize(("section", "key", "value"), [
    (None, "status", "RUNNING"), (None, "window", "negative"),
    (None, "numerical_qualification_pass", False),
    ("capture", "serial", "other"), ("capture", "manifest_sha256", "bad"),
    ("capture", "continuity_segment_index", 12),
    ("conditioned_ci16", "sha256", "bad"), ("conditioned_ci16", "bytes", 1),
    ("conditioned_ci16", "cfo_assistance_applied", True),
    ("conditioned_ci16", "first_canonical_index", 540000001),
    ("conditioning", "clipped_components", 1), ("geometry", "canonical_start_index", 1),
])
def test_bad_provenance_or_clipping_rejected(source, section, key, value):
    path, report, _values, save = source
    target = report if section is None else report[section]
    target[key] = value
    save()
    with pytest.raises(ValueError):
        fixture.load_recorded_slice(path, "baseline")


def test_missing_or_duplicate_variant_rejected(source):
    path, report, _values, save = source
    with pytest.raises(ValueError, match="selected replay variant"):
        fixture.load_recorded_slice(path, "other")
    report["variants"].append(report["variants"][0])
    save()
    with pytest.raises(ValueError, match="selected replay variant"):
        fixture.load_recorded_slice(path, "baseline")


def test_existing_output_untouched_before_read(source, tmp_path, monkeypatch):
    output = tmp_path / "exists"
    output.mkdir()
    monkeypatch.setattr(fixture, "load_recorded_slice", lambda *a: pytest.fail("no source read"))
    with pytest.raises(FileExistsError):
        fixture.generate(source[0], "baseline", output)
    assert list(output.iterdir()) == []


def test_failed_load_retains_partial_receipt_without_admission_manifest(source, tmp_path):
    path, report, _values, save = source
    report["conditioned_ci16"]["sha256"] = "bad"
    save()
    output = tmp_path / "failed"
    with pytest.raises(ValueError):
        fixture.generate(path, "baseline", output)
    assert not (output / "recorded_fixture.json").exists()
    partial = json.loads((output / "fixture_provenance.json").read_text())
    assert partial["status"] == "FAILED_PARTIAL" and partial["hardware_or_lock_qualified"] is False


def test_real_small_model_no_planted_peaks_and_exact_vector_wire_schema(source, tmp_path):
    if not fixture.replay.xfft_bitacc.INSTALLED_CMODEL_ARCHIVE.is_file():
        pytest.skip("installed Vivado C model unavailable")
    _path, report, values, save = source
    model_dir = fixture.replay.xfft_bitacc.prepare_installed_cmodel(tmp_path / "reference-model")
    coefficients = fixture.replay.quantize_q15(fixture.replay.projected_pss(15000000, "upper"))
    with fixture.replay.model_q17(model_dir) as model:
        reference = fixture.replay.xfft_bitacc.xfft_bitacc_match_scores(values[:7664], coefficients, model,
                                                                       first_sample_index=540000000)
    full_score_bytes = reference.stream.scores.astype(np.uint8).tobytes()
    score_path = tmp_path / "baseline.scores.u8"
    score_path.write_bytes(full_score_bytes)
    report["variants"][0]["scores"]["sha256"] = fixture.replay.sha256(full_score_bytes)
    save()
    output = tmp_path / "generated"
    evidence = fixture.generate(source[0], "baseline", output)
    manifest = json.loads((output / "recorded_fixture.json").read_text())
    assert set(manifest) == {"schema", "source_kind", "input_rate_hz", "first_canonical_index", "vectors"}
    assert manifest["first_canonical_index"] == 540005364
    assert set(manifest["vectors"]) == set(fixture.GEOMETRY)
    for name, (rows, width) in fixture.GEOMETRY.items():
        raw = (output / (name + ".mem")).read_bytes()
        assert manifest["vectors"][name] == {"rows": rows, "hex_digits": width,
                                              "sha256": fixture.replay.sha256(raw)}
        words = raw.decode().splitlines()
        assert len(words) == rows and all(len(word) == width for word in words)
    assert evidence["observed_score_summary"]["maximum"] < 255
    assert evidence["status"] == "RECORDED_FIXTURE_GENERATED"
    assert evidence["zero_padded_input_blocks"] == 0
    assert evidence["long_replay_score_subset_equivalence_asserted"]
    assert evidence["exact_score_slice_sha256"] == fixture.replay.sha256(full_score_bytes[5364:6705])


def test_trace_rejects_partial_last_fft():
    with pytest.raises(ValueError, match="exactly1406"):
        fixture.trace_vectors(np.zeros((1405, 2), dtype=np.int16), 0, None, {})


@pytest.mark.parametrize("kind", ["full_input_hash", "score_hash", "short_cfo", "unaligned_count"])
def test_full_replay_slice_crossbinding_failures(source, monkeypatch, kind):
    path, report, _values, save = source
    if kind == "full_input_hash":
        report["variants"][0]["model_input_ci16_sha256"] = "bad"
    elif kind == "score_hash":
        report["variants"][0]["scores"]["sha256"] = "bad"
    elif kind == "unaligned_count":
        report["variants"][0]["model_input_samples"] -= 1
    else:
        original = fixture.replay.derotate_ci16

        def corrupt(samples, first, cfo):
            result, clips = original(samples, first, cfo)
            if len(samples) == 1406:
                result[0, 0] += 1
            return result, clips

        monkeypatch.setattr(fixture.replay, "derotate_ci16", corrupt)
    save()
    with pytest.raises(ValueError):
        fixture.load_recorded_slice(path, "baseline")


def test_report_read_bound_before_allocation(source):
    path, _report, _values, _save = source
    path.write_bytes(b" " * (256 * 1024 + 1))
    with pytest.raises(ValueError, match="byte bound"):
        fixture.load_recorded_slice(path, "baseline")

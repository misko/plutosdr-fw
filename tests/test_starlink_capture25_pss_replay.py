"""Bounded synthetic admission/lifecycle tests; not capture or FPGA qualification."""

from __future__ import annotations

import json
import subprocess
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from tests.starlink_oracle import FixedMatchScoreStream
from tests.starlink_oracle.acquisition import PhaseMapTiles
from tools import starlink_capture25_pss_replay as replay


@pytest.fixture
def capture(tmp_path, monkeypatch):
    """Tiny synthetic manifest; no access to the named recording in unit tests."""
    root = tmp_path / "capture"
    root.mkdir()
    radio = root / f"radio-{replay.SERIAL}"
    radio.mkdir()
    monkeypatch.setattr(replay, "CAPTURE", root)
    monkeypatch.setattr(replay, "WINDOWS", {"negative": (5000, 6000), "positive": (15000, 16000)})
    settings = {"sample_rate_hz": 25_000_000, "bandwidth_hz": 25_000_000,
                "center_frequency_hz": 1_932_500_000, "receiver_ids": [0]}
    raw = np.arange(60_000, dtype=np.int16).reshape(-1, 2).tobytes()
    chunks = []
    for index in range(3):
        payload = raw[index * 40_000:(index + 1) * 40_000]
        path = radio / f"iq-{index:06d}.ci16.zst"
        path.write_bytes(payload)  # Deliberately identity codec in the loader stub.
        chunks.append({"chunk_index": index, "device_sample_start": index * 10000,
                       "sample_count": 10000, "content_kind": "observed",
                       "continuity_segment_index": 0, "sample_format": "ci16_le",
                       "sample_layout": "sample_receiver_iq", "schema_version": 1,
                       "relative_path": str(path.relative_to(root)),
                       "compressed_bytes": len(payload), "uncompressed_bytes": len(payload),
                       "compressed_sha256": "sha256:" + replay.sha256(payload),
                       "uncompressed_sha256": "sha256:" + replay.sha256(payload)})
    timeline = "sha256:" + "a" * 64
    gap = {"schema_version": 1, "stream_id": "stream-1", "first_device_sample_counter": 100,
           "timeline_sha256": timeline, "boundaries": []}
    inventory = {"schema_version": 1, "stream_id": "stream-1", "first_device_sample_counter": 100,
                 "timeline_sha256": timeline, "algorithm_version": "counter-authoritative-validity-v1",
                 "logical_sample_count": 30000,
                 "runs": [{"device_sample_start": 0, "sample_count": 30000,
                           "content_kind": "observed", "continuity_segment_index": 0}]}
    stream = {"schema_version": 3, "stream_id": "stream-1", "state": "partial",
              "error": "synthetic global degradation outside admitted interval",
              "radio": {"serial": replay.SERIAL, "radio_id": replay.RADIO_ID},
              "requested_settings": dict(settings), "applied_settings": dict(settings),
              "continuity": {"sample_loss_observable": True, "first_device_sample_counter": 100,
                             "validated_stream_generation": "123"},
              "logical_sample_count": 30000, "logical_iq_sha256": "sha256:" + "b" * 64,
              "timeline_sha256": timeline, "chunks": chunks}
    plan = {"radio_id": replay.RADIO_ID, "requested_settings": dict(settings),
            "starlink_edge": "upper", "starlink_channel": 4,
            "captured_if_start_hz": 1_920_000_000, "captured_if_stop_hz": 1_945_000_000,
            "channel_if_start_hz": 1_705_000_000, "channel_if_stop_hz": 1_945_000_000,
            "pilot_if_center_frequency_hz": 1_940_312_500,
            "profile_revision": {"profile": {"lnb_lo_hz": 9_750_000_000,
                                             "starlink_edge": "lower"}}}
    manifest = {"schema_version": 6, "session_id": root.name, "state": "degraded",
                "streams": [stream], "capture_plan": {"radio_plans": [plan]}}

    def save():
        for name, metadata in (("gap-map", gap), ("validity-inventory", inventory)):
            payload = json.dumps(metadata).encode()
            path = radio / (name + ".json")
            path.write_bytes(payload)
            key = name.replace("-", "_")
            stream[key + "_relative_path"] = str(path.relative_to(root))
            stream[key + "_sha256"] = "sha256:" + replay.sha256(payload)
            if name == "gap-map":
                inventory["gap_map_content_digest"] = stream["gap_map_sha256"]
        payload = json.dumps(manifest).encode()
        (root / "manifest.json").write_bytes(payload)
        monkeypatch.setattr(replay, "MANIFEST_SHA256", replay.sha256(payload))

    save()
    monkeypatch.setattr(replay, "decompress_chunk", lambda data, _size: data)
    return SimpleNamespace(root=root, radio=radio, manifest=manifest, stream=stream,
                           plan=plan, gap=gap, inventory=inventory, chunks=chunks,
                           raw=raw, save=save)


def test_admission_uses_resolved_upper_not_stale_profile_label(capture):
    provenance, chunks = replay.admit_capture("negative")
    assert [chunk["chunk_index"] for chunk in chunks] == [0, 1]
    assert provenance["continuity_segment_index"] == 0
    assert provenance["source_counter_start"] == 5100
    assert provenance["source_sample_axis"].startswith("stream-relative")
    assert provenance["manifest_state"] == "degraded"
    assert len(provenance["metadata_artifacts"]) == 3


@pytest.mark.parametrize(("owner", "key", "value"), [
    ("manifest", "schema_version", 5), ("manifest", "session_id", "other"),
    ("stream", "schema_version", 1), ("plan", "starlink_edge", "lower"),
    ("plan", "starlink_channel", 3), ("plan", "pilot_if_center_frequency_hz", 1),
    ("inventory", "first_device_sample_counter", 0),
    ("inventory", "timeline_sha256", "sha256:" + "c" * 64),
    ("inventory", "logical_sample_count", 1), ("gap", "stream_id", "stream-0"),
])
def test_rejects_metadata_mismatches(capture, owner, key, value):
    getattr(capture, owner)[key] = value
    capture.save()
    with pytest.raises(ValueError):
        replay.admit_capture("negative")


@pytest.mark.parametrize(("key", "value"), [
    ("sample_rate_hz", 15_000_000), ("center_frequency_hz", 1_717_500_000),
    ("receiver_ids", [0, 1]), ("bandwidth_hz", 20_000_000),
])
def test_rejects_actual_settings_mismatch(capture, key, value):
    capture.stream["applied_settings"][key] = value
    capture.save()
    with pytest.raises(ValueError, match="rate/RX0/applied IF LO"):
        replay.admit_capture("negative")


@pytest.mark.parametrize("kind", ["unobservable", "serial", "generation", "duplicate_stream", "duplicate_plan"])
def test_rejects_untrusted_origin_or_identity(capture, kind):
    if kind == "unobservable":
        capture.stream["continuity"]["sample_loss_observable"] = False
    elif kind == "serial":
        capture.stream["radio"]["serial"] = "other"
    elif kind == "generation":
        capture.stream["continuity"]["validated_stream_generation"] = None
    elif kind == "duplicate_stream":
        capture.manifest["streams"].append(capture.stream)
    else:
        capture.manifest["capture_plan"]["radio_plans"].append(capture.plan)
    capture.save()
    with pytest.raises(ValueError):
        replay.admit_capture("negative")


@pytest.mark.parametrize("kind", ["gap", "zero", "different_segment", "hole", "overlap", "unquantified"])
def test_rejects_discontinuity_including_halos(capture, kind):
    if kind in ("gap", "unquantified"):
        capture.gap["boundaries"] = [{"device_sample_offset": 10999,
                                      "missing_sample_count": 0 if kind == "unquantified" else 1}]
    elif kind == "zero":
        capture.chunks[1]["content_kind"] = "zero_fill"
    elif kind == "different_segment":
        capture.chunks[1]["continuity_segment_index"] = 1
    elif kind == "hole":
        capture.chunks[1]["device_sample_start"] += 1
    else:
        capture.chunks[1]["device_sample_start"] -= 1
    capture.save()
    with pytest.raises(ValueError):
        replay.admit_capture("negative")


def test_two_observed_islands_rejected_even_without_missing_samples(capture):
    capture.inventory["runs"] = [
        {"device_sample_start": 0, "sample_count": 10000, "content_kind": "observed",
         "continuity_segment_index": 0},
        {"device_sample_start": 10000, "sample_count": 20000, "content_kind": "observed",
         "continuity_segment_index": 1},
    ]
    capture.save()
    with pytest.raises(ValueError, match="one observed continuity island"):
        replay.admit_capture("negative")


@pytest.mark.parametrize("kind", ["format", "layout", "bytes", "size", "path", "hash"])
def test_bad_chunk_geometry_and_paths_fail_before_payload(capture, kind):
    fields = {"format": ("sample_format", "cf32"), "layout": ("sample_layout", "iq_receiver"),
              "bytes": ("uncompressed_bytes", 39996), "size": ("compressed_bytes", 2**30),
              "path": ("relative_path", "../other/iq-000000.ci16.zst"),
              "hash": ("compressed_sha256", "sha256:bad")}
    key, value = fields[kind]
    capture.chunks[0][key] = value
    capture.save()
    with pytest.raises(ValueError):
        replay.admit_capture("negative")


def test_reads_only_overlapping_chunks_and_binds_full_hashes(capture, monkeypatch):
    provenance, chunks = replay.admit_capture("negative")
    calls = []
    original = replay.read_capture

    def read(path, **kwargs):
        calls.append(path)
        return original(path, **kwargs)

    monkeypatch.setattr(replay, "read_capture", read)
    samples = replay.load_window(provenance, chunks)
    assert samples.shape == (11000, 2)
    assert samples.tobytes() == capture.raw[:44000]
    assert calls == [chunk["relative_path"] for chunk in chunks]
    assert len(provenance["verified_chunks"]) == 2
    assert provenance["halo_ci16_sha256"] == replay.sha256(samples.tobytes())


@pytest.mark.parametrize("kind", ["compressed", "uncompressed", "all_zero"])
def test_full_hash_mismatch_or_zero_observation_fails(capture, monkeypatch, kind):
    provenance, chunks = replay.admit_capture("negative")
    if kind == "compressed":
        (capture.radio / "iq-000000.ci16.zst").write_bytes(b"x" * 40000)
    elif kind == "uncompressed":
        monkeypatch.setattr(replay, "decompress_chunk", lambda data, _size: bytes(len(data)))
    else:
        zero = bytes(40000)
        (capture.radio / "iq-000000.ci16.zst").write_bytes(zero)
        chunks[0]["compressed_sha256"] = chunks[0]["uncompressed_sha256"] = "sha256:" + replay.sha256(zero)
    with pytest.raises(ValueError):
        replay.load_window(provenance, chunks)
    assert provenance["verified_chunks"] == []


def test_path_validation_rejects_symlink_and_never_calls_sudo(capture, monkeypatch, tmp_path):
    path = capture.radio / "iq-000000.ci16.zst"
    path.unlink()
    other = tmp_path / "other"
    other.write_bytes(b"secret")
    path.symlink_to(other)
    monkeypatch.setattr(replay.subprocess, "run", lambda *a, **k: pytest.fail("no sudo for aliases"))
    with pytest.raises(ValueError, match="non-aliased"):
        replay.read_capture(str(path.relative_to(capture.root)))


def test_permission_fallback_exact_path_no_shell(capture, monkeypatch):
    path = capture.radio / "iq-000000.ci16.zst"
    relative = str(path.relative_to(capture.root))
    original = Path.open

    def denied(self, *args, **kwargs):
        if self == path:
            raise PermissionError("test")
        return original(self, *args, **kwargs)

    def fake_run(command, **kwargs):
        assert command == ["sudo", "-n", "-u", "leo", "cat", "--", str(path)]
        assert "shell" not in kwargs and kwargs["timeout"] == 120
        return SimpleNamespace(stdout=capture.raw[:40000])

    monkeypatch.setattr(Path, "open", denied)
    monkeypatch.setattr(replay.subprocess, "run", fake_run)
    assert replay.read_capture(relative) == capture.raw[:40000]


@pytest.mark.parametrize("payload", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e309}'])
def test_json_fail_closed(payload):
    with pytest.raises(ValueError):
        replay.decode_json(payload)


def test_real_zstd_codec_small_bounded_case():
    payload = bytes(range(256)) * 32
    compressed = subprocess.run(["zstd", "--quiet", "--stdout"], input=payload,
                                capture_output=True, check=True).stdout
    assert replay.decompress_chunk(compressed, len(payload)) == payload
    with pytest.raises(ValueError, match="byte count"):
        replay.decompress_chunk(compressed, len(payload) - 1)


@pytest.mark.parametrize(("count", "blocks", "samples"), [(1, 1, 512), (447, 1, 512),
    (448, 2, 959), (1341, 3, 1406), (4800000, 10739, 4800398)])
def test_exact_fft_geometry_no_last_block_padding(count, blocks, samples):
    assert replay.fft_geometry(count) == (blocks, samples)
    assert samples - 65 == blocks * 447


def test_selects_absolute_canonical_origin_and_requires_all_fft_input():
    values = np.arange(3000, dtype=np.int16).reshape(-1, 2)
    conditioned = SimpleNamespace(samples_iq=values, first_canonical_index=2952)
    selected = replay.select_model_input(conditioned, 5000, 448)
    np.testing.assert_array_equal(selected, values[48:1007])
    with pytest.raises(ValueError, match="insufficient fully supported halo"):
        replay.select_model_input(conditioned, 5000, 1500)
    with pytest.raises(ValueError, match="canonical integer origin"):
        replay.select_model_input(conditioned, 5001, 1)


def test_cfo_absolute_phase_and_clip_reporting():
    samples = np.tile(np.array([[1000, 0]], dtype=np.int16), (128, 1))
    full, clips = replay.derotate_ci16(samples, 540000000, 285798.94603620283)
    piece, _ = replay.derotate_ci16(samples[31:93], 540000031, 285798.94603620283)
    np.testing.assert_array_equal(piece, full[31:93])
    np.testing.assert_array_equal(replay.derotate_ci16(samples, 540000000, 0)[0], samples)
    assert clips == 0
    loud = np.array([[32767, 32767]], dtype=np.int16)
    _, clips = replay.derotate_ci16(loud, 1, 1875000)
    assert clips == 1


@pytest.mark.parametrize("value", [float("inf"), float("nan"), 7500000, -7500000])
def test_invalid_cfo_before_directory_or_io(tmp_path, monkeypatch, value):
    output = tmp_path / "result"
    monkeypatch.setattr(replay, "admit_capture", lambda *_: pytest.fail("no source I/O"))
    with pytest.raises(ValueError, match="CFO"):
        replay.run("negative", output, value)
    assert not output.exists()


def test_width_bound_before_state_and_restored_on_error(monkeypatch, tmp_path):
    previous = replay.xfft_bitacc.XFFT_DATA_BITS, replay.xfft_bitacc.XFFT_FRACTION_BITS

    class FakeModel:
        def __init__(self, _directory):
            assert (replay.xfft_bitacc.XFFT_DATA_BITS, replay.xfft_bitacc.XFFT_FRACTION_BITS) == (18, 17)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

    monkeypatch.setattr(replay.xfft_bitacc, "XfftBitAccModel", FakeModel)
    with pytest.raises(RuntimeError), replay.model_q17(tmp_path):
        raise RuntimeError("test")
    assert (replay.xfft_bitacc.XFFT_DATA_BITS, replay.xfft_bitacc.XFFT_FRACTION_BITS) == previous


def test_real_installed_q17_kernel_equals_existing_memory_and_one_full_block(tmp_path):
    if not replay.xfft_bitacc.INSTALLED_CMODEL_ARCHIVE.is_file():
        pytest.skip("installed Vivado C model unavailable")
    directory = replay.xfft_bitacc.prepare_installed_cmodel(tmp_path / "model")
    coefficients = replay.quantize_q15(replay.projected_pss(15000000, "upper"))
    with replay.model_q17(directory) as model:
        kernel = replay.check_kernel(model, coefficients)
        assert kernel["exact_existing_kernel_match"]
        samples = np.random.default_rng(25).integers(-1000, 1000, (512, 2), dtype=np.int16)
        result = replay.xfft_bitacc.xfft_bitacc_match_scores(samples, coefficients, model)
        assert result.block_count == 1 and len(result.stream.scores) == 447
        assert result.kernel_sha256 == kernel["int32le_sha256"]


def test_kernel_width_and_golden_mismatch_rejected(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match="18-bit Q17"):
        replay.check_kernel(None, np.zeros((66, 2), dtype=np.int16))
    monkeypatch.setattr(replay.xfft_bitacc, "XFFT_DATA_BITS", 18)
    monkeypatch.setattr(replay.xfft_bitacc, "XFFT_FRACTION_BITS", 17)
    monkeypatch.setattr(replay.xfft_bitacc, "_template_kernel", lambda *_: np.zeros((512, 2), dtype=np.int32))
    with pytest.raises(ValueError, match="differs from existing"):
        replay.check_kernel(None, np.zeros((66, 2), dtype=np.int16))
    bad = tmp_path / "bad.mem"
    bad.write_text("000000000\n" * 511)
    monkeypatch.setattr(replay, "KERNEL", bad)
    with pytest.raises(ValueError, match="geometry"):
        replay.check_kernel(None, np.zeros((66, 2), dtype=np.int16))


def make_stream(count=447):
    return FixedMatchScoreStream(0, np.arange(count, dtype=np.uint32) % 256,
                                66, 12345, 512, float("nan"))


def test_all_three_maps_and_bounded_drift_with_finite_json(monkeypatch, tmp_path):
    values = np.full((3, 20000), 64, dtype=np.uint32)
    values[:, 123] = 1000
    tiles = PhaseMapTiles(values, np.array([0, 1280000, 2560000], dtype=np.int64),
                          1, 64, 20000, 8, 16, 0, 960000)
    monkeypatch.setattr(replay, "fold_phase_map_tiles", lambda *_: tiles)
    document = replay.describe_maps(make_stream(), tmp_path, "three")
    assert len(document["maps"]) == 3
    assert document["shape"] == [3, 20000]
    assert document["artifact"]["bytes"] == 120000
    assert document["combined_candidate"]["robust_z"] is None
    assert document["combined_candidate"]["robust_z_unbounded"]
    assert document["three_map_existing_epoch_gates_pass"]
    assert document["drift_bank_bins_per_tile"] == [-12, -8, -4, 0, 4, 8, 12]
    second = document["maps"][1]
    assert second["canonical_full_fft_dependency_start_index"] <= 1280000
    assert second["canonical_full_fft_dependency_stop_index"] >= 2560000 + 65
    assert second["source_full_fft_and_fir_dependency_start_index"] < 1280000 * 5 // 3
    json.dumps(document, allow_nan=False)
    monkeypatch.setattr(replay, "fold_phase_map_tiles", lambda *_: replace(tiles, maps=values[:1]))
    with pytest.raises(ValueError, match="exactly 3"):
        replay.describe_maps(make_stream(), tmp_path, "one")
    assert not (tmp_path / "one.maps.u16le").exists()


@pytest.mark.parametrize("conditioner_clips", [0, 1])
def test_model_scores_are_cropped_only_after_whole_blocks(monkeypatch, tmp_path, conditioner_clips):
    calls = []

    def score(samples, coefficients, model, *, first_sample_index):
        assert samples.shape == (512, 2) and first_sample_index == 0
        return SimpleNamespace(block_count=1, stream=make_stream(), kernel_sha256="k",
                               forward_overflow_blocks=0, inverse_overflow_blocks=0,
                               product_overflow_blocks=0, forward_block_exponents=(0,),
                               inverse_block_exponents=(1,))

    monkeypatch.setattr(replay.xfft_bitacc, "xfft_bitacc_match_scores", score)
    monkeypatch.setattr(replay, "describe_maps", lambda stream, *_: calls.append(len(stream.scores)) or {})
    document = replay.replay_variant(np.zeros((512, 2), dtype=np.int16), first_index=0,
                                     score_count=101, cfo_hz=0, model=None, coefficients=None,
                                     output=tmp_path, name="baseline", kernel={"int32le_sha256": "k"},
                                     conditioning_clipped_components=conditioner_clips)
    assert calls == [101, 101]
    assert document["discarded_extra_scores"] == 346
    assert document["zero_padded_input_blocks"] == 0
    assert document["negative_control"]["independent_rf_capture"] is False
    assert document["scores"]["bytes"] == 101
    assert document["numerical_qualification_pass"] is (conditioner_clips == 0)
    assert bool(document["qualification_errors"]) is (conditioner_clips != 0)


def test_existing_output_never_mutated_and_bad_cli_has_no_io(tmp_path, monkeypatch):
    output = tmp_path / "exists"
    output.mkdir()
    marker = output / "keep"
    marker.write_text("unchanged")
    monkeypatch.setattr(replay, "admit_capture", lambda *_: pytest.fail("no source I/O"))
    with pytest.raises(FileExistsError):
        replay.run("negative", output)
    with pytest.raises(SystemExit) as error:
        replay.main(["--window", "other", "--output", str(tmp_path / "new")])
    assert error.value.code == 2 and marker.read_text() == "unchanged"
    assert not (tmp_path / "new").exists()


def test_failed_admission_retains_strict_partial_receipt(tmp_path, monkeypatch):
    def fail(_window):
        raise ValueError("manifest digest mismatch")

    monkeypatch.setattr(replay, "admit_capture", fail)
    output = tmp_path / "failed"
    assert replay.run("negative", output) == 1
    report = replay.decode_json((output / "report.json").read_bytes())
    assert report["status"] == "FAILED_PARTIAL"
    assert report["stage"] == "admission" and report["variants"] == []
    assert report["hardware_qualified"] is False and report["lock_proven"] is False


def test_failed_assisted_preserves_baseline_and_conditioned_derivative(tmp_path, monkeypatch):
    provenance = {"source_halo_start_index": 0, "source_start_index": 5000,
                  "source_stop_index": 6000}
    monkeypatch.setattr(replay, "admit_capture", lambda _: (provenance, []))
    monkeypatch.setattr(replay, "load_window", lambda *_: np.zeros((11000, 2), dtype=np.int16))
    conditioned = SimpleNamespace(samples_iq=np.zeros((1200, 2), dtype=np.int16), clipped_components=0,
                                  first_canonical_index=2952, metadata=lambda: {"support": "test"})
    monkeypatch.setattr(replay, "condition_capture25", lambda *a, **k: conditioned)
    monkeypatch.setattr(replay.xfft_bitacc, "prepare_installed_cmodel", lambda p: p)

    @contextmanager
    def model(_path):
        yield None

    monkeypatch.setattr(replay, "model_q17", model)
    monkeypatch.setattr(replay, "check_kernel", lambda *_: {"int32le_sha256": "test"})

    def variant(*args, **kwargs):
        if kwargs["name"] == "assisted":
            raise ArithmeticError("injected second-model failure")
        return {"name": "baseline", "preserved": True}

    monkeypatch.setattr(replay, "replay_variant", variant)
    output = tmp_path / "partial"
    assert replay.run("negative", output, 285798.94603620283) == 1
    report = replay.decode_json((output / "report.json").read_bytes())
    assert report["status"] == "FAILED_PARTIAL" and report["stage"] == "assisted"
    assert report["variants"] == [{"name": "baseline", "preserved": True}]
    assert report["conditioned_ci16"]["first_canonical_index"] == 2952
    assert (output / "conditioned-15msps.ci16").stat().st_size == 4800

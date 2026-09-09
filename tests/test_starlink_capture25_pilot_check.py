"""Synthetic/mocked offline pilot-check lifecycle; never capture or RF access."""

import hashlib
import json
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from tests.starlink_oracle.pilot_ddc import PilotDdcOracle
from tools import starlink_capture25_pilot_check as check


class _Method(StrEnum):
    GLRT64 = "glrt64"


@dataclass(frozen=True)
class _Config:
    residual_cfo_min_hz: float = -400_000
    residual_cfo_max_hz: float = 400_000


@dataclass(frozen=True)
class _Score:
    method: _Method
    exact_score: float
    control_score: float
    margin: float
    residual_cfo_hz: float
    tracking_cfo_hz: float


class _Pilot:
    """Cheap source-lattice mock; real integer FIR is tested separately below."""

    def __init__(self, edge):
        assert edge == "upper"
        self.first = None
        self.next = None

    def process(self, iq, *, first_index):
        assert self.next is None or first_index == self.next
        self.next = first_index + len(iq)
        if self.first is None:
            self.first = first_index
        indexes = np.arange(first_index + (-first_index % 6), self.next, 6, dtype=np.uint64)
        return SimpleNamespace(samples_iq=np.zeros((len(indexes), 2), dtype=np.int16),
                               accepted_input_indexes=indexes,
                               support_valid=indexes >= self.first + 538,
                               saturation_events=0)


def _harness(tmp_path, monkeypatch, *, first=None, start=7_500_000):
    first = start - 3000 if first is None else first
    source = tmp_path / "canonical.ci16"
    source.write_bytes(bytes(4 * 4_806_000))
    output = tmp_path / "receipt.json"
    leo = tmp_path / "leo-source"
    base = leo / "src/leo/analysis/starlink"
    base.mkdir(parents=True)
    modules = {}
    for name in ("leo", "leo.analysis", "leo.analysis.starlink",
                 "leo.analysis.starlink.templates", "leo.analysis.starlink.acquisition",
                 "leo.analysis.starlink.pilot_methods"):
        module = ModuleType(name)
        module.__path__ = []
        filename = base / (name.rsplit(".", 1)[-1] + ".py")
        filename.write_text("# Synthetic module provenance fixture, not a numerical oracle.\n")
        module.__file__ = str(filename)
        modules[name] = module
        monkeypatch.setitem(sys.modules, name, module)
    acquisition = modules["leo.analysis.starlink.acquisition"]
    methods = modules["leo.analysis.starlink.pilot_methods"]
    acquisition.SymbolwiseAcquisitionConfig = _Config
    acquisition.ReceiverFrequencyCalibration = lambda *args: args
    calls = []

    def acquire(values, rate, calibration, *, edge, config):
        assert len(values) == 50_000 and rate == 2_500_000 and edge == "upper"
        assert calibration[1] == 0 and config == _Config()
        calls.append((len(values), rate, calibration))
        return SimpleNamespace(status="complete", candidates=(
            SimpleNamespace(refined_epoch_sample=0, absolute_cfo_hz=-123.0),
            SimpleNamespace(refined_epoch_sample=333, absolute_cfo_hz=456.0)))

    def scores(values, rate, *, edge, epoch_samples, acquired_cfo_hz):
        assert epoch_samples == [0, 333] and acquired_cfo_hz == [-123.0, 456.0]
        return (_Score(_Method.GLRT64, .02, .03, -.01, -1, -124),
                _Score(_Method.GLRT64, .51, .03, .48, 2, 458))

    acquisition.acquire_symbolwise = acquire
    methods.conditioned_glrt64_scores = scores
    monkeypatch.setattr(check, "PilotDdcOracle", _Pilot)
    monkeypatch.setattr(sys, "argv", ["pilot-check", "--canonical-ci16", str(source),
        "--first-canonical-index", str(first), "--start-canonical-index", str(start),
        "--leo-source", str(leo), "--output", str(output)])
    return SimpleNamespace(source=source, output=output, leo=leo, first=first, start=start,
                           modules=modules, acquisition=acquisition, methods=methods, calls=calls)


@pytest.mark.parametrize("start", [7_500_000, 7_500_001, 540_000_000])
def test_exact_absolute_center_lattice_rational_coordinates_and_score_schema(tmp_path, monkeypatch, start):
    radio = _harness(tmp_path, monkeypatch, start=start)
    check.main()
    result = json.loads(radio.output.read_text())
    first_center = start + ((1 - start) % 6)
    assert result["first_pilot_canonical_center"] == first_center
    assert result["last_pilot_canonical_center"] == first_center + 799_999 * 6
    assert result["pilot_samples"] == 800_000
    assert result["group_delay_already_removed_canonical_samples"] == 269
    assert len(radio.calls) == 3
    assert not result["hardware_access"] and not result["pss_seeds_used"]
    assert result["source_ci16_sha256"] == hashlib.sha256(radio.source.read_bytes()).hexdigest()
    assert result["declared_probe_offsets"] == [0, 250_000, 500_000]
    for row, offset in zip(result["probes"], (0, 250_000, 500_000), strict=True):
        assert row["pilot_offset"] == offset and row["sample_count"] == 50_000
        assert row["canonical_center_start"] == first_center + 6 * offset
        assert len(row["candidates"]) == 2  # Negative scores are not discarded.
        for candidate, epoch in zip(row["candidates"], (0, 333), strict=True):
            center = first_center + 6 * (offset + epoch)
            assert candidate["frame_start_canonical_center"] == center
            assert candidate["frame_start_original25_sample_numerator"] == 5 * center
            assert candidate["frame_start_original25_sample_denominator"] == 3
            assert candidate["phase_us_mod_750hz"] == (center % 20_000) / 15
            assert candidate["method"] == "glrt64"
        assert row["best"] == row["candidates"][1]


def test_empty_acquisition_is_retained_without_fabricating_best_candidate(tmp_path, monkeypatch):
    radio = _harness(tmp_path, monkeypatch)
    radio.acquisition.acquire_symbolwise = lambda *args, **kwargs: SimpleNamespace(
        status="no_result", candidates=())
    radio.methods.conditioned_glrt64_scores = lambda *args, **kwargs: ()
    check.main()
    result = json.loads(radio.output.read_text())
    assert all(row["best"] is None and row["candidates"] == [] and
               row["acquisition_status"] == "no_result" for row in result["probes"])


def test_existing_output_is_not_overwritten(tmp_path, monkeypatch):
    radio = _harness(tmp_path, monkeypatch)
    radio.output.write_text("original evidence")
    with pytest.raises(SystemExit):
        check.main()
    assert radio.output.read_text() == "original evidence" and not radio.calls


@pytest.mark.parametrize("first_delta", [-100, -537, 99])
def test_insufficient_halo_rejected_before_any_numerical_probe(tmp_path, monkeypatch, first_delta):
    radio = _harness(tmp_path, monkeypatch, first=7_500_000 + first_delta)
    with pytest.raises(SystemExit):
        check.main()
    assert not radio.calls and not radio.output.exists()


def test_missing_input_never_creates_success_receipt(tmp_path, monkeypatch):
    radio = _harness(tmp_path, monkeypatch)
    radio.source.unlink()
    with pytest.raises((FileNotFoundError, SystemExit)):
        check.main()
    assert not radio.calls
    if radio.output.exists():
        assert json.loads(radio.output.read_text()).get("status") != "complete"


def test_real_integer_oracle_support_index_names_latest_not_center():
    first = 7_499_000
    raw = np.zeros((2000, 2), dtype=np.int16)
    result = PilotDdcOracle("upper").process(raw, first_index=first)
    accepted = result.accepted_input_indexes
    assert np.all(accepted % 6 == 0)
    centers = accepted.astype(np.int64) - 269
    assert np.all(centers % 6 == 1)
    assert np.all(centers[result.support_valid] - 269 >= first)
    assert np.all(centers[result.support_valid] + 269 < first + len(raw))
    assert result.saturation_events == 0


@pytest.mark.parametrize("failure_type", [RuntimeError, KeyboardInterrupt])
def test_late_numerical_failure_keeps_completed_probes_and_rethrows(tmp_path, monkeypatch, failure_type):
    radio = _harness(tmp_path, monkeypatch)
    original = radio.acquisition.acquire_symbolwise

    def fail(*args, **kwargs):
        if len(radio.calls) == 2:
            raise failure_type("late numerical failure")
        return original(*args, **kwargs)

    radio.acquisition.acquire_symbolwise = fail
    with pytest.raises(failure_type):
        check.main()
    receipt = json.loads(radio.output.read_text())
    assert receipt["status"] == "failed" and len(receipt["probes"]) == 2
    assert receipt["error"]["type"] == failure_type.__name__
    assert receipt["pilot_samples"] == 800_000 and receipt["pilot_ci16_sha256"]
    assert receipt["source_sha256"] and not receipt["hardware_access"]


@pytest.mark.parametrize("name", ["templates", "acquisition", "pilot_methods"])
def test_cached_other_checkout_module_is_rejected_before_numerical_processing(tmp_path, monkeypatch, name):
    radio = _harness(tmp_path, monkeypatch)
    wrong = tmp_path / "wrong-checkout.py"
    wrong.write_text("# Wrong imported module\n")
    radio.modules["leo.analysis.starlink." + name].__file__ = str(wrong)
    with pytest.raises(ValueError, match="explicit checkout"):
        check.main()
    assert not radio.calls and not radio.output.exists()


def test_actual_loaded_native_extension_is_recorded_without_assumed_checkout_path(tmp_path, monkeypatch):
    radio = _harness(tmp_path, monkeypatch)
    name = "leo.analysis.starlink._native_acquisition"
    module = ModuleType(name)
    filename = tmp_path / ("_native_acquisition" + check.EXTENSION_SUFFIXES[0])
    filename.write_bytes(b"synthetic native provenance fixture")
    module.__file__ = str(filename)
    monkeypatch.setitem(sys.modules, name, module)
    radio.acquisition._native_acquisition = module
    check.main()
    receipt = json.loads(radio.output.read_text())
    assert receipt["loaded_native_modules"] == {name: {
        "path": str(filename), "sha256": hashlib.sha256(filename.read_bytes()).hexdigest()}}


def test_loaded_backend_without_native_file_provenance_is_not_silently_python_only(tmp_path, monkeypatch):
    radio = _harness(tmp_path, monkeypatch)
    radio.acquisition._native_acquisition = SimpleNamespace(__name__="missing_native")
    with pytest.raises(ValueError, match="backend lacks"):
        check.main()
    assert not radio.calls


def test_loaded_source_change_fails_final_receipt_without_losing_rows(tmp_path, monkeypatch):
    radio = _harness(tmp_path, monkeypatch)
    original = radio.acquisition.acquire_symbolwise

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        if len(radio.calls) == 3:
            Path(radio.acquisition.__file__).write_text("# Changed while numerical work ran\n")
        return result

    radio.acquisition.acquire_symbolwise = changed
    with pytest.raises(ValueError, match="source changed"):
        check.main()
    receipt = json.loads(radio.output.read_text())
    assert receipt["status"] == "failed" and len(receipt["probes"]) == 3


def test_oversized_input_is_rejected_from_stat_before_open(tmp_path, monkeypatch):
    source = tmp_path / "oversized.ci16"
    with source.open("wb") as output:
        output.truncate(check.MAX_CANONICAL_SAMPLES * 4 + 4)

    def forbidden(*args, **kwargs):
        raise AssertionError("oversized input must not be opened or allocated")

    monkeypatch.setattr(Path, "open", forbidden)
    with pytest.raises(ValueError, match="bounded"):
        check._bounded_input(source)


def test_input_growth_during_read_stays_bounded_and_is_rejected(tmp_path, monkeypatch):
    source = tmp_path / "changing.ci16"
    source.write_bytes(bytes(check.ANALYSIS_SAMPLES * 4))

    class Changed:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, count):
            assert count == check.MAX_CANONICAL_SAMPLES * 4 + 1
            return bytes(count)

    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: Changed())
    with pytest.raises(ValueError, match="size changed"):
        check._bounded_input(source)


def test_signed_index_overflow_rejected_before_oracle_allocation(tmp_path, monkeypatch):
    radio = _harness(tmp_path, monkeypatch, start=check.SIGNED_INDEX_LIMIT - 10)
    with pytest.raises(SystemExit):
        check.main()
    assert not radio.calls and not radio.output.exists()


@pytest.mark.parametrize("kind", ["saturation", "wrong-lattice"])
def test_bad_pilot_stream_never_reaches_glrt_and_is_retained(tmp_path, monkeypatch, kind):
    radio = _harness(tmp_path, monkeypatch)

    class Bad(_Pilot):
        def process(self, *args, **kwargs):
            result = super().process(*args, **kwargs)
            if kind == "saturation":
                result.saturation_events = 1
            else:
                result.accepted_input_indexes += 1
            return result

    monkeypatch.setattr(check, "PilotDdcOracle", Bad)
    with pytest.raises(RuntimeError):
        check.main()
    receipt = json.loads(radio.output.read_text())
    assert receipt["status"] == "failed" and not receipt["probes"] and not radio.calls


def test_nonfinite_score_does_not_leave_partial_json_or_count_incomplete_probe(tmp_path, monkeypatch):
    radio = _harness(tmp_path, monkeypatch)
    radio.methods.conditioned_glrt64_scores = lambda *args, **kwargs: (
        _Score(_Method.GLRT64, float("nan"), .1, .1, 0, 0),
        _Score(_Method.GLRT64, .2, .1, .1, 0, 0))
    with pytest.raises(ValueError):
        check.main()
    receipt = json.loads(radio.output.read_text())
    assert receipt["status"] == "failed" and receipt["probes"] == []


def test_receipt_encoding_precedes_creation_and_exclusive_open_never_overwrites(tmp_path):
    path = tmp_path / "receipt.json"
    with pytest.raises(ValueError):
        check._write_receipt(path, {"nonfinite": float("nan")})
    assert not path.exists()
    path.write_text("existing")
    with pytest.raises(FileExistsError):
        check._write_receipt(path, {"status": "complete"})
    assert path.read_text() == "existing"

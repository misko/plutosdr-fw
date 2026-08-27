"""Adversarial offline oracles for RC21 tandem measurement boundaries."""

from __future__ import annotations

import hashlib
import os
import stat
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from . import tandem_quality
from .experiment import EvidenceInvalid
from .metadata_abi import (
    FLAG_DEVICE_IIO_OVERFLOW,
    TandemEventDirection,
    TandemFrameMetadata,
    TandemGainEvent,
    TandemGainTable,
    TandemState,
)
from .tandem_quality import (
    _ACTIVE_MATRIX_FAILURE_IQ,
    _ACTIVE_TANDEM_SESSION,
    TandemQualityOptions,
    _capture_tandem,
    _DeferredTandemWrites,
    _EvidenceInvalidWithDetails,
    _MatrixFailureIqLedger,
    _measure_tandem,
    _metadata_dict,
    _run_mode,
    _TandemCaptureSession,
    _TandemContinuity,
    _validate_tandem_continuity,
)


def _options(output_dir: Path, **overrides: object) -> TandemQualityOptions:
    values: dict[str, object] = {
        "tx_gain_trajectory_db": (-60.0, -30.0, -60.0),
        "physical_attenuation_db": 0.0,
        "samples_per_channel": 8_192,
        "kernel_buffers": 1,
        "stable_frames": 2,
        "measurement_frames": 2,
        "max_settle_frames": 8,
        "settle_timeout_seconds": 2.0,
        "tandem_power_measurement_samples": 1_024,
        "tandem_cooldown_periods": 16,
        "output_dir": output_dir,
    }
    values.update(overrides)
    return TandemQualityOptions(**values)  # type: ignore[arg-type]


def _metadata(
    options: TandemQualityOptions,
    sequence: int,
    *,
    transition_count: int = 0,
    gain: int = 50,
    event_sequence: int | None = None,
    direction: TandemEventDirection = TandemEventDirection.DECREASE,
) -> TandemFrameMetadata:
    events: tuple[TandemGainEvent, ...] = ()
    if event_sequence is not None:
        events = (
            TandemGainEvent(
                sample_sequence=(sequence * options.samples_per_channel + 100),
                event_sequence=event_sequence,
                flags=(int(direction) << 4) | 4,
                rx1_gain_index=gain,
                rx2_gain_index=gain,
            ),
        )
    return TandemFrameMetadata(
        version=5,
        header_bytes=0,
        features=0,
        flags=0,
        stream_id=17,
        buffer_sequence=sequence,
        first_sample_sequence=sequence * options.samples_per_channel,
        samples_per_channel=options.samples_per_channel,
        iq_payload_bytes=options.samples_per_channel * 8,
        enabled_scan_mask=0x0F,
        sample_format=0,
        channel_count=2,
        observation_count=0,
        observation_capacity=64,
        event_count=len(events),
        event_capacity=64,
        observation_overflow_count=0,
        event_overflow_count=0,
        ownership_epoch=23,
        tandem_state=TandemState.ARMED_AUTO,
        tandem_fault_flags=0,
        tandem_transition_count=transition_count,
        gain_table_id=TandemGainTable.MHZ_200_1300,
        threshold_provenance=0,
        minimum_gain_db=0,
        maximum_gain_db=62,
        initial_gain_db=40,
        minimum_gain_index=0,
        maximum_gain_index=62,
        rx1_gain_index=gain,
        rx2_gain_index=gain,
        ad9361_temperature_mdeg_c=35_000,
        gain_events=events,
    )


def _seed_continuity(
    options: TandemQualityOptions,
    session: _TandemCaptureSession,
    metadata: TandemFrameMetadata,
) -> None:
    frame = {
        "capture_ordinal": -1,
        "capture_stage": "seed_settle",
        "metadata": _metadata_dict(metadata),
    }
    _validate_tandem_continuity(
        metadata,
        frame,
        options=options,
        continuity=session.continuity,
    )


class _SequenceRadio:
    def __init__(
        self,
        options: TandemQualityOptions,
        frames: list[TandemFrameMetadata],
    ) -> None:
        self.options = options
        self.frames = list(frames)
        self.capture_count = 0

    def capture_iq(
        self,
        _buffer: object,
        *,
        metadata: bool,
        samples_per_channel: int,
    ) -> tuple[bytes, TandemFrameMetadata, int]:
        assert metadata is True
        assert samples_per_channel == self.options.samples_per_channel
        parsed = self.frames.pop(0)
        self.capture_count += 1
        return (
            bytes(samples_per_channel * 8),
            parsed,
            self.capture_count,
        )


class _RunModeRadio:
    def __init__(self) -> None:
        self.in_buffer = False

    def mute_all(self) -> None:
        pass

    def configure_rx(self, *_args: object, **_kwargs: object) -> None:
        pass

    def arm_tx2_tone(self, **_kwargs: object) -> None:
        pass

    def set_tx2_gain(self, gain_db: float) -> float:
        return float(gain_db)

    @contextmanager
    def buffer(self, *_args: object, **_kwargs: object):
        self.in_buffer = True
        try:
            yield object(), 5
        finally:
            self.in_buffer = False


def test_adjacent_frames_cannot_hide_a_transition(tmp_path: Path) -> None:
    options = _options(tmp_path)
    continuity = _TandemContinuity()
    first = _metadata(options, 0)
    _validate_tandem_continuity(
        first,
        {"metadata": _metadata_dict(first)},
        options=options,
        continuity=continuity,
    )
    hidden = _metadata(options, 1, transition_count=1, gain=49)
    hidden_frame = {"metadata": _metadata_dict(hidden)}

    with pytest.raises(
        EvidenceInvalid, match="adjacent tandem frames lost transition event evidence"
    ):
        _validate_tandem_continuity(
            hidden,
            hidden_frame,
            options=options,
            continuity=continuity,
        )
    assert hidden_frame["continuity"] == {
        "buffer_delta": 1,
        "sample_delta": options.samples_per_channel,
        "missing_frame_count": 0,
        "transition_count_delta": 1,
        "visible_event_count": 0,
        "hidden_transition_count": 1,
        "initial_unrepresented_transition_count": 0,
    }


def test_gap_hidden_transition_is_bounded_and_only_accounted(tmp_path: Path) -> None:
    options = _options(tmp_path)
    continuity = _TandemContinuity()
    first = _metadata(options, 0)
    _validate_tandem_continuity(
        first,
        {"metadata": _metadata_dict(first)},
        options=options,
        continuity=continuity,
    )
    frame: dict[str, object] = {
        "metadata": _metadata_dict(_metadata(options, 2, transition_count=1, gain=49))
    }
    _validate_tandem_continuity(
        _metadata(options, 2, transition_count=1, gain=49),
        frame,  # type: ignore[arg-type]
        options=options,
        continuity=continuity,
    )

    assert frame["continuity"] == {
        "buffer_delta": 2,
        "sample_delta": 2 * options.samples_per_channel,
        "missing_frame_count": 1,
        "transition_count_delta": 1,
        "visible_event_count": 0,
        "hidden_transition_count": 1,
        "initial_unrepresented_transition_count": 0,
        "cumulative_missing_frame_count": 1,
        "cumulative_hidden_transition_count": 1,
        "cumulative_event_sequence_hole_count": 0,
    }

    capacity_continuity = _TandemContinuity()
    _validate_tandem_continuity(
        first,
        {"metadata": _metadata_dict(first)},
        options=options,
        continuity=capacity_continuity,
    )
    impossible = _metadata(options, 2, transition_count=2, gain=50)
    with pytest.raises(EvidenceInvalid, match="more hidden transitions"):
        _validate_tandem_continuity(
            impossible,
            {"metadata": _metadata_dict(impossible)},
            options=options,
            continuity=capacity_continuity,
        )


def test_invalid_capture_retains_raw_prior_current_and_pending_cell(
    tmp_path: Path,
) -> None:
    options = _options(tmp_path)
    base = _metadata(options, 0)
    invalid = replace(
        _metadata(options, 1),
        flags=FLAG_DEVICE_IIO_OVERFLOW,
    )
    radio = _SequenceRadio(options, [invalid])
    session = _TandemCaptureSession(output_dir=tmp_path)
    matrix_ledger = _MatrixFailureIqLedger(
        output_dir=tmp_path,
        planned_accepted_frames=1,
        expected_frame_bytes=options.samples_per_channel * 8,
    )
    pending_cell = {"level_index": 0, "tx2_gain_requested_db": -60.0}
    session.begin_cell(0, pending_cell)
    _seed_continuity(options, session, base)

    matrix_token = _ACTIVE_MATRIX_FAILURE_IQ.set(matrix_ledger)
    try:
        with pytest.raises(_EvidenceInvalidWithDetails, match="unsafe flags") as caught:
            _capture_tandem(
                radio,  # type: ignore[arg-type]
                object(),
                options=options,
                session=session,
            )
    finally:
        _ACTIVE_MATRIX_FAILURE_IQ.reset(matrix_token)

    evidence = caught.value.failure_evidence
    assert evidence["kind"] == "tandem_capture_invalid"
    assert evidence["prior_frame"]["metadata"]["buffer_sequence"] == 0
    assert evidence["current_frame"]["metadata"]["buffer_sequence"] == 1
    assert evidence["pending_cell"] is pending_cell
    assert "diagnostic_iq_path" not in evidence["current_frame"]
    assert matrix_ledger.current is not None
    assert matrix_ledger.current.frame is evidence["current_frame"]
    assert matrix_ledger.current.role == "offending_capture"
    session.deferred.flush()
    diagnostic = tmp_path / evidence["current_frame"]["diagnostic_iq_path"]
    assert diagnostic.read_bytes() == bytes(options.samples_per_channel * 8)


def test_fatal_tandem_continuity_failure_remains_in_matrix_ledger(
    tmp_path: Path,
) -> None:
    options = _options(tmp_path)
    base = _metadata(options, 0)
    # An adjacent transition without its event cannot be authorized.
    invalid = _metadata(options, 1, transition_count=1, gain=49)
    radio = _SequenceRadio(options, [invalid])
    session = _TandemCaptureSession(output_dir=tmp_path)
    session.begin_cell(0, {"level_index": 0})
    _seed_continuity(options, session, base)
    matrix_ledger = _MatrixFailureIqLedger(
        output_dir=tmp_path,
        planned_accepted_frames=1,
        expected_frame_bytes=options.samples_per_channel * 8,
    )

    matrix_token = _ACTIVE_MATRIX_FAILURE_IQ.set(matrix_ledger)
    try:
        with pytest.raises(
            _EvidenceInvalidWithDetails,
            match="lost transition event evidence",
        ) as caught:
            _capture_tandem(
                radio,  # type: ignore[arg-type]
                object(),
                options=options,
                session=session,
            )
    finally:
        _ACTIVE_MATRIX_FAILURE_IQ.reset(matrix_token)

    evidence = caught.value.failure_evidence
    assert evidence["kind"] == "tandem_metadata_continuity_invalid"
    assert matrix_ledger.current is not None
    assert matrix_ledger.current.frame is evidence["current_frame"]
    assert matrix_ledger.current.role == "offending_capture"


def test_capture_failure_retains_every_earlier_iq_in_abandoned_attempt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    options = _options(tmp_path, measurement_frames=2)
    base = _metadata(options, 0)
    invalid = replace(_metadata(options, 2), flags=FLAG_DEVICE_IIO_OVERFLOW)
    radio = _SequenceRadio(options, [_metadata(options, 1), invalid])
    session = _TandemCaptureSession(output_dir=tmp_path)
    pending_cell = {"level_index": 0, "tx2_gain_requested_db": -60.0}
    session.begin_cell(0, pending_cell)
    _seed_continuity(options, session, base)
    monkeypatch.setattr(
        "tests.radio_hardware.tandem_quality.analyze_common_tone",
        lambda *_args, **_kwargs: {
            "quality_valid": True,
            "quality_reasons": [],
        },
    )
    token = _ACTIVE_TANDEM_SESSION.set(session)
    try:
        with pytest.raises(_EvidenceInvalidWithDetails, match="unsafe flags") as caught:
            _measure_tandem(
                radio,  # type: ignore[arg-type]
                object(),
                options=options,
                output_dir=tmp_path,
                level_index=0,
                settled=base,
            )
    finally:
        _ACTIVE_TANDEM_SESSION.reset(token)

    accepted = caught.value.failure_evidence["capture_trace"][0]
    offending = caught.value.failure_evidence["current_frame"]
    assert "diagnostic_iq_path" not in accepted
    assert "diagnostic_iq_path" not in offending
    session.deferred.flush()
    accepted_path = tmp_path / accepted["diagnostic_iq_path"]
    offending_path = tmp_path / offending["diagnostic_iq_path"]
    expected = bytes(options.samples_per_channel * 8)
    assert accepted_path.read_bytes() == expected
    assert offending_path.read_bytes() == expected


def test_transition_discards_whole_attempt_and_restarts_frame_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    options = _options(tmp_path)
    base = _metadata(options, 0)
    frames = [
        _metadata(options, 1),
        _metadata(options, 2, transition_count=1, gain=49, event_sequence=1),
        _metadata(options, 3, transition_count=1, gain=49),
        _metadata(options, 4, transition_count=1, gain=49),
        _metadata(options, 5, transition_count=1, gain=49),
        _metadata(options, 6, transition_count=1, gain=49),
    ]
    radio = _SequenceRadio(options, frames)
    session = _TandemCaptureSession(output_dir=tmp_path)
    matrix_ledger = _MatrixFailureIqLedger(
        output_dir=tmp_path,
        planned_accepted_frames=options.measurement_frames,
        expected_frame_bytes=options.samples_per_channel * 8,
    )
    pending_cell = {"level_index": 0, "tx2_gain_requested_db": -60.0}
    session.begin_cell(0, pending_cell)
    _seed_continuity(options, session, base)
    analyzed_thresholds: list[float] = []

    def fake_analyze(
        *_args: object, thresholds, **_kwargs: object
    ) -> dict[str, object]:
        analyzed_thresholds.append(float(thresholds.min_tone_snr_db))
        return {"quality_valid": True, "quality_reasons": []}

    monkeypatch.setattr(
        "tests.radio_hardware.tandem_quality.analyze_common_tone", fake_analyze
    )
    token = _ACTIVE_TANDEM_SESSION.set(session)
    matrix_token = _ACTIVE_MATRIX_FAILURE_IQ.set(matrix_ledger)
    try:
        measurements = _measure_tandem(
            radio,  # type: ignore[arg-type]
            object(),
            options=options,
            output_dir=tmp_path,
            level_index=0,
            settled=base,
        )
        assert (
            "diagnostic_iq_path"
            not in session.measurement_attempts[0]["offending_frame"]
        )
        assert (
            "diagnostic_iq_path"
            not in session.measurement_attempts[0]["accepted_frames_before_transition"][
                0
            ]
        )
    finally:
        _ACTIVE_MATRIX_FAILURE_IQ.reset(matrix_token)
        _ACTIVE_TANDEM_SESSION.reset(token)

    assert [frame["metadata"]["buffer_sequence"] for frame in measurements] == [
        5,
        6,
    ]
    assert [
        frame["metadata"]["buffer_sequence"] for frame in session.cell_capture_trace
    ] == [1, 2, 3, 4, 5, 6]
    assert [
        frame["metadata"]["buffer_sequence"] for frame in session.recovery_settle_trace
    ] == [3, 4]
    assert [item["status"] for item in session.measurement_attempts] == [
        "rejected_transition",
        "accepted",
    ]
    abandoned = session.measurement_attempts[0]["accepted_frames_before_transition"]
    assert [frame["metadata"]["buffer_sequence"] for frame in abandoned] == [1]
    assert analyzed_thresholds == [10.0, 10.0, 10.0]
    # Simulate an overall matrix PASS: the general failure-only ledger is
    # discarded, while recovered-transition detail remains authorizing and is
    # still materialized after the tandem buffer has closed.
    matrix_ledger.discard()
    session.deferred.flush()
    diagnostic_path = (
        tmp_path
        / session.measurement_attempts[0]["offending_frame"]["diagnostic_iq_path"]
    )
    abandoned_path = (
        tmp_path
        / session.measurement_attempts[0]["accepted_frames_before_transition"][0][
            "diagnostic_iq_path"
        ]
    )
    assert diagnostic_path.read_bytes() == bytes(options.samples_per_channel * 8)
    assert abandoned_path.read_bytes() == bytes(options.samples_per_channel * 8)
    assert (
        hashlib.sha256(diagnostic_path.read_bytes()).hexdigest()
        == (session.measurement_attempts[0]["offending_frame"]["sha256"])
    )
    assert (
        hashlib.sha256(abandoned_path.read_bytes()).hexdigest()
        == (
            session.measurement_attempts[0]["accepted_frames_before_transition"][0][
                "sha256"
            ]
        )
    )
    assert not (tmp_path / "failure-iq").exists()
    assert not (tmp_path / "failure-iq-manifest.json").exists()


def test_retry_exhaustion_preserves_prior_current_and_pending_cell(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    options = _options(tmp_path)
    base = _metadata(options, 0)
    radio = _SequenceRadio(
        options,
        [
            _metadata(options, 1),
            _metadata(options, 2, transition_count=1, gain=49, event_sequence=1),
            _metadata(options, 3, transition_count=1, gain=49),
            _metadata(options, 4, transition_count=1, gain=49),
            _metadata(options, 5, transition_count=2, gain=48, event_sequence=2),
        ],
    )
    session = _TandemCaptureSession(output_dir=tmp_path)
    matrix_ledger = _MatrixFailureIqLedger(
        output_dir=tmp_path,
        planned_accepted_frames=options.measurement_frames * 2,
        expected_frame_bytes=options.samples_per_channel * 8,
    )
    pending_cell = {"level_index": 0, "tx2_gain_requested_db": -60.0}
    session.begin_cell(0, pending_cell)
    _seed_continuity(options, session, base)
    monkeypatch.setattr(
        "tests.radio_hardware.tandem_quality.analyze_common_tone",
        lambda *_args, **_kwargs: {
            "quality_valid": True,
            "quality_reasons": [],
        },
    )
    token = _ACTIVE_TANDEM_SESSION.set(session)
    matrix_token = _ACTIVE_MATRIX_FAILURE_IQ.set(matrix_ledger)
    try:
        with pytest.raises(
            _EvidenceInvalidWithDetails, match="recovery was exhausted"
        ) as caught:
            _measure_tandem(
                radio,  # type: ignore[arg-type]
                object(),
                options=options,
                output_dir=tmp_path,
                level_index=0,
                settled=base,
            )
    finally:
        _ACTIVE_MATRIX_FAILURE_IQ.reset(matrix_token)
        _ACTIVE_TANDEM_SESSION.reset(token)

    evidence = caught.value.failure_evidence
    assert evidence["kind"] == "tandem_measurement_transition_retry_exhausted"
    assert evidence["pending_cell"] is pending_cell
    assert [
        frame["metadata"]["buffer_sequence"]
        for frame in evidence["pending_cell"]["settling"]["trace"]
    ] == [3, 4]
    assert evidence["prior_frame"]["metadata"]["buffer_sequence"] == 4
    assert evidence["current_frame"]["metadata"]["buffer_sequence"] == 5
    assert [
        frame["metadata"]["buffer_sequence"] for frame in evidence["capture_trace"]
    ] == [1, 2, 3, 4, 5]
    assert len(evidence["measurement_attempts"]) == 2
    assert matrix_ledger.current is not None
    assert matrix_ledger.current.frame is evidence["current_frame"]
    assert matrix_ledger.current.role == "offending_capture"


def test_abandoned_batch_overflow_keeps_accepted_and_current_matrix_iq(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    options = _options(tmp_path, measurement_frames=3)
    frame_bytes = options.samples_per_channel * 8
    base = _metadata(options, 0)
    invalid = replace(_metadata(options, 3), flags=FLAG_DEVICE_IIO_OVERFLOW)
    radio = _SequenceRadio(
        options,
        [_metadata(options, 1), _metadata(options, 2), invalid],
    )
    session = _TandemCaptureSession(output_dir=tmp_path)
    session.deferred.maximum_bytes = frame_bytes * 2
    session.begin_cell(0, {"level_index": 0})
    _seed_continuity(options, session, base)
    matrix_ledger = _MatrixFailureIqLedger(
        output_dir=tmp_path,
        planned_accepted_frames=options.measurement_frames,
        expected_frame_bytes=frame_bytes,
    )
    monkeypatch.setattr(
        tandem_quality,
        "analyze_common_tone",
        lambda *_args, **_kwargs: {
            "quality_valid": True,
            "quality_reasons": [],
        },
    )

    session_token = _ACTIVE_TANDEM_SESSION.set(session)
    matrix_token = _ACTIVE_MATRIX_FAILURE_IQ.set(matrix_ledger)
    try:
        with pytest.raises(
            _EvidenceInvalidWithDetails,
            match="in-memory bound",
        ) as caught:
            _measure_tandem(
                radio,  # type: ignore[arg-type]
                object(),
                options=options,
                output_dir=tmp_path,
                level_index=0,
                settled=base,
            )
    finally:
        _ACTIVE_MATRIX_FAILURE_IQ.reset(matrix_token)
        _ACTIVE_TANDEM_SESSION.reset(session_token)

    # The invalid current frame was already retained as one detail item.  The
    # two-frame abandoned batch does not partially mutate the 32 MiB ledger.
    assert caught.value.failure_evidence["requested_items"] == 2
    assert len(session.deferred.pending) == 1
    assert session.deferred.pending_bytes == frame_bytes
    assert len(matrix_ledger.accepted) == 2
    assert matrix_ledger.current is not None
    assert matrix_ledger.current.frame["metadata"]["buffer_sequence"] == 3
    assert matrix_ledger.accepted_bytes == frame_bytes * 3


def test_tandem_artifact_writer_rejects_symlink_special_and_escape(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    sentinel = outside / "sentinel.cs16"
    sentinel.write_bytes(b"do-not-touch")

    attacks = (
        (root / "symlink.cs16", lambda path: path.symlink_to(sentinel)),
        (root / "fifo.cs16", lambda path: os.mkfifo(path)),
        (outside / "escaped.cs16", lambda _path: None),
    )
    for path, prepare in attacks:
        prepare(path)
        deferred = _DeferredTandemWrites(report_root=root)
        frame: dict[str, object] = {}
        deferred.queue(b"evidence", frame, path, path_field="diagnostic_iq_path")  # type: ignore[arg-type]
        with pytest.raises(_EvidenceInvalidWithDetails) as caught:
            deferred.flush()
        assert caught.value.failure_evidence["kind"] == "unsafe_artifact_path"
        assert "diagnostic_iq_path" not in frame

    assert sentinel.read_bytes() == b"do-not-touch"
    assert not (outside / "escaped.cs16").exists()
    assert stat.S_ISFIFO((root / "fifo.cs16").lstat().st_mode)

    real_root = tmp_path / "real-root"
    linked_root = tmp_path / "linked-root"
    real_root.mkdir()
    linked_root.symlink_to(real_root, target_is_directory=True)
    deferred = _DeferredTandemWrites(report_root=linked_root)
    linked_frame: dict[str, object] = {}
    deferred.queue(
        b"evidence",
        linked_frame,  # type: ignore[arg-type]
        linked_root / "root-link.cs16",
        path_field="diagnostic_iq_path",
    )
    with pytest.raises(_EvidenceInvalidWithDetails) as caught:
        deferred.flush()
    assert caught.value.failure_evidence["kind"] == "unsafe_artifact_path"
    assert not (real_root / "root-link.cs16").exists()


def test_deferred_iq_is_bounded_and_written_only_when_flushed(tmp_path: Path) -> None:
    deferred = _DeferredTandemWrites(maximum_bytes=4, report_root=tmp_path)
    frame: dict[str, object] = {}
    path = tmp_path / "diagnostic.cs16"

    deferred.queue(b"1234", frame, path, path_field="diagnostic_iq_path")  # type: ignore[arg-type]
    assert "diagnostic_iq_path" not in frame
    assert not path.exists()
    deferred.flush()
    assert frame["diagnostic_iq_path"] == "diagnostic.cs16"
    assert path.read_bytes() == b"1234"

    with pytest.raises(_EvidenceInvalidWithDetails, match="in-memory bound"):
        deferred.queue(
            b"12345",
            {},
            tmp_path / "too-large.cs16",
            path_field="diagnostic_iq_path",
        )


def test_tandem_run_flushes_json_and_iq_only_after_buffer_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    options = _options(tmp_path, measurement_frames=1)
    radio = _RunModeRadio()
    settled = SimpleNamespace(
        rx1_gain_index=50,
        rx2_gain_index=50,
        maximum_gain_index=62,
        bench_gain_indices=(50, 50),
    )
    json_write_states: list[bool] = []
    iq_write_states: list[bool] = []
    queued_paths: list[Path] = []
    original_safe_write = tandem_quality._safe_atomic_artifact_write

    monkeypatch.setattr(
        "tests.radio_hardware.tandem_quality._wait_for_idle",
        lambda _radio: {"state": 0, "fault_flags": 0, "fifo_level": 0},
    )
    monkeypatch.setattr(
        "tests.radio_hardware.tandem_quality._atomic_json",
        lambda *_args: json_write_states.append(radio.in_buffer),
    )
    monkeypatch.setattr(
        "tests.radio_hardware.tandem_quality._metadata_dict",
        lambda metadata: {
            "bench_gain_indices": list(metadata.bench_gain_indices),
            "maximum_gain_index": metadata.maximum_gain_index,
        },
    )
    monkeypatch.setattr(
        "tests.radio_hardware.tandem_quality._settle_tandem",
        lambda *_args, **_kwargs: (
            [{"metadata": {"gain_events": []}}],
            settled,
        ),
    )

    def fake_measure(
        *_args: object,
        level_index: int,
        **_kwargs: object,
    ) -> list[dict[str, object]]:
        session = _ACTIVE_TANDEM_SESSION.get()
        assert session is not None
        frame: dict[str, object] = {"quality": {"quality_valid": True}}
        path = tmp_path / f"deferred-level{level_index}.cs16"
        queued_paths.append(path)
        session.deferred.queue(
            b"diagnostic",
            frame,  # type: ignore[arg-type]
            path,
            path_field="diagnostic_iq_path",
        )
        assert not path.exists()
        return [frame]

    def observed_safe_write(root: Path, path: Path, payload: bytes) -> str:
        iq_write_states.append(radio.in_buffer)
        return original_safe_write(root, path, payload)

    monkeypatch.setattr(
        "tests.radio_hardware.tandem_quality._measure_tandem", fake_measure
    )
    monkeypatch.setattr(
        "tests.radio_hardware.tandem_quality.summarize_measurements",
        lambda _measurements: {"quality_valid": True},
    )
    monkeypatch.setattr(
        tandem_quality,
        "_safe_atomic_artifact_write",
        observed_safe_write,
    )

    _run_mode(
        radio,  # type: ignore[arg-type]
        mode="tandem_auto",
        options=options,
        report={"modes": []},
        report_path=tmp_path / "report.json",
        check_deadline=lambda: None,
    )

    assert json_write_states and not any(json_write_states)
    assert iq_write_states and not any(iq_write_states)
    assert all(path.read_bytes() == b"diagnostic" for path in queued_paths)

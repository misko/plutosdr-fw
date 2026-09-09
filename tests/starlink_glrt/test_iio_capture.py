"""Collector lifecycle tests with explicit fake IIO; no hardware is opened."""
from __future__ import annotations

from collections import deque
import errno
import json
import struct
import threading
from types import SimpleNamespace

import pytest

from tools.starlink_glrt_capture import collect, sha256, validate_request, wait_for_prefill, wait_for_final
from .test_abi import record


def arguments(tmp_path):
    return SimpleNamespace(uri="fake:fixture", serial="fixture-serial", firmware_version="fixture-fw",
                           source_rate=2_500_000, lo_hz=1_400_000_000, bandwidth_hz=2_000_000,
                           visit=99, samples=20, chunk_samples=10, acquisition_q16=15729,
                           threshold_q16=19661, margin_q16=9831, decisions_off=False,
                           libiio=None, output=tmp_path / "capture")


def snapshot(*, baseline=False, initial=False, acquisition=15729):
    words = [0]*64
    if not baseline:
        words[0], words[2], words[4], words[6] = 100, 119, 20, 20
        words[12] = words[14] = 20
        words[19], words[21] = 24, 1
    words[20], words[23] = 98 if initial else 99, 1
    words[57:61] = [acquisition, 19661, 9831, 1]
    words[62] = 2_500_000
    cpu = 5 if initial or baseline else 7
    if not initial and not baseline:
        words[30] = words[34] = words[38] = words[53] = words[55] = 2
    return f"GLR1 00010000 2500000 2500000 1 0 2500000 0 {cpu} {cpu} 0 0 0 0 " + " ".join(f"{w:08x}" for w in words)


def event(sequence, visit=99):
    words = record(sequence=sequence)
    words[0] = visit
    return struct.pack("<16I", *words)


@pytest.mark.parametrize("pending", [OSError(errno.ENODATA, "no final yet"), snapshot(initial=True)])
def test_final_wait_requires_current_visit_after_asynchronous_network_close(pending):
    answers = deque([pending, snapshot()])
    def read(name):
        assert name == "capture_final_snapshot"
        value = answers.popleft()
        if isinstance(value, Exception):
            raise value
        return value
    assert wait_for_final(SimpleNamespace(read=read), 99, sleep=lambda _: None) == snapshot()
    assert not answers


def test_final_wait_is_bounded_and_does_not_hide_io_or_decode_errors():
    clock = iter([0.0, 0.0, 3.0])
    old = SimpleNamespace(read=lambda _: snapshot(initial=True))
    with pytest.raises(TimeoutError, match="closed visit"):
        wait_for_final(old, 99, clock=lambda: next(clock), sleep=lambda _: None)
    def broken(_):
        raise OSError(errno.EIO, "driver failed")
    with pytest.raises(OSError) as error:
        wait_for_final(SimpleNamespace(read=broken), 99)
    assert error.value.errno == errno.EIO
    with pytest.raises(ValueError):
        wait_for_final(SimpleNamespace(read=lambda _: "malformed"), 99)


class Scenario:
    version = "fake-libiio"

    def __init__(self, fault=None, *, extension=False):
        self.fault, self.log, self.settings = fault, [], {}
        self.extension = extension
        self.condition = threading.Condition()
        self.events = deque([event(0, 98)])
        self.cancelled = False
        self.iq_closed = False
        self.context_count = 0
        self.live_snapshots = None

    def context(self, api, uri, serial, firmware):
        assert api is self and uri == "fake:fixture"
        assert serial == "fixture-serial" and firmware == "fixture-fw"
        self.context_count += 1
        return FakeContext(self, "iq" if self.context_count == 1 else "events")

    def emit(self, raw):
        with self.condition:
            self.events.append(raw)
            self.condition.notify_all()


class FakeContext:
    def __init__(self, scenario, role):
        self.scenario, self.role, self.buffers = scenario, role, []
        self.attributes = {"hw_serial": "fixture-serial", "fw_version": "fixture-fw"}

    def timeout(self, value):
        self.scenario.log.append((self.role, "timeout", value))

    def device(self, name):
        return FakeDevice(self, name)

    def close(self):
        assert not self.buffers
        self.scenario.log.append((self.role, "context_close"))


class FakeChannel:
    def __init__(self, scenario, name):
        self.scenario, self.name = scenario, name

    def read(self, attr):
        return str({"sampling_frequency": 2_500_000, "rf_bandwidth": 2_000_000,
                    "frequency": 1_400_000_000, "powerdown": int(self.scenario.fault != "tx"),
                    "gain_control_mode": "manual", "hardwaregain": "30.000000 dB",
                    "rf_port_select": "A_BALANCED"}[attr])


class FakeDevice:
    def __init__(self, context, name):
        self.context, self.scenario, self.name = context, context.scenario, name

    def channel(self, name, output=False):
        return FakeChannel(self.scenario, name)

    def scan(self, **kwargs):
        expected = dict(count=2, bits=16, signed=True) if self.name.endswith("-iq") else dict(count=16, bits=32, signed=False)
        assert kwargs == expected

    def read(self, attr):
        if attr == "capture_abi":
            return "GLR1-1.0-upper-only"
        if attr == "capture_extension_abi":
            return "GLX1-1.0" if self.scenario.extension else "none"
        if attr in ("capture_baseline_extension_snapshot", "capture_final_extension_snapshot"):
            assert self.scenario.extension
            words = [0]*16
            if attr == "capture_final_extension_snapshot":
                assert self.scenario.iq_closed
                # Synthetic native support exceeds the tiny exported mock IQ;
                # these records exercise transport, not physical pacing.
                words[0], words[2], words[8], words[10] = 7, 1826, 2, 2
                if self.scenario.fault == "closure_loss":
                    words[8] = 3
                elif self.scenario.fault == "closure_event_support":
                    words[2] = 119
                elif self.scenario.fault == "closure_identity":
                    return "GLX1 00010000 2 99 2500000 " + " ".join(f"{word:08x}" for word in words)
            return "GLX1 00010000 1 99 2500000 " + " ".join(f"{word:08x}" for word in words)
        if attr == "capture_snapshot":
            if self.scenario.live_snapshots is not None and ("iq", "open") in self.scenario.log:
                self.scenario.log.append(("iq", "live_snapshot"))
                return self.scenario.live_snapshots.popleft()
            return snapshot(initial=True)
        if attr == "capture_baseline_snapshot":
            return snapshot(baseline=True, acquisition=self.scenario.settings.get("acquisition_threshold_q16", 15729))
        if attr == "capture_final_snapshot":
            assert self.scenario.iq_closed, "final metadata must follow IQ disable"
            self.scenario.log.append(("iq", "final_snapshot"))
            return snapshot(acquisition=self.scenario.settings.get("acquisition_threshold_q16", 15729))
        raise AssertionError(attr)

    def write(self, name, value):
        self.scenario.settings[name] = value

    def buffer(self, samples, kernel_buffers):
        role = "iq" if self.name.endswith("-iq") else "events"
        assert (samples, kernel_buffers) == ((10, 4) if role == "iq" else (1, 1024))
        if role == "events":
            assert ("events", "timeout", 0) in self.scenario.log, "buffer inherits timeout at OPEN"
        self.scenario.log.append((role, "open"))
        if role == "iq":
            assert ("events", "open") in self.scenario.log
            assert self.scenario.settings["capture_sample_limit"] == 20
        buffer = FakeBuffer(self.context, role)
        self.context.buffers.append(buffer)
        return buffer


class FakeBuffer:
    def __init__(self, context, role):
        self.context, self.scenario, self.role, self.calls = context, context.scenario, role, 0

    def refill(self):
        if self.role == "iq":
            self.scenario.log.append(("iq", "refill"))
            self.calls += 1
            if self.calls == 1:
                self.scenario.emit(b"\0"*64 if self.scenario.fault == "event_malformed" else event(0))
            if self.calls == 2 and self.scenario.fault == "refill":
                raise TimeoutError("injected IQ timeout")
            if self.calls == 2 and self.scenario.fault == "partial":
                return bytes(range(20))
            return bytes(range(40))
        with self.scenario.condition:
            while not self.scenario.events and not self.scenario.cancelled:
                self.scenario.condition.wait()
            if self.scenario.cancelled:
                raise OSError(125, "cancelled")
            return self.scenario.events.popleft()

    def cancel(self):
        with self.scenario.condition:
            self.scenario.cancelled = True
            self.scenario.condition.notify_all()

    def close(self):
        self.scenario.log.append((self.role, "close"))
        self.context.buffers.remove(self)
        if self.role == "iq":
            self.scenario.iq_closed = True
            if self.scenario.live_snapshots is not None and ("iq", "refill") not in self.scenario.log:
                self.scenario.emit(event(0))
            if self.scenario.fault != "event_loss":
                self.scenario.emit(event(1))  # Last event arrives only at IQ disable.


def test_continuous_iq_and_short_event_tail_are_drained_before_context_close(tmp_path):
    scenario, args = Scenario(), arguments(tmp_path)
    summary = collect(args, library=scenario, context_factory=scenario.context)
    assert summary["status"] == "complete", summary
    assert summary["iq_prefix_attested"] and summary["event_transport_attested"]
    assert summary["event_records"] == 2 and summary["other_visit_event_records"] == 1
    assert (args.output / "iq.ci16").read_bytes() == bytes(range(40))*2
    assert (args.output / "events.raw").stat().st_size == 192
    assert scenario.log.index(("iq", "close")) < scenario.log.index(("iq", "final_snapshot"))
    assert scenario.log.index(("iq", "final_snapshot")) < scenario.log.index(("events", "close"))
    assert summary["independent_host_glrt_run"] is False
    assert "drain_bytes_per_second_after_prefill" not in summary


@pytest.mark.parametrize("purpose", [None,
    "event transport control; decisions disabled; not detector qualification"])
def test_protocol_purpose_preserves_default_or_records_explicit_observation(tmp_path, purpose):
    from tools.starlink_glrt_capture import DEFAULT_PURPOSE
    scenario, args = Scenario(), arguments(tmp_path)
    if purpose is not None:
        args.purpose = purpose
    summary = collect(args, library=scenario, context_factory=scenario.context)
    protocol = json.loads((args.output / "protocol.json").read_text())
    assert protocol["purpose"] == (purpose if purpose is not None else DEFAULT_PURPOSE)
    assert summary["status"] == "complete" and summary["live_detector_qualified"] is False
    assert protocol["detector_profile"]["fpga_gates_q16"] == [15729, 19661, 9831]


def test_cli_accepts_explicit_protocol_purpose_without_opening_hardware(monkeypatch, tmp_path):
    import sys
    from tools import starlink_glrt_capture as capture
    purpose = "event transport control; decisions disabled; not detector qualification"
    received = []
    monkeypatch.setattr(capture, "collect", lambda args: received.append(args) or {"status": "complete"})
    monkeypatch.setattr(sys, "argv", ["capture", "--uri", "fake:fixture", "--serial", "fixture",
        "--firmware-version", "test", "--source-rate", "2500000", "--lo-hz", "2400000000",
        "--bandwidth-hz", "2000000", "--visit", "1", "--output", str(tmp_path/"unused"),
        "--purpose", purpose])
    capture.main()
    assert received[0].purpose == purpose and not (tmp_path/"unused").exists()


def test_transport_error_disqualifies_events_even_when_all_counters_match(tmp_path, monkeypatch):
    from tools.starlink_glrt_capture import EventReader
    original_wait = EventReader.wait
    def failed_after_drain(reader, target):
        original_wait(reader, target)
        reader.error = OSError(errno.EPIPE, "quiet event socket expired")
        raise reader.error
    monkeypatch.setattr(EventReader, "wait", failed_after_drain)
    scenario, args = Scenario(), arguments(tmp_path)
    result = collect(args, library=scenario, context_factory=scenario.context)
    assert result["status"] == "failed" and result["iq_prefix_attested"]
    assert result["event_records"] == 2 and not result["event_transport_attested"]


@pytest.mark.parametrize("fault", [None, "closure_loss", "closure_identity", "closure_event_support"])
def test_candidate_capture_requires_atomic_accounted_finite_closure(tmp_path, fault):
    scenario, args = Scenario(fault, extension=True), arguments(tmp_path)
    args.acquisition_q16 = 13107
    summary = collect(args, library=scenario, context_factory=scenario.context)
    assert summary["iq_prefix_attested"]
    assert summary["status"] == ("complete" if fault is None else "failed")
    assert summary["finite_detector_closure_attested"] == (fault is None)
    assert summary["evidence_sha256"]["final_extension_snapshot.txt"] == sha256(args.output/"final_extension_snapshot.txt")


def test_candidate_refuses_legacy_image_before_any_iq_or_event_buffer_is_armed(tmp_path):
    scenario, args = Scenario(), arguments(tmp_path)
    args.acquisition_q16 = 13107
    summary = collect(args, library=scenario, context_factory=scenario.context)
    assert summary["status"] == "failed"
    assert any("requires the GLX1" in reason for reason in summary["failures"])
    assert not any("open" in item for item in scenario.log)


@pytest.mark.parametrize("fault,expected_bytes", [("refill", 40), ("partial", 60)])
def test_partial_iq_is_preserved_and_never_attested_as_complete(fault, expected_bytes, tmp_path):
    scenario, args = Scenario(fault), arguments(tmp_path)
    summary = collect(args, library=scenario, context_factory=scenario.context)
    assert summary["status"] == "failed" and not summary["iq_prefix_attested"]
    assert summary["received_bytes"] == expected_bytes
    assert (args.output / "iq.ci16").stat().st_size == expected_bytes
    assert (args.output / "final_snapshot.txt").is_file()
    assert ("events", "close") in scenario.log and ("iq", "context_close") in scenario.log


def test_tx_preflight_rejects_before_arming_any_buffer(tmp_path):
    scenario, args = Scenario("tx"), arguments(tmp_path)
    summary = collect(args, library=scenario, context_factory=scenario.context)
    assert summary["status"] == "failed"
    assert not any("open" in item for item in scenario.log)
    assert (args.output / "iq.ci16").stat().st_size == 0


@pytest.mark.parametrize("fault", ["event_loss", "event_malformed"])
def test_event_failure_does_not_shorten_or_invalidate_the_iq_prefix(fault, tmp_path):
    scenario, args = Scenario(fault), arguments(tmp_path)
    summary = collect(args, library=scenario, context_factory=scenario.context)
    assert summary["status"] == "failed" and summary["iq_prefix_attested"]
    assert not summary["event_transport_attested"]
    assert summary["received_bytes"] == 80
    assert (args.output / "iq.ci16").read_bytes() == bytes(range(40))*2


@pytest.mark.parametrize("change", [dict(samples=21), dict(chunk_samples=9), dict(samples=0),
                                  dict(samples=75_000_010), dict(visit=0), dict(threshold_q16=65537),
                                  dict(prefill=True, samples=50, chunk_samples=10)])
def test_invalid_capture_geometry_rejected_without_library_or_radio(change, tmp_path):
    args = arguments(tmp_path)
    vars(args).update(change)
    with pytest.raises(ValueError):
        validate_request(args)


def changed_snapshot(changes):
    fields = snapshot().split()
    for word, value in changes.items():
        fields[14+word] = f"{value:08x}"
    return " ".join(fields)


@pytest.mark.parametrize("fault", [None, "partial"])
def test_prefill_finishes_before_first_refill_and_only_complete_capture_gets_rate(tmp_path, fault):
    scenario, args = Scenario(fault), arguments(tmp_path)
    args.prefill = True
    scenario.live_snapshots = deque([changed_snapshot({19: 27, 4: 10, 6: 8, 22: 2}),
                                     changed_snapshot({19: 26, 6: 18, 22: 2}), snapshot()])
    summary = collect(args, library=scenario, context_factory=scenario.context)
    first_refill = scenario.log.index(("iq", "refill"))
    assert scenario.log[:first_refill].count(("iq", "live_snapshot")) == 3
    assert summary["prefill"]["samples"] == 20 and summary["prefill"]["poll_count"] == 3
    assert summary["evidence_sha256"]["prefill_snapshot.txt"] == sha256(args.output/"prefill_snapshot.txt")
    if fault is None:
        assert summary["status"] == "complete", summary
        assert summary["drain_bytes_per_second_after_prefill"] == 80/summary["drain_seconds_after_prefill"]
    else:
        assert summary["status"] == "failed"
        assert summary["drain_bytes_per_second_after_prefill"] is None


def test_prefill_failure_closes_iq_and_drains_events_without_fetching_unproven_backlog(tmp_path):
    scenario, args = Scenario(), arguments(tmp_path)
    args.prefill = True
    scenario.live_snapshots = deque([changed_snapshot({18: 1})])
    summary = collect(args, library=scenario, context_factory=scenario.context)
    assert summary["status"] == "failed" and summary["received_bytes"] == 0
    assert any("transport fault" in reason for reason in summary["failures"])
    assert ("iq", "refill") not in scenario.log
    assert ("iq", "close") in scenario.log and ("events", "context_close") in scenario.log
    assert summary["event_transport_attested"]
    assert summary["drain_bytes_per_second_after_prefill"] is None
    assert summary["evidence_sha256"]["prefill_snapshot.txt"] == sha256(args.output/"prefill_snapshot.txt")


@pytest.mark.parametrize("changes,exception,reason", [
    ({18: 1}, ValueError, "transport fault"),
    ({44: 1}, ValueError, "dropped samples"),
    ({20: 98}, ValueError, "visit mismatch"),
    ({4: 10}, ValueError, "stopped before"),
    ({19: 27, 22: 2}, TimeoutError, "fully DMA-delivered"),
    ({19: 26, 6: 18, 22: 2}, TimeoutError, "fully DMA-delivered"),
    ({6: 18}, ValueError, "not fully drained"),
])
def test_prefill_rejects_faults_short_stop_and_bounded_stall(tmp_path, changes, exception, reason):
    args = arguments(tmp_path)
    args.output.mkdir()
    wire = changed_snapshot(changes)
    ticks = [0.0]
    def sleep(seconds):
        assert seconds == .01
        ticks[0] += 1.0  # Virtual clock; no physical wait.
    iq = SimpleNamespace(read=lambda attr: wire)
    with pytest.raises(exception, match=reason):
        wait_for_prefill(iq, args, clock=lambda: ticks[0], sleep=sleep)
    assert (args.output/"prefill_snapshot.txt").read_text().strip() == wire
    assert ticks[0] <= 3.0

"""Collector lifecycle tests with explicit fake IIO; no hardware is opened."""
from __future__ import annotations

from collections import deque
import json
import struct
import threading
from types import SimpleNamespace

import pytest

from tools.starlink_glrt_capture import collect, validate_request
from .test_abi import record


def arguments(tmp_path):
    return SimpleNamespace(uri="fake:fixture", serial="fixture-serial", firmware_version="fixture-fw",
                           source_rate=2_500_000, lo_hz=1_400_000_000, bandwidth_hz=2_000_000,
                           visit=99, samples=20, chunk_samples=10, acquisition_q16=15729,
                           threshold_q16=19661, margin_q16=9831, decisions_off=False,
                           libiio=None, output=tmp_path / "capture")


def snapshot(*, baseline=False, initial=False):
    words = [0]*64
    if not baseline:
        words[0], words[2], words[4], words[6] = 100, 119, 20, 20
        words[12] = words[14] = 20
        words[19], words[21] = 24, 1
    words[20], words[23] = 98 if initial else 99, 1
    words[57:61] = [15729, 19661, 9831, 1]
    words[62] = 2_500_000
    cpu = 5 if initial or baseline else 7
    if not initial and not baseline:
        words[38] = words[53] = words[55] = 2
    return f"GLR1 00010000 2500000 2500000 1 0 2500000 0 {cpu} {cpu} 0 0 0 0 " + " ".join(f"{w:08x}" for w in words)


def event(sequence, visit=99):
    words = record(sequence=sequence)
    words[0] = visit
    return struct.pack("<16I", *words)


class Scenario:
    version = "fake-libiio"

    def __init__(self, fault=None):
        self.fault, self.log, self.settings = fault, [], {}
        self.condition = threading.Condition()
        self.events = deque([event(0, 98)])
        self.cancelled = False
        self.iq_closed = False
        self.context_count = 0

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
        if attr == "capture_snapshot":
            return snapshot(initial=True)
        if attr == "capture_baseline_snapshot":
            return snapshot(baseline=True)
        if attr == "capture_final_snapshot":
            assert self.scenario.iq_closed, "final metadata must follow IQ disable"
            self.scenario.log.append(("iq", "final_snapshot"))
            return snapshot()
        raise AssertionError(attr)

    def write(self, name, value):
        self.scenario.settings[name] = value

    def buffer(self, samples, kernel_buffers):
        role = "iq" if self.name.endswith("-iq") else "events"
        assert (samples, kernel_buffers) == ((10, 4) if role == "iq" else (1, 1024))
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
                                  dict(samples=75_000_010), dict(visit=0), dict(threshold_q16=65537)])
def test_invalid_capture_geometry_rejected_without_library_or_radio(change, tmp_path):
    args = arguments(tmp_path)
    vars(args).update(change)
    with pytest.raises(ValueError):
        validate_request(args)

"""GLA1 collector lifecycle with fake IIO, including results arriving at stop.

These are transport fixtures, not a numerical claim about their zero IQ bytes.
"""
import json
import struct
from collections import deque
from dataclasses import replace

import pytest

from tools.starlink_glrt_capture import collect, validate_request

from .test_iio_capture import FakeBuffer, FakeContext, FakeDevice, Scenario, arguments
from .test_local_abi import PERIOD, RATE, VISIT, WINDOW, evidence


def iq_wire(snapshot):
    header = ["GLA1", "00010000", RATE, RATE, snapshot.generation, int(snapshot.recovery_failed),
              snapshot.readback_rate, snapshot.dma_error, snapshot.cpu_read, snapshot.cpu_pushed,
              snapshot.cpu_disabled, snapshot.cpu_full, snapshot.cpu_malformed, snapshot.cpu_fault]
    return " ".join(map(str, header)) + " " + " ".join(f"{w:08x}" for w in snapshot.words)


def extension_wire(snapshot):
    return f"GLA1 00010000 {snapshot.generation} {snapshot.visit} {RATE} " + \
        " ".join(f"{w:08x}" for w in snapshot.words)


def search_wire(snapshot):
    return f"GLA1 00010000 {snapshot.generation} {RATE} {PERIOD} {WINDOW} " + \
        " ".join(f"{w:08x}" for w in snapshot.words)


class LocalScenario(Scenario):
    def __init__(self, fault=None):
        super().__init__(fault)
        self.events = deque()
        self.evidence = evidence()

    def context(self, api, uri, serial, firmware):
        assert api is self and uri == "fake:fixture"
        assert (serial, firmware) == ("fixture-serial", "fixture-fw")
        self.context_count += 1
        return LocalContext(self, "iq" if self.context_count == 1 else "events")


class LocalContext(FakeContext):
    def device(self, name):
        return LocalDevice(self, name)


class LocalDevice(FakeDevice):
    def read(self, attr):
        e = self.scenario.evidence
        if attr == "capture_abi":
            return "GLR1-1.0-upper-only" if self.scenario.fault == "abi" else "GLA1-1.0-upper-only"
        if attr in ("capture_extension_abi", "local_search_abi"):
            return "GLA1-1.0"
        if attr == "capture_snapshot":
            b = list(e["baseline"].words)
            b[20] -= 1
            return iq_wire(replace(e["baseline"], words=tuple(b)))
        if "final" in attr:
            assert self.scenario.iq_closed
            self.scenario.log.append(("iq", "final_snapshot"))
        if attr == "capture_baseline_snapshot":
            return iq_wire(e["baseline"])
        if attr == "capture_final_snapshot":
            return iq_wire(e["final"])
        if attr == "capture_baseline_extension_snapshot":
            return extension_wire(e["source_baseline"])
        if attr == "capture_final_extension_snapshot":
            source = e["source"]
            if self.scenario.fault == "source_visit":
                source = replace(source, visit=source.visit + 1)
            return extension_wire(source)
        if attr == "local_search_baseline_snapshot":
            return search_wire(e["search_baseline"])
        if attr == "local_search_final_snapshot":
            stats = e["search"]
            if self.scenario.fault == "search_loss":
                w = list(stats.words)
                w[9] -= 1
                stats = replace(stats, words=tuple(w))
            return search_wire(stats)
        raise AssertionError(attr)

    def buffer(self, samples, kernel_buffers):
        role = "iq" if self.name.endswith("-iq") else "events"
        assert (samples, kernel_buffers) == (((PERIOD+WINDOW)//2, 4) if role == "iq" else (1, 1024))
        if role == "iq":
            assert ("events", "open") in self.scenario.log
            assert self.scenario.settings == {"capture_visit_id": VISIT, "capture_sample_limit": PERIOD+WINDOW}
        self.scenario.log.append((role, "open"))
        buffer = LocalBuffer(self.context, role)
        self.context.buffers.append(buffer)
        return buffer


class LocalBuffer(FakeBuffer):
    def refill(self):
        if self.role == "events":
            return super().refill()
        self.calls += 1
        size = 2*(PERIOD+WINDOW)
        if self.scenario.fault == "truncated_iq" and self.calls == 2:
            size -= 4
        return b"\0" * size

    def close(self):
        self.scenario.log.append((self.role, "close"))
        self.context.buffers.remove(self)
        if self.role == "iq":
            self.scenario.iq_closed = True
            for event in self.scenario.evidence["events"]:
                w = list(event.words)
                if self.scenario.fault == "sequence" and w[2] == 2:
                    w[2] = 4
                self.scenario.emit(struct.pack("<16I", *w))


def local_arguments(tmp_path):
    args = arguments(tmp_path)
    args.local_search, args.visit = True, VISIT
    args.samples, args.chunk_samples = PERIOD+WINDOW, (PERIOD+WINDOW)//2
    args.acquisition_q16 = 13107
    return args


def test_local_iq_and_delayed_decisions_are_recorded_and_bound(tmp_path):
    scenario, args = LocalScenario(), local_arguments(tmp_path)
    result = collect(args, library=scenario, context_factory=scenario.context)
    assert result["status"] == "complete", result
    assert result["schema"] == "starlink-glrt-local-iio-capture/v1"
    assert result["iq_prefix_attested"] and result["event_transport_attested"]
    assert result["finite_detector_closure_attested"]
    assert result["finite_detector_closure"]["completed"] == 2
    assert result["finite_detector_closure"]["supported"] == 1
    assert result["event_records"] == 3
    assert not result["live_detector_qualified"] and not result["independent_host_glrt_run"]
    protocol = json.loads((args.output/"protocol.json").read_text())
    assert protocol["detector_profile"]["name"] == "gla1-upper-local-v1"
    assert "acquisition_q16" not in protocol
    assert scenario.log.index(("iq", "close")) < scenario.log.index(("iq", "final_snapshot"))
    assert scenario.log.index(("iq", "final_snapshot")) < scenario.log.index(("events", "close"))


@pytest.mark.parametrize("fault", ["abi", "source_visit", "search_loss", "sequence", "truncated_iq"])
def test_local_collector_retains_failures_and_never_attests_bad_evidence(tmp_path, fault):
    scenario, args = LocalScenario(fault), local_arguments(tmp_path)
    result = collect(args, library=scenario, context_factory=scenario.context)
    assert result["status"] == "failed" and result["failures"]
    assert not result["finite_detector_closure_attested"]
    if fault != "abi":
        assert result["event_records"] == 3
        assert (args.output/"final_local_search_snapshot.txt").is_file()


@pytest.mark.parametrize("name,value", [("source_rate", 60_000_000), ("decisions_off", True),
    ("prefill", True), ("acquisition_q16", 1), ("profile", "glrt-upper-candidate-v1")])
def test_local_legacy_overrides_are_rejected_before_creating_capture(tmp_path, name, value):
    args = local_arguments(tmp_path)
    setattr(args, name, value)
    with pytest.raises(ValueError):
        validate_request(args)
    assert not args.output.exists()

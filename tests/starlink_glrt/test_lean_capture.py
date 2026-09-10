"""Bounded GLF1 collector ownership, exact coarse prefix and source mapping."""
import json
from types import SimpleNamespace

import pytest

from tools.starlink_glrt_lean_capture import collect, final_snapshot, publish, validate
from .test_lean_abi import wire


def args(tmp_path):
    return SimpleNamespace(uri="ip:192.0.2.14", serial="fixture", firmware_version="fixture-fw",
        visit=91, samples=2000, chunk_samples=1000, lo_hz=1690312496, bandwidth_hz=2500000,
        output=tmp_path/"coarse", libiio=None)


class Fake:
    def __init__(self, fault=None):
        self.fault = fault
        self.live = False
        self.sent = 0
        self.events = []
        self.attributes = {"hw_serial": "fixture", "fw_version": "fixture-fw"}

    def context(self, *a, **kw):
        assert a == (self, "ip:192.0.2.14", "fixture", "fixture-fw")
        assert kw == {"timeout_ms": 2000}
        return self

    def device(self, name):
        assert name in ("starlink-glrt-iq", "ad9361-phy")
        return self

    def channel(self, name, output=False):
        return SimpleNamespace(read=lambda attr: str(dict(sampling_frequency=60000000,
            rf_bandwidth=2500000, frequency=1690312496, powerdown=int(self.fault != "tx"),
            gain_control_mode="manual", hardwaregain="30", rf_port_select="A_BALANCED")[attr]))

    def snapshot(self, mode):
        fields = wire(active=self.live).split()
        w = [int(v, 16) for v in fields[14:]]
        count = self.sent
        first = w[0] | w[1] << 32
        if mode == "initial": w[20] = 90
        elif mode == "baseline":
            w[:8] = [0]*8; w[19] = 0; w[61] = 0
            fields[4] = "4"
            count = 0
        else:
            if mode == "final" and self.fault == "origin": first += 24
            last = first+24*(count-1)
            w[:8] = [first % 2**32, first >> 32, last % 2**32, last >> 32, count, 0, count, 0]
            if self.fault == "gap": w[44] = 1
            if self.fault == "visit": w[20] = 92
        w[12:16] = [max(count*24, 30000), 0, max(count, 1000), 0]
        return ' '.join(fields[:14]+[f'{v:08x}' for v in w])

    def read(self, name):
        self.events.append(("read", name))
        if name == "capture_abi": return "GLR1-1.0-upper-only" if self.fault == "abi" else "GLF1-1.0-upper-only"
        if name == "capture_extension_abi": return "GLF1-1.0"
        if name == "native_capture_enable": return "0"
        if name == "native_schedule_abi": return "GLS1-1.0"
        if name == "native_schedule_snapshot":
            w = [0x474c5331, 1, 5, 1000000, 0, 50 if self.fault == "owned" else 34, 0]+[0]*13
            return 'GLS1SNAP 00010000 '+' '.join(f'{v:08x}' for v in w)
        if name == "capture_snapshot": return self.snapshot("live" if self.live else "initial")
        if name == "capture_baseline_snapshot": return self.snapshot("baseline")
        if name == "capture_final_snapshot": return self.snapshot("final")
        if name in ("capture_baseline_extension_snapshot", "capture_final_extension_snapshot"):
            baseline = name.startswith("capture_baseline")
            w = [0]*16
            if not baseline:
                fields = self.snapshot("final").split()[14:]
                w[:4] = [7, 0, int(fields[2], 16), int(fields[3], 16)]
                w[6] = 19
                if self.fault == "closure": w[8] = 1
            return f'GLF1 00010000 {4 if baseline else 5} 91 60000000 '+' '.join(f'{v:08x}' for v in w)
        raise AssertionError(name)

    def scan(self, **kw): assert kw == dict(count=2, bits=16, signed=True)

    def write(self, name, value):
        assert not self.live and name in ("capture_visit_id", "capture_sample_limit", "glrt_decision_enable")
        self.events.append(("write", name, value))

    def buffer(self, samples, count):
        assert (samples, count) == (1000, 4)
        self.events.append(("open",))
        if self.fault == "open": raise OSError("open failed")
        self.live = True
        fake = self
        class Buffer:
            def refill(self):
                fake.events.append(("refill",))
                if fake.fault == "refill": raise OSError("refill failed")
                fake.sent += samples
                return b"\x01\x02\x03\x04"*(samples-int(fake.fault == "short"))
            def close(self):
                fake.live = False
                fake.events.append(("buffer_close",))
                if fake.fault == "close": raise OSError("close failed")
        return Buffer()

    def close(self):
        assert not self.live
        self.events.append(("context_close",))


def test_coarse_only_capture_retains_live_origin_and_final_iq_without_event_claims(tmp_path):
    fake = Fake()
    a = args(tmp_path)
    result = collect(a, library=fake, context_factory=fake.context)
    assert result["status"] == "complete", result["failures"]
    assert result["iq_prefix_attested"] and result["lean_iq_closure_attested"]
    assert not result["event_transport_attested"] and result["received_bytes"] == 8000
    assert (a.output/"iq.ci16").read_bytes() == b"\x01\x02\x03\x04"*2000
    live = json.loads((a.output/"live_source.json").read_text())
    assert live["provisional"] and live["received_prefix_samples"] == 1000
    assert live["native_signal_center_at_output_zero"] == result["native_signal_center_at_output_zero"]
    assert live["native_signal_center_at_output_zero"] > 2**53
    assert fake.events[-1] == ("context_close",)
    assert not (a.output/"events.raw").exists()


@pytest.mark.parametrize("fault", ["tx", "abi", "owned", "open", "refill", "short", "gap", "visit", "origin", "closure", "close"])
def test_failed_capture_retains_evidence_and_closes_only_its_owned_buffer(tmp_path, fault):
    fake = Fake(fault)
    a = args(tmp_path)
    result = collect(a, library=fake, context_factory=fake.context)
    assert result["status"] == "failed" and result["failures"]
    assert not result["iq_prefix_attested"] and not fake.live
    if fault in ("tx", "abi", "owned"):
        assert not any(e[0] in ("write", "open") for e in fake.events)
    else:
        assert fake.events[-1] == ("context_close",)
    if fault in ("gap", "visit", "short", "origin", "closure"):
        assert (a.output/"iq.ci16").stat().st_size > 0


@pytest.mark.parametrize("name,value", [("uri", "usb:1.1.1"), ("serial", "1040007c4a94000211000b009186843ef2"),
    ("visit", 0), ("samples", 750000001), ("samples", 1999), ("chunk_samples", 999), ("chunk_samples", 250002)])
def test_bad_request_has_no_output_or_radio_access(tmp_path, name, value):
    a = args(tmp_path); setattr(a, name, value)
    with pytest.raises(ValueError): validate(a)
    assert not a.output.exists()


def test_live_mapping_is_published_complete_and_cannot_overwrite_existing_binding(tmp_path):
    path = tmp_path/"live.json"
    publish(path, {"origin": 2**60})
    assert json.loads(path.read_text()) == {"origin": 2**60}
    with pytest.raises(FileExistsError): publish(path, {"origin": 1})
    assert json.loads(path.read_text()) == {"origin": 2**60}


def test_stale_final_visit_is_not_accepted_as_current_capture():
    fake = Fake()
    times = iter([0, 0, 2])
    with pytest.raises(TimeoutError):
        final_snapshot(fake, 93, deadline=1, clock=lambda: next(times), sleep=lambda _: None)

"""Native collector sequencing with explicit fake IIO, never a physical radio."""
import errno
import json
import subprocess
import sys
from collections import deque
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.starlink_glrt_native_abi import SAMPLES
from tools.starlink_glrt_native_capture import (
    collect,
    decode_result,
    restore_default,
    validate_request,
    wait_default,
    wait_result,
)

from .test_native_abi import words


def test_native_collector_script_entrypoint_from_unrelated_directory(tmp_path):
    script = Path(__file__).resolve().parents[2]/"tools/starlink_glrt_native_capture.py"
    result = subprocess.run([sys.executable, str(script), "--help"], cwd=tmp_path,
        capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr
    assert "--jobs" in result.stdout and "--phase-step" in result.stdout


def arguments(tmp_path):
    return SimpleNamespace(uri="ip:192.0.2.14", serial="fixture", firmware_version="fixture-fw",
        output=tmp_path/"capture", lo_hz=1690312498, bandwidth_hz=2500000,
        jobs=2, tag=19, phase_seed=2**32-3, phase_step=2**32-91771, lead_samples=600000, libiio=None)


class Fake:
    def __init__(self, fault=None):
        self.fault = fault
        self.values = {"native_capture_enable": "0"}
        self.pending = self.live = False
        self.opens = 0
        self.events = []
        self.record = ""

    def context(self, api, uri, serial, firmware_version, timeout_ms):
        assert api is self and uri == "ip:192.0.2.14" and serial == "fixture" and firmware_version == "fixture-fw"
        assert timeout_ms == 2000
        self.attributes = {"hw_serial": serial, "fw_version": firmware_version}
        return self

    def device(self, name):
        assert name in ("ad9361-phy", "starlink-glrt-iq")
        return self

    def channel(self, name, output=False):
        return SimpleNamespace(read=lambda key: str({"sampling_frequency": 60000000,
            "rf_bandwidth": 2500000, "frequency": 1690312498, "powerdown": int(self.fault != "tx"),
            "gain_control_mode": "manual", "hardwaregain": "30", "rf_port_select": "A_BALANCED"}[key]))

    def scan(self, **kwargs):
        assert kwargs == {"count": 2, "bits": 16, "signed": True}

    def write(self, name, value):
        assert name.startswith("native_capture_") and not self.live
        self.events.append(("write", name, value))
        self.values[name] = str(value)

    def read(self, name):
        if name == "capture_abi":
            return "GLN1-1.0-native-iq" if self.values["native_capture_enable"] == "1" else "GLR1-1.0-upper-only"
        if name == "native_capture_abi":
            return "none" if self.fault == "abi" else "GLN1-1.0"
        if name == "native_capture_result":
            if not self.record:
                raise OSError(errno.EAGAIN, "no job")
            return self.record
        if name == "native_capture_status":
            return "GLN1STAT 00010000 0 0 0 0 0 00000061 00000000 0 0" if self.fault != "cleanup" else "GLN1STAT 00010000 0 1 0 0 1 00000010 00000000 1 0"
        return self.values[name]

    def buffer(self, samples, kernel_buffers):
        assert samples == SAMPLES and kernel_buffers == 2 and self.values["native_capture_enable"] == "1"
        if self.fault == "open":
            raise OSError(errno.EIO, "buffer open failed")
        assert not self.live
        self.live = True
        self.opens += 1
        w = words()
        w[1] = 0
        w[2] = int(self.values["native_capture_tag"]) + int(self.fault == "tag")
        w[5] = int(self.values["native_capture_phase_seed"])
        w[6] = int(self.values["native_capture_phase_step"]) + int(self.fault == "phase")
        w[8] = 1 if self.fault == "arithmetic" else 0
        self.record = "GLN1 00010000 " + " ".join(f"{value:08x}" for value in w)
        fake = self
        class Buffer:
            def refill(self):
                fake.events.append(("refill",))
                if fake.fault in ("timeout", "cancel"):
                    raise OSError(errno.ETIMEDOUT, "native capture timed out")
                return b"\x00\x01\x02\x03" * (SAMPLES-int(fake.fault == "short"))

            def cancel(self):
                fake.events.append(("cancel",))
                if fake.fault == "cancel":
                    raise OSError(errno.EIO, "injected cancellation failure")

            def close(self):
                fake.events.append(("buffer_close",))
                fake.live = False
                fake.values["native_capture_enable"] = "0"
        return Buffer()

    def close(self):
        assert not self.live
        self.events.append(("context_close",))


def test_two_jobs_reopen_native_mode_and_keep_identity_iq_results_and_cleanup(tmp_path):
    fake = Fake()
    result = collect(arguments(tmp_path), library=fake, context_factory=fake.context)
    assert result["status"] == "transport_pass" and len(result["jobs"]) == 2
    assert result["precision_qualified"] is False and result["arithmetic_replay_required"] is True
    assert fake.opens == 2 and fake.events[-1] == ("context_close",)
    assert [entry[2] for entry in fake.events if entry[:2] == ("write", "native_capture_enable")] == [1, 1]
    assert (tmp_path/"capture/job-0/iq.ci16").stat().st_size == 316800
    assert (tmp_path/"capture/job-1/result.raw").stat().st_size == 128
    assert json.loads((tmp_path/"capture/protocol.json").read_text())["sample_rate_hz"] == 60000000


@pytest.mark.parametrize("fault", ["abi", "tx", "open", "timeout", "cancel", "short", "tag", "phase", "arithmetic", "cleanup"])
def test_failed_capture_preserves_failure_and_does_not_start_another_job(tmp_path, fault):
    fake = Fake(fault)
    result = collect(arguments(tmp_path), library=fake, context_factory=fake.context)
    assert result["status"] == "failed" and result["failures"] and fake.opens <= 1
    assert not fake.live and fake.values["native_capture_enable"] == "0"
    assert fake.events[-1] == ("context_close",)
    if fault not in ("abi", "tx", "open", "timeout", "cancel"):
        assert (tmp_path/"capture/job-0/iq.ci16").exists()


@pytest.mark.parametrize("name,value", [("uri", "usb:1.2.3"), ("serial", "1040007c4a94000211000b009186843ef2"),
    ("jobs", 0), ("jobs", 4), ("tag", 0), ("phase_step", 2**32), ("lead_samples", 5999)])
def test_invalid_request_is_rejected_before_context_or_output(tmp_path, name, value):
    args = arguments(tmp_path)
    setattr(args, name, value)
    with pytest.raises(ValueError):
        validate_request(args)
    assert not args.output.exists()


def test_asynchronous_result_and_close_waits_are_bounded_and_preserve_real_io_errors():
    record = "GLN1 00010000 " + " ".join(f"{value:08x}" for value in words())
    answers = deque([OSError(errno.EAGAIN, "not yet"), record])
    def read(_):
        value = answers.popleft()
        if isinstance(value, Exception):
            raise value
        return value
    assert wait_result(SimpleNamespace(read=read), deadline=1, clock=lambda: 0, sleep=lambda _: None)[0] == record
    with pytest.raises(TimeoutError):
        wait_result(SimpleNamespace(read=read), deadline=1, clock=lambda: 2)
    with pytest.raises(TimeoutError):
        wait_default(SimpleNamespace(read=read), deadline=1, clock=lambda: 2)
    with pytest.raises(ValueError):
        decode_result("GLR1 00010000 " + "00000000 "*32)
    answers.append(OSError(errno.EIO, "real read failure"))
    with pytest.raises(OSError, match="real read failure"):
        wait_result(SimpleNamespace(read=read), deadline=1, clock=lambda: 0)


@pytest.mark.parametrize("fault", [None, errno.EIO, errno.EBUSY])
def test_mode_cleanup_retries_async_close_busy_only_and_obeys_deadline(fault):
    state = {"native_capture_enable": "1", "capture_abi": "GLN1-1.0-native-iq"}
    writes, elapsed = [], [0.0]

    def write(name, value):
        writes.append((name, value))
        if fault or len(writes) <= 2:
            raise OSError(fault or errno.EBUSY, "pending close or real failure")
        state.update(native_capture_enable="0", capture_abi="GLR1-1.0-upper-only")

    def sleep(duration):
        elapsed[0] += duration

    device = SimpleNamespace(read=state.__getitem__, write=write)
    if fault:
        with pytest.raises(TimeoutError if fault == errno.EBUSY else OSError):
            restore_default(device, deadline=0.05, clock=lambda: elapsed[0], sleep=sleep)
        assert len(writes) == (5 if fault == errno.EBUSY else 1)
        assert state["native_capture_enable"] == "1"
    else:
        restore_default(device, deadline=0.05, clock=lambda: elapsed[0], sleep=sleep)
        assert writes == [("native_capture_enable", 0)] * 3
        assert state["native_capture_enable"] == "0"

"""Bounded GLF1 coarse CI16 collection with an explicit live native origin.

Run as ``python -m tools.starlink_glrt_lean_capture``. PPU owns radio identity,
RX configuration and the exclusive lease. Start this coarse buffer before any
GLS1 controller and stop that controller before closing the coarse buffer.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import time
from pathlib import Path

if not __package__:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "tools"

from .starlink_glrt_capture import radio_state, sha256
from .starlink_glrt_iio import Context, Library
from .starlink_glrt_lean_abi import LeanClosure, LeanSnapshot
from .starlink_glrt_schedule_abi import ScheduleSnapshot

SCHEMA = "starlink-glrt-lean-iio-capture/v1"
EXCLUDED = "1040007c4a94000211000b009186843ef2"


def retain(path, value):
    data = value if isinstance(value, bytes) else (json.dumps(value, indent=2, allow_nan=False)+"\n").encode()
    with path.open("xb") as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())


def validate(args):
    if (not args.uri.startswith("ip:") or not args.serial or args.serial == EXCLUDED or
        not args.firmware_version or not 0 < args.visit < 2**32 or args.lo_hz <= 0 or args.bandwidth_hz <= 0 or
        not 2 <= args.chunk_samples <= 250000 or args.chunk_samples % 2 or
        not 0 < args.samples <= 750000000 or args.samples % args.chunk_samples):
        raise ValueError("requires a finite whole-buffer GLF1 Ethernet capture on a permitted receiver")


def publish(path, value):
    """Make the first live mapping visible only after its complete retention."""
    pending = path.with_name("."+path.name+".pending")
    retain(pending, value)
    os.link(pending, path)  # Atomic visibility, and never overwrites a prior run.
    pending.unlink()


def final_snapshot(device, visit, *, deadline, clock=time.monotonic, sleep=time.sleep):
    while clock() < deadline:
        try:
            raw = device.read("capture_final_snapshot")
            if LeanSnapshot.decode(raw).words[20] == visit:
                return raw
        except OSError as error:
            if error.errno != errno.ENODATA:
                raise
        sleep(.005)
    raise TimeoutError("GLF1 final snapshot did not arrive for this visit")


def collect(args, *, library=None, context_factory=Context, clock=time.monotonic):
    validate(args)
    args.output.mkdir(parents=True, exist_ok=False)
    files = [Path(__file__), *(Path(__file__).with_name(name) for name in (
        "starlink_glrt_lean_abi.py", "starlink_glrt_abi.py", "starlink_glrt_iio.py",
        "starlink_glrt_capture.py", "starlink_glrt_schedule_abi.py", "starlink_glrt_native_abi.py"))]
    hashes = {str(path.resolve()): sha256(path) for path in files}
    retain(args.output/"protocol.json", dict(schema=SCHEMA, **{k:str(v) if isinstance(v,Path) else v
        for k,v in vars(args).items()}, source_rate=60000000, output_rate_hz=2500000,
        base_abi="GLF1-1.0-upper-only", source_sha256=hashes, kernel_buffers=4,
        purpose="finite coarse IQ and provisional native mapping; no scored FPGA events"))
    context = device = buffer = baseline = base_closure = final = closure = None
    before = after = origin = None
    failures = []; blocks = []
    received = 0
    hasher = hashlib.sha256()
    began = clock(); deadline = began+args.samples/2500000+30
    with (args.output/"iq.ci16").open("xb") as stream:
        try:
            context = context_factory(library or Library(args.libiio), args.uri, args.serial,
                                      args.firmware_version, timeout_ms=2000)
            retain(args.output/"identity.json", dict(context.attributes))
            before = radio_state(context)
            if (before["sample_rate_hz"] != 60000000 or before["rx_lo_hz"] != args.lo_hz or
                before["rf_bandwidth_hz"] != args.bandwidth_hz or before["tx_powerdown"] != 1):
                raise ValueError("RF readback differs from pinned coarse request")
            device = context.device("starlink-glrt-iq")
            if (device.read("capture_abi") != "GLF1-1.0-upper-only" or
                device.read("capture_extension_abi") != "GLF1-1.0" or
                device.read("native_capture_enable") != "0" or
                device.read("native_schedule_abi") != "GLS1-1.0"):
                raise ValueError("requires idle GLF1/GLS1 with native capture disabled")
            schedule_raw = device.read("native_schedule_snapshot")
            retain(args.output/"initial_schedule.txt", (schedule_raw+"\n").encode())
            schedule = ScheduleSnapshot.from_sysfs(schedule_raw); schedule.require_drained()
            if schedule.configured or schedule.faults or schedule.status & 16:
                raise ValueError("coarse buffer must start before scheduled source ownership")
            raw = device.read("capture_snapshot")
            retain(args.output/"initial_snapshot.txt", (raw+"\n").encode())
            initial = LeanSnapshot.decode(raw)
            if initial.words[19] & 3 or initial.words[20] == args.visit:
                raise ValueError("coarse buffer is occupied or visit was reused")
            device.scan(count=2, bits=16, signed=True)
            for name, value in (("capture_visit_id", args.visit), ("capture_sample_limit", args.samples),
                                ("glrt_decision_enable", 0)):
                device.write(name, value)
            buffer = device.buffer(args.chunk_samples, 4)
            raw = device.read("capture_baseline_snapshot")
            retain(args.output/"baseline_snapshot.txt", (raw+"\n").encode())
            baseline = LeanSnapshot.decode(raw)
            baseline.require_iq_health(expected_visit=args.visit, expected_rate=60000000)
            if baseline.samples or baseline.words[19] & 0x1f:
                raise ValueError("coarse baseline is not pre-ARM")
            raw = device.read("capture_baseline_extension_snapshot")
            retain(args.output/"baseline_extension_snapshot.txt", (raw+"\n").encode())
            base_closure = LeanClosure.decode(raw); base_closure.require_pair(baseline)
            if any(base_closure.words):
                raise ValueError("coarse extension baseline is not pre-ARM")
            while received < 4*args.samples:
                if clock() >= deadline:
                    raise TimeoutError("bounded coarse capture deadline")
                start = clock(); raw = buffer.refill()
                stream.write(raw); stream.flush()
                hasher.update(raw); received += len(raw)
                blocks.append(dict(bytes=len(raw), refill_seconds=clock()-start))
                if len(raw) != 4*args.chunk_samples:
                    raise ValueError("partial coarse DMA block")
                if origin is None:
                    os.fsync(stream.fileno())
                    wire = device.read("capture_snapshot")
                    retain(args.output/"live_snapshot.txt", (wire+"\n").encode())
                    live = LeanSnapshot.decode(wire)
                    origin = live.require_live_prefix(expected_visit=args.visit, received_samples=received//4)
                    publish(args.output/"live_source.json", dict(schema="glrt-lean-live-source/v1", provisional=True,
                        serial=args.serial, visit=args.visit, source_rate_hz=60000000, output_rate_hz=2500000,
                        native_signal_center_at_output_zero=origin, native_samples_per_output_sample=24,
                        received_prefix_samples=received//4, received_prefix_sha256=hasher.hexdigest(),
                        snapshot_sha256=sha256(args.output/"live_snapshot.txt")))
        except BaseException as error:
            failures.append(f"{type(error).__name__}: {error}")
        finally:
            if buffer is not None:
                try: buffer.close()
                except BaseException as error: failures.append(f"coarse close: {error}")
                try:
                    raw = final_snapshot(device, args.visit, deadline=clock()+3, clock=clock)
                    retain(args.output/"final_snapshot.txt", (raw+"\n").encode())
                    final = LeanSnapshot.decode(raw)
                    raw = device.read("capture_final_extension_snapshot")
                    retain(args.output/"final_extension_snapshot.txt", (raw+"\n").encode())
                    closure = LeanClosure.decode(raw)
                except BaseException as error: failures.append(f"coarse final evidence: {error}")
            if context is not None:
                try: after = radio_state(context)
                except BaseException as error: failures.append(f"RF final readback: {error}")
                try: context.close()
                except BaseException as error: failures.append(f"context close: {error}")
            stream.flush(); os.fsync(stream.fileno())
    try:
        if final is None or closure is None or baseline is None or base_closure is None or origin is None:
            raise ValueError("incomplete GLF1 source evidence")
        final.require_iq_prefix(expected_visit=args.visit, expected_rate=60000000,
                                received_bytes=received, expected_samples=args.samples)
        closure.require_complete(final, baseline=base_closure, base_snapshot=baseline)
        if final.source_center(0) != origin or before != after:
            raise ValueError("live source origin or RF configuration changed")
        if sha256(args.output/"iq.ci16") != hasher.hexdigest():
            raise ValueError("saved coarse IQ differs from received bytes")
        if any(sha256(Path(path)) != digest for path,digest in hashes.items()):
            raise ValueError("coarse collector source changed")
    except (OSError, ValueError) as error:
        failures.append(f"coarse attestation: {error}")
    retain(args.output/"blocks.json", blocks)
    summary = dict(schema=SCHEMA, status="complete" if not failures else "failed", failures=failures,
        received_bytes=received, iq_sha256=hasher.hexdigest(), iq_prefix_attested=not failures,
        lean_iq_closure_attested=not failures, event_transport_attested=False,
        native_signal_center_at_output_zero=origin, elapsed_seconds_including_stop=clock()-began,
        radio_before=before, radio_after=after,
        evidence_sha256={path.name:sha256(path) for path in args.output.iterdir() if path.is_file()})
    retain(args.output/"summary.json", summary)
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("uri", "serial", "firmware-version"):
        p.add_argument("--"+name, required=True)
    for name in ("visit", "samples", "lo-hz", "bandwidth-hz"):
        p.add_argument("--"+name, required=True, type=int)
    p.add_argument("--chunk-samples", type=int, default=250000)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--libiio")
    result = collect(p.parse_args())
    print(json.dumps(result))
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())

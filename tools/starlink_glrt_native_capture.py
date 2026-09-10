"""Bounded Ethernet GLN1 bring-up capture; firmware/configuration is external."""
from __future__ import annotations

import argparse
import errno
import hashlib
import json
import re
import struct
import time
from pathlib import Path

if __package__:
    from .starlink_glrt_capture import radio_state
    from .starlink_glrt_iio import Context, Library
    from .starlink_glrt_native_abi import RATE, SAMPLES, NativeResult
else:
    from starlink_glrt_capture import radio_state
    from starlink_glrt_iio import Context, Library
    from starlink_glrt_native_abi import RATE, SAMPLES, NativeResult

EXCLUDED_SERIAL = "1040007c4a94000211000b009186843ef2"
BASE_ABIS = ("GLR1-1.0-upper-only", "GLF1-1.0-upper-only")


def save(path, value):
    with path.open("x") as file:
        json.dump(value, file, indent=2)
        file.write("\n")


def decode_result(text):
    fields = text.split()
    if len(fields) != 34 or fields[:2] != ["GLN1", "00010000"]:
        raise ValueError("unsupported/malformed native result header")
    if any(re.fullmatch(r"[0-9a-fA-F]{8}", word) is None for word in fields[2:]):
        raise ValueError("malformed native result word")
    payload = struct.pack("<32I", *(int(word, 16) for word in fields[2:]))
    return NativeResult.decode(payload), payload


def wait_result(device, *, deadline, clock=time.monotonic, sleep=time.sleep):
    while clock() < deadline:
        try:
            text = device.read("native_capture_result")
            result, payload = decode_result(text)
            return text, result, payload
        except OSError as error:
            if error.errno != errno.EAGAIN:
                raise
        sleep(0.01)
    raise TimeoutError("native result did not become readable")


def wait_default(device, *, deadline, base_abi=BASE_ABIS[0], clock=time.monotonic, sleep=time.sleep):
    # IIOD CLOSE can return before asynchronous kernel teardown has completed.
    while clock() < deadline:
        if device.read("capture_abi") == base_abi and device.read("native_capture_enable") == "0":
            return
        sleep(0.01)
    raise TimeoutError("native teardown did not return to the pinned base ABI")


def restore_default(device, *, deadline, base_abi=BASE_ABIS[0], clock=time.monotonic, sleep=time.sleep):
    # CLOSE may still be retiring DMA. Retry only the driver's EBUSY response;
    # do not treat a failed recovery or another I/O error as successful cleanup.
    while clock() < deadline:
        if device.read("capture_abi") == base_abi and device.read("native_capture_enable") == "0":
            return
        try:
            device.write("native_capture_enable", 0)
        except OSError as error:
            if error.errno != errno.EBUSY:
                raise
        sleep(0.01)
    raise TimeoutError("native mode could not be safely retired")


def require_stopped_status(text):
    fields = text.split()
    if len(fields) != 11 or fields[:2] != ["GLN1STAT", "00010000"]:
        raise ValueError("unsupported/malformed native status")
    if fields[2:7] != ["0", "0", "0", "0", "0"]:
        raise ValueError("native mode, job, error or recovery remains pending")
    status, fault, accepted, delivered = int(fields[7], 16), int(fields[8], 16), int(fields[9]), int(fields[10])
    if status & 0x1e or not status & 0x40 or fault or accepted or delivered:
        raise ValueError("native hardware ownership/counters did not clear")


def validate_request(args):
    start = getattr(args, "start_sample", None)
    if start is not None and (type(start) is not int or not 0 < start <= (1 << 64)-SAMPLES
                              or args.jobs != 1):
        raise ValueError("exact native start requires one job and a complete u64 pilot interval")
    if getattr(args, "base_abi", BASE_ABIS[0]) not in BASE_ABIS:
        raise ValueError("unsupported pinned base ABI")
    if not args.uri.startswith("ip:") or not args.serial or args.serial == EXCLUDED_SERIAL:
        raise ValueError("requires Ethernet and a permitted exact receiver serial")
    if not args.firmware_version or not 1 <= args.jobs <= 3:
        raise ValueError("requires pinned firmware identity and one to three jobs")
    if not 0 < args.tag <= (1 << 32)-args.jobs or not 0 <= args.phase_seed < 1 << 32 or not 0 <= args.phase_step < 1 << 32:
        raise ValueError("native tag/phase is outside u32 range")
    if not 6000 <= args.lead_samples <= 6000000:
        raise ValueError("native scheduling lead is outside driver bounds")


def collect(args, *, library=None, context_factory=Context, clock_ns=time.monotonic_ns):
    validate_request(args)
    base_abi = getattr(args, "base_abi", BASE_ABIS[0])
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    deadline = started+60
    protocol = {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()}
    exact_start = getattr(args, "start_sample", None)
    milestones = []

    def mark(stage):
        if exact_start is not None:
            milestones.append({"stage": stage, "monotonic_ns": str(clock_ns())})

    mark("request_preparation")
    if exact_start is None:
        protocol.pop("start_sample", None)
    files = [Path(__file__), Path(__file__).with_name("starlink_glrt_native_abi.py"),
        Path(__file__).with_name("starlink_glrt_iio.py"), Path(__file__).with_name("starlink_glrt_capture.py")]
    protocol.update(schema="starlink-gln1-native-bringup/v1", sample_rate_hz=RATE,
        samples_per_job=SAMPLES, maximum_collection_seconds=60,
        source_sha256={str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
        precision_qualified=False, arithmetic_replay_required=True)
    if exact_start is not None:
        protocol.update(schema="starlink-gln1-native-exact-start/v1",
            start_sample=str(exact_start), acquisition_verified=False,
            prediction_source_verified=False)
    save(args.output/"protocol.json", protocol)
    context = buffer = device = None
    driver_validated = False
    failures, jobs = [], []
    before = after = None
    try:
        api = library or Library(args.libiio)
        mark("context_open_begin")
        context = context_factory(api, args.uri, args.serial, args.firmware_version, timeout_ms=2000)
        mark("context_open_end")
        save(args.output/"identity.json", dict(context.attributes))
        before = radio_state(context)
        if (before["sample_rate_hz"] != RATE or before["tx_powerdown"] != 1 or
                before["rx_lo_hz"] != args.lo_hz or before["rf_bandwidth_hz"] != args.bandwidth_hz):
            raise ValueError("RF rate/LO/bandwidth or TX mute differs from pinned request")
        device = context.device("starlink-glrt-iq")
        if device.read("capture_abi") != base_abi or device.read("native_capture_abi") != "GLN1-1.0":
            raise ValueError("native capture requires the default receiver and GLN1 driver")
        driver_validated = True
        device.scan(count=2, bits=16, signed=True)
        mark("radio_and_driver_verified")
        for index in range(args.jobs):
            if time.monotonic()+5 >= deadline:
                raise TimeoutError("bounded native campaign has insufficient time for another job")
            root = args.output/f"job-{index}"
            root.mkdir()
            mark("configuration_begin")
            configuration = [("native_capture_tag", args.tag+index),
                    ("native_capture_phase_seed", args.phase_seed), ("native_capture_phase_step", args.phase_step),
                    ("native_capture_lead_samples", args.lead_samples)]
            if exact_start is not None:
                configuration.append(("native_capture_start_sample", exact_start))
            for name, value in configuration:
                device.write(name, value)
            if exact_start is not None and device.read("native_capture_start_sample") != str(exact_start):
                raise ValueError("native exact-start readback differs")
            device.write("native_capture_enable", 1)
            if device.read("capture_abi") != "GLN1-1.0-native-iq":
                raise ValueError("native buffer ABI did not switch")
            # One complete native observation per descriptor; the second
            # queued descriptor remains empty and is canceled at teardown.
            mark("buffer_open_begin")
            buffer = device.buffer(SAMPLES, 2)
            mark("buffer_open_end")
            raw = buffer.refill()
            mark("iq_received")
            (root/"iq.ci16").write_bytes(raw)
            text, result, payload = wait_result(device, deadline=min(deadline, time.monotonic()+3))
            mark("result_received")
            (root/"result.txt").write_text(text+"\n")
            (root/"result.raw").write_bytes(payload)
            # The kernel checks the result start against its locally scheduled
            # snapshot+lead. The collector independently checks tag and bytes;
            # it does not pretend to have predicted that start over Ethernet.
            if not result.capture_requested or result.tag != args.tag+index or len(raw) != 4*result.capture_delivered:
                raise ValueError("native IQ byte count or requested tag differs")
            result.require_complete()
            if result.sequence != 0 or result.phase_seed != args.phase_seed or result.phase_step != args.phase_step:
                raise ValueError("native result differs from the requested phase/sequence")
            if exact_start is not None and result.start != exact_start:
                raise ValueError("native result differs from the requested exact start")
            buffer.close()
            buffer = None
            mark("buffer_closed")
            wait_default(device, deadline=min(deadline, time.monotonic()+3), base_abi=base_abi)
            status = device.read("native_capture_status")
            (root/"final-status.txt").write_text(status+"\n")
            require_stopped_status(status)
            cached = device.read("native_capture_result")
            if cached != text:
                raise ValueError("native cached result changed during teardown")
            jobs.append({"tag": result.tag, "start": result.start, "samples": result.count,
                "iq_sha256": hashlib.sha256(raw).hexdigest(), "result_sha256": hashlib.sha256(payload).hexdigest()})
        after = radio_state(context)
        if before != after:
            raise ValueError("radio configuration changed during native capture")
    except (OSError, ValueError, RuntimeError) as error:
        failures.append(f"{type(error).__name__}: {error}")
    finally:
        if buffer is not None:
            try:
                buffer.cancel()
            except (OSError, ValueError, RuntimeError) as error:
                failures.append(f"buffer cancellation: {type(error).__name__}: {error}")
            try:
                buffer.close()
                buffer = None
            except (OSError, ValueError, RuntimeError) as error:
                failures.append(f"buffer cleanup: {type(error).__name__}: {error}")
        if device is not None:
            if buffer is None and driver_validated:
                try:
                    # Also cover an error after opt-in but before buffer OPEN.
                    # The kernel refuses this write if recovery is unsafe.
                    restore_default(device, deadline=time.monotonic()+3, base_abi=base_abi)
                except (OSError, ValueError, RuntimeError) as error:
                    failures.append(f"mode cleanup: {type(error).__name__}: {error}")
            for name in ("native_capture_result", "native_capture_status", "capture_abi"):
                try:
                    (args.output/f"last-{name}.txt").write_text(device.read(name)+"\n")
                except (OSError, ValueError, RuntimeError) as error:
                    failures.append(f"final {name}: {type(error).__name__}: {error}")
        if context is not None:
            try:
                context.close()
            except (OSError, ValueError, RuntimeError) as error:
                failures.append(f"context cleanup: {type(error).__name__}: {error}")
    if exact_start is not None:
        mark("cleanup_finished")
        save(args.output/"timing.json", dict(schema="starlink-gln1-native-host-timing/v1",
            clock="host_monotonic_ns", milestones=milestones,
            scope="host collector calls; buffer open includes local DMA setup and native admission",
            hardware_admission_timestamp_measured=False, source_continuity_verified=False,
            acquisition_verified=False))
    summary = {"status": "failed" if failures else "transport_pass", "jobs": jobs, "failures": failures,
        "radio_before": before, "radio_after": after, "elapsed_seconds": time.monotonic()-started,
        "precision_qualified": False, "arithmetic_replay_required": True}
    save(args.output/"summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri", required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--firmware-version", required=True)
    parser.add_argument("--base-abi", choices=BASE_ABIS, default=BASE_ABIS[0])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lo-hz", type=int, required=True)
    parser.add_argument("--bandwidth-hz", type=int, required=True)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--tag", type=int, required=True)
    parser.add_argument("--phase-seed", type=int, default=0)
    parser.add_argument("--phase-step", type=int, default=0)
    parser.add_argument("--lead-samples", type=int, default=600000)
    parser.add_argument("--start-sample", type=int,
        help="one exact native sample index; requires the additive driver attribute and --jobs 1")
    parser.add_argument("--libiio")
    result = collect(parser.parse_args())
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "transport_pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

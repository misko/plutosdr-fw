#!/usr/bin/env python3
"""Collect finite continuous GLR1 IQ/events inside an allocated hardware window.

Requires an already configured RX rate/LO/bandwidth and muted TX. This command
arms IQ capture; it does not tune, deploy firmware, or perform host detection.
Finite means a whole-buffer sample limit, with no detection-conditioned gaps.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import threading
import time

if __package__:
    from .starlink_glrt_abi import Closure, Event, Snapshot, RATES
    from .starlink_glrt_iio import Context, Library
    from .starlink_glrt_profile import CANDIDATE, add_arguments, profile
else:
    from starlink_glrt_abi import Closure, Event, Snapshot, RATES
    from starlink_glrt_iio import Context, Library
    from starlink_glrt_profile import CANDIDATE, add_arguments, profile

DEFAULT_PURPOSE = "whole finite continuous IQ prefix, independent of FPGA decisions"


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class EventReader:
    def __init__(self, buffer, stream, visit):
        self.buffer, self.stream, self.visit = buffer, stream, visit
        self.condition = threading.Condition()
        self.stopping = threading.Event()
        self.error = None
        self.events, self.other_visits = [], 0
        self.thread = threading.Thread(target=self.run, name="glrt-events", daemon=True)

    def run(self):
        try:
            while not self.stopping.is_set():
                try:
                    raw = self.buffer.refill()
                except OSError as error:
                    # Only cancellation of the pending libiio read is expected.
                    # A late malformed record, write failure, or unrelated I/O
                    # error remains evidence even when stop raced its arrival.
                    # libiio 0.26 network-unix.c wait_cancellable returns EBADF
                    # when its cancellation eventfd/pipe becomes readable.
                    if self.stopping.is_set() and error.errno in (errno.ECANCELED, errno.EBADF):
                        break
                    raise
                self.stream.write(raw)  # Retain even malformed records as evidence.
                event = Event.decode(raw)
                with self.condition:
                    if event.visit == self.visit:
                        self.events.append(event)
                    else:
                        self.other_visits += 1
                    self.condition.notify_all()
        except BaseException as error:
            with self.condition:
                self.error = error
                self.condition.notify_all()

    def start(self):
        self.thread.start()

    def wait(self, target, timeout=3.0):
        if target < 0:
            raise ValueError("CPU event counter went backwards")
        deadline = time.monotonic() + timeout
        with self.condition:
            while len(self.events) < target and self.error is None:
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("host did not receive all CPU-pushed GLR1 events")
                self.condition.wait(remaining)
            if self.error is not None:
                raise self.error

    def stop(self):
        self.stopping.set()
        self.buffer.cancel()
        self.thread.join(3.0)
        if self.thread.is_alive():
            raise RuntimeError("event reader did not exit after libiio cancellation")


def radio_state(context):
    phy = context.device("ad9361-phy")
    rx = phy.channel("voltage0")
    return {"sample_rate_hz": int(rx.read("sampling_frequency")),
            "rf_bandwidth_hz": int(rx.read("rf_bandwidth")),
            "rx_lo_hz": int(phy.channel("altvoltage0", output=True).read("frequency")),
            "tx_powerdown": int(phy.channel("altvoltage1", output=True).read("powerdown")),
            "gain_control_mode": rx.read("gain_control_mode"),
            "hardwaregain": rx.read("hardwaregain"), "rf_port_select": rx.read("rf_port_select")}


def validate_request(args):
    if args.source_rate not in RATES or not 0 < args.visit < 1 << 32:
        raise ValueError("requires a supported source rate and nonzero u32 visit")
    if not 1 <= args.chunk_samples <= 250_000 or not 0 < args.samples <= 75_000_000:
        raise ValueError("capture requires 1..250000 samples per buffer and at most 30 seconds")
    if args.samples % args.chunk_samples or args.chunk_samples % 2:
        raise ValueError("sample limit must fill whole DMA buffers, with even CI16 buffer length")
    if getattr(args, "prefill", False) and args.samples > 4*args.chunk_samples:
        raise ValueError("prefill requires the entire observation to fit in four requested IQ kernel buffers")
    if not all(0 <= v <= 65536 for v in (args.acquisition_q16, args.threshold_q16, args.margin_q16)):
        raise ValueError("Q16 gates must be 0..65536")
    profile((args.acquisition_q16, args.threshold_q16, args.margin_q16), requested=getattr(args, "profile", None))
    if args.lo_hz <= 0 or args.bandwidth_hz <= 0:
        raise ValueError("expected RX LO and bandwidth must be positive")


def wait_for_prefill(iq, args, *, clock=time.monotonic, sleep=time.sleep):
    """Wait for all requested IQ to reach DMA, before the first host refill.

    Keep the latest snapshot even on fault/timeout. A backend that cannot queue
    enough DMA without host reads fails this mode instead of yielding a rate.
    Per-read libiio timeouts also bound a stalled attribute request.
    """
    started = clock()
    timeout = 2.0 + 4*args.samples/2_500_000
    polls = 0
    while True:
        wire = iq.read("capture_snapshot")
        (args.output / "prefill_snapshot.txt").write_text(wire + "\n")
        snap = Snapshot.decode(wire)
        polls += 1
        snap.require_iq_health(expected_visit=args.visit, expected_rate=args.source_rate)
        if not snap.words[19] & 1:
            if snap.samples != args.samples:
                raise ValueError("prefill producer stopped before the requested sample limit")
            if not snap.words[19] & 2 and snap.words[22] == 0:
                snap.require_stopped_iq(expected_visit=args.visit, expected_rate=args.source_rate,
                                        expected_samples=args.samples)
                return {"producer_stopped_and_dma_prefix_complete": True,
                        "samples": snap.samples, "snapshot_generation": snap.generation,
                        "wait_seconds": clock()-started, "poll_count": polls,
                        "poll_timeout_seconds": timeout}
        if clock()-started >= timeout:
            raise TimeoutError("prefill did not reach a stopped, fully DMA-delivered prefix")
        sleep(.01)


def wait_for_final(iq, visit, *, timeout=3.0, clock=time.monotonic, sleep=time.sleep):
    """Await this visit's kernel teardown on the separate attribute socket.

    IIOD can acknowledge a nonexclusive buffer CLOSE before its worker disables
    the kernel buffer. Until then the final attribute is absent or still holds
    the previous visit. Neither is evidence for the capture just closed.
    """
    deadline = clock() + timeout
    while True:
        try:
            wire = iq.read("capture_final_snapshot")
            if Snapshot.decode(wire).words[20] == visit:
                return wire
        except OSError as error:
            if error.errno != errno.ENODATA:
                raise
        if clock() >= deadline:
            raise TimeoutError("kernel final snapshot did not arrive for the closed visit")
        sleep(0.005)


def collect(args, *, library=None, context_factory=Context):
    validate_request(args)
    args.output.mkdir(parents=True, exist_ok=False)
    protocol = {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()}
    protocol.update(schema="starlink-glrt-iio-capture/v1", output_rate_hz=2_500_000,
                    detector_profile=profile((args.acquisition_q16, args.threshold_q16, args.margin_q16),
                                             requested=getattr(args, "profile", None)),
                    prefill=bool(getattr(args, "prefill", False)),
                    edge="upper", event_buffer_records=1, event_kernel_buffer_count=1024,
                    iq_kernel_buffer_count=4, hardware_qualification="not inferred by this collector",
                    purpose=getattr(args, "purpose", DEFAULT_PURPOSE))
    protocol["closure_extension_required"] = (protocol["detector_profile"]["name"] == CANDIDATE or
                                               bool(getattr(args, "require_closure", False)))
    source_files = [Path(__file__).resolve(), Path(__file__).with_name("starlink_glrt_abi.py").resolve(),
                    Path(__file__).with_name("starlink_glrt_iio.py").resolve(),
                    Path(__file__).with_name("starlink_glrt_profile.py").resolve()]
    protocol["source_sha256"] = {str(path): sha256(path) for path in source_files}
    save(args.output / "protocol.json", protocol)
    api = library or Library(args.libiio)
    context = event_context = iq_buffer = event_buffer = reader = baseline = final = None
    extension_abi = baseline_closure = final_closure = None
    failures, blocks = [], []
    prefill = drain_seconds = None
    received, began = 0, time.monotonic()
    radio_before = radio_after = None
    with (args.output / "iq.ci16").open("xb") as iq_file, (args.output / "events.raw").open("xb") as event_file:
        try:
            context = context_factory(api, args.uri, args.serial, args.firmware_version)
            event_context = context_factory(api, args.uri, args.serial, args.firmware_version)
            save(args.output / "identity.json", {"iq_context": context.attributes,
                 "event_context": event_context.attributes, "libiio": api.version,
                 "host_begin_unix_ns": time.time_ns()})
            radio_before = radio_state(context)
            if (radio_before["sample_rate_hz"] != args.source_rate or radio_before["rx_lo_hz"] != args.lo_hz
                    or radio_before["rf_bandwidth_hz"] != args.bandwidth_hz or radio_before["tx_powerdown"] != 1):
                raise ValueError("configured RF rate/LO/bandwidth or TX mute differs from request")
            iq = context.device("starlink-glrt-iq")
            if iq.read("capture_abi") != "GLR1-1.0-upper-only":
                raise ValueError("unsupported GLR1 kernel ABI")
            try:
                extension_abi = iq.read("capture_extension_abi")
            except OSError as error:
                if error.errno not in (errno.ENOENT, errno.EOPNOTSUPP):
                    raise
                extension_abi = "none"
            (args.output/"extension_abi.txt").write_text(extension_abi+"\n")
            if extension_abi not in ("none", "GLX1-1.0"):
                raise ValueError("unsupported finite closure extension")
            if protocol["closure_extension_required"] and extension_abi != "GLX1-1.0":
                raise ValueError("candidate capture requires the GLX1 finite closure extension")
            initial_text = iq.read("capture_snapshot")
            (args.output / "initial_snapshot.txt").write_text(initial_text + "\n")
            initial = Snapshot.decode(initial_text)
            if initial.words[19] & 3 or initial.words[20] == args.visit:
                raise ValueError("capture is active/queued or visit ID repeats the previous observation")
            if initial.source_rate != args.source_rate:
                raise ValueError("FPGA image rate differs from requested source rate")
            iq.scan(count=2, bits=16, signed=True)
            events = event_context.device("starlink-glrt-events")
            events.scan(count=16, bits=32, signed=False)
            # libiio's software-buffer path uses samples * kernel_buffers for
            # the kernel kfifo length. One-record refills retain a short tail.
            # The network backend copies the context timeout into each new
            # buffer socket; changing it after OPEN does not update that socket.
            # A quiet detector is valid for the entire bounded IQ observation.
            event_context.timeout(0)
            event_buffer = events.buffer(1, 1024)
            reader = EventReader(event_buffer, event_file, args.visit)
            reader.start()
            for name, value in {
                "capture_visit_id": args.visit, "capture_sample_limit": args.samples,
                "acquisition_threshold_q16": args.acquisition_q16, "glrt_threshold_q16": args.threshold_q16,
                "glrt_margin_q16": args.margin_q16, "glrt_decision_enable": int(not args.decisions_off),
            }.items():
                iq.write(name, value)
            began = time.monotonic()
            iq_buffer = iq.buffer(args.chunk_samples, 4)  # Posts DMA, then ARM.
            baseline_text = iq.read("capture_baseline_snapshot")
            (args.output / "baseline_snapshot.txt").write_text(baseline_text + "\n")
            baseline = Snapshot.decode(baseline_text)
            if extension_abi == "GLX1-1.0":
                wire = iq.read("capture_baseline_extension_snapshot")
                (args.output/"baseline_extension_snapshot.txt").write_text(wire+"\n")
                baseline_closure = Closure.decode(wire)
                baseline_closure.require_pair(baseline)
            if baseline.words[20] != args.visit or baseline.samples or baseline.words[19] & 0x1f:
                raise ValueError("driver baseline is not the requested pre-ARM observation")
            if protocol["prefill"]:
                prefill = wait_for_prefill(iq, args)
            drain_start = time.monotonic()
            while received < 4*args.samples:
                start = time.monotonic()
                raw = iq_buffer.refill()
                iq_file.write(raw)
                received += len(raw)
                blocks.append({"bytes": len(raw), "refill_seconds": time.monotonic()-start})
                if len(raw) != args.chunk_samples*4:
                    raise ValueError("finite IQ DMA returned a partial buffer")
            drain_seconds = time.monotonic()-drain_start
        except BaseException as error:
            failures.append(f"{type(error).__name__}: {error}")
        finally:
            # Disable IQ while the event consumer remains active. Preserve the
            # driver's final snapshot even if a refill or readback failed.
            if iq_buffer is not None:
                try:
                    iq_buffer.close()
                except BaseException as error:
                    failures.append(f"IQ disable: {error}")
            if context is not None:
                try:
                    final_text = wait_for_final(context.device("starlink-glrt-iq"), args.visit)
                    (args.output / "final_snapshot.txt").write_text(final_text + "\n")
                    final = Snapshot.decode(final_text)
                    if extension_abi == "GLX1-1.0":
                        wire = context.device("starlink-glrt-iq").read("capture_final_extension_snapshot")
                        (args.output/"final_extension_snapshot.txt").write_text(wire+"\n")
                        final_closure = Closure.decode(wire)
                except BaseException as error:
                    failures.append(f"final evidence: {error}")
                try:
                    radio_after = radio_state(context)
                except BaseException as error:
                    failures.append(f"final RF readback: {error}")
            if reader is not None and baseline is not None and final is not None:
                try:
                    reader.wait(final.cpu_pushed-baseline.cpu_pushed)
                except BaseException as error:
                    failures.append(f"event drain: {error}")
            if reader is not None:
                try:
                    reader.stop()
                except BaseException as error:
                    failures.append(f"event cancellation: {error}")
            if event_buffer is not None and (reader is None or not reader.thread.is_alive()):
                try:
                    event_buffer.close()
                except BaseException as error:
                    failures.append(f"event disable: {error}")
            for label, opened in (("events", event_context), ("IQ", context)):
                if opened is not None:
                    try:
                        opened.close()
                    except BaseException as error:
                        failures.append(f"{label} context close: {error}")
            for stream in (iq_file, event_file):
                stream.flush()
                os.fsync(stream.fileno())
    elapsed = time.monotonic()-began
    iq_pass = event_pass = False
    try:
        if final is None:
            raise ValueError("final IQ evidence is unavailable")
        if radio_before != radio_after:
            raise ValueError("RF configuration or measured gain changed during the observation")
        final.require_iq_prefix(expected_visit=args.visit, expected_rate=args.source_rate,
                                received_bytes=(args.output / "iq.ci16").stat().st_size,
                                expected_samples=args.samples)
        if prefill:
            before_drain = Snapshot.decode((args.output / "prefill_snapshot.txt").read_text())
            if before_drain.words[:8] != final.words[:8]:
                raise ValueError("prefill and final IQ endpoints/counts differ")
        iq_pass = True
    except (OSError, ValueError) as error:
        failures.append(f"IQ attestation: {error}")
    try:
        if final is None or baseline is None or reader is None:
            raise ValueError("complete baseline/final/event evidence is unavailable")
        if reader.error is not None:
            raise ValueError(f"event reader failed ({type(reader.error).__name__}): {reader.error}")
        final.require_events(reader.events, baseline=baseline)
        if extension_abi == "GLX1-1.0":
            if final_closure is None or baseline_closure is None:
                raise ValueError("paired finite closure evidence is unavailable")
            final_closure.require_complete(final, baseline=baseline_closure, base_snapshot=baseline)
            final_closure.require_event_support(reader.events)
        event_pass = True
    except (OSError, ValueError) as error:
        failures.append(f"event attestation: {error}")
    save(args.output / "blocks.json", blocks)
    try:
        if any(sha256(Path(path)) != value for path, value in protocol["source_sha256"].items()):
            failures.append("collector source changed during observation")
    except OSError as error:
        failures.append(f"collector source verification: {error}")
    evidence_names = ("protocol.json", "identity.json", "initial_snapshot.txt", "baseline_snapshot.txt",
                      "final_snapshot.txt", "blocks.json", "iq.ci16", "events.raw")
    if protocol["prefill"]:
        evidence_names += ("prefill_snapshot.txt",)
    evidence_names += ("extension_abi.txt",)
    if extension_abi == "GLX1-1.0":
        evidence_names += ("baseline_extension_snapshot.txt", "final_extension_snapshot.txt")
    summary = {"schema": protocol["schema"], "status": "complete" if not failures else "failed",
               "failures": failures, "received_bytes": received,
               "iq_prefix_attested": iq_pass, "event_transport_attested": event_pass,
               "event_records": len(reader.events) if reader else 0,
               "other_visit_event_records": reader.other_visits if reader else 0,
               "elapsed_seconds_including_stop": elapsed,
               "effective_bytes_per_second_including_stop": received/elapsed,
               "radio_before": radio_before, "radio_after": radio_after,
               "iq_sha256": sha256(args.output / "iq.ci16"),
               "events_sha256": sha256(args.output / "events.raw"),
               "evidence_sha256": {name: sha256(args.output/name) for name in evidence_names
                                   if (args.output/name).is_file()},
               "independent_host_glrt_run": False, "live_detector_qualified": False,
               "detector_busy_rejections": final.u64(36) if final else None,
               "detector_pending_bits": final.words[61] if final else None,
               "ddc_clipping_count": final.words[16] if final else None}
    summary["extension_abi"] = extension_abi
    summary["finite_detector_closure_attested"] = event_pass and extension_abi == "GLX1-1.0"
    summary["finite_detector_closure"] = final_closure.evidence() if final_closure is not None else None
    if protocol["prefill"]:
        summary["prefill"] = prefill
        valid_drain = bool(prefill and drain_seconds and not failures)
        summary["drain_seconds_after_prefill"] = drain_seconds
        summary["drain_bytes_per_second_after_prefill"] = received/drain_seconds if valid_drain else None
        summary["prefill_drain_limitations"] = [
            "Finite buffered service rate includes host refills and buffered file writes; excludes final flush/fsync/stop.",
            "Backend prefetch, kernel buffering and transport scheduling require separate runtime characterization.",
            "This is not a sustained streaming or physical link capacity qualification."]
    save(args.output / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri", required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--firmware-version", required=True)
    parser.add_argument("--source-rate", type=int, choices=RATES, required=True)
    parser.add_argument("--lo-hz", type=int, required=True)
    parser.add_argument("--bandwidth-hz", type=int, required=True)
    parser.add_argument("--visit", type=int, required=True)
    parser.add_argument("--samples", type=int, default=300_000)
    parser.add_argument("--chunk-samples", type=int, default=25_000)
    parser.add_argument("--prefill", action="store_true",
                        help="wait for complete DMA backlog before timing refills; requires <=4 IQ buffers")
    add_arguments(parser, exact_option="--threshold-q16")
    parser.add_argument("--require-closure", action="store_true", help="require GLX1 also for custom development gates")
    parser.add_argument("--decisions-off", action="store_true")
    parser.add_argument("--purpose", default=DEFAULT_PURPOSE,
                        help="record the observation purpose without changing detector behavior")
    parser.add_argument("--libiio")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = collect(args)
    print(json.dumps(summary, sort_keys=True))
    if summary["status"] != "complete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Measure burst-scan listening duty cycle through a remote libiio context."""

import argparse
import gc
import json
import random
import statistics
import time

import iio


def percentile(values, fraction):
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = fraction * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def shuffled_slots(count, frame_count, seed):
    rng = random.Random(seed)
    result = []
    previous = None
    while len(result) < frame_count:
        sweep = list(range(count))
        rng.shuffle(sweep)
        if previous is not None and sweep[0] == previous and len(sweep) > 1:
            sweep[0], sweep[1] = sweep[1], sweep[0]
        result.extend(sweep)
        previous = sweep[-1]
    return result[:frame_count]


def set_attr(channel, name, value):
    channel.attrs[name].value = str(value)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", required=True)
    parser.add_argument("--sample-rate", type=int, default=3_000_000)
    parser.add_argument("--bandwidth", type=int, default=1_500_000)
    parser.add_argument("--frame-ms", type=float, default=80.0)
    parser.add_argument("--frames", type=int, default=75)
    parser.add_argument("--settle-us", type=int, default=250)
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument(
        "--frequencies",
        default="900000000,950000000,1000000000,1050000000,1100000000",
    )
    args = parser.parse_args()

    frequencies = [int(item) for item in args.frequencies.split(",")]
    frame_samples = round(args.sample_rate * args.frame_ms / 1000.0)
    requested_listen_seconds = args.frames * frame_samples / args.sample_rate
    slots = shuffled_slots(len(frequencies), args.frames, args.seed)

    context = iio.Context(args.uri)
    context.set_timeout(15_000)
    phy = context.find_device("ad9361-phy")
    rx = context.find_device("cf-ad9361-lpc")
    if phy is None or rx is None:
        raise RuntimeError("required ad9361-phy/cf-ad9361-lpc device missing")

    rx_lo = phy.find_channel("altvoltage0", True)
    rx_phy = phy.find_channel("voltage0", False)
    if rx_lo is None or rx_phy is None:
        raise RuntimeError("required RX LO/PHY channel missing")

    scan_channels = [
        channel
        for channel in rx.channels
        if channel.scan_element and not channel.output
    ]
    if len(scan_channels) < 4:
        raise RuntimeError("dual-RX scan channels missing")

    original = {
        "frequency": rx_lo.attrs["frequency"].value,
        "sampling_frequency": rx_phy.attrs["sampling_frequency"].value,
        "rf_bandwidth": rx_phy.attrs["rf_bandwidth"].value,
    }
    for channel in scan_channels:
        channel.enabled = True

    tune_times = []
    create_times = []
    refill_times = []
    copy_times = []
    destroy_times = []
    frame_times = []
    payload_bytes = 0
    checksum = 0
    completed = 0

    try:
        set_attr(rx_phy, "sampling_frequency", args.sample_rate)
        set_attr(rx_phy, "rf_bandwidth", args.bandwidth)
        rx.set_kernel_buffers_count(1)

        run_start = time.perf_counter_ns()
        for frame_index, slot in enumerate(slots):
            frame_start = time.perf_counter_ns()

            before = time.perf_counter_ns()
            set_attr(rx_lo, "frequency", frequencies[slot])
            after = time.perf_counter_ns()
            tune_times.append((after - before) / 1e9)

            time.sleep(args.settle_us / 1e6)

            before = time.perf_counter_ns()
            buffer = iio.Buffer(rx, frame_samples, False)
            after = time.perf_counter_ns()
            create_times.append((after - before) / 1e9)

            before = time.perf_counter_ns()
            buffer.refill()
            after = time.perf_counter_ns()
            refill_times.append((after - before) / 1e9)

            before = time.perf_counter_ns()
            payload = buffer.read()
            after = time.perf_counter_ns()
            copy_times.append((after - before) / 1e9)
            payload_bytes += len(payload)
            if payload:
                checksum = (checksum + payload[0] + payload[-1] + frame_index) & 0xFFFFFFFF

            before = time.perf_counter_ns()
            del payload
            del buffer
            gc.collect()
            after = time.perf_counter_ns()
            destroy_times.append((after - before) / 1e9)

            completed += 1
            frame_times.append((time.perf_counter_ns() - frame_start) / 1e9)

        wall_seconds = (time.perf_counter_ns() - run_start) / 1e9
    finally:
        set_attr(rx_phy, "rf_bandwidth", original["rf_bandwidth"])
        set_attr(rx_phy, "sampling_frequency", original["sampling_frequency"])
        set_attr(rx_lo, "frequency", original["frequency"])

    actual_listen_seconds = completed * frame_samples / args.sample_rate

    def stats(values):
        return {
            "mean_ms": statistics.fmean(values) * 1000.0,
            "p50_ms": percentile(values, 0.50) * 1000.0,
            "p95_ms": percentile(values, 0.95) * 1000.0,
            "p99_ms": percentile(values, 0.99) * 1000.0,
            "max_ms": max(values) * 1000.0,
        }

    result = {
        "implementation": "python-libiio-remote",
        "uri": args.uri,
        "context_description": context.description,
        "sample_rate_hz": args.sample_rate,
        "rf_bandwidth_hz": args.bandwidth,
        "frame_samples_per_channel": frame_samples,
        "frame_listen_ms": frame_samples / args.sample_rate * 1000.0,
        "frames_requested": args.frames,
        "frames_completed": completed,
        "frequencies_hz": frequencies,
        "settle_guard_us": args.settle_us,
        "requested_listen_seconds": requested_listen_seconds,
        "actual_listen_seconds": actual_listen_seconds,
        "wall_seconds": wall_seconds,
        "listening_duty_cycle": actual_listen_seconds / wall_seconds,
        "payload_bytes": payload_bytes,
        "effective_payload_mib_s": payload_bytes / wall_seconds / (1024.0 * 1024.0),
        "checksum": checksum,
        "tune": stats(tune_times),
        "buffer_create": stats(create_times),
        "buffer_refill": stats(refill_times),
        "buffer_copy": stats(copy_times),
        "buffer_destroy": stats(destroy_times),
        "whole_frame": stats(frame_times),
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

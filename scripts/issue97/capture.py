#!/usr/bin/env python3
"""Finite receive-only issue-97 qualification, restricted to one serial."""

from __future__ import annotations

import argparse
import ctypes
import gc
import hashlib
import json
import sys
import time
from pathlib import Path

SERIAL = "1040007c4a94000211000b009186843ef2"
URI = "ip:192.168.1.18"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--binding-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--counter-only", action="store_true")
    parser.add_argument("--usb", action="store_true")
    parser.add_argument("--ordinary", action="store_true")
    parser.add_argument("--channels", nargs="+", type=int, default=[0])
    parser.add_argument("--auto", action="store_true")
    parser.add_argument("--rates", nargs="+", type=int, default=[2_500_000, 5_000_000])
    parser.add_argument("--frames", type=int, default=5)
    parser.add_argument("--samples", type=int, default=1_000_000)
    parser.add_argument("--kernel-buffers", type=int, default=50)
    parser.add_argument("--delay", type=float, default=0)
    args = parser.parse_args()
    lib = args.library.resolve(strict=True)
    ctypes.CDLL(str(lib), mode=ctypes.RTLD_GLOBAL)
    sys.path.insert(0, str(args.binding_directory.resolve(strict=True)))
    import adi
    import iio
    from pluto_plus.hardware.iio_metadata import IioMetadataCaptureSession
    from pluto_plus.radio_lock import acquire_radio_lock
    from pluto_plus.tandem import TandemMode, TandemSessionRequestV1

    uri = URI
    if args.usb:
        from pluto_plus.inventory import scan_local_usb_plutos

        matches = [d for d in scan_local_usb_plutos() if d.serial == SERIAL]
        assert len(matches) == 1
        target = matches[0]
        uri = f"usb:{target.bus_number}.{target.device_number}.5"
    result = {
        "serial": SERIAL,
        "uri": uri,
        "native_version": iio.version,
        "native_sha256": hashlib.sha256(lib.read_bytes()).hexdigest(),
        "binding_sha256": hashlib.sha256(Path(iio.__file__).read_bytes()).hexdigest(),
        "counter_only": args.counter_only,
        "cells": [],
    }
    # Library selection is explicit and independently recorded for baseline/candidate controls.
    maps = Path("/proc/self/maps").read_text()
    assert str(lib) in maps, "requested native runtime was not mapped"
    other = {line.split()[-1] for line in maps.splitlines() if "libiio.so" in line}
    assert other == {str(lib)}, other
    with acquire_radio_lock(SERIAL):
        context = iio.Context(uri)
        assert context.attrs["hw_serial"] == SERIAL
        channels = [
            ch
            for ch in context.find_device("cf-ad9361-lpc").channels
            if ch.scan_element and not ch.output
        ]
        facade = adi.ad9364 if len(channels) == 2 else adi.ad9361
        del channels, context
        gc.collect()
        radio = facade(uri=uri)
        assert radio.ctx.attrs["hw_serial"] == SERIAL
        result["firmware"] = radio.ctx.attrs["fw_version"]
        rx = radio._rxadc
        result["scan_channels"] = [
            ch.id for ch in rx.channels if ch.scan_element and not ch.output
        ]
        phy = radio._ctrl
        # All ordinary buffers must be idle before this bounded diagnostic owns RX.
        assert (
            rx.attrs.get("buffer_enable", None) is None
            or rx.attrs["buffer_enable"].value == "0"
        )
        # Keep both physical transmitters muted; no waveform or DDS stimulation.
        for ch in phy.channels:
            if ch.output and ch.id.startswith("voltage") and "hardwaregain" in ch.attrs:
                ch.attrs["hardwaregain"].value = "-89.75"
                assert float(ch.attrs["hardwaregain"].value.split()[0]) <= -89
        for dev in radio.ctx.devices:
            if dev.name == "cf-ad9361-dds-core-lpc":
                for ch in dev.channels:
                    if "raw" in ch.attrs:
                        ch.attrs["raw"].value = "0"
                    if "scale" in ch.attrs:
                        ch.attrs["scale"].value = "0"
        original = {
            "sample_rate": radio.sample_rate,
            "rx_rf_bandwidth": radio.rx_rf_bandwidth,
            "rx_lo": radio.rx_lo,
            "rx_enabled_channels": list(radio.rx_enabled_channels),
        }
        gain = [
            (
                ch.id,
                {
                    name: ch.attrs[name].value
                    for name in ("gain_control_mode", "hardwaregain")
                    if name in ch.attrs
                },
            )
            for ch in phy.channels
            if not ch.output and ch.id.startswith("voltage")
        ]
        result["original"] = original
        result["original_gain"] = gain
        original_queue = rx.kernel_buffers_count
        original_control = rx.reg_read(0x800000BC)
        try:
            for rate in args.rates:
                cell = {
                    "requested_rate": rate,
                    "frames": [],
                    "requested_kernel_buffers": args.kernel_buffers,
                }
                result["cells"].append(cell)
                session = None
                try:
                    radio.rx_enabled_channels = args.channels
                    radio.sample_rate = rate
                    radio.rx_rf_bandwidth = min(rate, 50_000_000)
                    radio.rx_lo = 2_400_000_000
                    radio.gain_control_mode_chan0 = "manual"
                    radio.rx_hardwaregain_chan0 = 30
                    assert radio.sample_rate == rate
                    cell["sample_rate"] = radio.sample_rate
                    cell["rf_bandwidth"] = radio.rx_rf_bandwidth
                    cell["timestamp_control_before"] = rx.reg_read(0x800000BC)
                    rx.set_kernel_buffers_count(args.kernel_buffers)
                    session = IioMetadataCaptureSession(
                        radio,
                        iio.MetadataBuffer,
                        sample_rate_hz=rate,
                        samples_per_channel=args.samples,
                        kernel_buffers=args.kernel_buffers,
                        metadata_abi=3,
                        counter_only=args.counter_only,
                        iq_decoder="raw-complex64",
                        direct_async_frames=0 if args.ordinary else args.frames,
                        drop_backlog_on_overrun=True,
                        tandem_request=None
                        if args.counter_only
                        else TandemSessionRequestV1(
                            mode=TandemMode.AUTO if args.auto else TandemMode.HOLD
                        ),
                    )
                    start = time.monotonic()
                    session.open()
                    cell["allocated_kernel_buffers"] = session.allocated_kernel_buffers
                    for index in range(args.frames):
                        if index == 1 and args.delay:
                            time.sleep(args.delay)
                        block = session.read_block()
                        cell["frames"].append(
                            {
                                "first": block.first_sample_sequence,
                                "end": block.last_sample_sequence_exclusive,
                                "missing": block.missing_samples_before,
                                "flags": block.metadata_flags,
                                "shape": list(block.samples.shape),
                                "iq_sha256": hashlib.sha256(
                                    block.samples.tobytes()
                                ).hexdigest(),
                            }
                        )
                    cell["elapsed_seconds"] = time.monotonic() - start
                    cell["outcome"] = "completed"
                except Exception as error:  # noqa: BLE001 - preserve pyadi failures in evidence
                    cell["outcome"] = "error"
                    cell["error"] = f"{type(error).__name__}: {error}"
                    cell["errno"] = getattr(error, "errno", None)
                finally:
                    if session is not None:
                        session.close()
                    radio.rx_destroy_buffer()
                    gc.collect()
                    cell["timestamp_control_after"] = rx.reg_read(0x800000BC)
                    assert cell["timestamp_control_after"] == original_control
                    args.output.write_text(json.dumps(result, indent=2) + "\n")
        finally:
            radio.rx_destroy_buffer()
            gc.collect()
            for name, value in original.items():
                setattr(radio, name, value)
            for channel, attrs in gain:
                ch = phy.find_channel(channel, False)
                # Restore manual index before restoring the original gain mode.
                if "hardwaregain" in attrs:
                    ch.attrs["gain_control_mode"].value = "manual"
                    ch.attrs["hardwaregain"].value = attrs["hardwaregain"].split()[0]
                if "gain_control_mode" in attrs:
                    ch.attrs["gain_control_mode"].value = attrs["gain_control_mode"]
            rx.set_kernel_buffers_count(original_queue)
            result["restored"] = all(
                getattr(radio, k) == v for k, v in original.items()
            )
            result["restored_gain"] = all(
                phy.find_channel(ch, False).attrs[k].value == v
                for ch, attrs in gain
                for k, v in attrs.items()
            )
            result["restored_queue"] = rx.kernel_buffers_count == original_queue
            args.output.write_text(json.dumps(result, indent=2) + "\n")
            print(
                json.dumps(
                    {
                        "serial": SERIAL,
                        "restored": result["restored"],
                        "cells": [
                            {
                                "rate": c["requested_rate"],
                                "outcome": c["outcome"],
                                "frames": len(c["frames"]),
                                "error": c.get("error"),
                                "missing": sum(f["missing"] for f in c["frames"]),
                            }
                            for c in result["cells"]
                        ],
                    },
                    indent=2,
                )
            )


if __name__ == "__main__":
    main()

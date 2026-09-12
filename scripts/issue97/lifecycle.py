#!/usr/bin/env python3
"""Exercise admission, configuration exclusion and daemon-death recovery."""

import ctypes
import json
import time

from maintain import HOST, ROOT, SERIAL, link

ctypes.CDLL(
    "/home/mouse9911/gits/pluto-plus-utils-issue-97/.venv/lib/libiio.so.0",
    mode=ctypes.RTLD_GLOBAL,
)
import adi
import iio
from pluto_plus.hardware.iio_metadata import IioMetadataCaptureSession
from pluto_plus.radio_lock import acquire_radio_lock
from pluto_plus.tandem import TandemMode, TandemSessionRequestV1


def main():
    outcomes = {}
    with acquire_radio_lock(SERIAL):
        radio = adi.ad9364(uri="ip:" + HOST)
        assert radio.ctx.attrs["hw_serial"] == SERIAL
        rx = radio._rxadc
        originals = {
            k: getattr(radio, k)
            for k in (
                "sample_rate",
                "rx_rf_bandwidth",
                "rx_lo",
                "rx_enabled_channels",
                "gain_control_mode_chan0",
                "rx_hardwaregain_chan0",
            )
        }
        queue, control = rx.kernel_buffers_count, rx.reg_read(0x800000BC)
        (ROOT / "lifecycle-original.json").write_text(
            json.dumps(
                {"settings": originals, "queue": queue, "control": control}, indent=2
            )
        )
        radio.sample_rate = 5_000_000
        radio.rx_rf_bandwidth = 5_000_000
        radio.rx_enabled_channels = [0]
        radio.gain_control_mode_chan0 = "manual"
        rx.set_kernel_buffers_count(4)

        def session(**kw):
            args = {
                "sample_rate_hz": 5_000_000,
                "samples_per_channel": 100_000,
                "kernel_buffers": 4,
                "metadata_abi": 3,
                "counter_only": True,
                "iq_decoder": "raw-complex64",
                "direct_async_frames": 10,
            }
            args.update(kw)
            return IioMetadataCaptureSession(radio, iio.MetadataBuffer, **args)

        def reject(name, operation):
            try:
                operation()
            except OSError as error:
                assert error.errno in (16, 22, 95), (name, error)
                outcomes[name] = error.errno
            else:
                raise AssertionError(name + " unexpectedly admitted")

        def reject_session(name, **kw):
            s = session(**kw)
            try:
                reject(name, s.open)
            finally:
                s.close()
            assert rx.reg_read(0x800000BC) == control

        try:
            reject_session("wrong_rate", sample_rate_hz=6_000_000)
            radio.gain_control_mode_chan0 = "fast_attack"
            reject_session("automatic_gain")
            radio.gain_control_mode_chan0 = "manual"
            rx.reg_write(0x800000BC, control | 1)
            try:
                s = session()
                try:
                    reject("decimation_enabled", s.open)
                finally:
                    s.close()
                assert rx.reg_read(0x800000BC) == control | 1
            finally:
                rx.reg_write(0x800000BC, control)
            reject_session(
                "paired_hold_on_1r1t",
                counter_only=False,
                tandem_request=TandemSessionRequestV1(mode=TandemMode.HOLD),
            )
            s = session()
            s.open()
            try:
                first = s.read_block()
                assert first.first_sample_sequence is not None
                for name, obj, attr, value in (
                    ("rate_write", radio, "sample_rate", radio.sample_rate),
                    ("lo_write", radio, "rx_lo", radio.rx_lo),
                    (
                        "bandwidth_write",
                        radio,
                        "rx_rf_bandwidth",
                        radio.rx_rf_bandwidth,
                    ),
                    ("gain_mode_write", radio, "gain_control_mode_chan0", "manual"),
                    (
                        "gain_write",
                        radio,
                        "rx_hardwaregain_chan0",
                        radio.rx_hardwaregain_chan0,
                    ),
                ):
                    reject(name, lambda o=obj, a=attr, v=value: setattr(o, a, v))
                reject("timestamp_write", lambda: rx.reg_write(0x800000BC, control))
                other = session()
                try:
                    reject("second_counter_owner", other.open)
                finally:
                    other.close()
            finally:
                s.close()
            assert rx.reg_read(0x800000BC) == control
            outcomes["normal_close_restores_timestamp"] = True
            # The supervisor must restart iiOD; kernel descriptor release must
            # restore the lease even though userspace cleanup cannot run.
            s = session()
            s.open()
            s.read_block()
            (ROOT / "lifecycle.json").write_text(json.dumps(outcomes, indent=2))
            link().run("kill -KILL $(pidof iiod)", timeout_s=10)
            try:
                s.close()
            except OSError:
                pass
            deadline = time.monotonic() + 20
            while True:
                try:
                    new = adi.ad9364(uri="ip:" + HOST)
                    assert new.ctx.attrs["hw_serial"] == SERIAL
                    assert new._rxadc.reg_read(0x800000BC) == control
                    new.sample_rate = 5_000_000
                    radio = new
                    rx = radio._rxadc
                    radio.rx_enabled_channels = [0]
                    radio.gain_control_mode_chan0 = "manual"
                    rx.set_kernel_buffers_count(4)
                    recovered = session()
                    try:
                        recovered.open()
                        recovered.read_block()
                    finally:
                        recovered.close()
                    outcomes["iiod_death_releases_and_recaptures"] = True
                    break
                except Exception as error:
                    if isinstance(error, AssertionError):
                        raise
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(0.25)
        finally:
            radio.rx_destroy_buffer()
            radio.gain_control_mode_chan0 = "manual"
            for key, value in originals.items():
                if key != "gain_control_mode_chan0":
                    setattr(radio, key, value)
            radio.gain_control_mode_chan0 = originals["gain_control_mode_chan0"]
            rx.set_kernel_buffers_count(queue)
            outcomes["timestamp_restored"] = rx.reg_read(0x800000BC) == control
            outcomes["settings_restored"] = all(
                getattr(radio, k) == v for k, v in originals.items()
            )
            (ROOT / "lifecycle.json").write_text(json.dumps(outcomes, indent=2))
            print(json.dumps(outcomes, indent=2))


if __name__ == "__main__":
    main()

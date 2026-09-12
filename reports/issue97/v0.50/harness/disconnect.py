#!/usr/bin/env python3
"""Verify client-death and timeout release on the exact persistent candidate."""

import json
import select
import subprocess
import sys
import threading
import time

from maintain import HOST, ROOT, SERIAL, link
from pluto_plus.hardware.iio import IioRadioDevice
from pluto_plus.models import GainMode, RadioSettings
from pluto_plus.radio_lock import acquire_radio_lock
from pluto_plus.setup_profiles import AD9361_1R1T_TARGET_PROFILE


def open_radio():
    radio = IioRadioDevice(
        "ip:" + HOST, serial=SERIAL, expected_metadata_abi=3, iq_decoder="raw-complex64"
    )
    radio.configure_rx_layout(AD9361_1R1T_TARGET_PROFILE.rx_layout_expectation)
    radio.open()
    return radio


def configure(radio):
    radio.apply_settings(
        RadioSettings(
            center_frequency_hz=2_400_000_000,
            sample_rate_hz=5_000_000,
            bandwidth_hz=5_000_000,
            gain_mode=GainMode.MANUAL,
            gain_db=30,
            channels=(0,),
        )
    )


def child():
    radio = open_radio()
    configure(radio)
    capture = radio.begin_metadata_capture(
        1_000_000, kernel_buffers=4, counter_only=True, direct_async_frames=100
    )
    capture.read_block()
    print("READY " + SERIAL, flush=True)
    time.sleep(30)
    capture.close()
    radio.close()


def main():
    outcomes = {}
    with acquire_radio_lock(SERIAL):
        radio = open_radio()
        original, queue = radio.read_settings(), radio.read_kernel_buffers_count()
        control = radio._device._rxadc.reg_read(0x800000BC)
        process = None
        try:
            process = subprocess.Popen(
                [sys.executable, __file__, "--child"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            assert select.select([process.stdout], [], [], 20)[0], "child did not arm"
            assert process.stdout.readline().strip() == "READY " + SERIAL
            process.kill()
            process.wait(timeout=5)
            deadline = time.monotonic() + 20
            while True:
                try:
                    configure(radio)
                    with radio.begin_metadata_capture(
                        100_000,
                        kernel_buffers=4,
                        counter_only=True,
                        direct_async_frames=2,
                    ) as capture:
                        capture.read_block()
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(0.2)
            outcomes["killed_client_releases_and_recaptures"] = True
            completed = subprocess.run(
                [sys.executable, __file__, "--timeout"],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
            assert completed.returncode == 0, completed.stderr + completed.stdout
            outcomes["forced_timeout"] = json.loads(completed.stdout)
            radio.close()
            radio = open_radio()
            configure(radio)
            with radio.begin_metadata_capture(
                100_000, kernel_buffers=4, counter_only=True, direct_async_frames=2
            ) as capture:
                capture.read_block()
            outcomes["timeout_releases_and_recaptures"] = True
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            radio.apply_settings(original)
            radio.configure_kernel_buffers(queue)
            outcomes["settings_restored"] = radio.read_settings() == original
            outcomes["timestamp_restored"] = (
                radio._device._rxadc.reg_read(0x800000BC) == control
            )
            radio.ensure_transmit_muted()
            radio.close()
            (ROOT / "disconnect.json").write_text(json.dumps(outcomes, indent=2))
            print(json.dumps(outcomes, indent=2))


if __name__ == "__main__":
    if "--timeout" in sys.argv:
        from pluto_plus.hardware.iio_metadata import IioMetadataCaptureSession

        radio = open_radio()
        configure(radio)
        radio.configure_kernel_buffers(50)
        capture = IioMetadataCaptureSession(
            radio._device,
            radio._iio_module.MetadataBuffer,
            sample_rate_hz=5_000_000,
            samples_per_channel=1_000_000,
            kernel_buffers=50,
            metadata_abi=3,
            counter_only=True,
        )
        resume_timer = None
        stopped = False

        def resume():
            link().run("kill -CONT $(pidof iiod)", timeout_s=5)

        try:
            capture.open()
            owned_control = radio._device._rxadc.reg_read(0x800000BC)
            assert owned_control == 1_000_000
            radio._device.ctx.set_timeout(1)
            link().run("kill -STOP $(pidof iiod)", timeout_s=5)
            stopped = True
            resume_timer = threading.Timer(8, resume)
            resume_timer.start()
            capture.read_block()
        except OSError as error:
            assert error.errno in (110, 11, 32), error
            print(
                json.dumps(
                    {
                        "type": type(error).__name__,
                        "errno": error.errno,
                        "owned_timestamp_control": owned_control,
                    }
                ),
                flush=True,
            )
        else:
            raise AssertionError("one-ms admission/read did not time out")
        finally:
            if resume_timer is not None:
                resume_timer.cancel()
            if stopped:
                resume()
            try:
                capture.close()
            except OSError:
                pass
            try:
                radio.close()
            except OSError:
                pass
    elif "--child" in sys.argv:
        child()
    else:
        main()

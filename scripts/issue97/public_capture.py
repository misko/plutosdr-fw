#!/usr/bin/env python3
"""Post-deployment qualification through the public, receipt-verified PPU API."""

import json
from dataclasses import asdict

from maintain import HOST, ROOT, SERIAL
from pluto_plus.hardware.iio import IioRadioDevice
from pluto_plus.models import GainMode, RadioSettings
from pluto_plus.radio_lock import acquire_radio_lock
from pluto_plus.setup_profiles import AD9361_1R1T_TARGET_PROFILE


def main():
    with acquire_radio_lock(SERIAL):
        radio = IioRadioDevice(
            "ip:" + HOST,
            serial=SERIAL,
            expected_metadata_abi=3,
            iq_decoder="raw-complex64",
        )
        radio.configure_rx_layout(AD9361_1R1T_TARGET_PROFILE.rx_layout_expectation)
        radio.open()
        original = radio.read_settings()
        original_queue = radio.read_kernel_buffers_count()
        result = {
            "serial": SERIAL,
            "identity": radio.identity.model_dump(mode="json"),
            "original": original.model_dump(mode="json"),
            "cells": [],
        }
        try:
            for rate in (5_000_000, 60_000_000):
                settings = RadioSettings(
                    center_frequency_hz=2_400_000_000,
                    sample_rate_hz=rate,
                    bandwidth_hz=min(rate, 50_000_000),
                    gain_mode=GainMode.MANUAL,
                    gain_db=30,
                    channels=(0,),
                )
                actual = radio.apply_settings(settings)
                assert actual == settings
                source = radio.configure_source_locked_rx_rate(rate)
                cell = {"rate": rate, "source": asdict(source), "frames": []}
                with radio.begin_metadata_capture(
                    1_000_000,
                    kernel_buffers=50,
                    counter_only=True,
                    direct_async_frames=30,
                ) as capture:
                    cell["allocated_kernel_buffers"] = capture.allocated_kernel_buffers
                    assert capture.allocated_kernel_buffers == 50
                    for _ in range(30):
                        block = capture.read_block()
                        assert block.tandem_metadata is None
                        cell["frames"].append(
                            {
                                "first": block.first_sample_sequence,
                                "end": block.last_sample_sequence_exclusive,
                                "missing": block.missing_samples_before,
                            }
                        )
                assert all(f["missing"] == 0 for f in cell["frames"])
                result["cells"].append(cell)
        finally:
            radio.apply_settings(original)
            radio.configure_kernel_buffers(original_queue)
            result["restored"] = radio.read_settings() == original
            result["queue_restored"] = (
                radio.read_kernel_buffers_count() == original_queue
            )
            radio.ensure_transmit_muted()
            radio.close()
            (ROOT / "persistent-public-capture.json").write_text(
                json.dumps(result, indent=2)
            )
            print(
                json.dumps({k: v for k, v in result.items() if k != "cells"}, indent=2)
            )


if __name__ == "__main__":
    main()

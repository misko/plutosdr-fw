"""Fixture ordering and cleanup without a radio or an RF transmission."""
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import qualify_tones as tones


class Attribute:
    def __init__(self, name, value, events):
        self.name, self._value, self.events = name, value, events

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self.events.append((self.name, value))
        self._value = value


class Radio:
    def __init__(self, powerdown="1", serial=tones.SERIAL):
        self.events = []
        self._values = {"tx_lo": 900_000_000, "tx_rf_bandwidth": 2_000_000,
                        "tx_hardwaregain_chan0": -80.0, "tx_hardwaregain_chan1": -80.0}
        self.fail_on = None
        self.ignore_on = None
        self.dds_error = False
        self.dds_enabled = False
        self._ctx = types.SimpleNamespace(attrs={"hw_serial": serial})
        self.powerdown = Attribute("powerdown", powerdown, self.events)
        self.channel = types.SimpleNamespace(attrs={"powerdown": self.powerdown})
        self._ctrl = types.SimpleNamespace(
            find_channel=lambda name, output: self.channel,
            attrs={"calib_mode": Attribute("calib_mode", "auto", self.events)})

    def __getattr__(self, name):
        if name in self._values:
            return self._values[name]
        raise AttributeError(name)

    def __setattr__(self, name, value):
        values = self.__dict__.get("_values", {})
        if name in values:
            self.events.append((name, value))
            if self.fail_on == (name, value):
                raise OSError("injected " + name + " failure")
            if self.ignore_on != (name, value):
                values[name] = value
        else:
            object.__setattr__(self, name, value)

    def dds_single_tone(self, frequency, scale, channel):
        assert self.powerdown.value == "0"
        assert self.tx_hardwaregain_chan0 <= -80 and self.tx_hardwaregain_chan1 <= -80
        self.events.append(("dds", frequency, scale, channel))
        self.dds_enabled = True
        if self.dds_error:
            raise OSError("injected partial DDS setup failure")


def mute(radio):
    radio.events.append(("mute",))
    radio.tx_hardwaregain_chan0 = radio.tx_hardwaregain_chan1 = -80
    radio.dds_enabled = False


class FixtureTests(unittest.TestCase):
    def fixture(self, radio, gain=-30, muter=mute):
        return tones.ToneFixture(23, 2_011_328_125, gain,
            radio_factory=lambda **kwargs: radio, mute_transmit=muter, sleep=lambda _: None)

    def test_power_up_before_dds_and_unmute_only_after_dds(self):
        radio = Radio()
        fixture = self.fixture(radio)
        fixture.enable(None)
        dds = ("dds", 268_750, 0.25, 1)
        self.assertLess(radio.events.index(("powerdown", "0")), radio.events.index(dds))
        self.assertLess(radio.events.index(dds), radio.events.index(("tx_hardwaregain_chan1", -30)))
        self.assertEqual(fixture.receipt["logical_target"], 23)
        self.assertEqual(fixture.receipt["tx1_gain_db"], -80)
        self.assertEqual(fixture.receipt["external_attenuation_db"], 30)
        fixture.close()

    def test_close_restores_both_powerdown_states_and_mutes_dds(self):
        for initial in ("0", "1"):
            with self.subTest(initial=initial):
                radio = Radio(powerdown=initial)
                fixture = self.fixture(radio)
                fixture.enable(None)
                fixture.close()
                self.assertEqual(radio.tx_lo, 900_000_000)
                self.assertEqual(radio.tx_rf_bandwidth, 2_000_000)
                self.assertEqual(radio.powerdown.value, initial)
                self.assertEqual(radio.tx_hardwaregain_chan0, -80)
                self.assertEqual(radio.tx_hardwaregain_chan1, -80)
                self.assertFalse(radio.dds_enabled)
                self.assertTrue(fixture.cleanup["passed"])
                self.assertEqual(fixture.cleanup["expected"], fixture.cleanup["observed"])
                count = len(radio.events)
                fixture.close()
                self.assertEqual(len(radio.events), count)

    def test_failed_source_setup_still_restores_after_close(self):
        radio = Radio()
        fixture = self.fixture(radio)
        radio.dds_error = True
        with self.assertRaisesRegex(OSError, "partial DDS"):
            fixture.enable(None)
        fixture.close()
        self.assertFalse(radio.dds_enabled)
        self.assertEqual(radio.powerdown.value, "1")
        self.assertEqual(radio.tx_lo, 900_000_000)
        self.assertTrue(fixture.cleanup["passed"])

    def test_cleanup_attempts_restoration_after_mute_failure_and_powers_down(self):
        radio = Radio(powerdown="0")
        fixture = self.fixture(radio)
        fixture.enable(None)

        def failed_mute(device):
            raise OSError("mute transport failure")

        fixture.mute_transmit = failed_mute
        with self.assertRaisesRegex(RuntimeError, "mute transport failure"):
            fixture.close()
        self.assertEqual(radio.tx_lo, 900_000_000)
        self.assertEqual(radio.tx_rf_bandwidth, 2_000_000)
        self.assertEqual(radio.tx_hardwaregain_chan1, -80)
        self.assertEqual(radio.powerdown.value, "1")
        self.assertFalse(fixture.cleanup["passed"])

    def test_failed_lo_restore_does_not_prevent_bandwidth_or_powerdown(self):
        radio = Radio(powerdown="0")
        fixture = self.fixture(radio)
        fixture.enable(None)
        radio.fail_on = ("tx_lo", 900_000_000)
        with self.assertRaisesRegex(RuntimeError, "injected tx_lo"):
            fixture.close()
        self.assertEqual(radio.tx_rf_bandwidth, 2_000_000)
        self.assertEqual(radio.powerdown.value, "1")
        self.assertFalse(radio.dds_enabled)

    def test_silent_restore_failure_is_reported_and_powers_down(self):
        radio = Radio(powerdown="0")
        fixture = self.fixture(radio)
        fixture.enable(None)
        radio.ignore_on = ("tx_rf_bandwidth", 2_000_000)
        with self.assertRaisesRegex(RuntimeError, "restoration readback mismatch"):
            fixture.close()
        self.assertEqual(radio.powerdown.value, "1")
        self.assertFalse(fixture.cleanup["passed"])

    def test_wrong_serial_does_not_mutate_or_mute_another_radio(self):
        radio = Radio(serial="another-radio")
        fixture = self.fixture(radio)
        with self.assertRaisesRegex(ValueError, "serial mismatch"):
            fixture.enable(None)
        fixture.close()
        self.assertEqual(radio.events, [])

    def test_gain_bounds_include_minus30_and_reject_more_output(self):
        radio = Radio()
        self.fixture(radio, gain=-30)
        for gain in (-29.75, -81, float("nan")):
            with self.subTest(gain=gain), self.assertRaisesRegex(ValueError, "outside bounds"):
                self.fixture(radio, gain=gain)

    def test_cli_passes_cleanup_hook_and_preserves_capture_failure(self):
        radio = Radio()

        def recording(uri, serial, directory, **kwargs):
            directory.mkdir()
            try:
                kwargs["before_start_hook"](None)
                raise RuntimeError("injected capture failure")
            finally:
                radio.events.append(("owner-closed",))
                kwargs["after_close_hook"]()

        dependencies = {
            "pluto_plus.hardware.preflight": types.SimpleNamespace(verify_metadata_runtime=lambda abi: None),
            "adi": types.SimpleNamespace(ad9361=lambda **kwargs: radio),
            "numpy": types.SimpleNamespace(),
            "pluto_plus.hardware.iio": types.SimpleNamespace(_mute_transmit=mute),
            "pluto_plus.position_scan_record": types.SimpleNamespace(
                FREQUENCIES=(2_011_328_125,) * 24, record_position_scan=recording),
            "pluto_plus.position_scan_verify": types.SimpleNamespace(verify_position_scan=None),
            "pluto_plus.tx2_loopback": types.SimpleNamespace(analyze_tx2_splitter=None),
        }
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "capture"
            with patch.dict(sys.modules, dependencies), patch.object(sys, "argv", [
                    "qualify_tones.py", "--output", str(output), "--targets", "23",
                    "--duration", "1", "--tx-gain-db", "-30"]):
                with self.assertRaisesRegex(RuntimeError, "injected capture failure"):
                    tones.main()
            summary = json.loads((output / "target-23/tone-verification.json").read_text())
            self.assertFalse(summary["passed"])
            self.assertTrue(summary["fixture_cleanup"]["passed"])
            closed = radio.events.index(("owner-closed",))
            cleanup_mute = next(index for index, event in enumerate(radio.events)
                                if index > closed and event == ("mute",))
            self.assertGreater(cleanup_mute, closed)
            self.assertEqual(radio.powerdown.value, "1")


if __name__ == "__main__":
    unittest.main()

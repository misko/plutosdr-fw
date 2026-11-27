"""Prove the 24 tunings using the cabled TX2/30 dB/splitter fixture on .15."""
from __future__ import annotations

import argparse
import dataclasses
import json
import time
from pathlib import Path

SERIAL = "104000b29905000e17000800065934759d"
URI = "ip:192.168.1.15"


class ToneFixture:
    """TX fixture hooks run inside the recorder's station lock."""

    def __init__(self, target, frequency_hz, gain_db, *, radio_factory, mute_transmit,
                 sleep=time.sleep):
        if not 0 <= target < 24 or not -80 <= gain_db <= -30:
            raise ValueError("fixture target or TX gain outside bounds")
        self.target, self.frequency_hz, self.gain_db = target, frequency_hz, gain_db
        self.tone_hz = 125_000 + target * 6_250
        self.radio_factory, self.mute_transmit, self.sleep = radio_factory, mute_transmit, sleep
        self.source = None
        self.tx_lo_channel = None
        self.snapshot = {}
        self.receipt = {}
        self.cleanup = None

    def enable(self, preparation):
        source = self.radio_factory(uri=URI)
        if source._ctx.attrs["hw_serial"] != SERIAL:
            raise ValueError("fixture serial mismatch")
        tx_lo = source._ctrl.find_channel("altvoltage1", True)
        snapshot = {name: getattr(source, name) for name in ("tx_lo", "tx_rf_bandwidth")}
        snapshot["powerdown"] = tx_lo.attrs["powerdown"].value
        # Publish cleanup state before the first mutation, including failed START.
        self.source, self.snapshot, self.tx_lo_channel = source, snapshot, tx_lo
        self.mute_transmit(source)
        tx_lo.attrs["powerdown"].value = "0"
        if tx_lo.attrs["powerdown"].value != "0":
            raise ValueError("fixture TX LO did not power up")
        source.tx_rf_bandwidth = 8_000_000
        source.tx_lo = self.frequency_hz
        # The clock-framework getter rounds in half-rate units. The RX receipt
        # separately carries the frequency decoded from the selected PLL image.
        if abs(int(source.tx_lo) - self.frequency_hz) > 4:
            raise ValueError("fixture TX LO readback mismatch")
        source._ctrl.attrs["calib_mode"].value = "tx_quad"
        # Configure the waveform at minimum gain, then enable only physical TX2.
        source.dds_single_tone(self.tone_hz, 0.25, channel=1)
        if float(source.tx_hardwaregain_chan0) > -80:
            raise ValueError("TX1 must remain muted")
        source.tx_hardwaregain_chan1 = self.gain_db
        observed_gain = float(source.tx_hardwaregain_chan1)
        if not -80 <= observed_gain <= -30 or abs(observed_gain - self.gain_db) > 0.25:
            raise ValueError("fixture TX2 gain readback mismatch")
        self.receipt.update({"requested_tx_lo_hz": self.frequency_hz,
            "readback_tx_lo_hz": int(source.tx_lo), "dds_hz": self.tone_hz,
            "dds_scale": 0.25, "tx1_gain_db": float(source.tx_hardwaregain_chan0),
            "tx2_gain_db": float(source.tx_hardwaregain_chan1), "external_attenuation_db": 30,
            "serial": SERIAL, "logical_target": self.target,
            "previous_tx_lo_powerdown": snapshot["powerdown"]})
        self.sleep(0.1)

    def close(self):
        """Mute first, restore every field, and power down on a cleanup fault."""
        source = self.source
        if source is None:
            return
        errors = []

        def attempt(name, action):
            try:
                action()
            except BaseException as error:
                errors.append(f"{name}: {error!r}")

        tx_lo = self.tx_lo_channel
        observed = {}

        def powerdown(value):
            tx_lo.attrs["powerdown"].value = value
            observed["powerdown"] = tx_lo.attrs["powerdown"].value
            if observed["powerdown"] != value:
                raise ValueError("fixture TX LO powerdown readback mismatch")

        def restore(name):
            setattr(source, name, self.snapshot[name])
            observed[name] = getattr(source, name)
            if (abs(int(observed[name]) - int(self.snapshot[name])) > 2 if name == "tx_lo"
                    else observed[name] != self.snapshot[name]):
                raise ValueError("fixture " + name + " restoration readback mismatch")
        # Independent attenuation attempts also protect a partial mute failure.
        for name in ("tx_hardwaregain_chan0", "tx_hardwaregain_chan1"):
            attempt(name, lambda name=name: setattr(source, name, -80.0))
        attempt("mute", lambda: self.mute_transmit(source))
        attempt("power down", lambda: powerdown("1"))
        for name in ("tx_rf_bandwidth", "tx_lo"):
            attempt(name, lambda name=name: restore(name))
        for name in ("tx_hardwaregain_chan0", "tx_hardwaregain_chan1"):
            def verify_gain(name=name):
                if float(getattr(source, name)) > -80:
                    raise ValueError(name + " did not return to mute")
            attempt("verify " + name, verify_gain)
        restored_powerdown = "1" if errors else self.snapshot["powerdown"]
        attempt("restore powerdown", lambda: powerdown(restored_powerdown))
        if errors:
            attempt("final power down", lambda: powerdown("1"))
        self.cleanup = {"passed": not errors, "errors": errors,
                        "expected": self.snapshot, "observed": observed}
        self.source = None
        if errors:
            raise RuntimeError("fixture cleanup failed: " + "; ".join(errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--targets", default=",".join(map(str, range(24))))
    parser.add_argument("--duration", type=float, default=5)
    parser.add_argument("--tx-gain-db", type=float, default=-60)
    args = parser.parse_args()
    targets = tuple(map(int, args.targets.split(",")))
    if not targets or len(set(targets)) != len(targets) or any(not 0 <= target < 24 for target in targets):
        raise ValueError("targets must be distinct integers in 0..23")
    if not -80 <= args.tx_gain_db <= -30 or not 0 < args.duration <= 60:
        raise ValueError("fixture output or duration outside bounds")
    from pluto_plus.hardware.preflight import verify_metadata_runtime
    verify_metadata_runtime(3)
    import adi
    import numpy as np
    from pluto_plus.hardware.iio import _mute_transmit
    from pluto_plus.position_scan_record import FREQUENCIES, record_position_scan
    from pluto_plus.position_scan_verify import verify_position_scan
    from pluto_plus.tx2_loopback import analyze_tx2_splitter

    args.output.mkdir(parents=True, exist_ok=False)
    summaries = []
    for target in targets:
        fixture = ToneFixture(target, FREQUENCIES[target], args.tx_gain_db,
                              radio_factory=adi.ad9361, mute_transmit=_mute_transmit)
        metrics, retained = [], []

        def inspect(item, plan):
            if item.record.result.value != 1:
                return
            raw = np.frombuffer(item.iq, dtype="<i2").reshape(-1, 4)
            if np.any((raw <= -2047) | (raw >= 2047)):
                raise ValueError(f"fixture ADC clipping on visit {item.record.visit}")
            if item.record.target == target:
                retained.append((item.record.visit, item.record.slot_generation,
                                 item.record.verified_frequency_hz, bytes(item.iq)))

        directory = args.output / f"target-{target:02d}"
        try:
            record_position_scan(URI, SERIAL, directory, duration=args.duration,
                                 before_start_hook=fixture.enable, after_close_hook=fixture.close,
                                 on_visit=inspect)
            verified = verify_position_scan(directory, minimum_sweeps=2)
            for visit, slot_generation, verified_if, iq in retained:
                raw = np.frombuffer(iq, dtype="<i2").reshape(-1, 4)
                samples = np.stack((raw[:, 0] + 1j * raw[:, 1], raw[:, 2] + 1j * raw[:, 3]))
                expected = fixture.tone_hz + fixture.receipt["readback_tx_lo_hz"] - verified_if
                measured = analyze_tx2_splitter(samples, sample_rate_hz=10_000_000,
                                                expected_tone_hz=expected)
                metrics.append({"visit": visit, "slot_generation": slot_generation,
                                "tone": dataclasses.asdict(measured)})
            if len(metrics) < 2 or len({row["slot_generation"] for row in metrics}) < 2:
                raise ValueError("tone must be observed across slot reuse")
            summary = {"passed": True, "source": fixture.receipt, "observations": metrics,
                       "fixture_cleanup": fixture.cleanup, "independent_iq": verified}
        except BaseException as error:
            summary = {"passed": False, "source": fixture.receipt, "observations": metrics,
                       "fixture_cleanup": fixture.cleanup, "error": repr(error)}
            if directory.exists():
                (directory / "tone-verification.json").write_text(json.dumps(summary, indent=2) + "\n")
            summaries.append(summary)
            (args.output / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n")
            raise
        (directory / "tone-verification.json").write_text(json.dumps(summary, indent=2) + "\n")
        summaries.append(summary)
        (args.output / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n")
        print(json.dumps({"target": target, "observations": len(metrics), "passed": True}), flush=True)


if __name__ == "__main__":
    main()

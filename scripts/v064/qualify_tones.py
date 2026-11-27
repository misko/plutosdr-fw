"""Prove the 24 tunings using the cabled TX2/30 dB/splitter fixture on .15."""
from __future__ import annotations

import argparse
import dataclasses
import json
import time
from pathlib import Path

SERIAL = "104000b29905000e17000800065934759d"
URI = "ip:192.168.1.15"


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
    if not -80 <= args.tx_gain_db <= -40 or not 0 < args.duration <= 60:
        raise ValueError("fixture output or duration outside bounds")
    import adi
    import numpy as np
    from pluto_plus.hardware.iio import _mute_transmit
    from pluto_plus.position_scan_record import FREQUENCIES, record_position_scan
    from pluto_plus.position_scan_verify import verify_position_scan
    from pluto_plus.radio_lock import acquire_radio_lock
    from pluto_plus.tx2_loopback import analyze_tx2_splitter

    args.output.mkdir(parents=True, exist_ok=False)
    summaries = []
    with acquire_radio_lock(SERIAL):
        for target in targets:
            source = None
            snapshot = {}
            metrics = []
            retained = []
            source_receipt = {}
            original_tx_powerdown = None
            tone_hz = 125_000 + target * 6_250

            def enable_source(preparation):
                nonlocal source, snapshot, original_tx_powerdown
                source = adi.ad9361(uri=URI)
                if source._ctx.attrs["hw_serial"] != SERIAL:
                    raise ValueError("fixture serial mismatch")
                snapshot = {name: getattr(source, name) for name in ("tx_lo", "tx_rf_bandwidth")}
                _mute_transmit(source)
                tx_lo = source._ctrl.find_channel("altvoltage1", True)
                original_tx_powerdown = tx_lo.attrs["powerdown"].value
                source.tx_rf_bandwidth = 8_000_000
                source.tx_lo = FREQUENCIES[target]
                if abs(int(source.tx_lo) - FREQUENCIES[target]) > 4:
                    raise ValueError("fixture TX LO readback mismatch")
                tx_lo.attrs["powerdown"].value = "0"
                source._ctrl.attrs["calib_mode"].value = "tx_quad"
                source.tx_hardwaregain_chan1 = args.tx_gain_db
                source.dds_single_tone(tone_hz, 0.25, channel=1)
                if float(source.tx_hardwaregain_chan0) > -80:
                    raise ValueError("TX1 must remain muted")
                source_receipt.update({"requested_tx_lo_hz": FREQUENCIES[target],
                    "readback_tx_lo_hz": int(source.tx_lo), "dds_hz": tone_hz,
                    "tx2_gain_db": float(source.tx_hardwaregain_chan1), "external_attenuation_db": 30,
                    "serial": SERIAL, "logical_target": target})
                time.sleep(0.1)

            def inspect(item, plan):
                if item.record.target != target or item.record.result.value != 1:
                    return
                retained.append((item.record.visit, item.record.slot_generation, bytes(item.iq)))

            directory = args.output / f"target-{target:02d}"
            try:
                record_position_scan(URI, SERIAL, directory, duration=args.duration,
                                     before_start_hook=enable_source, on_visit=inspect)
                verified = verify_position_scan(directory, minimum_sweeps=2)
                for visit, slot_generation, iq in retained:
                    raw = np.frombuffer(iq, dtype="<i2").reshape(-1, 4)
                    samples = np.stack((raw[:, 0] + 1j * raw[:, 1], raw[:, 2] + 1j * raw[:, 3]))
                    measured = analyze_tx2_splitter(samples, sample_rate_hz=10_000_000,
                                                    expected_tone_hz=tone_hz)
                    metrics.append({"visit": visit, "slot_generation": slot_generation,
                                    "tone": dataclasses.asdict(measured)})
                if len(metrics) < 2 or len({row["slot_generation"] for row in metrics}) < 2:
                    raise ValueError("tone must be observed across slot reuse")
                summary = {"passed": True, "source": source_receipt, "observations": metrics,
                           "independent_iq": verified}
                (directory / "tone-verification.json").write_text(json.dumps(summary, indent=2) + "\n")
                summaries.append(summary)
                (args.output / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n")
                print(json.dumps({"target": target, "observations": len(metrics), "passed": True}), flush=True)
            finally:
                if source is not None:
                    _mute_transmit(source)
                    for name, value in snapshot.items():
                        setattr(source, name, value)
                    if original_tx_powerdown is not None:
                        source._ctrl.find_channel("altvoltage1", True).attrs["powerdown"].value = original_tx_powerdown
                    if float(source.tx_hardwaregain_chan1) > -80:
                        raise ValueError("TX2 did not return to mute")
                    source = None


if __name__ == "__main__":
    main()

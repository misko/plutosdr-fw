#!/usr/bin/env python3
"""Finite PIL1 AXI/DDC/AXIS RTL replay; NOT DMA/IIO/hardware/RF qualification."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.starlink_oracle.pilot_ddc import PilotDdcOracle
from tests.starlink_oracle.test_pilot_capture_rtl import (
    compile_simulator, cw_samples, run, snapshot, u64, write,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ppu-source", type=Path, required=True,
                        help="explicit read-only PPU checkout for offline PIL1 parsing")
    parser.add_argument("--samples", type=int, default=300_000)
    args = parser.parse_args()
    if args.output.exists() or not 1 <= args.samples <= 300_000:
        parser.error("use a new report path and 1..300000 supported output samples")
    ppu_file = args.ppu_source.resolve() / "src/pluto_plus/hardware/pilot_iio.py"
    if not ppu_file.is_file():
        parser.error("PPU checkout lacks the offline PIL1 parser")
    sys.path.insert(0, str(args.ppu_source.resolve() / "src"))
    from pluto_plus.hardware.pilot_iio import PilotSnapshot

    count = 6 * args.samples + 600
    records = [write(8, 4), write(0x20, 17), write(0x9c, args.samples), write(8, 1),
               (1, 9, 0, count, 0), (2000, 7, 0, 0, 0), *snapshot()]
    print(f"PIL1 RTL dwell started canonical_samples={count} output_limit={args.samples}",
          flush=True)
    with tempfile.TemporaryDirectory(prefix="starlink-pil1-dwell-") as directory:
        simulator = compile_simulator(Path(directory), watchdog_cycles=7 * count + 10_000)
        outputs, reads, final = run(simulator, records, timeout=600)
    regs = dict(reads)
    expected = PilotDdcOracle("upper").process(cw_samples(count), first_index=0)
    actual = np.asarray(outputs, dtype="<i2")
    np.testing.assert_array_equal(actual, expected.samples_iq[expected.support_valid][:args.samples])
    if final != (0, 0) or u64(regs, 0x40) != args.samples or u64(regs, 0x48) != args.samples:
        raise RuntimeError("capture did not auto-stop/drain exactly without faults")
    # Exercise the real PPU parser using REAL RTL snapshot words. The kernel
    # header is constructed here; no Linux driver or IIO device was exercised.
    wire = f"PIL1 00010000 15000000 2500000 {regs[0x98]} 0 15000000 0 " + " ".join(
        f"{regs[address]:08x}" for address in range(0x30, 0x98, 4)) + "\n"
    decoded = PilotSnapshot.decode(wire)
    decoded.require_complete_prefix(expected_visit_id=17, expected_source_rate_hz=15_000_000,
                                    expected_samples=args.samples, received_bytes=actual.nbytes)
    evidence = {
        "schema": "starlink-pil1-finite-dwell-rtl-v1",
        "canonical_source_rate_hz": 15_000_000,
        "output_rate_hz": 2_500_000,
        "input_samples_driven": count,
        "supported_output_samples": len(outputs),
        "exposure_seconds": str(decoded.axis_prefix_duration_seconds),
        "first_newest_canonical_index": decoded.first_newest_canonical_index,
        "last_newest_canonical_index": decoded.last_newest_canonical_index,
        "first_source_center": decoded.source_center(0),
        "last_source_center": decoded.source_center(len(outputs) - 1),
        "ddc_accepted_samples": decoded.ddc_accepted_samples,
        "ddc_emitted_samples": decoded.ddc_emitted_samples,
        "unsupported_samples": decoded.unsupported_samples,
        "export_fifo_high_water": decoded.words[21],
        "saturation_events": decoded.saturation_events,
        "capture_faults": decoded.capture_faults,
        "ddc_faults": decoded.ddc_faults,
        "rtl_snapshot_with_synthetic_kernel_header": wire.strip(),
        "kernel_header_executed": False,
        "ppu_offline_parser_verified": True,
        "axis_replay_bytes_not_iio": actual.nbytes,
        "iq_ci16_sha256": hashlib.sha256(actual.tobytes()).hexdigest(),
        "every_iq_sample_matches_integer_oracle": True,
        "hardware_accessed": False,
        "iio_capture_qualified": False,
        "live_glrt_evidence": False,
        "fpga_pss_lock": False,
        "sha256": {},
    }
    sources = [Path(__file__), ppu_file, ROOT / "tests/starlink_oracle/test_pilot_capture_rtl.py",
               ROOT / "hdl/library/axi_starlink_pilot_capture/axi_starlink_pilot_capture.v",
               ROOT / "hdl/library/axi_starlink_pilot_capture/tb/tb_starlink_pilot_capture.sv"]
    sources += [ROOT / "hdl/library/starlink_pss_acquisition" / name for name in (
        "starlink_pilot_ddc.v", "starlink_pilot_halfband2.v", "starlink_pilot_fir3.v",
        "pilot_mixer_q16.mem", "pilot_halfband2_q17.mem", "pilot_fir3_q17.mem")]
    evidence["sha256"] = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in sources}
    with args.output.open("x") as stream:
        json.dump(evidence, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(f"PIL1_RTL_DWELL_PASS samples={len(outputs)} exact_iq=1 ppu_offline_parser=1 "
          f"hardware_qualified=0 report={args.output}")


if __name__ == "__main__":
    main()

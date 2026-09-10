"""Export one closed native journal for recording consumers, without radio access.

The additive JSON port preserves all associated fits and arithmetic evidence.
An epoch is local to this journal; recording owners must separately bind the
radio, boot and coarse source. Reviewing a journal does not replay its solver
or prove the original native IQ, acquisition, or physical precision.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import tempfile

from .starlink_glrt_native_abi import RATE, SAMPLES
from .starlink_glrt_native_journal import review


def export_journal(data: bytes, *, epoch: int) -> dict:
    if type(epoch) is not int or not 0 < epoch < 2**32:
        raise ValueError("recording export requires a nonzero u32 source epoch")
    checked = review(data, epoch=epoch)
    measurements = []
    for head, estimate in zip(checked["heads"], checked["estimates"], strict=True):
        measurements.append({
            **estimate,
            "supported": estimate["rejection"] == 0,
            "tag": head.tag,
            "repeat": head.repeat,
            # Decimal strings preserve exact u64/69-bit values in browser JSON.
            "native_start_sample": str(head.start),
            "phase_seed_q32": head.phase_seed,
            "phase_step_q32": head.phase_step,
            "sample_count": head.count,
            "hardware_fault": head.fault,
            "reference_sum": [str(v) for v in head.reference_sum],
            "delay_sum": [str(v) for v in head.delay_sum],
            "reference_prefix_integral": [str(v) for v in head.reference_prefix_integral],
            "observed_energy": str(head.observed_energy),
        })
    descriptors = []
    for first, batch in checked["descriptors"].values():
        descriptors.append({"first_frame": first, "epoch": batch.epoch,
            "tag": batch.tag, "start_sample": str(batch.start),
            "start_fraction_q16": batch.fraction, "period_q16": batch.period,
            "phase_step_q32_16": batch.step, "phase_delta_q32_16": batch.delta,
            "phase_seed_q32": batch.seed, "repeats": batch.repeats,
            "expires_sample": str(batch.expires)})
    def snapshot(state):
        return {**asdict(state), "latest_index": str(state.latest_index)}
    return {
        "schema": "starlink-glrt-native-journal-recording/v1",
        "journal_sha256": hashlib.sha256(data).hexdigest(),
        "journal_bytes": len(data), "epoch": epoch,
        "epoch_scope": "journal_local_requires_radio_boot_binding",
        "source_rate_hz": RATE, "pilot_samples": SAMPLES,
        "pilot_center_offset_samples_twice": SAMPLES-1,
        "timing_rule": "native_start_sample + delay_s * source_rate_hz",
        "frequency_reference": "receiver_relative_uncalibrated",
        "timing_reference": "native_pilot_template",
        "association_and_closure_verified": True,
        "solver_replayed": False, "original_native_iq_verified": False,
        "acquisition_verified": False, "physical_precision_qualified": False,
        "descriptor_semantics": "retained_intent_execution_accounted_by_heads_and_drained",
        "head_count": len(measurements), "supported_count": checked["supported"],
        "rejected_count": len(measurements)-checked["supported"],
        "descriptors": descriptors, "measurements": measurements,
        "drained": snapshot(checked["drained"]), "final": snapshot(checked["final"]),
    }


def write_recording(journal: Path, output: Path, *, epoch: int) -> dict:
    # Bound memory even if a producer appends while a closed journal is expected.
    with journal.open("rb") as stream:
        data = stream.read(128*1024*1024+1)
    result = export_journal(data, epoch=epoch)
    # The visible artifact is complete or absent, and an existing recording is
    # never overwritten. Both names reside on the same destination filesystem.
    fd, temporary = tempfile.mkstemp(prefix=".native-recording-", dir=output.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, output)
        directory = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        os.unlink(temporary)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--epoch", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = write_recording(args.journal, args.output, epoch=args.epoch)
    print(json.dumps({key: result[key] for key in
        ("schema", "journal_sha256", "head_count", "supported_count", "rejected_count")}))


if __name__ == "__main__":
    main()

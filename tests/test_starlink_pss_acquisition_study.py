from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

from tests.starlink_oracle import projected_pss, quantize_q15


def test_acquisition_study_writes_a_reproducible_bounded_report(tmp_path: Path) -> None:
    coefficients = quantize_q15(projected_pss(15_000_000, "upper"))
    frame_samples = 20_000
    epoch = 1_234
    samples = np.zeros((4 * frame_samples + coefficients.shape[0] - 1, 2), dtype=np.int16)
    for frame in range(4):
        start = epoch + frame * frame_samples
        samples[start : start + coefficients.shape[0]] = coefficients
    input_path = tmp_path / "fixture.ci16"
    input_path.write_bytes(np.asarray(samples, dtype="<i2").tobytes())
    output_path = tmp_path / "report.json"

    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path.cwd())
    subprocess.run(
        (
            sys.executable,
            "tools/starlink_pss_acquisition_study.py",
            str(input_path),
            "--edge",
            "upper",
            "--score-bits",
            "8",
            "--phase-bin-samples",
            "1",
            "4",
            "--tile-frames",
            "4",
            "--maximum-period-error-ppm",
            "0",
            "--expected-phase-sample",
            str(epoch),
            "--generated-at-utc",
            "2026-09-02T18:00:00+00:00",
            "--output",
            str(output_path),
        ),
        check=True,
        cwd=Path.cwd(),
        env=environment,
        capture_output=True,
        text=True,
    )

    report = json.loads(output_path.read_text())
    assert report["schema"] == "starlink-pss-acquisition-oracle-v1"
    assert report["candidate_only"] is True
    assert report["over_the_air_starlink_pss_qualified"] is False
    assert report["generated_at_utc"] == "2026-09-02T18:00:00+00:00"
    assert report["input"]["compressed_sha256"] == hashlib.sha256(
        input_path.read_bytes()
    ).hexdigest()
    assert report["score_stream"]["score_bits"] == 8
    assert report["score_stream"]["valid_outputs_per_fft"] == 447
    assert len(report["matched"]) == 2
    one_sample = report["matched"][0]
    assert one_sample["phase_bin_samples"] == 1
    assert one_sample["candidate"]["phase_bin_start_sample"] == epoch
    assert one_sample["candidate"]["phase_error_samples"] == 0.0
    assert one_sample["candidate"]["passes_existing_epoch_gates"] is True
    assert len(report["frame_scrambled_negative_control"]["results"]) == 2

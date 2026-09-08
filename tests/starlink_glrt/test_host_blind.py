"""Independent acquisition tests using the explicitly pinned Leo environment."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import numpy as np
import pytest

from .pilot import frame
from tools.starlink_glrt_host import score_support, window_starts

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "artifacts/host-reference-5f25fc57"


def invoke(iq, output, edge="upper"):
    python = REFERENCE / ".venv/bin/python"
    assert python.is_file(), "explicit pinned host GLRT test dependency is unavailable"
    return subprocess.run([str(python), str(ROOT / "tools/starlink_glrt_host.py"),
                           "--leo-source", str(REFERENCE), "--iq", str(iq), "--edge", edge,
                           "--minimum-exact", "0.6", "--minimum-margin", "0.3",
                           "--output", str(output)], capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize("edge,cfo,epoch", [("upper", -90_000, 391), ("upper", 90_000, 3330),
                                           ("lower", -90_000, 3330), ("lower", 90_000, 391)])
def test_blind_host_recovers_timing_and_cfo_without_fpga_inputs(edge, cfo, epoch, tmp_path):
    # The stimulus is from the separately frozen firmware-test template. Truth
    # is used only here after the CLI has completed its unseeded acquisition.
    rate, count = 2_500_000, 20_000
    pilot = frame(rate, edge)
    rng = np.random.default_rng(98217)
    values = 80 * (rng.normal(size=count) + 1j * rng.normal(size=count))
    for number in range(8):
        start = epoch + round(number * rate / 750)
        if start >= count:
            break
        stop = min(count, start + len(pilot))
        values[start:stop] += 4000 * pilot[:stop-start]
    values *= np.exp(2j*np.pi*cfo*np.arange(count)/rate)
    raw = np.rint(np.column_stack((values.real, values.imag)))
    assert np.max(np.abs(raw)) < 32768
    iq, output = tmp_path / "iq.ci16", tmp_path / "analysis"
    raw.astype("<i2").tofile(iq)
    result = invoke(iq, output, edge)
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads((output / "summary.json").read_text())
    assert summary["complete"] == summary["windows_with_engineering_positive"] == 1
    assert summary["transport_qualified"] is False and summary["hardware_qualified"] is False
    rows = [json.loads(line) for line in (output / "blind-windows.jsonl").read_text().splitlines()]
    winner = next(c for c in rows[0]["candidates"] if c["acquisition"]["rank"] == rows[0]["winner_rank"])
    assert winner["engineering_positive"]
    difference = winner["acquisition"]["refined_epoch_sample"] - epoch
    circular_error = (difference + rate/1500) % (rate/750) - rate/1500
    assert abs(circular_error) <= 1
    assert abs(winner["glrt64"]["tracking_cfo_hz"] - cfo) <= 1000
    assert all(0 <= left < right <= count for left, right in winner["score_support_output_samples"])


@pytest.mark.parametrize("kind", ["noise", "tone", "short"])
def test_blind_controls_and_short_support_remain_explicit(kind, tmp_path):
    count = 500 if kind == "short" else 20_000
    rng = np.random.default_rng(71711)
    values = 500 * (rng.normal(size=count) + 1j*rng.normal(size=count))
    if kind == "tone":
        values += 9000 * np.exp(2j*np.pi*350_000*np.arange(count)/2_500_000)
    iq, output = tmp_path / "iq.ci16", tmp_path / "analysis"
    np.rint(np.column_stack((values.real, values.imag))).astype("<i2").tofile(iq)
    result = invoke(iq, output)
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads((output / "summary.json").read_text())
    assert summary["windows_with_engineering_positive"] == 0
    assert summary["insufficient"] == int(kind == "short")


def test_truncated_ci16_is_rejected_and_support_mapping_retains_frame_rounding(tmp_path):
    iq, output = tmp_path / "bad.ci16", tmp_path / "analysis"
    iq.write_bytes(b"123")
    result = invoke(iq, output)
    assert result.returncode != 0 and "whole number" in result.stderr
    assert not output.exists()
    assert list(window_starts(60_001)) == [0, 25_000, 50_000]
    assert score_support(17, 7500, 50_000) == [[50039, 50743], [53372, 54076], [56706, 57410]]

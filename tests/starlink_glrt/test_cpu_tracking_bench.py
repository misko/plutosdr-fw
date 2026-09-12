"""Actual saved-IQ executable: blind scan through resolution and supported history."""
import json
import os
from pathlib import Path
import subprocess

import numpy as np
import pytest

from tools.generate_glrt_tracking_gram import reference_rows
from .test_tracking_seed import SOURCES
from .test_cpu_coarse import bank as coarse_bank

pytestmark = pytest.mark.fftw


@pytest.fixture(scope="module")
def bench(tmp_path_factory):
    root = Path(__file__).resolve().parents[2]
    out = tmp_path_factory.mktemp("cpu-tracking-bench")
    prefix = os.environ.get("GLRT_FFTW_PREFIX")
    includes = ["-I", str(Path(prefix)/"include")] if prefix else []
    libraries = ["-L", str(Path(prefix)/"lib"), "-Wl,-rpath,"+str(Path(prefix)/"lib")] if prefix else []
    names = ["glrt_cpu_tracking_bench.c", "glrt_cpu_coarse.c", "glrt_cpu_seed.c",
             "glrt_tracking_worker.c", "glrt_tracking_live_bootstrap.c", "glrt_tracking_iq.c", *SOURCES]
    subprocess.run(["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread", *includes,
                    *(str(root/"tools"/name) for name in names), *libraries, "-lfftw3", "-lm",
                    "-o", str(out/"bench")], check=True)
    bank = root/"hdl/library/starlink_glrt"
    refs = np.asarray([reference_rows((bank/"native_cubic_60000000_upper.mem").read_bytes(),
        (bank/"native_direct_2500000_phase4_upper_interleaved.mem").read_bytes(), 2500000, p)
        for p in range(4)], dtype="<i2")
    refs.tofile(out/"refs")
    coarse_bank().astype("<i2").tofile(out/"bank")
    return out, refs


@pytest.mark.parametrize("signal", [False, True])
def test_complete_chain_with_pilots_and_zero_control(bench, tmp_path, signal):
    out, refs = bench
    iq = np.zeros((2621440, 2), dtype="<i2")
    if signal:
        for n in range(800):
            start = 22+(n*10000+1)//3
            if start+3300 <= len(iq): iq[start:start+3300] = refs[0, :, :2]
    iq.tofile(tmp_path/"iq")
    run = subprocess.run([str(out/"bench"), str(out/"bank"), str(tmp_path/"iq"), str(tmp_path/"grid"),
                          str(out/"refs")], capture_output=True, text=True, timeout=30)
    rows = [json.loads(line) for line in run.stdout.splitlines()]
    if not signal:
        assert run.returncode == 0
        terminal = [row for row in rows if row.get("kind") == "terminal"]
        assert len(terminal) == 4
        assert all(row["disposition"] == "no_candidate" and row["fft_calls"] == 0 for row in terminal)
        return
    assert run.returncode == 0, run.stdout+run.stderr
    terminal = [row for row in rows if row.get("kind") == "terminal"]
    assert len(terminal) == 4
    assert all(row["worker_result"] == 1 and row["supported_history"] >= 8 for row in terminal)
    assert all(row["fft_calls"] == 68 for row in terminal)
    assert rows[-1]["receiver_time"] == "frozen_snapshot" and not rows[-1]["live_tracking_qualified"]
    assert (tmp_path/"grid").stat().st_size == 4*11*3333*4

"""Drop the old proposer/scorer while preserving the reference IQ exporter."""
import re
import subprocess

import numpy as np
import pytest

from .ddc import BANK_ROOT
from .test_ddc_rtl import records
from .test_receiver_rtl import BENCH, observation, run


@pytest.fixture(scope="module")
def iq_only_receiver(tmp_path_factory):
    root = tmp_path_factory.mktemp("iq-only-receiver")
    bench = BENCH.replace(".SOURCE_RATE_HZ(RATE)",
        ".SOURCE_RATE_HZ(2500000),.ENABLE_LEGACY_SCORER(0),.ENABLE_ACQUISITION(0)")
    # Remove debug probes into the deliberately absent native scorer.
    start = bench.index('  if(dut.selected_valid && $test$plusargs("TRACE"))')
    end = bench.index("  #1;", start)
    bench = bench[:start] + bench[end:]
    bench = bench.replace(' $finish;',
        ' if(!detector_settled || processing_pending || stage_fault) $fatal(1,"not settled");\n $finish;')
    (root / "tb.sv").write_text(bench)
    executable = root / "sim"
    built = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable),
        str(root / "tb.sv"), *map(str, sorted(BANK_ROOT.glob("*.v")))], capture_output=True, text=True)
    assert built.returncode == 0, built.stdout + built.stderr
    modules = re.findall(r'\.scope module, "[^"]+" "([^"]+)"', executable.read_text())
    assert modules.count("starlink_glrt_ddc") == 1
    for removed in ("starlink_glrt_acquisition", "starlink_glrt_candidate_select", "starlink_glrt_correlator",
                    "starlink_glrt_score", "starlink_glrt_vector_stage", "starlink_glrt_fir_decimator"):
        assert removed not in modules
    return executable


@pytest.mark.parametrize("kind", ["positive", "noise"])
def test_iq_is_unchanged_and_no_legacy_work_is_reported(tmp_path, iq_only_receiver, kind):
    raw, _, _ = observation(2500000, kind)
    streams = run(iq_only_receiver, records(raw, 2500000) + ["0 0 2 0 0 0 0"] * 8, tmp_path)
    output = np.asarray(streams["O"], dtype=np.int64)
    np.testing.assert_array_equal(output[:, 1:3], raw)
    np.testing.assert_array_equal(output[:, 0], np.arange(len(raw)) + output[0, 0])
    assert np.all(output[:, 3] == 1)
    assert not streams["P"] and not streams["C"] and not streams["G"]
    assert streams["S"] == [(len(raw), len(raw)) + (0,) * 16]

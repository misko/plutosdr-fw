"""Existing DSP TRACK_ONE alternative at low rates; no receiver timing claim."""

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HDL = Path(os.environ.get("STARLINK_PSS_TEST_HDL", str(ROOT / "hdl")))
LIB = "library/starlink_pss_raw_correlator"
BASE = "6ee01b7c399f06765ea387720a5c3ccfa6e62de1"
CORE = "starlink_pss_reduced_tracking_core.v"
CHOICE = "if (RATE_MULTIPLIER == 4) begin : g_dsp_exact_reducer"
COMMON = ["ad_mem.v", "starlink_pss_async_fifo.v", "starlink_sat_add48.v",
          "starlink_pss_candidate_scheduler.v", "starlink_pss_capture_bridge.v",
          "starlink_pss_sliding_correlator.v", "starlink_pss_tracking_core.v",
          "starlink_pss_exact_reducer.v", "starlink_pss_exact_track_reducer.v",
          "starlink_pss_result_store.v"]


def frozen(name):
    path = f"library/common/{name}" if name == "ad_mem.v" else f"{LIB}/{name}"
    return subprocess.run(["git", "-C", str(HDL), "show", f"{BASE}:{path}"],
                          check=True, capture_output=True, text=True, timeout=10).stdout


def replace_once(source, old, new):
    assert source.count(old) == 1
    return source.replace(old, new, 1)


def test_current_selection_changes_no_reducer_math_or_other_core_logic():
    for name in ["starlink_pss_exact_reducer.v", "starlink_pss_exact_track_reducer.v"]:
        assert (HDL / LIB / name).read_text() == frozen(name)

    def tokens(text):
        return re.sub(r"\s+", "", re.sub(r"//[^\n]*", "", text))

    source = tokens((HDL / LIB / CORE).read_text())
    source = replace_once(source, ",parameterintegerUSE_DSP_REDUCER=(RATE_MULTIPLIER==4)", "")
    source = replace_once(source,
        'if((USE_DSP_REDUCER!=0)&&(USE_DSP_REDUCER!=1))begin:g_invalid_reducer_choice'
        'initial$fatal(1,"USE_DSP_REDUCERmustbe0or1");end', "")
    source = replace_once(source, "if(USE_DSP_REDUCER)begin:g_dsp_exact_reducer",
                         tokens(CHOICE))
    assert source == tokens(frozen(CORE))


def simulate(directory, sources, top, parameters=()):
    directory.mkdir(parents=True)
    (directory / "build").mkdir()
    paths = []
    for name, contents in sources.items():
        path = directory / name
        path.write_text(contents)
        if path.suffix in {".v", ".sv"}:
            paths.append(str(path))
    executable = directory / "bench.vvp"
    subprocess.run(["iverilog", "-g2012", "-Wall", "-s", top, *parameters,
                    "-o", str(executable), *paths], check=True, capture_output=True,
                   text=True, timeout=30)
    result = subprocess.run(["vvp", str(executable)], cwd=directory,
                            capture_output=True, text=True, timeout=40, check=False)
    (directory / "simulation.log").write_text(result.stdout + result.stderr)
    return result


def composed_bench(rate):
    bench = frozen("tb/tb_starlink_pss_reduced_tracking_core.sv")
    if rate == 4:
        # The original low-rate fixture's center=400 leaves <256 samples of
        # lead before the 60 MS/s capture START after command synchronization.
        # Move the known stimulus/expected winner together, retaining the real
        # scheduler's lead check and the original publication timeout.
        bench = replace_once(bench, "CENTER_INDEX = 64'd400;", "CENTER_INDEX = 64'd1600;")
        bench = replace_once(bench, "WINNER_SAMPLE_INDEX = 400 +", "WINNER_SAMPLE_INDEX = 1600 +")
    return bench


@pytest.mark.parametrize("rate", [1, 2, 4])
@pytest.mark.parametrize("dsp", [False, True])
def test_frozen_complete_track_one_packet_and_accounting(tmp_path, rate, dsp):
    core = frozen(CORE)
    assert core.count(CHOICE) == 1
    if dsp:
        core = replace_once(core, CHOICE, "if (1) begin : g_dsp_exact_reducer")
    sources = {name: frozen(name) for name in COMMON}
    sources[CORE] = core
    sources["bench.sv"] = composed_bench(rate)
    result = simulate(tmp_path / "run", sources, "tb_starlink_pss_reduced_tracking_core",
                      [f"-Ptb_starlink_pss_reduced_tracking_core.RATE_MULTIPLIER={rate}"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("REDUCED_TRACKING_PASS") == 1
    assert f"rate_multiplier={rate} jobs=1" in result.stdout
    assert "packet_words=26 score=absC2_over_Ex" in result.stdout


@pytest.mark.parametrize("rate,dsp", [(rate, dsp) for rate in [1, 2]
                                     for dsp in [None, 0, 1]] + [(4, None), (4, 1)])
def test_current_core_defaults_and_explicit_choices(tmp_path, rate, dsp):
    sources = {name: (HDL / ("library/common" if name == "ad_mem.v" else LIB) / name).read_text()
               for name in COMMON}
    sources[CORE] = (HDL / LIB / CORE).read_text()
    bench = composed_bench(rate)
    if dsp is not None:
        bench = replace_once(bench, ".RATE_MULTIPLIER (RATE_MULTIPLIER)",
                             f".RATE_MULTIPLIER (RATE_MULTIPLIER), .USE_DSP_REDUCER({dsp})")
    sources["bench.sv"] = bench
    result = simulate(tmp_path / "run", sources, "tb_starlink_pss_reduced_tracking_core",
                      [f"-Ptb_starlink_pss_reduced_tracking_core.RATE_MULTIPLIER={rate}"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("REDUCED_TRACKING_PASS") == 1


@pytest.mark.parametrize("rate", [15, 30, 60])
def test_actual_axi_wrapper_with_explicit_dsp_choice(tmp_path, rate):
    sources = {name: (HDL / ("library/common" if name == "ad_mem.v" else LIB) / name).read_text()
               for name in COMMON}
    sources[CORE] = (HDL / LIB / CORE).read_text()
    sources["up_axi.v"] = (HDL / "library/common/up_axi.v").read_text()
    wrapper_dir = HDL / "library/axi_starlink_pss_tracker"
    for name in ["starlink_pss_injection_mux.v", "axi_starlink_pss_tracker.v"]:
        sources[name] = (wrapper_dir / name).read_text()
    bench = (wrapper_dir / "tb/tb_axi_starlink_pss_tracker.sv").read_text()
    sources["bench.sv"] = replace_once(bench, ".RATE_MSPS       (RATE_MSPS),",
                                        ".RATE_MSPS       (RATE_MSPS), .USE_DSP_REDUCER(1),")
    result = simulate(tmp_path / "run", sources, "tb_axi_starlink_pss_tracker",
                      [f"-Ptb_axi_starlink_pss_tracker.RATE_MSPS={rate}"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "AXI_TRACKER_PASS" in result.stdout


def test_actual_dsp_wrapper_preserves_all_210_recorded_window_packets(tmp_path):
    sources = {name: (HDL / ("library/common" if name == "ad_mem.v" else LIB) / name).read_text()
               for name in COMMON}
    sources[CORE] = (HDL / LIB / CORE).read_text()
    sources["up_axi.v"] = (HDL / "library/common/up_axi.v").read_text()
    wrapper_dir = HDL / "library/axi_starlink_pss_tracker"
    for name in ["starlink_pss_injection_mux.v", "axi_starlink_pss_tracker.v"]:
        sources[name] = (wrapper_dir / name).read_text()
    bench = (wrapper_dir / "tb/tb_axi_starlink_pss_tracker_real_replay.sv").read_text()
    bench = replace_once(bench, "axi_starlink_pss_tracker dut (",
                         "axi_starlink_pss_tracker #(.USE_DSP_REDUCER(1)) dut (")
    for old, path in [
        ("../starlink_pss_raw_correlator/tb/upper_minus100k_coefficients_q15.mem",
         HDL / LIB / "tb/upper_minus100k_coefficients_q15.mem"),
        ("tb/real_071200_wrapper_samples_ci16.mem", wrapper_dir / "tb/real_071200_wrapper_samples_ci16.mem"),
        ("tb/real_071200_wrapper_packets.mem", wrapper_dir / "tb/real_071200_wrapper_packets.mem"),
    ]:
        sources[path.name] = path.read_text()
        bench = replace_once(bench, f'"{old}"', f'"{path.name}"')
    sources["bench.sv"] = bench
    result = simulate(tmp_path / "run", sources, "tb_axi_starlink_pss_tracker_real_replay")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "AXI_REAL_REPLAY_PASS windows=210 fixed_float_lag_matches=210" in result.stdout
    assert "packet_words=5460 aperture=-30..30 errors=0" in result.stdout
    assert "ERROR" not in result.stdout + result.stderr


def reducer_workload(directory, dsp, mutation=None):
    bench = frozen("tb/tb_starlink_pss_exact_reducer.sv")
    # Preserve the original five workload patterns, oracle, stalls, malformed
    # tail and exact error counters. Select only TRACK_ONE's include-Eh=false
    # contract; the DSP reducer intentionally does not support include-Eh=true.
    for pattern in range(1, 5):
        bench = replace_once(bench, f"drive_job({pattern}, 1'b1,",
                             f"drive_job({pattern}, 1'b0,")
    if dsp:
        bench = replace_once(bench, "starlink_pss_exact_reducer dut (",
                             "starlink_pss_exact_track_reducer #(.RATE_MULTIPLIER(1)) dut (")
    bench = replace_once(bench, "      result_ready = 1'b1;",
                         '      $display("EXACT_TRACK_PACKET %h", held_result);\n'
                         "      result_ready = 1'b1;")
    module = "starlink_pss_exact_track_reducer.v" if dsp else "starlink_pss_exact_reducer.v"
    source = frozen(module)
    if mutation:
        source = replace_once(source, *mutation)
    return simulate(directory, {module: source, "bench.sv": bench},
                    "tb_starlink_pss_exact_reducer")


def test_frozen_serial_and_dsp_exact_winners_match(tmp_path):
    traces = []
    for dsp in [False, True]:
        result = reducer_workload(tmp_path / str(dsp), dsp)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "EXACT_REDUCER_PASS jobs=5 emitted=5 invalid=61 bound=3 protocol=1" in result.stdout
        packets = re.findall(r"^EXACT_TRACK_PACKET ([0-9a-f]+)$", result.stdout, re.MULTILINE)
        assert len(packets) == 5  # Also rejects any X/Z in promised packet data.
        traces.append(packets)
    assert traces[0] == traces[1]


@pytest.mark.parametrize("mutation", [
    ("left_cross_product > multiply_product", "left_cross_product >= multiply_product"),
    ("winner_ex <= current_ex;", "winner_ex <= current_ex + 1'b1;"),
])
def test_exact_winner_workload_rejects_dsp_mutations(tmp_path, mutation):
    result = reducer_workload(tmp_path / "mutated", True, mutation)
    assert result.returncode != 0 and "EXACT_REDUCER_FAIL" in result.stdout
    assert "EXACT_REDUCER_PASS" not in result.stdout

"""Offline admission, compile-only and synthetic receipts; no native60 service.

The parser specimen uses invented in-bound cycles and frozen oracle words. It
is labeled PARSER_ONLY on disk; no simulator or measured service is involved.
The tiny independent clock/XZ test has no native modules or job.
"""

import json
import re
import shutil
import subprocess
from fractions import Fraction

import pytest

from tests.starlink_oracle import native60_budget as nb
from tests.starlink_oracle.native60_budget_recipe import recipe


@pytest.fixture(scope="session")
def bundle(tmp_path_factory):
    output = tmp_path_factory.mktemp("native60_offline_inputs") / "bundle"
    nb.prepare(output)
    return output


def line(name, values, hex_fields=()):
    return name + " " + " ".join(f"{key}={value:08x}" if key in hex_fields else f"{key}={value}"
                                  for key, value in values.items())


def specimen(output, bundle):
    """PARSER ONLY: no measured cycles, no fake run-status or terminal receipt."""
    output.mkdir()
    (output / "PARSER_ONLY.json").write_text(json.dumps({"synthetic_parser_specimen": True, "actual_RTL_run": False}))
    records = [
        line("NATIVE60_CONFIG", {"cycle": 10000, "id": 0x50535354, "abi": 0x10003, "rate": 60,
            "geometry": 0x0F8C1108, "caps": 0x1D, "generation": 0x60000001, "eh": 1073758594},
            {"id", "abi", "geometry", "caps", "generation"}),
        line("NATIVE60_ADMISSION", {"index": 34359738608, "center": 34359740384,
            "capture_first": 34359740256, "lead": 1647, "trigger_cycle": 15600, "handshake_cycle": 15680,
            "request": 0x60000520, "generation": 0x60000001}, {"request", "generation"}),
        line("NATIVE60_SOURCE_OFF", {"cycle": 37372, "source": 16423, "first": 34359735211,
            "stop": 34359751634, "capture": 520, "busy": 1}),
    ]
    packet = (bundle / "native_expected_packet.mem").read_text().splitlines()
    records += [f"NATIVE60_PACKET_WORD pass={p} word={n} data={v}" for p in range(2) for n, v in enumerate(packet)]
    records += [
        line("NATIVE60_RELEASE", {"cycle": 97800, "raw": 253, "qualified": 241, "packet_reads": 52,
            "retained_cycles": 32, "settle_cycles": 24, "irq": 0, "available": 0}),
        line("NATIVE60_DRAIN", {"cycle": 99100, "raw": 257, "qualified": 241, "engine_idle": 1, "bridge_idle": 1}),
        line("NATIVE60_BUDGET", {"capture_end": 19275, "publish": 97000, "drain": 99100, "release": 97800,
            "source_off": 37372, "quiet_start": 99101, "quiet_end": 99357, "raw_at_publish": 249, "raw_after_publish": 8,
            "maximum_axi": 8, "readout_transactions": 105, "source_off_compute": 61728, "maximum_tuple_hold": 13}),
        line("NATIVE60_CLOCK", {"first_edge_fs": 10433333, "first_fall_fs": 18766666, "half_fs": 8333333,
            "period_fs": 16666666, "control_period_fs": 10000000, "source_edges": 59614, "after_off_edges": 37191, "quiet_edges": 154}),
        line("NATIVE60_PASS", {"source": 16423, "capture": 520, "raw": 257, "qualified": 241, "packet_reads": 52,
            "admissions": 1, "health": 0, "source_stopped": 1, "clock_running": 1, "idle": 1, "irq": 0, "available": 0,
            "actual_native": 1, "actual_fft": 0, "actual_psma": 0, "actual_pil1": 0, "static_center": 1}),
    ]
    (output / "simulation.log").write_text("\n".join(records) + "\n")
    rows = json.loads((bundle / "native_all_raw_tuples.json").read_text())
    (output / "native60_actual_raw_tuples.txt").write_text("".join(
        f'{r["lag"]} {r["start_index"]:016x} {r["real"] & ((1<<48)-1):012x} '
        f'{r["imag"] & ((1<<48)-1):012x} {r["Ex"]:012x} {r["Eh"]:012x} {r["power"]:024x} '
        f'{r["saturation"]:03x} {int(r["qualified"])}\n' for r in rows))
    (output / "native60_actual_holds.txt").write_text("".join(f'{r["lag"]} {13 if r["qualified"] else 0}\n' for r in rows))
    indexes = (bundle / "source_index_u64.mem").read_text().splitlines()
    data = (bundle / "source_ci16.mem").read_text().splitlines()
    (output / "native60_actual_source.txt").write_text("".join(f"{i} {d}\n" for i, d in zip(indexes, data, strict=True)))
    capture = (bundle / "native_capture_ci16.mem").read_text().splitlines()
    (output / "native60_actual_capture.txt").write_text("".join(
        f"{n} {34359740256+n:016x} {34359740256+n:016x} {v}\n" for n, v in enumerate(capture)))
    return output


@pytest.fixture
def synthetic(tmp_path, bundle):
    return specimen(tmp_path / "PARSER_ONLY_NOT_MEASURED", bundle)


def replace_field(directory, marker, field, value):
    path = directory / "simulation.log"
    lines = path.read_text().splitlines()
    matching = [n for n, entry in enumerate(lines) if entry.startswith(marker + " ")]
    assert len(matching) == 1
    n = matching[0]
    lines[n], count = re.subn(r"\b" + field + r"=[^ ]+", field + "=" + str(value), lines[n])
    assert count == 1
    path.write_text("\n".join(lines) + "\n")


def test_budget_full_state_chain_and_original_support():
    b = nb.budget()
    assert b["derived_engine_cycles"] == 3*520+64 + 520+16 + 257*(264+16+16)+128 == 78360
    assert b["derived_post_capture_cycles"] == 84000+140*24+56 == 87416
    assert b["raw_after_capture"] == 34359751634-34359740776 == 10858
    assert b["raw_after_capture_engine_cycles_floor"] == 18096
    assert b["raw_after_capture_engine_cycles_floor"] < recipe()["post_capture_limit_cycles"]
    assert Fraction(1_000_000_000, 60) - 2*8333333 == Fraction(2, 3)
    assert recipe()["native_raw_count"]-recipe()["native_qualified_count"] == 16
    assert 128-120 == 8


@pytest.mark.parametrize("key", list(recipe()))
def test_every_recipe_field_is_admission_not_hint(key):
    candidate = recipe()
    value = candidate[key]
    candidate[key] = not value if isinstance(value, bool) else value+1 if isinstance(value, int) else "mutant"
    with pytest.raises(ValueError, match="unadmitted"):
        nb.budget(candidate)


@pytest.mark.parametrize("key", [key for key, value in recipe().items() if isinstance(value, (int, bool))])
def test_recipe_rejects_numeric_type_aliases(key):
    candidate = recipe()
    candidate[key] = int(candidate[key]) if isinstance(candidate[key], bool) else float(candidate[key])
    with pytest.raises(ValueError, match="unadmitted"):
        nb.budget(candidate)


def test_exact_old76_plus_new_source_closure_and_imports(bundle):
    r = nb.verify(bundle)
    assert len(r["source_sha256"]) == 87
    assert len(nb.check_cohort(bundle)["files"]) == 69
    assert set(nb.NATIVE_SOURCES) <= r["source_sha256"].keys()
    assert {"tests/starlink_oracle/__init__.py", "tests/starlink_oracle/xfft_bitacc.py",
            "tests/starlink_oracle/native60_budget_recipe.py"} <= r["python_import_edges"].keys()
    for name, value in r["source_sha256"].items():
        assert r["files"]["source_snapshot/"+name] == value == nb.sha((nb.ROOT/name).read_bytes())
    with pytest.raises(ValueError, match="overwrite"):
        nb.prepare(bundle)


@pytest.mark.parametrize("name", ["source_ci16.mem", "source_index_u64.mem", "native_coefficients_q15.mem",
    "native_capture_ci16.mem", "native_expected_packet.mem", "native_raw_lags_s32.mem", "native_raw_start_u64.mem",
    "native_raw_power_u96.mem", "native_raw_saturation_u12.mem", "native_all_raw_tuples.json",
    "recipe.json", "source_snapshot/"+nb.TOP, "source_snapshot/"+nb.CHECKS, "source_snapshot/"+nb.AXI])
def test_bundle_bytes_are_not_mutable_hints(bundle, tmp_path, name):
    altered = tmp_path / "altered"
    shutil.copytree(bundle, altered)
    path = altered / name
    path.write_bytes(path.read_bytes()+b"\n")
    with pytest.raises(ValueError):
        nb.verify(altered)


@pytest.mark.parametrize("kind", ["source_lie", "omit_source", "extra_file", "symlink", "bad_cohort", "bad_recipe", "imports", "measured"])
def test_self_consistent_manifest_does_not_bypass_base_or_closure(bundle, tmp_path, kind):
    altered = tmp_path / "altered"
    shutil.copytree(bundle, altered)
    path = altered / "bundle.json"
    r = json.loads(path.read_text())
    if kind == "source_lie":
        r["source_sha256"][nb.TOP] = "a"*64
        r["source_signature"] = nb.sha(nb.encoded(r["source_sha256"]))
    elif kind == "omit_source":
        r["source_sha256"].pop(nb.TOP)
        r["source_signature"] = nb.sha(nb.encoded(r["source_sha256"]))
    elif kind == "extra_file":
        (altered / "extra").write_text("unexpected")
    elif kind == "symlink":
        (altered / "link").symlink_to("source_ci16.mem")
    elif kind == "bad_cohort":
        (altered / "cohort.json").write_text("{}\n")
    elif kind == "bad_recipe":
        r["budget"]["recipe"]["added_tail_count"] = 4096
    elif kind == "imports":
        r["python_import_edges"].pop("tests/starlink_oracle/__init__.py")
    elif kind == "measured":
        r["service_measured"] = True
    path.write_bytes(nb.encoded(r))
    with pytest.raises(ValueError):
        nb.verify(altered)


BENCH_MUTANTS = [
    (nb.TOP, "#(500.0/60)", "#7"), (nb.TOP, "#2.1;", "#0;"),
    (nb.TOP, "first_edge, 10.433333", "first_edge, 2.1"),
    (nb.TOP, "first_fall, 18.766666", "first_fall, 10.0"),
    (nb.TOP, "SOURCE_COUNT = 16423", "SOURCE_COUNT = 20519"),
    (nb.TOP, "repeat (256)", "repeat (1)"), (nb.TOP, "wait(native_drain_cycle >= 0)", "wait(native_irq)"),
    (nb.CHECKS, ".RATE_MSPS(60)", ".RATE_MSPS(30)"), (nb.CHECKS, ".ENABLE_INJECTION(0)", ".ENABLE_INJECTION(1)"),
    (nb.CHECKS, "32'h0f8c1108", "32'h0bca0884"), (nb.CHECKS, "48'd1073758594", "48'd1073746351"),
    (nb.CHECKS, "native_raw_count == 257", "native_raw_count == 249"),
    (nb.CHECKS, "native_hold_cycles > 16", "native_hold_cycles > 1000"),
    (nb.CHECKS, "native_raw_payload !== native_held_payload", "1'b0"),
    (nb.CHECKS, "}) === 1'bx)", "}) == 1'bx)"),
    (nb.CHECKS, "native.result_overrun_count} !== 0", "native.result_overrun_count} != 0"),
    (nb.CHECKS, "native.active_coefficient_valid !== 1'b1", "!native.active_coefficient_valid"),
    (nb.CHECKS, "native_raw_saturation[n][11:9] !== 3'b0", "1'b0"),
    (nb.CHECKS, "{{23{native_raw_lag[n][8]}}, native_raw_lag[n][8:0]}", "native_raw_lag[n]"),
]


@pytest.mark.parametrize("name,old,new", BENCH_MUTANTS)
def test_bench_clock_packing_and_safety_source_mutations(tmp_path, name, old, new):
    for source in [nb.TOP, nb.CHECKS]:
        target = tmp_path / source
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(nb.ROOT/source, target)
    nb.check_bench(tmp_path)
    path = tmp_path/name
    original = path.read_text()
    assert old in original
    path.write_text(original.replace(old, new))
    with pytest.raises(ValueError):
        nb.check_bench(tmp_path)


def test_parser_only_healthy_specimen_not_a_service_measurement(synthetic, bundle):
    assert json.loads((synthetic / "PARSER_ONLY.json").read_text())["actual_RTL_run"] is False
    assert nb.verify_result(synthetic, bundle)["result"] == "NATIVE60_ONLY_VERIFIED"
    assert not (synthetic / "terminal.json").exists() and not (synthetic / "run-status.json").exists()


@pytest.mark.parametrize("text", ["Fatal: appended", "eRrOr: appended", "Warning: appended", "NATIVE60_fAiL", "parser_only"])
def test_case_insensitive_failure_after_otherwise_complete_receipts(synthetic, bundle, text):
    path = synthetic/"simulation.log"
    path.write_text(path.read_text()+text+"\n")
    with pytest.raises(ValueError, match="failure/nonservice"):
        nb.verify_result(synthetic, bundle)


@pytest.mark.parametrize("key,value", [("engine_derived_cycles", 78360.0), ("added_tail_count", False),
                                       ("source_clock_runs_after_valid_stop", 1)])
def test_bundle_budget_type_alias_rejected(bundle, tmp_path, key, value):
    altered = tmp_path/"altered"
    shutil.copytree(bundle, altered)
    path = altered/"bundle.json"
    r = json.loads(path.read_text())
    r["budget"]["recipe"][key] = value
    path.write_bytes(nb.encoded(r))
    with pytest.raises(ValueError, match="budget"):
        nb.verify(altered)


RECEIPTS = ["NATIVE60_CONFIG", "NATIVE60_ADMISSION", "NATIVE60_SOURCE_OFF", "NATIVE60_RELEASE",
            "NATIVE60_DRAIN", "NATIVE60_BUDGET", "NATIVE60_CLOCK", "NATIVE60_PASS"]


@pytest.mark.parametrize("marker", RECEIPTS)
@pytest.mark.parametrize("mutation", ["omit", "duplicate", "unknown", "extra_field"])
def test_every_receipt_required_unique_and_known(synthetic, bundle, marker, mutation):
    path = synthetic / "simulation.log"
    rows = path.read_text().splitlines()
    n = next(i for i, entry in enumerate(rows) if entry.startswith(marker+" "))
    if mutation == "omit":
        rows.pop(n)
    elif mutation == "duplicate":
        rows.append(rows[n])
    elif mutation == "unknown":
        rows[n] = re.sub(r"=[^ ]+", "=x", rows[n], count=1)
    else:
        rows[n] += " extra=1"
    path.write_text("\n".join(rows)+"\n")
    with pytest.raises(ValueError):
        nb.verify_result(synthetic, bundle)


RESULT_MUTANTS = [
    ("CONFIG", "rate", 30), ("CONFIG", "geometry", "0bca0884"), ("CONFIG", "eh", 1073746351),
    ("ADMISSION", "index", 34359738559), ("ADMISSION", "index", 34359738721),
    ("ADMISSION", "center", 34359740383), ("ADMISSION", "lead", 1646),
    ("ADMISSION", "handshake_cycle", 15857), ("ADMISSION", "request", "60000052"),
    ("SOURCE_OFF", "source", 20519), ("SOURCE_OFF", "busy", 0),
    ("DRAIN", "raw", 249), ("DRAIN", "engine_idle", 0), ("DRAIN", "bridge_idle", 0),
    ("RELEASE", "packet_reads", 26), ("RELEASE", "retained_cycles", 31),
    ("RELEASE", "irq", 1), ("RELEASE", "available", 1),
    ("BUDGET", "drain", 110000), ("BUDGET", "publish", 104000), ("BUDGET", "release", 110000),
    ("BUDGET", "quiet_start", 97000), ("BUDGET", "quiet_end", 99356),
    ("BUDGET", "raw_after_publish", 0), ("BUDGET", "raw_at_publish", 241),
    ("BUDGET", "maximum_axi", 25), ("BUDGET", "readout_transactions", 141),
    ("BUDGET", "source_off_compute", 0), ("BUDGET", "maximum_tuple_hold", 17),
    ("CLOCK", "first_edge_fs", 2100000), ("CLOCK", "first_fall_fs", 10000000),
    ("CLOCK", "half_fs", 7000000), ("CLOCK", "period_fs", 33333334),
    ("CLOCK", "control_period_fs", 14000000), ("CLOCK", "quiet_edges", 0),
    ("CLOCK", "after_off_edges", 0), ("PASS", "raw", 249), ("PASS", "health", 8192),
    ("PASS", "clock_running", 0), ("PASS", "actual_fft", 1), ("PASS", "static_center", 0),
]


@pytest.mark.parametrize("marker,field,value", RESULT_MUTANTS)
def test_numerical_support_clock_budget_lifetime_mutants(synthetic, bundle, marker, field, value):
    replace_field(synthetic, "NATIVE60_"+marker, field, value)
    with pytest.raises(ValueError):
        nb.verify_result(synthetic, bundle)


@pytest.mark.parametrize("filename", ["native60_actual_raw_tuples.txt", "native60_actual_source.txt",
    "native60_actual_capture.txt", "native60_actual_holds.txt"])
@pytest.mark.parametrize("mutation", ["omit", "duplicate", "reverse", "unknown"])
def test_every_source_capture_raw_and_hold_row_required(synthetic, bundle, filename, mutation):
    path = synthetic / filename
    rows = path.read_text().splitlines()
    if mutation == "omit":
        rows.pop()
    elif mutation == "duplicate":
        rows[-1] = rows[-2]
    elif mutation == "reverse":
        rows.reverse()
    else:
        rows[0] = "x"
    path.write_text("\n".join(rows)+"\n")
    with pytest.raises(ValueError):
        nb.verify_result(synthetic, bundle)


@pytest.mark.parametrize("word", range(26))
def test_every_public_packet_word_must_match_both_reads(synthetic, bundle, word):
    path = synthetic / "simulation.log"
    text, count = re.subn(rf"(NATIVE60_PACKET_WORD pass=1 word={word} data=)[0-9a-f]+", r"\g<1>ffffffff", path.read_text())
    assert count == 1
    path.write_text(text)
    with pytest.raises(ValueError, match="packet"):
        nb.verify_result(synthetic, bundle)


def test_actual_core_compile_only_never_native_service(bundle, tmp_path):
    output = tmp_path / "COMPILE_ONLY_NO_SERVICE"
    assert nb.run(bundle, output, nb.sha((bundle/"bundle.json").read_bytes())) == {
        "result": "NATIVE60_COMPILE_ONLY", "service_measured": False}
    assert (output/"native.vvp").is_file() and not (output/"simulation.log").exists()
    assert (output/"sources-before.json").read_bytes() == (output/"sources-after.json").read_bytes()
    assert (output/"fixture-before.json").read_bytes() == (output/"fixture-after.json").read_bytes()
    assert json.loads((output/"run-status.json").read_text())["simulation_exit"] is None


@pytest.mark.parametrize("failure", ["compile", "service", "timeout", "integrity"])
def test_stubbed_runner_failures_preserve_original_and_after_receipts(bundle, tmp_path, monkeypatch, failure):
    output = tmp_path / "STUBBED_NOT_SERVICE"
    calls = []

    def stub(command, **kwargs):
        calls.append(command)
        assert not {"PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH"} & kwargs["env"].keys()
        if failure == "integrity":
            (output/"inputs/source_ci16.mem").write_text("changed")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 30, output=b"retained timeout", stderr=b"stderr")
        code = 7 if failure in {"compile", "integrity"} or command[0] == "vvp" else 0
        return subprocess.CompletedProcess(command, code, "STUBBED_NOT_RTL", "original failure")

    monkeypatch.setenv("LD_LIBRARY_PATH", "/contaminated/parent")
    monkeypatch.setattr(nb.subprocess, "run", stub)
    with pytest.raises((ValueError, subprocess.TimeoutExpired)):
        nb.run(bundle, output, nb.sha((bundle/"bundle.json").read_bytes()), authorize_native_service=failure == "service")
    status = json.loads((output/"run-status.json").read_text())
    assert status["error"] is not None and (output/"sources-after.json").is_file()
    assert not (output/"terminal.json").exists()
    assert bool(status["integrity_error"]) == (failure == "integrity")
    assert len(calls) == (2 if failure == "service" else 1)
    if failure == "timeout":
        assert (output/"timeout-output.log").read_bytes() == b"retained timeoutstderr"


def test_run_admission_no_overwrite_and_exact_external_pin(bundle, tmp_path):
    with pytest.raises(ValueError, match="SHA"):
        nb.run(bundle, tmp_path/"wrong", "0"*64)
    with pytest.raises(ValueError, match="overwrite"):
        nb.run(bundle, tmp_path, nb.sha((bundle/"bundle.json").read_bytes()))
    with pytest.raises(ValueError, match="boolean"):
        nb.run(bundle, tmp_path/"ambiguous", nb.sha((bundle/"bundle.json").read_bytes()), authorize_native_service="yes")


def test_clock_and_known_zero_predicates_only_no_native_module(tmp_path):
    source = tmp_path/"clock_and_xz_only.sv"
    source.write_text("""`timescale 1ns/1fs
module micro;
 reg sample_clk=0; integer rises=0; realtime previous=0;
 reg [3:0] health; reg valid_flag; integer rejected=0;
 initial begin #2.1; forever #(500.0/60) sample_clk=!sample_clk; end
 always @(posedge sample_clk) begin
   rises=rises+1;
   if(rises==1 && ($realtime<10.433332 || $realtime>10.433334)) $fatal(1,"first edge");
   if(rises>1 && ($realtime-previous<16.666665 || $realtime-previous>16.666667)) $fatal(1,"cadence");
   previous=$realtime;
   if(rises==257) begin if(rejected!=4) $fatal(1,"XZ predicate"); $display("CLOCK_XZ_ONLY_PASS NO_NATIVE_MODULE=1"); $finish; end
 end
 initial begin
  health=0; #1; if(health !== 0) $fatal(1,"known zero");
  health=4'b00x0; if(health !== 0) rejected=rejected+1;
  health=4'b00z0; if(health !== 0) rejected=rejected+1;
  valid_flag=1'bx; if((^{valid_flag,1'b0}) === 1'bx) rejected=rejected+1;
  valid_flag=1'bz; if((^{valid_flag,1'b0}) === 1'bx) rejected=rejected+1;
 end
 initial begin #10000; $fatal(1,"watchdog"); end
endmodule
""")
    compiled = subprocess.run(["iverilog", "-g2012", "-s", "micro", "-o", str(tmp_path/"micro.vvp"), str(source)],
                              capture_output=True, text=True, check=False, timeout=30)
    assert compiled.returncode == 0, compiled.stderr
    result = subprocess.run(["vvp", str(tmp_path/"micro.vvp")], capture_output=True, text=True, check=False, timeout=30)
    (tmp_path/"clock-only.log").write_text(result.stdout+result.stderr)
    assert result.returncode == 0 and "CLOCK_XZ_ONLY_PASS NO_NATIVE_MODULE=1" in result.stdout

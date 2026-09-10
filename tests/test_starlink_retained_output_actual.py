"""Offline construction, scripted composition and parser-only negative controls."""
import csv
import json
import shutil

import pytest

from tests.starlink_oracle import retained_output_actual as a
from tests.starlink_oracle.retained_output_actual_result import verify_result


@pytest.fixture(scope="module")
def scripted(tmp_path_factory):
    p = tmp_path_factory.mktemp("retained_actual_script") / "run"
    status = a.offline(p, execute=True)
    assert status == {"compile": 0, "service_executed": False, "kind": "OFFLINE_SCRIPT_NOT_FFT", "script_exit": 0}
    return p


def test_seven_context_script_not_vendor(scripted):
    result = verify_result(scripted / "simulation.log", scripted / "actual_words.csv", kind="OFFLINE_SCRIPT_NOT_FFT")
    assert result["parser_only_not_execution_proof"] is True
    assert result["terminal"]["pairs"] == 19
    assert result["numerical_words"] == 77953
    assert [a["inputs"] for a in result["aborts"]] == [64, 65]


def test_originals_abi_and_full_inverse():
    a.verify_originals()
    assert a.inverse_bench(a.actual_bench()) == a.original.composition_bench()
    assert len(a.REFERENCE_PINS) == 12
    assert json.loads(a.ABI.read_text())["printed_pages"] == [21, 23, 24]
    assert all("scripted_fft_ports" not in p.name for p in a.compiled_sources())


@pytest.mark.parametrize("name", list(a.REFERENCE_PINS) + ["frozen46.sha256"])
def test_reference_mutants_reject_before_elaboration(tmp_path, monkeypatch, name):
    ref = tmp_path / "reference"
    shutil.copytree(a.REF, ref)
    (ref / name).write_bytes((ref / name).read_bytes() + b"\n")
    monkeypatch.setattr(a, "REF", ref)
    with pytest.raises(ValueError, match="identity"):
        a.verify_originals()


@pytest.mark.parametrize("target", ["RECIPE", "ABI"])
@pytest.mark.parametrize("replacement", ["true", "1.0", "2", "null"])
def test_type_or_recipe_alias_not_accepted(tmp_path, monkeypatch, target, replacement):
    p = tmp_path / "changed.json"
    source = getattr(a, target).read_text()
    p.write_text(source.replace("1", replacement, 1))
    monkeypatch.setattr(a, target, p)
    with pytest.raises(ValueError, match="identity"):
        a.verify_originals()


@pytest.mark.parametrize("needle", [
    "actual48 input", "actual raw packed payload", "actual seven-context total/shadow inventory",
    "payload_shadow", "forward_shadow", "local_guard_observer", "baseline_guard_0",
    "baseline_guard_1", "RACT_SLOW_PAUSE", "actual physical final certification",
    "actual sampled reset shorter than two cycles", "175 fast service cap",
])
def test_entire_bench_inverse_detects_checker_changes(needle):
    text = a.actual_bench()
    assert needle in text
    with pytest.raises(ValueError, match="inverse"):
        a.inverse_bench(text.replace(needle, needle + "_MUTANT", 1))


@pytest.mark.parametrize("prefix", [
    "RACT_BEGIN", "RACT_CONTEXT", "RACT_ADMIT", "RACT_RESET_RELEASE", "RACT_STATUS",
    "RACT_JOB", "RACT_SOURCE_ELIGIBILITY", "RACT_ABORT", "RACT_SHADOW", "RACT_PASS",
    "RACT_SLOW_PAUSE", "RACT_SLOW_RESUME", "OFFLINE_JOB", "OFFLINE_DISPATCH",
    "OFFLINE_PUBLICATION", "OFFLINE_ACK_CONTROLS", "OFFLINE_REAL_ACK", "OFFLINE_ACK_PHASE",
    "OFFLINE_SERVICE", "OFFLINE_PASS", "OFFLINE_RESET", "OFFLINE_CLOCK",
])
@pytest.mark.parametrize("mutation", ["missing", "duplicate"])
def test_receipt_inventory_mutants(scripted, tmp_path, prefix, mutation):
    lines = (scripted / "simulation.log").read_text().splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith(prefix + " "))
    if mutation == "missing":
        lines.pop(index)
    else:
        lines.insert(index, lines[index])
    log = tmp_path / "parser_only.log"
    log.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError):
        verify_result(log, scripted / "actual_words.csv", kind="OFFLINE_SCRIPT_NOT_FFT")


@pytest.mark.parametrize("before,after", [
    ("ordinal=2", "ordinal=3"), ("config_delta=3", "config_delta=4"),
    ("context=1 stall=1", "context=0 stall=1"), ("inputs=64", "inputs=63"),
    ("source=10752", "source=10751"), ("admit=0 publication=0", "admit=1 publication=0"),
    ("sampled_low=6", "sampled_low=1"), ("Fstarts=21", "Fstarts=20"),
])
def test_receipt_payload_mutants(scripted, tmp_path, before, after):
    text = (scripted / "simulation.log").read_text()
    assert before in text
    log = tmp_path / "parser_only.log"
    log.write_text(text.replace(before, after, 1))
    with pytest.raises(ValueError):
        verify_result(log, scripted / "actual_words.csv", kind="OFFLINE_SCRIPT_NOT_FFT")


@pytest.mark.parametrize("failure", ["Fatal: injected", "eRrOr: injected", "FATAL injected",
    "FATAL_ERROR: Vivado Simulator kernel has discovered an exceptional condition from which it cannot recover.",
    "fAtAl_ErRoR: Vivado Simulator kernel has discovered an exceptional condition from which it cannot recover."])
def test_mixed_case_failure_is_not_hidden(scripted, tmp_path, failure):
    log = tmp_path / "parser_only.log"
    log.write_text((scripted / "simulation.log").read_text() + failure + "\n")
    with pytest.raises(ValueError, match="fatal/error"):
        verify_result(log, scripted / "actual_words.csv", kind="OFFLINE_SCRIPT_NOT_FFT")


@pytest.mark.parametrize("stream,field", [
    (stream, "data") for stream in ("source", "inputF", "inputI", "rawF", "rawI", "product", "privateI", "read")
] + [("rawF", f) for f in ("context", "job", "position", "start", "exponent", "slow", "time_fs")]
   + [("inputF", "pad"), ("rawI", "pad"), ("rawF", "grid_shift"), ("rawF", "grid_shift_coherent"), ("inputI", "grid_shift"),
      ("inputF", "aborted_prefix"), ("read", "slow")])
def test_independent_numerical_row_mutants(scripted, tmp_path, stream, field):
    with (scripted / "actual_words.csv").open(newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames
        rows = list(reader)
    row = next(r for r in rows if r["stream"] == stream and
               (field != "aborted_prefix" or (r["context"] == "5" and r["job"] == "1")))
    if field == "pad":
        row["data"] = f'{int(row["data"], 16) ^ (1 << 18):012x}'
    elif field in ("grid_shift", "grid_shift_coherent"):
        row["fast"] = str(int(row["fast"])+1)
        row["time_fs"] = str(int(row["time_fs"])+5714286)
        if field == "grid_shift_coherent":
            assert row["context"] == "0"  # This first-job row precedes both pauses.
            row["slow"] = str(((int(row["time_fs"])-1300000)//5000000+1)//2)
    elif field == "aborted_prefix":
        row["data"] = f'{int(row["data"], 16) ^ 1:012x}'
    elif field in ("data", "start", "exponent"):
        row[field] = f'{int(row[field], 16) ^ 1:x}'
    else:
        row[field] = str(int(row[field]) + (1000000 if field == "slow" else 1))
    path = tmp_path / "parser_only.csv"
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader();writer.writerows(rows)
    with pytest.raises((ValueError, KeyError), match="raw row/job ordinal time join" if field == "grid_shift_coherent" else None):
        verify_result(scripted / "simulation.log", path, kind="OFFLINE_SCRIPT_NOT_FFT")


def test_script_adapter_is_padding_only():
    text = a.scripted_padding_adapter()
    assert "OFFLINE_NOT_FFT" in text
    assert "{6{word_out[35]}}" in text
    restored = text.replace("assign m_axis_data_tdata={{6{word_out[35]}},word_out[35:18],{6{word_out[17]}},word_out[17:0]};",
                            "assign m_axis_data_tdata={6'b0,word_out[35:18],6'b0,word_out[17:0]};")
    assert restored == (a.original.RTL / "tb/scripted_fft_ports.sv").read_text()

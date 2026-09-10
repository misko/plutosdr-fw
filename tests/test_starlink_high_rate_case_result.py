"""Synthetic parser specimens are NOT simulation evidence or numeric models."""

import re

import pytest

from tests.starlink_oracle.high_rate_case_result import terminal, verify_result
from tests.starlink_oracle.high_rate_harness import TERMINAL
from tests.test_starlink_high_rate_harness import parser_only_specimen


def specimen(directory, case):
    log = parser_only_specimen(directory).replace(TERMINAL, terminal(case))
    if case == "healthy343":
        log += "HIGH_RATE30_CASE_LEDGER selected=686 residue=239 potential_tail=208 visible_tail=1 map_reads=343\n"
        for old, new in [
            ("selected=894 visible=894", "selected=686 visible=687"),
            ("map_words=447 source=9000", "map_words=343 source=9000"),
            ("inverse=1024 prepare=894 ratio=894 visible_scores=894 admitted_scores=894",
             "inverse=817 prepare=687 ratio=687 visible_scores=687 admitted_scores=686"),
        ]:
            assert log.count(old) == 1
            log = log.replace(old, new)
    else:
        log += "HIGH_RATE30_CASE_LEDGER selected=894 residue=0 potential_tail=447 visible_tail=0 map_reads=447\n"
        log = "\n".join(line for line in log.splitlines() if not line.startswith(
            ("NATIVE30_ADMISSION ", "NATIVE30_BUDGET_PASS ", "NATIVE30_PACKET_WORD "))) + "\n"
        for old, new in [
            ("native_capture=260 native_busy=1", "native_capture=0 native_busy=0"),
            ("map_retained_through_native_release=1 native_result_released=1", "map_retained_through_late_observation=1 native_result_created=0"),
            ("capture_actual_fft=20 compute_coarse_pilot=300 compute_after_stop=10000", "capture_actual_fft=0 compute_coarse_pilot=0 compute_after_stop=0"),
            ("source_at_native_release", "source_at_native_observation"),
        ]:
            assert log.count(old) == 1
            log = log.replace(old, new)
        log += "NATIVE30_LATE_CONFIG_READY taps=132 generation=30000001 energy=1073746351 no_job=1\n"
        log += "NATIVE30_LATE_HANDSHAKE trigger=17179870160 index=17179870177 capture_start=17179870128 signed_lead=-50 elapsed_cycles=58\n"
        log += "NATIVE30_LATE_REJECT_PASS rejected=1 late=1 admitted=0 capture=0 compute=0 raw=0 qualified=0 packet_reads=0 result=0 irq=0 observation_index=17179875609\n"
        (directory / "native30_actual_raw_tuples.txt").write_bytes(b"")
    (directory / "simulate.log").write_text(log)
    return log


@pytest.mark.parametrize("case", ["healthy343", "late447"])
def test_parser_only_context_healthy_and_negative_are_distinct(tmp_path, case):
    d = tmp_path / "PARSER_ONLY"
    specimen(d, case)
    result = verify_result(case, d)
    assert result["outcome"] == ("healthy" if case == "healthy343" else "expected-late-rejection")
    with pytest.raises(ValueError):
        verify_result("late447" if case == "healthy343" else "healthy343", d)


COMMON = ["HIGH_RATE30_PASS", "HIGH_RATE30_PREROLL_PASS", "HIGH_RATE30_PREFIX", "HIGH_RATE30_OVERLAP", "HIGH_RATE30_CASE_LEDGER",
          "HIGH_RATE30_STOP", "HIGH_RATE30_RETENTION_PASS", "HIGH_RATE30_PIL1_SNAPSHOT", "HIGH_RATE30_PILOT_WORD"]
SPECIAL = {"healthy343": ["NATIVE30_BUDGET_PASS", "NATIVE30_ADMISSION", "NATIVE30_PACKET_WORD"],
           "late447": ["NATIVE30_LATE_CONFIG_READY", "NATIVE30_LATE_HANDSHAKE", "NATIVE30_LATE_REJECT_PASS"]}


@pytest.mark.parametrize("case,prefix", [(c, p) for c in SPECIAL for p in COMMON + SPECIAL[c]])
@pytest.mark.parametrize("mutation", ["missing", "duplicate"])
def test_every_missing_duplicate_context_receipt_rejected(tmp_path, case, prefix, mutation):
    d = tmp_path / "PARSER_ONLY"
    log = specimen(d, case)
    line = next(line for line in log.splitlines() if line.startswith(prefix + " "))
    (d / "simulate.log").write_text(log.replace(line + "\n", "", 1) if mutation == "missing" else log + line + "\n")
    with pytest.raises(ValueError):
        verify_result(case, d)


@pytest.mark.parametrize("case", ["healthy343", "late447"])
@pytest.mark.parametrize("before,after", [
    ("source=12303 ingress=12303", "source=12302 ingress=12303"),
    ("enabled_raw=7250", "enabled_raw=8206"), ("canonical=3618", "canonical=4096"),
    ("forward_input=1536", "forward_input=1023"),
    ("bank_quiet_fast_cycles=50000", "bank_quiet_fast_cycles=31"),
    ("source_at_map_release=9040", "source_at_map_release=12303"),
    ("pilot_all=602", "pilot_all=601"), ("pilot=200", "pilot=512"),
    ("generation=1 raw_words=", "generation=2 raw_words="),
    ("caps=000007ff", "caps=000007fe"),
])
def test_shared_coordinate_source_health_budget_mutants(tmp_path, case, before, after):
    d = tmp_path / "PARSER_ONLY"
    log = specimen(d, case)
    assert before in log
    (d / "simulate.log").write_text(log.replace(before, after))
    with pytest.raises(ValueError):
        verify_result(case, d)


@pytest.mark.parametrize("before,after", [
    ("signed_lead=-50", "signed_lead=-49"),
    ("index=17179870177", "index=17179870241"),
    ("trigger=17179870160", "trigger=17179870159"),
    ("capture_start=17179870128", "capture_start=17179870129"),
    ("elapsed_cycles=58", "elapsed_cycles=257"),
    ("no_job=1", "no_job=0"), ("late=1 admitted=0", "late=0 admitted=0"),
    ("capture=0 compute=0", "capture=1 compute=0"),
    ("result=0 irq=0", "result=1 irq=0"),
    ("observation_index=17179875609", "observation_index=17179875608"),
    ("native_result_created=0", "native_result_created=1"),
    ("native_capture=0 native_busy=0", "native_capture=0 native_busy=1"),
    ("compute_after_stop=0", "compute_after_stop=1"),
])
def test_negative_coordinate_no_work_mutants(tmp_path, before, after):
    d = tmp_path / "PARSER_ONLY"
    log = specimen(d, "late447")
    assert before in log
    (d / "simulate.log").write_text(log.replace(before, after))
    with pytest.raises(ValueError):
        verify_result("late447", d)


@pytest.mark.parametrize("before,after", [
    ("admitted_scores=686", "admitted_scores=687"),
    ("visible_scores=687", "visible_scores=895"),
    ("inverse=817", "inverse=815"), ("map_words=343 source", "map_words=447 source"),
    ("lead=926", "lead=127"), ("maximum_axi_cycles=7", "maximum_axi_cycles=25"),
    ("post_capture_cycles=20700", "post_capture_cycles=28001"),
    ("engine_cycles=19911", "engine_cycles=24001"),
    ("capture_actual_fft=20", "capture_actual_fft=0"),
])
def test_343_exact_geometry_and_positive_native_mutants(tmp_path, before, after):
    d = tmp_path / "PARSER_ONLY"
    log = specimen(d, "healthy343")
    assert before in log
    (d / "simulate.log").write_text(log.replace(before, after))
    with pytest.raises(ValueError):
        verify_result("healthy343", d)


@pytest.mark.parametrize("case", ["healthy343", "late447"])
@pytest.mark.parametrize("fault", ["ERROR: vendor", "FATAL: FFT", "HIGH_RATE30_FAIL stop", "NATIVE30_BUDGET_FAIL"])
def test_fault_never_hidden_by_context_terminal(tmp_path, case, fault):
    d = tmp_path / "PARSER_ONLY"
    log = specimen(d, case)
    (d / "simulate.log").write_text(log + fault + "\n")
    with pytest.raises(ValueError, match="failure evidence"):
        verify_result(case, d)


@pytest.mark.parametrize("case", ["healthy343", "late447"])
@pytest.mark.parametrize("name", ["native30_actual_raw_tuples.txt", "paired_pilot_actual.ci16"])
def test_actual_raw_or_pilot_binary_mutant(tmp_path, case, name):
    d = tmp_path / "PARSER_ONLY"
    specimen(d, case)
    path = d / name
    path.write_bytes(path.read_bytes() + b"1")
    with pytest.raises(ValueError):
        verify_result(case, d)


@pytest.mark.parametrize("marker", ["NATIVE30_PACKET_WORD pass=0 word=0 data=00000000",
                                  "NATIVE30_ADMISSION index=0", "NATIVE30_BUDGET_PASS engine_cycles=0"])
def test_positive_native_receipts_cannot_pass_negative(tmp_path, marker):
    d = tmp_path / "PARSER_ONLY"
    log = specimen(d, "late447")
    (d / "simulate.log").write_text(log + marker + "\n")
    with pytest.raises(ValueError):
        verify_result("late447", d)


def test_late_optional_provisional_tail_still_numeric_prefix_bounded(tmp_path):
    d = tmp_path / "PARSER_ONLY"
    log = specimen(d, "late447")
    (d / "simulate.log").write_text(re.sub(r"visible_scores=894", "visible_scores=1342", log))
    with pytest.raises(ValueError):
        verify_result("late447", d)

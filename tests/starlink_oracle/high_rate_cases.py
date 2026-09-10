"""Strict, invertible additive test-case derivation; no runtime/golden edit."""

from __future__ import annotations

from pathlib import Path

from .high_rate_harness import encoded, sha
from .high_rate_late_contract import validate_contract

ROOT = Path(__file__).resolve().parents[2]
TB = "hdl/library/starlink_pss_acquisition/tb/"
BASE = ROOT / "build/high-rate-harness-prelaunch-v1"
PINS = {
    "tb_starlink_pss_30_bank_native_paired.sv": "d0e78919b6950e3f20869731414d1398be6a9d16375987fd6b6a060614db5914",
    "bank_native30_checks.svh": "52ac102a898cac6f176371c59a487fc34e996caf50370379200b2bc65be0cfab",
    "bank_native30_fft_checks.svh": "b35b8a6762aa713f006ca789e16fe5c494b5bd61b128af597efbbff5242d9e9f",
    "bank_native30_source_checks.svh": "9af68c32d7a8876bfbd12d6eb7cd2be34602cf7522b1fe62db131cacef903a62",
    "tb_starlink_native30_budget.sv": "5995da619bd449ca1772c67711e8175fb7875996dc758eaf993f90984599f97c",
}
CASES = {
    "healthy343": {"profile": "30-upper-bank175-native132-pil1-343x2-healthy-v1", "bins": 343,
                   "selected": 686, "selected_residue": 239, "potential_tail": 208,
                   "visible_max": 894, "inverse_min": 816, "native_late": False},
    "late447": {"profile": validate_contract()["case"], "bins": 447,
                "selected": 894, "selected_residue": 0, "potential_tail": 447,
                "visible_max": 1341, "inverse_min": 1024, "native_late": True},
}


def base_text(name, base=BASE):
    data = (base / "source_snapshot" / TB / name).read_bytes()
    if sha(data) != PINS[name]:
        raise ValueError("unreviewed447 base source: " + name)
    return data.decode()


def inverse(candidate, receipt):
    if sha(candidate.encode()) != receipt["new_sha256"]:
        raise ValueError("altered derived source")
    result = candidate
    for edit in reversed(receipt["edits"]):
        offset, before, after = edit["offset"], edit["before"], edit["after"]
        if result[offset:offset + len(after)] != after:
            raise ValueError("changed inverse hunk")
        result = result[:offset] + before + result[offset + len(after):]
    if sha(result.encode()) != receipt["old_sha256"]:
        raise ValueError("strict inverse did not restore whole original447 body")
    return result


def edit_source(name, edits, base=BASE):
    original = base_text(name, base)
    result, applied = original, []
    for before, after, count in edits:
        if not before or result.count(before) != count:
            raise ValueError(f"context multiplicity changed: {name}: {before[:80]}")
        cursor = 0
        for _ in range(count):
            offset = result.index(before, cursor)
            applied.append({"offset": offset, "before": before, "after": after})
            result = result[:offset] + after + result[offset + len(before):]
            cursor = offset + len(after)
    receipt = {"base": name, "old_sha256": PINS[name], "new_sha256": sha(result.encode()), "edits": applied}
    if inverse(result, receipt) != original:
        raise ValueError("noninvertible case derivation")
    return result, receipt


def section(text, first, last):
    if text.count(first) != 1 or text.count(last) != 1:
        raise ValueError("section boundary changed")
    return text[text.index(first):text.index(last)]


def late_native_include(base=BASE):
    original = base_text("bank_native30_checks.svh", base)
    monitor = section(original, "  task automatic native_healthy;", "  task automatic configure_native;")
    command = section(original, "  task automatic run_native_command;", "`undef HN_CORE")
    return edit_source("bank_native30_checks.svh", [
        (monitor, '  `include "bank_native30_late_logic.svh"\n', 1),
        (command, "", 1),
    ], base)


def late_native_probe(base=BASE):
    original = base_text("tb_starlink_native30_budget.sv", base)
    endpoint = section(original, '    $display("NATIVE30_SOURCE_OFF_PASS', "    $finish;")
    return edit_source("tb_starlink_native30_budget.sv", [
        ("module tb_starlink_native30_budget #(parameter integer EARLY_OFF = 0);", "module tb_starlink_native30_late_probe;\n  localparam integer EARLY_OFF=0;", 1),
        ('`include "bank_native30_checks.svh"', '`include "bank_native30_case_checks.svh"', 1),
        ("resetn && !source_enable && native.i_core.i_raw_tracking_core.correlator_busy", "resetn && native_configured && !source_enable && native.i_core.i_raw_tracking_core.correlator_busy", 1),
        ("native_capture_count != 260 || !native.i_core.i_raw_tracking_core.correlator_busy", "native_capture_count != 0 || native.i_core.i_raw_tracking_core.correlator_busy || late_handshakes!=1", 1),
        ("source_off_compute_cycles < 1", "source_off_compute_cycles != 0", 1),
        (endpoint, '    $display("NATIVE30_LATE_ONLY_PASS source=8205 actual_native30=1 capture=0 raw=0 irq=0 late=1 actual_fft=0 actual_psma=0 actual_pil1=0");\n', 1),
    ], base)


def derive_case(case, base=BASE):
    if case not in CASES:
        raise ValueError("only healthy343 or late447 is admitted")
    config = CASES[case].copy()
    top = base_text("tb_starlink_pss_30_bank_native_paired.sv", base)
    top_edits = [
        ("// Healthy447x2 only. STATIC known center is not a causal coarse-guided command.",
         f"// Derived {case} only. STATIC known center is not a causal coarse-guided command.", 1),
        ("module tb_starlink_pss_30_bank_native_paired;", "module tb_starlink_high_rate30_case;", 1),
        ('`include "bank_native30_fft_checks.svh"', '`include "bank_native30_case_fft_checks.svh"', 1),
        ("30-upper-bank175-native132-pil1-447x2-healthy-v1", config["profile"], 1),
        ('    $display("HIGH_RATE30_PASS',
         f'    $display("HIGH_RATE30_CASE_LEDGER selected={config["selected"]} residue={config["selected_residue"]} potential_tail={config["potential_tail"]} visible_tail=%0d map_reads=%0d",score_count-{config["selected"]},map_reads);\n    $display("HIGH_RATE30_PASS', 1),
    ]
    fft_edits = []
    generated = {}
    receipts = {}
    if case == "healthy343":
        # Each literal is contextual and its whole source body is SHA-pinned.
        for before, after, count in [
            ("MAP_END=FIRST+894", "MAP_END=FIRST+686", 1),
            (".PHASE_BINS=447;", ".PHASE_BINS=343;", 2),
            ("dut.map_read_index>=447", "dut.map_read_index>=343", 1),
            ("dut.accepted_score_count!==894", "dut.accepted_score_count!==686", 3),
            ("score_count<894", "score_count<686", 2),
            ("HIGH_RATE30_STOP selected=894", "HIGH_RATE30_STOP selected=686", 1),
            ("p<447;p=p+1", "p<343;p=p+1", 1),
            ("map_words=447", "map_words=343", 2),
            (".DEPTH!=447", ".DEPTH!=343", 2),
            ("expect_reg(0,8'h08,447)", "expect_reg(0,8'h08,343)", 1),
            ("map_reads!=447", "map_reads!=343", 1),
            ("score_count>1341", "score_count>894", 1),
            ("inverse_count<1024 || prepare_count<894 || ratio_count<894", "inverse_count<816 || prepare_count<686 || ratio_count<686", 1),
            ("admitted_scores=894", "admitted_scores=686", 1),
            ("admitted=894 map_words=343", "admitted=686 map_words=343", 1),
        ]:
            top_edits.append((before, after, count))
        fft_edits = [
            ("map_words[0:446]", "map_words[0:342]", 1),
            ("map_447x2_u16.mem", "map_343x2_u16.mem", 1),
            ("score_count>=1341", "score_count>=894", 1),
            ("score_phase!==score_count%447", "score_phase!==score_count%343", 1),
            ("but every visible tail remains exact and map admission stays894.", "but every visible tail remains exact and map admission stays686.", 1),
        ]
    else:
        generated["bank_native30_case_checks.svh"], receipts["bank_native30_case_checks.svh"] = late_native_include(base)
        generated["tb_starlink_native30_late_probe.sv"], receipts["tb_starlink_native30_late_probe.sv"] = late_native_probe(base)
        generated["bank_native30_case_source_checks.svh"], receipts["bank_native30_case_source_checks.svh"] = edit_source(
            "bank_native30_source_checks.svh", [("native_capture_count!=260", "native_capture_count!=0", 1)], base)
        top_edits += [
            ('`include "bank_native30_checks.svh"', '`include "bank_native30_case_checks.svh"', 1),
            ('`include "bank_native30_source_checks.svh"', '`include "bank_native30_case_source_checks.svh"', 1),
            ("native_capture_count!=260", "native_capture_count!=0", 1),
            ("!native_capture_fft_overlap || !native_compute_overlap || !native_compute_after_stop", "native_capture_fft_overlap!=0 || native_compute_overlap!=0 || native_compute_after_stop!=0 || late_handshakes!=1 || !late_config_seen", 1),
            ("native public release did not preserve independent retained map/source", "late rejection observation did not preserve independent retained map/source", 1),
            ("HIGH_RATE30_RETENTION_PASS map_retained_through_native_release=1 native_result_released=1", "HIGH_RATE30_RETENTION_PASS map_retained_through_late_observation=1 native_result_created=0", 1),
            ("source_at_native_release", "source_at_native_observation", top.count("source_at_native_release")),
            ("capture=260 raw_tuples=129 qualified_tuples=121 packet_words=26 packet_reads=52", "capture=0 raw_tuples=0 qualified_tuples=0 packet_words=0 packet_reads=0 native_late=1", 1),
        ]
    generated["tb_starlink_high_rate30_case.sv"], receipts["tb_starlink_high_rate30_case.sv"] = edit_source(
        "tb_starlink_pss_30_bank_native_paired.sv", top_edits, base)
    generated["bank_native30_case_fft_checks.svh"], receipts["bank_native30_case_fft_checks.svh"] = edit_source(
        "bank_native30_fft_checks.svh", fft_edits, base)
    return generated, {"case": case, "contract": config, "late_contract": validate_contract() if config["native_late"] else None,
                       "strict_inverse": receipts, "original51_changed": False, "actual_fft_executed": False}


def prepare_case(case, output, base=BASE):
    if output.exists():
        raise ValueError("refusing to overwrite case/probe evidence")
    generated, receipt = derive_case(case, base)
    output.mkdir(parents=True)
    for name, text in generated.items():
        (output / name).write_text(text)
    (output / "case.json").write_bytes(encoded(receipt))
    return receipt


def verify_case(case, directory, base=BASE):
    generated, receipt = derive_case(case, base)
    if (directory / "case.json").read_bytes() != encoded(receipt):
        raise ValueError("case contract or strict-inverse receipt changed")
    if {p.name for p in directory.iterdir()} != {*generated, "case.json"}:
        raise ValueError("unexpected/missing generated case file")
    for name, expected in generated.items():
        actual = (directory / name).read_text()
        if actual != expected or inverse(actual, receipt["strict_inverse"][name]) != base_text(receipt["strict_inverse"][name]["base"], base):
            raise ValueError("derived case/inverse mismatch")
    return receipt

"""Invented paired receipts and immutable words: parser-only, never RTL proof."""

import json
import re
from collections import Counter

import pytest

from tests.starlink_oracle.high_rate60_harness_result import (
    EXPECTED_MARKERS,
    TERMINAL,
    verify_results,
)
from tests.starlink_oracle.native60_budget import COHORT
from tests.test_starlink_native60_budget import line, specimen


def replace(directory, marker, field, value):
    p = directory/"simulate.log"
    lines = p.read_text().splitlines()
    indexes = [n for n, text in enumerate(lines) if text.startswith(marker+" ")]
    assert len(indexes) == 1
    n = indexes[0]
    lines[n], count = re.subn(r"\b"+field+r"=[^ ]+", field+"="+str(value), lines[n])
    assert count == 1
    p.write_text("\n".join(lines)+"\n")


def paired_specimen(output):
    # Reuse original immutable word serializer; its standalone PASS is removed,
    # never presented as evidence of PSMA/FFT execution. Sidecar stays explicit.
    specimen(output, COHORT)
    original = output/"simulation.log"
    records = [r for r in original.read_text().splitlines() if not r.startswith("NATIVE60_PASS ")]
    (output/"simulate.log").write_text("\n".join(records)+"\n")
    original.unlink()  # Generated parser-only duplicate, not simulation evidence.
    raw_off_edges = 59614-37191
    off = 18766666+(raw_off_edges-1)*16666666
    first = off-8333333-13311*16666666
    rise_at = lambda index: first+(index-34359738322)*16666666
    cycle_at = lambda fs: (fs+5000000)//10000000
    trigger = cycle_at(rise_at(34359738560)-8333333)
    handshake = cycle_at(rise_at(34359738608))
    capture_end = cycle_at(rise_at(34359740775)+1000)
    replace(output, "NATIVE60_ADMISSION", "trigger_cycle", trigger)
    replace(output, "NATIVE60_ADMISSION", "handshake_cycle", handshake)
    replace(output, "NATIVE60_SNAPSHOT", "capture_cycle", trigger+2)
    replace(output, "NATIVE60_SNAPSHOT", "return_cycle", trigger+13)
    replace(output, "NATIVE60_BUDGET", "capture_end", capture_end)
    pilot = (COHORT/"pilot_expected_ci16.mem").read_text().splitlines()
    indexes = (COHORT/"pilot_expected_index_u64.mem").read_text().splitlines()
    snapshot = []
    for value in [int(indexes[0],16), int(indexes[-1],16),512,512,90,0,3616,602]:
        snapshot.extend([value & 0xffffffff, value>>32])
    snapshot.extend([0,0x100,0,24,0x60000052,2,0,0,0,0])
    records = [
        "HIGH_RATE60_PREROLL_PASS disabled_prime=2 original_raw=3111 intermediate30=1549 canonical=768 public_psma=00010008 caps=000007ff native_taps=264",
        "HIGH_RATE60_STOP selected=894 visible=894 source=6100 canonical=1900 pilot=200 native_capture=520 native_busy=1",
        "HIGH_RATE60_RETENTION_PASS map_retained_through_native_release=1 native_result_released=1 map_words=447 source=16425",
        "HIGH_RATE60_PREFIX source=16425 original=16423 prime=2 continuous=13312 ingress=16425 enabled_raw=14511 intermediate30=7249 intermediate30_accepted=7248 canonical=3617 pilot_accepted=3616 pilot_mixed=3616 pilot_half=1808 pilot_all=602 forward_input=1536 forward=1536 product=1536 inverse_input=1024 inverse=1024 prepare=894 ratio=894 visible_scores=894 admitted_scores=894",
        line("HIGH_RATE60_CONTINUOUS", {"count":13312,"first":34359738322,"stop":34359751634,
            "first_rise_fs":first,"last_rise_fs":off-8333333,"off_fs":off,"startup_pause_outside_segment":1}),
        line("HIGH_RATE60_FFT_CLOCK", {"first_edge_fs":4157143,"first_fall_fs":7014286,"half_fs":2857143,
            "period_fs":5714286,"edges":(99357*10000000-4157143)//5714286+1,"ideal_clock":1,"mmcm_claim":0}),
        "HIGH_RATE60_OVERLAP capture_actual_fft=20 compute_coarse_pilot=300 compute_after_stop=10000 bank_quiet_fast_cycles=50000 source_at_stop=6100 source_at_native_release=16425 source_at_map_release=16425",
        "HIGH_RATE60_PIL1_SNAPSHOT generation=1 raw_words="+"".join(f" {word:08x}" for word in snapshot),
        *[f"HIGH_RATE60_PILOT_WORD ordinal={n} newest={indexes[n]} word={pilot[n]}" for n in range(512)],
        TERMINAL,
    ]
    p = output/"simulate.log"
    p.write_text(p.read_text()+"\n".join(records)+"\n")
    (output/"paired_pilot_actual.ci16").write_bytes((COHORT/"pilot_expected.ci16").read_bytes())
    (output/"paired60_actual_prime.txt").write_text("".join(f"{34359735209+n:016x} {n+1:08x}\n" for n in range(2)))
    return output


@pytest.fixture
def synthetic(tmp_path):
    return paired_specimen(tmp_path/"PARSER_ONLY_NOT_MEASURED")


def test_parser_only_healthy_explicit_marker_inventory(synthetic):
    assert json.loads((synthetic/"PARSER_ONLY.json").read_text())["actual_RTL_run"] is False
    assert verify_results(synthetic,COHORT)["result"] == "HIGH_RATE60_SIMULATION_VERIFIED"
    log = (synthetic/"simulate.log").read_text()
    assert Counter(re.findall(r"^(HIGH_RATE60_\S+)",log,re.MULTILINE)) == EXPECTED_MARKERS
    assert sum(EXPECTED_MARKERS.values()) == 521
    assert not (synthetic/"terminal_receipt.json").exists()


@pytest.mark.parametrize("marker", [*EXPECTED_MARKERS, "NATIVE60_CONFIG", "NATIVE60_ADMISSION", "NATIVE60_SNAPSHOT",
    "NATIVE60_DRAIN", "NATIVE60_RELEASE", "NATIVE60_BUDGET", "NATIVE60_CLOCK", "NATIVE60_SOURCE_OFF", "NATIVE60_PACKET_WORD"])
@pytest.mark.parametrize("mode", ["missing", "duplicate"])
def test_receipt_missing_duplicate(synthetic, marker, mode):
    p = synthetic/"simulate.log"
    lines = p.read_text().splitlines()
    n = next(n for n,r in enumerate(lines) if r.startswith(marker+" "))
    if mode == "missing":
        lines.pop(n)
    else:
        lines.append(lines[n])
    p.write_text("\n".join(lines)+"\n")
    with pytest.raises(ValueError):
        verify_results(synthetic, COHORT)


@pytest.mark.parametrize("trailer", ["Fatal: late failure", "eRrOr shutdown", "WARNING truncated", "FAIL", "parser_only",
    "HIGH_RATE60_EXTRA identity=0", "HIGH_RATE60_PASSIVE fake=1", "NATIVE60_PASS fake=1"])
def test_fault_unknown_marker_or_nonsimulation_rejected(synthetic, trailer):
    p = synthetic/"simulate.log"
    p.write_text(p.read_text()+trailer+"\n")
    with pytest.raises(ValueError):
        verify_results(synthetic, COHORT)


MUTANTS = [
    ("HIGH_RATE60_PREROLL_PASS","disabled_prime",0), ("HIGH_RATE60_PREROLL_PASS","public_psma","00010007"),
    ("HIGH_RATE60_PREROLL_PASS","intermediate30",1548), ("HIGH_RATE60_PREROLL_PASS","native_taps",132),
    ("HIGH_RATE60_PREFIX","enabled_raw",14474), ("HIGH_RATE60_PREFIX","enabled_raw",16423),
    ("HIGH_RATE60_PREFIX","canonical",3608), ("HIGH_RATE60_PREFIX","canonical",4096),
    ("HIGH_RATE60_PREFIX","original",16424), ("HIGH_RATE60_PREFIX","continuous",13311),
    ("HIGH_RATE60_PREFIX","prime",0), ("HIGH_RATE60_PREFIX","ingress",16424),
    ("HIGH_RATE60_PREFIX","admitted_scores",895), ("HIGH_RATE60_PREFIX","visible_scores",1342),
    ("HIGH_RATE60_PREFIX","inverse",1023), ("HIGH_RATE60_PREFIX","forward_input",3585),
    ("HIGH_RATE60_PREFIX","prepare",893), ("HIGH_RATE60_PREFIX","ratio",3129),
    ("HIGH_RATE60_PREFIX","pilot_accepted",3608), ("HIGH_RATE60_PREFIX","pilot_mixed",4000),
    ("HIGH_RATE60_PREFIX","intermediate30_accepted",7250), ("HIGH_RATE60_PREFIX","pilot_half",1804),
    ("HIGH_RATE60_PREFIX","pilot_all",601), ("HIGH_RATE60_CONTINUOUS","count",13311),
    ("HIGH_RATE60_CONTINUOUS","first",34359738323), ("HIGH_RATE60_CONTINUOUS","stop",34359751633),
    ("HIGH_RATE60_CONTINUOUS","startup_pause_outside_segment",0),
    ("HIGH_RATE60_FFT_CLOCK","period_fs",5000000), ("HIGH_RATE60_FFT_CLOCK","first_edge_fs",1300000),
    ("HIGH_RATE60_FFT_CLOCK","mmcm_claim",1), ("HIGH_RATE60_FFT_CLOCK","edges",1),
    ("HIGH_RATE60_OVERLAP","capture_actual_fft",0), ("HIGH_RATE60_OVERLAP","compute_after_stop",0),
    ("HIGH_RATE60_OVERLAP","compute_coarse_pilot",0), ("HIGH_RATE60_OVERLAP","source_at_map_release",16424),
    ("HIGH_RATE60_RETENTION_PASS","map_retained_through_native_release",0), ("HIGH_RATE60_STOP","selected",893),
    ("HIGH_RATE60_STOP","source",6101), ("HIGH_RATE60_STOP","pilot",512), ("HIGH_RATE60_STOP","canonical",3500),
    ("NATIVE60_ADMISSION","index",34359738721), ("NATIVE60_ADMISSION","lead",1534),
    ("NATIVE60_ADMISSION","handshake_cycle",15680), ("NATIVE60_BUDGET","capture_end",19275),
    ("NATIVE60_BUDGET","drain",110000), ("NATIVE60_BUDGET","release",120000),
    ("NATIVE60_BUDGET","maximum_tuple_hold",17), ("NATIVE60_BUDGET","maximum_axi",25),
    ("NATIVE60_BUDGET","readout_transactions",141), ("NATIVE60_BUDGET","raw_after_publish",7),
    ("NATIVE60_DRAIN","raw",249), ("NATIVE60_DRAIN","engine_idle",0), ("NATIVE60_RELEASE","irq",1),
    ("NATIVE60_SOURCE_OFF","busy",0), ("NATIVE60_CLOCK","period_fs",14000000),
    ("NATIVE60_SNAPSHOT","public_index",34359738560), ("NATIVE60_SNAPSHOT","count",2),
    ("HIGH_RATE60_PREFIX","canonical","x"), ("HIGH_RATE60_OVERLAP","capture_actual_fft","-1"),
]


@pytest.mark.parametrize("marker,field,value", MUTANTS)
def test_context_specific_numeric_clock_source_service_mutations(synthetic, marker, field, value):
    replace(synthetic, marker, field, value)
    with pytest.raises(ValueError):
        verify_results(synthetic, COHORT)


@pytest.mark.parametrize("name", ["native60_actual_source.txt", "native60_actual_capture.txt", "native60_actual_holds.txt",
    "native60_actual_raw_tuples.txt", "paired60_actual_prime.txt", "paired_pilot_actual.ci16"])
def test_all_raw_source_capture_tuple_hold_pilot_bytes_exact(synthetic,name):
    p = synthetic/name
    # Removing only a terminal newline does not alter splitlines()-level data.
    # Drop actual payload (last token byte plus newline for text specimens).
    p.write_bytes(p.read_bytes()[:-2])
    with pytest.raises(ValueError):
        verify_results(synthetic, COHORT)


@pytest.mark.parametrize("name", ["HIGH_RATE60_PILOT_WORD", "NATIVE60_PACKET_WORD", "HIGH_RATE60_PIL1_SNAPSHOT"])
def test_public_words_not_just_pass_counts(synthetic,name):
    p = synthetic/"simulate.log"
    lines = p.read_text().splitlines()
    n = next(n for n,r in enumerate(lines) if r.startswith(name+" "))
    lines[n] = lines[n][:-1] + ("0" if lines[n][-1]!="0" else "1")
    p.write_text("\n".join(lines)+"\n")
    with pytest.raises(ValueError):
        verify_results(synthetic, COHORT)

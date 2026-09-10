"""Context-specific343-healthy /447-late receipts; never reinterpret as447-healthy."""

import re

from .high_rate_cases import CASES
from .high_rate_harness import one_receipt, rows, verify_native_results
from .high_rate_late_contract import validate_contract


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def terminal(case):
    c = CASES[case]
    native = ("capture=0 raw_tuples=0 qualified_tuples=0 packet_words=0 packet_reads=0 native_late=1"
              if c["native_late"] else "capture=260 raw_tuples=129 qualified_tuples=121 packet_words=26 packet_reads=52")
    return (f"HIGH_RATE30_PASS profile={c['profile']} admitted={c['selected']} map_words={c['bins']} {native} "
            "pilot_words=512 bytes=2048 source=12303 STATIC_NOT_CAUSAL_NO_RF_DMA_IIO_PHYSICAL_OR_PRODUCTION_MAP_CLAIM")


def verify_late(directory, log, *, native_only=False):
    c = validate_contract()
    config = "NATIVE30_LATE_CONFIG_READY taps=132 generation=30000001 energy=1073746351 no_job=1"
    require(log.splitlines().count(config) == 1, "missing/duplicate explicit late config-ready witness")
    pattern = (r"^NATIVE30_LATE_HANDSHAKE trigger=(\d+) index=(\d+) capture_start=(\d+) "
               r"signed_lead=(-\d+) elapsed_cycles=(\d+)$")
    matches = re.findall(pattern, log, re.MULTILINE)
    require(len(matches) == 1, "missing/duplicate late actual handshake")
    trigger, index, start, lead, elapsed = map(int, matches[0])
    require(trigger == c["command_trigger_raw"] and start == c["capture_start"] and
            c["actual_handshake_raw_closed"][0] <= index <= c["actual_handshake_raw_closed"][1] and
            c["actual_signed_lead_closed"][0] <= lead <= c["actual_signed_lead_closed"][1] and
            lead == start - index - 1 and 0 < elapsed <= c["command_control_cycle_limit"], "late coordinate/budget mismatch")
    rejected = one_receipt(log, "NATIVE30_LATE_REJECT_PASS")
    expected = dict.fromkeys(["admitted", "capture", "compute", "raw", "qualified", "packet_reads", "result", "irq"], 0)
    expected.update({"rejected": 1, "late": 1, "observation_index": rejected.get("observation_index", -1)})
    require(rejected == expected and c["negative_observation_raw"] <= rejected["observation_index"] < c["raw_first"] + 8205,
            "late zero-work/observation inventory mismatch")
    require(not any(marker in log for marker in ["NATIVE30_PACKET_WORD", "NATIVE30_BUDGET_PASS", "NATIVE30_ADMISSION "]),
            "positive native receipt leaked into negative case")
    require((directory / "native30_actual_raw_tuples.txt").read_bytes() == b"", "late case emitted a raw tuple")
    if native_only:
        require(log.splitlines().count("NATIVE30_LATE_ONLY_PASS source=8205 actual_native30=1 capture=0 raw=0 irq=0 late=1 actual_fft=0 actual_psma=0 actual_pil1=0") == 1,
                "missing native-only negative terminal")
    return {"trigger": trigger, "index": index, "signed_lead": lead, "elapsed_cycles": elapsed,
            "observation_index": rejected["observation_index"]}


def verify_result(case, directory):
    require(case in CASES, "unreviewed case")
    c = CASES[case]
    log = (directory / "simulate.log").read_text()
    require(not re.search(r"(?im)\b(?:FAIL(?:ED|URE)?|FATAL|ERROR)\b|HIGH_RATE30_FAIL|NATIVE30_\w*FAIL", log), "failure evidence")
    require(log.splitlines().count(terminal(case)) == 1 and sum(line.startswith("HIGH_RATE30_PASS") for line in log.splitlines()) == 1,
            "wrong/missing/duplicate case-specific terminal")
    preroll = "HIGH_RATE30_PREROLL_PASS disabled_prime=2 original_raw=1549 canonical=768 public_psma=00010007 caps=000007ff native_taps=132"
    require(log.splitlines().count(preroll) == 1, "public identity/preroll mismatch")
    p = one_receipt(log, "HIGH_RATE30_PREFIX")
    require(set(p) == {"source", "ingress", "enabled_raw", "canonical", "pilot_accepted", "pilot_mixed", "pilot_half", "pilot_all", "forward_input", "forward", "product", "inverse_input", "inverse", "prepare", "ratio", "visible_scores", "admitted_scores"}, "prefix field inventory")
    require(p["source"] == p["ingress"] == 12303 and p["admitted_scores"] == c["selected"] and
            c["selected"] <= p["visible_scores"] <= c["visible_max"] and
            3609 <= p["canonical"] < 4096 and 7231 <= p["enabled_raw"] < 8205 and
            3610 <= p["pilot_mixed"] <= p["pilot_accepted"] <= p["canonical"] and
            1805 <= p["pilot_half"] <= 2048 and 602 <= p["pilot_all"] <= 683, "source/pilot/map prefix support")
    require(all(1024 <= p[name] <= 3584 for name in ["forward_input", "forward", "product", "inverse_input"]) and
            c["inverse_min"] <= p["inverse"] <= 3584 and
            all(c["selected"] <= p[name] <= 3129 for name in ["prepare", "ratio"]), "FFT/ratio support")
    require(p["forward_input"] >= p["forward"] >= p["product"] >= p["inverse_input"] >= p["inverse"] and
            p["prepare"] >= p["ratio"] >= p["visible_scores"], "impossible stage order")
    require(one_receipt(log, "HIGH_RATE30_CASE_LEDGER") == {
        "selected": c["selected"], "residue": c["selected_residue"], "potential_tail": c["potential_tail"],
        "visible_tail": p["visible_scores"] - c["selected"], "map_reads": c["bins"],
    }, "case-specific selected/residue/visible-tail/map ledger")
    o = one_receipt(log, "HIGH_RATE30_OVERLAP")
    native_source = "source_at_native_observation" if c["native_late"] else "source_at_native_release"
    require(set(o) == {"capture_actual_fft", "compute_coarse_pilot", "compute_after_stop", "bank_quiet_fast_cycles", "source_at_stop", native_source, "source_at_map_release"} and
            o["bank_quiet_fast_cycles"] >= 32 and 1551 < o["source_at_stop"] < o[native_source] <= o["source_at_map_release"] < 12303,
            "source ownership/quiescence mismatch")
    if c["native_late"]:
        require(o["capture_actual_fft"] == o["compute_coarse_pilot"] == o["compute_after_stop"] == 0, "native work despite late rejection")
        native = verify_late(directory, log)
        expected_retention = {"map_retained_through_late_observation": 1, "native_result_created": 0}
    else:
        require(min(o["capture_actual_fft"], o["compute_coarse_pilot"], o["compute_after_stop"]) > 0, "missing native overlap")
        require("NATIVE30_LATE_" not in log, "negative receipt in healthy case")
        verify_native_results(directory, log)
        native = one_receipt(log, "NATIVE30_BUDGET_PASS")
        require(set(native) == {"capture_end_cycle", "publish_cycle", "release_cycle", "engine_cycles", "post_capture_cycles", "maximum_axi_cycles", "raw", "qualified", "capture", "packet_reads"} and
                native["raw"] == 129 and native["qualified"] == 121 and native["capture"] == 260 and native["packet_reads"] == 52 and
                0 < native["engine_cycles"] == native["publish_cycle"] - native["capture_end_cycle"] <= 24000 and
                native["engine_cycles"] < native["post_capture_cycles"] == native["release_cycle"] - native["capture_end_cycle"] <= 28000 and
                0 < native["maximum_axi_cycles"] <= 24, "native positive completion budget")
        admission = one_receipt(log, "NATIVE30_ADMISSION")
        require(set(admission) == {"index", "capture_start", "lead", "deadline"} and
                admission["capture_start"] == 17179870128 and admission["deadline"] == 17179869408 and
                admission["index"] <= admission["deadline"] and admission["lead"] == admission["capture_start"] - admission["index"] - 1 and admission["lead"] >= 128,
                "native positive admission mismatch")
        expected_retention = {"map_retained_through_native_release": 1, "native_result_released": 1}
    expected_retention.update({"map_words": c["bins"], "source": o[native_source]})
    require(one_receipt(log, "HIGH_RATE30_RETENTION_PASS") == expected_retention, "context-specific map retention mismatch")
    stop = one_receipt(log, "HIGH_RATE30_STOP")
    require(set(stop) == {"selected", "visible", "source", "canonical", "pilot", "native_capture", "native_busy"} and
            stop["selected"] == c["selected"] and c["selected"] <= stop["visible"] <= p["visible_scores"] and
            stop["source"] == o["source_at_stop"] and stop["canonical"] + 512 < p["canonical"] and
            1 <= stop["pilot"] < 512 and 0 <= stop["native_capture"] <= 260 and stop["native_busy"] in {0, 1}, "STOP support/lifetime")
    if c["native_late"]:
        require(stop["native_capture"] == stop["native_busy"] == 0, "late native work at STOP")
    words = rows((directory / "pilot_expected_ci16.mem").read_bytes(), 512, 8)
    indexes = rows((directory / "pilot_expected_index_u64.mem").read_bytes(), 512, 16)
    actual_pilot = re.findall(r"^HIGH_RATE30_PILOT_WORD ordinal=(\d+) newest=([0-9a-f]{16}) word=([0-9a-f]{8})$", log, re.MULTILINE)
    require(actual_pilot == [(str(n), f"{indexes[n]:016x}", f"{words[n]:08x}") for n in range(512)], "pilot log mismatch")
    require((directory / "paired_pilot_actual.ci16").read_bytes() == (directory / "pilot_expected.ci16").read_bytes(), "pilot binary mismatch")
    snapshots = re.findall(r"^HIGH_RATE30_PIL1_SNAPSHOT generation=1 raw_words=((?: [0-9a-f]{8}){26})$", log, re.MULTILINE)
    require(len(snapshots) == 1, "PIL1 snapshot missing/duplicate")
    snap = [int(word, 16) for word in snapshots[0].split()]
    pairs = [snap[2*n] | snap[2*n+1] << 32 for n in range(8)]
    require(pairs == [indexes[0], indexes[-1], 512, 512, 90, 0, p["pilot_accepted"], p["pilot_all"]] and not (
        snap[16] or snap[17] & 255 or snap[18] or snap[19] != 24 or snap[20] != 0x30000052 or any(snap[22:])
    ), "PIL1 snapshot support/count/health mismatch")
    return {"case": case, "profile": c["profile"], "result": "HIGH_RATE30_CASE_VERIFIED",
            "outcome": "expected-late-rejection" if c["native_late"] else "healthy",
            "prefix": p, "overlap": o, "native": native}

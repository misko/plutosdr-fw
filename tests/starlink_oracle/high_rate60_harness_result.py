"""Paired60-specific result gate. Original native limits and69 goldens unchanged.

Native evidence validation is a narrowly scoped adaptation of the previously
reviewed native60 verifier: paired outer identity replaces standalone terminal,
while all tuple/source/clock/readback/hold/deadline conditions remain exact.
"""

import json
import re
from collections import Counter

from .high_rate60_harness import PROFILE, check_recipe, rows
from .native60_budget import _receipt, check_cohort, require, verify_snapshot
from .native60_budget_recipe import recipe


def verify_native_component(directory, inputs, log):
    check_cohort(inputs)
    paths = [directory / name for name in ["native60_actual_raw_tuples.txt",
                                           "native60_actual_source.txt", "native60_actual_capture.txt",
                                           "native60_actual_holds.txt"]]
    require(all(path.is_file() and path.stat().st_size <= 10_000_000 for path in paths), "missing/oversized result logs")
    raw, source, capture, holds = [path.read_text() for path in paths]
    require(not any(word in log.lower() for word in ["fail", "fatal", "error", "warning", "parser_only"]), "failure/nonservice log")
    cfg = _receipt(log, "NATIVE60_CONFIG", ["cycle", "id", "abi", "rate", "geometry", "caps", "generation", "eh"],
                   {"id", "abi", "geometry", "caps", "generation"})
    require([cfg[key] for key in ["id", "abi", "rate", "geometry", "caps"]] == recipe()["public_identity"] and
            cfg["generation"] == 0x60000001 and cfg["eh"] == 1073758594, "public config identity")
    adm = _receipt(log, "NATIVE60_ADMISSION", ["index", "center", "capture_first", "lead", "trigger_cycle", "handshake_cycle", "request", "generation"],
                   {"request", "generation"})
    require(34359738560 <= adm["index"] <= 34359738720 and adm["center"] == 34359740384 and
            adm["capture_first"] == 34359740256 and adm["lead"] == 34359740256-adm["index"]-1 and
            1535 <= adm["lead"] <= 1695 and adm["request"] == 0x60000520 and adm["generation"] == 0x60000001 and
            cfg["cycle"] < adm["trigger_cycle"] <= adm["handshake_cycle"] <= adm["trigger_cycle"]+256,
            "actual command coordinate/identity/control budget")
    snapshot = _receipt(log, "NATIVE60_SNAPSHOT", ["count", "capture_cycle", "return_cycle", "captured_index",
        "live_at_capture", "public_index", "retained_index", "live_at_return", "capture_lag", "return_lag",
        "maximum_capture_lag", "maximum_return_lag", "maximum_return_cycles"])
    verify_snapshot(snapshot, adm["trigger_cycle"], adm["handshake_cycle"])
    off = _receipt(log, "NATIVE60_SOURCE_OFF", ["cycle", "source", "first", "stop", "capture", "busy"])
    require({key: off[key] for key in off if key != "cycle"} ==
            {"source": 16423, "first": 34359735211, "stop": 34359751634, "capture": 520, "busy": 1}, "source-off inventory")
    drain = _receipt(log, "NATIVE60_DRAIN", ["cycle", "raw", "qualified", "engine_idle", "bridge_idle"])
    require({key: drain[key] for key in drain if key != "cycle"} ==
            {"raw": 257, "qualified": 241, "engine_idle": 1, "bridge_idle": 1}, "complete raw drain")
    release = _receipt(log, "NATIVE60_RELEASE", ["cycle", "raw", "qualified", "packet_reads", "retained_cycles", "settle_cycles", "irq", "available"])
    require(249 <= release["raw"] <= 257 and release["qualified"] == 241 and release["packet_reads"] == 52 and
            release["retained_cycles"] == 32 and release["settle_cycles"] == 24 and
            release["irq"] == release["available"] == 0, "public retention/release inventory")
    b = _receipt(log, "NATIVE60_BUDGET", ["capture_end", "publish", "drain", "release", "source_off", "quiet_start", "quiet_end", "raw_at_publish", "raw_after_publish", "maximum_axi", "readout_transactions", "source_off_compute", "maximum_tuple_hold"])
    require(adm["handshake_cycle"] < b["capture_end"] < b["source_off"] < b["drain"] and
            b["capture_end"] < b["publish"] < b["release"] and
            max(b["source_off"], b["release"], b["drain"]) <= b["quiet_start"] and
            b["quiet_end"]-b["quiet_start"] == 256 and b["quiet_end"] < 160000, "lifecycle order/no-stale/watchdog")
    require(b["drain"] == drain["cycle"] and b["release"] == release["cycle"] and b["source_off"] == off["cycle"],
            "inconsistent lifecycle receipts")
    require(b["publish"]-b["capture_end"] <= 84000 and b["drain"]-b["capture_end"] <= 84000 and
            b["release"]-b["capture_end"] <= 88000 and 1 <= b["maximum_axi"] <= 24 and
            105 <= b["readout_transactions"] <= 140 and 1 <= b["source_off_compute"] <= b["drain"]-b["source_off"],
            "complete state/readout/source-off budget")
    require(249 <= b["raw_at_publish"] <= release["raw"] <= 257 and
            b["raw_at_publish"]+b["raw_after_publish"] == 257 and
            (release["raw"] == 257 if b["release"] >= b["drain"] else True), "raw tail not fully accounted")
    clock = _receipt(log, "NATIVE60_CLOCK", ["first_edge_fs", "first_fall_fs", "half_fs", "period_fs", "control_period_fs", "source_edges", "after_off_edges", "quiet_edges"])
    for key, expected in {"first_edge_fs": 10433333, "first_fall_fs": 18766666, "half_fs": 8333333,
                              "period_fs": 16666666, "control_period_fs": 10000000}.items():
        require(abs(clock[key]-expected) <= 1, "actual oscillator origin/cadence")
    require(clock["source_edges"] > 16423 and 152 <= clock["quiet_edges"] <= 155 and
            clock["quiet_edges"] <= clock["after_off_edges"] <= clock["source_edges"], "continuing source clock missing")
    # Control cycle n's falling edge is exactly n*10ns; oscillator starts at
    # the independently asserted first edge, with quantized fixed half periods.
    edges_at = lambda cycle: (cycle*10000000 - 10433333)//16666666 + 1
    require(clock["source_edges"] == edges_at(b["quiet_end"]) and
            clock["quiet_edges"] == edges_at(b["quiet_end"])-edges_at(b["quiet_start"]),
            "clock edge inventory versus control-cycle coordinates")
    off_time_fs = 18766666 + (clock["source_edges"]-clock["after_off_edges"]-1)*16666666
    require(b["source_off"]*10000000-5000000 <= off_time_fs < b["source_off"]*10000000+5000000,
            "source-off falling edge versus control-cycle coordinate")
    expected_packet = (inputs / "native_expected_packet.mem").read_text().splitlines()
    packets = re.findall(r"^NATIVE60_PACKET_WORD pass=(\d+) word=(\d+) data=([0-9a-f]{8})$", log, re.MULTILINE)
    require(packets == [(str(p), str(n), expected_packet[n]) for p in range(2) for n in range(26)], "exact repeated public packet")
    require(len(re.findall(r"^NATIVE60_", log, re.MULTILINE)) == 60, "unrecognized/duplicate native component evidence marker")
    rows = json.loads((inputs / "native_all_raw_tuples.json").read_bytes())
    expected_raw = []
    for row in rows:
        words = [str(row["lag"])] + [f"{int(row[field]) & ((1 << bits)-1):0{width}x}"
                    for field, bits, width in [("start_index", 64, 16), ("real", 48, 12), ("imag", 48, 12),
                                               ("Ex", 48, 12), ("Eh", 48, 12), ("power", 96, 24), ("saturation", 9, 3)]]
        expected_raw.append(" ".join(words + [str(int(row["qualified"]))]))
    require(raw.splitlines() == expected_raw and len(expected_raw) == 257, "all257 independent raw tuples/power")
    hold_rows = [line.split() for line in holds.splitlines()]
    require(len(hold_rows) == 257 and all(len(row) == 2 for row in hold_rows), "per-tuple hold trace incomplete")
    hold_rows = [[int(x) for x in row] for row in hold_rows]
    require([row[0] for row in hold_rows] == list(range(-128, 129)) and
            all(0 <= row[1] <= 16 for row in hold_rows) and
            max(row[1] for row in hold_rows) == b["maximum_tuple_hold"], "per-tuple reducer hold allowance")
    indexes = (inputs / "source_index_u64.mem").read_text().splitlines()
    source_iq = (inputs / "source_ci16.mem").read_text().splitlines()
    require(source.splitlines() == [f"{i} {v}" for i, v in zip(indexes, source_iq, strict=True)], "all16423 source coordinates/strobes/packing")
    capture_iq = (inputs / "native_capture_ci16.mem").read_text().splitlines()
    require(capture.splitlines() == [f"{n} {34359740256+n:016x} {34359740256+n:016x} {v}"
                                    for n, v in enumerate(capture_iq)], "all520 original capture coordinates/packing")
    return {"result": "PAIRED60_NATIVE_COMPONENT_VERIFIED", "budget": b, "clock": clock, "admission": adm,
            "snapshot": snapshot,
            "scope": "native component evidence inside paired60 simulation; static known center, not RF truth"}


TERMINAL = (
    f"HIGH_RATE60_PASS profile={PROFILE} admitted=894 map_words=447 capture=520 "
    "raw_tuples=257 qualified_tuples=241 packet_words=26 packet_reads=52 "
    "pilot_words=512 bytes=2048 source=16425 original=16423 prime=2 tail=0 "
    "STATIC_NOT_CAUSAL_NO_RF_DMA_IIO_PHYSICAL_OR_PRODUCTION_MAP_CLAIM"
)
EXPECTED_MARKERS = {
    "HIGH_RATE60_PASS": 1, "HIGH_RATE60_PREROLL_PASS": 1,
    "HIGH_RATE60_PREFIX": 1, "HIGH_RATE60_CONTINUOUS": 1,
    "HIGH_RATE60_FFT_CLOCK": 1, "HIGH_RATE60_OVERLAP": 1,
    "HIGH_RATE60_RETENTION_PASS": 1, "HIGH_RATE60_STOP": 1,
    "HIGH_RATE60_PIL1_SNAPSHOT": 1, "HIGH_RATE60_PILOT_WORD": 512,
}


def verify_results(directory, cohort):
    r = check_recipe()
    log_path = directory / "simulate.log"
    require(log_path.is_file() and log_path.stat().st_size < 10_000_000, "missing/oversized paired60 log")
    log = log_path.read_text()
    require(not re.search(r"(?i)\b(?:fail(?:ed|ure)?|fatal|error|warning)\b|parser_only", log), "paired60 failure/nonservice log")
    require(log.splitlines().count(TERMINAL) == 1 and
            sum(line.startswith("HIGH_RATE60_PASS") for line in log.splitlines()) == 1, "paired60 terminal identity/count")
    native = verify_native_component(directory, cohort, log)
    preroll = _receipt(log, "HIGH_RATE60_PREROLL_PASS", ["disabled_prime", "original_raw", "intermediate30", "canonical", "public_psma", "caps", "native_taps"],
                       {"public_psma", "caps"})
    require(preroll == {"disabled_prime": 2, "original_raw": 3111, "intermediate30": 1549,
                       "canonical": 768, "public_psma": 0x10008, "caps": 0x7ff, "native_taps": 264}, "public60 admission/preroll")
    fields = ["source", "original", "prime", "continuous", "ingress", "enabled_raw", "intermediate30", "intermediate30_accepted",
              "canonical", "pilot_accepted", "pilot_mixed", "pilot_half", "pilot_all", "forward_input", "forward", "product",
              "inverse_input", "inverse", "prepare", "ratio", "visible_scores", "admitted_scores"]
    p = _receipt(log, "HIGH_RATE60_PREFIX", fields)
    require(p["source"] == p["ingress"] == 16425 and p["original"] == 16423 and p["prime"] == 2 and p["continuous"] == 13312 and
            p["admitted_scores"] == 894 and 894 <= p["visible_scores"] <= 1341 and 14475 <= p["enabled_raw"] < 16423 and
            3609 <= p["canonical"] < 4096 and 3609 <= p["pilot_mixed"] <= p["pilot_accepted"] <= p["canonical"] and
            1805 <= p["pilot_half"] <= 2048 and 602 <= p["pilot_all"] <= 683,
            "source/cascade/pilot/map support-only bounds")
    require(7231 <= p["intermediate30_accepted"] <= p["intermediate30"] <= (p["enabled_raw"]-13)//2 and
            p["canonical"] <= (p["intermediate30_accepted"]-13)//2,
            "two-stage accepted/emitted support arithmetic")
    for name in ["forward_input", "forward", "product", "inverse_input", "inverse"]:
        require(1024 <= p[name] <= 3584, "FFT stage prefix outside two-block/full-golden support")
    require(p["forward_input"] >= p["forward"] >= p["product"] >= p["inverse_input"] >= p["inverse"] and
            3129 >= p["prepare"] >= p["ratio"] >= p["visible_scores"], "impossible FFT/score prefix ordering")
    cont = _receipt(log, "HIGH_RATE60_CONTINUOUS", ["count", "first", "stop", "first_rise_fs", "last_rise_fs", "off_fs", "startup_pause_outside_segment"])
    require(cont["count"] == 13312 and cont["first"] == 34359738322 and cont["stop"] == 34359751634 and
            cont["startup_pause_outside_segment"] == 1 and
            abs(cont["last_rise_fs"]-cont["first_rise_fs"]-13311*16666666) <= 1 and
            abs(cont["off_fs"]-cont["last_rise_fs"]-8333333) <= 1,
            "continuous13312 original source edge/index interval")
    phase = (cont["first_rise_fs"]-10433333) % 16666666
    require(cont["first_rise_fs"] >= 10433333 and min(phase,16666666-phase) <= 1, "continuous segment is not source-clock aligned")
    b, clock = native["budget"], native["clock"]
    # Common-source coordinates must agree with actual control-cycle witnesses,
    # not merely independently satisfy the old native bounds.
    adm = native["admission"]
    rise_at = lambda index: cont["first_rise_fs"]+(index-cont["first"])*16666666
    for cycle, time_fs in [(adm["handshake_cycle"], rise_at(adm["index"])),
                           (adm["trigger_cycle"], rise_at(34359738560)-8333333),
                           (b["capture_end"], rise_at(34359740775)+1000)]:
        require(cycle*10000000-5000000 <= time_fs < cycle*10000000+5000000,
                "native command/capture cycle not on continuous original source coordinate")
    off_time = 18766666 + (clock["source_edges"]-clock["after_off_edges"]-1)*16666666
    require(abs(off_time-cont["off_fs"]) <= 1, "native and continuous source-off coordinates disagree")
    prime = (directory / "paired60_actual_prime.txt").read_text().splitlines()
    require(prime == [f"{34359735209+n:016x} {n+1:08x}" for n in range(2)], "separate disabled prime evidence")
    fft = _receipt(log, "HIGH_RATE60_FFT_CLOCK", ["first_edge_fs", "first_fall_fs", "half_fs", "period_fs", "edges", "ideal_clock", "mmcm_claim"])
    for field, expected in {"first_edge_fs": 4157143, "first_fall_fs": 7014286, "half_fs": 2857143, "period_fs": 5714286}.items():
        require(abs(fft[field]-expected) <= 1, "actual175 ideal oscillator origin/cadence")
    require(fft["ideal_clock"] == 1 and fft["mmcm_claim"] == 0 and
            fft["edges"] == (b["quiet_end"]*10000000-4157143)//5714286+1, "FFT edge inventory/scope")
    overlap = _receipt(log, "HIGH_RATE60_OVERLAP", ["capture_actual_fft", "compute_coarse_pilot", "compute_after_stop", "bank_quiet_fast_cycles", "source_at_stop", "source_at_native_release", "source_at_map_release"])
    require(min(overlap["capture_actual_fft"],overlap["compute_coarse_pilot"],overlap["compute_after_stop"]) > 0 and
            overlap["bank_quiet_fast_cycles"] >= 32 and 3113 < overlap["source_at_stop"] < 16425 and
            overlap["source_at_native_release"] == overlap["source_at_map_release"] == 16425,
            "actual own-domain overlap/source-off/retention witnesses missing")
    retention = _receipt(log, "HIGH_RATE60_RETENTION_PASS", ["map_retained_through_native_release", "native_result_released", "map_words", "source"])
    require(retention == {"map_retained_through_native_release": 1, "native_result_released": 1, "map_words": 447, "source": 16425}, "independent map/native result lifetime")
    stop = _receipt(log, "HIGH_RATE60_STOP", ["selected", "visible", "source", "canonical", "pilot", "native_capture", "native_busy"])
    require(stop["selected"] == 894 and 894 <= stop["visible"] <= p["visible_scores"] and stop["source"] == overlap["source_at_stop"] and
            stop["canonical"]+512 < p["canonical"] and 1 <= stop["pilot"] < 512 and
            0 <= stop["native_capture"] <= 520 and stop["native_busy"] in [0,1], "STOP prefix/independent pilot/native lifetime")
    words = rows((cohort / "pilot_expected_ci16.mem").read_bytes(),512,8)
    indexes = rows((cohort / "pilot_expected_index_u64.mem").read_bytes(),512,16)
    observed = re.findall(r"^HIGH_RATE60_PILOT_WORD ordinal=(\d+) newest=([0-9a-f]{16}) word=([0-9a-f]{8})$",log,re.MULTILINE)
    require(observed == [(str(n),f"{indexes[n]:016x}",f"{words[n]:08x}") for n in range(512)], "all512 pilot values/indexes")
    require((directory / "paired_pilot_actual.ci16").read_bytes() == (cohort / "pilot_expected.ci16").read_bytes(), "independent2048 pilot bytes")
    snapshots = re.findall(r"^HIGH_RATE60_PIL1_SNAPSHOT generation=1 raw_words=((?: [0-9a-f]{8}){26})$",log,re.MULTILINE)
    require(len(snapshots) == 1, "PIL1 snapshot uniqueness/generation")
    snap = [int(word,16) for word in snapshots[0].split()]
    pairs = [snap[2*n] | snap[2*n+1]<<32 for n in range(8)]
    require(pairs == [indexes[0],indexes[-1],512,512,90,0,p["pilot_accepted"],p["pilot_all"]] and
            snap[16] == snap[18] == 0 and snap[17]&255 == 0 and snap[19] == 24 and snap[20] == r["pilot_visit"] and not any(snap[22:]),
            "PIL1 coherent counts/support/visit/health")
    require(Counter(re.findall(r"^(HIGH_RATE60_\S+)", log, re.MULTILINE)) == EXPECTED_MARKERS,
            "missing/unrecognized/duplicate paired60 evidence marker inventory")
    return {"result": "HIGH_RATE60_SIMULATION_VERIFIED", "profile": PROFILE, "prefix": p, "overlap": overlap,
            "native": native, "continuous": cont, "fft_clock": fft,
            "scope": r["scope"]}

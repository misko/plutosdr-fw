"""Additive 30-upper/175/447x2 harness preparation, not numerical regeneration.

The accepted51 originals are immutable. Only two disabled-DDC prime beats,
4096 source-only continuation beats, and nine raw-tuple wire serializers are
added. The continuation length was admitted by native30_budget before this
producer or any actual paired evaluation. No new FFT oracle is fitted to RTL.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .native30_budget import budget

COHORT_SHA = "ba3046d56a6eb1cf2792070cf63f8d7ffb44958f0ef9f4999907b2b2a49bdb4d"
PROFILE = "30-upper-bank175-native132-pil1-447x2-healthy-v1"
RAW_FIRST = 17179867609
TAIL_SEED = 0x30B17552
RAW_FIELDS = [
    ("lag", "lag", 8, 2), ("start_index", "index", 64, 16),
    ("real", "real", 48, 12), ("imag", "imag", 48, 12),
    ("Ex", "ex", 48, 12), ("Eh", "eh", 48, 12),
    ("power", "power", 96, 24), ("saturation", "saturation", 9, 3),
    ("qualified", "qualified", 1, 1),
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("ascii")


def mem(values, width):
    if any(not 0 <= n < 1 << (4 * width) for n in values):
        raise ValueError("wire serializer overflow")
    return "".join(f"{n:0{width}x}\n" for n in values).encode("ascii")


def rows(payload, count, width):
    data = payload.decode("ascii").splitlines()
    if len(data) != count or any(not re.fullmatch(rf"[0-9a-f]{{{width}}}", x) for x in data):
        raise ValueError("wrong fixture geometry/packing")
    return [int(x, 16) for x in data]


def continuation():
    state = TAIL_SEED
    result = []
    for _ in range(budget()["continuation_raw_count"]):
        components = []
        for _ in range(2):
            state ^= (state << 13) & 0xffffffff
            state ^= state >> 17
            state ^= (state << 5) & 0xffffffff
            components.append((state % 801 - 400) & 0xffff)
        result.append(components[0] | components[1] << 16)
    return result


def fixture_payloads(cohort: Path):
    receipt_bytes = (cohort / "cohort.json").read_bytes()
    if sha(receipt_bytes) != COHORT_SHA:
        raise ValueError("unapproved original cohort receipt")
    receipt = json.loads(receipt_bytes)
    if len(receipt["files"]) != 51:
        raise ValueError("original51 inventory changed")
    payloads = {}
    for name, expected in receipt["files"].items():
        data = (cohort / name).read_bytes()
        if sha(data) != expected["sha256"]:
            raise ValueError(f"original golden changed: {name}")
        payloads[name] = data
    originals = {name: sha(data) for name, data in payloads.items()}
    source = rows(payloads["source_ci16.mem"], 8205, 8)
    indexes = rows(payloads["source_index_u64.mem"], 8205, 16)
    if indexes != list(range(RAW_FIRST, RAW_FIRST + 8205)):
        raise ValueError("original raw support/phase changed")
    tail = continuation()
    payloads["paired_source_ci16.mem"] = mem([1, 2, *source, *tail], 8)
    payloads["paired_source_index_u64.mem"] = mem(list(range(RAW_FIRST - 2, RAW_FIRST + 8205 + len(tail))), 16)
    payloads["continuation_ci16.mem"] = mem(tail, 8)
    raw = json.loads(payloads["native_all_raw_tuples.json"])
    if [row["lag"] for row in raw] != list(range(-64, 65)) or sum(row["qualified"] for row in raw) != 121:
        raise ValueError("native raw/qualified geometry changed")
    for field, suffix, bits, width in RAW_FIELDS:
        payloads[f"native_raw_{suffix}.mem"] = mem([int(row[field]) & ((1 << bits) - 1) for row in raw], width)
    return payloads, {
        "profile": PROFILE, "original_cohort_sha256": COHORT_SHA,
        "original51": originals, "budget": budget(),
        "raw_first": RAW_FIRST, "disabled_prime": [RAW_FIRST - 2, RAW_FIRST],
        "original_raw_half_open": [RAW_FIRST, RAW_FIRST + 8205],
        "continuation_raw_half_open": [RAW_FIRST + 8205, RAW_FIRST + 8205 + 4096],
        "all_source_count": 12303, "original_raw_preroll_count": 1549,
        "continuation_rng": "uint32 xorshift13,17,5; separate I,Q draws modulo801 minus400",
        "continuation_seed": TAIL_SEED,
        "continuation_consumer": "source/CDC only; conditioner must be disabled before continuation; native capture already complete",
        "canonical_ledger": "five-edge issue pipeline; disabled flush cancels unpromised pipeline; every visible enabled prefix equals original oracle",
        "coarse_admitted": 894, "coarse_visible_min": 894, "coarse_visible_max": 1341,
        "fft_prefix_max_words_per_stage": 3584, "map_words": 447,
        "scope": "static-known-center healthy numerical composition; no causal/RF/ADC/DMA/IIO/physical/production-geometry qualification",
    }


def prepare_vectors(cohort: Path, output: Path):
    if output.exists():
        raise ValueError("refusing to overwrite prepared evidence")
    payloads, receipt = fixture_payloads(cohort)
    output.mkdir(parents=True)
    for name, data in payloads.items():
        (output / name).write_bytes(data)
    receipt["files"] = {name: {"sha256": sha(data), "bytes": len(data)} for name, data in sorted(payloads.items())}
    (output / "harness.json").write_bytes(encoded(receipt))
    return receipt


def verify_vectors(cohort: Path, directory: Path):
    payloads, expected = fixture_payloads(cohort)
    expected["files"] = {name: {"sha256": sha(data), "bytes": len(data)} for name, data in sorted(payloads.items())}
    if (directory / "harness.json").read_bytes() != encoded(expected):
        raise ValueError("harness profile/budget/source receipt mismatch")
    if {path.name for path in directory.iterdir()} != {*payloads, "harness.json"}:
        raise ValueError("unexpected/missing fixture inventory")
    for name, data in payloads.items():
        if (directory / name).is_symlink() or (directory / name).read_bytes() != data:
            raise ValueError(f"fixture mismatch: {name}")
    return expected


def verify_native_results(directory: Path, log: str):
    expected = json.loads((directory / "native_all_raw_tuples.json").read_bytes())
    packet = (directory / "native_expected_packet.mem").read_text().splitlines()
    packet_rows = re.findall(r"^NATIVE30_PACKET_WORD pass=(\d+) word=(\d+) data=([0-9a-f]{8})$", log, re.MULTILINE)
    if packet_rows != [(str(p), str(n), packet[n]) for p in range(2) for n in range(26)]:
        raise ValueError("missing/duplicate/wrong native packet word")
    actual = (directory / "native30_actual_raw_tuples.txt").read_text().splitlines()
    if len(actual) != 129:
        raise ValueError("all129 actual raw tuples required")
    for line, original in zip(actual, expected, strict=True):
        words = line.split()
        if len(words) != 9 or int(words[0]) != original["lag"] or int(words[8]) != int(original["qualified"]):
            raise ValueError("raw tuple identity/qualification mismatch")
        for word, (field, _, bits, _) in zip(words[1:8], RAW_FIELDS[1:8], strict=True):
            if int(word, 16) != int(original[field]) & ((1 << bits) - 1):
                raise ValueError(f"raw tuple {field} mismatch")


TERMINAL = (
    f"HIGH_RATE30_PASS profile={PROFILE} admitted=894 map_words=447 capture=260 "
    "raw_tuples=129 qualified_tuples=121 packet_words=26 packet_reads=52 "
    "pilot_words=512 bytes=2048 source=12303 "
    "STATIC_NOT_CAUSAL_NO_RF_DMA_IIO_PHYSICAL_OR_PRODUCTION_MAP_CLAIM"
)


def one_receipt(log, prefix):
    lines = [line for line in log.splitlines() if line.startswith(prefix + " ")]
    if len(lines) != 1:
        raise ValueError(f"missing/duplicate {prefix} receipt")
    fields = {}
    for item in lines[0][len(prefix) + 1:].split():
        key, value = item.split("=", 1)
        if key in fields or not value.isdigit():
            raise ValueError(f"malformed {prefix} receipt")
        fields[key] = int(value)
    return fields


def verify_results(directory: Path):
    log = (directory / "simulate.log").read_text()
    # Healthy-only: no deliberately induced fault exemption is admitted.
    if re.search(r"(?im)\b(?:FAIL(?:ED|URE)?|FATAL|ERROR)\b|HIGH_RATE30_FAIL|NATIVE30_\w*FAIL", log):
        raise ValueError("simulation contains failure evidence")
    if log.splitlines().count(TERMINAL) != 1 or sum(line.startswith("HIGH_RATE30_PASS") for line in log.splitlines()) != 1:
        raise ValueError("missing/duplicate/malformed healthy terminal")
    expected_preroll = "HIGH_RATE30_PREROLL_PASS disabled_prime=2 original_raw=1549 canonical=768 public_psma=00010007 caps=000007ff native_taps=132"
    if log.splitlines().count(expected_preroll) != 1:
        raise ValueError("missing/duplicate public admission and preroll")
    prefix = one_receipt(log, "HIGH_RATE30_PREFIX")
    if set(prefix) != {"source", "ingress", "enabled_raw", "canonical", "pilot_accepted", "pilot_mixed", "pilot_half", "pilot_all", "forward_input", "forward", "product", "inverse_input", "inverse", "prepare", "ratio", "visible_scores", "admitted_scores"}:
        raise ValueError("unknown/missing prefix inventory")
    if not (prefix["source"] == prefix["ingress"] == 12303 and prefix["admitted_scores"] == 894 and
            894 <= prefix["visible_scores"] <= 1341 and 3609 <= prefix["canonical"] < 4096 and
            7231 <= prefix["enabled_raw"] < 8205 and 3610 <= prefix["pilot_accepted"] <= prefix["canonical"] and
            3610 <= prefix["pilot_mixed"] <= prefix["pilot_accepted"] and
            1805 <= prefix["pilot_half"] <= 2048 and 602 <= prefix["pilot_all"] <= 683):
        raise ValueError("source/filter/map prefix outside frozen support")
    for name in ["forward_input", "forward", "product", "inverse_input", "inverse"]:
        if not 1024 <= prefix[name] <= 3584:
            raise ValueError("FFT prefix outside frozen support")
    for name in ["prepare", "ratio"]:
        if not 894 <= prefix[name] <= 3129:
            raise ValueError("score-prepare prefix outside frozen support")
    if not (prefix["forward_input"] >= prefix["forward"] >= prefix["product"] >= prefix["inverse_input"] >= prefix["inverse"] and
            prefix["prepare"] >= prefix["ratio"] >= prefix["visible_scores"]):
        raise ValueError("causally impossible stage inventory")
    overlap = one_receipt(log, "HIGH_RATE30_OVERLAP")
    if set(overlap) != {"capture_actual_fft", "compute_coarse_pilot", "compute_after_stop", "bank_quiet_fast_cycles", "source_at_stop", "source_at_native_release", "source_at_map_release"} or not (
        min(overlap["capture_actual_fft"], overlap["compute_coarse_pilot"], overlap["compute_after_stop"]) > 0 and
        overlap["bank_quiet_fast_cycles"] >= 32 and 1551 < overlap["source_at_stop"] < overlap["source_at_native_release"] <= overlap["source_at_map_release"] < 12303
    ):
        raise ValueError("missing own-domain overlap/source lifetime evidence")
    retention = one_receipt(log, "HIGH_RATE30_RETENTION_PASS")
    if retention != {"map_retained_through_native_release": 1, "native_result_released": 1,
                     "map_words": 447, "source": overlap["source_at_native_release"]}:
        raise ValueError("independent retained map/native release mismatch")
    stop = one_receipt(log, "HIGH_RATE30_STOP")
    if set(stop) != {"selected", "visible", "source", "canonical", "pilot", "native_capture", "native_busy"} or not (
        stop["selected"] == 894 and 894 <= stop["visible"] <= prefix["visible_scores"] and
        stop["source"] == overlap["source_at_stop"] and stop["canonical"] + 512 < prefix["canonical"] and
        1 <= stop["pilot"] < 512 and 0 <= stop["native_capture"] <= 260 and stop["native_busy"] in {0, 1}
    ):
        raise ValueError("STOP prefix/lifetime mismatch")
    timing = one_receipt(log, "NATIVE30_BUDGET_PASS")
    if set(timing) != {"capture_end_cycle", "publish_cycle", "release_cycle", "engine_cycles", "post_capture_cycles", "maximum_axi_cycles", "raw", "qualified", "capture", "packet_reads"} or not (
        timing["raw"] == 129 and timing["qualified"] == 121 and timing["capture"] == 260 and timing["packet_reads"] == 52 and
        0 < timing["engine_cycles"] == timing["publish_cycle"] - timing["capture_end_cycle"] <= 24000 and
        timing["engine_cycles"] < timing["post_capture_cycles"] == timing["release_cycle"] - timing["capture_end_cycle"] <= 28000 and
        0 < timing["maximum_axi_cycles"] <= 24
    ):
        raise ValueError("native completion bound violated")
    admission = one_receipt(log, "NATIVE30_ADMISSION")
    if set(admission) != {"index", "capture_start", "lead", "deadline"} or not (
        admission["capture_start"] == 17179870128 and admission["deadline"] == 17179869408 and
        admission["index"] <= admission["deadline"] and admission["lead"] == admission["capture_start"] - admission["index"] - 1 and admission["lead"] >= 128
    ):
        raise ValueError("native actual admission coordinate mismatch")
    verify_native_results(directory, log)
    words = rows((directory / "pilot_expected_ci16.mem").read_bytes(), 512, 8)
    indexes = rows((directory / "pilot_expected_index_u64.mem").read_bytes(), 512, 16)
    pilot_lines = re.findall(r"^HIGH_RATE30_PILOT_WORD ordinal=(\d+) newest=([0-9a-f]{16}) word=([0-9a-f]{8})$", log, re.MULTILINE)
    if pilot_lines != [(str(n), f"{indexes[n]:016x}", f"{words[n]:08x}") for n in range(512)]:
        raise ValueError("pilot word/index log mismatch")
    if (directory / "paired_pilot_actual.ci16").read_bytes() != (directory / "pilot_expected.ci16").read_bytes():
        raise ValueError("pilot binary mismatch")
    snapshots = re.findall(r"^HIGH_RATE30_PIL1_SNAPSHOT generation=1 raw_words=((?: [0-9a-f]{8}){26})$", log, re.MULTILINE)
    if len(snapshots) != 1:
        raise ValueError("missing/duplicate PIL1 coherent snapshot")
    snap = [int(word, 16) for word in snapshots[0].split()]
    pairs = [snap[2*n] | snap[2*n+1] << 32 for n in range(8)]
    if pairs != [indexes[0], indexes[-1], 512, 512, 90, 0, prefix["pilot_accepted"], prefix["pilot_all"]] or (
        snap[16] or snap[17] & 255 or snap[18] or snap[19] != 24 or snap[20] != 0x30000052 or any(snap[22:])
    ):
        raise ValueError("PIL1 snapshot support/count/health mismatch")
    return {"profile": PROFILE, "result": "HIGH_RATE30_SIMULATION_VERIFIED", "prefix": prefix, "overlap": overlap, "timing": timing}

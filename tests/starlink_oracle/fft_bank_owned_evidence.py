"""Portable actual-core evidence for the three-bank island; no physical gate."""
from __future__ import annotations

import argparse
import csv
import json
import re
from fractions import Fraction
from pathlib import Path

from .fft_island_budget import sha256, verify_reference


def fields(line: str) -> dict:
    return {key: float(value) if "." in value else int(value)
            for key, value in re.findall(r"(\w+)=([0-9.]+)", line)}


def records(log: str, prefix: str) -> list[dict]:
    return [fields(line) for line in log.splitlines() if line.startswith(prefix + " ")]


def require_pass(log: str, frequency: int) -> dict:
    receipts = records(log, "FFT_BANK_OWNED_SLICE_PASS")
    if len(receipts) != 1 or re.search(r"fatal:|error:", log, re.IGNORECASE):
        raise ValueError("requires one passing actual-core receipt without simulation errors")
    receipt = receipts[0]
    required = {"fast_mhz": frequency, "healthy_blocks": 44, "purge_cases": 4,
                "fault_cases": 10, "provisional_prefix_words": 130}
    if any(receipt.get(key) != value for key, value in required.items()):
        raise ValueError("receipt omits required clock, reset, fault, or provisional-prefix evidence")
    if receipt.get("inverse_words") != 44 * 512 + receipt["provisional_prefix_words"]:
        raise ValueError("complete and provisional inverse words do not reconcile")
    if any(receipt.get(key, 0) < 1 for key in
           ("overlap_loads", "acceptance_equality_witnesses", "closed_input_prefetch_witnesses",
            "held_final_ready_witnesses")):
        raise ValueError("missing required ownership/handshake witness")
    return receipt


def budget(interval: int, frequency: int) -> dict:
    if min(interval, frequency) <= 0:
        raise ValueError("positive cycle count and MHz required")
    allowed = Fraction(447 * frequency, 15)
    return {"observed_interval_fast_cycles": interval,
            "observed_interval_us": float(Fraction(interval, frequency)),
            "canonical_15MSps_budget_fast_cycles": float(allowed),
            "slack_fast_cycles": float(allowed - interval),
            "slack_us": float((allowed - interval) / frequency),
            "observed_interval_within_budget": interval <= allowed,
            "universal_worst_case_bound_proved": False}


def exactly_one(rows: list[dict], key: str, *, inverse: int | None = None) -> int:
    found = [row["cycle"] for row in rows if row[key] == 1 and
             (inverse is None or row["inverse"] == inverse)]
    if len(found) != 1:
        raise ValueError(f"expected exactly one {key} in the measured block")
    return found[0]


def time_for(collection: list[dict], epoch: int, index: int) -> float:
    found = [row["time_ns"] for row in collection if row["epoch"] == epoch and row["block"] == index]
    if len(found) != 1:
        raise ValueError("missing actual slow bank transfer endpoint")
    return found[0]


def read_run(directory: Path, frequency: int) -> dict:
    sim = directory / "project/fft_bank_owned_slice.sim/sim_1/behav/xsim"
    log_path, trace_path = sim / "simulate.log", sim / "fft_bank_owned_trace.csv"
    log = log_path.read_text()
    receipt = require_pass(log, frequency)
    with trace_path.open(newline="") as stream:
        trace = [{key: None if value in {"x", "z"} else int(value)
                  for key, value in row.items()} for row in csv.DictReader(stream)]
    admissions = records(log, "BANK_FORWARD_ADMIT")
    captures = records(log, "BANK_CAPTURE_START")
    capture_commits = records(log, "BANK_CAPTURE_COMMIT")
    output_starts, output_ends = records(log, "BANK_OUTPUT_START"), records(log, "BANK_OUTPUT")
    jobs = records(log, "BANK_JOB")
    blocks = []
    for epoch, count in ((1, 32), (2, 6)):
        epoch_admits = [row for row in admissions if row["epoch"] == epoch]
        epoch_trace = [row for row in trace if row["epoch"] == epoch]
        if len(epoch_admits) != count:
            raise ValueError("missing nominal or repeated-stall block admission")
        for index, admit in enumerate(epoch_admits):
            first = admit["fast_cycle"]
            stop = epoch_admits[index + 1]["fast_cycle"] if index + 1 < count else epoch_trace[-1]["cycle"] + 1
            rows = [row for row in epoch_trace if first <= row["cycle"] < stop]

            forward_commit = exactly_one(rows, "guard_commit", inverse=0)
            product_commit = exactly_one(rows, "product_commit")
            inverse_admit = exactly_one(rows, "admit", inverse=1)
            inverse_commit = exactly_one(rows, "guard_commit", inverse=1)
            handoff = next(row["cycle"] for row in rows if row["handoff_ack"] == 1)
            output_ack = next(row["cycle"] for row in rows
                              if row["cycle"] > inverse_commit + 1 and row["output_bank_ready"] == 1)
            if not forward_commit < product_commit < handoff < inverse_admit < inverse_commit < output_ack:
                raise ValueError("validated bank ownership/ACK order violated")
            if any(row["core_resetn"] != 1 for row in rows if inverse_commit <= row["cycle"] <= output_ack):
                raise ValueError("inverse core epoch reset before actual output ACK")
            pair = [job for job in jobs if job["epoch"] == epoch and job["admit"] in {first, inverse_admit}]
            if len(pair) != 2 or any(job["input_span"] != 513 or job["commit_delta"] != 1809 or
                                     job["input_last_to_output_first"] != 781 for job in pair):
                raise ValueError("actual FFT service behavior changed")

            captured, capture_commit = time_for(captures, epoch, index), time_for(capture_commits, epoch, index)
            output_start, output_end = time_for(output_starts, epoch, index), time_for(output_ends, epoch, index)
            blocks.append({
                "epoch": epoch, "profile": admit["profile"], "block": index,
                "forward_admit_cycle": first, "forward_commit_cycle": forward_commit,
                "product_commit_cycle": product_commit, "ownership_handoff_cycle": handoff,
                "inverse_admit_cycle": inverse_admit, "inverse_commit_cycle": inverse_commit,
                "actual_final_output_ACK_cycle": output_ack,
                "forward_commit_to_product_commit_cycles": product_commit - forward_commit,
                "product_commit_to_owned_prefetch_cycles": handoff - product_commit,
                "owned_prefetch_to_inverse_admit_cycles": inverse_admit - handoff,
                "inverse_commit_to_actual_output_ACK_cycles": output_ack - inverse_commit,
                "forward_to_inverse_admission_cycles": inverse_admit - first,
                "source_first_write_ns": captured, "source_final_write_ns": capture_commit,
                "inverse_first_slow_read_ns": output_start, "inverse_final_slow_read_ns": output_end,
                "capture_span_inclusive_slow_cycles": round((capture_commit - captured) / 10) + 1,
                "output_span_inclusive_slow_cycles": round((output_end - output_start) / 10) + 1,
                "source_first_write_to_output_last_us": (output_end - captured) / 1000,
                "interval_from_previous_forward_cycles": admit["interval_cycles"],
            })
    nominal = max(row["interval_from_previous_forward_cycles"] for row in blocks if row["profile"] == 0)
    stalled = max(row["interval_from_previous_forward_cycles"] for row in blocks if row["profile"] == 1)
    if nominal != receipt["nominal_max_forward_interval_cycles"]:
        raise ValueError("nominal trace interval disagrees with terminal receipt")
    sources = directory / "frozen_sources"
    return {"fast_mhz": frequency, "slow_mhz": 100, "receipt": receipt,
            "nominal": budget(nominal, frequency), "repeated_stalls": budget(stalled, frequency),
            "log_sha256": sha256(log_path), "trace_sha256": sha256(trace_path),
            "trace_rows": len(trace), "frozen_vector_hashes": verify_reference(sources),
            "frozen_source_hashes": {path.name: sha256(path) for path in sorted(sources.iterdir()) if path.is_file()},
            "prefix_fault_injection": records(log, "BANK_PREFIX_FAULT_INJECT"),
            "prefix_fault_quarantine": records(log, "BANK_PREFIX_FAULT_QUARANTINED"),
            "measured_blocks": blocks}


def read_mutation(directory: Path) -> dict:
    path = directory / "project/fft_bank_owned_slice.sim/sim_1/behav/xsim/simulate.log"
    log = path.read_text()
    marker = "Fatal: join acceptance differs from guard retirement"
    if marker not in log or "FFT_BANK_OWNED_SLICE_PASS" in log:
        raise ValueError("missing the specific held-final mutation rejection")
    return {"mutation": "remove only joiner product_bank_ready input-valid gate",
            "expected_failure": marker, "log_sha256": sha256(path),
            "mutated_RTL_sha256": sha256(directory / "frozen_sources/starlink_pss_fft_bank_owned_slice.v"),
            "scope": "actual generated core, delayed status, empty join pipeline, qualified held final"}


def read_resources(directory: Path) -> dict:
    text = (directory / "resource_receipt.txt").read_text()
    if "black_boxes=0" not in text or "synthesis_only=true" not in text:
        raise ValueError("requires complete actual-core synthesis inventory")
    return {"scope": "three-bank slice synthesis only, unplaced, unrouted",
            "receipt": text, "utilization_report": (directory / "utilization.rpt").read_text(),
            "hierarchy_report": (directory / "hierarchy.rpt").read_text(),
            "scope_and_pre_synthesis_source_hashes": (directory / "scope.txt").read_text(),
            "frozen_source_hashes": {path.name: sha256(path) for path in
                                     sorted((directory / "frozen_sources").iterdir()) if path.is_file()},
            "no_achieved_clock_or_receiver_area_saving_claim": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("evidence_150", type=Path)
    parser.add_argument("evidence_175", type=Path)
    parser.add_argument("evidence_200", type=Path)
    parser.add_argument("mutation", type=Path)
    parser.add_argument("--synthesis", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("refusing to overwrite portable evidence")
    runs = [read_run(path, frequency) for path, frequency in
            ((args.evidence_150, 150), (args.evidence_175, 175), (args.evidence_200, 200))]
    source_key = "starlink_pss_fft_bank_owned_slice.v"
    if len({run["frozen_source_hashes"][source_key] for run in runs}) != 1:
        raise ValueError("clock runs used different source RTL")
    report = {"schema": "fft-bank-owned-actual-core-evidence-v1", "runs": runs,
              "mutation": read_mutation(args.mutation), "actual_banks": [
                  {"name": "source", "writer": "100 MHz", "reader": "fast", "words": 512, "bits": 36},
                  {"name": "product", "writer": "fast", "reader": "fast", "words": 512, "bits": 36},
                  {"name": "inverse_output", "writer": "fast", "reader": "100 MHz", "words": 512, "bits": 36}],
              "additional_modeled_outer_banks": 0,
              "continuous_canonical_overlap_energy_scoring_qualified": False,
              "physical_CDC_full_receiver_RF_qualified": False}
    if args.synthesis:
        report["synthesis"] = read_resources(args.synthesis)
        if report["synthesis"]["frozen_source_hashes"][source_key] != runs[0]["frozen_source_hashes"][source_key]:
            raise ValueError("synthesis differs from the simulated source RTL")
    with args.output.open("x") as output:
        json.dump(report, output, indent=2)
        output.write("\n")
    print(json.dumps({"output": str(args.output), "budgets": [
        {"MHz": run["fast_mhz"], "nominal": run["nominal"], "stalled": run["repeated_stalls"]}
        for run in runs]}, indent=2))


if __name__ == "__main__":
    main()

"""Trace-backed scheduling estimate for the isolated FFT island, not RTL proof.

The measured single-clock slice retains both internal 512x36 mailbox copies.
The model ADDS one 512x36 ingress and one 512x36 egress CDC bank. Their slow
transfers overlap island compute only when bank ownership permits. CDC costs
are declared assumptions (four destination clocks to readable data and three
source clocks to ACK), not measured CDC/physical guarantees. A finite trace is
not a universal bound on generated FFT latency or permissible stalls.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from fractions import Fraction
from itertools import pairwise
from pathlib import Path

STRIDE = 447
CANONICAL_RATE = 15_000_000
BLOCK_PERIOD = Fraction(STRIDE, CANONICAL_RATE)
REFERENCE_HASHES = {
    "samples_ci16": "4abe27ba953cf49f84d9979966625a2436ad59359b616321e881b42dd4c84723",
    "forward_q17": "d934a8ecd0888c294fc0abfbdbe7c439bff7097ea169b937638c4b7000479bfd",
    "product_q17": "b316522a68529a73d3d8e4121badea61e24621c93a97365e894f5bd416bcecb7",
    "inverse_q17": "c8c5b4e28ab621d0b1d5c1dc288f6e66495b3319d348442ce5d7b8f6ea8025a1",
    "forward_exponents": "18ac6df6a1ae3f19e5153524b33f336a60eabdd6dbd182d46c43450302e4b52f",
    "inverse_exponents": "899b7a2486fd3759c6e4905110fc4d86ffdb6ec884da2a7f2aca4acdfd363dff",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_reference(directory: Path) -> dict[str, str]:
    observed = {name: sha256(directory / f"{name}.mem") for name in REFERENCE_HASHES}
    if observed != REFERENCE_HASHES:
        raise ValueError("immutable FFT numerical reference mismatch")
    return observed


def events(rows: list[dict], key: str) -> list[int]:
    return [row["cycle"] for row in rows if row[key] == 1]


def read_measurement(trace_path: Path, log_path: Path) -> dict:
    log = log_path.read_text()
    if "FFT_ISLAND_SLICE_PASS" not in log or re.search(r"fatal:|error:", log, re.IGNORECASE):
        raise ValueError("measurement lacks a passing actual-core simulation")
    with trace_path.open(newline="") as stream:
        rows = [{key: int(value) if value not in {"x", "z"} else None
                 for key, value in row.items()} for row in csv.DictReader(stream)]
    blocks = []
    for line in log.splitlines():
        if not line.startswith("ISLAND_BLOCK "):
            continue
        fields = {key: int(value) for key, value in re.findall(r"(\w+)=(\d+)", line)}
        block_rows = [row for row in rows if row["case"] == fields["case"] and
                      fields["first_input"] <= row["cycle"] <= fields["last_output"]]
        starts = events(block_rows, "admit")
        if len(starts) != 2:
            raise ValueError("complete block must have one forward and one inverse job")
        jobs = []
        for index, start in enumerate(starts):
            stop = starts[index + 1] if index == 0 else fields["last_output"] + 1
            job = [row for row in block_rows if start <= row["cycle"] < stop]
            delivered, raw = events(job, "core_input"), events(job, "core_output")
            config, status, commit = (events(job, key) for key in ("config", "status", "commit"))
            if not (len(delivered) == len(raw) == 512 and
                    len(config) == len(status) == len(commit) == 1):
                raise ValueError("job counts/config/status/commit are incomplete")
            jobs.append({
                "inverse": index, "admit_cycle": start,
                "admit_to_config": config[0] - start,
                "config_to_first_input": delivered[0] - config[0],
                "input_transfer_span": delivered[-1] - delivered[0] + 1,
                "last_input_to_first_output": raw[0] - delivered[-1],
                "output_transfer_span": raw[-1] - raw[0] + 1,
                "status_from_admission": status[0] - start,
                "last_output_to_commit": commit[0] - raw[-1],
                "admission_to_commit": commit[0] - start,
            })
        fields["jobs"] = jobs
        fields["first_output_offset"] = events(block_rows, "output")[0] - fields["first_input"]
        fields["forward_to_inverse_admission"] = starts[1] - starts[0]
        blocks.append(fields)
    nominal = [block for block in blocks if block["profile"] == 0 and block["case"] <= 6]
    if len(nominal) != 6:
        raise ValueError("six sequential nominal blocks required")
    intervals = [right["first_input"] - left["first_input"]
                 for left, right in pairwise(nominal)]
    return {
        "trace_sha256": sha256(trace_path), "log_sha256": sha256(log_path),
        "actual_clock_hz": 200_000_000,
        "nominal_observed_max_start_interval_cycles": max(intervals),
        "nominal_first_output_offset_cycles": max(block["first_output_offset"] for block in nominal),
        "blocks": blocks, "universal_latency_bound_proved": False,
    }


@dataclass(frozen=True)
class Estimate:
    fast_hz: int
    blocks: int
    extra_island_cycles_per_block: int
    egress_stall_slow_cycles_per_block: int
    nominal_island_us: float
    block_budget_us: float
    island_slack_us: float
    maximum_start_backlog_us: float
    final_start_backlog_us: float
    maximum_egress_wait_us: float
    maximum_energy_age_samples: int
    first_energy_expiry_block: int | None
    maximum_pending_input_blocks: int
    sustained_under_declared_model: bool


def estimate(fast_hz: int, *, service_cycles: int, output_offset: int,
             blocks: int = 4096, extra_cycles: int = 0, egress_stall: int = 0) -> Estimate:
    if min(fast_hz, service_cycles, blocks) <= 0 or min(output_offset, extra_cycles, egress_stall) < 0:
        raise ValueError("positive clocks/service/blocks and nonnegative offsets/stalls required")
    fast, slow = Fraction(1, fast_hz), Fraction(1, 100_000_000)
    duration = (service_cycles + extra_cycles) * fast
    ingress_free = egress_free = engine_free = Fraction(0)
    max_backlog = max_egress_wait = Fraction(0)
    max_energy_age = max_pending = 0
    first_expiry = None
    for block in range(blocks):
        # First complete block requires sample ordinals 0..511. No ADC backpressure.
        captured = Fraction(511 + STRIDE * block, CANONICAL_RATE)
        fill_start = max(captured, ingress_free)
        ingress_available = fill_start + 512 * slow + 4 * fast
        start = max(ingress_available, engine_free)
        ingress_free = start + 512 * fast + 3 * slow
        nominal_start = captured + 512 * slow + 4 * fast
        backlog = start - nominal_start
        max_backlog = max(max_backlog, backlog)
        max_pending = max(max_pending, math.ceil((start - captured) / BLOCK_PERIOD))
        # The internal inverse bank holds all 512 validated words while the
        # outer bank is unavailable. Its real ACK epoch is retained meanwhile.
        output_nominal = start + (output_offset + extra_cycles) * fast
        output_start = max(output_nominal, egress_free)
        egress_wait = output_start - output_nominal
        max_egress_wait = max(max_egress_wait, egress_wait)
        outer_commit = output_start + 512 * fast
        read_start = outer_commit + (4 + egress_stall) * slow
        egress_free = read_start + 512 * slow + 3 * fast
        engine_free = start + duration + egress_wait
        # First usable IFFT ordinal is 65; allow eight additional slow clocks
        # to request energy. Scoring/normalization itself is NOT implemented.
        energy_lookup = read_start + (65 + 8) * slow
        energy_created = Fraction(STRIDE * block + 65, CANONICAL_RATE)
        energy_age = math.ceil((energy_lookup - energy_created) * CANONICAL_RATE)
        max_energy_age = max(max_energy_age, energy_age)
        if energy_age >= 2048 and first_expiry is None:
            first_expiry = block
    return Estimate(
        fast_hz, blocks, extra_cycles, egress_stall,
        float(duration * 1e6), float(BLOCK_PERIOD * 1e6),
        float((BLOCK_PERIOD - duration) * 1e6), float(max_backlog * 1e6),
        float(backlog * 1e6), float(max_egress_wait * 1e6), max_energy_age,
        first_expiry, max_pending,
        duration <= BLOCK_PERIOD and first_expiry is None and max_pending <= 4,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("vectors", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("refusing to overwrite budget evidence")
    sim = args.evidence / "project/fft_island_slice.sim/sim_1/behav/xsim"
    measurement = read_measurement(sim / "fft_island_trace.csv", sim / "simulate.log")
    service = measurement["nominal_observed_max_start_interval_cycles"]
    offset = measurement["nominal_first_output_offset_cycles"]
    report = {
        "schema": "isolated-fft-island-trace-budget-v1",
        "reference_hashes": verify_reference(args.vectors),
        "measurement": measurement,
        "added_outer_banks": {"ingress_words": 512, "egress_words": 512,
                              "payload_width": 36, "total_payload_bits": 36864,
                              "metadata_bits_at_least": 145,
                              "physically_measured_BRAM": False},
        "retained_internal_banks": {"count": 2, "words_each": 512, "width": 36},
        "CDC_assumptions": {"request_to_readable_destination_cycles": 4,
                            "final_read_to_ACK_source_cycles": 3,
                            "slow_hz": 100_000_000,
                            "energy_lookup_extra_slow_cycles": 8},
        "estimates": [asdict(estimate(rate, service_cycles=service, output_offset=offset,
                                      extra_cycles=extra, egress_stall=stall))
                      for rate in (150_000_000, 175_000_000, 200_000_000)
                      for extra, stall in ((0, 0), (0, 1000), (64, 0))],
        "physical_CDC_full_receiver_RF_qualified": False,
        "source_rates_share_canonical_rate": [15_000_000, 30_000_000, 60_000_000],
        "numerical_scope": "unchanged upper-edge FFT/product/IFFT frozen vectors; no new scores or lower-edge evidence",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as output:
        json.dump(report, output, indent=2)
        output.write("\n")
    print(json.dumps({"output": str(args.output), "estimates": report["estimates"]}, indent=2))


if __name__ == "__main__":
    main()

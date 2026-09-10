"""Package actual-core bank-owned composition receipts; never infer RF/timing."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

REQUIRED_COMMON_FILES = {
    name + ".v"
    for name in [
        "starlink_pss_iq_to_score_bank_owned",
        "starlink_pss_fft_bank_owned_slice",
        "starlink_pss_realtime_input_guard",
        "starlink_pss_realtime_result_guard",
        "starlink_pss_block_mailbox",
        "starlink_pss_forward_kernel_join",
        "starlink_pss_kernel_rom",
        "starlink_pss_spectrum_product",
        "starlink_pss_overlap_scheduler",
        "starlink_pss_energy_cache",
        "starlink_pss_ifft_qualifier",
        "starlink_pss_raw_result_fifo",
        "starlink_pss_energy_join",
        "starlink_pss_score_prepare",
        "starlink_pss_score_divider",
        "starlink_pss_score_divider_radix4",
        "starlink_pss_score_lanes",
        "starlink_pss_candidate_score_path",
    ]
} | {
    "simulate_iq_to_score_bank_owned.tcl",
    "prepare_iq_to_score_bank_owned.tcl",
    "create_shared_realtime_xfft_ip.tcl",
    "verify_realtime_probe_result.tcl",
    "bank_owned_iq_fault_scenarios.svh",
    "bank_owned_iq_capacity_checks.svh",
    "upper_edge_pss_kernel_q17.mem",
}


def expected_sources(mode: str) -> set[str]:
    if mode == "capacity":
        return REQUIRED_COMMON_FILES | {"tb_starlink_pss_iq_to_score_xfft_longrun.sv"}
    if mode != "numeric":
        raise ValueError("unsupported evidence mode")
    return (
        REQUIRED_COMMON_FILES
        | {"tb_starlink_pss_iq_to_score_xfft.sv"}
        | {
            name + ".mem"
            for name in [
                "samples_ci16",
                "forward_q17",
                "product_q17",
                "inverse_q17",
                "forward_exponents",
                "inverse_exponents",
                "scores_u8",
            ]
        }
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(text: str, prefix: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith(prefix + " ")]


def values(line: str) -> dict[str, int]:
    return {key: int(value) for key, value in re.findall(r"([a-z0-9_]+)=(\d+)", line)}


def require_one(text: str, prefix: str) -> str:
    found = rows(text, prefix)
    if len(found) != 1:
        raise ValueError(f"expected one {prefix}, got {len(found)}")
    return found[0]


def parse_run(directory: Path, mode: str, mhz: int, profile: str) -> dict:
    log = directory / "project/iq_to_score_bank_owned.sim/sim_1/behav/xsim/simulate.log"
    top_log = directory / (directory.name + ".log")
    transcript = log.read_text()
    top = top_log.read_text()
    if re.search(
        r"(?im)^\s*(fatal|error)(:|\s)|^IQ_TO_SCORE_XFFT(?:_LONGRUN)?_(FAIL|FAULT) ",
        transcript,
    ):
        raise ValueError("simulation contains a failure diagnostic")
    terminal = require_one(top, "BANK_IQ_TO_SCORE_ACTUAL_CORE_VERIFIED")
    if (
        terminal
        != f"BANK_IQ_TO_SCORE_ACTUAL_CORE_VERIFIED mode={mode} fast_mhz={mhz} NO_PHYSICAL_OR_RF_CLAIM"
    ):
        raise ValueError("wrong runner mode or frequency")
    scope = (directory / "scope.txt").read_text()
    if f"fast_mhz={mhz} slow_mhz=100 source_msps=15" not in scope:
        raise ValueError("scope clock mismatch")
    source_hashes = {
        path.name: digest(path)
        for path in sorted((directory / "frozen_sources").iterdir())
    }
    inventory_records = [
        (sha, Path(path))
        for sha, path in re.findall(
            r"(?:^|source_hashes=)([0-9a-f]{64})  (.+)$", scope, re.MULTILINE
        )
        if Path(path).parent == directory / "frozen_sources"
    ]
    inventory_names = [path.name for _, path in inventory_records]
    if (
        len(inventory_names) != len(set(inventory_names))
        or set(inventory_names) != expected_sources(mode)
        or set(source_hashes) != set(inventory_names)
    ):
        raise ValueError("frozen source inventory missing, extra, or duplicated")
    for name, sha in source_hashes.items():
        if f"{sha}  {directory / 'frozen_sources' / name}" not in scope:
            raise ValueError(f"pre-simulation hash missing or changed: {name}")
    bench_suffix = "_longrun" if mode == "capacity" else ""
    generated_paths = [
        directory / f"tb_starlink_pss_iq_to_score_xfft{bench_suffix}.sv",
        directory / "project/iq_to_score_bank_owned.gen/sources_1/ip/"
        "starlink_pss_fft512_bfp18_rt_candidate/synth/"
        "starlink_pss_fft512_bfp18_rt_candidate.vhd",
    ]
    generated_hashes = {}
    for path in generated_paths:
        sha = digest(path)
        if f"{sha}  {path}" not in scope:
            raise ValueError("generated bench/core changed after pre-run freeze")
        generated_hashes[path.name] = sha
    result = {
        "mode": mode,
        "fast_mhz": mhz,
        "profile": profile,
        "artifact_directory": str(directory),
        "terminal_receipt": terminal,
        "simulate_log_sha256": digest(log),
        "runner_log_sha256": digest(top_log),
        "scope_sha256": digest(directory / "scope.txt"),
        "frozen_source_sha256": source_hashes,
        "generated_bench_core_sha256": generated_hashes,
    }
    if mode == "numeric":
        numeric = values(require_one(transcript, "IQ_TO_SCORE_XFFT_PASS"))
        fault = values(require_one(transcript, "BANK_IQ_FAULT_RESET_GAP_PASS"))
        replays = [
            values(line) for line in rows(transcript, "BANK_IQ_EXACT_REPLAY_PASS")
        ]
        if any(
            numeric.get(key) != val
            for key, val in {
                "samples": 1406,
                "blocks": 3,
                "forward": 1536,
                "product": 1536,
                "inverse": 1536,
                "scores": 1341,
                "pss255": 3,
            }.items()
        ):
            raise ValueError("incomplete exact numerical fixture")
        if fault != {
            "qualifier_mutations": 5,
            "descriptor": 1,
            "core_fault": 1,
            "fft_reset": 1,
            "slow_reset": 1,
            "source_gap": 1,
            "source_index": 1,
            "exact_epochs": 4,
            "exact_scores": 5364,
            "autonomous_gap_index_recovery": 1,
        }:
            raise ValueError("incomplete specific fault/reset/gap contract")
        if replays != [{"epoch": n, "scores": 1341} for n in (2, 3, 4)]:
            raise ValueError(
                "missing ordered exact autonomous/explicit recovery epochs"
            )
        result.update(numeric=numeric, boundary_receipt=fault, exact_replays=replays)
    else:
        numeric = values(require_one(transcript, "IQ_TO_SCORE_XFFT_LONGRUN_PASS"))
        backlog = values(require_one(transcript, "IQ_TO_SCORE_XFFT_BACKLOG_PASS"))
        metadata = values(require_one(transcript, "BANK_IQ_CAPACITY_METADATA_PASS"))
        completion = require_one(transcript, "BANK_IQ_CAPACITY_COMPLETE")
        progress = [
            values(line)
            for line in rows(transcript, "IQ_TO_SCORE_XFFT_LONGRUN_PROGRESS")
        ]
        if (
            completion
            != "BANK_IQ_CAPACITY_COMPLETE blocks=64 samples=28673 scores=28608"
        ):
            raise ValueError("incomplete continuous capacity receipt")
        if any(
            numeric.get(key) != val
            for key, val in {
                "samples": 28673,
                "blocks": 64,
                "forward": 32768,
                "product": 32768,
                "inverse": 32768,
                "scores": 28608,
            }.items()
        ):
            raise ValueError("incomplete continuous counts")
        if [row.get("block") for row in progress] != list(range(1, 65)) or any(
            row.get("scores") != row["block"] * 447 for row in progress
        ):
            raise ValueError("unordered or missing score completion blocks")
        if any(
            metadata.get(key) != val
            for key, val in {
                "blocks": 64,
                "forward": 32768,
                "product": 32768,
                "inverse": 32768,
            }.items()
        ):
            raise ValueError("missing independent metadata inventory")
        if (
            numeric["fifo_max"] >= 512
            or backlog["overlap_queue_max"] > 4
            or backlog["ring_retention_age_max"] > 2048
            or backlog["energy_lookup_age_max"] >= 2048
        ):
            raise ValueError("observed backlog exhausted unchanged declared capacity")
        stalled = int(profile == "bursty-stalled")
        if (
            backlog["source_burst_mode"] != stalled
            or backlog["score_stall_mode"] != stalled
        ):
            raise ValueError("profile did not execute requested source/sink stress")
        result.update(
            counts=numeric,
            backlog=backlog,
            independent_metadata=metadata,
            score_block_progress=progress,
        )
    return result


def collect(build: Path) -> dict:
    runs = []
    for mhz in (175, 200):
        runs.append(
            parse_run(build / f"bank-iq-numeric-{mhz}-v3", "numeric", mhz, "exact")
        )
        for profile in ("nominal", "bursty-stalled"):
            runs.append(
                parse_run(
                    build / f"bank-iq-capacity-{mhz}-{profile}-v3",
                    "capacity",
                    mhz,
                    profile,
                )
            )
    for name in REQUIRED_COMMON_FILES:
        if len({run["frozen_source_sha256"][name] for run in runs}) != 1:
            raise ValueError(
                f"different source across final clock/profile runs: {name}"
            )
    return {
        "study": "additive_bank_owned_iq_to_score_actual_core_v3",
        "scope": "100 MHz overlap scheduler/energy/scorer; actual fixed XFFT at 175/200 MHz; direct canonical15 input",
        "runs": runs,
        "not_qualified": [
            "physical timing",
            "CDC signoff",
            "full receiver resources/route",
            "source15/30/60 adapters",
            "original-native fine search",
            "2.5 MS/s pilot IIO",
            "RF accuracy",
            "eight-target 120ms dwells",
            "300-second scan",
        ],
        "known_physical_counterevidence": "Parent's unchanged-constraint standalone route of frozen slice at175 reported WNS -2.557 ns; not this composition and not a timing pass.",
        "discarded_runs": {
            "numeric200v1": "bench passes but repeated malformed beat could mask specific predicate failures; obsolete coverage",
            "capacity175nominalv1": "bench counts/backlog pass; automation rejects empty marker contract",
            "numeric175and200v2": "early check observed extra registered diagnostic; FAIL lines plus invalid automation contract; not a pass",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(collect(args.build.resolve()), indent=2) + "\n")


if __name__ == "__main__":
    main()

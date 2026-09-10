#!/usr/bin/env python3
"""Freeze/verify additive30 harness inputs; never invokes Vivado or a radio."""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.starlink_oracle.high_rate_harness import (
    COHORT_SHA,
    PROFILE,
    encoded,
    prepare_vectors,
    sha,
    verify_results,
    verify_vectors,
)

ACQ = "hdl/library/starlink_pss_acquisition/"
ADDITIVE = [
    "tests/starlink_oracle/native30_budget.py", "tests/starlink_oracle/high_rate_harness.py",
    "tests/test_starlink_native30_budget.py", "tests/test_starlink_high_rate_harness.py",
    "tools/prepare_starlink_high_rate_harness.py",
    ACQ + "simulate_high_rate_bank_native_paired.tcl",
    ACQ + "create_shared_realtime_xfft_ip.tcl",
    *[ACQ + "tb/" + name for name in [
        "bank_native30_checks.svh", "bank_native30_source_checks.svh", "bank_native30_fft_checks.svh",
        "high_rate_paired_axi.svh", "tb_starlink_native30_budget.sv",
        "tb_starlink_native30_conditioner_prefix.sv", "tb_starlink_pss_30_bank_native_paired.sv",
    ]],
    "hdl/library/axi_starlink_pss_phase_map/starlink_pss_axi_lite.v",
    "hdl/library/common/up_axi.v", "hdl/library/common/ad_mem.v",
    "hdl/library/axi_starlink_pss_tracker/starlink_pss_injection_mux.v",
    *[ACQ + name for name in [
        "simulate_bank_native_paired.tcl", "prepare_bank_native_paired.tcl",
        "simulate_paired_realtime_psma_stop.tcl", "verify_realtime_probe_result.tcl",
        "tb/bank_native_paired_checks.svh", "tb/tb_starlink_pss_paired_realtime_psma_stop.sv",
    ]],
]
APPROVED_STAGE_A = {
    "hdl/library/axi_starlink_pss_acquisition/axi_starlink_pss_acquisition.v":
        "2ce3a4943b43af7120500ba5064bedf0e7b1338517cc1d41b7ea30a33b0951d0",
    "hdl/library/axi_starlink_pss_acquisition/axi_starlink_pss_phase_map_sync.v":
        "8911f045cb0811b9aabb008f8954f8c00f19bae7ba596996ec1e3c6b61f6bd4a",
}


def inventory(directory, allow_budget_link=False):
    result = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            if allow_budget_link and path.name == "test_actual_native30_bound_andcurrent" and path.resolve().parent == path.parent.resolve():
                continue  # pytest convenience alias, never an input/evidence file
            raise ValueError("no source/evidence symlinks")
        if path.is_file():
            if path.stat().st_size > 4_000_000:
                raise ValueError("unbounded input file")
            result[str(path.relative_to(directory))] = sha(path.read_bytes())
    return result


def freeze(cohort, output, budget_evidence):
    if output.exists():
        raise ValueError("refusing to overwrite prelaunch input bundle")
    if sha((cohort / "cohort.json").read_bytes()) != COHORT_SHA:
        raise ValueError("unapproved original cohort")
    original = json.loads((cohort / "cohort.json").read_bytes())
    sources = {name: ROOT / name for name in sorted(set(original["source_sha256"]) | set(ADDITIVE))}
    for name, path in sources.items():
        if name.endswith(".v"):
            baseline = subprocess.check_output([
                "git", "-C", str(ROOT / "hdl"), "show", "e2a8773bb8cd24540b0b8d2ab96a7724667ff4ba:" + name.removeprefix("hdl/"),
            ])
            if path.read_bytes() != baseline:
                raise ValueError(f"runtime delta beyond StageA: {name}")
        if name.endswith(".v") and name in original["source_sha256"] and sha(path.read_bytes()) != APPROVED_STAGE_A.get(name, original["source_sha256"][name]):
            raise ValueError(f"runtime delta beyond accepted original/StageA: {name}")
    budget_hashes = inventory(budget_evidence, allow_budget_link=True)
    budget_logs = [path for path in budget_evidence.rglob("simulation.log")]
    if len(budget_logs) != 2 or not all("NATIVE30_ONLY_PASS" in path.read_text() for path in budget_logs):
        raise ValueError("two retained actual native-only budget probes required")
    output.mkdir(parents=True)
    prepare_vectors(cohort, output / "vectors")
    shutil.copytree(cohort, output / "original_cohort")
    for name in budget_hashes:
        target = output / "native_budget_evidence" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(budget_evidence / name, target)
    for name, path in sources.items():
        target = output / "source_snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    hashes = inventory(output)
    source_hashes = {name: sha(path.read_bytes()) for name, path in sources.items()}
    for name, digest in source_hashes.items():
        if hashes["source_snapshot/" + name] != digest:
            raise ValueError("source changed while freezing")
    if budget_hashes != inventory(budget_evidence, allow_budget_link=True):
        raise ValueError("budget evidence changed while freezing")
    receipt = {
        "profile": PROFILE, "source_sha256": source_hashes,
        "source_signature": sha(encoded(source_hashes)), "files": hashes,
        "budget_evidence_sha256": budget_hashes, "approved_stage_a": APPROVED_STAGE_A,
        "actual_fft_run": False, "authorization": "offline preparation only; actual launch requires separate review",
    }
    (output / "bundle.json").write_bytes(encoded(receipt))
    return receipt


def verify_bundle(output):
    receipt = json.loads((output / "bundle.json").read_bytes())
    actual = inventory(output)
    actual.pop("bundle.json")
    if actual != receipt["files"] or receipt["profile"] != PROFILE or receipt["actual_fft_run"] is not False:
        raise ValueError("frozen bundle inventory/profile changed")
    if sha(encoded(receipt["source_sha256"])) != receipt["source_signature"]:
        raise ValueError("frozen source signature changed")
    original = json.loads((output / "original_cohort/cohort.json").read_bytes())
    if set(receipt["source_sha256"]) != set(original["source_sha256"]) | set(ADDITIVE):
        raise ValueError("frozen source-list closure changed")
    if any(receipt["files"].get("source_snapshot/" + name) != digest
           for name, digest in receipt["source_sha256"].items()):
        raise ValueError("source signature is disconnected from frozen file inventory")
    if receipt["approved_stage_a"] != APPROVED_STAGE_A:
        raise ValueError("unapproved runtime delta")
    verify_vectors(output / "original_cohort", output / "vectors")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["freeze", "verify", "result"])
    parser.add_argument("output", type=Path)
    parser.add_argument("--cohort", type=Path)
    parser.add_argument("--budget-evidence", type=Path)
    args = parser.parse_args()
    if args.mode == "freeze":
        if args.cohort is None or args.budget_evidence is None:
            parser.error("freeze requires --cohort and --budget-evidence")
        result = freeze(args.cohort.absolute(), args.output.absolute(), args.budget_evidence.absolute())
    elif args.mode == "verify":
        result = verify_bundle(args.output.absolute())
    else:
        result = verify_results(args.output.absolute())
    print(json.dumps({key: result[key] for key in ["profile", "source_signature", "result"] if key in result}, sort_keys=True))

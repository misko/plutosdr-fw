#!/usr/bin/env python3
"""Inventory/package an already terminal fixed-case run; never launches one."""

import argparse
import hashlib
import io
import json
import platform
import tarfile
from pathlib import Path

from prepare_starlink_high_rate_cases import verify, verify_simulation

ROOT = Path(__file__).resolve().parents[1]
SIGNATURE = "b9d4d306fd9665133e36dc21e24125bce9ac7a6b3b34ed335b45fd5e2ba9ab09"
RUNS = {"main-high-rate30-bank175-343-v1": "healthy343", "main-high-rate30-bank175-late447-v1": "late447"}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def package(run, report, output, handle):
    if run.name not in RUNS or not report.is_relative_to(ROOT):
        raise ValueError("unreviewed run or report")
    inventory_path = run / "artifact-inventory.sha256"
    summary_path = run / "artifact-summary.json"
    if output.exists() or output.with_suffix(".json").exists() or inventory_path.exists() or summary_path.exists():
        raise ValueError("refusing to overwrite actual receipts")
    simulation = run / "project/high_rate_bank_native_case.sim/sim_1/behav/xsim"
    bundle = verify(run / "inputs")
    result = verify_simulation(run / "inputs", simulation)
    if bundle["case"] != RUNS[run.name] or bundle["source_signature"] != SIGNATURE:
        raise ValueError("wrong case/source signature")
    if (run / "run_status.txt").read_text().splitlines()[0] != "run_tcl_exit=0 integrity_exit=0":
        raise ValueError("run/integrity not terminal success")
    if any(sha(ROOT / name) != digest for name, digest in bundle["source_sha256"].items()):
        raise ValueError("live source changed after actual run")
    artifacts = {}
    for path in sorted(run.rglob("*")):
        if path.is_symlink():
            raise ValueError("unexpected run symlink")
        if path.is_file():
            artifacts[str(path.relative_to(run))] = {"bytes": path.stat().st_size, "sha256": sha(path)}
    inventory_path.write_text("".join(f"{r['sha256']}  {name}\n" for name, r in artifacts.items()))
    external = {name: sha(run.parent / (run.name + suffix)) for name, suffix in [("vivado.log", ".vivado.log"), ("vivado.jou", ".vivado.jou")]}
    summary = {"original_handle": handle, "terminal_exit": 0, "case": RUNS[run.name], "result": result,
               "host": platform.node(), "machine": platform.machine(), "source_signature": SIGNATURE,
               "live_source_files_verified": len(bundle["source_sha256"]), "files": artifacts,
               "external_sha256": external, "artifact_inventory_sha256": sha(inventory_path),
               "inventory_exclusions": "this generated artifact-summary.json and artifact-inventory.sha256 only",
               "scope": "behavioral actual IP only; no physical, RF, driver, DMA/IIO or causal handoff claim"}
    summary_path.write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n")
    selected = {"run/" + str(path.relative_to(run)): path for path in (run / "inputs").rglob("*") if path.is_file()}
    for name in ["prelaunch_receipt.txt", "generated_ip.txt", "after_integrity.txt", "run_status.txt",
                 "terminal_receipt.json", "artifact-inventory.sha256", "artifact-summary.json"]:
        selected["run/" + name] = run / name
    for name in ["compile.log", "elaborate.log", "simulate.log", "native30_actual_raw_tuples.txt", "paired_pilot_actual.ci16"]:
        selected["run/simulation/" + name] = simulation / name
    selected["run/generated_actual_fft_wrapper.vhd"] = run / "project/high_rate_bank_native_case.gen/sources_1/ip/starlink_pss_fft512_bfp18_rt_candidate/synth/starlink_pss_fft512_bfp18_rt_candidate.vhd"
    for suffix in [".vivado.log", ".vivado.jou"]:
        selected["launch/" + run.name + suffix] = run.parent / (run.name + suffix)
    selected["repository/" + str(report.relative_to(ROOT))] = report
    selected["repository/tools/" + Path(__file__).name] = Path(__file__).resolve()
    payloads = {}
    for name, path in sorted(selected.items()):
        if path.is_symlink() or path.stat().st_size > 4_000_000:
            raise ValueError("unsafe/unbounded portable member")
        payloads[name] = path.read_bytes()
    if sum(map(len, payloads.values())) > 16_000_000:
        raise ValueError("portable actual proof exceeds16MB")
    receipt = {"result": result, "source_signature": SIGNATURE,
               "files": {name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in payloads.items()},
               "excluded": "generated project executables/libraries/WDB not duplicated; entire original run retained and inventoried"}
    payloads["portable_receipt.json"] = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as archive:
        for name, data in payloads.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            archive.addfile(info, io.BytesIO(data))
    with tarfile.open(output, "r:gz") as archive:
        members = archive.getmembers()
        if {m.name for m in members} != payloads.keys() or any(
            not m.isfile() or m.name.startswith("/") or ".." in Path(m.name).parts for m in members
        ):
            raise ValueError("unsafe/incomplete archive")
        for member in members:
            if archive.extractfile(member).read() != payloads[member.name]:
                raise ValueError("archive readback mismatch")
    for name, path in selected.items():
        if path.read_bytes() != payloads[name]:
            raise ValueError("portable input changed during packaging")
    for name, r in artifacts.items():
        if sha(run / name) != r["sha256"]:
            raise ValueError("original generated run changed during packaging")
    summary = {"archive_sha256": sha(output), "archive_bytes": output.stat().st_size,
               "receipt_files": len(receipt["files"]), "regular_members": len(payloads),
               "raw_run_inventory_files": len(artifacts), "raw_run_bytes": sum(r["bytes"] for r in artifacts.values()),
               "artifact_inventory_sha256": sha(inventory_path), "source_signature": SIGNATURE,
               "case": result["case"], "outcome": result["outcome"]}
    output.with_suffix(".json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--handle", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(package(args.run.absolute(), args.report.absolute(), args.output.absolute(), args.handle), sort_keys=True))

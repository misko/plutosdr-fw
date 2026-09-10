#!/usr/bin/env python3
"""Package the one approved healthy30 actual run; never launches a simulator."""

import argparse
import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = Path("/tmp/starlink-bank-route.I50MDJ/main-high-rate30-bank175-447-v2")
SIM = RUN / "project/high_rate_bank_native_paired.sim/sim_1/behav/xsim"
sys.path.insert(0, str(ROOT))

from tests.starlink_oracle.high_rate_harness import verify_results
from tools.prepare_starlink_high_rate_harness import verify_bundle


def sha(data):
    return hashlib.sha256(data).hexdigest()


def package(output):
    if output.exists() or output.with_suffix(".json").exists():
        raise ValueError("refusing to overwrite actual evidence")
    bundle = verify_bundle(RUN / "inputs")
    result = verify_results(SIM)
    if bundle["source_signature"] != "413f9cd065da934d258750b30075d5e9c75ff16efd9484a51222ca0b3043cb31":
        raise ValueError("wrong actual-run source signature")
    if (RUN / "run_status.txt").read_text().splitlines()[0] != "run_tcl_exit=0 integrity_exit=0":
        raise ValueError("actual run/integrity failure")
    selected = {"run/" + str(path.relative_to(RUN)): path for path in (RUN / "inputs").rglob("*") if path.is_file()}
    for name in ["prelaunch_receipt.txt", "generated_ip.txt", "after_integrity.txt", "run_status.txt",
                 "terminal_receipt.json", "run_summary.md", "artifact-inventory.sha256", "external-launch-artifacts.sha256"]:
        selected["run/" + name] = RUN / name
    for name in ["compile.log", "elaborate.log", "simulate.log", "native30_actual_raw_tuples.txt", "paired_pilot_actual.ci16"]:
        selected["run/simulation/" + name] = SIM / name
    wrapper = RUN / "project/high_rate_bank_native_paired.gen/sources_1/ip/starlink_pss_fft512_bfp18_rt_candidate/synth/starlink_pss_fft512_bfp18_rt_candidate.vhd"
    selected["run/generated_actual_fft_wrapper.vhd"] = wrapper
    for name in ["main-high-rate30-bank175-447-v2.vivado.log", "main-high-rate30-bank175-447-v2.vivado.jou",
                 "main-high-rate30-bank175-447-v1.initialization-failure.json", "main-high-rate30-bank175-447-v2.inventory-verification.log"]:
        selected["launch/" + name] = RUN.parent / name
    for name in ["docs/starlink-high-rate30-actual-447-20260910.md", "tools/package_starlink_high_rate_actual.py"]:
        selected["repository/" + name] = ROOT / name
    payloads = {}
    for name, path in sorted(selected.items()):
        if path.is_symlink() or path.stat().st_size > 4_000_000:
            raise ValueError("unsafe/unbounded portable input")
        payloads[name] = path.read_bytes()
    if sum(map(len, payloads.values())) > 16_000_000:
        raise ValueError("portable actual receipt exceeds16MB")
    receipt = {"result": result, "source_signature": bundle["source_signature"],
               "files": {name: {"bytes": len(data), "sha256": sha(data)} for name, data in payloads.items()},
               "excluded": "generated project libraries/executables/WDB not duplicated; complete636-file original run retained and inventoried"}
    payloads["portable_receipt.json"] = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as archive:
        for name, payload in payloads.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(payload))
    with tarfile.open(output, "r:gz") as archive:
        members = archive.getmembers()
        if {member.name for member in members} != set(payloads) or any(
            not member.isfile() or member.name.startswith("/") or ".." in Path(member.name).parts for member in members
        ):
            raise ValueError("unsafe/incomplete portable actual archive")
        for member in members:
            if archive.extractfile(member).read() != payloads[member.name]:
                raise ValueError("actual archive readback mismatch")
    for name, path in selected.items():
        if path.read_bytes() != payloads[name]:
            raise ValueError("actual evidence changed during packaging")
    summary = {"archive_sha256": sha(output.read_bytes()), "archive_bytes": output.stat().st_size,
               "regular_members": len(payloads), "receipt_files": len(receipt["files"]),
               "source_signature": bundle["source_signature"]}
    output.with_suffix(".json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    print(json.dumps(package(parser.parse_args().output.absolute()), sort_keys=True))

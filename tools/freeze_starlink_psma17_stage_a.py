#!/usr/bin/env python3
"""Absent-only, bounded source/evidence freeze for the PSMA 1.7 Stage A gate.

Copies and hashes artifacts; never executes RTL or changes a golden. The old
cohort producer must first pass independent verification with python -B.
"""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRA = [
    "tools/freeze_starlink_psma17_stage_a.py",
    "tools/generate_starlink_pss_tracker_coefficients.py",
    "docs/starlink-psma17-stage-a-20260910.md",
    "tests/starlink_oracle/psma17_projection.py",
    "tests/starlink_oracle/psma17_stage_a_delta.json",
    "tests/starlink_oracle/test_psma17_contract.py",
    "tests/starlink_oracle/test_psma_boundary_stop.py",
    "tests/starlink_oracle/test_stop_health_integration.py",
    "tests/starlink_oracle/test_health_stop_summary.py",
    "tests/starlink_oracle/test_shared_xfft_integration.py",
    "tests/starlink_oracle/test_ddc.py",
    "tests/starlink_oracle/test_pilot_ddc.py",
    "tests/test_starlink_pss_tracker_coefficients.py",
    "hdl/projects/pluto/system_bd.tcl",
    "hdl/projects/pluto/starlink_pss_build_options.tcl",
    "hdl/library/axi_starlink_pss_acquisition/axi_starlink_pss_acquisition_ip.tcl",
    "hdl/library/axi_starlink_pss_phase_map/starlink_pss_axi_lite.v",
    *[f"hdl/library/axi_starlink_pss_acquisition/tb/{name}" for name in [
        "starlink_pss_iq_to_phase_map_stub.v", "tb_axi_starlink_pss_psma17.sv",
        "tb_axi_starlink_pss_psma17_startup.sv", "tb_axi_starlink_pss_map_stop.sv",
        "tb_axi_starlink_pss_stop_wiring.sv", "tb_axi_starlink_pss_phase_map_sync_rate.sv",
    ]],
    "hdl/library/starlink_pss_acquisition/tb/tb_starlink_pss_health_stop_summary.sv",
    "hdl/library/starlink_pss_acquisition/tb/tb_starlink_pss_acquisition_health.sv",
]


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def freeze(output: Path, evidence: Path, cohort: Path):
    if output.exists() or output.is_symlink():
        raise FileExistsError("refusing to replace Stage A evidence")
    delta = json.loads((ROOT / "tests/starlink_oracle/psma17_stage_a_delta.json").read_bytes())
    original = json.loads((cohort / "cohort.json").read_bytes())
    pending = {}

    def admit(target, source, expected=None):
        if source.is_symlink() or not source.is_file() or source.stat().st_size > 8_000_000:
            raise ValueError(f"unsafe or oversized source: {source}")
        payload = source.read_bytes()
        if expected is not None and sha(payload) != expected:
            raise ValueError(f"changed frozen source: {source}")
        if target in pending:
            raise ValueError(f"duplicate inventory: {target}")
        pending[target] = (source, sha(payload), len(payload))

    for relative, old_hash in original["source_sha256"].items():
        new = delta["files"].get(relative.removeprefix("hdl/"))
        expected = new["after_sha256"] if new else old_hash
        admit(f"source/{relative}", ROOT / relative, expected)
        admit(f"cohort/source_snapshot/{relative}", cohort / "source_snapshot" / relative, old_hash)
    for relative in EXTRA:
        if f"source/{relative}" not in pending:
            admit(f"source/{relative}", ROOT / relative)
    for relative, properties in original["files"].items():
        admit(f"cohort/{relative}", cohort / relative, properties["sha256"])
    admit("cohort/cohort.json", cohort / "cohort.json",
          "ba3046d56a6eb1cf2792070cf63f8d7ffb44958f0ef9f4999907b2b2a49bdb4d")
    for attempt in sorted((ROOT / "build").glob("psma17-stage-a-*")):
        if not attempt.is_dir() or attempt.is_symlink():
            continue
        for path in sorted(attempt.rglob("*")):
            # The collector's own redirected stdout is still open; exclude
            # it rather than freeze an empty, subsequently changing receipt.
            if path.is_file() and not path.is_symlink() and path.name != "freeze.log" and (
                path.suffix in {".log", ".xml"} or
                (attempt == evidence and path.name == "psma-public-trace.txt") or
                "source_receipt" in path.parts
            ):
                admit("evidence/" + str(path.relative_to(ROOT / "build")), path)
    if sum(size for _, _, size in pending.values()) > 32_000_000:
        raise ValueError("bounded archive inventory exceeds 32 MB")
    output.mkdir()
    for target, (source, digest, _) in sorted(pending.items()):
        destination = output / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        if sha(destination.read_bytes()) != digest:
            raise RuntimeError("source changed during evidence copy")
    receipt = {
        "scope": "PSMA1.7 Stage A; no actual FFT/native/PIL1/physical/RF execution",
        "source_signature": sha(json.dumps(
            {name: digest for name, (_, digest, _) in sorted(pending.items()) if name.startswith("source/")},
            sort_keys=True, separators=(",", ":")).encode()),
        "files": {name: {"sha256": digest, "bytes": size}
                  for name, (_, digest, size) in sorted(pending.items())},
    }
    (output / "receipt.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    return {"files": len(pending), "source_signature": receipt["source_signature"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--cohort", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(freeze(args.output.absolute(), args.evidence.absolute(), args.cohort.absolute()),
                     sort_keys=True))

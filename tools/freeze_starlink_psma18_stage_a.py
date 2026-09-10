#!/usr/bin/env python3
"""Bounded source receipts/portable proof only; never launches a simulator."""

import argparse
import hashlib
import io
import json
import platform
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.freeze_starlink_psma17_stage_a import EXTRA

COHORT = ROOT / "build/high-rate60-offline-v2/cohort"
TESTS = [
    "tests/starlink_oracle/test_psma18_contract.py", "tests/starlink_oracle/test_psma17_contract.py",
    "tests/starlink_oracle/test_psma_boundary_stop.py", "tests/starlink_oracle/test_stop_health_integration.py",
    "tests/starlink_oracle/test_health_stop_summary.py", "tests/starlink_oracle/test_shared_xfft_integration.py",
    "tests/test_starlink_high_rate_paired.py", "tests/starlink_oracle/test_ddc.py",
    "tests/starlink_oracle/test_pilot_ddc.py", "tests/test_starlink_pss_tracker_coefficients.py",
    "tests/test_starlink_high_rate60_paired.py", "tests/test_starlink_high_rate60_support.py",
]
ADDITIVE = [
    "tools/freeze_starlink_psma18_stage_a.py", "tests/starlink_oracle/psma18_contract.py",
    "tests/starlink_oracle/psma18_projection.py", "tests/starlink_oracle/psma18_stage_a_delta.json",
    "hdl/library/axi_starlink_pss_acquisition/tb/tb_axi_starlink_pss_psma18_counters.sv",
]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def read(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8_000_000:
        raise ValueError(f"unsafe or unbounded source: {path}")
    return path.read_bytes()


def executable_digest(path):
    # Executables have a separate bounded policy, not the 8MB text-source
    # limit. Stream the installed 21.7MB Python binary without archiving it.
    resolved = path.resolve(strict=True)
    if not resolved.is_file() or resolved.stat().st_size > 64_000_000:
        raise ValueError("unbounded executable identity")
    with resolved.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def source_receipt():
    cohort = json.loads(read(COHORT / "cohort.json"))
    delta = json.loads(read(ROOT / "tests/starlink_oracle/psma18_stage_a_delta.json"))
    for name, expected in cohort["source_sha256"].items():
        changed = delta["files"].get(name.removeprefix("hdl/"))
        if digest(read(ROOT / name)) != (changed["after_sha256"] if changed else expected):
            raise ValueError(f"unreviewed original76 source delta: {name}")
    names = set(cohort["source_sha256"]) | set(EXTRA) | set(TESTS) | set(ADDITIVE)
    names.update(str(p.relative_to(ROOT)) for p in [ROOT / "pytest.ini", ROOT / "pyproject.toml",
                 ROOT / "conftest.py", ROOT / "tests/conftest.py"] if p.is_file())
    return {name: digest(read(ROOT / name)) for name in sorted(names)}


def snapshot(output):
    if output.exists() or output.is_symlink():
        raise FileExistsError("source receipt directory must be absent")
    before = source_receipt()
    output.mkdir()
    (output / "sources-before.json").write_bytes(encoded(before))
    for name, expected in before.items():
        data = read(ROOT / name)
        if digest(data) != expected:
            raise ValueError("source changed while freezing")
        target = output / "source_snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    environment = {"host": platform.node(), "machine": platform.machine(), "python": sys.version,
                   "python_executable": sys.executable,
                   "python_resolved": str(Path(sys.executable).resolve()),
                   "python_sha256": executable_digest(Path(sys.executable)),
                   "test_files": TESTS, "scope": "offline initial-admission/public-contract only"}
    for executable in ["iverilog", "vvp"]:
        result = subprocess.run([executable, "-V"], capture_output=True, text=True, check=False)
        environment[executable] = {"returncode": result.returncode, "output": result.stdout + result.stderr}
    (output / "environment.json").write_bytes(encoded(environment))
    return {"sources": len(before), "source_signature": digest(encoded(before))}


def after(output):
    before = json.loads(read(output / "sources-before.json"))
    current = source_receipt()
    if before != current:
        raise ValueError("source closure changed during tests")
    for name, expected in before.items():
        if digest(read(output / "source_snapshot" / name)) != expected:
            raise ValueError("source snapshot changed during tests")
    target = output / "sources-after.json"
    if target.exists():
        raise FileExistsError("after receipt already exists")
    target.write_bytes(encoded(current))
    return {"sources": len(current), "source_signature": digest(encoded(current)), "pre_post_equal": True}


def package(output, final):
    if output.exists() or output.with_suffix(".json").exists():
        raise FileExistsError("portable proof must be absent")
    before = json.loads(read(final / "sources-before.json"))
    if before != json.loads(read(final / "sources-after.json")) or before != source_receipt():
        raise ValueError("final source pre/post/current mismatch")
    selected = {p for p in final.rglob("*") if p.is_file()}
    selected.update(p for p in COHORT.rglob("*") if p.is_file())
    selected.add(ROOT / "docs/starlink-psma18-stage-a60-20260910.md")
    selected.add(ROOT / "build/psma18-collection-attempts.json")
    selected.update(p for p in (ROOT / "build/psma18-stage-a-source-freeze-v1").rglob("*") if p.is_file())
    selected.update(p for p in (ROOT / "build/psma18-stage-a-source-freeze-v2").rglob("*") if p.is_file())
    selected.update(p for p in (ROOT / "build/psma18-stage-a-source-freeze-v3").rglob("*") if p.is_file())
    # Raw test directories stay intact. Portable proof contains all logs,
    # XML and simulated source specimens, not duplicate numerical mutants
    # or compiler executables; unchanged original69/cohort76 are included.
    for attempt in [ROOT / "build/psma18-stage-a-v1", ROOT / "build/psma18-stage-a-v2",
                    ROOT / "build/psma18-stage-a-v3", ROOT / "build/psma18-stage-a-v4",
                    ROOT / "build/psma18-stage-a-v5"]:
        for path in attempt.rglob("*"):
            if path.is_file() and (path.suffix in {".log", ".xml"} or
                (path.name == "psma-public-trace.txt" and attempt.name == "psma18-stage-a-v5") or
                (path.suffix in {".v", ".sv", ".vh"} and any(path.parent.glob("*.vvp")))):
                selected.add(path)
    payloads = {str(path.relative_to(ROOT)): read(path) for path in sorted(selected)}
    # Earlier passing trace copies alone add20MB. Keep them intact in their
    # original raw runs and include exact file receipts instead of duplicating
    # them in this archive. All compile/simulation logs and final traces stay.
    earlier_traces = [p for i in range(1, 5) for p in
                      (ROOT / f"build/psma18-stage-a-v{i}").rglob("psma-public-trace.txt")]
    payloads["earlier-public-traces-retained.json"] = encoded({str(p.relative_to(ROOT)):
        {"bytes": p.stat().st_size, "sha256": digest(read(p))} for p in sorted(earlier_traces)})
    # Preserve every historical complete body used by the inverse/trace tests.
    paths = json.loads(read(ROOT / "tests/starlink_oracle/psma18_stage_a_delta.json"))["files"]
    for commit in ["706ffb7b5b842409d8a8714c056203d8b5555034", "b49553c16319f59ad8d7b44fd24c494f96eba142",
                   "653a3205bc7bd158a7267a9288beba63aebe12cf"]:
        for path in paths:
            payloads[f"historical/{commit}/{path}"] = subprocess.check_output(
                ["git", "-C", str(ROOT / "hdl"), "show", f"{commit}:{path}"])
    if sum(map(len, payloads.values())) > 48_000_000 or len(payloads) > 6000:
        raise ValueError("portable proof exceeds bounded48MB/6000-file inventory")
    receipt = {"schema": "psma18-stage-a60-portable-v1", "source_signature": digest(encoded(before)),
               "source_count": len(before), "tests": TESTS,
               "files": {name: {"bytes": len(data), "sha256": digest(data)} for name, data in sorted(payloads.items())}}
    payloads["receipt.json"] = encoded(receipt)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as archive:
        for name, data in sorted(payloads.items()):
            member = tarfile.TarInfo(name)
            member.size = len(data)
            member.mode = 0o644
            archive.addfile(member, io.BytesIO(data))
    # Verify every stored member and reject links, duplicate or unsafe names.
    with tarfile.open(output, "r:gz") as archive:
        members = archive.getmembers()
        if len(members) != len(payloads) or {m.name for m in members} != payloads.keys():
            raise ValueError("portable member inventory mismatch")
        for member in members:
            if not member.isfile() or Path(member.name).is_absolute() or ".." in Path(member.name).parts or \
                    archive.extractfile(member).read() != payloads[member.name]:
                raise ValueError("unsafe or corrupted portable member")
    receipt["archive_sha256"] = digest(read(output))
    receipt["archive_bytes"] = output.stat().st_size
    output.with_suffix(".json").write_bytes(encoded(receipt))
    return {"files": len(payloads), "source_count": len(before), "source_signature": receipt["source_signature"],
            "archive_sha256": receipt["archive_sha256"], "archive_bytes": receipt["archive_bytes"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["snapshot", "after", "package"])
    parser.add_argument("output", type=Path)
    parser.add_argument("--final", type=Path)
    args = parser.parse_args()
    result = package(args.output.absolute(), args.final.absolute()) if args.action == "package" else \
        (snapshot if args.action == "snapshot" else after)(args.output.absolute())
    print(json.dumps(result, sort_keys=True))

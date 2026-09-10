"""Closed, immutable preparation and one-shot staging; no vendor invocation."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

from . import retained_output_actual as a
from .retained_output_actual_result import verify_result

EXTRAS = (
    "tests/starlink_oracle/retained_output_actual.py",
    "tests/starlink_oracle/retained_output_actual_result.py",
    "tests/starlink_oracle/retained_output_actual_bundle.py",
    "tests/starlink_oracle/retained_output_actual_recipe.json",
    "tests/starlink_oracle/retained_output_actual_abi.json",
    "tests/starlink_oracle/retained_completion_declaration.py",
    "tests/test_starlink_retained_completion_declaration.py",
    "tests/test_starlink_retained_output_actual.py",
    "tests/test_starlink_retained_output_actual_bundle.py",
    "tools/prepare_starlink_retained_output_actual.py",
    "hdl/library/starlink_pss_acquisition/retained_output_actual/context.svh",
    "hdl/library/starlink_pss_acquisition/retained_output_actual/witness.svh",
    "hdl/library/starlink_pss_acquisition/retained_output_actual/simulate_retained_output_actual.tcl",
    "hdl/library/starlink_pss_acquisition/retained_output_actual/run_retained_output_actual.tcl",
)
RUNNER = EXTRAS[-2]


def encoded(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def receipt(path: Path) -> dict:
    return {"sha256": a.sha(path), "bytes": path.stat().st_size}


def safe(path: Path) -> Path:
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("absolute lexical path without parent traversal required")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError(f"symlink path prohibited: {part}")
    return path


def source_names() -> tuple[str, ...]:
    old = [line.split(maxsplit=1)[1].removeprefix("source/")
           for line in (a.REF / "frozen46.sha256").read_text().splitlines()]
    refs = [str((a.REF / name).relative_to(a.ROOT)) for name in (*a.REFERENCE_PINS, "frozen46.sha256")]
    result = tuple(sorted(old + refs + list(EXTRAS)))
    if len(set(result)) != len(result) or len(old) != 46:
        raise ValueError("closed source-list duplicate/original omission")
    return result


def live_sources(root: Path) -> dict:
    return {name: receipt(safe(root / name)) for name in source_names()}


def _files(root: Path) -> dict:
    result = {}
    for folder, dirs, names in os.walk(root, followlinks=False):
        for name in dirs + names:
            p = Path(folder) / name
            if p.is_symlink():
                raise ValueError("bundle symlink")
            if p.is_file() and p != root / "manifest.json":
                result[p.relative_to(root).as_posix()] = receipt(p)
    return dict(sorted(result.items()))


def prepare(output: Path) -> dict:
    a.verify_originals()
    output = safe(output)
    if output.exists():
        raise ValueError("refusing preparation overwrite")
    before = live_sources(a.ROOT)
    output.mkdir(parents=True)
    for name in before:
        target = output / "source_snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(a.ROOT / name, target)
    (output / "bench.sv").write_text(a.actual_bench())
    compiled = ["source_snapshot/" + p.relative_to(a.ROOT).as_posix() for p in a.compiled_sources()]
    vectors = ["source_snapshot/" + p.relative_to(a.ROOT).as_posix() for p in sorted(a.original.BASELINE.glob("*.mem"))]
    profile = "set compiled_names {" + " ".join(compiled) + " bench.sv}\nset vector_names {" + " ".join(vectors) + "}\n"
    (output / "profile.tcl").write_text(profile)
    (output / "environment.json").write_bytes(encoded({"python_version": sys.version, "python_executable": sys.executable,
                                                       "qualification": "preparation only; no vendor invocation"}))
    after = live_sources(a.ROOT)
    if before != after:
        raise ValueError("source changed during preparation")
    manifest = {"kind": "retained-output-actual-v1", "source_root": str(a.ROOT),
                "sources": before, "source_signature": hashlib.sha256(encoded(before)).hexdigest(),
                "files": _files(output), "compiled": compiled, "vectors": vectors,
                "source_before_after_equal": True, "actual_execution": False}
    (output / "manifest.json").write_bytes(encoded(manifest))
    return verify(output, a.sha(output / "manifest.json"), live=True)


def verify(bundle: Path, expected: str, *, live=False) -> dict:
    a.verify_originals()
    bundle = safe(bundle)
    manifest_file = bundle / "manifest.json"
    if a.sha(manifest_file) != expected:
        raise ValueError("external manifest digest")
    raw = manifest_file.read_bytes()
    m = json.loads(raw)
    if encoded(m) != raw or m.get("kind") != "retained-output-actual-v1" or m.get("actual_execution") is not False or m.get("source_before_after_equal") is not True:
        raise ValueError("manifest canonical types/kind")
    if set(m) != {"kind", "source_root", "sources", "source_signature", "files", "compiled", "vectors", "source_before_after_equal", "actual_execution"}:
        raise ValueError("manifest fields")
    expected_files = {"source_snapshot/" + name for name in source_names()} | {"bench.sv", "profile.tcl", "environment.json"}
    if set(m["files"]) != expected_files or encoded(_files(bundle)) != encoded(m["files"]):
        raise ValueError("complete bundle inventory")
    if sorted(m["sources"]) != list(source_names()) or hashlib.sha256(encoded(m["sources"])).hexdigest() != m["source_signature"]:
        raise ValueError("closed source signature")
    for name, value in m["sources"].items():
        if encoded(m["files"].get("source_snapshot/" + name)) != encoded(value):
            raise ValueError("source signature not joined to actual snapshot")
    if encoded(live_sources(a.ROOT)) != encoded(m["sources"]):
        raise ValueError("executing frozen source does not match manifest sources")
    expected_compiled = ["source_snapshot/" + p.relative_to(a.ROOT).as_posix() for p in a.compiled_sources()]
    expected_vectors = ["source_snapshot/" + p.relative_to(a.ROOT).as_posix() for p in sorted(a.original.BASELINE.glob("*.mem"))]
    if m["compiled"] != expected_compiled or m["vectors"] != expected_vectors or any("scripted_fft" in p for p in m["compiled"]):
        raise ValueError("actual-only exact compiled profile")
    a.inverse_bench((bundle / "bench.sv").read_text())
    profile = "set compiled_names {" + " ".join(expected_compiled) + " bench.sv}\nset vector_names {" + " ".join(expected_vectors) + "}\n"
    if (bundle / "profile.tcl").read_text() != profile:
        raise ValueError("exact source profile")
    if live and live_sources(safe(Path(m["source_root"]))) != m["sources"]:
        raise ValueError("live source changed")
    return {"manifest_sha256": expected, "source_signature": m["source_signature"], "sources": len(m["sources"]),
            "files": len(m["files"]), "live_checked": live, "actual_execution": False}


def stage(bundle: Path, output: Path, expected: str, *, authorize=False) -> dict:
    if not authorize:
        raise ValueError("explicit one-shot actual staging flag required")
    before = verify(bundle, expected, live=True)
    output = safe(output)
    if output.exists():
        raise ValueError("refusing actual output restart/overwrite")
    output.mkdir(parents=True)
    shutil.copytree(bundle, output / "inputs")
    copied = verify(output / "inputs", expected, live=True)
    (output / "before.json").write_bytes(encoded({"original": before, "copied": copied}))
    return before


def after(bundle: Path, output: Path, expected: str) -> dict:
    result = {"original": verify(bundle, expected, live=True), "copied": verify(output / "inputs", expected, live=True)}
    path = safe(output) / "after.json"
    if path.exists():
        raise ValueError("refusing after-receipt overwrite")
    path.write_bytes(encoded(result))
    return result


def results(output: Path, expected: str) -> dict:
    verify(output / "inputs", expected, live=True)
    simulation = output / "project/retained_output_actual.sim/sim_1/behav/xsim"
    return verify_result(simulation / "simulate.log", simulation / "actual_words.csv", kind="ACTUAL_VENDOR_FFT")

#!/usr/bin/env python3
"""Freeze two additive30 cases over the unchanged reviewed447 input closure."""

import argparse
import ast
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.starlink_oracle.high_rate_case_result import verify_late, verify_result
from tests.starlink_oracle.high_rate_cases import CASES, prepare_case, verify_case
from tests.starlink_oracle.high_rate_harness import encoded, sha
from tools.prepare_starlink_high_rate_harness import inventory, verify_bundle

BASE_SHA = "2d410bc8a7984425751a527725e8f43c8406596b23f610e904199d1524863da5"
BASE_SIGNATURE = "413f9cd065da934d258750b30075d5e9c75ff16efd9484a51222ca0b3043cb31"
ACQ = "hdl/library/starlink_pss_acquisition/"
ADDITIVE = [
    "tests/starlink_oracle/high_rate_late_contract.py",
    "tests/starlink_oracle/high_rate_cases.py", "tests/starlink_oracle/high_rate_case_result.py",
    "tests/test_starlink_high_rate_cases.py", "tests/test_starlink_high_rate_case_result.py",
    "tests/test_starlink_high_rate_case_bundle.py", "tools/prepare_starlink_high_rate_cases.py",
    ACQ + "tb/bank_native30_late_logic.svh", ACQ + "simulate_high_rate_bank_native_cases.tcl",
]


def python_dependencies(source_root):
    """Static local import closure, including imports nested inside tests.

    Standard-library/third-party imports are host dependencies, not silently
    sourced from another worktree. All tests/tools local imports must resolve
    within the frozen closure; record exact edges, not just a file count.
    """
    pending = [name for name in ADDITIVE if name.endswith(".py")]
    edges = {}
    while pending:
        name = pending.pop()
        if name in edges:
            continue
        imports = set()
        for node in ast.walk(ast.parse((source_root / name).read_text())):
            modules = []
            if isinstance(node, ast.Import):
                modules = [entry.name for entry in node.names]
            elif isinstance(node, ast.ImportFrom):
                parent = name.removesuffix(".py").split("/")[:-1]
                modules = ([".".join(parent[:len(parent) - node.level + 1] + [node.module or ""]).rstrip(".")]
                           if node.level else [node.module or ""])
            for module in modules:
                if module.split(".")[0] not in {"tests", "tools"}:
                    continue
                dependency = module.replace(".", "/") + ".py"
                if not (source_root / dependency).is_file():
                    dependency = module.replace(".", "/") + "/__init__.py"
                if not (source_root / dependency).is_file():
                    raise ValueError(f"local Python dependency absent from frozen closure: {name}: {module}")
                imports.add(dependency)
        edges[name] = sorted(imports)
        pending.extend(imports)
    return dict(sorted(edges.items()))


def check_base(base):
    if sha((base / "bundle.json").read_bytes()) != BASE_SHA:
        raise ValueError("original447 bundle identity changed")
    result = verify_bundle(base)
    if result["source_signature"] != BASE_SIGNATURE or len(result["source_sha256"]) != 95:
        raise ValueError("original447 source closure changed")
    return result


def evidence_inventory(directory):
    # Omit only compiled native-only executable; retain code, vectors, logs,
    # contract-before and before/after receipts. No symlinks or generated IP.
    return {name: digest for name, digest in inventory(directory).items() if not name.endswith(".vvp")}


def freeze(case, base, output, native_probe):
    if case not in CASES:
        raise ValueError("only healthy343 or late447 is admitted")
    if output.exists():
        raise ValueError("refusing to overwrite case bundle")
    original = check_base(base)
    probe_before = evidence_inventory(native_probe)
    log = (native_probe / "simulation.log").read_text()
    if any(word in log for word in ["FAIL", "ERROR", "FATAL"]):
        raise ValueError("successful native-only late probe required; rejected attempts remain separate")
    verify_late(native_probe, log, native_only=True)
    sources = {name: ROOT / name for name in sorted(set(original["source_sha256"]) | set(ADDITIVE))}
    source_before = {name: sha(path.read_bytes()) for name, path in sources.items()}
    if any(source_before[name] != digest for name, digest in original["source_sha256"].items()):
        raise ValueError("live original447 source changed; no runtime/old helper/golden edits admitted")
    output.mkdir(parents=True)
    shutil.copytree(base, output / "base")
    prepare_case(case, output / "generated", output / "base")
    for name, path in sources.items():
        target = output / "source_snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    for name in probe_before:
        target = output / "native_only_late_evidence" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(native_probe / name, target)
    hashes = inventory(output)
    if source_before != {name: sha(path.read_bytes()) for name, path in sources.items()} or probe_before != evidence_inventory(native_probe):
        raise ValueError("source/evidence changed during freeze")
    if any(hashes["source_snapshot/" + name] != digest for name, digest in source_before.items()):
        raise ValueError("copied source mismatch")
    receipt = {"case": case, "profile": CASES[case]["profile"], "contract": CASES[case].copy(),
               "base_bundle_sha256": BASE_SHA, "base_source_signature": BASE_SIGNATURE,
               "source_sha256": source_before, "source_signature": sha(encoded(source_before)),
               "native_probe_sha256": probe_before, "files": hashes, "actual_fft_run": False,
               "python_dependency_edges": python_dependencies(output / "source_snapshot"),
               "scope": "offline prepared only; separately authorized actual launch required; no RF/physical/causal claim"}
    (output / "bundle.json").write_bytes(encoded(receipt))
    verify(output)
    return receipt


def verify(output):
    receipt = json.loads((output / "bundle.json").read_bytes())
    case = receipt["case"]
    if case not in CASES or receipt["profile"] != CASES[case]["profile"] or receipt["contract"] != CASES[case]:
        raise ValueError("unreviewed case/rate/geometry contract")
    actual = inventory(output)
    actual.pop("bundle.json")
    if actual != receipt["files"] or receipt["actual_fft_run"] is not False:
        raise ValueError("case bundle inventory changed")
    original = check_base(output / "base")
    if receipt["base_bundle_sha256"] != BASE_SHA or receipt["base_source_signature"] != BASE_SIGNATURE:
        raise ValueError("original447 identity disconnected")
    source_hashes = receipt["source_sha256"]
    if set(source_hashes) != set(original["source_sha256"]) | set(ADDITIVE):
        raise ValueError("additive source-list closure changed")
    if sha(encoded(source_hashes)) != receipt["source_signature"] or any(
        actual.get("source_snapshot/" + name) != digest for name, digest in source_hashes.items()
    ):
        raise ValueError("source signature disconnected from exact files")
    if any(source_hashes[name] != digest for name, digest in original["source_sha256"].items()):
        raise ValueError("original447 source or runtime changed")
    dependencies = python_dependencies(output / "source_snapshot")
    if dependencies != receipt["python_dependency_edges"] or not set(dependencies) <= set(source_hashes):
        raise ValueError("Python dependency graph disconnected from signed source closure")
    verify_case(case, output / "generated", output / "base")
    probe = output / "native_only_late_evidence"
    if evidence_inventory(probe) != receipt["native_probe_sha256"]:
        raise ValueError("native-only probe inventory changed")
    verify_late(probe, (probe / "simulation.log").read_text(), native_only=True)
    return receipt


def verify_simulation(output, simulation):
    receipt = verify(output)
    # Independent expected outputs must be the original reviewed files, not
    # a self-consistent replacement next to a damaged actual output.
    for name in ["native_all_raw_tuples.json", "native_expected_packet.mem", "pilot_expected_ci16.mem",
                 "pilot_expected_index_u64.mem", "pilot_expected.ci16"]:
        if (simulation / name).is_symlink() or (simulation / name).read_bytes() != (output / "base/vectors" / name).read_bytes():
            raise ValueError("simulation expected oracle differs from frozen base: " + name)
    return verify_result(receipt["case"], simulation)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["freeze", "verify", "result"])
    parser.add_argument("output", type=Path)
    parser.add_argument("--case", choices=list(CASES))
    parser.add_argument("--base", type=Path)
    parser.add_argument("--native-probe", type=Path)
    parser.add_argument("--simulation", type=Path)
    args = parser.parse_args()
    if args.mode == "freeze":
        if args.case is None or args.base is None or args.native_probe is None:
            parser.error("freeze requires --case, --base and --native-probe")
        result = freeze(args.case, args.base.absolute(), args.output.absolute(), args.native_probe.absolute())
    else:
        result = verify(args.output.absolute())
        if args.mode == "result":
            if args.simulation is None:
                parser.error("result requires --simulation; case comes only from frozen bundle")
            result = verify_simulation(args.output.absolute(), args.simulation.absolute())
    print(json.dumps({key: result[key] for key in ["case", "profile", "source_signature", "result", "outcome"] if key in result}, sort_keys=True))

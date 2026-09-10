"""Freeze/compile/verify the additive native60-only probe. No default service run.

The69 numbers are copied byte-for-byte, never regenerated here. Run admission
requires the separately reviewed bundle SHA and explicit native-service consent.
Compile-only and synthetic parser tests are not service or clock evidence.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .native60_budget_recipe import recipe
from .native60_readback_contract import contract as readback_contract
from .native60_readback_contract import limits as readback_limits

ROOT = Path(__file__).resolve().parents[2]
COHORT = ROOT / "build/high-rate60-offline-v2/cohort"
TB = "hdl/library/starlink_pss_acquisition/tb/"
TOP = TB + "tb_starlink_native60_budget.sv"
CHECKS = TB + "native60_budget_checks.svh"
AXI = TB + "high_rate_paired_axi.svh"
ADDITIVE = [TOP, CHECKS, "tests/starlink_oracle/native60_budget_recipe.py",
            "tests/starlink_oracle/native60_budget.py", "tests/test_starlink_native60_budget.py",
            "tools/prepare_starlink_native60_budget.py",
            "docs/starlink-native60-service-recipe-before-evaluation-20260910.md"]
ADDITIVE += [TB + "native60_readback_checks.svh", "tests/starlink_oracle/native60_readback_contract.py",
             "tests/test_starlink_native60_readback.py", "docs/starlink-native60-readback-correction-20260910.md"]
NATIVE_SOURCES = [
    *["hdl/library/starlink_pss_raw_correlator/" + name + ".v" for name in [
        "starlink_pss_async_fifo", "starlink_sat_add48", "starlink_pss_candidate_scheduler",
        "starlink_pss_capture_bridge", "starlink_pss_sliding_correlator", "starlink_pss_tracking_core",
        "starlink_pss_exact_reducer", "starlink_pss_exact_track_reducer", "starlink_pss_result_store",
        "starlink_pss_reduced_tracking_core"]],
    "hdl/library/common/ad_mem.v", "hdl/library/common/up_axi.v",
    "hdl/library/axi_starlink_pss_tracker/axi_starlink_pss_tracker.v",
    "hdl/library/axi_starlink_pss_tracker/starlink_pss_injection_mux.v",
]
# The rest of the compiled native runtime is pinned by the immutable cohort.
EXTRA_IMMUTABLE = {
    "hdl/library/common/ad_mem.v": "472d518b7f3d7b77a86dc8826169c910a48098f14f78eb1ef78c620fe518e9c4",
    "hdl/library/common/up_axi.v": "161efc9d4cb6f0358c1614cf2b6307b14524b399409b0b8c3a953ac0030ce409",
    "hdl/library/axi_starlink_pss_tracker/starlink_pss_injection_mux.v": "f9b77edd045854c65ca7a2f2cadc9a7f677a7a0365699d1d23c58f43f17cfc30",
    AXI: "5fc5e08a1c80a908fa40e9f8e3982d77f42dc2a82eefa24bdb4f33a61c427548",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def inventory(directory):
    result = {}
    for path in sorted(directory.rglob("*")):
        require(not path.is_symlink(), f"symlink forbidden: {path}")
        if path.is_file():
            result[path.relative_to(directory).as_posix()] = sha(path.read_bytes())
    return result


def budget(value=None):
    r = recipe() if value is None else value
    require(encoded(r) == encoded(recipe()), "unadmitted native60 clock/source/ABI/budget recipe")
    derived = r["capture_transfer_cycles"] + r["sample_energy_cycles"] + 257*r["per_raw_lag_cycles"] + 128
    require(derived == r["engine_derived_cycles"] == 78360, "state-chain arithmetic")
    post = 84000 + 140*24 + 32 + 24
    require(derived <= 84000 and post == 87416 and post <= r["post_capture_limit_cycles"], "complete post-capture arithmetic")
    require(r["native_capture_half_open"][0] - r["command_handshake_closed"][1] - 1 == 1535 and
            r["native_capture_half_open"][0] - r["command_handshake_closed"][0] - 1 == 1695, "lead coordinates")
    return {"recipe": r, "derived_engine_cycles": derived, "derived_post_capture_cycles": post,
            "raw_after_capture": 10858, "raw_after_capture_engine_cycles_floor": 10858*5//3,
            "finite_source_covers_full_service_bound": False,
            "full_raw_drain_required_separately_from_publication": True}


def check_cohort(directory):
    payload = (directory / "cohort.json").read_bytes()
    require(sha(payload) == recipe()["cohort_sha256"], "immutable69 cohort manifest changed")
    result = json.loads(payload)
    require(len(result["files"]) == 69 and len(result["source_sha256"]) == 76, "cohort closure count")
    require(sha(encoded(result["source_sha256"])) == recipe()["cohort_source_signature"], "cohort source signature")
    for name, info in result["files"].items():
        require(Path(name).name == name, "nonlocal numerical name")
        require(sha((directory / name).read_bytes()) == info["sha256"], f"immutable numerical changed: {name}")
    return result


def python_dependencies(source_root):
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
                modules = ([".".join(parent[:len(parent)-node.level+1] + [node.module or ""]).rstrip(".")]
                           if node.level else [node.module or ""])
            for module in modules:
                if module.split(".")[0] not in {"tests", "tools"}:
                    continue
                # Package initializers execute even for an explicit submodule.
                pieces = module.split(".")
                for length in range(1, len(pieces)):
                    init = "/".join(pieces[:length]) + "/__init__.py"
                    if (source_root / init).is_file():
                        imports.add(init)
                dependency = module.replace(".", "/") + ".py"
                if not (source_root / dependency).is_file():
                    dependency = module.replace(".", "/") + "/__init__.py"
                require((source_root / dependency).is_file(), f"missing local import: {name}: {module}")
                imports.add(dependency)
        edges[name] = sorted(imports)
        pending.extend(imports)
    return dict(sorted(edges.items()))


def check_bench(source_root):
    top, checks = [(source_root / name).read_text() for name in [TOP, CHECKS]]
    for token in ["reg clk = 0, sample_clk = 0", "always #5 clk = !clk;",
                  "#2.1; forever #(500.0/60)", "close_time(first_edge, 10.433333)",
                  "close_time(first_fall, 18.766666)", "close_time(observed_half, 8.333333)",
                  "close_time(observed_period, 16.666666)", "cycles >= 160000", "SOURCE_COUNT = 16423",
                  "repeat (256)", "wait(native_drain_cycle >= 0)"]:
        require(token in top, f"native60 source/clock/lifetime contract absent: {token}")
    for token in [".RATE_MSPS(60)", ".ENABLE_INJECTION(0)", ".USE_DSP_REDUCER(1)",
                  "8'h0c, 32'h0f8c1108", "48'd1073758594", "native_raw_lag[native_raw_count][8:0]",
                  "{{23{native_raw_lag[n][8]}}, native_raw_lag[n][8:0]}",
                  "native_raw_saturation[n][11:9] !== 3'b0", "raw_result_valid === 1'b0",
                  "descriptor_read_valid === 1'b0", "native.result_overrun_count} !== 0",
                  "native.active_coefficient_valid !== 1'b1", "cycles-native_capture_end_cycle > 84000",
                  "cycles-native_capture_end_cycle > 88000", "cycles - native_trigger_cycle > 256",
                  "64'd34359738560", "64'd34359738720", "native_raw_count == 257",
                  "repeat (32)", "repeat (24)", "native_raw_count < 249", "native_hold_cycles > 16",
                  "native_raw_payload !== native_held_payload", "unknown control-domain raw/engine protocol flag",
                  "unknown sample-domain command/capture protocol flag"]:
        require(token in checks, f"native60 ABI/tuple/budget contract absent: {token}")
    code = re.sub(r"//[^\n]*", "", top + checks)
    require(checks.count("}) === 1'bx)") == 3, "configured protocol flags must reject X/Z")
    require(not re.search(r"\b(force|defparam)\b", code), "hierarchy forcing/override forbidden")
    require(not re.search(r"\bnative\.[\w.]+\s*(?:<=|=(?!=))", code), "hierarchy writes forbidden")
    require("#7" not in code and "EARLY_OFF" not in code and "$stop" not in code, "alternate clock/source/terminal")
    require('`include "native60_readback_checks.svh"' in top and "check_native_snapshot(current_index);" in checks,
            "independent low-read witness absent")


def prepare(output, cohort=COHORT, source_root=ROOT):
    require(not output.exists(), "refusing to overwrite native60 bundle")
    original = check_cohort(cohort)
    names = sorted(set(original["source_sha256"]) | set(EXTRA_IMMUTABLE) | set(ADDITIVE))
    before = {name: sha((source_root / name).read_bytes()) for name in names}
    for name, expected in (original["source_sha256"] | EXTRA_IMMUTABLE).items():
        require(before[name] == expected, f"immutable runtime/old source changed: {name}")
    check_bench(source_root)
    output.mkdir(parents=True)
    for name in ["cohort.json", *original["files"]]:
        shutil.copyfile(cohort / name, output / name)
    for name in names:
        target = output / "source_snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_root / name, target)
    (output / "recipe.json").write_bytes(encoded(budget()))
    after = {name: sha((source_root / name).read_bytes()) for name in names}
    require(before == after, "source changed during preparation")
    check_cohort(cohort)
    result = {"schema": "native60-service-prelaunch-v1", "budget": budget(),
              "readback_contract": readback_contract(),
              "source_sha256": before, "source_signature": sha(encoded(before)),
              "python_import_edges": python_dependencies(output / "source_snapshot"),
              "files": inventory(output), "service_measured": False}
    (output / "bundle.json").write_bytes(encoded(result))
    verify(output)
    return result


def verify(directory, expected_sha=None):
    payload = (directory / "bundle.json").read_bytes()
    if expected_sha is not None:
        require(re.fullmatch("[0-9a-f]{64}", expected_sha) is not None and sha(payload) == expected_sha,
                "reviewed bundle SHA mismatch")
    r = json.loads(payload)
    require(r["schema"] == "native60-service-prelaunch-v1" and r["service_measured"] is False,
            "unadmitted service bundle")
    require(encoded(r["budget"]) == encoded(budget()) and
            (directory / "recipe.json").read_bytes() == encoded(budget()), "budget changed")
    require(encoded(r["readback_contract"]) == encoded(readback_contract()), "readback-only contract changed")
    original = check_cohort(directory)
    actual = inventory(directory)
    actual.pop("bundle.json")
    require(actual == r["files"], "bundle file inventory mismatch")
    expected_names = set(original["source_sha256"]) | set(EXTRA_IMMUTABLE) | set(ADDITIVE)
    require(set(r["source_sha256"]) == expected_names, "exact original76 plus additive closure required")
    require(sha(encoded(r["source_sha256"])) == r["source_signature"], "source signature mismatch")
    for name, value in r["source_sha256"].items():
        require(actual["source_snapshot/" + name] == value, "source receipt not tied to snapshot bytes")
    for name, value in (original["source_sha256"] | EXTRA_IMMUTABLE).items():
        require(r["source_sha256"][name] == value, "immutable original source changed")
    frozen = directory / "source_snapshot"
    require(r["python_import_edges"] == python_dependencies(frozen), "Python import closure changed")
    require(set(r["python_import_edges"]) <= expected_names, "Python import source not frozen")
    check_bench(frozen)
    return r


def _receipt(log, name, fields, hex_fields=()):
    rows = re.findall(r"^" + name + r" (.*)$", log, re.MULTILINE)
    require(len(rows) == 1, f"missing/duplicate {name}")
    pairs = [word.split("=") for word in rows[0].split()]
    require(all(len(pair) == 2 for pair in pairs), f"malformed {name}")
    require(len(pairs) == len(fields) and {pair[0] for pair in pairs} == set(fields), f"unexpected fields {name}")
    try:
        result = {key: int(value, 16 if key in hex_fields else 10) for key, value in pairs}
    except ValueError as error:
        raise ValueError(f"unknown/noninteger {name}") from error
    require(all(value >= 0 for value in result.values()), f"negative receipt {name}")
    return result


def verify_result(directory, inputs):
    verify(inputs)
    paths = [directory / name for name in ["simulation.log", "native60_actual_raw_tuples.txt",
                                           "native60_actual_source.txt", "native60_actual_capture.txt",
                                           "native60_actual_holds.txt"]]
    require(all(path.is_file() and path.stat().st_size <= 10_000_000 for path in paths), "missing/oversized result logs")
    log, raw, source, capture, holds = [path.read_text() for path in paths]
    require(not any(word in log.lower() for word in ["fail", "fatal", "error", "warning", "parser_only"]), "failure/nonservice log")
    cfg = _receipt(log, "NATIVE60_CONFIG", ["cycle", "id", "abi", "rate", "geometry", "caps", "generation", "eh"],
                   {"id", "abi", "geometry", "caps", "generation"})
    require([cfg[key] for key in ["id", "abi", "rate", "geometry", "caps"]] == recipe()["public_identity"] and
            cfg["generation"] == 0x60000001 and cfg["eh"] == 1073758594, "public config identity")
    adm = _receipt(log, "NATIVE60_ADMISSION", ["index", "center", "capture_first", "lead", "trigger_cycle", "handshake_cycle", "request", "generation"],
                   {"request", "generation"})
    require(34359738560 <= adm["index"] <= 34359738720 and adm["center"] == 34359740384 and
            adm["capture_first"] == 34359740256 and adm["lead"] == 34359740256-adm["index"]-1 and
            1535 <= adm["lead"] <= 1695 and adm["request"] == 0x60000520 and adm["generation"] == 0x60000001 and
            cfg["cycle"] < adm["trigger_cycle"] <= adm["handshake_cycle"] <= adm["trigger_cycle"]+256,
            "actual command coordinate/identity/control budget")
    snapshot = _receipt(log, "NATIVE60_SNAPSHOT", ["count", "capture_cycle", "return_cycle", "captured_index",
        "live_at_capture", "public_index", "retained_index", "live_at_return", "capture_lag", "return_lag",
        "maximum_capture_lag", "maximum_return_lag", "maximum_return_cycles"])
    verify_snapshot(snapshot, adm["trigger_cycle"], adm["handshake_cycle"])
    off = _receipt(log, "NATIVE60_SOURCE_OFF", ["cycle", "source", "first", "stop", "capture", "busy"])
    require({key: off[key] for key in off if key != "cycle"} ==
            {"source": 16423, "first": 34359735211, "stop": 34359751634, "capture": 520, "busy": 1}, "source-off inventory")
    drain = _receipt(log, "NATIVE60_DRAIN", ["cycle", "raw", "qualified", "engine_idle", "bridge_idle"])
    require({key: drain[key] for key in drain if key != "cycle"} ==
            {"raw": 257, "qualified": 241, "engine_idle": 1, "bridge_idle": 1}, "complete raw drain")
    release = _receipt(log, "NATIVE60_RELEASE", ["cycle", "raw", "qualified", "packet_reads", "retained_cycles", "settle_cycles", "irq", "available"])
    require(249 <= release["raw"] <= 257 and release["qualified"] == 241 and release["packet_reads"] == 52 and
            release["retained_cycles"] == 32 and release["settle_cycles"] == 24 and
            release["irq"] == release["available"] == 0, "public retention/release inventory")
    b = _receipt(log, "NATIVE60_BUDGET", ["capture_end", "publish", "drain", "release", "source_off", "quiet_start", "quiet_end", "raw_at_publish", "raw_after_publish", "maximum_axi", "readout_transactions", "source_off_compute", "maximum_tuple_hold"])
    require(adm["handshake_cycle"] < b["capture_end"] < b["source_off"] < b["drain"] and
            b["capture_end"] < b["publish"] < b["release"] and
            max(b["source_off"], b["release"], b["drain"]) <= b["quiet_start"] and
            b["quiet_end"]-b["quiet_start"] == 256 and b["quiet_end"] < 160000, "lifecycle order/no-stale/watchdog")
    require(b["drain"] == drain["cycle"] and b["release"] == release["cycle"] and b["source_off"] == off["cycle"],
            "inconsistent lifecycle receipts")
    require(b["publish"]-b["capture_end"] <= 84000 and b["drain"]-b["capture_end"] <= 84000 and
            b["release"]-b["capture_end"] <= 88000 and 1 <= b["maximum_axi"] <= 24 and
            105 <= b["readout_transactions"] <= 140 and 1 <= b["source_off_compute"] <= b["drain"]-b["source_off"],
            "complete state/readout/source-off budget")
    require(249 <= b["raw_at_publish"] <= release["raw"] <= 257 and
            b["raw_at_publish"]+b["raw_after_publish"] == 257 and
            (release["raw"] == 257 if b["release"] >= b["drain"] else True), "raw tail not fully accounted")
    clock = _receipt(log, "NATIVE60_CLOCK", ["first_edge_fs", "first_fall_fs", "half_fs", "period_fs", "control_period_fs", "source_edges", "after_off_edges", "quiet_edges"])
    for key, expected in {"first_edge_fs": 10433333, "first_fall_fs": 18766666, "half_fs": 8333333,
                              "period_fs": 16666666, "control_period_fs": 10000000}.items():
        require(abs(clock[key]-expected) <= 1, "actual oscillator origin/cadence")
    require(clock["source_edges"] > 16423 and 152 <= clock["quiet_edges"] <= 155 and
            clock["quiet_edges"] <= clock["after_off_edges"] <= clock["source_edges"], "continuing source clock missing")
    # Control cycle n's falling edge is exactly n*10ns; oscillator starts at
    # the independently asserted first edge, with quantized fixed half periods.
    edges_at = lambda cycle: (cycle*10000000 - 10433333)//16666666 + 1
    require(clock["source_edges"] == edges_at(b["quiet_end"]) and
            clock["quiet_edges"] == edges_at(b["quiet_end"])-edges_at(b["quiet_start"]),
            "clock edge inventory versus control-cycle coordinates")
    off_time_fs = 18766666 + (clock["source_edges"]-clock["after_off_edges"]-1)*16666666
    require(b["source_off"]*10000000-5000000 <= off_time_fs < b["source_off"]*10000000+5000000,
            "source-off falling edge versus control-cycle coordinate")
    terminal = {"source": 16423, "capture": 520, "raw": 257, "qualified": 241, "packet_reads": 52, "admissions": 1,
                    "health": 0, "source_stopped": 1, "clock_running": 1, "idle": 1, "irq": 0, "available": 0,
                    "actual_native": 1, "actual_fft": 0, "actual_psma": 0, "actual_pil1": 0, "static_center": 1}
    require(_receipt(log, "NATIVE60_PASS", list(terminal)) == terminal, "terminal inventory/health/scope")
    expected_packet = (inputs / "native_expected_packet.mem").read_text().splitlines()
    packets = re.findall(r"^NATIVE60_PACKET_WORD pass=(\d+) word=(\d+) data=([0-9a-f]{8})$", log, re.MULTILINE)
    require(packets == [(str(p), str(n), expected_packet[n]) for p in range(2) for n in range(26)], "exact repeated public packet")
    require(len(re.findall(r"^NATIVE60_", log, re.MULTILINE)) == 61, "unrecognized/duplicate evidence marker")
    rows = json.loads((inputs / "native_all_raw_tuples.json").read_bytes())
    expected_raw = []
    for row in rows:
        words = [str(row["lag"])] + [f"{int(row[field]) & ((1 << bits)-1):0{width}x}"
                    for field, bits, width in [("start_index", 64, 16), ("real", 48, 12), ("imag", 48, 12),
                                               ("Ex", 48, 12), ("Eh", 48, 12), ("power", 96, 24), ("saturation", 9, 3)]]
        expected_raw.append(" ".join(words + [str(int(row["qualified"]))]))
    require(raw.splitlines() == expected_raw and len(expected_raw) == 257, "all257 independent raw tuples/power")
    hold_rows = [line.split() for line in holds.splitlines()]
    require(len(hold_rows) == 257 and all(len(row) == 2 for row in hold_rows), "per-tuple hold trace incomplete")
    hold_rows = [[int(x) for x in row] for row in hold_rows]
    require([row[0] for row in hold_rows] == list(range(-128, 129)) and
            all(0 <= row[1] <= 16 for row in hold_rows) and
            max(row[1] for row in hold_rows) == b["maximum_tuple_hold"], "per-tuple reducer hold allowance")
    indexes = (inputs / "source_index_u64.mem").read_text().splitlines()
    source_iq = (inputs / "source_ci16.mem").read_text().splitlines()
    require(source.splitlines() == [f"{i} {v}" for i, v in zip(indexes, source_iq, strict=True)], "all16423 source coordinates/strobes/packing")
    capture_iq = (inputs / "native_capture_ci16.mem").read_text().splitlines()
    require(capture.splitlines() == [f"{n} {34359740256+n:016x} {34359740256+n:016x} {v}"
                                    for n, v in enumerate(capture_iq)], "all520 original capture coordinates/packing")
    return {"result": "NATIVE60_ONLY_VERIFIED", "budget": b, "clock": clock, "admission": adm,
            "snapshot": snapshot,
            "scope": "actual native60 standalone simulation only; static known center; no PSMA/PIL1/FFT or RF claim"}


def verify_snapshot(s, trigger_cycle, handshake_cycle):
    """Public-pair coherence and separately derived CDC/return-age limits."""
    bounds = readback_limits()
    require(all(type(v) is int and v >= 0 for v in s.values()), "known unsigned snapshot fields")
    require(s["count"] == 1 and
            trigger_cycle <= s["capture_cycle"] <= s["return_cycle"] <= handshake_cycle and
            s["return_cycle"]-s["capture_cycle"] <= bounds["return_cycles"], "low-register capture/read timing")
    require(34359735211 <= s["captured_index"] <= s["live_at_capture"] <= s["live_at_return"] < 34359751634 and
            s["public_index"] == s["retained_index"] == s["captured_index"], "known/nonfuture/coherent public64 snapshot")
    require(s["live_at_capture"]-s["captured_index"] == s["capture_lag"] <= bounds["capture_lag"] and
            s["live_at_return"]-s["public_index"] == s["return_lag"] <= bounds["return_lag"] and
            s["maximum_capture_lag"] == bounds["capture_lag"] and
            s["maximum_return_lag"] == bounds["return_lag"] and
            s["maximum_return_cycles"] == bounds["return_cycles"], "separately bounded snapshot age")


def run(bundle, output, expected_sha, *, authorize_native_service=False):
    """Default is compile-only. The caller, not this helper, owns authorization."""
    require(type(authorize_native_service) is bool, "explicit native service boolean required")
    require(not output.exists(), "refusing to overwrite run directory")
    admitted = verify(bundle, expected_sha)
    require(sha(Path(__file__).read_bytes()) == admitted["source_sha256"]["tests/starlink_oracle/native60_budget.py"],
            "runner helper differs from reviewed snapshot")
    output.mkdir(parents=True)
    shutil.copytree(bundle, output / "inputs")
    inputs = output / "inputs"
    before = inventory(inputs)
    (output / "sources-before.json").write_bytes(encoded(before))
    (output / "environment.json").write_bytes(encoded({"host": platform.node(), "platform": platform.platform(),
        "python": sys.version, "python_executable": sys.executable, "native_service_authorized": authorize_native_service,
        "scope": "host-only Icarus simulation; not Zynq runtime", "wall_timeout_seconds": 120}))
    for name in json.loads((inputs / "cohort.json").read_bytes())["files"]:
        shutil.copyfile(inputs / name, output / name)
    fixture_before = {name: sha((output / name).read_bytes()) for name in json.loads((inputs / "cohort.json").read_bytes())["files"]}
    (output / "fixture-before.json").write_bytes(encoded(fixture_before))
    frozen = inputs / "source_snapshot"
    executable = output / "native.vvp"
    command = ["iverilog", "-g2012", "-Wall", "-I", str(frozen / TB), "-s", "tb_starlink_native60_budget",
               "-o", str(executable), *[str(frozen / name) for name in NATIVE_SOURCES + [TOP]]]
    status = {"mode": "native-service" if authorize_native_service else "compile-only", "compile_command": command,
              "compile_exit": None, "simulation_exit": None, "error": None, "integrity_error": None}
    child_env = {k: v for k, v in os.environ.items() if k not in {"PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH"}}
    try:
        for tool in ["iverilog", "vvp"]:
            path = shutil.which(tool)
            require(path is not None, f"missing {tool}")
            status[tool + "_path"] = path
            status[tool + "_sha256"] = sha(Path(path).read_bytes())
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False, env=child_env)
        diagnostics = compiled.stdout + compiled.stderr
        (output / "compile.log").write_text(diagnostics)
        status["compile_exit"] = compiled.returncode
        status["compile_diagnostics_bytes"] = len(diagnostics.encode())
        status["compile_warning_mentions"] = diagnostics.lower().count("warning")
        require(compiled.returncode == 0, "native60 compile failed")
        if authorize_native_service:
            simulation = subprocess.run(["vvp", str(executable)], cwd=output, capture_output=True,
                                        text=True, timeout=120, check=False, env=child_env)
            (output / "simulation.log").write_text(simulation.stdout + simulation.stderr)
            status["simulation_exit"] = simulation.returncode
            require(simulation.returncode == 0, "native60 service failed")
            result = verify_result(output, inputs)
        else:
            result = {"result": "NATIVE60_COMPILE_ONLY", "service_measured": False}
    except Exception as error:
        status["error"] = repr(error)
        if isinstance(error, subprocess.TimeoutExpired):
            fragments = [x.encode() if isinstance(x, str) else x or b"" for x in [error.stdout, error.stderr]]
            (output / "timeout-output.log").write_bytes(b"".join(fragments))
        raise
    finally:
        try:
            after = inventory(inputs)
            (output / "sources-after.json").write_bytes(encoded(after))
            fixture_after = {name: sha((output / name).read_bytes()) for name in fixture_before}
            (output / "fixture-after.json").write_bytes(encoded(fixture_after))
            require(before == after and fixture_before == fixture_after, "source/fixture changed during run")
            verify(inputs, expected_sha)
        except Exception as error:  # noqa: BLE001 - preserve original failure plus separate integrity failure
            status["integrity_error"] = repr(error)
            if status["error"] is None:
                status["error"] = "post-run integrity failure"
        (output / "run-status.json").write_bytes(encoded(status))
    require(status["integrity_error"] is None, "post-run integrity failed")
    (output / "terminal.json").write_bytes(encoded(result))
    return result

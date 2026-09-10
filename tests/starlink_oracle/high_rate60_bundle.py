"""Offline paired60 source closure, admission and compile-only preparation.

No simulator is launched here. The old native91 source pins retain all original
76 cohort dependencies; precisely two reviewed StageA60 bodies are substituted.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
from pathlib import Path

from .high_rate60_harness import PROFILE, check_recipe, prepare_vectors, verify_vectors
from .native60_budget import check_cohort, encoded, require, sha

ROOT = Path(__file__).resolve().parents[2]
ACQ = "hdl/library/starlink_pss_acquisition/"
TB = ACQ + "tb/"
TOP = TB + "tb_starlink_pss_60_bank_native_paired.sv"
RUNNER = ACQ + "simulate_high_rate60_bank_native_paired.tcl"
CLI = "tools/prepare_starlink_high_rate60_harness.py"
PINS = "tests/starlink_oracle/high_rate60_native_source_pins.json"
ADDITIVE = [TOP, RUNNER, CLI, PINS,
    *[TB + "bank_native60_" + name + "_checks.svh" for name in ["clock", "source", "fft"]],
    *["tests/starlink_oracle/high_rate60_" + name + ".py" for name in ["harness", "harness_result", "harness_recipe", "bundle"]],
    *["tests/test_starlink_high_rate60_" + name + ".py" for name in ["harness", "harness_result", "bundle"]],
    "docs/starlink-high-rate60-harness-recipe-before-evaluation-20260910.md",
    ACQ + "create_shared_realtime_xfft_ip.tcl",
    "hdl/library/axi_starlink_pss_phase_map/starlink_pss_axi_lite.v",
]


def safe_path(path):
    require(not any(p.is_symlink() for p in [path, *path.parents]), "symlink source/output parent forbidden")


def inventory(directory):
    safe_path(directory)
    result = {}
    for p in sorted(directory.rglob("*")):
        require(not p.is_symlink(), "symlink input forbidden")
        if p.is_file():
            require(p.stat().st_size <= 10_000_000, "oversized source/numerical input")
            result[p.relative_to(directory).as_posix()] = sha(p.read_bytes())
    require(len(result) <= 1000, "unbounded bundle inventory")
    return result


def python_dependencies(root, names):
    pending, edges = [name for name in names if name.endswith(".py")], {}
    while pending:
        name = pending.pop()
        if name in edges:
            continue
        dependencies = set()
        for node in ast.walk(ast.parse((root / name).read_text())):
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
                pieces = module.split(".")
                for length in range(1, len(pieces)):
                    init = "/".join(pieces[:length]) + "/__init__.py"
                    if (root / init).is_file():
                        dependencies.add(init)
                dependency = module.replace(".", "/") + ".py"
                if not (root / dependency).is_file():
                    dependency = module.replace(".", "/") + "/__init__.py"
                require((root / dependency).is_file(), f"missing local import: {name}: {module}")
                dependencies.add(dependency)
        edges[name] = sorted(dependencies)
        pending.extend(dependencies)
    return dict(sorted(edges.items()))


def base_pins(root):
    payload = (root / PINS).read_bytes()
    require(sha(payload) == "7c3793f72d5673d09c7ff6fe2dc0039387e8bb23b89e2ab596d77851122c8f0a", "original native pin table changed")
    p = json.loads(payload)
    require(p["native_bundle_sha256"] == "bbcb423cf7d1f73bd6a6e7be3666aafe1eaa80414f7d99384ec5ad73c049ba83" and
            len(p["source_sha256"]) == 91, "original native91 identity")
    return p["source_sha256"] | check_recipe()["approved_stage_a"] | {
        ACQ + "create_shared_realtime_xfft_ip.tcl": "0795ea7e6aa981d78080ac22fa4ba6355da59d6829ceb409dda07a54f7f9420d",
        "hdl/library/axi_starlink_pss_phase_map/starlink_pss_axi_lite.v": "7ccf4a8a297670c43f9184d9965f533bfd7ff5e32954dff6267b4d083299be7c",
    }


def native_adaptation(root):
    """Strict complete-function projection, with eight enumerated outer edits.

    AST equality discards whitespace ONLY. All expressions, bounds, constants,
    messages, ordering and complete inner numerical/lifecycle checks remain.
    """
    base = (root / "tests/starlink_oracle/native60_budget.py").read_text()
    original = next(n for n in ast.parse(base).body if isinstance(n, ast.FunctionDef) and n.name == "verify_result")
    expected = ast.get_source_segment(base, original)
    terminal = expected[expected.index('    terminal = {"source": 16423'):expected.index('    expected_packet =')]
    changes = [
        ("def verify_result(directory, inputs):", "def verify_native_component(directory, inputs, log):"),
        ("    verify(inputs)", "    check_cohort(inputs)"),
        ('["simulation.log", "native60_actual_raw_tuples.txt",', '["native60_actual_raw_tuples.txt",'),
        ("log, raw, source, capture, holds =", "raw, source, capture, holds ="),
        (terminal, ""),
        ('== 61, "unrecognized/duplicate evidence marker"', '== 60, "unrecognized/duplicate native component evidence marker"'),
        ('"result": "NATIVE60_ONLY_VERIFIED"', '"result": "PAIRED60_NATIVE_COMPONENT_VERIFIED"'),
        ('"actual native60 standalone simulation only; static known center; no PSMA/PIL1/FFT or RF claim"',
         '"native component evidence inside paired60 simulation; static known center, not RF truth"'),
    ]
    for before, after in changes:
        require(expected.count(before) == 1, "native projection original context changed")
        expected = expected.replace(before, after)
    actual = (root / "tests/starlink_oracle/high_rate60_harness_result.py").read_text()
    component = next(n for n in ast.parse(actual).body if isinstance(n, ast.FunctionDef) and n.name == "verify_native_component")
    require(ast.dump(ast.parse(expected).body[0]) == ast.dump(component), "native complete verifier adaptation changed")


def check_bench(root):
    texts = {name: (root / name).read_text() for name in [TOP, *[TB + "bank_native60_" + s + "_checks.svh" for s in ["source", "fft", "clock"]]]}
    tokens = {
        TOP: ["#(500.0/60)", "#(500.0/175)", ".INPUT_RATE_MSPS(60)", ".ENABLE_BANK60_PAIRED(1)",
              ".USE_BANK_OWNED_XFFT(1)", ".ENABLE_BOUNDARY_STOP(1)", "32'h10008", "32'h020f0403",
              "dut.acquisition.COEFFICIENT_ENERGY!=1073765335", "8'hbc,1073765335", "32'h8e807d15", "32'ha31de5b2", "source_range(0,2)", "source_range(2,3111)",
              "repeat(2000)", "source_range(3114,16425-3114)", "source_checked!=16425", "continuous_checked!=13312",
              "wait(native_drain_cycle>=0)", "native_raw_count!=257", "native_qualified_count!=241", "repeat(256)",
              "pilot_irq} !== 0", "cycles>=160000", "source_enable!==0", "map_retained=1", "native_compute_after_stop",
              "pss_irq!==1", "{dut.map_ready_mask,pss_irq}!==0", "stop_terminal_valid})===1'bx)"],
        TB + "bank_native60_source_checks.svh": ["checked_enable=expected_coarse_enable || expected_pilot_enable",
              "dut.conditioner_enable!==checked_enable", "pilot_enable!==expected_pilot_enable", "first_pipe[5]",
              "second_pipe[5]", "first_history==14", "second_history==14", "if(first_output_now)",
              "expected_pilot_enable=0", "pilot.admitted!==admitted_count", "continuous_checked*16.666666",
              "34359738322+continuous_checked", "source_checked!=3113+continuous_checked", "8.333333",
              "dut.ddc_accepted_sample_count!==enabled_raw", "dut.ddc_emitted_sample_count!==emitted_raw_model",
              "pilot_ready})===1'bx)", "pilot.ddc.mixed_saturations!==0", "pilot.capture_support!==1"],
        TB + "bank_native60_fft_checks.svh": ["always @(posedge fft_clk)", "native.capture_active===1'b1",
              "core_input_valid===1'b1 && `H60_ISLAND.core_input_ready===1'b1", "6'b0,expected_fft_input[35:18]",
              "score_count>=1341", "score_phase!==score_count%447", "output_denominator!==denominators[ratio_count]",
              "inverse_output_valid}!==0", "core_aresetn!==0", "output_denominator_zero!==0",
              "score_denominator_zero!==0", "product_overflow!==0"],
        TB + "bank_native60_clock_checks.svh": ["10.433333", "18.766666", "16.666666", "8.333333", "4.157143", "7.014286", "5.714286", "2.857143"],
    }
    for name, required in tokens.items():
        for token in required:
            require(token in texts[name], f"paired60 bench contract missing: {token}")
    code = re.sub(r"//[^\n]*", "", "\n".join(texts.values()))
    require(not re.search(r"\bforce\b|\$stop\b", code), "hierarchy forcing/interactive stop forbidden")
    assignments = re.findall(r"defparam\s+([^;]+);", code)
    require(assignments == [
        "dut.acquisition.PHASE_BINS=447", "dut.acquisition.TILE_FRAMES=2",
        "dut.acquisition.MAP_SEGMENT_ADDRESS_WIDTH=9", "dut.acquisition.MAP_SEGMENT_COUNT=1",
        "dut.acquisition.MAP_SEGMENT_INDEX_WIDTH=1", "dut.phase_map_control.PHASE_BINS=447",
        "dut.phase_map_control.TILE_FRAMES=2"], "only declared reduced map geometry overrides admitted")
    no_defparam = re.sub(r"defparam[^;]+;", "", code)
    require(not re.search(r"\b(?:dut|native|pilot)\.[\w.]+\s*(?:<=|=(?!=))", no_defparam), "hierarchy writes forbidden")
    native_adaptation(root)


def freeze(cohort, output, root=ROOT):
    safe_path(output)
    require(not output.exists(), "refusing to overwrite paired60 bundle")
    original = check_cohort(cohort)
    pins = base_pins(root)
    require(set(original["source_sha256"]) <= pins.keys(), "old76 source closure absent")
    edges = python_dependencies(root, set(pins) | set(ADDITIVE))
    names = sorted(set(pins) | set(ADDITIVE) | set(edges))
    before = {}
    for name in names:
        safe_path(root / name)
        before[name] = sha((root / name).read_bytes())
        require(before[name] == pins.get(name, before[name]), f"unapproved old/native/runtime delta: {name}")
    check_bench(root)
    output.mkdir(parents=True)
    prepare_vectors(cohort, output / "vectors")
    (output / "cohort").mkdir()
    for name in ["cohort.json", *original["files"]]:
        shutil.copyfile(cohort / name, output / "cohort" / name)
    for name in names:
        target = output / "source_snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
    after = {name: sha((root / name).read_bytes()) for name in names}
    require(before == after, "source changed during freeze")
    check_cohort(cohort)
    result = {"schema": "paired60-prelaunch-v1", "profile": PROFILE, "actual_execution": False,
              "recipe": check_recipe(), "source_sha256": before, "source_signature": sha(encoded(before)),
              "python_import_edges": edges, "files": inventory(output)}
    (output / "bundle.json").write_bytes(encoded(result))
    verify_bundle(output)
    return result


def verify_bundle(output, expected_sha=None):
    safe_path(output)
    payload = (output / "bundle.json").read_bytes()
    if expected_sha is not None:
        require(re.fullmatch("[0-9a-f]{64}", expected_sha) is not None and sha(payload) == expected_sha,
                "reviewed external bundle SHA mismatch")
    r = json.loads(payload)
    require(r["schema"] == "paired60-prelaunch-v1" and r["profile"] == PROFILE and r["actual_execution"] is False,
            "unadmitted paired60 bundle")
    check_recipe(r["recipe"])
    actual = inventory(output)
    actual.pop("bundle.json")
    require(actual == r["files"], "bundle inventory changed")
    frozen = output / "source_snapshot"
    pins = base_pins(frozen)
    edges = python_dependencies(frozen, set(pins) | set(ADDITIVE))
    names = set(pins) | set(ADDITIVE) | set(edges)
    require(set(r["source_sha256"]) == names and r["python_import_edges"] == edges, "source/import closure changed")
    require(r["source_signature"] == sha(encoded(r["source_sha256"])), "source signature changed")
    for name, digest in r["source_sha256"].items():
        require(digest == actual["source_snapshot/" + name], "disconnected source signature")
        require(digest == pins.get(name, digest), "original/native/StageA runtime changed")
    original = check_cohort(output / "cohort")
    require(set(original["source_sha256"]) <= pins.keys(), "old76 missing")
    verify_vectors(output / "cohort", output / "vectors")
    check_bench(frozen)
    return r

"""Additive late60 bundle; immutable healthy closure nested without replacement."""

import json
import re
import shutil

from .high_rate60_bundle import inventory, python_dependencies, safe_path
from .high_rate60_bundle import verify_bundle as verify_healthy
from .high_rate60_late import LOGIC, ROOT, adapted_sources, check_recipe
from .native60_budget import encoded, require, sha

ADDITIVE = [LOGIC, "tools/prepare_starlink_high_rate60_late.py",
    *["tests/starlink_oracle/high_rate60_late"+suffix+".py" for suffix in ["","_recipe","_result","_bundle"]],
    *["tests/test_starlink_high_rate60_late"+suffix+".py" for suffix in ["","_result","_bundle"]],
    "tests/test_starlink_high_rate60_late_settle.py",
    "docs/starlink-high-rate60-late-recipe-before-evaluation-20260910.md"]


def closure(root, healthy):
    edges = python_dependencies(root,set(healthy["source_sha256"]) | set(ADDITIVE))
    names = sorted(set(healthy["source_sha256"]) | set(ADDITIVE) | set(edges))
    hashes = {}
    for name in names:
        safe_path(root/name)
        hashes[name] = sha((root/name).read_bytes())
        require(hashes[name] == healthy["source_sha256"].get(name,hashes[name]), f"unchanged healthy source differs: {name}")
    return hashes,edges


def check_logic(root):
    text = (root/LOGIC).read_text()
    for token in ["LATE_TRIGGER=64'd34359740288,LATE_LAST=64'd34359740448", "cycles-native_trigger_cycle>256",
        "late_signed_lead < -193 || late_signed_lead > -33", "continuous_source}!==3'b111",
        "STATE_COEFFICIENT_COPY_FINISH", "late post-ready native engine not exactly idle", "native_engine_idle!==1",
        "native.result_word_read,native.result_release", "`N60_SCHED.last_admitted_valid}!==0",
        "native.rejected_count!==late_handshakes", "native.late_count!==late_handshakes",
        "native.candidate_command_handshake===1'b1", "native.candidate_submit_accepted===1'b1",
        "cycles-begin_cycle>512", "cycles-begin_cycle>1328", "cycles-source_off_cycle>2048",
        "late_register_reads!=62", "repeat(8)", "late_snapshot(1)", "late_snapshot(2)",
        "while(cycles-late_handshake_cycle<8) @(negedge clk);",
        "while(cycles-source_off_cycle<8) @(negedge clk);",
        "core_input_ready===1'b1", "next_inverse===1'b0", "pilot.ddc.accept===1'b1",
        "source_checked!=16425", "!source_finished || !coarse_stopped || !map_retained"]:
        count = 2 if token in {"cycles-native_trigger_cycle>256", "continuous_source}!==3'b111",
                              "cycles-source_off_cycle>2048", "late_register_reads!=62", "repeat(8)",
                              "`N60_SCHED.last_admitted_valid}!==0"} else 1
        require(text.count(token) == count, f"late evidence contract count changed: {token}")
    code = re.sub(r"//[^\n]*","",text)
    require(not re.search(r"\bforce\b|\$stop\b|\bdefparam\b",code), "late hierarchy forcing/override forbidden")
    require(not re.search(r"\b(?:native|dut|pilot)\.[\w.]+\s*(?:<=|=(?!=))",code), "late hierarchy writes forbidden")
    require(not re.search(r"(?:read|write)_reg\(2,\s*8'h(?:54|58)",code), "late packet access/release forbidden")


def freeze(healthy_path, output, root=ROOT):
    safe_path(output)
    require(not output.exists(), "refusing to overwrite late60 bundle")
    recipe = check_recipe()
    healthy = verify_healthy(healthy_path,recipe["healthy_bundle_sha256"])
    require(healthy["source_signature"] == recipe["healthy_source_signature"], "healthy108 identity changed")
    before,edges = closure(root,healthy)
    check_logic(root)
    derived = adapted_sources(root,healthy)
    output.mkdir(parents=True)
    shutil.copytree(healthy_path,output/"healthy")
    for name in before:
        target = output/"source_snapshot"/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(root/name,target)
    (output/"case").mkdir()
    for name,value in derived.items():
        (output/"case"/name).write_text(value)
    after,after_edges = closure(root,healthy)
    require(before == after and edges == after_edges, "source changed during late60 freeze")
    verify_healthy(healthy_path,recipe["healthy_bundle_sha256"])
    result = {"schema":"paired60-late-prelaunch-v1","profile":recipe["profile"],"actual_execution":False,
        "recipe":recipe,"source_sha256":before,"source_signature":sha(encoded(before)),
        "python_import_edges":edges,"files":inventory(output)}
    (output/"bundle.json").write_bytes(encoded(result))
    verify_bundle(output)
    return result


def verify_bundle(output, expected_sha=None):
    safe_path(output)
    payload = (output/"bundle.json").read_bytes()
    if expected_sha is not None:
        require(re.fullmatch("[0-9a-f]{64}",expected_sha) is not None and sha(payload) == expected_sha,
                "reviewed external late60 bundle SHA mismatch")
    r = json.loads(payload)
    require(r["schema"] == "paired60-late-prelaunch-v1" and r["profile"] == check_recipe()["profile"] and
            r["actual_execution"] is False, "late60 unadmitted bundle context")
    check_recipe(r["recipe"])
    actual = inventory(output)
    actual.pop("bundle.json")
    require(actual == r["files"], "late60 bundle inventory changed")
    healthy = verify_healthy(output/"healthy",r["recipe"]["healthy_bundle_sha256"])
    frozen = output/"source_snapshot"
    hashes,edges = closure(frozen,healthy)
    require(hashes == r["source_sha256"] and edges == r["python_import_edges"] and
            sha(encoded(hashes)) == r["source_signature"], "late60 source/import closure changed")
    require(all(digest == actual["source_snapshot/"+name] for name,digest in hashes.items()), "disconnected late60 source signature")
    check_logic(frozen)
    expected = adapted_sources(frozen,healthy)
    require({p.name:p.read_text() for p in (output/"case").iterdir()} == expected, "strict complete-source inverse/context changed")
    return r

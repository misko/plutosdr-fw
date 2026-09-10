"""Standalone issuer + real guards/product; not a vendor FFT/top integration."""
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.test_checked_product_read import clean_env

ROOT = Path(__file__).resolve().parents[2]
ACQ = ROOT / "hdl/library/starlink_pss_acquisition"
NAMES = ["starlink_pss_product_sealed_adapter.v", "starlink_pss_checked_product_read.v",
         "starlink_pss_epoch_sealed_bank.v", "starlink_pss_block_mailbox.v",
         "starlink_pss_realtime_input_guard.v", "starlink_pss_realtime_result_guard.v",
         "starlink_pss_spectrum_product.v", "tb/tb_starlink_pss_product_sealed_adapter.sv"]


def compile_case(path, mutation=None, parameter="1"):
    path.mkdir()
    for name in NAMES:
        shutil.copyfile(ACQ / name, path / Path(name).name)
    if parameter != "1":
        bench = path / Path(NAMES[-1]).name
        source = bench.read_text()
        assert source.count("parameter integer ENABLED=1") == 1
        bench.write_text(source.replace("parameter integer ENABLED=1", f"parameter integer ENABLED={parameter}"))
    shutil.copyfile(Path(__file__), path / Path(__file__).name)
    shutil.copyfile(Path(__file__).with_name("test_checked_product_read.py"), path / "test_checked_product_read.py")
    if mutation:
        name, old, new = mutation
        p = path / name
        source = p.read_text()
        assert source.count(old) == 1
        p.write_text(source.replace(old, new))
    (path / "sources.json").write_text(json.dumps({p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in path.iterdir() if p.is_file()}, indent=2))
    command = ["iverilog", "-g2012", "-Wall", "-s", "tb_starlink_pss_product_sealed_adapter",
               "-o", "sim.vvp", *[Path(n).name for n in NAMES]]
    p = subprocess.run(command, cwd=path, env=clean_env(), text=True, capture_output=True, timeout=30, check=False)
    (path / "compile.log").write_text(p.stdout + p.stderr)
    (path / "compile.json").write_text(json.dumps({"command": command, "exit": p.returncode}))
    assert p.returncode == 0 and not re.search(r"(?im)^.*error:", p.stderr), p.stderr
    return path


@pytest.fixture(scope="module")
def compiled(tmp_path_factory):
    return compile_case(tmp_path_factory.mktemp("product_adapter") / "original")


def execute(path, kind=0, bit=0, target=37):
    command = ["vvp", "sim.vvp", f"+CASE={kind}", f"+BIT={bit}", f"+TARGET={target}"]
    p = subprocess.run(command, cwd=path, env=clean_env(), text=True, capture_output=True, timeout=30, check=False)
    log = p.stdout + p.stderr
    name = f"case-{kind}-bit-{bit}-target-{target}"
    (path / f"{name}.log").write_text(log)
    (path / f"{name}.json").write_text(json.dumps({"command": command, "exit": p.returncode}))
    return p.returncode, log


def test_eight_actual_guard_product_leases_complete(compiled):
    code, log = execute(compiled)
    assert code == 0 and "PRODUCT_ADAPTER_PASS case=0 jobs=8" in log, log
    assert log.count("take=512 seal_delta=2 publish_delta=3") == 8, log


@pytest.mark.parametrize("target", [0, 37, 511])
def test_real_arithmetic_overflow_never_publishes(compiled, target):
    code, log = execute(compiled, 1, target=target)
    assert code == 0 and "PRODUCT_ADAPTER_NEGATIVE_PASS case=1" in log, log


def test_prefetch_final_waits_actual_guard_complete(compiled):
    code, log = execute(compiled, 2)
    assert code == 0 and "PRODUCT_ADAPTER_PASS case=2 jobs=1" in log, log


@pytest.mark.parametrize("bit", range(8))
def test_all_current_faults_and_private_reset_preserve_poison(compiled, bit):
    code, log = execute(compiled, 3, bit)
    assert code == 0 and "PRODUCT_ADAPTER_NEGATIVE_PASS case=3" in log, log


@pytest.mark.parametrize("bit", range(70))
@pytest.mark.parametrize("target", [0, 37, 511])
def test_all_actual_product_metadata_bits(compiled, bit, target):
    code, log = execute(compiled, 4, bit, target)
    assert code == 0 and "PRODUCT_ADAPTER_NEGATIVE_PASS case=4" in log, log


@pytest.mark.parametrize("bit", range(75))
@pytest.mark.parametrize("target", [3, 37, 511])
def test_all_raw_bank_read_bits_including_full_queue_stall(compiled, bit, target):
    code, log = execute(compiled, 5, bit, target)
    assert code == 0 and "PRODUCT_ADAPTER_NEGATIVE_PASS case=5" in log, log


@pytest.mark.parametrize("bit", range(8))
@pytest.mark.parametrize("target", range(4))
def test_current_causes_on_seal_publish_handoff_release_edges(compiled, bit, target):
    code, log = execute(compiled, 6, bit, target)
    assert code == 0 and "PRODUCT_ADAPTER_NEGATIVE_PASS case=6" in log, log


@pytest.mark.parametrize("target", [0, 37, 511])
def test_real_consumer_duplicate_start_veto(compiled, target):
    code, log = execute(compiled, 7, target=target)
    assert code == 0 and "PRODUCT_ADAPTER_NEGATIVE_PASS case=7" in log, log


@pytest.mark.parametrize("target", [0, 1, 2])
@pytest.mark.parametrize("bit", [0, 69, 74])
def test_taken_head_words_checked_before_handoff(compiled, target, bit):
    code, log = execute(compiled, 5, bit, target)
    assert code == 0 and "PRODUCT_ADAPTER_NEGATIVE_PASS case=5" in log, log


@pytest.mark.parametrize("delay", [0, 1, 2])
def test_stalled_corruption_onset_before_current_after_handoff(compiled, delay):
    code, log = execute(compiled, 8, 74, delay)
    assert code == 0 and "PRODUCT_ADAPTER_ONSET_PASS" in log, log
    row = re.search(r"handoffs=(\d+) corruption=(\d+) verdict=(\d+) head=(-?\d+) received=(\d+)", log)
    assert row and int(row[5]) <= 3, log
    if delay == 0:
        assert int(row[1]) == 0, log
    else:
        assert int(row[1]) == 1 and int(row[3]) > int(row[4]), log


@pytest.mark.parametrize("mutation,kind,bit,target,marker", [
    (("starlink_pss_product_sealed_adapter.v", " && !queue_validation_fault;", ";"),
     5, 74, 3, "POISONED_PREFETCH_HANDOFF"),
    (("starlink_pss_product_sealed_adapter.v", "input_metadata({5'b0,product_metadata})", "input_metadata({expected_metadata[74:5],product_metadata[4:0]})"),
     4, 69, 37, "PREHANDOFF_FAULT_NOT_QUARANTINED"),
    (("starlink_pss_product_sealed_adapter.v", "wire certificate_valid = completion_reference && !certificate_consumed;",
      "wire certificate_valid = producer_reference && !certificate_consumed;"),
     0, 0, 37, "CERTIFIED_HANDOFF_MISSING"),
    (("starlink_pss_product_sealed_adapter.v", "handoff_seen && queue_drained &&", "handoff_seen && queue_final &&"),
     9, 0, 37, "LEASE_RELEASE_BEFORE_CERTIFIED_FINAL_DRAIN"),
])
def test_executed_issuer_lifetime_mutants(tmp_path, mutation, kind, bit, target, marker):
    path = compile_case(tmp_path / "mutant", mutation)
    code, log = execute(path, kind, bit, target)
    assert code != 0 and marker in log, log


def test_real_completion_certificate_delivery_hold(compiled):
    code, log = execute(compiled, 9)
    assert code == 0 and "PRODUCT_ADAPTER_PASS case=9 jobs=1" in log, log


def test_default_off_inert_under_hostile_inputs(tmp_path):
    path = compile_case(tmp_path / "default", parameter="0")
    code, log = execute(path, 10)
    assert code == 0 and "PRODUCT_ADAPTER_DEFAULT_INERT_PASS" in log, log


@pytest.mark.parametrize("value", ["-1", "2", "32'bx", "32'bz"])
def test_issuer_parameter_fail_closed(tmp_path, value):
    path = compile_case(tmp_path / "invalid", parameter=value)
    code, log = execute(path)
    assert code != 0 and "SEALED_PRODUCT_ADAPTER must be zero or one" in log, log


@pytest.mark.parametrize("side", [0, 1])
@pytest.mark.parametrize("boundary", [0, 1, 2])
def test_one_sided_common_epoch_requires_explicit_peer_purge(compiled, side, boundary):
    code, log = execute(compiled, 11, side, boundary)
    assert code == 0 and "PRODUCT_ADAPTER_RESET_PASS" in log, log


def test_stale_verdict_at_release_cannot_bypass_drain(compiled):
    code, log = execute(compiled, 12)
    assert code == 0 and "PRODUCT_ADAPTER_NEGATIVE_PASS case=12" in log, log


@pytest.mark.parametrize("bit", [0, 1])
@pytest.mark.parametrize("target", [0, 37, 511])
def test_actual_product_ordinal_and_tlast_are_checked(compiled, bit, target):
    code, log = execute(compiled, 13, bit, target)
    assert code == 0 and "PRODUCT_ADAPTER_NEGATIVE_PASS case=13" in log, log


def combinational_graph(path):
    """Bounded Icarus netlist audit; procedural variables are state/input cuts.

    This is not synthesis, timing, or a proof of arbitrary procedural RTL.
    All this fixture's RTL control is continuous assignment; its only ufuncs
    are the unchanged register-fed numerical rounding functions.
    """
    source = (path / "sim.vvp").read_text()
    graph, names, operations = {}, {}, set()
    token = r"(?:L_0x|v0x)[0-9a-f]+(?:_\d+)?"
    for line in source.splitlines():
        match = re.match(r"(\w+) \.(\S+) (.*);", line)
        if not match:
            continue
        label, operation, body = match.groups()
        if operation.startswith("net") or label.startswith("L_"):
            operations.add(operation)
            graph[label] = set(re.findall(token, body))
            if operation.startswith("net") and (name := re.search(r'"([^\"]+)"', body)):
                names.setdefault(name[1], []).append(label)
            if operation.startswith("ufunc"):
                assert "product.round_and_saturate" in body
    allowed = {"net", "net/2u", "net/2s", "net/s", "arith/sum", "array/port",
               "cmp/eeq", "cmp/eq", "cmp/gt", "cmp/ne", "cmp/nee", "concat", "concat8",
               "functor", "part", "part/v", "reduce/and", "reduce/nor", "reduce/or",
               "reduce/xor", "shift/l", "ufunc/vec4"}
    assert operations <= allowed, operations - allowed
    colors, stack = {}, []

    def visit(node):
        if colors.get(node) == 1:
            raise AssertionError("COMBINATIONAL_CYCLE " + " -> ".join(stack + [node]))
        if colors.get(node) == 2:
            return
        colors[node] = 1
        stack.append(node)
        for other in graph.get(node, ()):
            visit(other)
        stack.pop()
        colors[node] = 2

    for node in graph:
        visit(node)
    def ancestors(node):
        result, pending = set(), [node]
        while pending:
            current = pending.pop()
            if current not in result:
                result.add(current)
                pending.extend(graph.get(current, ()))
        return result
    # These names are unique top-level aliases in this frozen fixture.
    checks = {}
    for fence in ("publication", "handoff_valid", "core_valid", "lease_release"):
        cone = set().union(*(ancestors(node) for node in names[fence]))
        raw_drivers = set().union(*(graph[node] for node in names["offered_metadata"]))
        assert not cone.intersection(raw_drivers), fence
        checks[fence] = len(cone)
    receipt = {"netlist_sha256": hashlib.sha256(source.encode()).hexdigest(),
               "continuous_nodes": len(graph), "operations": sorted(operations),
               "cycles": 0, "cone_nodes": checks,
               "scope": "Icarus continuous graph; procedural state/input cuts; no physical claim"}
    (path / "combinational-graph.json").write_text(json.dumps(receipt, indent=2))
    return receipt


def test_actual_composed_continuous_control_graph(compiled):
    receipt = combinational_graph(compiled)
    assert receipt["continuous_nodes"] > 1000


def test_graph_rejects_release_feedback_mutant(tmp_path):
    mutation = ("starlink_pss_checked_product_read.v", "uncertain || closed_offer || admission_bad;",
                "uncertain || closed_offer || admission_bad || release_valid;")
    path = compile_case(tmp_path / "feedback", mutation)
    with pytest.raises(AssertionError, match="COMBINATIONAL_CYCLE"):
        combinational_graph(path)

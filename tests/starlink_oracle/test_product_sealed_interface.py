"""Additive primitive interface proof; no top/controller or vendor execution."""
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.test_checked_product_read import clean_env
from tests.starlink_oracle.product_interface_graph import ancestors, first_cycle, parse

ROOT = Path(__file__).resolve().parents[2]
ACQ = ROOT / "hdl/library/starlink_pss_acquisition"
NAMES = ["starlink_pss_product_sealed_interface.v", "starlink_pss_checked_product_read_interface.v",
         "starlink_pss_epoch_sealed_bank.v", "starlink_pss_block_mailbox.v",
         "starlink_pss_realtime_input_guard.v", "starlink_pss_realtime_result_guard.v",
         "starlink_pss_spectrum_product.v", "tb/tb_starlink_pss_product_sealed_interface.sv",
         "tb/product_sealed_interface_cases.svh"]


def build(path, mutation=None, parameter="1"):
    path.mkdir()
    for name in NAMES:
        shutil.copyfile(ACQ / name, path / Path(name).name)
    shutil.copyfile(__file__, path / Path(__file__).name)
    shutil.copyfile(Path(__file__).with_name("product_interface_graph.py"), path / "product_interface_graph.py")
    if parameter != "1":
        bench = path / "tb_starlink_pss_product_sealed_interface.sv"
        source = bench.read_text()
        assert source.count("parameter integer ENABLED=1") == 1
        bench.write_text(source.replace("parameter integer ENABLED=1", f"parameter integer ENABLED={parameter}"))
    if mutation:
        name, old, new = mutation
        file = path / name
        source = file.read_text()
        assert source.count(old) == 1
        file.write_text(source.replace(old, new))
    (path / "sources.json").write_text(json.dumps({p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in path.iterdir() if p.is_file()}, indent=2))
    command = ["iverilog", "-g2012", "-Wall", "-I", ".", "-s", "tb_starlink_pss_product_sealed_interface",
               "-o", "sim.vvp", *[Path(n).name for n in NAMES if not n.endswith(".svh")]]
    p = subprocess.run(command, cwd=path, env=clean_env(), capture_output=True, text=True, timeout=30, check=False)
    (path / "compile.log").write_text(p.stdout + p.stderr)
    (path / "compile.json").write_text(json.dumps({"command": command, "exit": p.returncode}))
    assert p.returncode == 0 and not re.search(r"(?im)^.*error:", p.stderr), p.stderr
    return path


@pytest.fixture(scope="module")
def compiled(tmp_path_factory):
    return build(tmp_path_factory.mktemp("interface") / "original")


def run(path, kind=0, bit=0, target=37):
    command = ["vvp", "sim.vvp", f"+CASE={kind}", f"+BIT={bit}", f"+TARGET={target}"]
    p = subprocess.run(command, cwd=path, env=clean_env(), capture_output=True, text=True, timeout=30, check=False)
    log = p.stdout + p.stderr
    key = f"kind-{kind}-bit-{bit}-target-{target}"
    (path / f"{key}.log").write_text(log)
    (path / f"{key}.json").write_text(json.dumps({"command": command, "exit": p.returncode}))
    if p.returncode == 0:
        assert not re.search(r"(?im)^(?:ERROR|FATAL|FAIL)(?::|\b)", log), "EXIT_ZERO_ERROR_RECEIPT " + log
    return p.returncode, log


def test_complete_eight_lease_lifetime(compiled):
    code, log = run(compiled)
    assert code == 0 and "PRODUCT_ADAPTER_PASS case=0 jobs=8" in log, log
    assert "PRODUCT_INTERFACE_ORDER_COUNTS admissions=8 completions=8" in log, log


@pytest.mark.parametrize("old,new", [
    ("iface_completions=iface_completions+1;", "iface_completions=iface_completions;"),
    ('if(kind==0)$display("PRODUCT_INTERFACE_ORDER_COUNTS',
     'if(kind==0)$display("ERROR: injected late receipt failure");\n    if(kind==0)$display("PRODUCT_INTERFACE_ORDER_COUNTS'),
])
def test_exit_zero_missing_count_and_late_error_receipts_rejected(tmp_path, old, new):
    path = build(tmp_path / "receipt_mutant", ("product_sealed_interface_cases.svh", old, new))
    with pytest.raises(AssertionError, match="EXIT_ZERO_ERROR_RECEIPT"):
        run(path)


# Literal original cases/assertions execute against the additive primitive too.
# This does not replace the separate immutable848 repeat.
ORIGINAL_CASES = (
    [(1, 0, t) for t in (0, 37, 511)] + [(2, 0, 37), (9, 0, 37), (12, 0, 37)] +
    [(3, b, 37) for b in range(8)] +
    [(4, b, t) for b in range(70) for t in (0, 37, 511)] +
    [(5, b, t) for b in range(75) for t in (3, 37, 511)] +
    [(5, b, t) for b in (0, 69, 74) for t in range(3)] +
    [(6, b, t) for b in range(8) for t in range(4)] +
    [(7, 0, t) for t in (0, 37, 511)] + [(8, 74, t) for t in range(3)] +
    [(11, b, t) for b in range(2) for t in range(3)] +
    [(13, b, t) for b in range(2) for t in (0, 37, 511)]
)


@pytest.mark.parametrize("kind,bit,target", ORIGINAL_CASES)
def test_original_composed_cases_with_real_qualified_order_assertions(compiled, kind, bit, target):
    code, log = run(compiled, kind, bit, target)
    marker = "PRODUCT_ADAPTER_PASS" if kind in (2, 9) else (
        "PRODUCT_ADAPTER_RESET_PASS" if kind == 11 else (
        "PRODUCT_ADAPTER_ONSET_PASS" if kind == 8 else "PRODUCT_ADAPTER_NEGATIVE_PASS"))
    assert code == 0 and marker in log, log


@pytest.mark.parametrize("bit", [0, 69, 74])
def test_good_capacity_and_matured_bad_stalled_verdict(compiled, bit):
    code, log = run(compiled, 109, bit)
    assert code == 0 and "PRODUCT_INTERFACE_CAPACITY_VERDICT_PASS" in log, log


@pytest.mark.parametrize("bit", range(3))
def test_raw_offer_current_fault_on_ack_and_release(compiled, bit):
    code, log = run(compiled, 110, bit)
    assert code == 0 and "PRODUCT_INTERFACE_RAW_BOUNDARY_PASS" in log, log


@pytest.mark.parametrize("bit,phase", [(0, 0), (1, 0), (0, 1), (1, 1), (2, 1)])
def test_forged_qualified_pulses_capture_reject_and_explicit_reason_latency(compiled, bit, phase):
    code, log = run(compiled, 111, bit, phase)
    assert code == 0 and "PRODUCT_INTERFACE_QUALIFIED_DIAGNOSTIC_PASS" in log, log


def test_default_off_public_interface_stays_inert(tmp_path):
    path = build(tmp_path / "default", parameter="0")
    code, log = run(path, 10)
    assert code == 0 and "PRODUCT_ADAPTER_DEFAULT_INERT_PASS" in log, log


@pytest.mark.parametrize("value", ["-1", "2", "32'bx", "32'bz"])
def test_additive_issuer_parameter_fail_closed(tmp_path, value):
    path = build(tmp_path / "invalid", parameter=value)
    code, log = run(path)
    assert code != 0 and "SEALED_PRODUCT_ADAPTER must be zero or one" in log, log


@pytest.mark.parametrize("value", ["-1", "2", "32'bx", "32'bz"])
def test_additive_reader_parameter_fail_closed(tmp_path, value):
    path = build(tmp_path / "invalid", ("starlink_pss_product_sealed_interface.v",
        ".CHECKED_PRODUCT_READ(1)", f".CHECKED_PRODUCT_READ({value})"))
    code, log = run(path)
    assert code != 0 and "CHECKED_PRODUCT_READ must be zero or one" in log, log


@pytest.mark.parametrize("target", [37, 511])
def test_actual_exported_ready_finite_hold(compiled, target):
    code, log = run(compiled, 100, target=target)
    marker = "PRODUCT_INTERFACE_NEGATIVE_PASS kind=100" if target == 37 else "PRODUCT_INTERFACE_FINAL_STALL_PASS"
    assert code == 0 and marker in log, log
    if target == 511:
        assert "PRODUCT_ADAPTER_PASS case=100 jobs=1" in log, log


@pytest.mark.parametrize("bit", range(3))
def test_closed_and_unknown_raw_offers_survive_ready_zero(compiled, bit):
    code, log = run(compiled, 101, bit)
    assert code == 0 and "PRODUCT_INTERFACE_NEGATIVE_PASS kind=101" in log, log


@pytest.mark.parametrize("bit", [0, 69, 74])
def test_admission_and_checked_head_are_independent_register_sources(compiled, bit):
    code, log = run(compiled, 102, bit)
    assert code == 0 and "PRODUCT_INTERFACE_SNAPSHOT_PASS kind=102" in log, log


@pytest.mark.parametrize("kind,bit", [(103, 0), (105, 0)] + [(104, n) for n in range(8)])
def test_post_ack_receipt_checked_head_and_current_health(compiled, kind, bit):
    code, log = run(compiled, kind, bit)
    assert code == 0 and "PRODUCT_INTERFACE_SNAPSHOT_PASS" in log, log


def test_wrong_phase_then_restored_handoff(compiled):
    code, log = run(compiled, 106)
    assert code == 0 and "PRODUCT_ADAPTER_PASS case=106 jobs=1" in log, log


@pytest.mark.parametrize("bit", range(5))
def test_fresh_raw_orphan_on_exact_guard_ack_edge(compiled, bit):
    code, log = run(compiled, 107, bit)
    assert code == 0 and "PRODUCT_INTERFACE_ACK_ORPHAN_PASS" in log, log


@pytest.mark.parametrize("bit", range(5))
@pytest.mark.parametrize("boundary", [0, 1])
def test_orphan_after_ack_at_receipt_capture_and_consume(compiled, bit, boundary):
    code, log = run(compiled, 108, bit, boundary)
    assert code == 0 and "PRODUCT_INTERFACE_RECEIPT_ORPHAN_PASS" in log, log


@pytest.mark.parametrize("mutation,kind,bit,target,marker", [
    (("starlink_pss_product_sealed_interface.v", "producer_reference && !final_taken && product_ready)",
      "producer_reference && !final_taken)"), 100, 0, 511, "PRODUCT_LOGICAL_TAKE_DIVERGED"),
    (("starlink_pss_product_sealed_interface.v", ".input_valid(product_valid), .input_offer_new",
      ".input_valid(product_valid && product_ready), .input_offer_new"), 101, 1, 37, "INTERFACE_RAW_OFFER_MASKED"),
    (("starlink_pss_product_sealed_interface.v", "assign admitted_metadata = expected_metadata;",
      "assign admitted_metadata = queue_metadata;"), 102, 74, 37, "INTERFACE_ADMISSION_HEAD_ALIAS"),
    (("starlink_pss_product_sealed_interface.v", "assign admitted_lease = lease_reference;",
      "assign admitted_lease = read_head_lease;"), 102, 0, 37, "INTERFACE_ADMISSION_HEAD_ALIAS"),
    (("starlink_pss_product_sealed_interface.v", "epoch_resetn && handoff_seen && published_reference &&",
      "epoch_resetn && handoff && published_reference &&"), 103, 0, 37, "INTERFACE_ACK_HEAD_BOUNDARY_MISSING"),
    (("starlink_pss_checked_product_read_interface.v", "count!=0 && occupied[head] && good[head];",
      "count!=0 && occupied[head];"), 105, 0, 37, "INTERFACE_UNCHECKED_HEAD_VISIBLE"),
    (("starlink_pss_product_sealed_interface.v", "    forward_phase && !fault;",
      "    !fault;"), 106, 0, 37, "INTERFACE_WRONG_PHASE_HANDOFF"),
    (("product_sealed_interface_cases.svh", "actor_private_start && !actor_epoch_fault;",
      "actor_private_start;"), 108, 0, 1, "INTERFACE_RECEIPT_EMITTED_START_ESCAPE"),
    (("starlink_pss_product_sealed_interface.v", "forward_phase && !fault;",
      "forward_phase && direct_clean && !fault;"), 109, 74, 37, "INTERFACE_CAPACITY_VERDICT_BOUNDARY_MISSING"),
    (("starlink_pss_product_sealed_interface.v", "queue_validation_fault || producer_verdict_fault_now;",
      "reader_offer_fault_now || producer_verdict_fault_now;"), 109, 74, 37, "INTERFACE_CAPACITY_VERDICT_BOUNDARY_MISSING"),
    (("starlink_pss_product_sealed_interface.v", "queue_validation_fault || producer_verdict_fault_now;",
      "reader_token_fault_now || producer_verdict_fault_now;"), 110, 0, 37, "INTERFACE_RAW_OFFER_BOUNDARY_ESCAPE"),
    (("starlink_pss_product_sealed_interface.v", "admission && !invalid_admission && direct_clean",
      "admission && direct_clean"), 111, 0, 0, "INTERFACE_FORGED_CAPTURE_OR_REASON_FAILURE"),
    (("starlink_pss_product_sealed_interface.v", "forward_completion && !invalid_completion",
      "forward_completion"), 111, 1, 1, "INTERFACE_FORGED_CAPTURE_OR_REASON_FAILURE"),
])
def test_executed_interface_mutants(tmp_path, mutation, kind, bit, target, marker):
    path = build(tmp_path / "mutant", mutation)
    code, log = run(path, kind, bit, target)
    assert code != 0 and marker in log, log


@pytest.mark.parametrize("name,new,old,patch_name", [
    ("reader", "starlink_pss_checked_product_read_interface.v", "starlink_pss_checked_product_read.v", "reader.patch"),
    ("issuer", "starlink_pss_product_sealed_interface.v", "starlink_pss_product_sealed_adapter.v", "issuer.patch"),
    ("bench", "tb/tb_starlink_pss_product_sealed_interface.sv", "tb/tb_starlink_pss_product_sealed_adapter.sv", "bench.patch"),
])
def test_whole_literal_inverse(tmp_path, name, new, old, patch_name):
    source = tmp_path / "source"
    shutil.copyfile(ACQ / new, source)
    patch = Path(__file__).with_name("product_interface_inverse") / patch_name
    p = subprocess.run(["patch", "-R", "--batch", "--fuzz=0", "-i", str(patch)],
                       cwd=tmp_path, env=clean_env(), capture_output=True, text=True, check=False)
    (tmp_path / "inverse.log").write_text(p.stdout + p.stderr)
    assert p.returncode == 0 and source.read_bytes() == (ACQ / old).read_bytes(), (name, p.stdout, p.stderr)


@pytest.mark.parametrize("new,old,patch_name", [
    ("starlink_pss_checked_product_read_interface.v", "starlink_pss_checked_product_read.v", "reader.patch"),
    ("starlink_pss_product_sealed_interface.v", "starlink_pss_product_sealed_adapter.v", "issuer.patch"),
    ("tb/tb_starlink_pss_product_sealed_interface.sv", "tb/tb_starlink_pss_product_sealed_adapter.sv", "bench.patch"),
])
def test_whole_inverse_rejects_unreviewed_body_addition(tmp_path, new, old, patch_name):
    source = tmp_path / "source"
    source.write_bytes((ACQ / new).read_bytes().replace(b"endmodule", b"wire unreviewed_extra = 1'b0;\nendmodule"))
    patch = Path(__file__).with_name("product_interface_inverse") / patch_name
    p = subprocess.run(["patch", "-R", "--batch", "--fuzz=0", "-i", str(patch)],
                       cwd=tmp_path, env=clean_env(), capture_output=True, text=True, check=False)
    (tmp_path / "inverse-mutant.log").write_text(p.stdout + p.stderr)
    assert p.returncode != 0 or source.read_bytes() != (ACQ / old).read_bytes()


def test_no_added_primitive_state_declarations():
    for new, old in (("starlink_pss_product_sealed_interface.v", "starlink_pss_product_sealed_adapter.v"),
                     ("starlink_pss_checked_product_read_interface.v", "starlink_pss_checked_product_read.v")):
        declarations = r"(?m)^\s*reg\s+[^;]+;"
        assert re.findall(declarations, (ACQ / new).read_text()) == re.findall(declarations, (ACQ / old).read_text())


def test_complete_graph_and_raw_metadata_cone_exclusion(compiled):
    source = (compiled / "sim.vvp").read_text()
    graph, names = parse(source)
    cycle = first_cycle(graph)
    assert cycle is None, "COMBINATIONAL_CYCLE " + repr(cycle)
    raw = set().union(*(graph[n] for n in names["offered_metadata"]))
    cones = {}
    for fence in ("publication", "handoff_valid", "core_valid", "lease_release"):
        cone = ancestors(graph, names[fence])
        assert not raw.intersection(cone), fence
        cones[fence] = len(cone)
    (compiled / "complete-graph.json").write_text(json.dumps({"nodes": len(graph),
        "LS_nodes": sum(n.startswith("LS_") for n in graph), "cycles": 0,
        "cones": cones, "source_sha256": hashlib.sha256(source.encode()).hexdigest()}, indent=2))


def test_frozen_848_graph_false_negative_is_preserved_and_rejected(tmp_path):
    from tests.starlink_oracle.test_product_sealed_adapter import compile_case
    path = compile_case(tmp_path / "frozen848")
    source = (path / "sim.vvp").read_text()
    legacy, _ = parse(source, legacy=True)
    complete, _ = parse(source)
    assert len(legacy) == 3123 and first_cycle(legacy) is None
    assert len(complete) == 3159 and first_cycle(complete)
    (path / "graph-correction.json").write_text(json.dumps({"legacy_nodes": len(legacy),
        "complete_nodes": len(complete), "missed_cycle": first_cycle(complete)}, indent=2))


@pytest.mark.parametrize("source,marker", [
    ("L_0xa .functor BUF 1, LS_0xb_0_4;\n", "UNRESOLVED_REFERENCES"),
    ("L_0xa .unreviewed 1, C4<0>;\n", "UNKNOWN_OPERATION"),
])
def test_graph_fail_closed(source, marker):
    with pytest.raises(ValueError, match=marker):
        parse(source)


def test_graph_ls_suffix_cycle_and_acyclic_controls():
    source = "L_0xa .functor OR 1, LS_0xb_0_4;\nLS_0xb_0_4 .concat [1], L_0xa;\n"
    assert first_cycle(parse(source)[0]) and first_cycle(parse(source, legacy=True)[0]) is None
    assert first_cycle(parse("L_0xa .functor BUF 1, C4<0>;\n")[0]) is None


@pytest.mark.parametrize("mutation", [
    ("tb_starlink_pss_product_sealed_interface.sv", ".external_fault_now(adapter_fault || dut.handoff_fault_now)",
     ".external_fault_now(adapter_fault || dut.handoff_fault_now || dut.issuer_fault_events_now[0])"),
    ("tb_starlink_pss_product_sealed_interface.sv", ".completed_input_fault_now(adapter_fault || dut.handoff_fault_now)",
     ".completed_input_fault_now(adapter_fault || dut.handoff_fault_now || dut.issuer_fault_events_now[1])"),
    ("starlink_pss_product_sealed_interface.v", "{(issuer_bank_current || |reasons || |reader_reasons),7'b0}",
     "{(issuer_bank_current || extra_bank_offer || |reasons || |reader_reasons),7'b0}"),
    ("starlink_pss_product_sealed_interface.v", "{(issuer_bank_current || |reasons || |reader_reasons),7'b0}",
     "{(issuer_bank_current || reader_offer_fault_now || |reasons || |reader_reasons),7'b0}"),
    ("tb_starlink_pss_product_sealed_interface.sv", "{product_overflow,closed_raw_fault,guard_fault,consumer_duplicate,consumer_fault,3'b0}",
     "{product_overflow,closed_raw_fault,guard_fault,consumer_duplicate,consumer_fault,consumer_beat,2'b0}"),
    ("tb_starlink_pss_product_sealed_interface.sv", "{product_overflow,closed_raw_fault,guard_fault,consumer_duplicate,consumer_fault,3'b0}",
     "{product_overflow,closed_raw_fault,guard_fault,consumer_duplicate,consumer_fault,guard.fault_now,2'b0}"),
])
def test_graph_rejects_individual_backedges_from_acyclic_base(tmp_path, mutation):
    path = build(tmp_path / "backedge", mutation)
    graph, _ = parse((path / "sim.vvp").read_text())
    assert first_cycle(graph), mutation
    (path / "backedge-cycle.json").write_text(json.dumps({"mutation": mutation, "cycle": first_cycle(graph)}, indent=2))

"""Two additive integration seams; offline actors, never vendor/top qualification."""
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.product_interface_graph import ancestors, first_cycle, parse
from tests.starlink_oracle.test_checked_product_read import clean_env
from tests.starlink_oracle.test_product_sealed_interface import ORIGINAL_CASES

ROOT = Path(__file__).resolve().parents[2]
ACQ = ROOT / "hdl/library/starlink_pss_acquisition"
BANK = "starlink_pss_epoch_sealed_publication_bank.v"
ISSUER = "starlink_pss_product_sealed_publication_interface.v"
BANK_TB = "tb_starlink_pss_publication_bank.sv"
IF_TB = "tb_starlink_pss_product_sealed_interface.sv"
BASE = ["starlink_pss_epoch_sealed_bank.v", "starlink_pss_block_mailbox.v", BANK]


def replace_once(source, old, new):
    assert source.count(old) == 1, old
    return source.replace(old, new)


def build(path, kind="bank", option="1", mutation=None):
    path.mkdir()
    names = BASE + (["tb/" + BANK_TB] if kind == "bank" else [
        ISSUER, "starlink_pss_checked_product_read_interface.v",
        "starlink_pss_realtime_input_guard.v", "starlink_pss_realtime_result_guard.v",
        "starlink_pss_spectrum_product.v", "tb/" + IF_TB,
        "tb/product_sealed_interface_cases.svh", "tb/product_publication_seam_cases.svh"])
    for name in names:
        shutil.copyfile(ACQ / name, path / Path(name).name)
    if kind == "bank":
        bench = path / BANK_TB
        bench.write_text(replace_once(bench.read_text(), "parameter integer OPTION=1",
                                     f"parameter integer OPTION={option}"))
        top = BANK_TB.removesuffix(".sv")
    else:
        bench = path / IF_TB
        bench.write_text(interface_bench(bench.read_text(), option))
        top = IF_TB.removesuffix(".sv")
    if mutation:
        name, old, new = mutation
        file = path / name
        file.write_text(replace_once(file.read_text(), old, new))
    for helper in (Path(__file__), Path(__file__).with_name("product_interface_graph.py"),
                   Path(__file__).with_name("test_product_sealed_interface.py"),
                   Path(__file__).with_name("test_checked_product_read.py")):
        shutil.copyfile(helper, path / helper.name)
    (path / "sources.json").write_text(json.dumps({p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in path.iterdir() if p.is_file()}, indent=2))
    command = ["iverilog", "-g2012", "-Wall", "-I", ".", "-s", top, "-o", "sim.vvp",
               *[Path(n).name for n in names if not n.endswith(".svh")]]
    p = subprocess.run(command, cwd=path, env=clean_env(), capture_output=True, text=True, timeout=30, check=False)
    (path / "compile.log").write_text(p.stdout + p.stderr)
    (path / "compile.json").write_text(json.dumps({"command": command, "exit": p.returncode}))
    assert p.returncode == 0, p.stderr
    return path


def interface_changes(option):
    return [
        ("starlink_pss_product_sealed_interface #(.SEALED_PRODUCT_ADAPTER(ENABLED)) dut (",
         f"starlink_pss_product_sealed_publication_interface #(.SEALED_PRODUCT_ADAPTER(ENABLED), .SEPARATE_PRODUCT_SEAMS({option})) dut ("),
        (".product_valid(product_valid),.product_ready(product_ready),.product_data",
         ".sampled_product_ready(sampled_ready_for_dut),.publication_faults(publication_faults),\n    .product_valid(product_valid),.product_ready(product_ready),.product_data"),
        (".output_valid(product_valid),.output_ready(product_ready)",
         ".output_valid(product_valid),.output_ready(actual_product_ready)"),
        ("product_take !== (product_valid && product_ready)",
         "product_take !== (product_valid && actual_product_ready)"),
        (".external_fault_now(adapter_fault || dut.handoff_fault_now)",
         ".external_fault_now(adapter_fault || dut.handoff_fault_now || (dut.SEPARATE_PRODUCT_SEAMS && publication_faults !== 8'b0))"),
        (".completed_input_fault_now(adapter_fault || dut.handoff_fault_now)",
         ".completed_input_fault_now(adapter_fault || dut.handoff_fault_now || (dut.SEPARATE_PRODUCT_SEAMS && publication_faults !== 8'b0))"),
        ('  `include "product_sealed_interface_cases.svh"',
         '  `include "product_sealed_interface_cases.svh"\n  `include "product_publication_seam_cases.svh"'),
        ("      interface_after_wait();", "      interface_after_wait();\n      seam_after_wait();"),
    ]


def interface_bench(source, option="1"):
    for old, new in interface_changes(option):
        source = replace_once(source, old, new)
    return source


def run(path, kind=0, bit=0, target=0, reset=-1):
    command = ["vvp", "sim.vvp", f"+CASE={kind}", f"+BIT={bit}", f"+TARGET={target}"]
    if reset >= 0:
        command.append(f"+RESET_SIDE={reset}")
    p = subprocess.run(command, cwd=path, env=clean_env(), capture_output=True, text=True, timeout=30, check=False)
    log = p.stdout + p.stderr
    stem = f"case-{kind}-bit-{bit}-target-{target}"
    if reset >= 0:
        stem += f"-reset-{reset}"
    (path / (stem + ".log")).write_text(log)
    (path / (stem + ".json")).write_text(json.dumps({"command": command, "exit": p.returncode}))
    if not p.returncode:
        assert not re.search(r"(?im)^(?:ERROR|FATAL|FAIL)(?::|\b)", log), log
    return p.returncode, log


def verify_bank_receipt(log, phase, bit, value, option=1, reset=-1):
    marker = "PUBLICATION_BANK_CERT_PASS" if phase == 3 else (
        "PUBLICATION_BANK_REARM_PASS" if phase == 5 else "PUBLICATION_BANK_PASS")
    prefix = f"{marker} option={option} phase={phase} bit={bit} value={value} checks="
    suffix = r"(\d+)" if phase in (3, 5) else r"(\d+) reads=(\d+) reasons=([0-9a-f]{4})"
    rows = re.findall(r"(?m)^" + re.escape(prefix) + suffix + "$", log)
    terminals = re.findall(r"(?m)^PUBLICATION_BANK_(?!RESET_PASS).*$", log)
    assert len(rows) == len(terminals) == 1, "BANK_PROFILE_RECEIPT " + log
    checks = int(rows[0] if phase in (3, 5) else rows[0][0])
    assert checks > 0, "BANK_COUNT_RECEIPT " + log
    resets = re.findall(r"(?m)^PUBLICATION_BANK_RESET_PASS side=(\d+)$", log)
    assert resets == ([] if reset < 0 else [str(reset)]), "BANK_RESET_RECEIPT " + log
    assert not re.search(r"(?im)^(?:ERROR|FATAL|FAIL)(?::|\b)", log), log


def verify_seam_receipt(log, kind, bit, target):
    terminals = re.findall(r"(?m)^PRODUCT_SEAM_.*$", log)
    if kind == 200:
        expected = [f"PRODUCT_SEAM_READY_HOLD target={target} edges=4"]
        if target == 37:
            expected.append("PRODUCT_SEAM_INTERIOR_QUARANTINE_PASS")
        else:
            assert log.count("PRODUCT_ADAPTER_PASS case=200 jobs=1") == 1, "SEAM_LIFETIME_RECEIPT " + log
        assert terminals == expected, "SEAM_PROFILE_RECEIPT " + log
    elif kind in (201, 202, 204, 205):
        assert terminals == [f"PRODUCT_SEAM_BOUNDARY_PASS kind={kind} phase={target} bitvalue={bit}"], "SEAM_PROFILE_RECEIPT " + log
    elif kind == 203:
        assert terminals == ["PRODUCT_SEAM_OVERADVERTISED_READY_PASS"], "SEAM_PROFILE_RECEIPT " + log
    elif kind == 206:
        assert len(terminals) == 1, "SEAM_PROFILE_RECEIPT " + log
        row = re.fullmatch(r"PRODUCT_SEAM_REAL_CERTIFICATE_PASS received=(\d+)", terminals[0])
        assert row and int(row[1]) > 0, "SEAM_CERTIFICATE_RECEIPT " + log
    else:
        raise AssertionError("UNKNOWN_SEAM_PROFILE")
    assert not re.search(r"(?im)^(?:ERROR|FATAL|FAIL)(?::|\b)", log), log


@pytest.fixture(scope="module")
def bank(tmp_path_factory):
    return build(tmp_path_factory.mktemp("bank") / "enabled")


@pytest.fixture(scope="module")
def bank_default(tmp_path_factory):
    return build(tmp_path_factory.mktemp("bank") / "disabled", option="0")


@pytest.fixture(scope="module")
def interface(tmp_path_factory):
    return build(tmp_path_factory.mktemp("interface") / "enabled", kind="interface")


@pytest.fixture(scope="module")
def interface_default(tmp_path_factory):
    return build(tmp_path_factory.mktemp("interface") / "disabled", kind="interface", option="0")


@pytest.mark.parametrize("phase", range(6))
@pytest.mark.parametrize("bit", range(8))
@pytest.mark.parametrize("value", range(3))
def test_bank_current_publication_categories_and_observation_window(bank, phase, bit, value):
    code, log = run(bank, phase, bit, value)
    assert code == 0, log
    verify_bank_receipt(log, phase, bit, value)


@pytest.mark.parametrize("phase", range(7))
def test_bank_disabled_whole_state_equivalence(bank_default, phase):
    code, log = run(bank_default, phase, 7, 2)
    assert code == 0, log
    verify_bank_receipt(log, phase, 7, 2, option=0)


@pytest.mark.parametrize("side", range(2))
@pytest.mark.parametrize("phase", (0, 1, 2))
def test_publication_fault_one_sided_reset(bank, side, phase):
    code, log = run(bank, phase, 7, 2, reset=side)
    assert code == 0, log
    verify_bank_receipt(log, phase, 7, 2, reset=side)


def test_interface_healthy_eight_leases(interface):
    code, log = run(interface)
    assert code == 0 and "PRODUCT_ADAPTER_PASS case=0 jobs=8" in log, log
    assert "PRODUCT_INTERFACE_ORDER_COUNTS admissions=8 completions=8" in log, log


@pytest.mark.parametrize("kind,bit,target", ORIGINAL_CASES)
def test_literal_old_composed_cases(interface, kind, bit, target):
    code, log = run(interface, kind, bit, target)
    assert code == 0 and "PASS" in log, log


@pytest.mark.parametrize("kind,bit,target", [(0, 0, 0)] + ORIGINAL_CASES)
def test_disabled_old_cases_and_all_changed_predicates(interface_default, kind, bit, target):
    code, log = run(interface_default, kind, bit, target)
    assert code == 0 and "PASS" in log, log


def test_fixture_full_inverse():
    original = (ACQ / "tb" / IF_TB).read_text()
    assert hashlib.sha256(original.encode()).hexdigest() == "3c13624cef0dc13668e4a47d8e85e3b5c1b889e6b28a192c6fd9f28446b5a6fc"
    for option in ("0", "1"):
        result = interface_bench(original, option)
        for old, new in reversed(interface_changes(option)):
            result = replace_once(result, new, old)
        assert result == original


SEAM_CASES = [(200, 0, t) for t in (37, 511)] + [(201, b, t) for b in range(2) for t in (37, 511)] + [
    (202, b, 0) for b in range(3)] + [(203, 0, 0)] + [(204, b, t) for b in range(24) for t in range(2)] + [
    (205, b, 0) for b in range(24)] + [(206, 0, 0)]


@pytest.mark.parametrize("kind,bit,target", SEAM_CASES)
def test_new_actual_ready_and_publication_boundaries(interface, kind, bit, target):
    code, log = run(interface, kind, bit, target)
    assert code == 0, log
    verify_seam_receipt(log, kind, bit, target)


def graph_receipt(path):
    graph, names = parse((path / "sim.vvp").read_text())
    cycle = first_cycle(graph)
    receipt = {"nodes": len(graph), "LS": sum(n.startswith("LS_") for n in graph), "cycle": cycle}
    (path / "graph.json").write_text(json.dumps(receipt, indent=2))
    return graph, names, cycle


def net_driver_roots(graph, names, name):
    # VVP consumers reference a net's driver directly, not every named alias.
    # Do not expand to all fan-in: shared upstream state is not this bus route.
    assert names[name] and all(graph[node] for node in names[name])
    return set().union(*(graph[node] for node in names[name]))


def test_complete_publication_coupled_graph_is_acyclic(interface):
    graph, names, cycle = graph_receipt(interface)
    assert not cycle, cycle
    assert sum(n.startswith("LS_") for n in graph) > 0
    source = net_driver_roots(graph, names, "publication_faults")
    for sink in ("bank_live", "output_valid", "certificate_ready", "certificate_take", "lease_release_ready", "lease_release", "product_ready"):
        assert not (ancestors(graph, names[sink]) & source), sink
    for sink in ("checked_seal", "publish"):
        assert ancestors(graph, names[sink]) & source, sink


@pytest.mark.parametrize("connected", [False, True])
def test_named_net_alias_connected_and_disconnected_route_witness(connected):
    text = '''v0x1_0 .var "state", 0 0;
v0x2_0 .var "other_state", 0 0;
L_0x3 .functor BUFZ 1, v0x1_0;
v0x4_0 .net "publication_faults", 0 0, L_0x3;  1 drivers
v0x5_0 .net "publication_faults", 0 0, L_0x3;  alias, 1 drivers
'''
    # Disconnected still shares the upstream state: broad ancestry would be
    # a false positive, while the exact bus driver remains absent.
    text += "L_0x6 .functor BUFZ 1, " + ("L_0x3" if connected else "v0x1_0") + ";\n"
    text += 'v0x7_0 .net "sink", 0 0, L_0x6;  1 drivers\n'
    graph, names = parse(text)
    cone = ancestors(graph, names["sink"])
    # Retained negative control: alias-ID membership misses even connected.
    assert not cone.intersection(names["publication_faults"])
    assert bool(cone & net_driver_roots(graph, names, "publication_faults")) == connected


@pytest.mark.parametrize("mutation", [
    (ISSUER, "wire [7:0] bank_live = current_faults |", "wire [7:0] bank_live = current_faults | publication_faults |"),
    (BANK, "wire local_current_clean = errors_now == 0;", "wire local_current_clean = errors_now == 0 && publication_faults === 8'b0;"),
    (BANK, "assign output_valid = running && armed", "assign output_valid = publication_only_clean && running && armed"),
])
def test_executed_restored_publication_backedges(tmp_path, mutation):
    path = build(tmp_path / "backedge", kind="interface", mutation=mutation)
    _, _, cycle = graph_receipt(path)
    assert cycle, "RESTORED_BACKEDGE_WAS_NOT_REJECTED"


@pytest.mark.parametrize("kind,value,marker", [
    (kind, value, marker) for kind, marker in (("bank", "PUBLICATION_ONLY_FAULTS"), ("interface", "SEPARATE_PRODUCT_SEAMS"))
    for value in ("-1", "2", "32'bx", "32'bz")])
def test_new_parameters_fail_closed(tmp_path, kind, value, marker):
    path = build(tmp_path / "invalid", kind=kind, option=value)
    code, log = run(path)
    assert code != 0 and marker + " must be zero or one" in log, log


@pytest.mark.parametrize("which,new,old,expected", [
    ("bank", BANK, "starlink_pss_epoch_sealed_bank.v", "d9c2382f9087ccd2088fa5a5d3fed5c6fe885359d6d4c367ed2ea81ce099d9f6"),
    ("issuer", ISSUER, "starlink_pss_product_sealed_interface.v", "5e060a23903641c8f0c0ec7a0afae22428d1ad15829d1af9985ca0a662de5669")])
def test_strict_whole_body_inverse_and_zero_new_state(tmp_path, which, new, old, expected):
    baseline = (ACQ / old).read_bytes()
    assert hashlib.sha256(baseline).hexdigest() == expected
    source = tmp_path / "source"
    shutil.copyfile(ACQ / new, source)
    patch = Path(__file__).with_name("product_publication_inverse") / (which + ".patch")
    p = subprocess.run(["patch", "-R", "--batch", "--fuzz=0", "-i", str(patch)],
                       cwd=tmp_path, env=clean_env(), capture_output=True, text=True, check=False)
    (tmp_path / "inverse.log").write_text(p.stdout + p.stderr)
    assert p.returncode == 0 and source.read_bytes() == baseline, (p.stdout, p.stderr)
    registers = lambda text: re.findall(r"\breg\s+[^;]+;", text)
    assert registers((ACQ / new).read_text()) == registers(baseline.decode())


@pytest.mark.parametrize("which,new,old", [
    ("bank", BANK, "starlink_pss_epoch_sealed_bank.v"),
    ("issuer", ISSUER, "starlink_pss_product_sealed_interface.v")])
def test_inverse_rejects_unreviewed_body(tmp_path, which, new, old):
    source = tmp_path / "source"
    source.write_text((ACQ / new).read_text().replace("endmodule", "wire unreviewed_change=1;\nendmodule"))
    patch = Path(__file__).with_name("product_publication_inverse") / (which + ".patch")
    p = subprocess.run(["patch", "-R", "--batch", "--fuzz=0", "-i", str(patch)],
                       cwd=tmp_path, env=clean_env(), capture_output=True, text=True, check=False)
    (tmp_path / "inverse-negative.log").write_text(p.stdout + p.stderr)
    assert p.returncode != 0 or source.read_bytes() != (ACQ / old).read_bytes()


@pytest.mark.parametrize("mutation,kind,bit,target,marker", [
    ((BANK, "local_current_clean && publication_only_clean;", "local_current_clean;"), 0, 7, 0, "PUBLICATION_CURRENT_VETO_MISSING"),
    ((BANK, "request_toggle == acknowledge_sync[1] && publication_only_clean;", "request_toggle == acknowledge_sync[1];"), 1, 7, 0, "PUBLICATION_CURRENT_VETO_MISSING"),
    ((BANK, "reasons | errors_now | {publication_causes,8'b0}", "reasons | errors_now"), 1, 7, 0, "PUBLICATION_REASON_CAPTURE_MISSING"),
    ((BANK, "publication_faults[publication_cause] !== 1'b0", "publication_faults[publication_cause] === 1'b1"), 1, 7, 1, "PUBLICATION_CURRENT_VETO_MISSING"),
    ((BANK, "if (checked_seal) seal_q <= 1;", "if (full && check_valid[1] && check_last[1]) seal_q <= 1;"), 0, 7, 0, "PUBLICATION_INTERNAL_SEAL_BYPASS"),
    ((BANK, "if (publish) begin", "if (seal_q && certificate_seen && pipe_empty && !published_q) begin"), 1, 7, 0, "PUBLICATION_INTERNAL_PUBLISH_BYPASS"),
])
def test_bank_missing_current_reason_and_internal_state_mutants(tmp_path, mutation, kind, bit, target, marker):
    path = build(tmp_path / "mutant", mutation=mutation)
    code, log = run(path, kind, bit, target)
    assert code != 0 and marker in log, log


@pytest.mark.parametrize("mutation,kind,bit,target,marker", [
    ((ISSUER, "sampled_ready && product_ready)", "product_ready)"), 200, 0, 511, "SEAM_ACTUAL_READY_HOLD_FAILED"),
    ((ISSUER, "sampled_ready && product_ready)", "sampled_ready)"), 203, 0, 0, "SEAM_OVERADVERTISED_READY_PRIVATE_TAKE"),
    ((ISSUER, ".input_valid(product_valid),", ".input_valid(product_valid && sampled_ready),"), 202, 1, 0, "SEAM_RAW_CLOSED_OFFER_MASKED"),
    ((ISSUER, "wire sampled_ready_error = SEPARATE_PRODUCT_SEAMS", "wire sampled_ready_error = 1'b0 && SEPARATE_PRODUCT_SEAMS"), 201, 0, 37, "SEAM_UNKNOWN_READY_NOT_OBSERVED"),
    ((IF_TB, ".external_fault_now(adapter_fault || dut.handoff_fault_now || (dut.SEPARATE_PRODUCT_SEAMS && publication_faults !== 8'b0))",
      ".external_fault_now(adapter_fault || dut.handoff_fault_now)"), 205, 0, 0, "SEAM_CALLER_CURRENT_ACK_FENCE_MISSING"),
])
def test_interface_missing_fence_mutants(tmp_path, mutation, kind, bit, target, marker):
    path = build(tmp_path / "mutant", kind="interface", mutation=mutation)
    code, log = run(path, kind, bit, target)
    assert code != 0 and marker in log, log


@pytest.mark.parametrize("profile", ["bank", "seam"])
@pytest.mark.parametrize("mutation", ["missing", "wrong", "duplicate", "bare", "late_error", "zero_count"])
def test_receipt_missing_wrong_duplicate_and_exit_zero_error_rejected(bank, interface, profile, mutation):
    if profile == "bank":
        code, log = run(bank, 1, 7, 2)
        validator = lambda value: verify_bank_receipt(value, 1, 7, 2)
        token, wrong = "PUBLICATION_BANK_PASS", "PUBLICATION_BANK_OTHER_PASS"
    else:
        code, log = run(interface, 206)
        validator = lambda value: verify_seam_receipt(value, 206, 0, 0)
        token, wrong = "PRODUCT_SEAM_REAL_CERTIFICATE_PASS", "PRODUCT_SEAM_OTHER_PASS"
    assert code == 0
    validator(log)
    line = next(line for line in log.splitlines() if line.startswith(token))
    if mutation == "missing":
        changed = log.replace(line, "")
    elif mutation == "wrong":
        changed = log.replace(token, wrong)
    elif mutation == "duplicate":
        changed = log + line + "\n"
    elif mutation == "bare":
        changed = log.replace(line, token)
    elif mutation == "late_error":
        changed = log + "ERROR: deliberately late exit-zero failure\n"
    else:
        changed = re.sub(r"(checks|received)=\d+", r"\1=0", log)
    with pytest.raises(AssertionError):
        validator(changed)


def test_enabled_and_disabled_healthy_measured_lifetime_equal(interface, interface_default):
    traces = []
    for path in (interface, interface_default):
        code, log = run(path)
        assert code == 0 and log.count("PRODUCT_ADAPTER_PASS case=0 jobs=8") == 1, log
        traces.append(re.findall(r"(?m)^PRODUCT_ADAPTER_(?:JOB|LATENCY) .*$", log))
    assert len(traces[0]) == 16 and traces[0] == traces[1]


@pytest.mark.parametrize("old,new", [("option=1", "option=0"), ("phase=1", "phase=0"),
                                    ("bit=7", "bit=6"), ("value=2", "value=1")])
def test_bank_receipt_wrong_declared_arguments(bank, old, new):
    code, log = run(bank, 1, 7, 2)
    assert code == 0
    with pytest.raises(AssertionError, match="BANK_PROFILE_RECEIPT"):
        verify_bank_receipt(log.replace(old, new), 1, 7, 2)


@pytest.mark.parametrize("old,new", [("kind=205", "kind=204"), ("phase=0", "phase=1"),
                                    ("bitvalue=23", "bitvalue=22")])
def test_seam_receipt_wrong_declared_arguments(interface, old, new):
    code, log = run(interface, 205, 23, 0)
    assert code == 0
    with pytest.raises(AssertionError, match="SEAM_PROFILE_RECEIPT"):
        verify_seam_receipt(log.replace(old, new), 205, 23, 0)

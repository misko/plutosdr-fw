"""Additive real-controller integration; explicit control actor, NEVER vendor FFT."""
import ast
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.product_interface_graph import first_cycle, parse
from tests.starlink_oracle.test_checked_product_read import clean_env

ROOT = Path(__file__).resolve().parents[2]
ACQ = ROOT / "hdl/library/starlink_pss_acquisition"
TOP = "tb_starlink_pss_checked_product_top"
MODULES = ["fft_bank_owned_checked_product", "fft_bank_owned_product_fence",
           "realtime_checked_product_input_guard", "realtime_input_guard",
           "realtime_result_guard_observe", "realtime_result_guard",
           "checked_product_read_observe", "product_sealed_observe", "epoch_sealed_publication_bank",
           "block_mailbox", "product_fence_mailbox", "forward_kernel_join_read_ahead",
           "kernel_rom_read_ahead", "spectrum_product"]


def expected_actor_payload(kernel_text, fresh=False):
    """Independent integer complex multiply/ties-even for identity actor only."""
    def signed(value):
        return value - (1 << 18) if value & (1 << 17) else value

    def rounded(value):
        quotient, remainder = divmod(value, 1 << 18)
        quotient += remainder > (1 << 17) or (remainder == (1 << 17) and quotient % 2)
        return min((1 << 17) - 1, max(-(1 << 17), quotient)) & ((1 << 18) - 1)

    result = []
    for n, line in enumerate(kernel_text.splitlines()):
        word = int(line, 16)
        ki, kq = signed(word & ((1 << 18) - 1)), signed(word >> 18)
        i, q = n % 23 - 11, n % 17 - 8
        if fresh:
            i, q = i - 4096, q + 3072
        result.append(rounded(i * ki - q * kq) | (rounded(i * kq + q * ki) << 18))
    assert len(result) == 512
    return "".join(f"{word:09x}\n" for word in result)


def default_observer(source):
    """Literal old runtime field lists; no invalid-data exception in this actor."""
    lists = {}
    for statement in ast.parse(source).body:
        if isinstance(statement, ast.Assign) and isinstance(statement.value, ast.List):
            lists[statement.targets[0].id] = ast.literal_eval(statement.value)
    fields = lists["WRAPPER_FIELDS"] + ["result_guard." + x for x in lists["GUARD_FIELDS"]]
    fields += ["input_guard." + x for x in lists["INPUT_FIELDS"]]
    fields += ["joiner.kernel_rom." + x for x in lists["ROM_FIELDS"]]
    fields += [bank + "." + x for bank in ("source_bank", "product_bank", "output_bank") for x in lists["BANK_FIELDS"]]
    assert len(fields) == len(set(fields)) == 194
    statements = []
    for field in fields:
        candidate = field.replace("product_bank.", "original_product_bank.product_bank.")
        statements.append(f'    if(dut.{candidate} !== reference_top.{field}) $fatal(1,"CHECKED_TOP_DEFAULT_FIELD_CHANGED {field}");')
    return ("generate if(!ENABLED)begin : default_original_fields\n  integer checks=0;\n"
            "  always @(posedge fft_clk or negedge fft_clk)begin\n    #0.001;\n    checks=checks+1;\n" +
            "\n".join(statements) + "\n  end\nend endgenerate\n"), fields


def build(path, enabled=1, mutation=None, reference_purge=1, expect_cycle=False):
    path.mkdir()
    names = [f"starlink_pss_{name}.v" for name in MODULES] + [
        "tb/starlink_pss_fft512_control_actor.v", "tb/" + TOP + ".sv", "tb/upper_edge_pss_kernel_q17.mem"]
    for name in names:
        shutil.copyfile(ACQ / name, path / Path(name).name)
    if isinstance(enabled, str):
        bench = path / (TOP + ".sv")
        body = bench.read_text()
        assert body.count("parameter integer ENABLED=1,") == 1
        bench.write_text(body.replace("parameter integer ENABLED=1,", f"parameter integer ENABLED={enabled},"))
    (path / "actor_expected_product.mem").write_text(expected_actor_payload((path / "upper_edge_pss_kernel_q17.mem").read_text()))
    fresh_expected = expected_actor_payload((path / "upper_edge_pss_kernel_q17.mem").read_text(), fresh=True)
    (path / "actor_fresh_expected_product.mem").write_text(fresh_expected)
    assert sum(a != b for a, b in zip(fresh_expected.splitlines(), (path / "actor_expected_product.mem").read_text().splitlines(), strict=True)) == 512
    shutil.copyfile(ACQ / "prepare_exact_control_actual.py", path / "original_field_policy.py")
    assert hashlib.sha256((path / "original_field_policy.py").read_bytes()).hexdigest() == "3491798ccf8da4d145f6891653d8c799c598ac78b7afb9f9abf1afb59123a895"
    observer, fields = default_observer((path / "original_field_policy.py").read_text())
    (path / "checked_product_default_observer.svh").write_text(observer)
    (path / "default_fields.json").write_text(json.dumps(fields, indent=2))
    if mutation:
        name, old, new = mutation
        source = path / name
        text = source.read_text()
        assert text.count(old) == 1
        source.write_text(text.replace(old, new))
    for helper in (Path(__file__), Path(__file__).with_name("product_interface_graph.py"),
                   Path(__file__).with_name("test_checked_product_read.py")):
        shutil.copyfile(helper, path / helper.name)
    (path / "sources.json").write_text(json.dumps({x.name: hashlib.sha256(x.read_bytes()).hexdigest()
        for x in path.iterdir() if x.is_file()}, indent=2))
    command = ["iverilog", "-g2012", "-Wall", "-s", TOP,
               *([] if isinstance(enabled, str) else [f"-P{TOP}.ENABLED={enabled}"]), f"-P{TOP}.RESET_REFERENCE_PURGE={reference_purge}",
               "-o", "sim.vvp", *[Path(n).name for n in names if not n.endswith(".mem")]]
    p = subprocess.run(command, cwd=path, env=clean_env(), capture_output=True, text=True, timeout=30, check=False)
    (path / "compile.log").write_text(p.stdout + p.stderr)
    (path / "compile.json").write_text(json.dumps({"command": command, "exit": p.returncode}))
    assert p.returncode == 0 and not re.search(r"(?im)error:|implicit definition", p.stderr), p.stderr
    graph, _ = parse((path / "sim.vvp").read_text())
    cycle = first_cycle(graph)
    (path / "graph.json").write_text(json.dumps({"nodes": len(graph), "LS": sum(x.startswith("LS_") for x in graph), "cycle": cycle}, indent=2))
    assert bool(cycle) == expect_cycle, cycle
    return path


def run(path, kind=0, bit=0, target=0):
    command = ["vvp", "sim.vvp", f"+CASE={kind}", f"+BIT={bit}", f"+TARGET={target}"]
    p = subprocess.run(command, cwd=path, env=clean_env(), capture_output=True, text=True, timeout=30, check=False)
    log = p.stdout + p.stderr
    key = f"case-{kind}-bit-{bit}-target-{target}"
    (path / (key + ".log")).write_text(log)
    (path / (key + ".json")).write_text(json.dumps({"command": command, "exit": p.returncode}))
    return p.returncode, log


@pytest.mark.parametrize("enabled", [0, 1])
def test_four_complete_pairs_control_actor(tmp_path, enabled):
    path = build(tmp_path / "top", enabled)
    code, log = run(path)
    assert code == 0 and not re.search(r"(?im)^(ERROR|FATAL|FAIL)(:|\b)", log), log
    marker = f"CHECKED_PRODUCT_TOP_CONTROL_PASS enabled={enabled} compared=2048 starts=8"
    assert log.count(marker) == 1 and "control_actor_not_fft=1" in log, log
    rows = re.findall(r"^CHECKED_TOP_LATENCY job=(\d+) forward_start=(\d+) product_final=(\d+) seal=(\d+) publication=(\d+) ack=(\d+) inverse_start=(\d+) core_first=(\d+) core_last=(\d+) release=(\d+)$", log, re.MULTILINE)
    reference = re.findall(r"^CHECKED_TOP_REFERENCE_LATENCY job=(\d+) forward_start=(\d+) product_final=(\d+) inverse_start=(\d+) core_first=(\d+) core_last=(\d+)$", log, re.MULTILINE)
    assert len(reference) == 4
    if enabled:
        assert len(rows) == 4
        for row in rows:
            _, _, final, seal, pub, ack, start, first, last, release = map(int, row)
            assert (seal-final, pub-final, ack-pub, start-ack, first-start, last-first, release-last) == (2, 3, 10, 9, 3, 511, 1)
    else:
        assert len(json.loads((path / "default_fields.json").read_text())) == 194


@pytest.fixture(scope="module")
def integrated(tmp_path_factory):
    return build(tmp_path_factory.mktemp("integrated") / "top")


@pytest.mark.parametrize("target", [37, 511])
def test_actual_exported_ready(integrated, target):
    code, log = run(integrated, 1, target=target)
    assert code == 0 and "FATAL" not in log and "ERROR" not in log, log
    outcome = "quarantine" if target == 37 else "complete"
    assert len(re.findall(rf"^CHECKED_TOP_READY_PASS target={target} compared=\d+ outcome={outcome} control_actor_not_fft=1$", log, re.MULTILINE)) == 1, log


@pytest.mark.parametrize("kind,bit,target", [
    *[(2, bit, target) for bit in (0, 5, 68, 69, 70, 74) for target in range(5)],
    *[(3, bit, target) for bit in range(2) for target in range(5)],
    (4, 0, 4), (11, 0, 4),
    *[(kind, bit, target) for kind in (13, 14) for bit in (0, 69, 74) for target in (0, 4)],
    *[(5, bit, target) for bit in range(11) for target in (0, 5, 6, 7, 8, 9)],
])
def test_bound_head_and_current_faults(integrated, kind, bit, target):
    code, log = run(integrated, kind, bit, target)
    assert code == 0 and "FATAL" not in log and "ERROR" not in log, log
    expected_ack = 0 if target in (0, 7, 8, 9) else 1
    marker = f"CHECKED_TOP_REJECT_PASS kind={kind} bit={bit} target={target} starts=1 ack={expected_ack} releases=0 current=1 control_actor_not_fft=1"
    assert log.count(marker) == 1, log


@pytest.mark.parametrize("bit,target", [(bit, target) for bit in range(75) for target in (3, 37, 511)])
def test_all_raw_read_identity_bits_including_stall(integrated, bit, target):
    code, log = run(integrated, 6, bit, target)
    assert code == 0 and "FATAL" not in log and "ERROR" not in log, log
    assert len(re.findall(rf"^CHECKED_TOP_RAW_READ_PASS bit={bit} target={target} core=\d+ reason=[0-9a-f]+ control_actor_not_fft=1$", log, re.MULTILINE)) == 1, log


@pytest.mark.parametrize("kind,bit,target", [
    *[(7, bit, target) for bit in range(70) for target in (37, 511)],
    *[(8, bit, target) for bit in range(2) for target in (37, 511)],
])
def test_raw_producer_metadata_position_last(integrated, kind, bit, target):
    code, log = run(integrated, kind, bit, target)
    assert code == 0 and "FATAL" not in log and "ERROR" not in log, log
    assert len(re.findall(rf"^CHECKED_TOP_RAW_PRODUCT_PASS kind={kind} bit={bit} target={target} bank_reason=[0-9a-f]+ issuer_reason=[0-9a-f]+ control_actor_not_fft=1$", log, re.MULTILINE)) == 1, log


@pytest.mark.parametrize("kind,reset,target", [
    *[(9, reset, target) for reset in range(2) for target in range(5)],
    *[(10, reset, target) for reset in range(2) for target in (2, 3, 4)],
])
def test_paused_slow_epoch_and_recovery(integrated, kind, reset, target):
    code, log = run(integrated, kind, reset, target)
    assert code == 0 and "FATAL" not in log and "ERROR" not in log, log
    marker = f"CHECKED_TOP_RESET_PASS kind={kind} reset={reset} target={target} paused_edges=8 compared=512 starts=2 ack=1 releases=1 independent_expected=512 secondary_reference_reset_provider=1 control_actor_not_fft=1"
    assert log.count(marker) == 1, log


@pytest.mark.parametrize("kind,marker", [(9, "CHECKED_TOP_ACCEPTED_OUTPUT_CHANGED"), (10, "CHECKED_TOP_WATCHDOG")])
def test_original_p1_paused_reset_gap_retained(tmp_path, kind, marker):
    path = build(tmp_path / "old_reset_provider", reference_purge=0)
    code, log = run(path, kind, 0, 2)
    assert code != 0 and marker in log and "CHECKED_TOP_INDEPENDENT_ACTOR_TUPLE_CHANGED" not in log, log


RESTORE = [
    ("top", "fft_bank_owned_checked_product", "fft_bank_owned_product_fence", "8923b42b3574fc1418eee99c5f5819f173c73fbf7b8bb65726a7ab3a5d8a6f7c"),
    ("input", "realtime_checked_product_input_guard", "realtime_input_guard", "eb1f968a30ae0371421cfb0766c7f8bf0c23411e730717cd0d4924be0604109e"),
    ("result", "realtime_result_guard_observe", "realtime_result_guard", "09ab35339d55ddf88e813830322d21574d0794c489c9749f68113e9da7807be2"),
    ("reader", "checked_product_read_observe", "checked_product_read_interface", "b29a700232c9ee0d62dc4cbade48e266bcf6bce4665eff670f9232584194ec3e"),
    ("issuer", "product_sealed_observe", "product_sealed_publication_interface", "03c37b96aa77562c9f544b0ff4604e944a7b986677703fc546543caa42718f1f"),
]


@pytest.mark.parametrize("label,new,old,digest", RESTORE)
@pytest.mark.parametrize("mutated", [False, True])
def test_full_source_inverse_and_nonlocal_edit_rejection(tmp_path, label, new, old, digest, mutated):
    source = (ACQ / f"starlink_pss_{new}.v").read_bytes()
    if mutated:
        source = source.replace(b"// SPDX-License-Identifier: GPL-2.0", b"// UNAUTHORIZED WHOLE-BODY EDIT", 1)
        assert b"UNAUTHORIZED WHOLE-BODY EDIT" in source
    (tmp_path / "source.v").write_bytes(source)
    inverse = Path(__file__).with_name("checked_product_top_inverse") / f"{label}.patch"
    shutil.copyfile(inverse, tmp_path / "inverse.patch")
    p = subprocess.run(["patch", "--batch", "--fuzz=0", "source.v", "inverse.patch"], cwd=tmp_path,
                       env=clean_env(), capture_output=True, text=True, check=False)
    restored = (tmp_path / "source.v").read_bytes()
    (tmp_path / "inverse.log").write_text(p.stdout + p.stderr)
    assert hashlib.sha256((ACQ / f"starlink_pss_{old}.v").read_bytes()).hexdigest() == digest
    matches = p.returncode == 0 and hashlib.sha256(restored).hexdigest() == digest
    assert matches != mutated


TOP_RTL = "starlink_pss_fft_bank_owned_checked_product.v"
MUTANTS = [
    ("origin_lease", (TOP_RTL, "product_head_lease === origin_lease", "1'b1"), 3, 0, 0, "CHECKED_TOP_CURRENT_UNBOUND_ACK"),
    ("independent_descriptor", (TOP_RTL, "product_head_metadata === {5'b0, expected_product_metadata}", "1'b1"), 2, 74, 0, "CHECKED_TOP_CURRENT_UNBOUND_ACK"),
    ("bound_receipt", (TOP_RTL, "bound_receipt && product_handoff_state_owned &&", "product_handoff_state_owned &&"), 4, 0, 4, "CHECKED_TOP_CURRENT_UNBOUND_START"),
    ("head_good", (TOP_RTL, "product_head_owned_good && independent_head_identity", "independent_head_identity"), 11, 0, 4, "CHECKED_TOP_CURRENT_UNBOUND_START"),
    ("actual_ready", (TOP_RTL, ".sampled_product_ready(product_bank_ready && !fast_fault)", ".sampled_product_ready(advertised_ready)"), 1, 0, 511, "CHECKED_TOP_FORCED_READY_TAKE"),
    ("source_reader_purge", (TOP_RTL, ".output_resetn(source_epoch_open)", ".output_resetn(fast_running)"), 9, 0, 0, "CHECKED_TOP_PAUSED_SLOW_REOPENED"),
    ("source_fault_purge", (TOP_RTL, "if (!source_epoch_open) source_fault_fast <= 0;", "if (!fast_running) source_fault_fast <= 0;"), 10, 0, 2, "CHECKED_TOP_PAUSED_SLOW_REOPENED"),
    ("origin_reset", (TOP_RTL, "origin_lease<=0;origin_valid<=0;bound_receipt<=0;", "origin_lease<=0;bound_receipt<=0;"), 9, 0, 3, "CHECKED_TOP_PAUSED_SLOW_REOPENED"),
    ("receipt_reset", (TOP_RTL, "origin_lease<=0;origin_valid<=0;bound_receipt<=0;", "origin_lease<=0;origin_valid<=0;"), 9, 0, 3, "CHECKED_TOP_PAUSED_SLOW_REOPENED"),
    ("publication_closed_input", (TOP_RTL, "wire [7:0] publication_current = {closed_forward_events,6'b0,input_fault_now};", "wire [7:0] publication_current = {1'b0,6'b0,input_fault_now};"), 5, 3, 8, "CHECKED_TOP_CURRENT_RAW_ESCAPE"),
    ("publication_current_input", (TOP_RTL, "wire [7:0] publication_current = {closed_forward_events,6'b0,input_fault_now};", "wire [7:0] publication_current = {closed_forward_events,7'b0};"), 5, 9, 8, "CHECKED_TOP_CURRENT_RAW_ESCAPE"),
]


@pytest.mark.parametrize("label,mutation,kind,bit,target,marker", MUTANTS)
def test_executed_missing_binding_ready_reset_mutants(tmp_path, label, mutation, kind, bit, target, marker):
    path = build(tmp_path / label, mutation=mutation)
    code, log = run(path, kind, bit, target)
    assert code != 0 and marker in log, log


@pytest.mark.parametrize("label,old,new", [
    ("live_head_start", "product_head_owned_good && independent_head_identity", "head_valid && independent_head_identity"),
    ("publication_shared_live", ".current_faults(independent_current)", ".current_faults(independent_current | publication_current)"),
    ("qualified_admission", ".current_faults(independent_current)", ".current_faults(independent_current | {7'b0,issuer_events[0]})"),
    ("qualified_completion", ".current_faults(independent_current)", ".current_faults(independent_current | {7'b0,issuer_events[1]})"),
])
def test_restored_composed_backedges_rejected_before_execution(tmp_path, label, old, new):
    path = build(tmp_path / label, mutation=(TOP_RTL, old, new), expect_cycle=True)
    assert json.loads((path / "graph.json").read_text())["cycle"]
    assert not list(path.glob("case-*.log"))


@pytest.mark.parametrize("invalid", ["-1", "2", "1'bx", "1'bz"])
def test_invalid_top_parameter_fails_closed(tmp_path, invalid):
    path = build(tmp_path / "invalid", enabled=invalid)
    code, log = run(path)
    assert code != 0 and "CHECKED_PRODUCT_BANK must be zero or one" in log, log


@pytest.mark.parametrize("kind,value,target", [(kind, value, target) for kind in (12, 15) for value in range(2) for target in (37, 511)])
def test_unknown_actual_ready_and_ungated_raw_offer(integrated, kind, value, target):
    code, log = run(integrated, kind, value, target)
    assert code == 0 and "FATAL" not in log and "ERROR" not in log, log
    marker = f"CHECKED_TOP_UNKNOWN_PRODUCT_PASS kind={kind} value={value} target={target} current=1 sticky=1 control_actor_not_fft=1"
    assert log.count(marker) == 1, log


@pytest.mark.parametrize("reset", [0, 1])
def test_full_prejoin_capture_assumption_is_rejected(integrated, reset):
    code, log = run(integrated, 17, reset)
    # Retained rejected capacity assumption, NOT a complete prejoin-fill PASS.
    assert code != 0 and "CHECKED_TOP_PREJOIN_SOURCE_NOT_ACCEPTED n=2 req=0 ack_sync=11 fast_ack=1 write=2 epoch=0 fault=0" in log, log


@pytest.mark.parametrize("reset", [0, 1])
def test_held_fresh_prefix_rejoins_and_completes(integrated, reset):
    code, log = run(integrated, 18, reset)
    assert code == 0 and "FATAL" not in log and "ERROR" not in log, log
    marker = f"CHECKED_TOP_PREJOIN_HELD_PASS reset={reset} accepted_while_fast_paused=2 held_edges=8 accepted_total=512 independent_expected=512 starts=2 ack=1 releases=1 secondary_reference_held_reset=1 control_actor_not_fft=1"
    assert log.count(marker) == 1, log


@pytest.mark.parametrize("reset", [0, 1])
def test_distinct_payload_reset_prefix_and_full_fresh_completion(integrated, reset):
    code, log = run(integrated, 19, reset)
    assert code == 0 and "FATAL" not in log and "ERROR" not in log, log
    marker = f"CHECKED_TOP_DISTINCT_PAYLOAD_PASS reset={reset} input_words_changed=512 expected_outputs_changed=512 independently_checked=512 starts=2 ack=1 releases=1 control_actor_not_fft=1"
    assert log.count(marker) == 1, log

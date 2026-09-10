"""Offline real-RAM/issuer traces, independent public model and killed mutants."""

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).parent
FW = HERE.parents[1]
ACQ = FW / "hdl/library/starlink_pss_acquisition"
RTL = ACQ / "starlink_pss_epoch_sealed_bank.v"
BENCH = ACQ / "tb_epoch_sealed_bank.sv"
LEGACY_BENCH = ACQ / "tb_epoch_sealed_legacy.sv"
MAILBOX = ACQ / "starlink_pss_block_mailbox.v"
SPEC = importlib.util.spec_from_file_location(
    "sealed_reference", HERE / "epoch_sealed_bank.py"
)
MODEL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODEL)


def child_env():
    env = dict(os.environ)
    for key in ("LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH"):
        env.pop(key, None)
    return env


def compile_case(path, mutation=None, top="tb_epoch_sealed_bank", extra=None):
    path.mkdir()
    for source in (
        RTL,
        BENCH,
        LEGACY_BENCH,
        MAILBOX,
        Path(__file__),
        HERE / "epoch_sealed_bank.py",
    ):
        shutil.copyfile(source, path / source.name)
    source = path / RTL.name
    if extra:
        (path / "extra.sv").write_text(extra)
    if mutation:
        old, new = mutation
        text = source.read_text()
        assert text.count(old) == 1
        source.write_text(text.replace(old, new))
    inventory = {
        item.name: hashlib.sha256(item.read_bytes()).hexdigest()
        for item in path.iterdir()
        if item.is_file()
    }
    (path / "sources.json").write_text(json.dumps(inventory, indent=2))
    command = [
        "iverilog",
        "-g2012",
        "-s",
        top,
        "-o",
        "simv",
        RTL.name,
        BENCH.name,
        LEGACY_BENCH.name,
        MAILBOX.name,
    ]
    if extra:
        command.append("extra.sv")
    process = subprocess.run(
        command, cwd=path, env=child_env(), text=True, capture_output=True, check=False
    )
    (path / "compile.log").write_text(process.stdout + process.stderr)
    (path / "compile_command.json").write_text(
        json.dumps({"command": command, "exit": process.returncode})
    )
    assert process.returncode == 0, process.stdout + process.stderr
    return path


@pytest.fixture(scope="module")
def compiled(tmp_path_factory):
    parent = tmp_path_factory.mktemp("sealed_sources")
    return compile_case(parent / "original")


def execute(path, case, bit=0, phase=0):
    command = ["vvp", "simv", f"+CASE={case}", f"+BIT={bit}", f"+PHASE={phase}"]
    process = subprocess.run(
        command,
        cwd=path,
        env=child_env(),
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    name = f"case-{case}-bit-{bit}-phase-{phase}"
    with (path / f"{name}.log").open("x") as stream:
        stream.write(process.stdout + process.stderr)
    (path / f"{name}.json").write_text(
        json.dumps({"command": command, "exit": process.returncode})
    )
    assert process.returncode == 0, (process.stdout + process.stderr)[-3000:]
    return MODEL.verify_events(process.stdout + process.stderr, case, bit, phase)


@pytest.fixture(scope="module")
def healthy_log(compiled):
    execute(compiled, 0)
    return (compiled / "case-0-bit-0-phase-0.log").read_text()


def test_complete_healthy_ownership_inventory(healthy_log):
    assert MODEL.verify_events(healthy_log, 0)["words"] == 4096


@pytest.mark.parametrize(
    "case,bit,phase",
    [
        (4, 0, 0),
        (5, 0, 0),
        (7, 0, 0),
        (8, 0, 0),
        (9, 0, 0),
        (10, 0, 0),
        (10, 0, 1),
        (12, 0, 0),
        (13, 0, 0),
    ],
)
def test_ownership_issuers_and_current_faults(compiled, case, bit, phase):
    execute(compiled, case, bit, phase)


@pytest.mark.parametrize("bit", range(75))
@pytest.mark.parametrize("phase", range(3))
def test_every_metadata_bit_first_interior_final(compiled, bit, phase):
    execute(compiled, 1, bit, phase)


@pytest.mark.parametrize("bit", range(75))
def test_every_certificate_bit_after_seal(compiled, bit):
    execute(compiled, 2, bit, 1)


@pytest.mark.parametrize("bit", range(75))
def test_first_token_only_metadata_corruption_and_two_edge_evidence(compiled, bit):
    execute(compiled, 14, bit)


@pytest.mark.parametrize("kind", range(4))
def test_ordinal_lease_early_and_missing_last(compiled, kind):
    execute(compiled, 15, kind)


@pytest.mark.parametrize("kind", range(2))
def test_wrong_certificate_lease_and_failed_certificate(compiled, kind):
    execute(compiled, 16, kind)


@pytest.mark.parametrize("bit", range(8))
@pytest.mark.parametrize("phase", range(4))
def test_live_cause_at_each_final_boundary(compiled, bit, phase):
    execute(compiled, 3, bit, phase)


@pytest.mark.parametrize("side", range(2))
@pytest.mark.parametrize("phase", range(5))
def test_one_sided_reset_join_and_explicit_finite_peer_drain(compiled, side, phase):
    execute(compiled, 6, side, phase)


@pytest.mark.parametrize("kind", range(6))
def test_unknown_current_interface_is_simulation_fail_closed(compiled, kind):
    execute(compiled, 11, kind)


@pytest.mark.parametrize("phase", range(4))
def test_certificate_before_with_and_after_seal(compiled, phase):
    result = execute(compiled, 17, phase=phase)
    assert result["completed"] == 1 and result["words"] == 512


@pytest.mark.parametrize("side", range(2))
@pytest.mark.parametrize("phase", range(5))
def test_async_reset_certificate_seal_publication_final_read_and_ack(
    compiled, side, phase
):
    execute(compiled, 18, side, phase)


@pytest.mark.parametrize("phase", range(2))
def test_raw_orphan_at_final_read_ack_prohibits_next_admission(compiled, phase):
    execute(compiled, 19, phase=phase)


MUTANTS = [
    (
        "seal_q && full && certificate_seen && pipe_empty",
        "seal_q && full && 1'b1 && pipe_empty",
        0,
    ),
    (
        "full && !seal_q &&\n      check_valid[1]",
        "full && !seal_q &&\n      check_valid[0]",
        13,
    ),
    (
        "wire publication_current_clean = live_clean",
        "wire publication_current_clean = 1'b1",
        3,
    ),
    (
        " && !closed_input_offer && !duplicate_certificate_offer",
        " && 1'b1 && !duplicate_certificate_offer",
        7,
    ),
    (
        " && !duplicate_certificate_offer && !uncertain_interface",
        " && 1'b1 && !uncertain_interface",
        8,
    ),
    (
        "assign groups_next[group_index] = &equal_leaves[6*group_index +: BITS];",
        "assign groups_next[group_index] = group_index==4 ? 1'b1 : &equal_leaves[6*group_index +: BITS];",
        1,
    ),
    (
        "old_certificate_drained && old_input_drained",
        "certificate_valid === 1'b0 && input_valid === 1'b0",
        9,
    ),
    ("certificate_lease !== lease ||", "1'b0 ||", 16),
    ("lease_release_tag !== lease", "1'b0", 5),
    ("reasons <= reasons | errors_now;", "reasons <= errors_now;", 10),
    (
        "if (rearm_valid === 1'b1 && rearm_ready) armed <= 1;",
        "if (!armed) armed <= 1;",
        6,
    ),
    (
        "if (private_take) payload_memory[write_position] <= input_data;",
        "if (private_take) payload_memory[write_position] <= input_data ^ 36'b1;",
        13,
    ),
    (
        "fault_position_q <= check_position1;",
        "fault_position_q <= check_position1 ^ 9'b1;",
        15,
    ),
    ("fault_lease_q <= check_lease1;", "fault_lease_q <= check_lease1 ^ 2'b1;", 15),
    (
        "assign output_valid = running && armed && read_valid && clean && publication_current_clean;",
        "reg withdrawal_used=0, withdrawal_pulse=0; always @(posedge clk) begin withdrawal_pulse<=0; if(read_valid && !output_ready && !withdrawal_used) begin withdrawal_pulse<=1; withdrawal_used<=1; end end assign output_valid = running && armed && read_valid && clean && publication_current_clean && !withdrawal_pulse;",
        13,
    ),
]


@pytest.mark.parametrize("index", range(len(MUTANTS)))
def test_semantic_mutants_reject(tmp_path, index):
    old, new, case = MUTANTS[index]
    path = compile_case(tmp_path / "mutant", (old, new))
    with pytest.raises((AssertionError, ValueError)):
        execute(
            path,
            case,
            74 if index == 5 else (1 if index == 13 else 0),
            1 if index == 5 else (3 if index == 2 else 0),
        )
    if index == 14:
        assert (
            "stalled output VALID/tuple changed"
            in (path / "case-13-bit-0-phase-0.log").read_text()
        )


def test_default_and_explicit_zero_exact_original_mailbox(tmp_path):
    path = compile_case(tmp_path / "legacy", top="tb_epoch_sealed_legacy")
    process = subprocess.run(
        ["vvp", "simv"],
        cwd=path,
        env=child_env(),
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    (path / "run.log").write_text(process.stdout + process.stderr)
    assert process.returncode == 0, process.stdout + process.stderr
    assert re.fullmatch(r"SEALED_LEGACY_PASS checks=\d+ words=1024\n", process.stdout)


@pytest.mark.parametrize("value", ["-1", "2", "32'bx", "32'bz"])
def test_invalid_public_parameter_rejected(tmp_path, value):
    source = f"module invalid; starlink_pss_epoch_sealed_bank #(.SEALED_PUBLICATION({value})) d(); initial begin #1; $finish(0); end endmodule"
    path = compile_case(tmp_path / "invalid", top="invalid", extra=source)
    process = subprocess.run(
        ["vvp", "simv"],
        cwd=path,
        env=child_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    (path / "run.log").write_text(process.stdout + process.stderr)
    assert (
        process.returncode != 0
        and "SEALED_PUBLICATION must be zero or one" in process.stdout
    )


@pytest.mark.parametrize("event", ["SEAL", "PUB", "REL"])
@pytest.mark.parametrize("field", ["epoch", "lease", "cycle"])
def test_public_receipt_ownership_and_order_mutations_reject(healthy_log, event, field):
    log = healthy_log
    match = re.search(r"^" + event + r" (\d+) (\d+) (\d+)$", log, re.MULTILINE)
    assert match
    parts = match.group().split()
    index = {"cycle": 1, "epoch": 2, "lease": 3}[field]
    parts[index] = str(int(parts[index]) + 1 if field != "cycle" else 0)
    mutated = log[: match.start()] + " ".join(parts) + log[match.end() :]
    with pytest.raises(ValueError):
        MODEL.verify_events(mutated, 0)


def test_state_and_literal_legacy_binding():
    assert (
        hashlib.sha256(MAILBOX.read_bytes()).hexdigest()
        == "e85122eb6689ff49b31aa5a0c200e2666786629055b4f45856fe79fb829dbb55"
    )
    text = RTL.read_text()
    assert "parameter integer SEALED_PUBLICATION = 0" in text
    assert "if (SEALED_PUBLICATION !== 0 && SEALED_PUBLICATION !== 1)" in text
    assert ".METADATA_WIDTH(75), .EXPLICIT_COMMIT(1)" in text
    assert text.count("payload_memory [0:511]") == 1
    state = MODEL.logical_state(text)
    assert state["memory"] == {"payload_memory": 512 * 36}
    assert state["reused_bank_bits"] == 222
    assert state["registers"]["equal_leaves"] == 25
    assert state["registers"]["equal_groups"] == 5
    assert (
        state["registers"]["check_position0"]
        == state["registers"]["check_position1"]
        == 9
    )
    assert (
        "input_metadata !== metadata_in_hold"
        not in text.split("wire framing_bad", 1)[1].split(";", 1)[0]
    )
    fence = text.split("wire publication_current_clean =", 1)[1].split(";", 1)[0]
    assert not re.search(
        "framing|certificate_bad|pipeline_bad|local_current_clean", fence
    )


@pytest.mark.parametrize(
    "suffix",
    [
        "\nFATAL: late failure",
        "\nERROR late",
        "\nSEALED_BANK_PASS case=0 bit=0 phase=0 cycles=2",
        "\nunknown_receipt",
    ],
)
def test_terminal_and_late_failure_are_strict(healthy_log, suffix):
    with pytest.raises(ValueError):
        MODEL.verify_events(healthy_log + suffix, 0)


@pytest.mark.parametrize("anchor", ["RESET", "JOB", "PUB"])
def test_unknown_fault_after_initial_reset_never_uses_startup_exception(
    healthy_log, anchor
):
    match = re.search(r"^" + anchor + r" .+$", healthy_log, re.MULTILINE)
    parts = match.group().split()
    injected = f"\nFAULT {parts[1]} {parts[2]} xxxx"
    with pytest.raises(ValueError):
        MODEL.verify_events(
            healthy_log[: match.end()] + injected + healthy_log[match.end() :], 0
        )


@pytest.mark.parametrize("value", ["xx00", "zzzz", "xxxz", "000x"])
def test_only_exact_documented_pre_reset_unknown_receipt_is_admitted(
    healthy_log, value
):
    with pytest.raises(ValueError):
        MODEL.verify_events(
            healthy_log.replace("FAULT 1 0 xxxx", "FAULT 1 0 " + value, 1), 0
        )


@pytest.mark.parametrize(
    "event,field", [("TAKE", 3), ("TAKE", 6), ("CERT", 3), ("CERT", 4)]
)
def test_offered_source_lease_and_25th_metadata_leaf_reject(healthy_log, event, field):
    match = re.search(r"^" + event + r" .+$", healthy_log, re.MULTILINE)
    parts = match.group().split()
    parts[field] = (
        str(int(parts[field]) ^ 1)
        if field == 3
        else f"{int(parts[field], 16) ^ (1 << 74):x}"
    )
    mutated = (
        healthy_log[: match.start()] + " ".join(parts) + healthy_log[match.end() :]
    )
    with pytest.raises(ValueError):
        MODEL.verify_events(mutated, 0)


@pytest.mark.parametrize("case", [1, 2, 3, 4, 5, 7, 8, 10, 11, 12, 14, 15, 16, 19])
def test_terminal_only_negative_is_never_evidence(case):
    with pytest.raises(ValueError):
        MODEL.verify_events(
            f"SEALED_BANK_PASS case={case} bit=0 phase=0 cycles=1\n", case
        )


@pytest.fixture(scope="module")
def negative_log(tmp_path_factory):
    path = compile_case(
        tmp_path_factory.mktemp("negative_receipt_sources") / "original"
    )
    execute(path, 7)
    return (path / "case-7-bit-0-phase-0.log").read_text()


@pytest.mark.parametrize("event", ["JOB", "TAKE", "CERT", "SEAL", "FAULT"])
def test_truncated_negative_event_inventory_rejects(negative_log, event):
    pattern = r"^" + event + r" .+\n"
    if event == "FAULT":
        # Remove the actual owned nonzero cause, not the optional startup-X or
        # reset-clear diagnostic preceding this negative transaction.
        pattern = r"^FAULT \d+ [1-9]\d* (?!0000\n)[0-9a-f]{4}\n"
    mutated, count = re.subn(pattern, "", negative_log, count=1, flags=re.MULTILINE)
    assert count == 1
    with pytest.raises(ValueError):
        MODEL.verify_events(mutated, 7)


def new_issuer():
    issuer = MODEL.FiniteIssuer()
    issuer.reset()
    for peer in issuer.peers:
        issuer.flush(peer)
    issuer.rearm(True)
    return issuer


def test_finite_issuer_eight_lifetimes_require_consume_ack_and_drain():
    issuer = new_issuer()
    for lifetime in range(8):
        tag = lifetime % 4
        assert issuer.lease == tag
        for peer in issuer.peers:
            issuer.enqueue(peer, lifetime, tag)
            issuer.consume(peer, lifetime)
            with pytest.raises(ValueError):
                issuer.consume(peer, lifetime)
        for peer in issuer.peers:
            with pytest.raises(ValueError):
                issuer.release(tag, True, True)
            issuer.acknowledge_consumption(peer, lifetime)
        for request in ((tag ^ 1, True, True), (tag, False, True), (tag, True, False)):
            with pytest.raises(ValueError):
                issuer.release(*request)
        issuer.release(tag, True, True)


def test_finite_future_queue_survives_old_release_without_deadlock():
    issuer = new_issuer()
    for peer in ("producer", "certificate"):
        issuer.enqueue(peer, "old", 0)
        issuer.enqueue(peer, "future", 1)
        with pytest.raises(ValueError):
            issuer.consume(peer, "future")
        issuer.consume(peer, "old")
        issuer.acknowledge_consumption(peer, "old")
    issuer.release(0, True, True)
    for peer in ("producer", "certificate"):
        issuer.consume(peer, "future")


@pytest.mark.parametrize("retained_peer", MODEL.FiniteIssuer.peers)
def test_reset_does_not_erase_a_held_reference_or_create_rearm_authority(retained_peer):
    issuer = new_issuer()
    issuer.enqueue(retained_peer, "held", 0)
    issuer.reset()
    assert "held" in issuer.refs[retained_peer]
    for peer in issuer.peers:
        if peer != retained_peer:
            issuer.flush(peer)
        with pytest.raises(ValueError):
            issuer.rearm(True)
    with pytest.raises(ValueError):
        issuer.consume(retained_peer, "held")
    issuer.flush(retained_peer)
    with pytest.raises(ValueError):
        issuer.rearm(False)
    issuer.rearm(True)
    assert issuer.lease == 0 and not any(issuer.refs.values())


def test_lease_bits_alone_cannot_prove_aba_or_reset_freshness():
    issuer = new_issuer()
    stale_wire_certificate = (issuer.lease, MODEL.golden_metadata(0), True)
    issuer.enqueue("certificate", "stale", 0)
    issuer.consume("certificate", "stale")
    with pytest.raises(ValueError):
        issuer.release(0, True, True)  # VALID becoming zero is insufficient.
    issuer.acknowledge_consumption("certificate", "stale")
    for tag in range(4):
        issuer.release(tag, True, True)
    assert stale_wire_certificate == (issuer.lease, MODEL.golden_metadata(0), True)
    # If an untracked external copy survives the attested ACK/flush, equality
    # cannot distinguish it. This is a counterexample OUTSIDE the contract,
    # not a claim that the RTL rejects arbitrary stale two-bit tags.
    issuer.reset()
    assert stale_wire_certificate[0] == issuer.lease


def test_finite_issuer_enforces_capacity_order_and_ownership():
    issuer = new_issuer()
    issuer.enqueue("certificate", "old", 0)
    with pytest.raises(ValueError):
        issuer.acknowledge_consumption("certificate", "old")
    for identity, lease in (("old", 0), ("nonadjacent", 2)):
        with pytest.raises(ValueError):
            issuer.enqueue("certificate", identity, lease)
    issuer.enqueue("certificate", "future", 1)
    with pytest.raises(ValueError):
        issuer.enqueue("certificate", "overflow", 1)

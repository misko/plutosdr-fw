"""Offline timeline reconstruction and abstract ownership, never RTL evidence."""

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tests.starlink_oracle.output_overlap_ledger import (
    Clocks, RetainedConsumer, conditional, output_reads, read_actual, recipe,
    reconstruct, sha_file, source_block, summary,
)

ACTUAL = Path("/tmp/starlink-coarse-alternatives.Y3JzOI/bank-arithmetic/hdl/library/starlink_pss_acquisition/build/local-admission-actual-R1B1O1-L1-175-prepared-v4")
SIM = ACTUAL / "project/fft_bank_arithmetic_actual.sim/sim_1/behav/xsim"


@pytest.fixture(scope="module")
def measured():
    epochs, markers = read_actual(SIM/"fft_bank_owned_trace.csv", SIM/"simulate.log")
    return epochs, markers, reconstruct(epochs, markers)


def reference_reader(publication, profile):
    """Independent old-state/NBA recurrence of the actual mailbox reader."""
    c = Clocks(); start = c.fast(publication)
    fast_edges = {c.fast(n): n for n in range(publication+1, publication+2000)}
    first_slow = c.next_slow(start)
    slow_edges = {c.slow(n): n for n in range(first_slow, first_slow+1000)}
    assert not set(fast_edges) & set(slow_edges)
    sync0 = sync1 = ack0 = ack1 = ack = reading = valid = 0
    loaded = 0; read_position = 0; accepted = []
    for time in sorted(set(fast_edges) | set(slow_edges)):
        if time in fast_edges:
            if ack1:
                return {"first_read_slow": accepted[0], "last_read_slow": accepted[-1],
                        "ack_observed_fast": fast_edges[time]}
            ack0, ack1 = ack, ack0
        else:
            s = slow_edges[time]; ready = profile == 0 or s % 17 < 13
            take = valid and ready
            load = reading and loaded < 512 and (not valid or ready)
            new_reading = reading or sync1
            if take:
                accepted.append(s)
                if read_position == 511:
                    ack = sync1; new_reading = 0
            if load:
                valid = 1; read_position = loaded; loaded += 1
            elif take:
                valid = 0
            reading = new_reading
            sync0, sync1 = 1, sync0
    raise AssertionError("reference reader failed to drain")


@pytest.mark.parametrize("profile", [0, 1])
@pytest.mark.parametrize("publication", [4582+n for n in range(34)])
def test_exact_reader_phase_recurrence(publication, profile):
    assert output_reads(Clocks(), profile, publication) == reference_reader(publication, profile)


def test_known_clock_origins_and_strict_edge_order():
    c = Clocks()
    assert c.half == 2_857_143 and c.fast(0) == 2_857_143 and c.slow(0) == 6_300_000
    for n in (0, 1, 945, 4582, 149466):
        assert c.next_fast(c.fast(n)) == n+1
        assert c.next_fast(c.fast(n)-1) == n
        assert c.next_slow(c.slow(n)) == n+1
        assert c.next_slow(c.slow(n)-1) == n
    with pytest.raises(ValueError):
        _ = Clocks(True).half


def test_source_producer_pause_and_cdc():
    c = Clocks()
    assert source_block(c, 0, 536, 945) == {
        "source_first_slow": 838, "source_commit_slow": 1349,
        "source_visible_fast": 2366, "source_ready_observed_fast": 1466}
    assert source_block(c, 1, 536, 945)["source_commit_slow"] == 1469
    # Independent per-word original send_words task spacing.
    s = 0
    for word in range(511):
        s += 1 + (3 if word % 13 == 0 else 0)
    assert s == 631


def test_original_every_block_and_job_reconstructed(measured):
    _, _, rows = measured
    assert len(rows) == 38
    assert summary(rows)["1"]["pair_periods"] == {4548: 24, 4549: 7}
    assert summary(rows)["2"]["pair_periods"] == {4822: 2, 4821: 3}
    assert sum(x["next_source_full_at_inverse_publication"] for x in rows) == 36
    assert all(x["product_read_valid_at_inverse_publication"] == 0 for x in rows)
    assert rows[0]["inverse_publication_fast"] == 4582
    assert rows[0]["ack_observed_fast"] == 5486


@pytest.mark.parametrize("field", ["input", "output", "status", "config", "commit", "product", "handoff", "block_start"])
def test_original_job_mutants_rejected(measured, field):
    epochs, markers, _ = measured; bad = copy.deepcopy(epochs)
    if field == "block_start":
        bad[1]["jobs"][0][field] += 447
    else:
        bad[1]["jobs"][0][field][0] += 1
    with pytest.raises(ValueError):
        reconstruct(bad, markers)


@pytest.mark.parametrize("field", ["source_visible", "source_ready", "output_ready"])
def test_actual_cdc_receipt_mutants_rejected(measured, field):
    epochs, markers, _ = measured; bad = copy.deepcopy(epochs)
    bad[1][field] = [x+1 for x in bad[1][field]]
    with pytest.raises(ValueError):
        reconstruct(bad, markers)


@pytest.mark.parametrize("kind", ["CAPTURE_START", "CAPTURE_COMMIT", "OUTPUT_START", "OUTPUT"])
def test_actual_slow_receipt_mutants_rejected(measured, kind):
    epochs, markers, _ = measured; bad = dict(markers)
    bad[1,1,kind] += 1
    with pytest.raises(ValueError):
        reconstruct(epochs, bad)


@pytest.mark.parametrize("mhz", [175,150,140,130,125,120])
@pytest.mark.parametrize("extra", [0,24])
def test_counterfactual_causality_and_finite_storage(measured, mhz, extra):
    rows = conditional(measured[2], mhz, extra)
    for a,b in zip(rows, rows[1:]):
        if b["block"] == 0:
            continue
        assert b["forward_admit_fast"] >= a["inverse_publication_fast"]+8
        assert b["forward_admit_fast"] >= b["source_visible_fast"]+2
        assert b["inverse_admit_fast"] >= a["ack_observed_fast"]+3
        assert b["inverse_admit_fast"] >= b["forward_publication_fast"]+17+extra
        assert b["forward_input_edges_while_old_output_owned"] == 512
        assert b["old_read_edges_during_forward_input_span"] > 0
        assert b["old_output_released_before_next_inverse"]
        assert b["pair_period_fast"] == 3645+extra
    # This is arithmetic on a proposed schedule, never a changed RTL bound.
    maximum_fs = max(x.get("pair_period_fs", 0) for x in rows)
    assert (maximum_fs <= 29_800_000_000) == (mhz >= 125)


def test_arbitrary_reader_stall_is_not_hidden_without_bound():
    with pytest.raises(ValueError, match="did not drain"):
        output_reads(Clocks(), 0, 4582, ready=lambda _: False)
    late = output_reads(Clocks(), 0, 4582, ready=lambda s: s >= 10_000)
    # A prolonged hold can exceed the next forward's compute. It must delay
    # next inverse; no second output or third product slot exists.
    assert late["ack_observed_fast"] > 4582+8+1810+17


def test_naive_phase_and_orphan_issuer_counterexamples():
    # Exact Boolean leaves from frozen issuer 8ad9c2e7, not RTL execution.
    producer = certificate = 0; published = reader = final_taken = 1
    inverse_phase = 0
    phase_lost = (producer or certificate or published or reader) and inverse_phase != 1
    assert phase_lost  # Merely starting next forward immediately faults.
    guard_busy = 1; reader = 0
    release_valid = published and not producer and not certificate and not reader and not guard_busy
    assert not release_valid  # New forward busy pins the OLD consumer release.
    raw_orphan = final_taken and 1 != 0
    assert raw_orphan  # Next forward's valid output is misattributed to old inverse.


def test_retained_owner_independent_of_current_core_and_real_ack():
    owner = RetainedConsumer(); owner.publish(2, 0x200010000, True)
    owner.start_forward(True)
    assert owner.descriptor == 0x200010000  # Not current forward N+1 descriptor.
    with pytest.raises(ValueError):
        owner.start_inverse()
    owner.reset()  # Per-transform reset must retain consumer ownership.
    assert owner.lease == 2 and owner.descriptor == 0x200010000
    owner.acknowledge(0, 2, True)  # Does not require new forward guard_busy=0.
    owner.start_inverse()


@pytest.mark.parametrize("epoch,lease,final", [(1,2,True),(0,3,True),(0,2,False)])
def test_false_ack_rejected(epoch, lease, final):
    owner = RetainedConsumer(); owner.publish(2, 70, True)
    with pytest.raises(ValueError):
        owner.acknowledge(epoch, lease, final)
    assert owner.lease == 2


def test_reset_pause_and_lease_aba_require_fresh_epoch_and_no_references():
    owner = RetainedConsumer(); owner.publish(2, 70, True)
    old_epoch = owner.epoch; owner.reset(common=True)
    with pytest.raises(ValueError): owner.rearm(old_epoch, True)
    with pytest.raises(ValueError): owner.rearm(owner.epoch, False)
    with pytest.raises(ValueError): owner.start_forward(True)
    owner.rearm(owner.epoch, True)
    # Numeric lease equality after wrap alone cannot distinguish an old ACK.
    owner.publish((2+4) % 4, 71, True)
    with pytest.raises(ValueError): owner.acknowledge(old_epoch, 2, True)


def test_fault_quarantines_both_obligations_and_never_retracts_old_prefix():
    owner = RetainedConsumer(); owner.publish(2, 70, True); owner.start_forward(True)
    accepted_prefix = tuple(range(128)); owner.faulted = True
    with pytest.raises(ValueError): owner.start_inverse()
    with pytest.raises(ValueError): owner.acknowledge(0, 2, True)
    assert accepted_prefix == tuple(range(128)) and owner.lease == 2


def test_reviewed_runtime_dependencies_unchanged():
    pins = {
        "starlink_pss_fft_bank_owned_local_admission_probe.v": "0cb54617eb6757e1d6c719d97b0fd5002ec7f6105c8c4b50c41eba67d4306235",
        "starlink_pss_realtime_result_guard.v": "09ab35339d55ddf88e813830322d21574d0794c489c9749f68113e9da7807be2",
        "starlink_pss_block_mailbox.v": "e85122eb6689ff49b31aa5a0c200e2666786629055b4f45856fe79fb829dbb55",
        "tb_starlink_pss_local_admission_actual.sv": "a347cd6ec4bb3e888f0ce171aedb7c4a85cebea4932bc880f348a75ada5ae238",
    }
    for name, digest in pins.items():
        assert sha_file(ACTUAL/"frozen_sources"/name) == digest
    assert recipe()["unchanged_nominal_pair_budget_at_175"] == 5215
    assert recipe()["unchanged_guard_watchdog_fast_cycles"] == 8192


def test_cli_source_freeze_and_no_overwrite(tmp_path):
    target = tmp_path/"proof"
    command = [sys.executable, "-B", "-m", "tests.starlink_oracle.output_overlap_ledger",
               "--trace", str(SIM/"fft_bank_owned_trace.csv"), "--log", str(SIM/"simulate.log"),
               "--output", str(target)]
    run = subprocess.run(command, capture_output=True, text=True, check=False)
    assert run.returncode == 0, run.stdout+run.stderr
    proof = json.loads((target/"ledger.json").read_text())
    assert proof["original_reconstruction"] == "PASS_ALL_38_BLOCKS_76_JOBS"
    receipt = json.loads((target/"integrity.json").read_text())
    assert receipt["before"] == receipt["after"] and receipt["equal"] is True
    assert len(receipt["before"]) == 9
    for path, entry in receipt["before"].items():
        if Path(path).name == "fft_bank_owned_trace.csv":
            continue
        assert sha_file(target/"source_snapshot"/Path(path).name) == entry["sha256"]
    digest = sha_file(target/"ledger.json")
    second = subprocess.run(command, capture_output=True, text=True, check=False)
    assert second.returncode != 0 and "new output" in second.stderr
    assert sha_file(target/"ledger.json") == digest


def test_wrong_or_symlinked_trace_rejected(tmp_path):
    wrong = tmp_path/"wrong.csv"; wrong.write_text("not the original trace\n")
    with pytest.raises(ValueError, match="wrong original trace"):
        read_actual(wrong, SIM/"simulate.log")
    link = tmp_path/"link.csv"; link.symlink_to(SIM/"fft_bank_owned_trace.csv")
    with pytest.raises(ValueError, match="regular bounded input"):
        read_actual(link, SIM/"simulate.log")

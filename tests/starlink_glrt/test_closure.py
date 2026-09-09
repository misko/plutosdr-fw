"""An incomplete native tail may retire; completed vectors and metadata cannot disappear."""
from dataclasses import replace
import struct

import pytest

from tools.starlink_glrt_abi import Closure, Event, Snapshot
from .test_abi import wire


def closure_wire(words, *, generation=1, visit=29, rate=10_000_000):
    return f"GLX1 00010000 {generation} {visit} {rate} " + " ".join(f"{word:08x}" for word in words)


def attest_fabric_closure(evidence):
    """Bridge real AXI reads to host checks with explicitly constructed CPU headers.

    The caller's RTL test supplies the raw registers and IQ count. This does
    not execute Linux or attest CPU/IIO transfers; all CPU counters are zero.
    """
    decoded = []
    rate, visit = evidence["rate"], evidence["visit"]
    for label in ("baseline_registers", "final_registers"):
        registers = {int(key): value for key, value in evidence[label].items()}
        assert (registers[0x5c], registers[0x60], registers[0x64]) == (0x474c5831, 0x10000, 16)
        generation = registers[0x48]
        words = [registers[0x80+4*index] for index in range(64)]
        header = f"GLR1 00010000 {rate} 2500000 {generation} 0 {rate} 0 0 0 0 0 0 0 "
        snapshot = Snapshot.decode(header+" ".join(f"{word:08x}" for word in words))
        extension = [registers[0x300+4*index] for index in range(16)]
        closure = Closure.decode(closure_wire(extension, generation=generation, visit=visit, rate=rate))
        decoded.append((snapshot, closure))
    (baseline, before), (final, closure) = decoded
    closure.require_complete(final, baseline=before, base_snapshot=baseline)
    final.require_stopped_iq(expected_visit=visit, expected_rate=rate, expected_samples=evidence["iq_samples"])
    if "event_words" in evidence:
        events = [Event.decode(struct.pack("<16I", *words)) for words in evidence["event_words"]]
        assert len(events) == final.u64(38)
        closure.require_event_support(events)
    return closure.evidence()


def evidence():
    final = Snapshot.decode(wire())
    words = list(final.words)
    words[30], words[34], words[36], words[38] = 5, 3, 1, 2
    final = replace(final, words=tuple(words))
    before = list(words)
    before[19] = 0
    before[4:8] = [0]*4
    before[30:40] = [0]*10
    baseline = replace(final, words=tuple(before))
    extension = [7, 0, final.u64(2)+3, 0, 1, 0, 1, 0, 2, 0, 2, 0, 1, 0, 0, 0]
    return final, baseline, Closure.decode(closure_wire(extension)), Closure.decode(closure_wire([0]*16))


def test_partial_tail_is_explicit_and_no_completed_vector_is_discarded():
    final, baseline, closure, before = evidence()
    closure.require_complete(final, baseline=before, base_snapshot=baseline)
    assert closure.evidence() == {"native_endpoint": 1495, "incomplete_native_tails": 1,
                                 "discarded_selector_groups": 1, "completed_native_vectors": 2,
                                 "completed_scorer_vectors": 2, "selected_close_rejections": 1, "expired_candidates": 0}


@pytest.mark.parametrize("index,value", [(0, 3), (0, 6), (1, 1), (2, 1491), (4, 0), (8, 3), (10, 1), (12, 0), (14, 2)])
def test_fault_or_lost_work_cannot_be_reclassified_as_a_complete_observation(index, value):
    final, baseline, closure, before = evidence()
    words = list(closure.words)
    words[index] = value
    with pytest.raises(ValueError):
        replace(closure, words=tuple(words)).require_complete(final, baseline=before, base_snapshot=baseline)


@pytest.mark.parametrize("mutation", [{"generation": 2}, {"visit": 30}, {"source_rate": 2_500_000}])
def test_extension_must_belong_to_the_exact_atomic_base_snapshot(mutation):
    final, baseline, closure, before = evidence()
    with pytest.raises(ValueError, match="identity mismatch"):
        replace(closure, **mutation).require_complete(final, baseline=before, base_snapshot=baseline)


@pytest.mark.parametrize("pending", [1, 2, 4, 8])
def test_even_previously_accepted_native_or_selector_pending_state_is_not_finite_closure(pending):
    final, baseline, closure, before = evidence()
    words = list(final.words)
    words[61] = pending
    with pytest.raises(ValueError, match="pending"):
        closure.require_complete(replace(final, words=tuple(words)), baseline=before, base_snapshot=baseline)


@pytest.mark.parametrize("index,value", [(0, 8), (1, 2)])
def test_reserved_extension_fields_are_never_silently_accepted(index, value):
    words = [0]*16
    words[index] = value
    with pytest.raises(ValueError, match="reserved"):
        Closure.decode(closure_wire(words))

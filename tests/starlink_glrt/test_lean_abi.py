"""GLF1's distinct IQ contract and provisional live native source mapping."""
from dataclasses import replace

import pytest

from tools.starlink_glrt_abi import Closure, Snapshot
from tools.starlink_glrt_lean_abi import LeanClosure, LeanSnapshot


def wire(*, active=False, first=2**60+8):
    # First must be a multiple of 24; keep its integer precision above 2**53.
    first -= first % 24
    last = first+24*999
    w = [0]*64
    w[:8] = [first % 2**32, first >> 32, last % 2**32, last >> 32, 1000, 0, 1000, 0]
    w[12:16] = [30000, 0, 1000, 0]
    w[19:24] = [25 if active else 24, 91, 1, 0, 0]
    w[61] = 8 if active else 0  # Timing-selector groups may be pending live.
    w[62:64] = [60000000, 1272]
    return 'GLF1 00010000 60000000 2500000 5 0 60000000 0 0 0 0 0 0 0 '+' '.join(f'{v:08x}' for v in w)


def closure(base, *, initial=False):
    w = [0]*16
    if not initial:
        w[:4] = [7, 0, base.words[2], base.words[3]]
        w[6] = 19  # Discarded timing proposals do not imply lost scorer work.
    return LeanClosure.decode(f'GLF1 00010000 {base.generation} 91 60000000 '+' '.join(f'{v:08x}' for v in w))


def test_native_origin_remains_exact_with_live_selector_and_large_source_counter():
    s = LeanSnapshot.decode(wire(active=True))
    origin = s.require_live_prefix(expected_visit=91, received_samples=750)
    assert origin == s.u64(0)-1272
    assert s.source_center(749) == origin+24*749
    assert isinstance(origin, int) and origin > 2**53
    with pytest.raises(ValueError): s.require_stopped_iq(expected_visit=91, expected_rate=60000000)


def test_old_and_lean_contracts_cannot_be_mistaken_for_each_other():
    text = wire()
    with pytest.raises(ValueError): Snapshot.decode(text)
    with pytest.raises(ValueError): LeanSnapshot.decode(text.replace('GLF1', 'GLR1', 1))
    s = LeanSnapshot.decode(text)
    with pytest.raises(ValueError): s.require_events([], baseline=s)
    ext = closure(s)
    with pytest.raises(ValueError): Closure.decode('GLF1 00010000 5 91 60000000 '+' '.join(f'{v:08x}' for v in ext.words))
    with pytest.raises(ValueError): ext.require_event_support([])


@pytest.mark.parametrize('word,value', [(17, 1), (18, 1), (34, 1), (36, 1), (38, 1),
    (44, 1), (46, 1), (50, 1), (51, 1), (52, 1), (53, 1), (55, 1), (61, 1),
    (61, 2), (61, 4), (20, 92), (0, 123), (2, 999), (19, 0)])
def test_live_binding_rejects_faults_legacy_work_wrong_visit_and_bad_endpoints(word, value):
    s = LeanSnapshot.decode(wire(active=True))
    w = list(s.words); w[word] = value
    with pytest.raises(ValueError):
        replace(s, words=tuple(w)).require_live_prefix(expected_visit=91, received_samples=750)


@pytest.mark.parametrize('received', [0, -1, 1001, True, 750.0])
def test_live_binding_cannot_attest_unreceived_or_unadmitted_samples(received):
    with pytest.raises(ValueError):
        LeanSnapshot.decode(wire(active=True)).require_live_prefix(expected_visit=91, received_samples=received)


def test_lean_closure_checks_source_and_zero_legacy_without_selected_to_scored_equation():
    s = LeanSnapshot.decode(wire())
    w = list(s.words); w[:8] = [0]*8; w[19] = 0
    baseline = replace(s, words=tuple(w), generation=4)
    final_w = list(s.words); final_w[30] = 21
    s = replace(s, words=tuple(final_w))
    closure(s).require_complete(s, baseline=closure(baseline, initial=True), base_snapshot=baseline)


@pytest.mark.parametrize('word,value', [(0, 3), (1, 1), (4, 1), (8, 1), (10, 1), (12, 1), (14, 1)])
def test_lean_closure_rejects_unsettled_or_legacy_extension(word, value):
    s = LeanSnapshot.decode(wire())
    w = list(s.words); w[:8] = [0]*8; w[19] = 0
    base = replace(s, words=tuple(w), generation=4)
    ext = closure(s); ew = list(ext.words); ew[word] = value
    with pytest.raises(ValueError):
        replace(ext, words=tuple(ew)).require_complete(s, baseline=closure(base, initial=True), base_snapshot=base)

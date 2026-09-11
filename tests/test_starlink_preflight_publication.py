"""Source-bound ordering checks and an abstract ownership state exploration.

The graph is a conservative timing abstraction, NOT RTL formal verification.
Its assumptions are checked against the pinned source and real FFT bench.
"""
from collections import deque
import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
BASE=ROOT.parent/'staged-guardfacts-prepared-v1'
spec=importlib.util.spec_from_file_location('preflight_publication',ROOT/'tools/staged_fft_experiment.py')
experiment=importlib.util.module_from_spec(spec);spec.loader.exec_module(experiment)

def test_runtime_unchanged_and_publication_order(tmp_path):
    receipt=experiment.prepare(tmp_path/'inputs')
    experiment.verify(tmp_path/'inputs',receipt['sha256sums'])
    for name in (tmp_path/'inputs/profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split():
        if name not in {'starlink_pss_fft_staged_output_impl.v','starlink_pss_input_identity_stage.v',
                        'starlink_pss_realtime_input_guard_staged_identity.v','starlink_pss_result_guard_owner_view.v',
                        'starlink_pss_product_identity_split_capacity.v','starlink_pss_product_mailbox_staged_identity.v',
                        'starlink_pss_mailbox_split_metadata_view.v',
                        'starlink_pss_mailbox_reset_receipt.v','starlink_pss_output_reset_receipt.v',
                        'starlink_pss_reset_receipt_barrier.v','starlink_pss_completion_mailbox_stage.v'}:
            assert (tmp_path/'inputs'/name).read_bytes()==(BASE/name).read_bytes(),name
    top=(RTL/'starlink_pss_fft_staged_output_impl.v').read_text()
    # Current top has a complete input-stage inverse in its dedicated tests.
    assert hashlib.sha256((BASE/'starlink_pss_fft_staged_output_impl.v').read_bytes()).hexdigest()=='b3511a70b97b91e3e9b4106ea0c9bab8df4f7a43a07ff30a5447cd522dc5d143'
    assert 'if (output_published_valid) begin retained_published<=1;producer_transfer_receipt<=1;end' in top
    assert '(next_inverse ? producer_transfer_receipt : (!guard_busy[0] && forward_committed && product_bank_valid))' in top
    assert 'ACK_DRAIN: if (completion_receipt)' in top
    adapter=(RTL/'starlink_pss_staged_mailbox_control.v').read_text()
    assert 'if (bank_request !== !initial_request ||' in adapter
    assert 'if (!publication_seen) begin publication_seen<=1;published_pending<=1;end' in adapter

def transitions(s,mutant=None):
    stage,inverse,bank,receipt=s
    # State stalls are implicit. Reset purges core, bank and publication token.
    yield 'reset',('prep',False,'empty',False)
    if stage=='prep' and (not inverse or bank=='empty'):
        yield 'admit',('run',inverse,'owned' if inverse else bank,receipt)
    if stage=='run':
        yield 'private_complete',('drain',inverse,'replay' if inverse else bank,
                                receipt or (inverse and mutant=='private_receipt'))
    if stage=='drain' and (not inverse or receipt or mutant=='ungated_close'):
        yield 'close',('prep',not inverse,bank,False if inverse else receipt)
    if bank=='replay':
        # Real bank request observed before publication receipt can exist.
        yield 'actual_publication',(stage,inverse,'published',True)
    if bank=='published':
        yield 'reader_release',(stage,inverse,'empty',receipt)

def explore(mutant=None):
    initial=('prep',False,'empty',False)
    seen={initial};pending=deque([(initial,[])])
    unread_preflight=False
    while pending:
        s,trace=pending.popleft()
        if s[0]=='prep' and s[2]=='replay':return seen,trace,unread_preflight
        unread_preflight|=s[0]=='prep' and s[2]=='published'
        for event,next_state in transitions(s,mutant):
            if next_state not in seen:
                seen.add(next_state);pending.append((next_state,trace+[(event,next_state)]))
    return seen,None,unread_preflight

def test_abstract_publication_order_and_unread_overlap():
    states,counterexample,unread=explore()
    assert len(states)>=10 and counterexample is None and unread

@pytest.mark.parametrize('mutant',['private_receipt','ungated_close'])
def test_early_close_models_have_counterexample(mutant):
    _,trace,_=explore(mutant)
    assert trace is not None and trace[-1][1][0]=='prep' and trace[-1][1][2]=='replay'
    assert all(event!='actual_publication' for event,_ in trace)

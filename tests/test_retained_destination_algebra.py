"""Source-bound four-state scalar experiment only; no vendor or RTL writes."""
import hashlib
import re

import pytest

from tests.starlink_oracle import retained_destination_algebra as p


def test_source_closure_and_literal_preflight():
    src = p.source_texts()
    generated = p.bench()
    for name in ('preflight_events_now', 'preparation_fault_now', 'external_fault_now',
                 'offered_external_fault_now', 'original_common_current_fault',
                 'offered_common_current_fault', 'destination_reserved'):
        assert generated.count(p.statement(src['top'], name)) == 1
    assert p.statement(src['mailbox'], 'input_ready', 'assign') in generated
    assert hashlib.sha256(src['owner'].encode()).hexdigest() == p.PINS['owner'][1]
    for name in ('external_fault_now', 'offered_external_fault_now'):
        copied = p.statement(generated, 'scalar_' + name)
        assert copied.replace('scalar_' + name, name, 1) == p.statement(src['top'], name)


@pytest.mark.parametrize('name', p.PINS)
def test_rehashed_source_cannot_replace_pinned_input(tmp_path, name):
    for key, (relative, _) in p.PINS.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((p.SNAPSHOT / relative).read_bytes() + (b'\n' if key == name else b''))
    with pytest.raises(ValueError, match='source pin'):
        p.bench(tmp_path)


def test_four_state_source_bound_experiment(tmp_path):
    result = p.run(tmp_path / 'algebra')
    assert result.returncode == 0, result.stdout + result.stderr
    p.verify_receipt(result.stdout + result.stderr)


@pytest.mark.parametrize('kind', ['current', 'reason', 'knownness', 'fallback'])
def test_missing_context_or_independent_fault_rejected(tmp_path, kind):
    text = p.bench()
    if kind in ('current', 'reason'):
        before = p.statement(text, 'scalar_offered_external_fault_now')
        token = 'retained_fault_now' if kind == 'current' else '(|retained_reasons)'
        assert before.count(token) == 1
        after = before.replace(token, "1'b0")
    else:
        before = p.statement(text, 'contextual_common')
        after = (before.replace(' && reserved_known', '') if kind == 'knownness' else
                 before.replace(': common_current_fault;', ": 1'b0;"))
    result = p.run(tmp_path / kind, (before, after))
    assert result.returncode != 0
    assert 'DESTINATION_CONTEXTUAL_EQUIVALENCE_FAILED' in result.stdout
    assert 'DESTINATION_ALGEBRA_PASS' not in result.stdout


@pytest.mark.parametrize('kind', ['bare', 'missing', 'duplicate', 'wrong_count', 'wrong_witness', 'late_error'])
def test_receipt_rejects_missing_or_fabricated_proof(kind):
    # A recorded expected shape is parser-only data, never simulation evidence.
    log = ('DESTINATION_RAW_COUNTEREXAMPLE R=1 B=1 request=0 ack=0 reserve=x '
           'published=0 expected=0 lease=00 held=00 reason=00 current=0 phase=1 '
           'preparing=1 P=0 old_vector=0x0000 old=x raw=0 tight=1\n'
           'DESTINATION_ALGEBRA_PASS owners=98304 signatures=110 contexts=333056 '
           'known_equal=236288 fallback_equal=124416 raw_differences=72 tightened=384 '
           'clean_equal=5153 roots=13824 lemmas=2916\n')
    p.verify_receipt(log)
    malformed = {
        'bare': 'DESTINATION_ALGEBRA_PASS\n',
        'missing': log.splitlines()[1] + '\n',
        'duplicate': log + log,
        'wrong_count': log.replace('contexts=333056', 'contexts=0'),
        'wrong_witness': log.replace('old=x raw=0', 'old=0 raw=0'),
        'late_error': log + 'ERROR after terminal\n',
    }[kind]
    with pytest.raises(ValueError, match='destination'):
        p.verify_receipt(malformed)

"""Only additive witnesses; original full numerical/frame/service verifier runs first."""
import pytest

from tests.starlink_oracle import retained_summary_actual as c


@pytest.fixture(scope='module')
def scripted(tmp_path_factory):
    path = tmp_path_factory.mktemp('summary_script') / 'run'
    assert c.offline(path) == {'compile': 0, 'script_exit': 0, 'kind': 'OFFLINE_SCRIPT_NOT_FFT', 'service_executed': False}
    return path


def test_strict_whole_bench_and_four_compiled_path_inverse():
    c.verify_sources()
    assert c.inverse_bench(c.bench()) == c.qualified.bench()
    baseline, current = c.qualified.compiled_sources(), c.compiled_sources()
    assert len(baseline) == len(current) == 26
    assert sum(a != b for a, b in zip(baseline, current, strict=True)) == 4
    assert all(a == b or (a.name == b.name and b.parent == c.candidate.RTL)
               for a, b in zip(baseline, current, strict=True))
    text = c.bench()
    assert text.count('.completed_input_fault_now(candidate_original_completed_input_fault)') == 3
    assert 'unconditional owner0 mailbox_input_metadata' in text
    assert 'unconditional owner1 descriptor' in text


def test_script_all_original_data_and_two_summary_receipts(scripted):
    result = c.verify_result(scripted / 'simulation.log', scripted / 'actual_words.csv', kind='OFFLINE_SCRIPT_NOT_FFT')
    assert result['numerical_words'] == 77953
    assert result['parser_only_not_execution_proof'] is True
    assert sum(map(len, result['candidate'].values())) == 44
    assert sum(map(len, result['offer_summary'].values())) == 2


def test_complete_script_bytes_and_parsed_result_equal_qualified(scripted, tmp_path):
    original = tmp_path / 'qualified_control'
    assert c.qualified.offline(original)['script_exit'] == 0
    assert (original / 'actual_words.csv').read_bytes() == (scripted / 'actual_words.csv').read_bytes()
    expected = c.qualified.verify_result(original / 'simulation.log', original / 'actual_words.csv', kind='OFFLINE_SCRIPT_NOT_FFT')
    result = c.verify_result(scripted / 'simulation.log', scripted / 'actual_words.csv', kind='OFFLINE_SCRIPT_NOT_FFT')
    del result['offer_summary']
    assert result == expected


@pytest.mark.parametrize('token', ['INPUT_OFFER_FAULT_SUMMARY=1', 'summary exact per-owner',
    'summary original physical', 'summary known input fault', 'summary_unknown=0',
    'actual48 input', 'actual causal frame', 'candidate_original_completed_input_fault',
    'candidate binding 1', 'unconditional owner1 descriptor'])
def test_whole_inverse_rejects_old_or_new_checker_edits(token):
    text = c.bench(); assert token in text
    with pytest.raises(ValueError, match='inverse'):
        c.inverse_bench(text.replace(token, token + '_mutant', 1))


@pytest.mark.parametrize('prefix', ['RSUMMARY_FLAGS', 'RSUMMARY_PROOF', 'RCAND_PROOF', 'RACT_FRAME'])
@pytest.mark.parametrize('change', ['missing', 'duplicate'])
def test_no_synthesized_old_or_new_markers(scripted, tmp_path, prefix, change):
    lines = (scripted / 'simulation.log').read_text().splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith(prefix + ' '))
    if change == 'missing': lines.pop(index)
    else: lines.insert(index, lines[index])
    log = tmp_path / 'parser_only.log'; log.write_text('\n'.join(lines) + '\n')
    with pytest.raises(ValueError): c.verify_result(log, scripted / 'actual_words.csv', kind='OFFLINE_SCRIPT_NOT_FFT')


@pytest.mark.parametrize('prefix,field', [('RSUMMARY_FLAGS', x) for x in ('wrapper', 'top', 'cutover', 'owner0', 'owner1')]
    + [('RSUMMARY_PROOF', x) for x in ('pre', 'post', 'zero_pre', 'zero_post', 'known_one', 'unknown',
                                      'forward', 'inverse', 'ends', 'routed')])
def test_every_summary_field_mutant(scripted, tmp_path, prefix, field):
    lines = (scripted / 'simulation.log').read_text().splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith(prefix + ' '))
    tokens = lines[index].split(); k = next(i for i, t in enumerate(tokens) if t.startswith(field + '='))
    tokens[k] = field + '=-1'; lines[index] = ' '.join(tokens)
    log = tmp_path / 'parser_only.log'; log.write_text('\n'.join(lines) + '\n')
    with pytest.raises(ValueError): c.verify_result(log, scripted / 'actual_words.csv', kind='OFFLINE_SCRIPT_NOT_FFT')


@pytest.mark.parametrize('mutation', ['extra_field', 'extra_marker', 'fatal', 'count_plus_one', 'numerical'])
def test_no_failure_numeric_or_input_join_relaxation(scripted, tmp_path, mutation):
    log = tmp_path / 'parser_only.log'; csv = tmp_path / 'parser_only.csv'
    text = (scripted / 'simulation.log').read_text(); words = (scripted / 'actual_words.csv').read_text()
    if mutation == 'extra_field': text = text.replace('RSUMMARY_FLAGS ', 'RSUMMARY_FLAGS undeclared=0 ', 1)
    elif mutation == 'extra_marker': text += 'RSUMMARY_UNKNOWN anything=0\n'
    elif mutation == 'fatal': text += 'FATAL_ERROR: injected simulator failure\n'
    elif mutation == 'count_plus_one':
        import re
        text = re.sub(r'(RSUMMARY_PROOF .*?forward=)(\d+)', lambda m: m[1] + str(int(m[2]) + 1), text, count=1)
    else:
        rows = words.splitlines(); fields = rows[1].split(','); fields[4] = '000000000001'; rows[1] = ','.join(fields)
        words = '\n'.join(rows) + '\n'
    log.write_text(text); csv.write_text(words)
    with pytest.raises(ValueError): c.verify_result(log, csv, kind='OFFLINE_SCRIPT_NOT_FFT')


def test_executed_wrong_option_readback_fails(tmp_path):
    text = c.bench(); token = 'dut.INPUT_OFFER_FAULT_SUMMARY=1'
    assert text.count(token) == 1
    status = c.offline(tmp_path / 'wrong-option', text=text.replace(token, 'dut.INPUT_OFFER_FAULT_SUMMARY=0', 1))
    assert status['compile'] == 0 and status['script_exit'] != 0
    assert 'summary option forwarding readback' in (tmp_path / 'wrong-option/simulation.log').read_text()

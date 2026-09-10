"""Causal frame checks: directed scripted producer, not a vendor latency model."""
import csv
import hashlib
import re

import pytest

from tests.starlink_oracle import retained_frame_contract as f
from tests.starlink_oracle import retained_output_actual as a
from tests.starlink_oracle.retained_output_actual_result import verify_result


def records(path):
    result = {}
    for line in path.read_text().splitlines():
        if line.startswith('RACT_'):
            result.setdefault(line.split()[0], []).append(
                {k: int(v) for k, v in (s.split('=') for s in line.split()[1:])})
    return result


@pytest.fixture(scope='module')
def scripted(tmp_path_factory):
    path = tmp_path_factory.mktemp('causal_frame_script') / 'run'
    assert a.offline(path, execute=True)['script_exit'] == 0
    verify_result(path / 'simulation.log', path / 'actual_words.csv', kind='OFFLINE_SCRIPT_NOT_FFT')
    return path


def test_exact_v4_source_and_parser_inverses():
    assert hashlib.sha256(f.inverse((a.RTL / 'witness.svh').read_text()).encode()).hexdigest() == f.ORIGINAL_WITNESS_SHA
    assert hashlib.sha256(f.inverse(a.actual_bench(), bench=True).encode()).hexdigest() == f.ORIGINAL_BENCH_SHA
    text = (a.ROOT / 'tests/starlink_oracle/retained_output_actual_result.py').read_text()
    assert hashlib.sha256(f.inverse_result(text).encode()).hexdigest() == f.ORIGINAL_RESULT_SHA
    assert 'legacy' not in text


@pytest.mark.parametrize('needle', [
    'actual_epoch_release!=actual_admit+2', 'actual_config_cycle!=actual_admit+3',
    'actual_frames!=0', 'actual_inputs<1', 'actual_raw!=0', 'actual_frame_cycle>=fast_cycles',
    "`D.event_frame!==1'b0", 'actual_frame_cycle+1', 'actual_frame_before=actual_inputs_before',
    'actual_frame_on=actual_input_on', 'actual_frame_after=actual_inputs', 'actual raw packed payload',
])
def test_frame_whole_source_inverse_mutants(needle):
    text = (a.RTL / 'witness.svh').read_text()
    assert needle in text
    with pytest.raises(ValueError, match='inverse'):
        f.inverse(text.replace(needle, needle + '_MUTANT', 1))


@pytest.mark.parametrize('addition', f.RESULT_ADDITIONS)
def test_legacy_parser_projection_cannot_omit_new_join(addition):
    text = (a.ROOT / 'tests/starlink_oracle/retained_output_actual_result.py').read_text()
    with pytest.raises(ValueError, match='inverse'):
        f.inverse_result(text.replace(addition, '', 1))


def test_all_40_frame_owners_and_aborted_prefixes(scripted):
    r = records(scripted / 'simulation.log')
    assert len(r['RACT_FRAME']) == 40
    assert {x['job'] for x in r['RACT_FRAME']} == set(range(1, 41))
    assert [(x['job'], x['before'], x['on'], x['after']) for x in r['RACT_FRAME'] if x['job'] in (33, 38)] == [(33, 0, 1, 1), (38, 0, 1, 1)]
    assert all(x['end_cycle'] == x['cycle']+1 for x in r['RACT_FRAME'])
    assert hashlib.sha256((scripted / 'actual_words.csv').read_bytes()).hexdigest() == '07321b026a637e5922c56a84a955e58549056337198c952a9d73b1245cb4efaa'


def test_new_verifier_never_accepts_legacy_missing_frame_log(scripted, tmp_path):
    text = (scripted / 'simulation.log').read_text()
    lines = [line for line in text.splitlines() if not line.startswith('RACT_FRAME ')]
    path = tmp_path / 'legacy_parser_only.log'
    path.write_text('\n'.join(lines)+'\n')
    with pytest.raises(ValueError, match='exact marker inventory'):
        verify_result(path, scripted / 'actual_words.csv', kind='OFFLINE_SCRIPT_NOT_FFT')


def event_adapter(expression):
    """Only a directed producer event override; never compiled in actual profile."""
    original = a.scripted_padding_adapter()
    old = '(s_axis_data_tvalid&&s_axis_data_tready&&input_count==0) : extra_frame;'
    assert original.count(old) == 1
    new = f'(aresetn&&configured&&({expression})) : extra_frame;'
    adapted = original.replace(old, new, 1)
    assert adapted.replace(new, old, 1) == original
    return adapted


@pytest.mark.parametrize('position,expression', [
    ('idle_gap', 'age==2'),
    ('mixed_later', '(config_count==33||config_count==38) ? age==4 : (config_count%3==0 ? age==1293 : (config_count%3==1 ? age==4 : age==514))'),
])
def test_causal_positions_do_not_fit_third_word(tmp_path, monkeypatch, position, expression):
    script = event_adapter(expression)
    monkeypatch.setattr(a, 'scripted_padding_adapter', lambda: script)
    run = tmp_path / position
    assert a.offline(run, execute=True)['script_exit'] == 0
    verify_result(run / 'simulation.log', run / 'actual_words.csv', kind='OFFLINE_SCRIPT_NOT_FFT')
    r = records(run / 'simulation.log')['RACT_FRAME']
    assert len(r) == 40
    if position == 'idle_gap':
        assert {(x['before'], x['on'], x['after']) for x in r} == {(1, 0, 1)}
    else:
        assert {(x['before'], x['on'], x['after']) for x in r} == {(2, 1, 3), (512, 0, 512)}
        assert {x['cycle']-x['admit'] for x in r} == {8, 518, 1297}
    assert hashlib.sha256((run / 'actual_words.csv').read_bytes()).hexdigest() == '07321b026a637e5922c56a84a955e58549056337198c952a9d73b1245cb4efaa'


@pytest.mark.parametrize('name,expression', [
    ('before_input', 'age==0'), ('held_two_cycles', 'age==1||age==2'),
    ('duplicate', 'age==1||age==4'), ('missing', "1'b0"),
    ('raw_same_cycle', 'age==1294'), ('after_first_raw', 'age==1295'),
    ('unknown_x', "1'bx"), ('unknown_z', "1'bz"),
])
def test_bad_producer_frame_events_reject(tmp_path, monkeypatch, name, expression):
    script = event_adapter(expression)
    monkeypatch.setattr(a, 'scripted_padding_adapter', lambda: script)
    run = tmp_path / name
    status = a.offline(run, execute=True)
    assert status['compile'] == 0 and status['script_exit'] != 0
    assert re.search(r'\bfatal\b', (run / 'simulation.log').read_text(), re.I)
    with pytest.raises(ValueError, match='fatal/error'):
        verify_result(run / 'simulation.log', run / 'actual_words.csv', kind='OFFLINE_SCRIPT_NOT_FFT')


@pytest.mark.parametrize('field', 'context job inverse fixture start admit release config cycle end_cycle before on after'.split())
@pytest.mark.parametrize('delta', [-1, 1])
def test_each_frame_receipt_field_mutation(scripted, tmp_path, field, delta):
    text = (scripted / 'simulation.log').read_text()
    old = next(line for line in text.splitlines() if line.startswith('RACT_FRAME '))
    value = int(re.search(rf'\b{field}=(-?\d+)', old).group(1))
    new = re.sub(rf'\b{field}=-?\d+', f'{field}={value+delta}', old)
    log = tmp_path / 'parser_only.log'
    log.write_text(text.replace(old, new, 1))
    with pytest.raises(ValueError, match='frame'):
        verify_result(log, scripted / 'actual_words.csv', kind='OFFLINE_SCRIPT_NOT_FFT')


@pytest.mark.parametrize('kind', ['missing', 'duplicate', 'stale_job', 'swapped_releases',
                                 'reset_other_context', 'release_other_cycle', 'before_input',
                                 'raw_same_cycle', 'after_raw', 'wrong_physical_count'])
def test_frame_lifecycle_counterexamples(scripted, tmp_path, kind):
    lines = (scripted / 'simulation.log').read_text().splitlines()
    indexes = [i for i, line in enumerate(lines) if line.startswith('RACT_FRAME ')]
    i = indexes[0]
    r = records(scripted / 'simulation.log')
    if kind == 'missing':
        lines.pop(i)
    elif kind == 'duplicate':
        lines.insert(i, lines[i])
    elif kind == 'stale_job':
        lines[indexes[1]] = lines[i]
    elif kind == 'swapped_releases':
        releases = [i for i, line in enumerate(lines) if line.startswith('RACT_RESET_RELEASE ')]
        lines[releases[0]], lines[releases[1]] = lines[releases[1]], lines[releases[0]]
    elif kind.startswith('release_') or kind == 'reset_other_context':
        n = next(i for i, line in enumerate(lines) if line.startswith('RACT_RESET_RELEASE '))
        field = 'context' if kind == 'reset_other_context' else 'cycle'
        value = r['RACT_RESET_RELEASE'][0][field]
        lines[n] = re.sub(rf'\b{field}=\d+', f'{field}={value+1}', lines[n])
    else:
        j = r['RACT_JOB'][0]
        cycle = {'before_input': j['input_first']-1, 'raw_same_cycle': j['raw_first'],
                 'after_raw': j['raw_first']+1}.get(kind, j['input_first'])
        before, on = (0, 0) if kind == 'before_input' else (512, 0)
        for field, value in {'cycle': cycle, 'end_cycle': cycle+1, 'before': before,
                             'on': on, 'after': before+on}.items():
            lines[i] = re.sub(rf'\b{field}=\d+', f'{field}={value}', lines[i])
    log = tmp_path / 'parser_only.log'
    log.write_text('\n'.join(lines)+'\n')
    with pytest.raises(ValueError):
        verify_result(log, scripted / 'actual_words.csv', kind='OFFLINE_SCRIPT_NOT_FFT')


def test_physical_input_shift_cannot_authorize_forged_frame(scripted, tmp_path):
    with (scripted / 'actual_words.csv').open(newline='') as stream:
        reader = csv.DictReader(stream)
        header, rows = reader.fieldnames, list(reader)
    row = next(r for r in rows if r['stream'] == 'inputF')
    row['fast'] = str(int(row['fast'])-1)
    row['time_fs'] = str(int(row['time_fs'])-5714286)
    row['slow'] = str(((int(row['time_fs'])-1300000)//5000000+1)//2)
    path = tmp_path / 'parser_only.csv'
    with path.open('w', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=header)
        writer.writeheader();writer.writerows(rows)
    with pytest.raises(ValueError, match='input row/job ordinal time join'):
        verify_result(scripted / 'simulation.log', path, kind='OFFLINE_SCRIPT_NOT_FFT')

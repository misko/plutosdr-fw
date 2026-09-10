"""Offline original21014 transition diagnosis; no vendor invocation or edits."""
import copy
import csv
import importlib.util
from pathlib import Path

import pytest

HERE = Path(__file__).parent
RUN = Path('/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/'
           'inverse-actual-prepared-v1.sUupdgsv/inverse-sealed-actual-R1B1O1L1E1-175-prepared-v1')
SIM = RUN / 'project/fft_bank_arithmetic_actual.sim/sim_1/behav/xsim'


def load(path):
    spec = importlib.util.spec_from_file_location('transition_' + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TIMING = load(HERE / 'inverse_sealed_actual_timing.py')
FROZEN = load(RUN / 'frozen_sources/inverse_sealed_actual_timing.py')


@pytest.fixture(scope='module')
def transition_rows():
    rows = []
    with (SIM / 'fft_bank_owned_trace.csv').open() as stream:
        for row in csv.DictReader(stream):
            if int(row['epoch']) == 1:
                rows.append(row)
            if int(row['cycle']) == 146692:
                break
    assert rows[-2]['cycle'] == '146691' and rows[-2]['profile'] == '1'
    assert rows[-1]['running'] == '0'
    return rows


def write_rows(path, rows):
    with path.open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=TIMING.TRACE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_original_collector_failure_is_preserved_and_exact():
    with pytest.raises(ValueError, match='healthy trace profile/fault'):
        FROZEN.parse_trace(SIM / 'fft_bank_owned_trace.csv')
    outcome = (RUN / 'run_outcome.txt').read_text()
    assert outcome.startswith('run_status=1\n') and '\nafter_status=0\n' in outcome
    assert not (RUN / 'results.json').exists()


def test_full_original_timing_and_protocol_reassessed_not_automation_pass():
    transitions = []
    jobs = TIMING.parse_trace(SIM / 'fft_bank_owned_trace.csv', transitions)
    assert transitions == [{'epoch': 1, 'next_profile': 1, 'first_cycle': 146691,
        'last_cycle': 146691, 'final_admit': 143966, 'final_commit': 145779, 'reset_cycle': 146692}]
    intervals = TIMING.verify_jobs(jobs, True)
    assert set(intervals[1]) == {4554, 4555}
    assert intervals[2] == [4827, 4827, 4835, 4827, 4828]
    ledger = TIMING.verify_event_cycles(SIM / 'bank_arithmetic_events.csv', jobs)
    assert sum(value['count'] for value in ledger.values()) == 3 * 19456
    source = RUN / 'frozen_sources'
    words = lambda name: [int(line, 16) for line in (source / name).read_text().splitlines()]
    assert TIMING.verify_protocol(SIM / 'inverse_sealed_protocol.csv', jobs,
        words('inverse_q17.mem'), words('forward_exponents.mem'), words('inverse_exponents.mem')) == {
        'lifetimes': 38, 'takes': 19456, 'ordered_protocol_events': 19760,
        'qualification_to_publication': 3, 'ack_to_release': 1}


@pytest.mark.parametrize('length', [1, 2])
def test_bounded_completed_idle_transition(length, transition_rows, tmp_path):
    rows = copy.deepcopy(transition_rows)
    if length == 2:
        extra = dict(rows[-2], cycle='146692')
        rows.insert(-1, extra)
        rows[-1]['cycle'] = '146693'
    receipts = []
    jobs = TIMING.parse_trace(write_rows(tmp_path / 'bounded.csv', rows), receipts)
    assert len(jobs) == 64
    assert receipts[0]['reset_cycle'] - receipts[0]['first_cycle'] == length


@pytest.mark.parametrize('field,value', [
    ('admit', '1'), ('config', '1'), ('core_input', '1'), ('core_output', '1'),
    ('status', '1'), ('guard_commit', '1'), ('result_busy', '1'), ('core_resetn', '1'),
    ('source_valid', '1'), ('product_read_valid', '1'), ('product_read_ready', '1'),
    ('forward_committed', '1'), ('product_commit', '1'), ('handoff_ack', '1'),
    ('output_bank_ready', '0'), ('source_ready', '0'), ('state', '7'), ('inverse', '1'),
    ('block_start', '0'), ('fault', '1'), ('fault', 'x'), ('profile', 'x'),
    ('profile', '2'), ('running', 'x'), ('running', '2'), ('source_valid', 'z'),
])
def test_mismatch_cannot_hide_activity_fault_unknown_or_ownership(field, value, transition_rows, tmp_path):
    rows = copy.deepcopy(transition_rows)
    rows[-2][field] = value
    with pytest.raises(ValueError):
        TIMING.parse_trace(write_rows(tmp_path / 'bad.csv', rows))


@pytest.mark.parametrize('mutation', ['missing_job', 'missing_raw', 'missing_input', 'missing_commit',
    'wrong_identity', 'duplicate_admit', 'third_row', 'truncated', 'cycle_gap',
    'epoch_changed_without_reset', 'reset_unknown', 'reset_fault', 'reset_event',
    'reset_profile', 'resume_old_profile', 'resume_after_reset'])
def test_incomplete_epoch_or_unbounded_reset_transition_rejected(mutation, transition_rows, tmp_path):
    rows = copy.deepcopy(transition_rows)
    if mutation == 'missing_job':
        rows = [row for row in rows if int(row['cycle']) >= 5500]
    elif mutation in ('missing_raw', 'missing_input', 'missing_commit'):
        key = {'missing_raw': 'core_output', 'missing_input': 'core_input', 'missing_commit': 'guard_commit'}[mutation]
        next(row for row in reversed(rows) if row[key] == '1')[key] = '0'
    elif mutation == 'wrong_identity':
        next(row for row in reversed(rows) if row['admit'] == '1')['block_start'] = '0'
    elif mutation == 'duplicate_admit':
        next(row for row in rows if row['core_output'] == '1')['admit'] = '1'
    elif mutation == 'third_row':
        rows[-1]['cycle'] = '146694'
        rows[-1:-1] = [dict(rows[-2], cycle=str(cycle)) for cycle in (146692, 146693)]
    elif mutation == 'truncated':
        rows.pop()
    elif mutation == 'cycle_gap':
        rows[-1]['cycle'] = '146693'
    elif mutation == 'epoch_changed_without_reset':
        rows[-1]['epoch'] = '2'
    elif mutation in ('reset_unknown', 'reset_fault', 'reset_event', 'reset_profile'):
        key, value = {'reset_unknown': ('state', 'x'), 'reset_fault': ('fault', '1'),
            'reset_event': ('core_output', '1'), 'reset_profile': ('profile', '0')}[mutation]
        rows[-1][key] = value
    elif mutation == 'resume_old_profile':
        rows[-1] = dict(rows[-2], cycle='146692', profile='0')
    else:
        rows.append(dict(rows[-2], cycle='146693', profile='0'))
    with pytest.raises(ValueError):
        TIMING.parse_trace(write_rows(tmp_path / 'bad.csv', rows))

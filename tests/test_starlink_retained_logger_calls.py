"""Logging compatibility proof, with full CSV equality to the frozen v3 bench."""
import hashlib

import pytest

from tests.starlink_oracle import retained_logger_calls as calls
from tests.starlink_oracle import retained_output_actual as a
from tests.starlink_oracle import retained_frame_contract as frames


def legacy_verifier():
    """Test-only exact v4 parser; the live verifier has no legacy mode."""
    source = frames.inverse_result((a.ROOT / 'tests/starlink_oracle/retained_output_actual_result.py').read_text())
    namespace = {'__name__': 'tests.starlink_oracle._v4_logging_regression',
                 '__package__': 'tests.starlink_oracle'}
    exec(compile(source, '<strict-v4-logger-regression>', 'exec'), namespace)
    return namespace['verify_result']


def test_whole_witness_and_bench_inverse():
    calls.inverse(frames.inverse((a.RTL / 'witness.svh').read_text()))
    old_bench = calls.inverse(frames.inverse(a.actual_bench(), bench=True), bench=True)
    assert hashlib.sha256(old_bench.encode()).hexdigest() == calls.ORIGINAL_BENCH_SHA


@pytest.mark.parametrize('kind', ['old_site', 'missing_else', 'duplicate_site', 'swapped_phase',
                                  'changed_argument', 'changed_format', 'changed_task', 'changed_check'])
def test_literal_calls_inverse_mutants(kind):
    text = frames.inverse((a.RTL / 'witness.svh').read_text())
    old, new = calls.replacements()[0]
    if kind == 'old_site':
        text = text.replace(new, old)
    elif kind == 'missing_else':
        text = text.replace(new, new.splitlines(keepends=True)[0])
    elif kind == 'duplicate_site':
        text = text.replace(new, new + new)
    elif kind == 'swapped_phase':
        text = text.replace('if(actual_inverse)actual_word("inputI"', 'if(actual_inverse)actual_word("inputF"')
    elif kind == 'changed_argument':
        text = text.replace(new, new.replace('actual_inputs,', 'actual_inputs+1,'))
    elif kind == 'changed_format':
        text = text.replace('%012h', '%013h')
    elif kind == 'changed_task':
        text = text.replace('task automatic actual_word', 'task actual_word')
    else:
        text = text.replace('actual raw packed payload/index/exponent', 'MUTATED_CHECK')
    with pytest.raises(ValueError, match='inverse'):
        calls.inverse(text)


def test_full_scripted_csv_is_byte_identical_to_v3(tmp_path):
    new_bench = frames.inverse(a.actual_bench(), bench=True)
    old_bench = calls.inverse(new_bench, bench=True)
    verify_result = legacy_verifier()
    for name, bench in (('original_v3', old_bench), ('literal_calls', new_bench)):
        run = tmp_path / name
        assert a.offline(run, execute=True, bench=bench) == {
            'compile': 0, 'service_executed': False, 'kind': 'OFFLINE_SCRIPT_NOT_FFT', 'script_exit': 0}
        result = verify_result(run / 'simulation.log', run / 'actual_words.csv', kind='OFFLINE_SCRIPT_NOT_FFT')
        assert result['numerical_words'] == 77953
        assert result['terminal']['pairs'] == 19
    original = (tmp_path / 'original_v3/actual_words.csv').read_bytes()
    current = (tmp_path / 'literal_calls/actual_words.csv').read_bytes()
    assert current == original
    assert hashlib.sha256(current).hexdigest() == calls.ORIGINAL_CSV_SHA
    logs = []
    finish_lines = []
    for name, bench in (('original_v3', old_bench), ('literal_calls', new_bench)):
        locations = [i for i, line in enumerate(bench.splitlines(), 1) if line.strip() == '$finish;']
        assert len(locations) == 1
        finish_lines.append(f'{tmp_path / name / "bench.sv"}:{locations[0]}: $finish called at 512702882778 (1fs)\n'.encode())
        logs.append((tmp_path / name / 'simulation.log').read_bytes())
        assert logs[-1].count(finish_lines[-1]) == 1
    # Only Icarus's explicit source filename/line provenance changes (+2 lines).
    assert logs[0].replace(finish_lines[0], finish_lines[1], 1) == logs[1]

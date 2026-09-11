"""Bounded combinational experiment; copies exact pinned RTL, never edits it."""
import hashlib
import os
import re
import subprocess
from pathlib import Path

SNAPSHOT = Path('/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-summary-synth-parent.39BysdkS/synthesis/inputs/source_snapshot')
ACQ = Path('hdl/library/starlink_pss_acquisition')
PINS = {
    'top': (ACQ / 'retained_output_summary_candidate/starlink_pss_fft_retained_output_impl.v',
            '3b98a25b8c5d50a18da1692511ae1647c2969fadf5c55d679278b2d5a7bbf0ff'),
    'owner': (ACQ / 'retained_output/starlink_pss_retained_output_owner.v',
              'b6280f6a894ec120f0e57415d5cc6da7b9e193a65f42b1d7f9789cbdbaa5d648'),
    'mailbox': (ACQ / 'retained_output/starlink_pss_mailbox_owner_view.v',
                'de060a7930be1d65cc91903da447e51ead3efad4ebed4b61e4f257e45d76d2d6'),
}
TEMPLATE = Path(__file__).with_name('tb_retained_destination_algebra.sv')


def source_texts(root=SNAPSHOT):
    result = {}
    for name, (relative, pin) in PINS.items():
        data = (root / relative).read_bytes()
        if hashlib.sha256(data).hexdigest() != pin:
            raise ValueError('destination source pin: ' + name)
        result[name] = data.decode()
    return result


def statement(text, name, kind='wire'):
    matches = re.findall(r'^  ' + kind + r' (?:\[[^\n]+?\] )?' + name + r' =[^;]+;', text, re.M)
    if len(matches) != 1:
        raise ValueError('destination literal statement: ' + name)
    return matches[0]


def bench(root=SNAPSHOT):
    src = source_texts(root)
    originals = '\n'.join(statement(src['top'], name) for name in (
        'destination_reserved', 'preflight_events_now', 'preparation_fault_now',
        'external_fault_now', 'offered_external_fault_now',
        'original_common_current_fault', 'offered_common_current_fault'))
    originals += '\n' + statement(src['top'], 'common_current_fault', 'assign')
    ready = statement(src['mailbox'], 'input_ready', 'assign')
    template = TEMPLATE.read_text()
    if any(template.count(marker) != 1 for marker in
           ('@@ORIGINALS@@', '@@MAILBOX_READY@@', '@@SCALAR_EXTERNALS@@')):
        raise ValueError('destination template marker')
    # Literal name-only copies make each independently retained fault term
    # inspectable/mutable without altering the original full expression.
    scalar = '\n'.join(statement(src['top'], name).replace(name, 'scalar_' + name, 1)
                       for name in ('external_fault_now', 'offered_external_fault_now'))
    return (template.replace('@@ORIGINALS@@', originals).replace('@@MAILBOX_READY@@', ready)
            .replace('@@SCALAR_EXTERNALS@@', scalar))


def verify_receipt(log):
    if re.search(r'FATAL|ERROR|FAIL', log):
        raise ValueError('destination error marker')
    rows = re.findall(r'^DESTINATION_ALGEBRA_PASS (.+)$', log, re.M)
    expected = dict(owners=98304, signatures=110, contexts=333056, known_equal=236288,
                    fallback_equal=124416, raw_differences=72, tightened=384,
                    clean_equal=5153, roots=13824, lemmas=2916)
    if len(rows) != 1 or rows[0] != ' '.join(f'{k}={v}' for k, v in expected.items()):
        raise ValueError('destination terminal inventory')
    witness = ('DESTINATION_RAW_COUNTEREXAMPLE R=1 B=1 request=0 ack=0 reserve=x '
               'published=0 expected=0 lease=00 held=00 reason=00 current=0 phase=1 '
               'preparing=1 P=0 old_vector=0x0000 old=x raw=0 tight=1')
    if re.findall(r'^DESTINATION_RAW_COUNTEREXAMPLE.*$', log, re.M) != [witness]:
        raise ValueError('destination raw counterexample')
    return expected


def run(directory, mutation=None):
    directory.mkdir()
    src = source_texts()
    tb = bench()
    if mutation:
        before, after = mutation
        if tb.count(before) != 1:
            raise ValueError('destination mutation seam')
        tb = tb.replace(before, after)
    (directory / 'tb.sv').write_text(tb)
    (directory / 'owner.v').write_text(src['owner'])
    (directory / 'source-pins.txt').write_text(''.join(f'{pin}  {name}\n' for name, (_, pin) in PINS.items()))
    env = {k: v for k, v in os.environ.items()
           if k not in ('PYTHONHOME', 'PYTHONPATH', 'PYTHONOPTIMIZE', 'LD_LIBRARY_PATH')}
    compile_result = subprocess.run(['iverilog', '-g2012', '-s', 'tb', '-o', 'sim.vvp', 'tb.sv', 'owner.v'],
                                    cwd=directory, env=env, text=True, capture_output=True)
    (directory / 'compile.log').write_text(compile_result.stdout + compile_result.stderr)
    (directory / 'compile.exit').write_text(str(compile_result.returncode) + '\n')
    if compile_result.returncode:
        raise AssertionError('destination compile failed: ' + str(directory))
    result = subprocess.run(['vvp', 'sim.vvp'], cwd=directory, env=env, text=True, capture_output=True)
    (directory / 'run.log').write_text(result.stdout + result.stderr)
    (directory / 'run.exit').write_text(str(result.returncode) + '\n')
    return result

"""Additive offered-summary actual adapter; old complete result authority retained."""
import csv
import json
from pathlib import Path
import subprocess

from . import retained_control_actual as qualified
from . import retained_offer_summary_candidate as candidate

old = qualified.old
ROOT = old.ROOT
RTL = old.original.RTL.parent / 'retained_summary_actual'
RECIPE = Path(__file__).with_name('retained_summary_actual_recipe.json')
RECIPE_SHA = '4831bf1a03f306075aa02483df6497e6e72ebf78b1467415e8e364a3b0e58529'
PINS = {
    'starlink_pss_core_job_cutover.v': 'c67b62486356215a12cd8e9c2b220c5a877a661bd1b15a13b25f9904171ba330',
    'starlink_pss_fft_bank_owned_retained_output_probe.v': '7367d534792385eab3b4264f2e36849b18222e6fe848ef7dbc0887394de8bf94',
    'starlink_pss_fft_retained_output_impl.v': '3b98a25b8c5d50a18da1692511ae1647c2969fadf5c55d679278b2d5a7bbf0ff',
    'starlink_pss_result_guard_owner_view.v': '8b853ee26ab18b4639ab0faf156fd75661f86030773c14f5a9843140c52b5d02',
}


def verify_sources():
    qualified.verify_sources()
    if old.sha(RECIPE) != RECIPE_SHA: raise ValueError('summary recipe identity')
    for name, pin in PINS.items():
        path = candidate.RTL / name
        if path.is_symlink() or old.sha(path) != pin: raise ValueError('summary runtime identity')
        if candidate.inverse(name, path.read_text()) != (qualified.candidate.RTL / name).read_text():
            raise ValueError('summary qualified runtime inverse')


def adaptations():
    verify_sources()
    return [('module tb;', 'module tb;\n  defparam dut.INPUT_OFFER_FAULT_SUMMARY=1;'),
            ('endmodule', (RTL / 'witness.svh').read_text() + '\nendmodule')]


def bench():
    text = qualified.bench()
    for before, after in adaptations():
        if text.count(before) != 1: raise ValueError('summary literal bench boundary')
        text = text.replace(before, after, 1)
    inverse_bench(text)
    return text


def inverse_bench(text):
    for before, after in reversed(adaptations()):
        if text.count(after) != 1: raise ValueError('summary whole bench inverse boundary')
        text = text.replace(after, before, 1)
    if text != qualified.bench(): raise ValueError('summary whole bench inverse mismatch')
    return text


def compiled_sources():
    verify_sources()
    return [candidate.RTL / p.name if p.parent == qualified.candidate.RTL and p.name in PINS else p
            for p in qualified.compiled_sources()]


def offline(directory, *, text=None):
    """Same bounded script runner mechanics, only selected compiled paths differ."""
    verify_sources(); directory.mkdir(parents=True, exist_ok=False)
    for p in old.original.BASELINE.glob('*.mem'): (directory / p.name).write_bytes(p.read_bytes())
    (directory / 'bench.sv').write_text(bench() if text is None else text)
    (directory / 'OFFLINE_NOT_FFT.sv').write_text(old.scripted_padding_adapter())
    command = ['iverilog', '-g2012', '-s', 'tb', '-o', str(directory / 'sim.vvp'), str(directory / 'bench.sv'),
               str(directory / 'OFFLINE_NOT_FFT.sv'), *map(str, compiled_sources())]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    (directory / 'compile.log').write_text(result.stdout + result.stderr)
    status = {'compile': result.returncode, 'kind': 'OFFLINE_SCRIPT_NOT_FFT', 'service_executed': False}
    if result.returncode == 0:
        run = subprocess.run(['vvp', 'sim.vvp'], cwd=directory, capture_output=True, text=True, timeout=60)
        (directory / 'simulation.log').write_text(run.stdout + run.stderr); status['script_exit'] = run.returncode
    (directory / 'status.json').write_text(json.dumps(status, sort_keys=True) + '\n')
    return status


def verify_result(log, numerical, *, kind):
    verify_sources()
    result = qualified.verify_result(log, numerical, kind=kind)
    require = qualified.original_result._require
    records = {}
    for line in log.read_text().splitlines():
        if line.startswith('RSUMMARY_'):
            records.setdefault(line.split()[0], []).append(qualified.original_result._fields(line))
    require({k: len(v) for k, v in records.items()} == {'RSUMMARY_FLAGS': 1, 'RSUMMARY_PROOF': 1},
            'summary marker inventory')
    require(records['RSUMMARY_FLAGS'] == [dict(wrapper=1, top=1, cutover=1, owner0=1, owner1=1)], 'summary flags')
    proof = records['RSUMMARY_PROOF'][0]
    require(set(proof) == {'pre', 'post', 'zero_pre', 'zero_post', 'known_one', 'unknown',
                           'forward', 'inverse', 'ends', 'routed'}, 'summary proof fields')
    require(proof['pre'] >= 1000 and proof['post'] >= 1000 and proof['zero_pre'] == proof['pre'] and
            proof['zero_post'] == proof['post'] and proof['known_one'] == proof['unknown'] == 0,
            'summary enabled observation inventory')
    require(proof['routed'] == 2 * (proof['pre'] + proof['post']), 'summary both-owner routed checks')
    counts = {'inputF': 0, 'inputI': 0}
    with numerical.open() as stream:
        for row in csv.DictReader(stream):
            if row['stream'] in counts: counts[row['stream']] += 1
    require(proof['forward'] == counts['inputF'] and proof['inverse'] == counts['inputI'] and
            proof['ends'] == 38, 'summary physical input CSV/complete-end joins')
    return dict(result, offer_summary=records)

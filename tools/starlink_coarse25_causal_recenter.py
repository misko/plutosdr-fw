"""Pre-filter CFO recentering diagnostic on already-inspected development data.

The CFO comes from the earlier 36.0/36.1/36.2 s pilot receipt, not the later
positive windows. Negative windows precede that receipt and are explicitly
NONCAUSAL controls; do not claim them as a causal operational test.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import starlink_coarse25 as base
from tools import starlink_coarse25_normalized as norm

PRIOR_PLAN = Path('/tmp/starlink-coarse-alternatives.Y3JzOI/narrow-coarse/reports/'
                  'narrow-coarse-20260910-v1/plan.json')


def run(output: Path, *, prior_alias: int = 0) -> None:
    output.mkdir(parents=True, exist_ok=True)
    cases = json.loads((base.ROOT / 'reports/coarse25-screen-20260912/plan.json').read_bytes())['cases']
    prior_bytes = PRIOR_PLAN.read_bytes()
    if base.digest(prior_bytes) != 'cf701ae2ad5c11434469869d2a52b9075ca5a4432211cb6f3b64cbd1d393af66':
        raise ValueError('independent prior provenance changed')
    if prior_alias not in (0, 1):
        raise ValueError('only the two earlier recorded pilot clusters are defined')
    prior_cluster = json.loads(prior_bytes)['positive_prior']['clusters'][prior_alias]
    prior_hz = prior_cluster['median_hz']
    base.write_new(output / 'plan.json', {
        'development_only': True, 'hardware_access': False,
        'code_sha256': base.digest(Path(__file__).read_bytes()),
        'normalized_code_sha256': base.digest(Path(norm.__file__).read_bytes()),
        'base_hashes': base.code_hashes(), 'cases': cases,
        'prior_hz': prior_hz, 'prior_alias_index': prior_alias,
        'prior_cluster': prior_cluster, 'prior_plan_sha256': base.digest(prior_bytes),
        'unchanged_configuration': base.configuration(),
        'negative_prior_is_noncausal': True,
        'change': 'recenter canonical IQ before frozen pilot DDC; normalized correlation'})
    banks = [base.template(cfo)[0] for cfo in base.CFO_BANK]
    results = []
    for case in cases:
        payload = base.source_bytes(case)
        if base.digest(payload) != case['source_window_sha256']:
            raise ValueError('source changed')
        raw = np.frombuffer(payload, dtype='<i2').reshape(-1, 2)
        first = case['center_start'] - base.HALO
        values = raw[:, 0].astype(float) + 1j * raw[:, 1]
        # Local phase origin differs only by a constant carrier phase, which
        # normalized complex-correlation magnitude eliminates.
        values *= np.exp(-2j * np.pi * prior_hz * np.arange(len(raw)) / base.CANONICAL_RATE)
        filtered, centers = base.condition(base.iq(values), first)
        take = (centers >= case['center_start']) & (centers < case['center_start'] + base.WINDOW)
        result = norm.search(filtered[take], centers[take], banks)
        expected = case['historical_pilot_phase_us_for_comparison_only']
        error = (None if expected is None else float(base.circular_distance(
            result['winner']['phase_us'], expected, 4000 / 3)))
        entry = {'case': case['name'], 'result': result,
                 'historical_pilot_phase_error_us': error,
                 'passes_original_criteria': (not result['detected'] if expected is None
                                              else result['detected'] and error <= 2)}
        results.append(entry)
        print(json.dumps({'case': case['name'], 'winner': result['winner'], 'error_us': error}),
              flush=True)
    base.write_new(output / 'result.json', {
        'plan_sha256': base.digest((output / 'plan.json').read_bytes()),
        'development_only': True, 'hardware_access': False, 'real': results})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prior-alias', type=int, choices=(0, 1), default=0)
    args = parser.parse_args()
    run(args.output, prior_alias=args.prior_alias)

"""Development diagnostic: locally normalized coarse PSS, not a release gate.

The first screen used raw matched power, unlike the existing wider-band PSS
oracle. This variant divides by local input energy before frame folding. The
previously inspected real windows are DEVELOPMENT data, never new holdouts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import starlink_coarse25 as base


def normalized_scores(samples: np.ndarray, bank: np.ndarray) -> np.ndarray:
    samples, bank = np.asarray(samples), np.asarray(bank)
    if (samples.ndim != 1 or bank.ndim != 1 or len(bank) < 1
            or len(samples) < len(bank) or not np.all(np.isfinite(samples))
            or not np.all(np.isfinite(bank))):
        raise ValueError('finite one-dimensional samples and nonempty template required')
    template_energy = float(np.vdot(bank, bank).real)
    if template_energy <= 0:
        raise ValueError('template must have positive energy')
    energy = np.convolve(np.abs(samples) ** 2, np.ones(len(bank)), mode='valid')
    numerator = np.abs(np.correlate(samples, bank, mode='valid')) ** 2
    denominator = energy * template_energy
    return np.clip(np.divide(numerator, denominator, out=np.zeros_like(numerator),
                             where=denominator > 0), 0, 1)


def search(samples: np.ndarray, centers: np.ndarray, banks: list[np.ndarray]) -> dict:
    if (len(samples) != len(centers) or len(samples) < 10_000
            or not np.all(np.diff(centers) == 6)):
        raise ValueError('contiguous supported inspection epoch required')
    phase = (((centers[:len(samples) - base.TAPS + 1]
               - base.TEMPLATE_FIRST_CENTER) % 20_000) // 2).astype(int)
    count = np.bincount(phase, minlength=10_000)
    if np.any(count == 0):
        raise ValueError('insufficient phase coverage')
    results = []
    for cfo, bank in zip(base.CFO_BANK, banks, strict=True):
        scores = normalized_scores(samples, bank)
        folded = np.bincount(phase, weights=scores, minlength=10_000) / count
        folded = (np.roll(folded, 1) + folded + np.roll(folded, -1)) / 3
        peak = int(np.argmax(folded))
        background = folded[base.circular_distance(np.arange(10_000), peak, 10_000) > 150]
        mean, sigma = float(np.mean(background)), float(np.std(background))
        z = (float(folded[peak]) - mean) / max(sigma, abs(mean) * 1e-8, 1e-30)
        results.append({'cfo_hypothesis_hz': cfo, 'phase_us': peak * 2 / 15,
                        'peak_z': z, 'peak_normalized_score': float(folded[peak])})
    winner = max(results, key=lambda item: item['peak_z'])
    return {'winner': winner, 'detected': winner['peak_z'] >= base.THRESHOLD,
            'hypotheses': results}


def run(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    original = base.ROOT / 'reports/coarse25-screen-20260912/plan.json'
    cases = json.loads(original.read_bytes())['cases']
    plan = {'schema': 'coarse25-local-energy-development-v1',
            'code_sha256': base.digest(Path(__file__).read_bytes()),
            'base_hashes': base.code_hashes(), 'numpy_version': np.__version__,
            'configuration': base.configuration(), 'cases': cases,
            'previously_inspected_development_data': True,
            'acceptance_unchanged': True, 'hardware_access': False,
            'change': 'normalized match power before identical phase folding'}
    base.write_new(output / 'plan.json', plan)
    banks = [base.template(cfo)[0] for cfo in base.CFO_BANK]
    report = {'plan_sha256': base.digest((output / 'plan.json').read_bytes()),
              'real': [], 'development_only': True, 'hardware_access': False}
    for case in cases:
        payload = base.source_bytes(case)
        if base.digest(payload) != case['source_window_sha256']:
            raise ValueError('source changed since original evaluation')
        values, centers = base.condition(np.frombuffer(payload, dtype='<i2').reshape(-1, 2),
                                        case['center_start'] - base.HALO)
        take = ((centers >= case['center_start'])
                & (centers < case['center_start'] + base.WINDOW))
        result = search(values[take], centers[take], banks)
        expected = case['historical_pilot_phase_us_for_comparison_only']
        error = (None if expected is None else float(base.circular_distance(
            result['winner']['phase_us'], expected, 4000 / 3)))
        passed = (not result['detected'] if expected is None else
                  result['detected'] and error <= 2)
        entry = {'case': case['name'], 'result': result, 'passes_original_criteria': passed,
                 'historical_pilot_phase_error_us': error}
        report['real'].append(entry)
        print(json.dumps(entry), flush=True)
    base.write_new(output / 'result.json', report)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output)

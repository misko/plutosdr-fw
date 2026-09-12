"""5/15 MS/s development control for the failed narrow-band PSS screen.

No FPGA or radio access. The new 5 MS/s Q17 FIR is an experimental response,
not a qualified decimator. Windows are already-inspected development data.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import starlink_coarse25 as base
from tools.starlink_coarse25_normalized import normalized_scores

CFO_BANK = tuple(range(-800000, 800001, 100000))


def fir5() -> np.ndarray:
    n = np.arange(255) - 127
    ratio = 2 * 2350000 / 15000000
    h = ratio * np.sinc(ratio * n) * np.kaiser(255, 7.86)
    h /= h.sum()
    q = np.rint(h * 2**17).astype(np.int64)
    q[127] += 2**17 - q.sum()
    return q


def condition5(x: np.ndarray, first: int) -> tuple[np.ndarray, np.ndarray]:
    # Float evaluation of pinned integer FIR coefficients, not fixed RTL output.
    mixed = x * np.exp(-2j * np.pi * (12 / 64) * np.arange(len(x)))
    out = np.convolve(mixed, fir5() / 2**17, mode='valid')
    newest = np.arange(len(out), dtype=np.int64) + first + 254
    take = newest % 3 == 0
    return out[take], newest[take] - 127


def bank(rate: int, cfo: int) -> tuple[np.ndarray, int]:
    pulse = base.projected_pss(15_000_000, 'upper').astype(complex)
    if rate == 15:
        return pulse * np.exp(2j * np.pi * cfo * np.arange(len(pulse)) / 15_000_000), 0
    x = np.zeros(1800, dtype=complex)
    x[600:600 + len(pulse)] = pulse
    x *= np.exp(2j * np.pi * cfo * np.arange(len(x)) / 15_000_000)
    values, centers = condition5(x, 0)
    take = (centers - 600 >= -16) & (centers - 600 < -16 + 32 * 3)
    assert len(values[take]) == 32
    assert centers[take][0] - 600 == -16
    return values[take], -16


def search(x: np.ndarray, centers: np.ndarray, rate: int) -> dict:
    step = 15 // rate
    if not np.all(np.diff(centers) == step):
        raise ValueError('noncontiguous rate-specific source mapping')
    hypotheses = []
    for cfo in CFO_BANK:
        h, first = bank(rate, cfo)
        score = normalized_scores(x, h)
        phases = (centers[:len(score)] - first) % 20000
        counts = np.bincount(phases, minlength=20000)
        sums = np.bincount(phases, weights=score, minlength=20000)
        # Pool one output-sample-wide support, retaining exact source phase.
        pooled_sum = sum(np.roll(sums, shift) for shift in range(-(step // 2), step // 2 + 1))
        pooled_count = sum(np.roll(counts, shift) for shift in range(-(step // 2), step // 2 + 1))
        if np.any(pooled_count == 0):
            raise ValueError('incomplete phase coverage')
        folded = pooled_sum / pooled_count
        peak = int(np.argmax(folded))
        background = folded[base.circular_distance(np.arange(20000), peak, 20000) > 300]
        mean, sigma = float(np.mean(background)), float(np.std(background))
        z = (float(folded[peak]) - mean) / max(sigma, abs(mean) * 1e-8, 1e-30)
        hypotheses.append({'cfo_hz': cfo, 'phase_us': peak / 15, 'peak_z': z})
    return {'winner': max(hypotheses, key=lambda h: h['peak_z']), 'hypotheses': hypotheses}


def run(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    cases = json.loads((base.ROOT / 'reports/coarse25-screen-20260912/plan.json').read_bytes())['cases']
    base.write_new(output / 'plan.json', {
        'development_only': True, 'hardware_access': False, 'cases': cases,
        'code_sha256': base.digest(Path(__file__).read_bytes()),
        'normalization_code_sha256': base.digest((base.ROOT / 'tools/starlink_coarse25_normalized.py').read_bytes()),
        'base_hashes': base.code_hashes(), 'rates_msps': [5, 15], 'cfo_bank_hz': list(CFO_BANK),
        'five_msps_fir_q17': fir5().tolist(), 'five_msps_fir_hardware_qualified': False,
        'first_screen_threshold_not_recalibrated_for_new_search': 8,
        'positive_comparison_tolerance_us': 2})
    results = []
    for case in cases:
        raw = base.source_bytes(case)
        if base.digest(raw) != case['source_window_sha256']:
            raise ValueError('source changed')
        iq = np.frombuffer(raw, dtype='<i2').reshape(-1, 2)
        x = iq[:, 0].astype(float) + 1j * iq[:, 1]
        first = case['center_start'] - base.HALO
        for rate in (5, 15):
            values, centers = (condition5(x, first) if rate == 5 else
                               (x, np.arange(len(x), dtype=np.int64) + first))
            take = (centers >= case['center_start']) & (centers < case['center_start'] + base.WINDOW)
            result = search(values[take], centers[take], rate)
            expected = case['historical_pilot_phase_us_for_comparison_only']
            error = (None if expected is None else float(base.circular_distance(
                result['winner']['phase_us'], expected, 4000 / 3)))
            entry = {'case': case['name'], 'rate_msps': rate, 'result': result,
                     'historical_pilot_phase_error_us': error}
            results.append(entry)
            print(json.dumps({**entry, 'result': result['winner']}), flush=True)
    base.write_new(output / 'result.json', {'development_only': True, 'hardware_access': False,
                  'plan_sha256': base.digest((output / 'plan.json').read_bytes()), 'real': results})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output)

"""Fresh, bounded direct-PSS feasibility screen. No radio access.

Prepare pins code, configuration and input bytes before evaluate. Float direct
correlation is deliberately independent of an eventual sequential RTL MAC.
This screen is not a calibrated false-alarm or native-rate timing claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.starlink_oracle.pilot_ddc import PilotDdcOracle, GROUP_DELAY_INPUT_SAMPLES
from tests.starlink_oracle.waveforms import projected_pss

RATE = 2_500_000
CANONICAL_RATE = 15_000_000
CFO_BANK = tuple(range(-400_000, 400_001, 100_000))
TAPS = 16
TEMPLATE_FIRST_CENTER = -17
WINDOW = 1_800_000
HALO = 600
THRESHOLD = 8.0
SOURCE_ROOT = Path('/home/mouse9911/gits/plutosdr-fw-starlink-rx-only/hdl/library/'
                   'starlink_pss_acquisition/build/capture25-causal-heldout-v1')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_new(path: Path, value: dict) -> None:
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def iq(values: np.ndarray) -> np.ndarray:
    lanes = np.column_stack((values.real, values.imag))
    if not np.all(np.isfinite(lanes)) or np.any(np.abs(lanes) > 32767):
        raise ValueError('source does not fit CI16')
    return np.rint(lanes).astype(np.int16)


def condition(raw: np.ndarray, first: int) -> tuple[np.ndarray, np.ndarray]:
    oracle = PilotDdcOracle('upper')
    samples, centers = [], []
    for offset in range(0, len(raw), 60_000):
        block = oracle.process(raw[offset:offset + 60_000], first_index=first + offset)
        if block.saturation_events:
            raise ValueError('conditioner saturation invalidates this screen')
        take = block.support_valid
        samples.append(block.samples_iq[take, 0].astype(float)
                       + 1j * block.samples_iq[take, 1])
        centers.append(block.accepted_input_indexes[take].astype(np.int64)
                       - GROUP_DELAY_INPUT_SAMPLES)
    return np.concatenate(samples), np.concatenate(centers)


def template(cfo: int) -> tuple[np.ndarray, float]:
    """Include pre-filter CFO and causal filter tails, not post-filter rotation."""
    start = 600
    raw = np.zeros(1800, dtype=complex)
    pulse = projected_pss(CANONICAL_RATE, 'upper').astype(complex) * 24_000
    raw[start:start + len(pulse)] = pulse
    raw *= np.exp(2j * np.pi * cfo * np.arange(len(raw)) / CANONICAL_RATE)
    filtered, centers = condition(iq(raw), 0)
    relative = centers - start
    take = ((relative >= TEMPLATE_FIRST_CENTER)
            & (relative < TEMPLATE_FIRST_CENTER + 6 * TAPS))
    result = filtered[take]
    if len(result) != TAPS or relative[take][0] != TEMPLATE_FIRST_CENTER:
        raise RuntimeError('template coordinate mismatch')
    energy = float(np.vdot(result, result).real)
    retained = energy / float(np.vdot(filtered, filtered).real)
    return result / np.sqrt(energy), retained


def circular_distance(left: np.ndarray | float, right: float, period: float):
    return np.abs((left - right + period / 2) % period - period / 2)


def search(samples: np.ndarray, centers: np.ndarray, banks: list[np.ndarray]) -> dict:
    if (len(samples) != len(centers) or len(samples) < 10_000
            or not np.all(np.isfinite(samples))
            or not np.all(np.diff(centers) == 6)):
        raise ValueError('a finite, contiguous, supported inspection epoch is required')
    # Exact 20,000-canonical-sample period = 3333 1/3 inspection samples.
    # Across three frames, 10,000 phase cells each receive equal opportunities.
    starts = centers[:len(samples) - TAPS + 1] - TEMPLATE_FIRST_CENTER
    phase = ((starts % 20_000) // 2).astype(int)
    count = np.bincount(phase, minlength=10_000)
    if np.any(count == 0):
        raise ValueError('insufficient phase coverage')
    results = []
    for cfo, bank in zip(CFO_BANK, banks, strict=True):
        correlation = np.correlate(samples, bank, mode='valid')
        power = np.abs(correlation) ** 2
        folded = np.bincount(phase, weights=power, minlength=10_000) / count
        # One inspection-sample-wide circular averaging, centered on the cell.
        folded = (np.roll(folded, 1) + folded + np.roll(folded, -1)) / 3
        peak = int(np.argmax(folded))
        background = folded[circular_distance(np.arange(10_000), peak, 10_000) > 150]
        mean, sigma = float(np.mean(background)), float(np.std(background))
        z = (float(folded[peak]) - mean) / max(sigma, abs(mean) * 1e-8, 1e-30)
        results.append({'cfo_hypothesis_hz': cfo, 'phase_canonical_samples': peak * 2,
                        'phase_us': peak * 2 / 15, 'peak_z': z,
                        'peak_power': float(folded[peak]), 'background_mean': mean,
                        'background_std': sigma})
    winner = max(results, key=lambda item: item['peak_z'])
    return {'winner': winner, 'detected': winner['peak_z'] >= THRESHOLD,
            'hypotheses': results, 'inspection_samples': len(samples),
            'min_fold_contributions': int(count.min()),
            'max_fold_contributions': int(count.max())}


def source_bytes(case: dict) -> bytes:
    offset = case['center_start'] - HALO - case['file_first_canonical_index']
    if offset < 0:
        raise ValueError('missing source halo')
    with Path(case['path']).open('rb') as stream:
        stream.seek(offset * 4)
        payload = stream.read((WINDOW + 2 * HALO) * 4)
    if len(payload) != (WINDOW + 2 * HALO) * 4:
        raise ValueError('short source window')
    return payload


def configuration() -> dict:
    return {'source_rate_hz': CANONICAL_RATE, 'inspection_rate_hz': RATE,
            'window_canonical_samples': WINDOW, 'cfo_bank_hz': list(CFO_BANK),
            'template_taps': TAPS, 'template_first_center': TEMPLATE_FIRST_CENTER,
            'phase_cells': 10_000, 'smoothing_cells': 3,
            'background_guard_cells': 150, 'peak_z_threshold': THRESHOLD,
            'positive_tolerance_us': 2.0, 'synthetic_tolerance_us': 0.4,
            'drift_bank_ppm': [0], 'noise_seed': 20260912,
            'noise_trials': 32, 'cw_hz': [-300000, 0, 300000],
            'synthetic_cfo_hz': [-300000, 0, 300000],
            'synthetic_phase_offsets_canonical': list(range(6)),
            'synthetic_phase_canonical_base': 6012,
            'synthetic_duration_canonical_samples': 240_000,
            'synthetic_scope': 'noiseless periodic PSS, random carrier phase per frame'}


def code_hashes() -> dict:
    names = ['tools/starlink_coarse25.py', 'tests/starlink_oracle/waveforms.py',
             'tests/starlink_oracle/pilot_ddc.py', 'tests/starlink_oracle/numerology.py',
             'FPGA_COARSE25_PLAN.md']
    return {name: digest((ROOT / name).read_bytes()) for name in names}


def prepare(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    cases = []
    for name, start, expected in (
        ('negative_later_1', 15_000_000, None),
        ('negative_later_2', 22_500_000, None),
        ('positive_later_1', 547_500_000, 400.46666666666664),
        ('positive_later_2', 555_000_000, 401.26666666666665),
    ):
        item = {'name': name, 'path': str(SOURCE_ROOT / name / 'conditioned-15msps.ci16'),
                'file_first_canonical_index': start - 2952, 'center_start': start,
                'historical_pilot_phase_us_for_comparison_only': expected}
        item['source_window_sha256'] = digest(source_bytes(item))
        cases.append(item)
    write_new(output / 'plan.json', {'schema': 'fresh-coarse25-screen-v1',
              'configuration': configuration(), 'code_sha256': code_hashes(),
              'numpy_version': np.__version__, 'cases': cases,
              'hardware_access': False, 'timing_or_cfo_seeds_used': False})


def evaluate(output: Path) -> int:
    plan_bytes = (output / 'plan.json').read_bytes()
    plan = json.loads(plan_bytes)
    if (plan['configuration'] != configuration() or plan['code_sha256'] != code_hashes()
            or plan['numpy_version'] != np.__version__):
        raise ValueError('code/configuration/environment changed since plan freeze')
    banks_with_energy = [template(cfo) for cfo in CFO_BANK]
    banks = [item[0] for item in banks_with_energy]
    report = {'schema': 'fresh-coarse25-screen-result-v1',
              'plan_sha256': digest(plan_bytes), 'hardware_access': False,
              'template_retained_energy': [item[1] for item in banks_with_energy],
              'real': [], 'synthetic': [], 'controls': []}
    # Evaluate recorded data without passing comparison labels to the detector.
    for case in plan['cases']:
        started = time.monotonic()
        payload = source_bytes(case)
        if digest(payload) != case['source_window_sha256']:
            raise ValueError('source bytes changed')
        raw = np.frombuffer(payload, dtype='<i2').reshape(-1, 2)
        values, centers = condition(raw, case['center_start'] - HALO)
        take = ((centers >= case['center_start']) & (centers < case['center_start'] + WINDOW))
        values, centers = values[take], centers[take]
        if len(values) != 300_000:
            raise RuntimeError('inspection sample accounting failed')
        result = search(values, centers, banks)
        expected = case['historical_pilot_phase_us_for_comparison_only']
        error = (None if expected is None else
                 float(circular_distance(result['winner']['phase_us'], expected, 4000 / 3)))
        passed = ((not result['detected']) if expected is None else
                  (result['detected'] and error <= 2.0))
        entry = {'case': case['name'], 'passed': passed, 'result': result,
                 'historical_pilot_phase_error_us': error,
                 'elapsed_seconds': time.monotonic() - started,
                 'inspection_ci16_sha256': digest(iq(values).astype('<i2').tobytes())}
        report['real'].append(entry)
        print(json.dumps({'case': entry['case'], 'passed': passed, 'error_us': error,
                          'winner': result['winner']}), flush=True)
    rng = np.random.default_rng(20260912)
    for cfo in (-300_000, 0, 300_000):
        for offset in range(6):
            phase = 6012 + offset
            raw = np.zeros(240_000 + 1200, dtype=complex)
            pulse = projected_pss(CANONICAL_RATE, 'upper') * 24_000
            for start in range(phase, len(raw) - len(pulse), 20_000):
                raw[start:start + len(pulse)] = pulse * np.exp(2j * np.pi * rng.random())
            raw *= np.exp(2j * np.pi * cfo * np.arange(len(raw)) / CANONICAL_RATE)
            values, centers = condition(iq(raw), 0)
            result = search(values, centers, banks)
            error = float(circular_distance(result['winner']['phase_us'], phase / 15, 4000 / 3))
            report['synthetic'].append({'cfo_hz': cfo, 'offset': offset, 'error_us': error,
                                       'passed': result['detected'] and error <= .4 + 1e-9,
                                       'result': result})
        print(f'synthetic CFO {cfo} complete', flush=True)
    centers = np.arange(300_000, dtype=np.int64) * 6 + 1
    for trial in range(32):
        samples = rng.normal(size=300_000) + 1j * rng.normal(size=300_000)
        result = search(samples, centers, banks)
        report['controls'].append({'kind': 'white_noise', 'trial': trial,
                                   'passed': not result['detected'], 'result': result})
    for cfo in (-300_000, 0, 300_000):
        samples = np.exp(2j * np.pi * cfo * np.arange(300_000) / RATE)
        result = search(samples, centers, banks)
        report['controls'].append({'kind': 'cw', 'cfo_hz': cfo,
                                   'passed': not result['detected'], 'result': result})
    report['passed'] = all(item['passed'] for group in ('real', 'synthetic', 'controls')
                           for item in report[group])
    write_new(output / 'result.json', report)
    print(json.dumps({'screen_passed': report['passed']}), flush=True)
    return 0 if report['passed'] else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'evaluate'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare(args.output)
        return 0
    return evaluate(args.output)


if __name__ == '__main__':
    raise SystemExit(main())

"""Freeze then validate recentered PSS against blind GLRT on the same IQ.

Nonoverlapping 120 ms windows within the known capture episode, NOT independent
RF captures. Earlier wide-band studies covered these episodes. No radio/RTL.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import starlink_coarse25 as base
from tools import starlink_coarse25_normalized as norm
from tools.starlink_capture25_pilot_check import _loaded_oracle, _require_source_hashes
from tools.starlink_coarse25_causal_recenter import PRIOR_PLAN

PRIOR_HZ = 512585.3848550797


def run(output: Path, leo_source: Path) -> int:
    output.mkdir(parents=True, exist_ok=True)
    modules, hashes, native = _loaded_oracle(leo_source)
    prior_bytes = PRIOR_PLAN.read_bytes()
    if base.digest(prior_bytes) != 'cf701ae2ad5c11434469869d2a52b9075ca5a4432211cb6f3b64cbd1d393af66':
        raise ValueError('earlier frequency evidence changed')
    assert json.loads(prior_bytes)['positive_prior']['clusters'][1]['median_hz'] == PRIOR_HZ
    original = json.loads((base.ROOT / 'reports/coarse25-screen-20260912/plan.json').read_bytes())
    cases = []
    for old in original['cases']:
        case = dict(old)
        case['center_start'] += base.WINDOW
        # The old epoch label is deliberately removed; new blind GLRT supplies
        # the comparison only after independent PSS search.
        case.pop('historical_pilot_phase_us_for_comparison_only')
        case['source_window_sha256'] = base.digest(base.source_bytes(case))
        case['positive_episode'] = case['name'].startswith('positive')
        cases.append(case)
    acquisition = modules['acquisition']
    config = acquisition.SymbolwiseAcquisitionConfig(
        residual_cfo_min_hz=-400000, residual_cfo_max_hz=400000,
        retained_candidate_count=8, candidate_epoch_separation_samples=20,
        candidate_cfo_separation_hz=80000)
    code_hashes = {str(Path(module.__file__)): base.digest(Path(module.__file__).read_bytes())
                   for module in (base, norm)}
    code_hashes[str(Path(__file__))] = base.digest(Path(__file__).read_bytes())
    plan = {'scope': 'same-episode nonoverlapping temporal validation, not independent capture',
            'hardware_access': False, 'source_rate_hz': 15000000, 'output_rate_hz': 2500000,
            'prior_hz': PRIOR_HZ, 'prior_sha256': base.digest(prior_bytes),
            'negative_prior_noncausal': True, 'cases': cases,
            'code_sha256': code_hashes, 'leo_hashes': hashes, 'leo_native': native,
            'numpy_version': np.__version__, 'pss_configuration': base.configuration(),
            'glrt_configuration': asdict(config), 'glrt_probe_samples': 50000,
            'pss_timing_seeds_to_glrt': False, 'glrt_seeds_to_pss': False,
            'acceptance': {'positive_min_pss_z': 8, 'positive_min_glrt_margin': .025,
                           'positive_max_phase_difference_us': 2,
                           'negative_requires_pss_below_threshold': True,
                           'negative_requires_glrt_below_margin': True}}
    base.write_new(output / 'plan.json', plan)
    banks = [base.template(cfo)[0] for cfo in base.CFO_BANK]
    results = []
    for case in cases:
        payload = base.source_bytes(case)
        if base.digest(payload) != case['source_window_sha256']:
            raise ValueError('source changed after freeze')
        raw = np.frombuffer(payload, dtype='<i2').reshape(-1, 2)
        x = raw[:, 0].astype(float) + 1j * raw[:, 1]
        x *= np.exp(-2j * np.pi * PRIOR_HZ * np.arange(len(x)) / 15000000)
        x, centers = base.condition(base.iq(x), case['center_start'] - base.HALO)
        take = (centers >= case['center_start']) & (centers < case['center_start'] + base.WINDOW)
        x, centers = x[take], centers[take]
        if len(x) != 300000 or not np.all(np.diff(centers) == 6):
            raise ValueError('inspection accounting mismatch')
        iq_bytes = base.iq(x).astype('<i2').tobytes()
        iq_path = output / (case['name'] + '.ci16')
        with iq_path.open('xb') as stream:
            stream.write(iq_bytes)
        # Read the exported bytes back for both consumers; neither gets a
        # different filter output or an unquantized hidden reference.
        exported = np.frombuffer(iq_path.read_bytes(), dtype='<i2').reshape(-1, 2)
        inspected = exported[:, 0].astype(float) + 1j * exported[:, 1]
        pss = norm.search(inspected, centers, banks)
        probe = inspected[:50000]
        candidates = acquisition.acquire_symbolwise(
            probe, 2500000,
            acquisition.ReceiverFrequencyCalibration('coarse25-offline-not-calibrated', 0, '0' * 64),
            edge='upper', config=config)
        glrt_scores = modules['pilot_methods'].conditioned_glrt64_scores(
            probe, 2500000, edge='upper',
            epoch_samples=[c.refined_epoch_sample for c in candidates.candidates],
            acquired_cfo_hz=[c.absolute_cfo_hz for c in candidates.candidates])
        glrt = [{'epoch_sample': int(c.refined_epoch_sample), **asdict(score)}
                for c, score in zip(candidates.candidates, glrt_scores, strict=True)]
        best = max(glrt, key=lambda s: s['margin'], default=None)
        glrt_phase = (None if best is None else
                      ((int(centers[0]) + 6 * best['epoch_sample']) % 20000) / 15)
        error = (None if glrt_phase is None else float(base.circular_distance(
            pss['winner']['phase_us'], glrt_phase, 4000 / 3)))
        glrt_detected = best is not None and best['margin'] >= .025
        passed = ((pss['detected'] and glrt_detected and error <= 2) if case['positive_episode']
                  else not pss['detected'] and not glrt_detected)
        entry = {'case': case['name'], 'passed': passed, 'pss': pss,
                 'glrt_candidates': glrt, 'glrt_phase_us': glrt_phase,
                 'phase_difference_us': error, 'iq_path': str(iq_path),
                 'iq_sha256': base.digest(iq_bytes), 'iq_bytes': len(iq_bytes),
                 'first_canonical_center': int(centers[0]), 'canonical_stride': 6}
        results.append(entry)
        print(json.dumps({'case': case['name'], 'passed': passed, 'pss': pss['winner'],
                          'glrt_margin': None if best is None else best['margin'],
                          'glrt_phase_us': glrt_phase, 'error_us': error}), flush=True)
    _require_source_hashes(hashes, native)
    report = {'plan_sha256': base.digest((output / 'plan.json').read_bytes()),
              'hardware_access': False, 'passed': all(r['passed'] for r in results),
              'results': results}
    base.write_new(output / 'result.json', report)
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--leo-source', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.output, args.leo_source))

"""Exact Q15 / uint8 scoring oracle for the fresh coarse25 datapath."""
from __future__ import annotations

import math
import numpy as np

from tools import starlink_coarse25 as base


def coefficients() -> np.ndarray:
    words = [int(s, 16) for s in (base.ROOT / 'hdl/library/starlink_coarse25/coarse25_q15.mem')
             .read_text().splitlines()]
    lanes = [(word & 65535, word >> 16) for word in words]
    values = np.asarray(lanes, dtype=np.int64)
    return np.where(values >= 32768, values - 65536, values)


def round_score(re: int, im: int, energy: int, template_energy: int) -> int:
    numerator = re * re + im * im
    denominator = energy * template_energy
    if denominator <= 0:
        return 0
    if numerator >= denominator:
        return 255
    whole, remainder = divmod(numerator * 255, denominator)
    return whole + int(remainder > denominator - remainder or
                       (remainder == denominator - remainder and whole & 1))


def scores(samples_iq: np.ndarray) -> np.ndarray:
    raw = np.asarray(samples_iq)
    if (raw.ndim != 2 or raw.shape[1] != 2 or len(raw) < 16
            or not np.issubdtype(raw.dtype, np.integer)
            or np.any(raw < -32768) or np.any(raw > 32767)):
        raise ValueError('at least 16 CI16 samples required')
    raw = raw.astype(np.int64)
    h = coefficients()
    re = np.correlate(raw[:, 0], h[:, 0], 'valid') + np.correlate(raw[:, 1], h[:, 1], 'valid')
    im = np.correlate(raw[:, 1], h[:, 0], 'valid') - np.correlate(raw[:, 0], h[:, 1], 'valid')
    energy = np.convolve(np.sum(raw * raw, axis=1), np.ones(16, dtype=np.int64), 'valid')
    template_energy = int(np.sum(h * h))
    # Fast exact int64 route only when every intermediate is provably bounded.
    bound = math.isqrt((2**63 - 1) // 510)
    if (max(int(np.max(abs(re))), int(np.max(abs(im)))) <= bound
            and int(energy.max()) * template_energy < 2**63):
        numerator = re * re + im * im
        denominator = energy * template_energy
        safe_denominator = np.maximum(denominator, 1)
        whole, remainder = np.divmod(numerator * 255, safe_denominator)
        rounded = whole + ((remainder > safe_denominator - remainder) |
                           ((remainder == safe_denominator - remainder) & ((whole & 1) != 0)))
        return np.where(denominator == 0, 0, np.minimum(rounded, 255)).astype(np.uint8)
    # Python integers retain the full 75-bit power domain, including extremes.
    return np.fromiter((round_score(int(r), int(i), int(e), template_energy)
                        for r, i, e in zip(re, im, energy, strict=True)), dtype=np.uint8)

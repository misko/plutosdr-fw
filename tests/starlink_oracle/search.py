"""Direct deterministic floating-point correlation search.

This deliberately does not use FFT convolution.  It is a compact golden
reference against which an optimized host or firmware implementation can be
compared.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True, slots=True)
class FloatSearchResult:
    """The unique best result under the oracle's documented tie ordering."""

    sample_index: int
    frequency_offset_hz: float
    normalized_match_power: float
    correlation: complex
    window_energy: float
    template_energy: float
    evaluated_hypotheses: int


def deterministic_float_search(
    samples: npt.ArrayLike,
    template: npt.ArrayLike,
    sample_rate_hz: int,
    *,
    frequency_offsets_hz: tuple[float, ...] = (0.0,),
    start_sample: int = 0,
    stop_sample: int | None = None,
) -> FloatSearchResult:
    """Search direct complex correlations over lag and a finite CFO bank.

    For CFO ``f``, ``h_f[n] = h[n] exp(+j 2 pi f n / Fs)``.  The score is
    ``|sum(conj(h_f[n]) x[k+n])|^2 / (sum|h|^2 sum|x_window|^2)``.

    Ties select the smallest lag, then the numerically smallest CFO.  CFOs are
    sorted here, so caller ordering cannot change the answer.
    """

    values = np.asarray(samples, dtype=np.complex128)
    reference = np.asarray(template, dtype=np.complex128)
    if values.ndim != 1 or not values.size or not np.all(np.isfinite(values)):
        raise ValueError("samples must be finite, nonempty, one-dimensional complex IQ")
    if reference.ndim != 1 or not reference.size or not np.all(np.isfinite(reference)):
        raise ValueError("template must be finite, nonempty, and one-dimensional")
    if reference.size > values.size:
        raise ValueError("template must not be longer than samples")
    if isinstance(sample_rate_hz, bool) or not isinstance(sample_rate_hz, int):
        raise TypeError("sample_rate_hz must be an integer")
    if sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be positive")
    if isinstance(start_sample, bool) or not isinstance(start_sample, int):
        raise TypeError("start_sample must be an integer")
    if start_sample < 0:
        raise ValueError("start_sample must be nonnegative")

    last_stop = values.size - reference.size + 1
    resolved_stop = last_stop if stop_sample is None else stop_sample
    if isinstance(resolved_stop, bool) or not isinstance(resolved_stop, int):
        raise TypeError("stop_sample must be an integer")
    if resolved_stop <= start_sample or resolved_stop > last_stop:
        raise ValueError("search interval contains no complete template window")

    offsets = tuple(sorted(float(value) for value in frequency_offsets_hz))
    if not offsets or not all(math.isfinite(value) for value in offsets):
        raise ValueError("frequency_offsets_hz must be finite and nonempty")
    if len(set(offsets)) != len(offsets):
        raise ValueError("frequency_offsets_hz must be unique")
    if any(abs(value) >= sample_rate_hz / 2 for value in offsets):
        raise ValueError("frequency offset must lie strictly inside complex Nyquist")

    time_s = np.arange(reference.size, dtype=np.float64) / sample_rate_hz
    conditioned = tuple(
        reference * np.exp(2j * np.pi * offset * time_s) for offset in offsets
    )
    template_energy = float(
        np.sum(reference.real * reference.real + reference.imag * reference.imag)
    )
    if template_energy <= 0:
        raise ValueError("template must have positive energy")

    best: FloatSearchResult | None = None
    evaluated = 0
    # Lag-major, CFO-minor traversal implements the declared tie ordering.
    for sample_index in range(start_sample, resolved_stop):
        window = values[sample_index : sample_index + reference.size]
        window_energy = float(
            np.sum(window.real * window.real + window.imag * window.imag)
        )
        for offset, candidate in zip(offsets, conditioned, strict=True):
            correlation = complex(
                np.sum(window * np.conj(candidate), dtype=np.complex128)
            )
            numerator = (
                correlation.real * correlation.real
                + correlation.imag * correlation.imag
            )
            score = (
                numerator / (template_energy * window_energy)
                if window_energy > 0
                else 0.0
            )
            evaluated += 1
            if best is None or score > best.normalized_match_power:
                best = FloatSearchResult(
                    sample_index=sample_index,
                    frequency_offset_hz=offset,
                    normalized_match_power=float(score),
                    correlation=correlation,
                    window_energy=window_energy,
                    template_energy=template_energy,
                    evaluated_hypotheses=0,
                )
    assert best is not None
    return FloatSearchResult(
        sample_index=best.sample_index,
        frequency_offset_hz=best.frequency_offset_hz,
        normalized_match_power=best.normalized_match_power,
        correlation=best.correlation,
        window_energy=best.window_energy,
        template_energy=best.template_energy,
        evaluated_hypotheses=evaluated,
    )

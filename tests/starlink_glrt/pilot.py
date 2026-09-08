"""GLRT-only numerical design reference, independent of the host GLRT package.

This is a development oracle for fabric arithmetic, not a runtime detector or
evidence that the FPGA implements GLRT. Published states are factual Appendix-A
data. Symbol clocks are rational/integer for all five requested source rates.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from functools import lru_cache

import numpy as np
from scipy.signal import correlate

from .ddc import BANK_ROOT, RATES

CODE_SHA256 = "ae79f6884b0d6e93e6ba899e0ef0209cae952c12c8295e61f71d119ff0af38e3"
SYMBOL_SECONDS = 22 / 5_000_000
CP_SECONDS = 2 / 15_000_000
FFT_SIZE = 512
GLRT_SYMBOLS = 64
ACQUISITION_SYMBOLS = 16
TEMPLATE_SCALE = 32


@lru_cache(maxsize=2)
def states(edge: str) -> np.ndarray:
    if edge not in ("lower", "upper"):
        raise ValueError("unknown pilot edge")
    raw = (BANK_ROOT / "qin_pilot_codes.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != CODE_SHA256:
        raise ValueError("published pilot state freeze changed")
    codes = json.loads(raw)["codes"]
    carriers = range(528, 536) if edge == "lower" else range(488, 496)
    result = np.array([[(int(codes[str(k)], 16) >> (2 * (299-row))) & 3
                        for k in carriers] for row in range(300)], dtype=np.int8)
    result.flags.writeable = False
    return result


def symbol_samples(rate: int) -> int:
    if isinstance(rate, bool) or rate not in RATES:
        raise ValueError("unsupported source rate")
    return rate * 22 // 5_000_000


@lru_cache(maxsize=10)
def waveforms(rate: int, edge: str) -> np.ndarray:
    count = symbol_samples(rate)
    local_time = np.arange(count) / rate - CP_SECONDS
    frequencies = (np.arange(8) - 3.5) * 234_375
    rotation = np.exp(2j*np.pi*frequencies[:, None]*local_time)
    qpsk = np.exp(.5j*np.pi*(states(edge) + .5))
    result = qpsk @ rotation / np.sqrt(8)
    result.flags.writeable = False
    return result


@lru_cache(maxsize=10)
def templates(rate: int, edge: str) -> np.ndarray:
    source = waveforms(rate, edge)
    # Equal mean template energy gives each symbol correlation the same noise
    # variance before coefficient quantization. This defines the symbol-vector
    # GLRT nuisance model; the host's coherent-ceiling score is different.
    normalized = source / np.sqrt(np.mean(abs(source)**2, axis=1))[:, None]
    iq = np.rint(np.stack((normalized.real, normalized.imag), axis=-1)*TEMPLATE_SCALE)
    if np.any(iq < -128) or np.any(iq > 127):
        raise ValueError("Q7 template scaling clips")
    result = iq.astype(np.int8)
    result.flags.writeable = False
    return result


def frame(rate: int, edge: str, *, roll: int = 0) -> np.ndarray:
    count = symbol_samples(rate)
    result = np.zeros(round(rate / 750), dtype=np.complex128)
    result[2*count:302*count] = np.roll(waveforms(rate, edge), roll, axis=0).reshape(-1)
    return result


def acquisition_surface(iq: np.ndarray, edge: str) -> np.ndarray:
    """Blind 16-symbol noncoherent pilot proposals on every 2.5 MS/s epoch.

    No FPGA/host timing or CFO seed is accepted. Threshold and peak/candidate
    scheduling are not frozen by this initial arithmetic design reference.
    """
    count = symbol_samples(2_500_000)
    values = np.asarray(iq, dtype=np.complex128)
    n = len(values) - (ACQUISITION_SYMBOLS + 2)*count + 1
    if n <= 0:
        return np.empty(0)
    bank = templates(2_500_000, edge)
    numerator = np.zeros(n)
    for symbol in range(ACQUISITION_SYMBOLS):
        local = bank[symbol, :, 0].astype(float) + 1j*bank[symbol, :, 1]
        correlations = correlate(values, local, mode="valid", method="direct")
        start = (symbol + 2)*count
        numerator += abs(correlations[start:start+n])**2 / np.vdot(local, local).real
    energy = np.concatenate(([0.0], np.cumsum(abs(values)**2)))
    denominator = energy[(ACQUISITION_SYMBOLS+2)*count:(ACQUISITION_SYMBOLS+2)*count+n] - energy[2*count:2*count+n]
    return numerator / np.maximum(denominator, 1e-20)


def round_shift(values: np.ndarray, shift: int) -> np.ndarray:
    floor = values >> shift
    remainder = values & ((1 << shift) - 1)
    half = 1 << (shift-1)
    return floor + ((remainder > half) | ((remainder == half) & ((floor & 1) != 0)))


def symbol_correlations(iq: np.ndarray, rate: int, edge: str, epoch: int, roll: int = 0) -> np.ndarray:
    """CI16 x signed-eight-bit templates, 36-bit MAC, ties-even -> CI24."""
    raw = np.asarray(iq)
    if raw.ndim != 2 or raw.shape[1] != 2 or raw.dtype != np.int16:
        raise ValueError("native reference input must be CI16")
    n = symbol_samples(rate)
    start, stop = epoch + 2*n, epoch + (2+GLRT_SYMBOLS)*n
    if epoch < 0 or stop > len(raw):
        raise ValueError("incomplete native GLRT support")
    samples = raw[start:stop].reshape(GLRT_SYMBOLS, n, 2).astype(np.int64)
    bank = templates(rate, edge)[(np.arange(GLRT_SYMBOLS)-roll) % 300].astype(np.int64)
    real = np.sum(samples[:, :, 0]*bank[:, :, 0] + samples[:, :, 1]*bank[:, :, 1], axis=1)
    imag = np.sum(samples[:, :, 1]*bank[:, :, 0] - samples[:, :, 0]*bank[:, :, 1], axis=1)
    shift = (n-1).bit_length()
    result = round_shift(np.column_stack((real, imag)), shift)
    if np.any(result < -(1 << 23)) or np.any(result >= 1 << 23):
        raise ValueError("native correlation overflow")
    return result


@dataclass(frozen=True)
class Glrt:
    exact: float
    control: float
    margin: float
    cfo_hz: float
    control_cfo_hz: float
    exact_bin: int


def score(iq: np.ndarray, rate: int, edge: str, epoch: int) -> Glrt:
    def evaluate(roll):
        c = symbol_correlations(iq, rate, edge, epoch, roll)
        values = c[:, 0].astype(float) + 1j*c[:, 1]
        spectrum = abs(np.fft.fft(values, FFT_SIZE))**2
        best = int(np.argmax(spectrum))
        denominator = GLRT_SYMBOLS * np.sum(abs(values)**2)
        statistic = float(spectrum[best] / denominator) if denominator else 0.0
        frequency = np.fft.fftfreq(FFT_SIZE, SYMBOL_SECONDS)[best]
        return statistic, float(frequency), best
    exact, frequency, best = evaluate(0)
    control, control_frequency, _ = evaluate(17)
    return Glrt(exact, control, exact-control, frequency, control_frequency, best)

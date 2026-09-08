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


def acquisition_fixed(iq: np.ndarray, edge: str) -> tuple[np.ndarray, np.ndarray]:
    """Per-window integer proposal numerator and energy, 16 x 11 samples.

    Returned window zero ends at sample 175 and implies frame epoch -22.
    Coefficient quantization gives small per-symbol energy differences; the
    proposal denominator deliberately uses common energy 11*32^2. This is
    separate from the final native GLRT and its independent control lane.
    """
    raw = np.asarray(iq)
    if raw.dtype != np.int16 or raw.ndim != 2 or raw.shape[1] != 2:
        raise ValueError("acquisition input requires CI16")
    if len(raw) < 176:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64)
    values = raw.astype(np.int64)
    bank = templates(2_500_000, edge).astype(np.int64)
    length = len(raw)-175
    numerator = np.zeros(length, dtype=np.int64)
    for symbol in range(16):
        ti, tq = bank[symbol, :, 0], bank[symbol, :, 1]
        real = np.correlate(values[:, 0], ti, "valid") + np.correlate(values[:, 1], tq, "valid")
        imag = np.correlate(values[:, 1], ti, "valid") - np.correlate(values[:, 0], tq, "valid")
        start = symbol*11
        c = round_shift(np.column_stack((real[start:start+length], imag[start:start+length])), 4)
        numerator += np.sum(c**2, axis=1)
    energy = np.concatenate(([0], np.cumsum(np.sum(values**2, axis=1))))
    denominator_energy = energy[176:]-energy[:-176]
    return numerator, denominator_energy


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


def fixed_score(exact: np.ndarray, control: np.ndarray) -> dict:
    """Integer DFT/energy/division oracle for every FPGA score output field."""
    inputs = [np.asarray(exact, dtype=np.int64), np.asarray(control, dtype=np.int64)]
    if any(c.shape != (64, 2) or np.any(c < -(1 << 23)) or np.any(c >= 1 << 23) for c in inputs):
        raise ValueError("scorer requires two 64-symbol CI24 vectors")
    largest = max(int(abs(c).max()) for c in inputs)
    shift = max(0, 21-largest.bit_length()) if largest else 0
    words = np.array([int(word, 16) for word in (BANK_ROOT / "glrt_dft512_q15.mem").read_text().split()], dtype=np.int64)
    twiddle = np.column_stack((words & 0x1ffff, words >> 17))
    twiddle = np.where(twiddle & 0x10000, twiddle-0x20000, twiddle)
    phases = np.arange(512)[:, None]*np.arange(64)[None, :] % 512
    rotation = twiddle[phases]
    output = {"block_shift": shift}
    for name, c in zip(("exact", "control"), inputs):
        c = c << shift
        real = np.sum(c[None, :, 0]*rotation[:, :, 0] - c[None, :, 1]*rotation[:, :, 1], axis=1)
        imag = np.sum(c[None, :, 0]*rotation[:, :, 1] + c[None, :, 1]*rotation[:, :, 0], axis=1)
        rounded = round_shift(np.column_stack((real, imag)), 21)
        powers = np.sum(rounded**2, axis=1)
        best = int(np.argmax(powers))
        peak = int(powers[best])
        energy = int(np.sum(c**2))
        ratio = (peak << 22)//energy if energy else 0
        output[name] = dict(bin=best, peak=peak, energy=energy,
                            score=min(ratio, 65536), clamped=int(ratio > 65536), zero=int(energy == 0))
    return output

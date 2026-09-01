"""Exact native PSS/SSS construction and deterministic edge projection.

The sequence construction is independently copied from the clean, reviewed
``leo-tracker-reduxredux-pss-sss-five-dwell`` numerical oracle.  The projector
is the tracked rate-generic construction from ``pss_timing.py`` in
``leo-tracker-reduxredux-all-rate-main``.  Neither repository is imported at
runtime; detailed revision and file hashes live beside this module in README.
"""

from __future__ import annotations

import hashlib
import math
from functools import lru_cache

import numpy as np
import numpy.typing as npt

from .numerology import (
    NATIVE_CYCLIC_PREFIX_SAMPLES,
    NATIVE_SAMPLE_RATE_HZ,
    NATIVE_USEFUL_SAMPLES,
    numerology_for_rate,
)

PSS_HEX_V1 = "C1B5D191024D3DC3F8EC52FAA16F3958"
PSS_NATIVE_SHA256 = "e950ec78f60f8d9d9f0f6d98fc9f17ae77ebed9ef224df38efe9545c8d5a21f7"
SSS_NATIVE_SHA256 = "21e9844ec67a498b139e914d0123cb5cdd35a53b1c7b6388115c483220c8e5be"
SSS_FREQUENCY_SHA256 = (
    "1ece2fb4719619d004fbb2524f6db70f2a3972e85ac5919799fc792c11012452"
)
_RESAMPLE_LOBES = 10.0

# The 1,020 non-zero SSS subcarriers from the public UT Radionavigation Lab
# Starlink simulator at revision 5de898badd03f6a8b3c7d5196b9b31d4039263ed.
# Its source sssVec.mat has SHA-256
# d1e35826279baf0fc3e5a6fa3d34e5a83dd525956132ad9cecdb2af48450f982.
# States are MSB-first with -1 -> 0, -j -> 1, +j -> 2, +1 -> 3.
SSS_QPSK_PACKED_HEX_V1 = (
    "7fcaffd9cf8431cb3a5327508f8124850a16268b853ac1a6b4b81fc16561b023"
    "ff9d3e7fcba72d3368ee9b34eeac1352938e7b53452194b64a9fe572807e0e2"
    "dc5e7d95b7a1d3c154a583231b0e3d8edfe4dee58ee1690225533be63040ad37"
    "39c868638b672485942ed583ee69f2fda307141fbf52ed49f8a56e7498fca257"
    "fcf7fc10fca30243f8b3e1cc560d5708f8efe05cad42b7b75ed196a7565c03eb"
    "fcbffdecf9031a73b4320209ac14e4404eede606ea953485c30856bb0358fda0f"
    "8e3e07cadb2b537adee4b5856a15418f09fdd1c0b8196bfa9ef020bf94f1b934"
    "e3de476e4d51a45e1f5fe4a588b2e8f2a919e32c35ca8e807481e2fa9a2a94"
)

PROJECTED_PSS_SHA256 = {
    (
        15_000_000,
        "lower",
    ): "4edc636f6b176c651a3547cbd8254429fda41f35c677bc30801eeba71c325a21",
    (
        15_000_000,
        "upper",
    ): "3c4e6e36250c970c2905ae64d177e0d9d40e941702483f15f11cc57e88edaced",
    (
        30_000_000,
        "lower",
    ): "6e69a4accde4c0540f472c54ef65a7821dc08dedcdc7a0f44cde291d54d86368",
    (
        30_000_000,
        "upper",
    ): "4e9ccb3d9baddd1b893601d1b29c9b61c4419b06b55614403b63fe8427c77513",
    (
        60_000_000,
        "lower",
    ): "55fb38251f2fc9147f98b54f53d23bdf7c764d950843e7a246fb26604ad4e900",
    (
        60_000_000,
        "upper",
    ): "a00122e3bff666e2a4fb945d7b3b6be00bf8ca222a296540d16e6c1ba57b8c38",
}

PROJECTED_SSS_SHA256 = {
    (
        15_000_000,
        "lower",
    ): "ca010d5860cb0a19f474fb398ffeb3551162f69c8e5a45eaf178cd2ac424ef43",
    (
        15_000_000,
        "upper",
    ): "5a8d0bb91c7aa0940e89791a3a98d29e9d855138e5ad32efd7eda1f52bacac72",
    (
        30_000_000,
        "lower",
    ): "0cd12e40bbda1122309aeb7a71c350544c6b06617c38046c12545295626bedb4",
    (
        30_000_000,
        "upper",
    ): "be598b7789b573d92e40e43edbc7226fbe4fb24aeb571f1d90388efd7db77e43",
    (
        60_000_000,
        "lower",
    ): "b9d7d104962e6c8f665129df7674b3e4a8bd31a04be1aea5628aa15b8b549c91",
    (
        60_000_000,
        "upper",
    ): "721a745dabb2fc76edb8564dfd2282137771e4c2acde40a135ae712523246d5f",
}


def complex64_sha256(samples: npt.ArrayLike) -> str:
    """Hash canonical little-endian interleaved complex64 bytes."""

    values = np.asarray(samples)
    if values.ndim != 1 or not np.iscomplexobj(values):
        raise ValueError("digest input must be one-dimensional complex samples")
    return hashlib.sha256(
        np.asarray(values, dtype="<c8").tobytes(order="C")
    ).hexdigest()


@lru_cache(maxsize=1)
def pss_native_time_samples() -> npt.NDArray[np.complex64]:
    """Return the exact published 1056-sample PSS at 240 MS/s.

    Samples ``k=-32..-1`` are the sign-inverted cyclic prefix.  This unusual
    prefix rule belongs to PSS only.
    """

    encoded = int(PSS_HEX_V1, 16)
    output = np.empty(1056, dtype=np.complex64)
    for output_index, k in enumerate(range(-32, 1024)):
        position = k % 128
        cumulative = sum(2 * ((encoded >> bit) & 1) - 1 for bit in range(position + 1))
        phase_pi = (1.0 if k < 128 else 0.0) - 0.25 - 0.5 * cumulative
        output[output_index] = np.exp(1j * np.pi * phase_pi)
    if complex64_sha256(output) != PSS_NATIVE_SHA256:
        raise RuntimeError("native PSS construction changed")
    output.flags.writeable = False
    return output


@lru_cache(maxsize=1)
def sss_frequency_symbols() -> npt.NDArray[np.complex128]:
    """Return the exact published SSS in natural, unshifted FFT-bin order."""

    packed = int(SSS_QPSK_PACKED_HEX_V1, 16)
    states = np.fromiter(
        ((packed >> (2 * (1019 - index))) & 3 for index in range(1020)),
        dtype=np.int8,
        count=1020,
    )
    constellation = np.asarray((-1 + 0j, -1j, 1j, 1 + 0j), dtype=np.complex128)
    output = np.zeros(NATIVE_USEFUL_SAMPLES, dtype=np.complex128)
    output[2:-2] = constellation[states]
    if complex64_sha256(output) != SSS_FREQUENCY_SHA256:
        raise RuntimeError("SSS frequency sequence changed")
    output.flags.writeable = False
    return output


@lru_cache(maxsize=1)
def sss_native_time_samples() -> npt.NDArray[np.complex64]:
    """Return SSS at 240 MS/s using ``sqrt(1024) * ifft(X)`` and normal CP."""

    useful = np.fft.ifft(sss_frequency_symbols()) * math.sqrt(NATIVE_USEFUL_SAMPLES)
    output = np.concatenate((useful[-NATIVE_CYCLIC_PREFIX_SAMPLES:], useful)).astype(
        np.complex64
    )
    if complex64_sha256(output) != SSS_NATIVE_SHA256:
        raise RuntimeError(
            "native SSS FFT bytes differ from the NumPy 2.5.2 oracle; "
            "review before accepting a new implementation digest"
        )
    output.flags.writeable = False
    return output


def project_native_symbol_to_edge(
    native_samples: npt.ArrayLike,
    sample_rate_hz: int,
    edge: str,
) -> npt.NDArray[np.complex64]:
    """Mix and windowed-sinc project one native symbol into an edge capture.

    The output is normalized to unit L2 energy.  This direct construction is
    intentionally small and slow; it is the float oracle for faster DUT paths.
    """

    numerology = numerology_for_rate(sample_rate_hz)
    values = np.asarray(native_samples, dtype=np.complex64)
    if values.ndim != 1 or values.size != 1056 or not np.all(np.isfinite(values)):
        raise ValueError("native symbol must contain 1056 finite complex samples")
    slice_offset_hz = numerology.edge_center_offset_hz(edge)
    native = np.asarray(values, dtype=np.complex128)
    native_time_s = np.arange(native.size, dtype=float) / NATIVE_SAMPLE_RATE_HZ
    translated = native * np.exp(-2j * np.pi * slice_offset_hz * native_time_s)

    ratio = sample_rate_hz / NATIVE_SAMPLE_RATE_HZ
    output_count = math.ceil(native.size * ratio - 1e-12)
    if output_count != numerology.symbol_samples:
        raise RuntimeError(
            "declared symbol geometry does not close the native projection"
        )
    output_positions = np.arange(output_count, dtype=float) / ratio
    source_positions = np.arange(native.size, dtype=float)
    scaled = ratio * (output_positions[:, None] - source_positions[None, :])
    inside = np.abs(scaled) < _RESAMPLE_LOBES
    window = np.zeros_like(scaled)
    window[inside] = 0.5 * (1.0 + np.cos(np.pi * scaled[inside] / _RESAMPLE_LOBES))
    weights = ratio * np.sinc(scaled) * window
    output = np.asarray(weights @ translated, dtype=np.complex64)
    norm = float(np.linalg.norm(output))
    if not math.isfinite(norm) or norm <= 0:
        raise ValueError("projected symbol has no finite energy")
    output /= norm
    output.flags.writeable = False
    return output


def projected_pss(sample_rate_hz: int, edge: str) -> npt.NDArray[np.complex64]:
    """Return one immutable, unit-energy edge PSS template."""

    return project_native_symbol_to_edge(
        pss_native_time_samples(), sample_rate_hz, edge
    )


def projected_sss(sample_rate_hz: int, edge: str) -> npt.NDArray[np.complex64]:
    """Return one immutable, unit-energy edge SSS template."""

    return project_native_symbol_to_edge(
        sss_native_time_samples(), sample_rate_hz, edge
    )

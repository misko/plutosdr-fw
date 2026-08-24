"""RTL-derived PNXX oracle and a P15 phase witness for RX IQ boundaries."""

from __future__ import annotations

import re
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

# Each tuple lists the input-state bits XORed into one output bit.  The tuple
# index is the output bit number.  These are the complete PRBS_P15/PRBS_P20
# cases in axi_ad9361_tx_channel.v, not a nominal polynomial approximation.
P15_TAPS: tuple[tuple[int, ...], ...] = (
    (6, 4),
    (7, 5),
    (8, 6),
    (9, 7),
    (10, 8),
    (11, 9),
    (12, 10),
    (13, 11),
    (14, 12),
    (0, 14, 13),
    (1, 0),
    (2, 1),
    (3, 2),
    (4, 3),
    (5, 4),
    (6, 5),
    (7, 6),
    (8, 7),
    (9, 8),
    (10, 9),
    (11, 10),
    (12, 11),
    (13, 12),
    (14, 13),
)

P20_TAPS: tuple[tuple[int, ...], ...] = (
    (16, 2, 5, 8, 11, 14, 17, 0),
    (17, 3, 6, 9, 12, 15, 18, 1),
    (18, 4, 7, 10, 13, 16, 19, 2),
    (19, 5, 8, 11, 14, 17, 0),
    (0, 3, 6, 9, 12, 15, 18, 1),
    (1, 4, 7, 10, 13, 16, 19, 2),
    (2, 5, 8, 11, 14, 17, 0),
    (3, 6, 9, 12, 15, 18, 1),
    (4, 7, 10, 13, 16, 19, 2),
    (5, 8, 11, 14, 17, 0),
    (6, 9, 12, 15, 18, 1),
    (7, 10, 13, 16, 19, 2),
    (8, 11, 14, 17, 0),
    (9, 12, 15, 18, 1),
    (10, 13, 16, 19, 2),
    (11, 14, 17, 0),
    (12, 15, 18, 1),
    (13, 16, 19, 2),
    (14, 17, 0),
    (15, 18, 1),
    (16, 19, 2),
    (17, 0),
    (18, 1),
    (19, 2),
)

# The state advances after two 12-bit halves.  The serialized P15 and P20
# streams also have an odd-sample symmetry, so their minimum observable phase
# periods are one state period.  The doubled joint value remains the
# conservative, halfword-aligned repeat bound documented for this fixture.
P15_UPDATE_PERIOD = 32_767
P15_SAMPLE_PERIOD = 32_767
P20_UPDATE_PERIOD = 349_525
P20_SAMPLE_PERIOD = 349_525
PNXX_JOINT_SAMPLE_PERIOD = 738_895_850


def _parity(state: int, taps: Sequence[int]) -> int:
    value = 0
    for bit in taps:
        value ^= (state >> bit) & 1
    return value


def pn_step(state: int, taps: Sequence[Sequence[int]]) -> int:
    if not 0 <= state <= 0xFFFFFF:
        raise ValueError("PN state must fit 24 bits")
    output = 0
    for bit, inputs in enumerate(taps):
        output |= _parity(state, inputs) << bit
    return output


def signed_12(value: int) -> int:
    value &= 0xFFF
    return value - 0x1000 if value & 0x800 else value


def pn_samples(
    taps: Sequence[Sequence[int]], count: int, *, initial_state: int = 0xFFFFFF
) -> Iterable[int]:
    """Yield the RTL's high half, low half, then advance sequence."""

    if count < 0:
        raise ValueError("count must be nonnegative")
    state = initial_state
    emitted = 0
    while emitted < count:
        yield signed_12(state >> 12)
        emitted += 1
        if emitted >= count:
            break
        yield signed_12(state)
        emitted += 1
        state = pn_step(state, taps)


@lru_cache(maxsize=1)
def p15_period() -> tuple[int, ...]:
    canonical_state = pn_step(0xFFFFFF, P15_TAPS)
    return tuple(
        pn_samples(P15_TAPS, P15_SAMPLE_PERIOD, initial_state=canonical_state)
    )


@lru_cache(maxsize=1)
def p20_period() -> tuple[int, ...]:
    canonical_state = pn_step(0xFFFFFF, P20_TAPS)
    return tuple(
        pn_samples(P20_TAPS, P20_SAMPLE_PERIOD, initial_state=canonical_state)
    )


def _extract_rtl_taps(source: str, label: str, next_label: str) -> tuple[tuple[int, ...], ...]:
    pattern = rf"{label}:\s*begin(?P<body>.*?)(?=\n\s*{next_label}:|\n\s*endcase)"
    match = re.search(pattern, source, flags=re.DOTALL)
    if match is None:
        raise ValueError(f"could not find {label} in RTL")
    assignments: dict[int, tuple[int, ...]] = {}
    for output_bit, expression in re.findall(
        r"dout\[\s*(\d+)\]\s*=\s*([^;]+);", match.group("body")
    ):
        inputs = tuple(int(value) for value in re.findall(r"din\[\s*(\d+)\]", expression))
        assignments[int(output_bit)] = inputs
    if set(assignments) != set(range(24)):
        raise ValueError(f"{label} does not assign all 24 output bits")
    return tuple(assignments[index] for index in range(24))


def verify_rtl_contract(path: Path) -> None:
    """Fail if the pinned HDL no longer implements this exact PNXX oracle."""

    source = path.read_text(encoding="utf-8")
    if _extract_rtl_taps(source, "PRBS_P15", "PRBS_P20") != P15_TAPS:
        raise ValueError("P15 oracle differs from pinned HDL")
    if _extract_rtl_taps(source, "PRBS_P20", "unused_label") != P20_TAPS:
        raise ValueError("P20 oracle differs from pinned HDL")
    required_fragments = (
        "localparam  PRBS_P15  = 2;",
        "localparam  PRBS_P20  = 3;",
        "4'h9: dac_data_out_int <= dac_pn_data;",
        "dac_pn_seq <= 24'hffffff;",
        "dac_pn_data <= dac_pn_seq[11: 0];",
        "dac_pn_data <= dac_pn_seq[23:12];",
    )
    missing = [fragment for fragment in required_fragments if fragment not in source]
    if missing:
        raise ValueError(f"PNXX HDL contract fragments are missing: {missing}")


@dataclass(frozen=True)
class PnPhaseEstimate:
    phase: int
    coherence: float
    peak_ratio: float


def _numpy() -> Any:
    try:
        import numpy
    except ImportError as exc:
        raise RuntimeError("PN hardware correlation requires numpy") from exc
    return numpy


def estimate_p15_phase(
    raw_dual_iq: bytes,
    *,
    rx_channel: int,
    window_samples: int = 4096,
) -> PnPhaseEstimate:
    """Estimate a buffer's P15 phase despite complex gain and the P20 Q stream.

    The score is normalized complex correlation against every cyclic P15
    phase.  P20 and receiver noise are uncorrelated nuisance terms.  RX0 and
    RX1 are estimated separately and only their boundary deltas are compared.
    """

    if rx_channel not in (0, 1):
        raise ValueError("rx_channel must be 0 or 1")
    np = _numpy()
    words = np.frombuffer(raw_dual_iq, dtype="<i2")
    if words.size % 4:
        raise ValueError("dual-RX CS16 payload is not a multiple of four words")
    matrix = words.reshape((-1, 4))
    count = min(int(window_samples), int(matrix.shape[0]))
    if count < 256:
        raise ValueError("PN correlation requires at least 256 IQ samples")
    base = rx_channel * 2
    observed = matrix[:count, base].astype(np.float64) + (
        1j * matrix[:count, base + 1].astype(np.float64)
    )
    observed -= observed.mean()
    observed_energy = float(np.vdot(observed, observed).real)
    if observed_energy <= 0:
        raise ValueError("RX PN witness has zero energy")

    reference = np.asarray(p15_period(), dtype=np.float64)
    reference -= reference.mean()
    doubled = np.concatenate((reference, reference[: count - 1]))

    # c[s] = sum(conj(reference[s+k]) * observed[k]).  FFT convolution keeps
    # the full 65,534-phase search bounded and avoids a 2 GiB sliding matrix.
    convolution_length = len(doubled) + count - 1
    fft_length = 1 << (convolution_length - 1).bit_length()
    convolution = np.fft.ifft(
        np.fft.fft(doubled.conj(), fft_length)
        * np.fft.fft(observed[::-1], fft_length)
    )
    correlation = convolution[count - 1 : count - 1 + P15_SAMPLE_PERIOD]
    cumulative_energy = np.concatenate(
        (np.asarray([0.0]), np.cumsum(np.abs(doubled) ** 2))
    )
    reference_energy = (
        cumulative_energy[count : count + P15_SAMPLE_PERIOD]
        - cumulative_energy[:P15_SAMPLE_PERIOD]
    )
    coherence = np.abs(correlation) ** 2 / (reference_energy * observed_energy)
    phase = int(np.argmax(coherence))
    peak = float(coherence[phase])

    exclusion = 16
    runner = coherence.copy()
    for offset in range(-exclusion, exclusion + 1):
        runner[(phase + offset) % P15_SAMPLE_PERIOD] = 0.0
    runner_up = float(np.max(runner))
    ratio = peak / runner_up if runner_up > 0 else float("inf")
    return PnPhaseEstimate(phase=phase, coherence=peak, peak_ratio=ratio)


def analyze_tone(
    raw_dual_iq: bytes,
    *,
    sample_rate_hz: int,
    tone_hz: int,
) -> Mapping[str, Any]:
    """Bounded DDS-tone fixture check; it is never used as a continuity oracle."""

    np = _numpy()
    words = np.frombuffer(raw_dual_iq, dtype="<i2")
    if words.size % 4:
        raise ValueError("dual-RX CS16 payload is not a multiple of four words")
    matrix = words.reshape((-1, 4))
    result: dict[str, Any] = {}
    for rx_channel in (0, 1):
        base = rx_channel * 2
        signal = matrix[1024:, base].astype(np.float64) + (
            1j * matrix[1024:, base + 1].astype(np.float64)
        )
        signal -= signal.mean()
        rms = float(np.sqrt(np.mean(np.abs(signal) ** 2)))
        peak = float(np.max(np.maximum(np.abs(signal.real), np.abs(signal.imag))))
        spectrum = np.abs(np.fft.fft(signal)) ** 2
        frequencies = np.fft.fftfreq(signal.size, d=1.0 / sample_rate_hz)
        tone_window = np.abs(np.abs(frequencies) - abs(tone_hz)) <= 5_000
        noise_window = (np.abs(frequencies) > 20_000) & ~tone_window
        tone_power = float(np.max(spectrum[tone_window]))
        noise_power = float(np.median(spectrum[noise_window]))
        snr_db = 10.0 * float(np.log10(max(tone_power, 1.0) / max(noise_power, 1.0)))
        result[f"rx{rx_channel}"] = {
            "rms_counts": rms,
            "peak_counts": peak,
            "rms_dbfs": 20.0 * float(np.log10(max(rms, 1e-12) / 2048.0)),
            "tone_snr_db": snr_db,
            "valid": bool(rms >= 0.25 and peak < 2047 and snr_db >= 10.0),
        }
    result["valid"] = all(result[f"rx{channel}"]["valid"] for channel in (0, 1))
    return result

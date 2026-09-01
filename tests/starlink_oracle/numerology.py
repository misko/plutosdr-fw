"""Closed Starlink synchronization numerology for the experimental oracle."""

from __future__ import annotations

from dataclasses import dataclass

NATIVE_SAMPLE_RATE_HZ = 240_000_000
NATIVE_USEFUL_SAMPLES = 1024
NATIVE_CYCLIC_PREFIX_SAMPLES = 32
FRAME_RATE_HZ = 750
SUBCARRIER_SPACING_HZ = 234_375.0


@dataclass(frozen=True, slots=True)
class StarlinkNumerology:
    """One exact integer-rate view of the 240 MHz Starlink waveform."""

    sample_rate_hz: int
    useful_samples: int
    cyclic_prefix_samples: int
    symbol_samples: int
    frame_samples: int
    edge_center_magnitude_hz: float

    def edge_center_offset_hz(self, edge: str) -> float:
        """Return the edge-capture center relative to the channel reference."""

        if edge == "lower":
            return -self.edge_center_magnitude_hz
        if edge == "upper":
            return self.edge_center_magnitude_hz
        raise ValueError("edge must be 'lower' or 'upper'")


NUMEROLOGIES = {
    15_000_000: StarlinkNumerology(
        sample_rate_hz=15_000_000,
        useful_samples=64,
        cyclic_prefix_samples=2,
        symbol_samples=66,
        frame_samples=20_000,
        edge_center_magnitude_hz=112_382_812.5,
    ),
    30_000_000: StarlinkNumerology(
        sample_rate_hz=30_000_000,
        useful_samples=128,
        cyclic_prefix_samples=4,
        symbol_samples=132,
        frame_samples=40_000,
        edge_center_magnitude_hz=104_882_812.5,
    ),
    60_000_000: StarlinkNumerology(
        sample_rate_hz=60_000_000,
        useful_samples=256,
        cyclic_prefix_samples=8,
        symbol_samples=264,
        frame_samples=80_000,
        edge_center_magnitude_hz=89_882_812.5,
    ),
}


def numerology_for_rate(sample_rate_hz: int) -> StarlinkNumerology:
    """Resolve only the three integer sample rates declared by this oracle."""

    if isinstance(sample_rate_hz, bool) or not isinstance(sample_rate_hz, int):
        raise TypeError("sample_rate_hz must be an integer")
    try:
        return NUMEROLOGIES[sample_rate_hz]
    except KeyError as exc:
        raise ValueError("sample_rate_hz must be 15, 30, or 60 MHz") from exc

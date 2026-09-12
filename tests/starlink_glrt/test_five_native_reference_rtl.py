"""The actual 5-MS/s ROM output matches the independent native replay model."""
import hashlib

from tools.starlink_glrt_native_replay import BANK_SHA256, coefficients

from .ddc import BANK_ROOT
from .test_cubic_coefficients_rtl import simulate


def test_complete_five_megasample_pilot_uses_exact_pinned_reference_and_derivative(tmp_path):
    bank = (BANK_ROOT / "native_cubic_60000000_upper.mem").read_bytes()
    assert hashlib.sha256(bank).hexdigest() == BANK_SHA256
    segments = []
    for text in bank.splitlines():
        word, terms = int(text, 16), []
        for width in (12, 13, 14, 15):
            pair = []
            for _ in range(2):
                value = word & ((1 << width) - 1)
                pair.append(value - (1 << width) if value & (1 << (width - 1)) else value)
                word >>= width
            terms.append(pair)
        assert word == 0
        segments.append(terms)
    model = coefficients(bank, rate_hz=5000000)
    assert len(model) == 6600
    # Deliberately stall across segment boundaries and the final coefficient.
    # Values and coordinates must remain stable until consumed.
    cycles = [(1, 0, 1, 0)] + [(1, 0, 0, int(cycle % 20 == 0 and cycle % 97 != 0))
                               for cycle in range(140000)]
    result, aborted = simulate(tmp_path, segments, 24, len(model), cycles, stride=12)
    assert aborted == 0
    assert result == [[n, *values, int(n == 6599), 0] for n, values in enumerate(model)]

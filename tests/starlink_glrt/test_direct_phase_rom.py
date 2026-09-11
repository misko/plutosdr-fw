"""Direct ROM layout conversion preserves signed coefficient bits and phase order."""
import pytest

from tools.generate_glrt_direct_phase_rom import pack_phase_rom


def test_two_phase_words_interleave_by_sample_with_phase_zero_in_low_bits():
    encoded = b"0000000000000001\nffffffffffffffff\n8000000000000000\n0000000000000004\n"
    assert pack_phase_rom(encoded, phases=2, samples=2) == (
        b"80000000000000000000000000000001\n0000000000000004ffffffffffffffff\n"
    )
    assert pack_phase_rom(encoded, phases=1, samples=4) == encoded


@pytest.mark.parametrize("encoded,phases,samples", [
    (b"",1,1), (b"0\n",1,1), (b"fffffffffffffffff\n",1,1),
    (b"-000000000000001\n",1,1), (b"0000000000000000\n",2,1),
    (b"0000000000000000\n",3,1), (b"0000000000000000\n",1,0),
    (b"0000000000000000\n",True,1),
])
def test_malformed_or_incomplete_phase_inventory_is_rejected(encoded, phases, samples):
    with pytest.raises(ValueError):
        pack_phase_rom(encoded, phases=phases, samples=samples)

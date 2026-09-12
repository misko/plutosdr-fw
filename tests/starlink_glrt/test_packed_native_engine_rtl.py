"""Packed storage admission deadlines and the exact committed coefficient bank."""
import hashlib

import pytest

from tools.generate_glrt_packed_direct_rom import pack_direct_rom

from .ddc import BANK_ROOT
from .test_native_engine_rtl import bank_for, expected, row, sample, simulate


def test_committed_packed_rom_preserves_the_canonical_four_phase_bank():
    source = (BANK_ROOT / "native_direct_2500000_phase4_upper.mem").read_bytes()
    assert hashlib.sha256(source).hexdigest() == "10c79cc95433325bdb81de5edcf186d7a952d5d5e01668e708a20d3b318996c2"
    packed = (BANK_ROOT / "native_direct_2500000_phase4_upper_packed.mem").read_bytes()
    assert packed == pack_direct_rom(source, phases=4, samples=3300)
    assert hashlib.sha256(packed).hexdigest() == "c39fd3291163fc443fe113a46bc32183c3c8b067805fb71523d9580112ff036a"


@pytest.mark.parametrize("phase", range(4))
@pytest.mark.parametrize("lead", [0, 8, 9, 39])
def test_first_sample_deadline_is_explicit_and_full_cadence_remains_exact(tmp_path, phase, lead):
    count = 33
    job = (2**55 + 17, phase, 2**32 - 731)
    direct = [(p*109+n, -p*227-n, 32767-n, -32768+n)
              for p in range(4) for n in range(count)]
    rows = [row(job=job)] + [row()]*lead
    for n in range(count):
        rows += [row(value=sample(job[0]+n), closed=int(n == count-1))] + [row()]*39
    result = simulate(tmp_path, count, bank_for(79200), rows, stride=24,
                      direct=direct, phases=4, serial=True, packed=True)
    if lead < 9:
        assert result == [expected(job, [], [], 0x12) + [phase]]
    else:
        coefficients = [[n, *c, int(n == count-1), 0]
                        for n, c in enumerate(direct[phase*count:(phase+1)*count])]
        assert result == [expected(job, [sample(job[0]+n) for n in range(count)], coefficients) + [phase]]

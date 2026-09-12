"""Lossless storage and all signed coefficients, including every phase boundary."""
import hashlib
import random

import pytest

from tools.generate_glrt_packed_direct_rom import pack_direct_rom
from .ddc import BANK_ROOT
from .test_direct_coefficients_rtl import check_bank


@pytest.mark.parametrize("samples", [1,2,8,9,10,17,3300])
@pytest.mark.parametrize("phases", [1,2,4,8])
def test_packing_matches_independent_concatenated_bit_string(samples,phases):
    rng=random.Random(samples+phases*812)
    words=[rng.getrandbits(64) for _ in range(samples*phases)]
    encoded=''.join(f'{w:016x}\n' for w in words).encode()
    wire_rows=[int(row,16) for row in pack_direct_rom(encoded,phases=phases,samples=samples).splitlines()]
    binary=''.join(f'{w:064b}'[::-1] for w in words)
    expected=[int(binary[n:n+9][::-1],2) for n in range(0,len(binary),9)]+[0,0]
    banks=(len(expected)+4095)//4096
    assert len(wire_rows)==4096
    assert all(0<=row<1<<(9*banks) for row in wire_rows)
    actual=[(row>>(9*b))&511 for b in range(banks) for row in wire_rows]
    assert actual==expected+[0]*(banks*4096-len(expected))


@pytest.mark.parametrize("encoded,phases,samples", [(b'',1,1),(b'0\n',1,1),
    (b'fffffffffffffffff\n',1,1),(b'-000000000000001\n',1,1),
    (b'0000000000000000\n',2,1),(b'0000000000000000\n',3,1),
    (b'0000000000000000\n',1,0),(b'0000000000000000\n',True,1)])
def test_invalid_banks_are_never_packed(encoded,phases,samples):
    with pytest.raises(ValueError):pack_direct_rom(encoded,phases=phases,samples=samples)


@pytest.mark.parametrize("count", [1,17])
@pytest.mark.parametrize("phases", [1,2,4,8])
@pytest.mark.parametrize("reset", [False,True])
@pytest.mark.parametrize("ready", [False,True])
def test_serial_reads_preserve_signed_rails_phase_capture_and_cancel(tmp_path,count,phases,reset,ready):
    values=[[(32767-n-phase*113,-32768+n+phase*57,71*n-13+phase*19,29-37*n-phase*23)
        for n in range(count)] for phase in range(phases)]
    check_bank(tmp_path,values,reset,packed=True,always_ready=ready)


@pytest.mark.parametrize("ready", [False,True])
def test_every_physical_bank_coefficient_is_exact_without_requantization(tmp_path,ready):
    encoded=(BANK_ROOT/'native_direct_2500000_phase4_upper.mem').read_bytes()
    assert hashlib.sha256(encoded).hexdigest()=='10c79cc95433325bdb81de5edcf186d7a952d5d5e01668e708a20d3b318996c2'
    rows=[tuple(((int(word,16)>>(16*k)&65535)^32768)-32768 for k in range(4)) for word in encoded.splitlines()]
    check_bank(tmp_path,[rows[p*3300:(p+1)*3300] for p in range(4)],False,packed=True,always_ready=ready)


@pytest.mark.parametrize("delay",range(11))
@pytest.mark.parametrize("reset",[False,True])
def test_each_occupied_read_stage_can_be_discarded_before_new_phase_job(tmp_path,delay,reset):
    values=[[(p*100+n,-p*100-n,32767-n,-32768+n) for n in range(17)] for p in range(4)]
    check_bank(tmp_path,values,reset,packed=True,always_ready=True,cancel_delay=delay)

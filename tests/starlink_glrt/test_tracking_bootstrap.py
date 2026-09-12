"""Explicit GLT1 executable boundary and atomic retained-seed parsing."""
import ctypes as c
import json
import os
import subprocess

import pytest

from tools.starlink_glrt_tracking_abi import bank_id
from tools.starlink_glrt_tracking_journal import batch as python_batch

from . import test_native_radio
from .test_tracking_schedule import RATES
from .test_tracking_schedule import TrackingBatch as CBatch
from .test_tracking_transport import cbatch, descriptor

runner = test_native_radio.runner


@pytest.fixture(scope="module")
def parser(runner):
    lib,_ = runner
    lib.glrt_tracking_batch_parse.argtypes = [c.c_char_p,c.c_size_t,c.POINTER(CBatch)]
    return lib.glrt_tracking_batch_parse


@pytest.mark.parametrize("rate", RATES)
def test_c_seed_decode_matches_python_including_fractional_phase_and_negative_rate(parser,rate):
    for fraction in (0,8192,24576,32768,57344,65535):
        b = descriptor(rate,fraction=fraction)
        text = b.encode().encode()
        parsed = CBatch()
        assert parser(text,len(text),c.byref(parsed)) == 0
        assert parsed.rate == rate
        assert {name:getattr(parsed.prediction,name) for name,_ in parsed.prediction._fields_} == {
            name:getattr(b,name) for name,_ in parsed.prediction._fields_}
        assert python_batch(text.decode(),rate=rate) == b


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("damage", ["prefix", "version", "bank", "rate", "short", "extra", "nul",
    "sign", "hexprefix", "overflow", "epoch_width", "fraction", "expiry", "source_wrap", "canonical",
    "leading_space", "prefix_tab"])
def test_malformed_seed_is_rejected_atomically(parser,rate,damage):
    b = descriptor(rate); fields = b.encode().split()
    if damage=='prefix': fields[0] = 'GLS1'
    elif damage=='version': fields[1] = '00020000'
    elif damage=='bank': fields[3] = '00000000'
    elif damage=='rate': fields[2] = f'{25000000:08x}'
    elif damage=='short': fields.pop()
    elif damage=='extra': fields.append('0')
    elif damage=='nul': fields[-1] += '\0'
    elif damage=='sign': fields[4] = '+3'
    elif damage=='hexprefix': fields[4] = '0x3'
    elif damage=='overflow': fields[6] = '10000000000000000'
    elif damage=='epoch_width': fields[4] = '100000003'
    elif damage=='fraction': fields[7] = '10000'
    elif damage=='expiry': fields[-1] = f'{b.start+b.samples-1:x}'
    elif damage=='source_wrap': fields[6] = f'{2**64-100:x}'
    elif damage=='canonical': fields[1] = '10000'
    text = ' '.join(fields).encode()
    if damage=='leading_space': text = b' '+text
    elif damage=='prefix_tab': text = text.replace(b'GLT1 ',b'GLT1\t',1)
    out = cbatch(b); before = bytes(out)
    assert parser(text,len(text),c.byref(out)) == -1
    assert bytes(out) == before
    with pytest.raises(ValueError): python_batch(text.decode(),rate=rate)


def test_null_or_truncated_buffer_does_not_publish_a_batch(parser):
    b = descriptor(2500000); text = b.encode().encode(); out = cbatch(b); before = bytes(out)
    for size in range(5):
        assert parser(text,size,c.byref(out)) == -1 and bytes(out) == before
    assert parser(None,len(text),c.byref(out)) == -1
    assert parser(text,len(text),None) == -1


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("mode", ["ready", "unrebased", "foreign_profile"])
def test_tracking_cli_uses_only_explicit_rate_bound_attributes(runner,tmp_path,rate,mode):
    _,binary = runner
    origin = 2**60
    b = descriptor(rate,start=origin+rate//200,repeats=16)
    seed = tmp_path/'seed'; seed.write_text(b.encode())
    observed_rate = (15000000 if rate!=15000000 else 30000000) if mode=='foreign_profile' else rate
    w = [0x474c5431,1,3,origin%2**32,origin>>32,0x23 if mode=='unrebased' else 0x33,0]+[0]*13
    w += [observed_rate,observed_rate*33//25000,bank_id(observed_rate),4 if observed_rate==2500000 else 1]
    raw = 'GLT1SNAP 00010000 '+' '.join(f'{x:08x}' for x in w)+'\n'
    (tmp_path/'tracking_snapshot').write_text(raw)
    (tmp_path/'tracking_submit').touch(); (tmp_path/'tracking_command').touch()
    journal = tmp_path/'journal'
    result = subprocess.run([str(binary),str(tmp_path),str(journal),str(seed),'128','1','--tracking'],
                            capture_output=True,text=True,timeout=5,check=False)
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report['protocol'] == 'GLT1' and report['rate'] == rate
    assert report['result'] == (-3 if mode=='unrebased' else -2)
    # Static files cannot acknowledge submission. One valid submit then an
    # inventory mismatch is the expected boundary, never a hardware success.
    assert (tmp_path/'tracking_submit').read_text() == (b.encode() if mode=='ready' else '')
    assert report['configured'] == (16 if mode=='ready' else 0)
    assert (tmp_path/'tracking_command').read_bytes() == b'2\n'
    assert not list(tmp_path.glob('native_schedule_*'))


@pytest.mark.parametrize("damage", ["legacy_seed", "symlink", "fifo", "nul", "short_frames", "expired"])
def test_tracking_cli_bad_seed_fails_before_creating_journal(runner,tmp_path,damage):
    _,binary = runner
    b = descriptor(2500000,repeats=16)
    text = b.encode()
    if damage=='legacy_seed': text = ' '.join(text.split()[4:])
    elif damage=='nul': text += '\0'
    elif damage=='expired': text = ' '.join(text.split()[:-1]+[f'{b.start:x}'])
    seed = tmp_path/'seed'
    if damage=='symlink':
        target = tmp_path/'target'; target.write_text(text); seed.symlink_to(target)
    elif damage=='fifo': os.mkfifo(seed)
    else: seed.write_text(text)
    journal = tmp_path/'journal'
    result = subprocess.run([str(binary),str(tmp_path),str(journal),str(seed),
                             '15' if damage=='short_frames' else '128','1','--tracking'],
                            capture_output=True,timeout=5,check=False)
    assert result.returncode == 2 and not journal.exists()

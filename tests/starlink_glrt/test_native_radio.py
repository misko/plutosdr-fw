"""Executable launch boundary: strict finite acquired seed, no implicit RX."""
import ctypes as c
import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from tests.starlink_glrt.test_native_trend import Batch
from tools.starlink_glrt_schedule_abi import ScheduleBatch

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def runner(tmp_path_factory):
    out = tmp_path_factory.mktemp("native-radio-runner")
    wrapper = out/"wrapper.c"
    wrapper.write_text('#define main native_radio_main\n#include "glrt_native_radio.c"\n'
        'int read_bootstrap(const char *p,struct glrt_native_batch *b) { char raw[256]; size_t n; return bootstrap(p,b,raw,&n); }\n')
    common = ["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT/"tools")]
    sources = [str(ROOT/"tools"/f"glrt_native_{name}.c") for name in
               ("posix", "controller", "trend", "schedule", "solver")]
    subprocess.run([*common, "-shared", "-fPIC", str(wrapper), *sources, "-lm", "-o", str(out/"runner.so")], check=True)
    subprocess.run([*common, str(ROOT/"tools/glrt_native_radio.c"), *sources, "-lm", "-o", str(out/"runner")], check=True)
    lib = c.CDLL(str(out/"runner.so"))
    lib.read_bootstrap.argtypes = [c.c_char_p, c.POINTER(Batch)]
    return lib, out/"runner"


def seed():
    return ScheduleBatch(3, 7, 2**60+300000, 0, 80000*65536, 7310173*65536,
                         0, 17, 16, 2**60+300000+16*80000)


@pytest.mark.parametrize("mutation", ["none", "nul", "sign", "overflow", "epoch_width", "missing",
                                     "extra", "fraction", "prefix", "too_long", "empty", "symlink", "fifo"])
def test_strict_acquisition_seed_parser_never_wraps_or_ignores_hidden_fields(runner, tmp_path, mutation):
    lib, _ = runner
    b = seed()
    data = b.encode().encode()
    if mutation == "nul": data += b"\x00hidden"
    elif mutation == "sign": data = b"+"+data
    elif mutation == "overflow": data = b"10000000000000000 "+b" ".join(data.split()[1:])
    elif mutation == "epoch_width": data = b"100000003 "+b" ".join(data.split()[1:])
    elif mutation == "missing": data = b" ".join(data.split()[:-1])
    elif mutation == "extra": data += b"1"
    elif mutation == "fraction":
        fields = data.split(); fields[3] = b"10000"; data = b" ".join(fields)
    elif mutation == "prefix": data = b"0x"+data
    elif mutation == "too_long": data += b" "*256
    elif mutation == "empty": data = b""
    path = tmp_path/"bootstrap"
    if mutation == "symlink":
        target = tmp_path/"target"; target.write_bytes(data); path.symlink_to(target)
    elif mutation == "fifo": os.mkfifo(path)
    else: path.write_bytes(data)
    actual = Batch()
    rc = lib.read_bootstrap(os.fsencode(path), c.byref(actual))
    assert rc == (0 if mutation == "none" else -1)
    if not rc:
        assert {name: getattr(actual, name) for name, _ in Batch._fields_} == vars(b)


@pytest.mark.parametrize("frames,seconds", [("0", "1"), ("225001", "1"), ("16", "301"),
                                           ("16", "0"), ("16", "nan"), ("+16", "1"),
                                           ("18446744073709551616", "1")])
def test_invalid_bounds_fail_before_creating_journal_or_writing_radio(runner, tmp_path, frames, seconds):
    _, binary = runner
    seed_file = tmp_path/"seed"; seed_file.write_text(seed().encode())
    journal = tmp_path/"journal"
    result = subprocess.run([str(binary), str(tmp_path), str(journal), str(seed_file), frames, seconds],
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 2 and not journal.exists()


def test_runner_requires_operator_rebase_and_never_starts_rx_or_submits_without_it(runner, tmp_path):
    _, binary = runner
    seed_file = tmp_path/"seed"; seed_file.write_text(seed().encode())
    w = [0x474c5331, 1, 3, 1000000, 0, 0x22, 0]+[0]*13
    raw = "GLS1SNAP 00010000 "+" ".join(f"{v:08x}" for v in w)+"\n"
    (tmp_path/"native_schedule_snapshot").write_text(raw)
    (tmp_path/"native_schedule_command").touch()
    result = subprocess.run([str(binary), str(tmp_path), str(tmp_path/"journal"), str(seed_file), "16", "1"],
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 1
    summary = json.loads(result.stdout)
    assert summary["result"] == -3 and summary["configured"] == summary["retained_popped"] == 0
    assert summary["ticks"] == 1 and summary["max_tick_us"] > 0 and summary["elapsed_s"] > 0
    assert (tmp_path/"native_schedule_command").read_text() == "2\n"
    assert not (tmp_path/"native_schedule_submit").exists()
    assert (tmp_path/"native_schedule_snapshot").read_text() == raw


@pytest.mark.parametrize('option,first_count',[(None,64),('--bootstrap-slices',12)])
def test_sliced_startup_is_explicit_and_default_batch_semantics_are_preserved(runner,tmp_path,option,first_count):
    _,binary=runner
    initial=seed()
    initial=replace(initial,repeats=64,expires=initial.start+64*80000)
    seed_file=tmp_path/'seed';seed_file.write_text(initial.encode())
    w=[0x474c5331,1,3,0,2**28,0x33,0]+[0]*13
    (tmp_path/'native_schedule_snapshot').write_text('GLS1SNAP 00010000 '+' '.join(f'{v:08x}' for v in w)+'\n')
    (tmp_path/'native_schedule_submit').touch();(tmp_path/'native_schedule_command').touch()
    command=[str(binary),str(tmp_path),str(tmp_path/'journal'),str(seed_file),'128','1']
    if option:command.append(option)
    result=subprocess.run(command,capture_output=True,text=True,timeout=5)
    # This static port never advances configured counters. The executable must
    # stop after its first submit rather than claiming successful hardware work.
    assert result.returncode==1 and json.loads(result.stdout)['result']==-2
    fields=(tmp_path/'native_schedule_submit').read_text().split()
    assert int(fields[8],16)==first_count
    assert (tmp_path/'native_schedule_command').read_text()=='2\n'


def test_unknown_startup_option_fails_before_io(runner,tmp_path):
    _,binary=runner
    result=subprocess.run([str(binary),str(tmp_path),str(tmp_path/'journal'),
        str(tmp_path/'missing-seed'),'128','1','--unknown'],capture_output=True,timeout=5)
    assert result.returncode==2 and not (tmp_path/'journal').exists()

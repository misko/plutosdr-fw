"""Radio-local POSIX ports: exclusive bounded evidence and exact narrow I/O."""
import ctypes as c
import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from tests.starlink_glrt.test_native_controller import Ports

ROOT = Path(__file__).resolve().parents[2]


class Posix(c.Structure):
    _fields_ = [(name, c.c_int) for name in ("device", "journal", "failed")]+[
        (name, c.c_uint64) for name in ("bytes", "limit")]


@pytest.fixture(scope="module")
def adapter(tmp_path_factory):
    out = tmp_path_factory.mktemp("native-posix")
    common = ["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror"]
    subprocess.run([*common, "-shared", "-fPIC", str(ROOT/"tools/glrt_native_posix.c"),
                    "-o", str(out/"ports.so")], check=True)
    subprocess.run([*common, *(str(ROOT/"tools"/f"glrt_native_{name}.c") for name in
                              ("io_probe", "posix", "schedule", "solver")),
                    "-lm", "-o", str(out/"probe")], check=True)
    lib = c.CDLL(str(out/"ports.so"))
    lib.glrt_native_posix_open.argtypes = [c.POINTER(Posix), c.POINTER(Ports),
                                         c.c_char_p, c.c_char_p, c.c_uint64]
    lib.glrt_native_posix_close.argtypes = [c.POINTER(Posix)]
    return lib, out/"probe"


def open_ports(lib, directory, path, limit=4096):
    io, ports = Posix(), Ports()
    rc = lib.glrt_native_posix_open(c.byref(io), c.byref(ports), os.fsencode(directory), os.fsencode(path), limit)
    return rc, io, ports


def test_exclusive_journal_retains_exact_length_framed_payload_and_private_mode(adapter, tmp_path):
    lib, _ = adapter
    path = tmp_path/"journal"
    rc, io, p = open_ports(lib, tmp_path, path)
    assert rc == 0
    try:
        data = b"line one\nhead 999\n\x00line two"
        assert p.retain(p.context, b"head", data, len(data)) == 0
        assert path.read_bytes() == b"GLRJ1\nhead 27\n"+data
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert open_ports(lib, tmp_path, path)[0] == -1
        assert p.clock(p.context) > 0
    finally:
        assert lib.glrt_native_posix_close(c.byref(io)) == 0
    assert io.device == io.journal == -1


def test_bounded_spool_failure_is_sticky_and_cannot_acknowledge_more_evidence(adapter, tmp_path):
    lib, _ = adapter
    path = tmp_path/"journal"
    rc, io, p = open_ports(lib, tmp_path, path)
    assert rc == 0
    try:
        data = b"x"*4000
        assert p.retain(p.context, b"head", data, len(data)) == 0
        previous = path.read_bytes()
        assert p.retain(p.context, b"head", b"y"*100, 100) == -1
        assert p.retain(p.context, b"head", b"z", 1) == -1
        assert path.read_bytes() == previous and io.failed
    finally:
        lib.glrt_native_posix_close(c.byref(io))


@pytest.mark.parametrize("name", [b"../outside", b"native_schedule_rebase", b"out_altvoltage0_RX_LO_frequency"])
def test_port_names_cannot_escape_to_other_device_attributes(adapter, tmp_path, name):
    lib, _ = adapter
    rc, io, p = open_ports(lib, tmp_path, tmp_path/"journal")
    assert rc == 0
    try:
        raw = c.create_string_buffer(512)
        assert p.read(p.context, name, raw, len(raw)) == -1
        assert p.write(p.context, name, b"1", 1) == -1
    finally:
        lib.glrt_native_posix_close(c.byref(io))


@pytest.mark.parametrize("prefix", ["native_schedule_", "tracking_"])
@pytest.mark.parametrize("read_name", ["result", "snapshot"])
@pytest.mark.parametrize("write_name", ["submit", "pop", "command"])
def test_exact_attribute_bytes_without_implicit_nul_or_newline(adapter, tmp_path,prefix,read_name,write_name):
    lib, _ = adapter
    data = b"GLS1 sample\n"
    read_name,write_name = prefix+read_name,prefix+write_name
    (tmp_path/read_name).write_bytes(data)
    (tmp_path/write_name).touch()
    rc, io, p = open_ports(lib, tmp_path, tmp_path/"journal")
    assert rc == 0
    try:
        raw = c.create_string_buffer(512)
        assert p.read(p.context, read_name.encode(), raw, len(raw)) == len(data)
        assert raw.raw[:len(data)] == data
        assert p.write(p.context, write_name.encode(), b"3 7\n", 4) == 4
        assert (tmp_path/write_name).read_bytes() == b"3 7\n"
    finally:
        lib.glrt_native_posix_close(c.byref(io))


@pytest.mark.parametrize("prefix", ["native_schedule_", "tracking_"])
def test_symlink_attributes_are_not_followed(adapter, tmp_path,prefix):
    lib, _ = adapter
    target = tmp_path/"outside"
    target.write_bytes(b"untouched")
    name = prefix+"command"
    (tmp_path/name).symlink_to(target)
    rc, io, p = open_ports(lib, tmp_path, tmp_path/"journal")
    assert rc == 0
    try:
        assert p.write(p.context, name.encode(), b"2\n", 2) == -1
        assert target.read_bytes() == b"untouched"
    finally:
        lib.glrt_native_posix_close(c.byref(io))


@pytest.mark.parametrize("active", [False, True])
def test_probe_is_read_only_and_requires_idle_cleared_schedule(adapter, tmp_path, active):
    _, probe = adapter
    w = [0x474c5331, 1, 3, 1000000, 0, 0x32 if active else 0x22, 0]+[0]*13
    raw = ("GLS1SNAP 00010000 "+" ".join(f"{v:08x}" for v in w)+"\n").encode()
    (tmp_path/"native_schedule_snapshot").write_bytes(raw)
    result = subprocess.run([str(probe), str(tmp_path), str(tmp_path/"journal")], capture_output=True, text=True)
    if active:
        assert result.returncode == 1
        assert (tmp_path/"journal").read_bytes() == b"GLRJ1\n"
    else:
        assert result.returncode == 0, result.stderr
        summary = json.loads(result.stdout)
        assert summary["iterations"] == 512
        assert summary["scope"] == "idle_snapshot_and_retention_only"
        assert summary["journal_bytes"] == len((tmp_path/"journal").read_bytes())
        assert (tmp_path/"journal").read_bytes() == b"GLRJ1\n"+(f"snapshot {len(raw)}\n".encode()+raw)*512
    assert (tmp_path/"native_schedule_snapshot").read_bytes() == raw

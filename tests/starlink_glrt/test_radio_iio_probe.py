"""Local owner lifecycle without radio access; real IIO/ARM qualification is separate."""
import base64
import csv
import json
import os
from pathlib import Path
import struct
import subprocess

import pytest

from tools.starlink_glrt_local_abi import LocalEvent, LocalIQSnapshot, LocalSearchSnapshot, LocalSourceClosure, attest_capture

SERIAL = "10400056f695001322002d0010ad1719f2"


@pytest.fixture(scope="module")
def probe(tmp_path_factory):
    root = Path(__file__).resolve().parents[2]
    fixture = root/"tests/starlink_glrt/iio_probe_fixture"
    binary = tmp_path_factory.mktemp("iio-probe")/"probe"
    subprocess.run(["cc","-std=c99","-O2","-Wall","-Wextra","-Werror","-I",str(fixture),
        str(root/"tools/glrt_radio_iio_probe.c"),str(root/"tools/glrt_capture_source.c"),
        str(root/"tools/glrt_tracking_recent_iq.c"),str(root/"tools/glrt_tracking_iq_owner.c"),
        str(fixture/"backend.c"),"-pthread","-o",str(binary)],check=True)
    return binary


def run(probe,tmp_path,fault="",arguments=None):
    args = arguments or [SERIAL,"test-fw","917","4096","4",str(tmp_path/"evidence")]
    return subprocess.run([str(probe),*args],env={**os.environ,"PROBE_FAULT":fault,
        "PROBE_TRACE":str(tmp_path/"trace")},capture_output=True,text=True,timeout=10)


@pytest.mark.parametrize("attribute_encoding", ["", "newline_attrs"])
def test_one_owner_saves_exact_contiguous_iq_and_independently_attested_closure(probe,tmp_path,attribute_encoding):
    result = run(probe,tmp_path,attribute_encoding)
    assert result.returncode == 0,result.stdout+result.stderr
    status = json.loads(result.stdout)
    assert status["completed_blocks"] == 4 and status["events"] == 1
    root = tmp_path/"evidence"
    iq = (root/"iq.ci16").read_bytes()
    assert iq == struct.pack("<32768h",*(i-32768 for i in range(32768)))
    snapshot = lambda name: LocalIQSnapshot.decode((root/(name+"_snapshot.txt")).read_text())
    closure = lambda name: LocalSourceClosure.decode((root/(name+"_extension_snapshot.txt")).read_text())
    search = lambda name: LocalSearchSnapshot.decode((root/(name+"_local_search_snapshot.txt")).read_text())
    evidence = attest_capture(final=snapshot("final"),baseline=snapshot("baseline"),source=closure("final"),
        source_baseline=closure("baseline"),search=search("final"),search_baseline=search("baseline"),
        events=[LocalEvent.decode((root/"events.raw").read_bytes())],received_bytes=len(iq))
    assert evidence["samples"] == 16384 and evidence["completed"] == 1 and evidence["supported"] == 0
    with (root/"blocks.csv").open() as stream: rows = list(csv.DictReader(stream))
    for n,(row,wire) in enumerate(zip(rows,(root/"block_snapshots.txt").read_text().splitlines(),strict=True)):
        s = LocalIQSnapshot.decode(wire)
        assert int(row["first"]) == 100+n*4096
        assert int(row["source_now"]) == s.u64(42)+1 == 100+(n+1)*4096+124
        times = [int(value) for key,value in row.items() if key.endswith("_ns")]
        assert times == sorted(times) and times[0] > 0
    assert (tmp_path/"trace").read_text() == "1 1 1\n"
    assert (root/"rf_before.txt").read_bytes() == (root/"rf_after.txt").read_bytes()


@pytest.mark.parametrize("fault,stage,trace", [
    ("identity","pinned_identity","0 0 0"),("rate","rf_before","0 0 0"),
    ("tx_enabled","rf_before","0 0 0"),("embedded_nul","rf_before","0 0 0"),("layout","scan_layout","0 0 0"),
    ("nonblocking","nonblocking_events","0 0 1"),("refill","whole_iq_block","1 1 1"),
    ("partial","whole_iq_block","1 1 1"),("source_gap","block_source_binding","1 1 1"),
    ("stale_snapshot","block_source_binding","1 1 1"),("event_sequence","live_event_drain","1 1 1"),
    ("rf_change","rf_after","1 1 1")])
def test_failure_never_claims_capture_and_closes_only_owned_buffers(probe,tmp_path,fault,stage,trace):
    result = run(probe,tmp_path,fault)
    assert result.returncode == 1,result.stdout+result.stderr
    assert json.loads(result.stdout)["failed_stage"] == stage
    assert (tmp_path/"trace").read_text().strip() == trace
    if trace.startswith("1"):
        assert (tmp_path/"evidence/final_snapshot.txt").is_file()


@pytest.mark.parametrize("index,value", [(0,"bad/name"),(1,"bad/name"),(2,"0"),(2,"4294967296"),
    (3,"4095"),(3,"250002"),(4,"0"),(4,"999999999999999999999"),(4,"4000"),(5,"relative")])
def test_invalid_or_unbounded_requests_do_not_open_context(probe,tmp_path,index,value):
    args = [SERIAL,"test-fw","917","4096","4",str(tmp_path/"evidence")];args[index]=value
    assert run(probe,tmp_path,arguments=args).returncode == 2
    assert not (tmp_path/"trace").exists() and not (tmp_path/"evidence").exists()


def test_existing_evidence_directory_cannot_be_overwritten(probe,tmp_path):
    target = tmp_path/"evidence";target.mkdir();sentinel=target/"iq.ci16";sentinel.write_bytes(b"preserve")
    result = run(probe,tmp_path)
    assert result.returncode == 1 and json.loads(result.stdout)["failed_stage"] == "new_output_directory"
    assert sentinel.read_bytes() == b"preserve" and not (tmp_path/"trace").exists()


@pytest.mark.parametrize("length", [0,1,2,3,47,48,49,12287,12288,12289,30000])
def test_post_capture_binary_export_matches_independent_codec_without_iio(probe,tmp_path,length):
    raw=bytes(i%256 for i in range(length))
    result=subprocess.run([str(probe),"--base64"],input=raw,capture_output=True,
        env={**os.environ,"PROBE_TRACE":str(tmp_path/"trace")},timeout=5)
    assert result.returncode == 0
    lines=result.stdout.splitlines()
    assert lines[0] == b"GLRTBASE64_BEGIN" and lines[-1] == b"GLRTBASE64_END"
    assert b"".join(lines[1:-1]) == base64.b64encode(raw)
    assert not (tmp_path/"trace").exists()

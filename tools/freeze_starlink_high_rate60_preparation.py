#!/usr/bin/env python3
"""Bounded generated evidence archive; not part of the311 policy-test claim."""

import io
import json
import platform
import subprocess
import sys
import tarfile
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tests.starlink_oracle.high_rate60_bundle import inventory, verify_bundle
from tests.starlink_oracle.native60_budget import encoded, require, sha

BUNDLE = ROOT/"build/high-rate60-harness-prelaunch-v1"
BUNDLE_SHA = "b5f7d48a96217691d7a034634d3bdc7006e489066e571d93b00ce2ed5f741714"
ARCHIVE = ROOT/"reports/experiments/20260910-high-rate60-harness-prelaunch-v1.tgz"
REPORT = ROOT/"docs/starlink-high-rate60-harness-prelaunch-20260910.md"


def main():
    require(not ARCHIVE.exists() and not ARCHIVE.with_suffix(".json").exists(), "no archive overwrite")
    r=verify_bundle(BUNDLE,BUNDLE_SHA)
    before={name:sha((ROOT/name).read_bytes()) for name in r["source_sha256"]}
    require(before==r["source_sha256"], "live sources drifted before packaging")
    paths={"inputs/"+name:BUNDLE/name for name in inventory(BUNDLE)}
    paths["report.md"]=REPORT
    paths["collector.py"]=Path(__file__)
    for v in range(1,5):
        for name in ["pytest.log","junit.xml"]:
            paths[f"attempt-v{v}/"+name]=ROOT/f"build/high-rate60-harness-offline-v{v}"/name
    base=Path("/tmp/starlink-highrate60-harness-tests-v4")
    for folder in ["test_entire_composition_compil0", "test_tiny_clock_and_unknown_he0"]:
        for path in sorted((base/folder).rglob("*")):
            require(not path.is_symlink(), "unexpected compile/unit evidence symlink")
            if path.is_file() and path.suffix!=".vvp":
                paths["offline-tests/"+path.relative_to(base).as_posix()]=path
    payloads={name:path.read_bytes() for name,path in paths.items()}
    payloads["packaging-receipt.json"]=encoded({"bundle_sha256":BUNDLE_SHA,"source_before":before,
        "collector_pytest_qualified":False,"actual_vendor_service":False,"host":platform.platform(),
        "python":sys.version,"python_binary_sha256":sha(Path(sys.executable).read_bytes()),
        "fw_tested":"aac863cea50cffd99b90f516286751c38e15c8b9",
        "hdl_tested":"88195cd9029a0c66f642fe21045ff70053fc46de",
        "raw_attempts_preserved":[f"/tmp/starlink-highrate60-harness-tests-v{v}" for v in range(1,5)],
        "omitted_generated_parser_specimens_and_stub_projects":True,
        "iverilog_version":subprocess.run(["iverilog","-V"],capture_output=True,text=True,check=True).stdout.splitlines()[0]})
    require(len(payloads)<=500 and sum(map(len,payloads.values()))<15_000_000,"bounded archive exceeded")
    for name in payloads:
        require(not Path(name).is_absolute() and ".." not in Path(name).parts,"unsafe member")
    after={name:sha((ROOT/name).read_bytes()) for name in r["source_sha256"]}
    require(before==after,"live source changed during packaging")
    verify_bundle(BUNDLE,BUNDLE_SHA)
    payloads["source-after.json"]=encoded(after)
    receipts={name:{"sha256":sha(data),"bytes":len(data)} for name,data in sorted(payloads.items())}
    payloads["receipts.json"]=encoded(receipts)
    ARCHIVE.parent.mkdir(parents=True,exist_ok=True)
    with tarfile.open(ARCHIVE,"w:gz") as archive:
        for name,data in sorted(payloads.items()):
            info=tarfile.TarInfo(name); info.size=len(data); info.mtime=0; info.mode=0o644
            archive.addfile(info,io.BytesIO(data))
    with tarfile.open(ARCHIVE,"r:gz") as archive:
        members=archive.getmembers()
        require(len(members)==len(payloads) and all(m.isfile() for m in members),"archive member safety")
        require({m.name:archive.extractfile(m).read() for m in members}==payloads,"archive byte roundtrip failed")
    summary={"archive":ARCHIVE.name,"sha256":sha(ARCHIVE.read_bytes()),"bytes":ARCHIVE.stat().st_size,
             "members":len(payloads),"receipt_files":len(receipts),"files":receipts,
             "bundle_sha256":BUNDLE_SHA,"source_signature":r["source_signature"]}
    ARCHIVE.with_suffix(".json").write_bytes(encoded(summary))
    print(json.dumps({key:summary[key] for key in summary if key!="files"},sort_keys=True))


if __name__=="__main__":
    main()

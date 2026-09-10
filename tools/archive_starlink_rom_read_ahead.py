"""Archive retained ROM-prototype test attempts; never execute or qualify RTL."""

import argparse
import hashlib
import io
import json
import tarfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("initial", "second", "final", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    output = args.output
    receipt_path = output.with_suffix(".json")
    if output.exists() or receipt_path.exists() or any(
        p.is_symlink() for p in (output, receipt_path, *output.parents)
    ):
        raise ValueError("refusing existing/symlinked output")
    root = Path(__file__).resolve().parents[1]
    members = {}
    excluded = []
    for label in ("initial", "second", "final"):
        directory = getattr(args, label)
        if not directory.is_dir() or any(p.is_symlink() for p in (directory, *directory.parents)):
            raise ValueError("missing/symlinked attempt")
        for path in sorted(directory.rglob("*")):
            name = label + "/" + path.relative_to(directory).as_posix()
            if path.is_symlink():
                if not path.name.endswith("current"):
                    raise ValueError("unexpected non-pytest symlink")
                excluded.append(name)
            elif path.is_file():
                members[name] = path
    for relative in (
        "hdl/library/starlink_pss_acquisition/starlink_pss_kernel_rom_read_ahead.v",
        "hdl/library/starlink_pss_acquisition/tb/tb_starlink_pss_rom_read_ahead.sv",
        "tests/starlink_oracle/rom_prefetch_delta.json",
        "tests/starlink_oracle/test_rom_read_ahead.py",
        "tools/archive_starlink_rom_read_ahead.py",
    ):
        members["source/" + relative] = root / relative
    sizes = [path.stat().st_size for path in members.values()]
    if not members or len(members) > 10000 or max(sizes) > 64*1024**2 or sum(sizes) > 128*1024**2:
        raise ValueError("archive size/member budget exceeded")
    hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in members.items()}
    receipt = {
        "scope": "retained_offline_attempts_NOT_actual_FFT_or_physical_qualification",
        "members": len(members), "file_sha256": hashes,
        "excluded_pytest_current_symlinks": excluded,
    }
    payload = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
    with tarfile.open(output, "x:gz") as archive:
        for name, path in sorted(members.items()):
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != hashes[name]:
                raise ValueError("source changed during archival")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        info = tarfile.TarInfo("receipt.json")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    with output.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    receipt.update(archive_sha256=digest, archive_bytes=output.stat().st_size)
    with receipt_path.open("x") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({k: v for k, v in receipt.items() if k != "file_sha256"}))


if __name__ == "__main__":
    main()

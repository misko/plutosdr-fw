"""Losslessly reconstruct ordered archive bytes in a new directory, without overwrite.

Narrow generic adaptation of the reviewed control WDB-parts helper. The payload
is an opaque archive, not a WDB, and no decompression or extraction is performed.
"""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

MAX_PART_BYTES = 40 * 1024 * 1024


def identity(path):
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            size += len(block)
            digest.update(block)
    return {"bytes": size, "sha256": digest.hexdigest()}


def validate(manifest):
    if manifest.get("format") != "starlink-portable-archive-parts-v1":
        raise ValueError("unknown portable archive format")
    archive = manifest["archive"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", archive["name"]) or archive["name"] in {".", ".."}:
        raise ValueError("unsafe output filename")
    if type(archive["bytes"]) is not int or archive["bytes"] <= 0:
        raise ValueError("invalid archive size")
    if not re.fullmatch(r"[0-9a-f]{64}", archive["sha256"]):
        raise ValueError("invalid archive digest")
    if manifest.get("max_part_bytes") != MAX_PART_BYTES:
        raise ValueError("unexpected portable part limit")
    parts = manifest["parts"]
    if not isinstance(parts, list) or not parts:
        raise ValueError("missing part inventory")
    total = 0
    for index, part in enumerate(parts):
        if type(part["index"]) is not int or part["index"] != index:
            raise ValueError("missing or reordered part index")
        if part["name"] != f"{archive['name']}.part{index:03d}":
            raise ValueError("missing or reordered part filename")
        if type(part["bytes"]) is not int or not 0 < part["bytes"] <= MAX_PART_BYTES:
            raise ValueError("invalid part size")
        if not re.fullmatch(r"[0-9a-f]{64}", part["sha256"]):
            raise ValueError("invalid part digest")
        total += part["bytes"]
    if total != archive["bytes"]:
        raise ValueError("part size total differs")


def reconstruct(manifest_path, output_dir):
    manifest_path, output_dir = Path(manifest_path).resolve(), Path(output_dir).resolve()
    if output_dir.exists():
        raise FileExistsError("refusing to overwrite reconstruction evidence")
    manifest = json.loads(manifest_path.read_text())
    validate(manifest)
    for part in manifest["parts"]:
        path = manifest_path.parent / part["name"]
        if path.is_symlink() or identity(path) != {key: part[key] for key in ("bytes", "sha256")}:
            raise ValueError(f"part hash/size mismatch: {part['name']}")
    output_dir.mkdir()
    assembled = output_dir / manifest["archive"]["name"]
    with assembled.open("xb") as target:
        for part in manifest["parts"]:
            with (manifest_path.parent / part["name"]).open("rb") as source:
                shutil.copyfileobj(source, target, 1024 * 1024)
    actual = identity(assembled)
    if actual != {key: manifest["archive"][key] for key in ("bytes", "sha256")}:
        raise ValueError("assembled archive hash/size mismatch")
    return {"parts": len(manifest["parts"]), "archive": actual}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(reconstruct(args.manifest, args.output_dir), sort_keys=True))


if __name__ == "__main__":
    main()

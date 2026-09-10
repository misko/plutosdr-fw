"""Opaque archive reconstruction only; no simulation or artifact extraction."""
import hashlib
import importlib.util
import json
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("archive_parts", ROOT / "tools/starlink_reconstruct_archive_parts.py")
PARTS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PARTS)


def small_manifest(tmp_path):
    raw = bytes(range(256)) * 8
    identity = lambda data: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    manifest = {"format": "starlink-portable-archive-parts-v1", "max_part_bytes": 41943040,
                "archive": {"name": "evidence.tgz", **identity(raw)}, "parts": []}
    for index, offset in enumerate(range(0, len(raw), 100)):
        data = raw[offset:offset + 100]
        name = f"evidence.tgz.part{index:03d}"
        (tmp_path / name).write_bytes(data)
        manifest["parts"].append({"index": index, "name": name, **identity(data)})
    path = tmp_path / "parts.json"
    path.write_text(json.dumps(manifest))
    return path, manifest, raw


def test_lossless_small_reconstruction_and_no_overwrite(tmp_path):
    path, manifest, raw = small_manifest(tmp_path)
    output = tmp_path / "reconstructed"
    assert PARTS.reconstruct(path, output)["parts"] == len(manifest["parts"])
    assert (output / "evidence.tgz").read_bytes() == raw
    with pytest.raises(FileExistsError, match="overwrite"):
        PARTS.reconstruct(path, output)
    assert (output / "evidence.tgz").read_bytes() == raw


@pytest.mark.parametrize("fault", ["missing", "reordered", "corrupt", "oversized", "traversal",
                                  "archive_digest", "size_total", "duplicate", "symlink"])
def test_missing_reordered_corrupt_unsafe_and_identity_failures_rejected(tmp_path, fault):
    path, manifest, _ = small_manifest(tmp_path)
    part = tmp_path / manifest["parts"][1]["name"]
    if fault == "missing":
        part.unlink()
    elif fault == "reordered":
        manifest["parts"][0], manifest["parts"][1] = manifest["parts"][1], manifest["parts"][0]
    elif fault == "corrupt":
        data = bytearray(part.read_bytes()); data[0] ^= 1; part.write_bytes(data)
    elif fault == "oversized":
        manifest["parts"][0]["bytes"] = 41943041
    elif fault == "traversal":
        manifest["archive"]["name"] = "../evidence.tgz"
    elif fault == "archive_digest":
        manifest["archive"]["sha256"] = "0" * 64
    elif fault == "size_total":
        manifest["archive"]["bytes"] += 1
    elif fault == "duplicate":
        manifest["parts"][1]["name"] = manifest["parts"][0]["name"]
    else:
        alternate = tmp_path / "retained_part"
        part.rename(alternate)
        part.symlink_to(alternate)
    path.write_text(json.dumps(manifest))
    with pytest.raises(FileNotFoundError if fault == "missing" else ValueError):
        PARTS.reconstruct(path, tmp_path / "reconstructed")
    assert (tmp_path / "reconstructed").exists() == (fault == "archive_digest")


def test_actual_original_archive_reconstructed_and_every_safe_member_hash_verified(tmp_path):
    reports = ROOT / "reports/experiments"
    name = "20260910-bank-arithmetic-monitor-actual175-originals-v3"
    result = PARTS.reconstruct(reports / (name + ".parts.json"), tmp_path / "actual-reconstructed")
    assert result == {"parts": 6, "archive": {"bytes": 241304017,
        "sha256": "470f5a8c81ca725d77efcdbbe8bd506a2b02921d9be88ac40602eb5c0304848e"}}
    receipt = json.loads((reports / (name + ".json")).read_text())
    archive = tmp_path / "actual-reconstructed" / (name + ".tgz")
    with tarfile.open(archive) as package:
        members = package.getmembers()
        assert len(members) == len({member.name for member in members}) == 341
        for member in members:
            assert member.isfile() and not member.name.startswith("/") and ".." not in Path(member.name).parts
            assert hashlib.sha256(package.extractfile(member).read()).hexdigest() == receipt["archive_file_sha256"][member.name]
    (tmp_path / "actual-reconstruction-receipt.json").write_text(json.dumps(result, indent=2) + "\n")

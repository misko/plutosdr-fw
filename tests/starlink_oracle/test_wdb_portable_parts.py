"""Lossless artifact packaging only; no simulation or runtime changes."""

import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ARCHIVE = Path(__file__).resolve().parents[2] / (
    "hdl/library/starlink_pss_acquisition/evidence/exact-control-combined-actual-v1"
)
SPEC = importlib.util.spec_from_file_location(
    "wdb_parts", ARCHIVE / "reconstruct_wdb_parts.py"
)
PARTS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PARTS)


def small_manifest(tmp_path):
    raw = bytes(range(256)) * 8
    compressed = gzip.compress(raw, mtime=0)
    identity = lambda data: {
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    manifest = {
        "format": "starlink-portable-gzip-parts-v1",
        "max_part_bytes": 41943040,
        "gzip": {"name": "trace.wdb.gz", **identity(compressed)},
        "uncompressed": {"name": "trace.wdb", **identity(raw)},
        "parts": [],
    }
    for index, offset in enumerate(range(0, len(compressed), 100)):
        data = compressed[offset : offset + 100]
        name = f"trace.wdb.gz.part{index:03d}"
        (tmp_path / name).write_bytes(data)
        manifest["parts"].append({"index": index, "name": name, **identity(data)})
    path = tmp_path / "parts.json"
    path.write_text(json.dumps(manifest))
    return path, manifest, compressed, raw


def test_lossless_small_reconstruction_and_no_overwrite(tmp_path):
    path, manifest, compressed, raw = small_manifest(tmp_path)
    output = tmp_path / "reconstructed"
    result = PARTS.reconstruct(path, output)
    assert result["parts"] == len(manifest["parts"])
    assert (output / "trace.wdb.gz").read_bytes() == compressed
    assert (output / "trace.wdb").read_bytes() == raw
    with pytest.raises(FileExistsError, match="overwrite"):
        PARTS.reconstruct(path, output)
    assert (output / "trace.wdb.gz").read_bytes() == compressed
    assert (output / "trace.wdb").read_bytes() == raw


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "reordered",
        "corrupt",
        "oversized",
        "traversal",
        "gzip_digest",
        "raw_digest",
        "size_total",
    ],
)
def test_missing_reordered_corrupt_unsafe_and_identity_failures_rejected(
    tmp_path, fault
):
    path, manifest, _, _ = small_manifest(tmp_path)
    if fault == "missing":
        (tmp_path / manifest["parts"][1]["name"]).unlink()
    elif fault == "reordered":
        manifest["parts"][0], manifest["parts"][1] = (
            manifest["parts"][1],
            manifest["parts"][0],
        )
    elif fault == "corrupt":
        part = tmp_path / manifest["parts"][1]["name"]
        data = bytearray(part.read_bytes())
        data[0] ^= 1
        part.write_bytes(data)
    elif fault == "oversized":
        manifest["parts"][0]["bytes"] = 41943041
    elif fault == "traversal":
        manifest["gzip"]["name"] = "../trace.wdb.gz"
    elif fault == "gzip_digest":
        manifest["gzip"]["sha256"] = "0" * 64
    elif fault == "raw_digest":
        manifest["uncompressed"]["sha256"] = "0" * 64
    elif fault == "size_total":
        manifest["gzip"]["bytes"] += 1
    path.write_text(json.dumps(manifest))
    output = tmp_path / "reconstructed"
    marker = {
        "missing": None,
        "reordered": "reordered part index",
        "corrupt": "part hash/size",
        "oversized": "invalid part size",
        "traversal": "unsafe output filename",
        "gzip_digest": "assembled gzip hash/size",
        "raw_digest": "uncompressed WDB hash/size",
        "size_total": "part size total",
    }[fault]
    with pytest.raises(
        FileNotFoundError if fault == "missing" else ValueError, match=marker
    ):
        PARTS.reconstruct(path, output)
    assert output.exists() == (fault in {"gzip_digest", "raw_digest"})


def test_actual_full_saved_wdb_reconstruction_exact(tmp_path):
    output = tmp_path / "actual-reconstructed"
    result = PARTS.reconstruct(ARCHIVE / "simulation/wdb-parts.json", output)
    assert result == {
        "parts": 3,
        "gzip": {
            "bytes": 105807603,
            "sha256": "bbc9ffd1d907b80ed4522b0b2d28b1ee62ead1810fc542681a12908b6e8341ea",
        },
        "uncompressed": {
            "bytes": 116445321,
            "sha256": "12d13666cf7d62c65581d66150539e2105c5db06d0c621357affb54da3f8a20f",
        },
    }
    (tmp_path / "actual-reconstruction-receipt.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )

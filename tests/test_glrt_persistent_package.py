"""Persistent package preserves verified FIT bytes and fails on stale evidence."""
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from scripts.package_glrt_persistent import digest, package


def inputs(tmp_path):
    source = tmp_path / "ram"
    source.mkdir()
    dts = source / "minimal.dts"
    dts.write_text('/dts-v1/; / { magic = "ITB PlutoSDR (ADALM-PLUTO)"; };\n')
    fit = source / "pluto.itb"
    subprocess.run(["dtc", "-I", "dts", "-O", "dtb", "-o", str(fit), str(dts)], check=True)
    manifest = {"schema": "starlink-glrt-ram-package/v1", "firmware_label": "glrt-test",
                "source_rate_hz": 2500000, "output_rate_hz": 2500000, "edge": "upper",
                "source_commits": {"firmware": "fixture"},
                "outputs_sha256": {"pluto.itb": digest(fit), "pluto.dfu": "fixture"}}
    (source / "manifest.json").write_text(json.dumps(manifest))
    receipt = tmp_path / "verification.json"
    receipt.write_text(json.dumps({
        "schema": "starlink-glrt-independent-package-verification/v1", "status": "pass",
        "manifest_sha256": digest(source / "manifest.json"),
        "outputs_sha256": manifest["outputs_sha256"]}))
    return source, receipt


def test_persistent_image_matches_existing_makefile_format(tmp_path):
    source, receipt = inputs(tmp_path)
    before = (source / "pluto.itb").read_bytes()
    output = tmp_path / "persistent"
    result = package(source, receipt, output)
    checksum = subprocess.check_output(["md5sum", str(source / "pluto.itb")]).split()[0]
    assert (output / "pluto.frm").read_bytes() == before + checksum + b"\n"
    assert result["frm_bytes"] == len(before) + 33
    assert result["fit_sha256"] == hashlib.sha256(before).hexdigest()
    assert result["hardware_qualified"] is result["deployment_approved"] is False
    assert (source / "pluto.itb").read_bytes() == before
    with pytest.raises(FileExistsError):
        package(source, receipt, output)


@pytest.mark.parametrize("changed", ["fit", "manifest", "receipt_status", "receipt_outputs"])
def test_changed_or_failed_verification_cannot_produce_persistent_image(tmp_path, changed):
    source, receipt = inputs(tmp_path)
    if changed == "fit":
        with (source / "pluto.itb").open("ab") as stream:
            stream.write(b"bad")
    elif changed == "manifest":
        with (source / "manifest.json").open("a") as stream:
            stream.write("\n")
    else:
        value = json.loads(receipt.read_text())
        if changed == "receipt_status":
            value["status"] = "fail"
        else:
            value["outputs_sha256"]["pluto.itb"] = "different"
        receipt.write_text(json.dumps(value))
    output = tmp_path / "persistent"
    with pytest.raises(ValueError):
        package(source, receipt, output)
    assert not output.exists()


def test_verified_blob_with_trailing_data_is_not_treated_as_fit(tmp_path):
    source, receipt = inputs(tmp_path)
    fit = source / "pluto.itb"
    fit.write_bytes(fit.read_bytes() + b"suffix")
    manifest_path = source / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["outputs_sha256"]["pluto.itb"] = digest(fit)
    manifest_path.write_text(json.dumps(manifest))
    evidence = json.loads(receipt.read_text())
    evidence.update(manifest_sha256=digest(manifest_path), outputs_sha256=manifest["outputs_sha256"])
    receipt.write_text(json.dumps(evidence))
    with pytest.raises(ValueError, match="one complete FDT"):
        package(source, receipt, tmp_path / "persistent")

"""Keep the v0.51 direct-async route and source locks consistent."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_direct_async_v5_release_route_and_locks():
    workflow = (ROOT / ".github/workflows/firmware-main.yml").read_text()
    branch = "refs/heads/codex/issue-102-fw-release"
    assert workflow.count(branch) == 4
    assert workflow.count("'v0.51-plutoplus-spf-iq-direct-async-v5'") == 1
    assert workflow.count("'iq-direct-async-v5-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-iq-direct-async-v5'") == 1
    manifest = dict(
        line.split(": ", 1)
        for line in (ROOT / "manifests/iq-direct-async-v5-source.yaml").read_text().splitlines()
        if ": " in line and not line.startswith("#")
    )
    for component in ("buildroot", "linux", "hdl", "hdl-quantulum", "u-boot-xlnx"):
        pin = subprocess.check_output(
            ["git", "ls-files", "--stage", component], cwd=ROOT, text=True
        ).split()[1]
        assert manifest["submodule_" + component.replace("-", "_")] == pin
    assert manifest["libiio_0_25_source"] == "0de80c0ed05fed86da58ff5afadfdda83dadd0e1"
    assert manifest["libiio_0_25_archive_sha256"] == "7dddda42e75231797a59933958d2c34a9abc2c6943fa0161d98e9aa38d64c056"
    for script in ("scripts/build_gain_series_candidate.sh", "scripts/ci/package_main_firmware.sh"):
        assert "iq-direct-async-v5-source.yaml |" in (ROOT / script).read_text()

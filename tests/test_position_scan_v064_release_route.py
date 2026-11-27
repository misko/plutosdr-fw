"""Keep the new scanner route source locked without changing past releases."""

from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
NAME = "position-scan-v064-source.yaml"
VERSION = "v0.64-plutoplus-spf-position-scan"
BRANCH = "refs/heads/codex/position-scan-v064"


def manifest(name):
    return dict(line.split(": ", 1) for line in (ROOT / "manifests" / name).read_text().splitlines()
                if ": " in line and not line.startswith("#"))


def test_v064_binds_corrected_daemon_and_preserves_unchanged_sources():
    current = manifest(NAME)
    previous = manifest("continuous-fast-scan-v063-source.yaml")
    assert current["release_state"] in ("candidate", "final-release")
    assert current["submodule_linux"] == "5bc91a9be7dd19b8528506a025fc6a89c0273420"
    assert current["libiio_0_25_source"] == "43580988b7cf26141309b02d55dcb68b470e2181"
    assert current["libiio_0_25_ref"] == "refs/tags/position-scan-v064-source/libiio-v2"
    assert current["submodule_buildroot_ref"] == "refs/tags/position-scan-v064-source/buildroot-v2"
    for component in ("buildroot", "linux", "hdl", "hdl-quantulum", "u-boot-xlnx"):
        key = "submodule_" + component.replace("-", "_")
        staged = subprocess.check_output(["git", "ls-files", "--stage", "--", component],
                                         cwd=ROOT, text=True).split()
        assert staged[0] == "160000" and staged[1] == current[key]
        assert current[key + "_ref"].startswith("refs/tags/")
    for key in previous:
        if key.startswith(("metadata_", "gadget_", "ip_gadget_", "submodule_hdl", "submodule_u_boot")):
            assert current[key] == previous[key]
    assert len(current["libiio_0_25_archive_sha256"]) == 64


def test_candidate_and_main_require_v064_identity_and_keep_v063_history():
    workflow = (ROOT / ".github/workflows/firmware-main.yml").read_text()
    for branch in (BRANCH, "refs/heads/main"):
        assert f"github.ref == '{branch}' &&\n          '{NAME}'" in workflow
    for title, branch in (("position scan candidate", BRANCH), ("final release", "refs/heads/main")):
        gate = re.search(r"- name: Require the exact " + title + r" identity\n(?P<body>.*?)(?=\n      - name:)",
                         workflow, re.DOTALL)
        assert gate is not None
        assert f"github.ref == '{branch}'" in gate["body"] and f"'{VERSION}'" in gate["body"]
    package = (ROOT / "scripts/ci/package_main_firmware.sh").read_text()
    assert f"{NAME}:candidate | {NAME}:final-release)" in package
    assert f"protected_version='{VERSION}'" in package
    assert "continuous-fast-scan-v063-source.yaml:final-release)" in package
    checker = (ROOT / "scripts/check_tandem_release_offline.sh").read_text()
    assert "SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/continuous-fast-scan-v063-source.yaml" in checker
    assert f"    ./scripts/check_source_graph.sh manifests/{NAME}" in checker
    ci = (ROOT / ".github/workflows/firmware.yml").read_text()
    assert "python3 -m unittest discover -s scripts/v064 -v" in ci

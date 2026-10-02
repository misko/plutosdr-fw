"""Prevent main from rebuilding the old kernel after the issue-119 merge."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def test_main_source_graph_preserves_v059_and_routes_fixed_kernel():
    name = 'fastlock-attestation-v059-source.yaml'
    manifest = dict(line.split(': ',1) for line in (ROOT/'manifests'/name).read_text().splitlines() if ': ' in line and not line.startswith('#'))
    baseline = dict(line.split(': ',1) for line in (ROOT/'manifests/dual-rx-counter-fix-v059-source.yaml').read_text().splitlines() if ': ' in line and not line.startswith('#'))
    for component in ('buildroot','linux','hdl','hdl-quantulum','u-boot-xlnx'):
        entry = subprocess.check_output(['git','ls-files','--stage','--',component],cwd=ROOT,text=True).split()
        key = 'submodule_'+component.replace('-','_')
        assert manifest[key] == entry[1]
        if component not in ('linux','buildroot'):
            assert manifest[key] == baseline[key]
    assert manifest['libiio_0_25_source'] != baseline['libiio_0_25_source']
    assert manifest['submodule_linux'] != baseline['submodule_linux']
    workflow = (ROOT/'.github/workflows/firmware-main.yml').read_text()
    assert "(github.ref == 'refs/heads/main' || github.ref == 'refs/heads/codex/issue-119') &&\n          '"+name+"'" in workflow
    assert "'v0.59-issue119-fastlock-rc2'" in workflow
    for script in ('scripts/build_gain_series_candidate.sh','scripts/ci/package_main_firmware.sh'):
        assert name in (ROOT/script).read_text()

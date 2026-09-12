"""Keep the counter release's trusted route and component locks consistent."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_counter_release_route_and_locks():
    workflow = (ROOT / '.github/workflows/firmware-main.yml').read_text()
    branch = 'refs/heads/codex/issue-97-counter-metadata'
    assert workflow.count(branch) == 4
    assert workflow.count("'v0.50-plutoplus-spf-counter-rx-v1'") == 2
    assert workflow.count("'counter-rx-v1-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-counter-rx-v1'") == 1
    manifest = dict(
        line.split(': ', 1)
        for line in (ROOT / 'manifests/counter-rx-v1-source.yaml').read_text().splitlines()
        if ': ' in line and not line.startswith('#')
    )
    for component in ('buildroot', 'linux', 'hdl', 'hdl-quantulum', 'u-boot-xlnx'):
        pin = subprocess.check_output(
            ['git', 'ls-files', '--stage', component], cwd=ROOT, text=True
        ).split()[1]
        assert manifest['submodule_' + component.replace('-', '_')] == pin
    assert manifest['libiio_0_25_source'] == '47a75cbc5e7d24a063b8b54eb531fdba6602b85c'
    assert manifest['libiio_0_25_archive_sha256'] == 'a6676eee9318a38d25e098ce7dce78c3af7df3f8e357f40efdf7f059e8ef2d50'
    for script in ('scripts/build_gain_series_candidate.sh', 'scripts/ci/package_main_firmware.sh'):
        assert 'counter-rx-v1-source.yaml |' in (ROOT / script).read_text()

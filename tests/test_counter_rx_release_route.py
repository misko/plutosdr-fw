"""Keep the counter release's trusted route and component locks consistent."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_counter_release_route_and_locks():
    workflow = (ROOT / '.github/workflows/firmware-main.yml').read_text()
    branch = 'refs/heads/codex/issue-97-counter-metadata'
    assert workflow.count(branch) == 4
    counter_gate = re.search(
        r"- name: Require the exact counter RX v1 candidate identity\n"
        r"(?P<body>.*?)(?=\n      - name:)",
        workflow,
        re.DOTALL,
    )
    assert counter_gate is not None
    assert branch in counter_gate["body"]
    assert "'v0.50-plutoplus-spf-counter-rx-v1'" in counter_gate["body"]
    assert workflow.count("'counter-rx-v1-source.yaml'") == 1
    assert workflow.count("'plutoplus-spf-counter-rx-v1'") == 1
    manifest = dict(
        line.split(': ', 1)
        for line in (ROOT / 'manifests/counter-rx-v1-source.yaml').read_text().splitlines()
        if ': ' in line and not line.startswith('#')
    )
    expected_submodules = {
        'buildroot': 'fedd002ca16d4cd6eb6aec4db851d8249c5aff93',
        'linux': '4683cd2e3556448295e03a216a3a7fc6e8bbc474',
        'hdl': '145bd47e55d5c5537e0ba49d53cb25a5393f66ba',
        'hdl-quantulum': '364b3dc7e770c3971d1f41a75c00e6cae76e2e6d',
        'u-boot-xlnx': '1ff0468e9bea29b0a768a7bf52db8d025c521b9a',
    }
    for component, pin in expected_submodules.items():
        assert manifest['submodule_' + component.replace('-', '_')] == pin
    assert manifest['libiio_0_25_source'] == '47a75cbc5e7d24a063b8b54eb531fdba6602b85c'
    assert manifest['libiio_0_25_archive_sha256'] == 'a6676eee9318a38d25e098ce7dce78c3af7df3f8e357f40efdf7f059e8ef2d50'
    for script in ('scripts/build_gain_series_candidate.sh', 'scripts/ci/package_main_firmware.sh'):
        assert 'counter-rx-v1-source.yaml |' in (ROOT / script).read_text()

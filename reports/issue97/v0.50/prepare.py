"""Bind a downloaded trusted build to the exact-byte qualification inputs."""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
FW = BASE.parents[1]
BUILD = '619ecedf23a3fd2103e1237d69db830e26d8959c'
RUN = '34722030151'
VERSION = 'v0.50-plutoplus-spf-counter-rx-v1'
SERIAL = '1040007c4a94000211000b009186843ef2'
root = Path(sys.argv[1]).resolve(strict=True)
bundle = Path(sys.argv[2]).resolve(strict=True)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
subprocess.run(['sha256sum', '--check', 'SHA256SUMS'], cwd=root, check=True)
subprocess.run(['sha256sum', '--check', 'PAYLOAD_SHA256SUMS'], cwd=root, check=True)
source = root / 'counter-rx-v1-source.yaml'
expected = subprocess.check_output(['git', 'show', f'{BUILD}:manifests/counter-rx-v1-source.yaml'], cwd=FW)
assert source.read_bytes() == expected
values = dict(line.split(': ', 1) for line in source.read_text().splitlines() if ': ' in line and not line.startswith('#'))
stem = 'plutoplus-spf-counter-rx-v1-' + BUILD[:12]
provenance = (root / (stem + '-provenance.txt')).read_text()
assert f'firmware_source={BUILD}\n' in provenance
assert f'github_run_id={RUN}\n' in provenance
assert 'github_run_attempt=1\n' in provenance
verdict = json.loads((root / 'integrated-release-verdict.json').read_text())
assert verdict['verdict'] == 'PASS' and verdict['firmware_release_eligible'] is True
assert verdict['source_commit'] == BUILD and verdict['source_manifest_sha256'] == sha(source)
versions = dict(line.split(maxsplit=1) for line in (root / 'packed-VERSIONS.txt').read_text().splitlines())
assert versions['device-fw'] == VERSION
for name in ('hdl', 'buildroot', 'linux', 'u-boot-xlnx'):
    assert versions[name] == values['versions_' + name.replace('-', '_')]
dfu, frm = root / (stem + '-pluto.dfu'), root / (stem + '-pluto.frm')
fit = dfu.read_bytes()[:-16]
assert frm.read_bytes() == fit + hashlib.md5(fit).hexdigest().encode() + b'\n'
subprocess.run(['dfu-suffix', '-c', str(dfu)], check=True)
manifest = {
    'firmware': VERSION, 'serial': SERIAL, 'fit_sha256': hashlib.sha256(fit).hexdigest(),
    'fit_size': len(fit), 'asset_sha256': sha(dfu), 'asset_path': str(dfu),
    'ci_run_id': int(RUN), 'ci_run_attempt': 1,
    'sources': {'firmware_base': BUILD, 'linux': values['submodule_linux'], 'libiio': values['libiio_0_25_source']},
}
(BASE / 'build/counter-rx-v1.json').write_text(json.dumps(manifest, indent=2) + '\n')
release = values | {
    'schema': 'plutosdr-fw.build-manifest', 'release_state': 'candidate',
    'release_tag': VERSION, 'release_url': f'https://github.com/misko/plutosdr-fw/releases/tag/{VERSION}',
    'device_fw': VERSION, 'firmware_source': BUILD, 'firmware_ref': f'refs/tags/{VERSION}',
    'asset_name': dfu.name, 'image_url': f'https://github.com/misko/plutosdr-fw/releases/download/{VERSION}/{dfu.name}',
    'image_sha256': sha(dfu), 'image_size': dfu.stat().st_size,
    'fit_body_sha256': manifest['fit_sha256'], 'fit_body_size': len(fit),
    'frm_asset_name': frm.name, 'frm_sha256': sha(frm), 'frm_size': frm.stat().st_size,
    'bundle_asset_name': bundle.name, 'bundle_sha256': sha(bundle), 'bundle_size': bundle.stat().st_size,
    'source_manifest_name': source.name, 'source_manifest_sha256': sha(source),
    'ci_run_id': RUN, 'ci_run_attempt': 1,
    'fpga_bitstream_sha256': sha(root / 'packed-fpga.bit'),
    'rootfs_sha256': sha(root / 'packed-rootfs.cpio.gz'),
    'xsa_sha256': sha(root / (stem + '-system_top.xsa')),
    'fpga_bitstream_md5': hashlib.md5((root / 'packed-fpga.bit').read_bytes()).hexdigest(),
    'ramdisk_md5': hashlib.md5((root / 'packed-rootfs.cpio.gz').read_bytes()).hexdigest(),
    'fit_description': re.search(r'^FIT description: (.+)$', (root / 'fit-layout.txt').read_text(), re.M)[1],
    'integrated_route_verdict': 'PASS', 'hardware_qualified': 'false', 'persistent_qualified': 'false',
    'qualification_serial': SERIAL,
}
(BASE / 'build/counter-rx-v1.yaml').write_text(''.join(f'{key}: {value}\n' for key, value in release.items()))
print(json.dumps(manifest, indent=2))

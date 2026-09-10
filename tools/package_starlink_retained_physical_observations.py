#!/usr/bin/env python3
"""Collect fixed parent-owned diagnostic runs; no vendor invocation or signoff."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile

from package_starlink_retained_frame_actual import encoded, inventory, receipt


def fixed_inventory(label, root):
    if label.startswith('prepared_'):
        return inventory(root)
    # Parent pytest trees intentionally contain symlink admission controls and
    # pytest current aliases. They are not vendor inputs or raw run products.
    files = {p.name: receipt(p) for p in root.iterdir() if p.is_file() and not p.is_symlink()}
    files.update({label + '/' + name: value for name, value in inventory(root / label).items()})
    return files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    output = parser.parse_args().output
    recovery = Path('/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz')
    if (not output.is_absolute() or output.exists() or output.parent != recovery
            or any(p.is_symlink() for p in (output, *output.parents))):
        raise ValueError('new direct recovery child required')
    roots = {
        'synthesis': recovery / 'retained-synthesis-parent.JqxbVb4y',
        'route': recovery / 'retained-route-parent.I7WoLBxe',
        'prepared_v1': recovery / 'retained-output-synthesis-prepared-v1',
        'prepared_v2': recovery / 'retained-output-synthesis-prepared-v2',
    }
    before = {name: fixed_inventory(name, root) for name, root in roots.items()}
    synth = roots['synthesis'] / 'synthesis'
    route = roots['route'] / 'route'
    expected = {
        synth / 'retained_output_synth.dcp': 'd0a5e0c70d960ab6cf5c9b616610df88c2599ed73932f4fc9c8415c10f4ff840',
        route / 'retained_output_routed.dcp': 'f93d0280e5ace9756fe99e1b118b8e12b57dd1b4b45bd14820aa70a1ad209cc8',
        roots['prepared_v2'] / 'SHA256SUMS': '4a0bbd1b07ea94c51e5b001dbbd7c48b601d1abd8659253a318e3d3f6d357ecb',
        route / 'probe.tcl': '034d1eaa197757b762644acd0cad9dc267338ae23fd5d757290c8485d0f1ac9a',
    }
    for path, digest in expected.items():
        assert receipt(path)['sha256'] == digest
    for line in (roots['prepared_v2'] / 'SHA256SUMS').read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        assert receipt(roots['prepared_v2'] / name)['sha256'] == digest
    manifest = json.loads((synth / 'inputs/manifest.json').read_text())
    for name, value in manifest['files'].items():
        assert receipt(synth / 'inputs' / name) == value
        assert receipt(roots['prepared_v2'] / 'qualified' / name) == value
    for name in ('synthesis', 'route'):
        execution = json.loads((roots[name] / 'execution.json').read_text())
        assert execution['vendor_exit'] == 0 and execution['timed_out'] is False
    assert (synth / 'generated_ip_before.txt').read_bytes() == (synth / 'generated_ip_after.txt').read_bytes()
    ip_hash, ip_name = (synth / 'generated_ip_before.txt').read_text().strip().split(maxsplit=1)
    assert receipt(Path(ip_name))['sha256'] == ip_hash
    payload = {}
    for label, root in roots.items():
        for name in before[label]:
            path = root / name
            # Complete preparation, all owner receipts and final products. The
            # complete generated project/pytest inventories remain in place.
            if label.startswith('prepared_') or len(Path(name).parts) == 1 or (
                    len(Path(name).parts) == 2 and Path(name).parts[0] == label):
                payload[label + '/' + name] = path.read_bytes()
    payload['generated_ip/synthesis_wrapper.vhd'] = Path(ip_name).read_bytes()
    payload['collector.py'] = Path(__file__).read_bytes()
    payload['collector_dependency.py'] = Path(__file__).with_name('package_starlink_retained_frame_actual.py').read_bytes()
    payload['full_raw_inventories.json'] = encoded({
        label: {'root': str(root), 'files': before[label]} for label, root in roots.items()})
    files = {name: {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
             for name, data in payload.items()}
    payload['receipt.json'] = encoded({'files': files, 'timing_pass': False,
        'cdc_qualified': False, 'deployment_eligible': False,
        'vendor_execution_owner': 'parent', 'collector_invokes_no_vendor': True})
    output.mkdir()
    archive = output / 'retained-physical-observations-v1.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for name, data in sorted(payload.items()):
            member = tarfile.TarInfo(name)
            member.size = len(data); member.mode = 0o644; member.mtime = 0
            tar.addfile(member, io.BytesIO(data))
    assert before == {name: fixed_inventory(name, root) for name, root in roots.items()}
    with tarfile.open(archive) as tar:
        assert len(tar.getmembers()) == len(payload)
        for member in tar:
            assert member.isfile() and not Path(member.name).is_absolute() and '..' not in Path(member.name).parts
            assert tar.extractfile(member).read() == payload[member.name]
    result = {'archive': receipt(archive), 'members': len(payload), 'file_receipts': len(files),
              'raw_before_after_equal': True, 'raw_roots': {
                  label: {'files': len(items), 'bytes': sum(r['bytes'] for r in items.values())}
                  for label, items in before.items()}}
    (output / 'package-receipt.json').write_bytes(encoded(result))
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Fixed offline evidence collector; excludes only replayable compiled VVP payloads."""
import hashlib
import io
import json
from pathlib import Path
import tarfile

from package_starlink_retained_frame_actual import encoded, receipt

RECOVERY = Path('/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz')
ROOT = Path(__file__).resolve().parents[1]
ROOTS = {
    'prelaunch': RECOVERY/'retained-summary-actual-prelaunch-v1',
    'owner67': RECOVERY/'retained-summary-actual-first.jtRe2yOy',
    'graph_first_rejected': RECOVERY/'retained-summary-graph-island.bsIkvPOd',
    'graph_v2_failed': RECOVERY/'retained-summary-graph-island-v2.dFxs8QaF',
    'graph_v3_failed': RECOVERY/'retained-summary-graph-island-v3.XqFnNINy',
    'graph_v4_superseded': RECOVERY/'retained-summary-graph-island-v4.hSeDAVGb',
    'graph_v5': RECOVERY/'retained-summary-graph-island-v5.cwe7eS6U',
    'parent_graph': RECOVERY/'retained-summary-graph-parent.Y4nrivfy',
}


def main():
    output = RECOVERY/'retained-summary-actual-package-v1'
    if output.exists(): raise ValueError('no overwrite')
    selected, full, aliases = {}, {}, {}
    for label, root in ROOTS.items():
        if not root.is_dir(): raise ValueError('missing fixed evidence root')
        for path in sorted(root.rglob('*')):
            name = label+'/'+path.relative_to(root).as_posix()
            if path.is_symlink(): aliases[name] = str(path.readlink()); continue
            if path.is_file():
                full[name] = receipt(path)
                if path.suffix != '.vvp': selected[name] = path
    manifest = json.loads((ROOTS['prelaunch']/'manifest.json').read_text())
    assert receipt(ROOTS['prelaunch']/'manifest.json')['sha256'] == 'b5d112562b7db31164dc4a6ff92404de8e7d7d5d96b1c1b23e1a7dbac9d2c368'
    before = manifest['sources']
    assert len(before) == 116
    for name, pin in before.items(): assert receipt(ROOT/name) == pin
    payload = {name: path.read_bytes() for name, path in selected.items()}
    payload['report.md'] = (ROOT/'docs/starlink-retained-summary-actual-preparation-20260910.md').read_bytes()
    payload['collector.py'] = Path(__file__).read_bytes()
    payload['full_raw_inventory.json'] = encoded({'files': full, 'excluded_symlink_aliases': aliases,
        'excluded_regular_payload': '*.vvp only; source/bench/compile/simulation logs retained',
        'source116_live_before_after_equal': True, 'graph_v4_status': 'superseded wire-array cut; not complete graph qualification'})
    files = {n: {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)} for n, data in payload.items()}
    payload['receipt.json'] = encoded({'files': files, 'offline_only': True, 'vendor_executed': False})
    output.mkdir(); archive = output/'retained-summary-actual-preparation-v1.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for name, data in sorted(payload.items()):
            member = tarfile.TarInfo(name); member.size = len(data); member.mode = 0o644; member.mtime = 0
            tar.addfile(member, io.BytesIO(data))
    for name, path in selected.items(): assert receipt(path) == full[name]
    for name, pin in before.items(): assert receipt(ROOT/name) == pin
    with tarfile.open(archive) as tar:
        assert len(tar.getmembers()) == len(payload)
        for member in tar:
            assert member.isfile() and not Path(member.name).is_absolute() and '..' not in Path(member.name).parts
            assert tar.extractfile(member).read() == payload[member.name]
    result = {'archive': receipt(archive), 'members': len(payload), 'file_receipts': len(files),
              'raw_regular_files': len(full), 'excluded_symlink_aliases': len(aliases),
              'selected_unchanged': True, 'source116_unchanged': True}
    (output/'package-receipt.json').write_bytes(encoded(result)); print(json.dumps(result))


if __name__ == '__main__': main()

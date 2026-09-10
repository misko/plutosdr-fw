#!/usr/bin/env python3
"""Package existing offline evidence only; never tests, vendor tools or source edits."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile


ROOT = Path(__file__).resolve().parents[1]
RECOVERY = Path('/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz')
INPUTS = {
    'original_bundle': RECOVERY / 'retained-output-actual-prelaunch-v1',
    'corrected_bundle': RECOVERY / 'retained-output-actual-prelaunch-language-v2',
    'draft_failure': RECOVERY / 'retained-actual-gate.dwywUQMK',
    'final138': RECOVERY / 'retained-actual-final.2VAeyjCJ',
    'language31': RECOVERY / 'retained-actual-language-tests.7tqwIaNj',
    'earlier_attempts': RECOVERY / 'retained-actual-preparation-v1',
}
BUNDLE_HASHES = {
    'original_bundle': 'e524c0ba1b3f4ac0135d58a891ee3dc4b7fbe37b338f4797032159072b8311fc',
    'corrected_bundle': '3a0eb7872722b65764178c813ec96946e61ce0ac226c0202ea0a70d24e559eeb',
}


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def receipt(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return {'sha256': digest.hexdigest(), 'bytes': path.stat().st_size}


def inventory(root):
    files, links = {}, {}
    for folder, dirs, names in os.walk(root, followlinks=False):
        for name in dirs + names:
            path = Path(folder) / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                links[relative] = os.readlink(path)
            elif path.is_file():
                files[relative] = receipt(path)
    return {'files': dict(sorted(files.items())), 'symlinks_not_archived': dict(sorted(links.items()))}


def selected(label, name):
    if label.endswith('bundle'):
        return True
    path = Path(name)
    if path.suffix in ('.log', '.json', '.xml', '.tcl', '.txt'):
        return True
    if label == 'earlier_attempts':
        return path.parts[0].startswith('source-') or (
            path.parts[0] in ('compile-v1', 'script-v1', 'script-v2') and path.suffix != '.vvp')
    return label == 'final138' and name.startswith('pytest/retained_actual_script0/run/') and path.suffix != '.vvp'


def bundle_verify(label):
    path = INPUTS[label]
    assert receipt(path / 'manifest.json')['sha256'] == BUNDLE_HASHES[label]
    manifest = json.loads((path / 'manifest.json').read_text())
    for name, expected in manifest['files'].items():
        assert receipt(path / name) == expected, (label, name)
    assert len(manifest['sources']) == 71 and len(manifest['files']) == 74
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    output = args.output
    assert output.is_absolute() and '..' not in output.parts
    assert not output.exists() and not any(p.is_symlink() for p in (output, *output.parents))
    assert output.parent.is_dir() and output.parent.is_relative_to(RECOVERY)
    old = bundle_verify('original_bundle')
    new = bundle_verify('corrected_bundle')
    changed = [n for n in old['sources'] if old['sources'][n] != new['sources'][n]]
    assert changed == [
        'hdl/library/starlink_pss_acquisition/retained_output_actual/simulate_retained_output_actual.tcl',
        'tests/test_starlink_retained_output_actual_bundle.py',
    ]
    before = {label: inventory(path) for label, path in INPUTS.items()}
    live_before = {name: receipt(ROOT / name) for name in new['sources']}
    assert live_before == new['sources']
    payload = {}
    for label, data in before.items():
        for name in data['files']:
            if selected(label, name):
                payload[f'evidence/{label}/{name}'] = INPUTS[label] / name
    for name in ('docs/starlink-retained-output-actual-preparation-20260910.md',
                 'tools/package_starlink_retained_actual_preparation.py'):
        payload[name] = ROOT / name
    report = {
        'kind': 'OFFLINE_PREPARATION_ARCHIVE_NOT_VENDOR_RESULT',
        'input_roots': {k: str(v) for k, v in INPUTS.items()},
        'raw_inputs': before,
        'selection': 'Complete bundles; all log/json/xml/tcl/txt receipts; original script evidence; no VVP or redundant mutant CSV payloads. Every omitted regular file remains inventoried in place.',
        'changed_sources': changed,
        'source_before': live_before,
        'bundle_hashes': BUNDLE_HASHES,
        'collector_is_separate_not_part_of_prior_test_cohort': True,
    }
    assert before == {label: inventory(path) for label, path in INPUTS.items()}
    live_after = {name: receipt(ROOT / name) for name in new['sources']}
    assert live_after == live_before
    report.update(raw_inputs_before_after_equal=True, source_after=live_after)
    blobs = {'inventory.json': encoded(report)}
    receipts = {name: receipt(path) for name, path in payload.items()}
    receipts.update({name: {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)} for name, data in blobs.items()})
    blobs['receipt.json'] = encoded({'files': receipts})
    output.mkdir()
    archive = output / 'retained-output-actual-preparation-v1.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for name in sorted(set(payload) | set(blobs)):
            data = blobs[name] if name in blobs else payload[name].read_bytes()
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            tar.addfile(info, io.BytesIO(data))
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        assert len({m.name for m in members}) == len(members) == len(receipts) + 1
        for member in members:
            assert member.isfile() and not member.name.startswith('/') and '..' not in Path(member.name).parts
            if member.name != 'receipt.json':
                data = tar.extractfile(member).read()
                assert receipts[member.name] == {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    result = {'archive': receipt(archive), 'members': len(members), 'regular_file_receipts': len(receipts),
              'raw_regular_files': sum(len(d['files']) for d in before.values()),
              'raw_bytes': sum(f['bytes'] for d in before.values() for f in d['files'].values()),
              'raw_inputs_before_after_equal': True, 'all71_live_sources_before_after_equal': True}
    (output / 'archive.json').write_bytes(encoded(result))
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()

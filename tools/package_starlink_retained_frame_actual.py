#!/usr/bin/env python3
"""Compact terminal evidence package; never invokes simulation or modifies inputs."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def receipt(path):
    return {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size}


def inventory(root):
    files = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('symlink in terminal evidence')
        if path.is_file():
            files[path.relative_to(root).as_posix()] = receipt(path)
    if len(files) > 10000 or sum(r['bytes'] for r in files.values()) > 1_000_000_000:
        raise ValueError('bounded evidence inventory exceeded')
    return files


def main():
    p = argparse.ArgumentParser()
    p.add_argument('actual', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    if not args.actual.is_absolute() or not args.output.is_absolute() or args.output.exists():
        raise ValueError('absolute existing input/new output required')
    for path in (args.actual, args.output):
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            raise ValueError('symlink ancestry')
    actual, output = args.actual, args.output
    run = actual / 'run'
    before = inventory(run)
    manifest = json.loads((run / 'inputs/manifest.json').read_text())
    expected = 'c3936f7e8552d7d377ca1e6fc5ba220d0667b68d00a24e24f524de33e75cbae8'
    assert receipt(run / 'inputs/manifest.json')['sha256'] == expected
    for name, r in manifest['files'].items():
        assert before['inputs/' + name] == r
    execution = json.loads((actual / 'execution.json').read_text())
    assert execution['vendor_exit'] == 0 and execution['timed_out'] is False
    assert execution['original_source_check_exit'] == execution['copied_source_check_exit'] == 0
    assert execution['result_file_exists'] is True
    ip_before = (run / 'generated_ip_before.txt').read_bytes()
    assert ip_before == (run / 'generated_ip_after.txt').read_bytes()
    ip_hash, ip_name = ip_before.decode().strip().split(maxsplit=1)
    assert receipt(Path(ip_name))['sha256'] == ip_hash
    sim = run / 'project/retained_output_actual.sim/sim_1/behav/xsim'
    assert receipt(sim / 'actual_words.csv')['sha256'] == '07321b026a637e5922c56a84a955e58549056337198c952a9d73b1245cb4efaa'
    assert receipt(sim / 'simulate.log')['sha256'] == 'e9a77faa32ace748f606f00753a43da3dd542301c39f44ffa7ad0e9432116e52'
    selected = {f'inputs/{name}': run / 'inputs' / name for name in manifest['files']}
    selected['inputs/manifest.json'] = run / 'inputs/manifest.json'
    for name in ('owner.py', 'command.json', 'execution.json', 'process.json',
                 'parent251-audit.json', 'stdout.log', 'vivado.log', 'vivado.jou',
                 'before.log', 'after.log', 'copied-after.log'):
        selected['owner/' + name] = actual / name
    for path in run.iterdir():
        if path.is_file():
            selected['terminal/' + path.name] = path
    for path in sim.iterdir():
        if path.is_file() and path.suffix in ('.log', '.csv', '.prj', '.sh', '.ini', '.mem'):
            selected['simulation/' + path.name] = path
    selected['generated_ip/synthesis_wrapper.vhd'] = Path(ip_name)
    selected['collector.py'] = Path(__file__).resolve()
    source_before = {name: receipt(path) for name, path in selected.items()}
    output.mkdir(parents=True)
    payload = {name: path.read_bytes() for name, path in selected.items()}
    payload['raw_run_inventory.json'] = encoded({'root': str(run), 'files': before,
        'scope': 'complete raw run retained in place; generated project not duplicated in compact archive'})
    payload['source_receipts.json'] = encoded(source_before)
    members = {name: {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
               for name, data in payload.items()}
    payload['receipt.json'] = encoded({'manifest_sha256': expected, 'files': members,
        'vendor_execution_owned_by_parent': True, 'packaging_invokes_no_vendor': True})
    archive = output / 'retained-frame-actual-v1.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for name, data in sorted(payload.items()):
            info = tarfile.TarInfo(name)
            info.size = len(data);info.mode = 0o644;info.mtime = 0
            tar.addfile(info, io.BytesIO(data))
    assert before == inventory(run)
    assert source_before == {name: receipt(path) for name, path in selected.items()}
    with tarfile.open(archive, 'r:gz') as tar:
        assert len(tar.getmembers()) == len(payload)
        for member in tar:
            assert member.isfile() and not Path(member.name).is_absolute() and '..' not in Path(member.name).parts
            assert tar.extractfile(member).read() == payload[member.name]
    result = {'archive': receipt(archive), 'members': len(payload), 'file_receipts': len(members),
              'raw_run_files': len(before), 'raw_run_bytes': sum(r['bytes'] for r in before.values()),
              'raw_before_after_equal': True, 'selected_before_after_equal': True}
    (output / 'package-receipt.json').write_bytes(encoded(result))
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Archive existing tiny-reproducer receipts, including expected kernel crashes."""
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
RECOVERY = Path('/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz')
INPUTS = {'vendor': RECOVERY/'retained-logger-repro-parent.u30ykGsn',
          'offline': RECOVERY/'retained-logger-offline.KDnjoVLt'}
OUTPUT = RECOVERY/'retained-logger-repro-package-v1'


def receipt(data):
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def main():
    assert not OUTPUT.exists()
    files, links = {}, {}
    for label, root in INPUTS.items():
        for folder, dirs, names in os.walk(root, followlinks=False):
            for name in dirs + names:
                path = Path(folder)/name
                key = label+'/'+path.relative_to(root).as_posix()
                if path.is_symlink():
                    links[key] = os.readlink(path)
                elif path.is_file():
                    files[key] = path
    for name in ('hdl/library/starlink_pss_acquisition/retained_output_actual/logger_repro/tb_retained_logger_repro.sv',
                 'tests/test_starlink_retained_logger_repro.py',
                 'docs/starlink-retained-logger-reproducer-20260910.md',
                 'docs/starlink-retained-logger-reproducer-result-20260910.md',
                 'tools/package_starlink_retained_logger_repro.py'):
        files['source/'+name] = ROOT/name
    before = {n: receipt(p.read_bytes()) for n, p in files.items()}
    results = json.loads((INPUTS['vendor']/'results.json').read_text())
    assert [r['case'] for r in results] == list(range(12))
    for row in results:
        crash = row['case'] in (2, 3, 8, 9)
        assert row['source_unchanged'] and row['kernel_crash'] == crash
        assert row['completed'] == row['exact_two_rows'] == (not crash)
        assert row['simulate']['exit'] == 0 and not row['simulate']['timeout']
        if crash:
            assert row['csv_bytes'] == 131
    meta = json.dumps({'kind': 'ISOLATED_LOGGER_REPRO_NOT_FFT', 'files': before,
                       'symlinks_recorded_not_followed': links,
                       'roots': {k: str(v) for k, v in INPUTS.items()}}, sort_keys=True, indent=2).encode()
    OUTPUT.mkdir()
    archive = OUTPUT/'retained-logger-repro-v1.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for name in sorted(files):
            data = files[name].read_bytes()
            assert receipt(data) == before[name]
            info = tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;info.mtime=0
            tar.addfile(info, io.BytesIO(data))
        info = tarfile.TarInfo('receipt.json');info.size=len(meta);info.mode=0o644;info.mtime=0
        tar.addfile(info, io.BytesIO(meta))
    assert before == {n: receipt(p.read_bytes()) for n, p in files.items()}
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        assert len(members) == len({m.name for m in members}) == len(files)+1
        for member in members:
            assert member.isfile() and not member.name.startswith('/') and '..' not in Path(member.name).parts
            if member.name != 'receipt.json':
                assert receipt(tar.extractfile(member).read()) == before[member.name]
    output = {'archive': receipt(archive.read_bytes()), 'members': len(files)+1,
              'receipts': len(files), 'sources_before_after_equal': True}
    (OUTPUT/'archive.json').write_text(json.dumps(output, sort_keys=True, indent=2)+'\n')
    print(json.dumps(output, sort_keys=True))


if __name__ == '__main__':
    main()

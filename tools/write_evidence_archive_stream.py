"""Exclusive-create evidence archive with linear sequential read-back verification."""
import io
import json
from pathlib import Path, PurePosixPath
import tarfile
from verify_evidence_archive_stream import digest_file, verify


def write_verified_archive(output, sources):
    output = Path(output)
    receipt = output.with_suffix('.json')
    if output.exists() or receipt.exists():
        raise ValueError('no archive or receipt overwrite')
    inventory = {}
    for name, source in sources.items():
        source = Path(source)
        if not name or name == 'manifest.json' or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts:
            raise ValueError('unsafe archive member')
        if source.is_symlink() or not source.is_file():
            raise ValueError('regular source file required')
        inventory[name] = dict(bytes=source.stat().st_size, sha256=digest_file(source))
    payload = (json.dumps(inventory, sort_keys=True, indent=2) + '\n').encode()
    with output.open('xb') as destination:
        with tarfile.open(fileobj=destination, mode='w:gz') as archive:
            header = tarfile.TarInfo('manifest.json')
            header.size = len(payload)
            archive.addfile(header, io.BytesIO(payload))
            for name in sorted(sources):
                archive.add(sources[name], arcname=name, recursive=False)
    result = verify(output)
    for name, source in sources.items():
        source = Path(source)
        if source.is_symlink() or not source.is_file() or source.stat().st_size != inventory[name]['bytes'] or digest_file(source) != inventory[name]['sha256']:
            raise ValueError('source changed during archive creation')
    result['writer_sha256'] = digest_file(Path(__file__).resolve())
    result['sources_unchanged'] = True
    with receipt.open('x') as destination:
        destination.write(json.dumps(result, indent=2) + '\n')
    return result

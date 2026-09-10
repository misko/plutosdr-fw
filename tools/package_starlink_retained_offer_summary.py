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
    'owner_first_failed': RECOVERY/'retained-offer-first.SUbHFlw8',
    'owner51': RECOVERY/'retained-offer-second.RtUsyFvh',
    'parent51': RECOVERY/'retained-summary-parent.lSiN2UN2',
    'parent6': RECOVERY/'retained-summary-smoke-parent.wO6w9uMv',
    'parent_real_premise': RECOVERY/'retained-real-premise-parent.xigrZuV8',
    'parent_abstract_premise': RECOVERY/'offer-premise-parent.Qo3DFUXN',
}


def main():
    output = RECOVERY/'retained-offer-summary-package-v1'
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
    before = json.loads((ROOTS['parent51']/'sources-before.json').read_text())
    after = json.loads((ROOTS['parent51']/'sources-after.json').read_text())
    assert before == after and len(before) == 50
    for name, pin in before.items(): assert receipt(Path(name))['sha256'] == pin
    payload = {name: path.read_bytes() for name, path in selected.items()}
    # Preserve exact first-attempt helper/test bytes by a pinned strict prefix
    # inverse; these hashes were recorded before fixing its missing dependency.
    for name, cut, pin in [
        ('tests/starlink_oracle/retained_offer_summary_candidate.py', 'def common_algebra_bench',
         '466ba97fc741f1877a0398ee9c7e62fec43a2a844d43546b6891a3ade37cd6e5'),
        ('tests/test_starlink_retained_offer_summary.py', 'def test_common_literal_roots_and_four_state_partition',
         '966a3d8b72f1fcb52329c8f60c604ccab2659e02a7f043a3452d86ce076bec84'),
    ]:
        text = (ROOT/name).read_text().split(cut)[0].rstrip('\n')+'\n'
        if '/test_' in name:
            token = "        old.BASELINE / 'starlink_pss_block_mailbox.v',\n"
            assert text.count(token) == 1
            text = text.replace(token, '', 1)
        assert hashlib.sha256(text.encode()).hexdigest() == pin
        payload['first_attempt_source/'+name] = text.encode()
    payload['report.md'] = (ROOT/'docs/starlink-retained-offer-summary-offline-20260910.md').read_bytes()
    payload['collector.py'] = Path(__file__).read_bytes()
    payload['full_raw_inventory.json'] = encoded({'files': full, 'excluded_symlink_aliases': aliases,
        'excluded_regular_payload': '*.vvp only; source/bench/compile/simulation logs retained',
        'parent50_live_before_after_equal': True, 'original_first_attempt': '32 PASS, 2 missing-mailbox compile errors'})
    files = {n: {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)} for n, data in payload.items()}
    payload['receipt.json'] = encoded({'files': files, 'offline_only': True, 'vendor_executed': False})
    output.mkdir(); archive = output/'retained-offer-summary-v1.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for name, data in sorted(payload.items()):
            member = tarfile.TarInfo(name); member.size = len(data); member.mode = 0o644; member.mtime = 0
            tar.addfile(member, io.BytesIO(data))
    for name, path in selected.items(): assert receipt(path) == full[name]
    for name, pin in before.items(): assert receipt(Path(name))['sha256'] == pin
    with tarfile.open(archive) as tar:
        assert len(tar.getmembers()) == len(payload)
        for member in tar:
            assert member.isfile() and not Path(member.name).is_absolute() and '..' not in Path(member.name).parts
            assert tar.extractfile(member).read() == payload[member.name]
    result = {'archive': receipt(archive), 'members': len(payload), 'file_receipts': len(files),
              'raw_regular_files': len(full), 'excluded_symlink_aliases': len(aliases),
              'selected_unchanged': True, 'parent50_sources_unchanged': True}
    (output/'package-receipt.json').write_bytes(encoded(result)); print(json.dumps(result))


if __name__ == '__main__': main()

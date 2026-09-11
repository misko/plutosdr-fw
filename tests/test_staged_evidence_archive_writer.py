"""Shared evidence writer preserves byte identity and refuses unsafe members."""
import hashlib
import json
from pathlib import Path
import sys
import tarfile

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from package_staged_fft_evidence import write_verified_archive


def test_round_trip_and_no_overwrite(tmp_path):
    source=tmp_path/'source';source.write_bytes(bytes(range(256)))
    output=tmp_path/'evidence.tgz'
    receipt=write_verified_archive(output,{'data/source':source})
    assert receipt['all_members_verified'] and receipt['members']==2
    assert receipt['sha256']==hashlib.sha256(output.read_bytes()).hexdigest()
    assert json.loads(output.with_suffix('.json').read_text())==receipt
    with tarfile.open(output) as archive:
        assert archive.extractfile('data/source').read()==source.read_bytes()
    with pytest.raises(ValueError,match='overwrite'):write_verified_archive(output,{'source':source})


@pytest.mark.parametrize('name',['/absolute','../escape','a/../../escape','manifest.json'])
def test_unsafe_names_rejected(tmp_path,name):
    source=tmp_path/'source';source.write_text('evidence')
    with pytest.raises(ValueError,match='invalid archive member'):
        write_verified_archive(tmp_path/'evidence.tgz',{name:source})


def test_symlink_and_missing_source_rejected(tmp_path):
    source=tmp_path/'source';source.write_text('evidence')
    link=tmp_path/'link';link.symlink_to(source)
    for path in [link,tmp_path/'missing']:
        with pytest.raises(ValueError,match='invalid archive member'):
            write_verified_archive(tmp_path/'evidence.tgz',{'source':path})


def test_existing_receipt_rejected_before_archive_write(tmp_path):
    output=tmp_path/'evidence.tgz';output.with_suffix('.json').write_text('existing')
    with pytest.raises(ValueError,match='overwrite'):write_verified_archive(output,{})
    assert not output.exists()

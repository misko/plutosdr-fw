import hashlib
import io
import json
import sys
from pathlib import Path
import tarfile
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from verify_evidence_archive_stream import verify

@pytest.mark.parametrize('mutation',['none','duplicate','missing','extra','digest','link','unsafe'])
def test_stream_inventory_and_payload(tmp_path,mutation):
    path=tmp_path/'archive.tgz';data=b'checked evidence'
    name='../bad' if mutation=='unsafe' else 'payload'
    manifest={name:{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}}
    if mutation=='digest':manifest[name]['sha256']='0'*64
    with tarfile.open(path,'w:gz') as archive:
        def put(name,data):
            member=tarfile.TarInfo(name);member.size=len(data)
            archive.addfile(member,io.BytesIO(data))
        put('manifest.json',json.dumps(manifest).encode())
        if mutation=='link':
            member=tarfile.TarInfo(name);member.type=tarfile.SYMTYPE;member.linkname='target';archive.addfile(member)
        elif mutation!='missing':put(name,data)
        if mutation=='duplicate':put(name,data)
        if mutation=='extra':put('extra',data)
    if mutation=='none':
        result=verify(path);assert result['members']==2 and result['all_members_verified']
    else:
        with pytest.raises(ValueError):verify(path)

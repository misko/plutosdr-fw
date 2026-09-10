#!/usr/bin/env python3
"""Fixed offline receipts/source collector; never invokes simulation."""
import hashlib
import io
import json
from pathlib import Path
import tarfile

from package_starlink_retained_frame_actual import encoded, receipt

RECOVERY = Path('/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz')
ROOTS = {
    'owner26': RECOVERY/'retained-private-offer-tests-v1.xZ6zD8rp',
    'owner32': RECOVERY/'retained-private-offer-tests-v2.07be9IZT',
    'parent32': RECOVERY/'retained-private-parent.PmtrTqnC',
}


def main():
    output=RECOVERY/'retained-private-offer-package-v1'
    if output.exists(): raise ValueError('no overwrite')
    selected={};full={};aliases={}
    for label,root in ROOTS.items():
        for path in sorted(root.rglob('*')):
            name=label+'/'+path.relative_to(root).as_posix()
            if path.is_symlink(): aliases[name]=str(path.readlink());continue
            if path.is_file():
                full[name]=receipt(path)
                if path.name!='sim.vvp': selected[name]=path
    pins=json.loads((ROOTS['parent32']/'source-pins.json').read_text())
    payload={name:path.read_bytes() for name,path in selected.items()}
    payload['full_raw_inventory.json']=encoded({'files':full,'excluded_symlink_aliases':aliases,
        'excluded_regular_payload':'sim.vvp only; complete sources/benches/compile and simulation logs retained',
        'parent_source_pins':pins})
    payload['collector.py']=Path(__file__).read_bytes()
    files={name:{'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)} for name,data in payload.items()}
    payload['receipt.json']=encoded({'files':files,'offline_only':True,'actual_fft_executed':False})
    output.mkdir();archive=output/'retained-private-offer-v1.tar.gz'
    with tarfile.open(archive,'w:gz') as tar:
        for name,data in sorted(payload.items()):
            member=tarfile.TarInfo(name);member.size=len(data);member.mode=0o644;member.mtime=0
            tar.addfile(member,io.BytesIO(data))
    for name,path in selected.items():assert receipt(path)==full[name]
    with tarfile.open(archive) as tar:
        assert len(tar.getmembers())==len(payload)
        for member in tar:
            assert member.isfile() and not Path(member.name).is_absolute() and '..' not in Path(member.name).parts
            assert tar.extractfile(member).read()==payload[member.name]
    result={'archive':receipt(archive),'members':len(payload),'file_receipts':len(files),
        'raw_regular_files':len(full),'excluded_symlink_aliases':len(aliases),'selected_unchanged':True}
    (output/'package-receipt.json').write_bytes(encoded(result));print(json.dumps(result))


if __name__=='__main__':main()

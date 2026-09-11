"""Read-back verified packet for the isolated product validation components."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from package_staged_fft_evidence import write_verified_archive
from staged_fft_experiment import ROOT, require, sha


def package(artifacts,output):
    require(artifacts.is_absolute() and artifacts.is_dir(),'absolute test root required')
    tests=ET.parse(artifacts/'component-v4.xml').getroot().findall('testsuite')
    require(sum(int(t.attrib['tests']) for t in tests)==15 and
            all(int(t.attrib[k])==0 for t in tests for k in ['failures','errors','skipped']),
            'complete successful final component suite required')
    rtl=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
    parent=Path('/dev/shm/starlink-forward-receipt.7z0zKX/prepared-v1')
    require(sha(parent/'SHA256SUMS')=='0d222aa4968145b0026ac4e8c9288c9b1ad5fc9f8f9b1bdd07a6d3eda4f1af8b','parent inventory pin')
    sources={}
    def add(name,path):
        require(name not in sources,'duplicate member');sources[name]=path
    for version in range(1,5):
        name=f'component-v{version}'
        add('tests/'+name+'.xml',artifacts/(name+'.xml'))
        for path in sorted((artifacts/name).rglob('*')):
            if not path.is_symlink() and path.is_file() and path.suffix in {'.sv','.v','.log','.xml'}:
                add('tests/'+name+'/'+str(path.relative_to(artifacts/name)),path)
    for name in ['starlink_pss_product_identity_stage.v','starlink_pss_product_mailbox_staged_identity.v','tb_product_identity_stage.sv']:
        add('current/rtl/'+name,rtl/name)
    add('current/tests/test_starlink_product_identity_stage.py',ROOT/'tests/test_starlink_product_identity_stage.py')
    add('current/docs/components.md',ROOT/'docs/starlink-product-validation-components-20260911.md')
    for name in ['package_product_identity_components.py','package_staged_fft_evidence.py']:
        add('current/tools/'+name,ROOT/'tools'/name)
    for path in sorted(parent.iterdir()):
        if path.is_file():add('reference/prepared-parent/'+path.name,path)
    mailbox=ROOT.parent/'retained-summary-actual-prelaunch-v1/source_snapshot/hdl/library/starlink_pss_acquisition/retained_output/starlink_pss_mailbox_owner_view.v'
    require(sha(mailbox)=='de060a7930be1d65cc91903da447e51ead3efad4ebed4b61e4f257e45d76d2d6','original mailbox pin')
    add('reference/original-mailbox.v',mailbox)
    return write_verified_archive(output,sources)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('artifacts',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();print(json.dumps(package(args.artifacts,args.output),indent=2))

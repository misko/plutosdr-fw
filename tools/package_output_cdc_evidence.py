"""Preserve the CDC contract and its explicitly unqualified physical assessment."""
import argparse
import json
from pathlib import Path

from audit_output_metadata_cdc import assess
from package_staged_fft_evidence import write_verified_archive
from staged_fft_experiment import ROOT, require, sha


def package(artifacts,output):
    require(artifacts.is_absolute() and artifacts.is_dir(),'absolute artifacts required')
    result=assess(artifacts)
    require(result==json.loads((artifacts/'cdc_assessment.json').read_text()),'fresh assessment differs')
    require(result['constraint_change_authorized'] is False and result['deployment_eligible'] is False,'diagnostic only')
    sources={}
    def add(name,path):
        require(name not in sources,'duplicate member');sources[name]=path
    def tree(prefix,folder,suffixes):
        require(folder.is_dir(),'missing evidence directory '+str(folder))
        for path in sorted(folder.rglob('*')):
            if any(part=='.Xil' for part in path.parts):continue
            if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent!=folder.parent):continue
            if path.is_file() and path.suffix in suffixes:add(prefix+'/'+str(path.relative_to(folder)),path)
    tree('inspection',artifacts/'inspection-v1',{'.log','.json','.txt','.tsv','.rpt'})
    tree('fanout',artifacts/'fanout-v1',{'.txt','.rpt'})
    add('fanout/vivado.log',artifacts/'fanout-v1-vivado.log')
    for name in ['contract-v1','audit-v1']:
        tree('tests/'+name,artifacts/name,{'.v','.sv','.py','.log','.json','.txt','.xml','.tsv','.rpt'})
        add('tests/'+name+'.xml',artifacts/(name+'.xml'))
    add('assessment.json',artifacts/'cdc_assessment.json')
    for name in ['inspect_output_metadata_cdc.py','inspect_output_metadata_cdc.tcl',
                 'inspect_metadata_control_fanout.tcl','audit_output_metadata_cdc.py',
                 'package_output_cdc_evidence.py','package_staged_fft_evidence.py','staged_fft_experiment.py']:
        add('current/tools/'+name,ROOT/'tools'/name)
    for name in ['test_starlink_output_metadata_cdc.py','test_starlink_output_cdc_audit.py','test_staged_evidence_archive_writer.py']:
        add('current/tests/'+name,ROOT/'tests'/name)
    add('current/tests/tb_output_metadata_cdc.sv',ROOT/'tests/fixtures/tb_output_metadata_cdc.sv')
    add('current/docs/contract.md',ROOT/'docs/starlink-output-cdc-contract-20260911.md')
    prepared=Path('/dev/shm/starlink-output-metadata.MB5fY8/prepared-v3')
    require(sha(prepared/'SHA256SUMS')=='dc97c80ce1999e9a18053524c3dcd325d029705560c2425aef2e0fe05f20d1b7','runtime parent pin')
    for name in ['SHA256SUMS','profile.tcl','starlink_pss_fft_staged_output_impl.v',
                 'starlink_pss_mailbox_split_metadata_view.v','starlink_pss_retained_epoch_barrier.v']:
        add('reference/parent/'+name,prepared/name)
    runtime_names=(prepared/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    require(len(runtime_names)==22,'complete unchanged runtime inventory')
    for name in runtime_names:
        current=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'/name
        if current.exists():require(current.read_bytes()==(prepared/name).read_bytes(),'runtime changed '+name)
    receipt=Path('/home/mouse9911/gits/plutosdr-fw-starlink-rx-only/reports/experiments/20260911-staged-outputmetadata-evidence.json')
    require(json.loads(receipt.read_text())['sha256']=='7b3909f3b4737d226741d9a5675eec6c6114ec81ec464d31c6dd91d993a8c6f4','parent archive dependency')
    add('reference/parent-archive-receipt.json',receipt)
    return write_verified_archive(output,sources)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('artifacts',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();print(json.dumps(package(args.artifacts,args.output),indent=2))

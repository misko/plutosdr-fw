"""Archive the integrated experiment, including failing timing without promotion."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from staged_fft_experiment import require, sha
from route_product_current_fence import evidence
from package_staged_fft_evidence import write_verified_archive
import buffered_forward_experiment as main

def tests(path,count):
    root=ET.parse(path).getroot()
    cases=list(root.iter('testcase'))
    require(len(cases)==count and not list(root.iter('failure')) and not list(root.iter('error')) and not list(root.iter('skipped')),'complete passing tests '+str(path))
    return count

def record(root):
    checked=evidence(root/'actual-v1',root/'synth-v1',root/'aux-actual-v1')
    total=tests(root/'regression-v1.xml',1324)+tests(root/'route-tests-v1.xml',23)
    route=json.loads((root/'route-v1/audit.json').read_text())
    outcome=json.loads((root/'route-v1/outcome.json').read_text())
    require(outcome.get('returncode')==0 and outcome.get('sources_unchanged') is True and 'error' not in outcome,'terminal route')
    require(sha(root/'route-v1/route/retained_output_routed.dcp')==outcome['routed_dcp_sha'],'routed DCP pin')
    require(route['source_and_checkpoint_verified'] is True and route['routing_errors']==0,'routed observations')
    require(route['full_receiver_or_physical_signoff'] is False and route['deployment_eligible'] is False,'no deployment promotion')
    assessment={'source_evidence':checked,'tests':total,'route':route,
                'native_fine_and_inspection_receiver_sources_changed':False,
                'receiver_integrated':False,'radios_accessed':[],
                'deployment_eligible':False,'routed_dcp_sha256':outcome['routed_dcp_sha']}
    destination=root/'assessment.json';require(not destination.exists(),'no assessment overwrite')
    destination.write_text(json.dumps(assessment,indent=2)+'\n')
    sources={};omitted=[]
    def add(name,path):
        require(name not in sources and path.is_file() and not path.is_symlink(),'regular unique archive member '+name)
        sources[name]=path
    add('assessment.json',destination)
    for folder in ['prepared-v1','aux-prepared-v1']:
        for p in sorted((root/folder).iterdir()):
            if p.is_file():add(folder+'/'+p.name,p)
    for folder in ['actual-v1','aux-actual-v1','synth-v1','route-v1']:
        base=root/folder
        for p in sorted(base.iterdir()):
            if p.is_file():add(folder+'/'+p.name,p)
        if folder=='route-v1':
            for p in sorted((base/'route').iterdir()):
                if p.is_file():add(folder+'/route/'+p.name,p)
        if 'actual' in folder:
            sim=base/'project/staged_fft.sim/sim_1/behav/xsim'
            for name in ['simulate.log','buffered_words.csv','xvlog.log','xvhdl.log','elaborate.log']:
                add(folder+'/sim/'+name,sim/name)
            wrapper=base/'project/staged_fft.gen/sources_1/ip/starlink_pss_fft512_bfp18_rt_candidate/synth/starlink_pss_fft512_bfp18_rt_candidate.vhd'
            add(folder+'/generated_fft.vhd',wrapper)
    for folder in ['regression-v1','route-tests-v1']:
        add('tests/'+folder+'.xml',root/(folder+'.xml'))
        for p in sorted((root/folder).rglob('*')):
            if not p.is_file() or p.is_symlink() or any(parent.is_symlink() for parent in p.parents):continue
            relative=str(p.relative_to(root))
            if p.suffix in {'.csv','.dcp'}:
                omitted.append({'source':str(p),'sha256':sha(p),'bytes':p.stat().st_size});continue
            if p.suffix in {'.v','.sv','.svh','.py','.log','.json','.txt','.xml','.tcl','.mem'}:
                add('tests/'+relative,p)
    for pattern in ['tools/*product_current_fence*.py','tests/test_starlink_product_current_fence*.py','docs/starlink-product-current-fence-*.md']:
        for p in sorted(main.ROOT.glob(pattern)):add('source/'+str(p.relative_to(main.ROOT)),p)
    inventory=root/'omitted_regression_payload_inventory.json';require(not inventory.exists(),'no inventory overwrite')
    inventory.write_text(json.dumps({'reason':'Historical regression CSV/DCP payloads are retained locally; current actual numerical streams and route checkpoints are included in full.','omitted':omitted},indent=2)+'\n')
    add(inventory.name,inventory)
    return write_verified_archive(root/'20260911-product-current-fence-evidence.tgz',sources)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path)
    print(json.dumps(record(parser.parse_args().root),indent=2))

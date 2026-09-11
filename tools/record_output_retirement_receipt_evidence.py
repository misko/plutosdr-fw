"""Archive the integrated experiment, including failing timing without promotion."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from staged_fft_experiment import require, sha, verify
from route_output_retirement_receipt import evidence
from package_staged_fft_evidence import write_verified_archive
import buffered_forward_experiment as main

def tests(path,count):
    root=ET.parse(path).getroot()
    cases=list(root.iter('testcase'))
    require(len(cases)==count and not list(root.iter('failure')) and not list(root.iter('error')) and not list(root.iter('skipped')),'complete passing tests '+str(path))
    return count

def record(root):
    checked=evidence(root/'actual-v1',root/'synth-v1',root/'aux-v3')
    total=tests(root/'regression-v4.xml',1866)
    tests(root/'regression-v3.xml',1852)
    tests(root/'regression-v1.xml',1850)
    tests(root/'component-v2.xml',26)
    tests(root/'component-v3.xml',28)
    tests(root/'protocol-v1.xml',14)
    rejected_aux=json.loads((root/'aux-v1/outcome.json').read_text())
    require(rejected_aux.get('passed') is False and 'error' in rejected_aux,'retain rejected recursive campaign')
    require(len(list(ET.parse(root/'regression-v2.xml').getroot().iter('failure')))==1,'retain task-declaration counting failure')
    traces=[]
    for name in ['delay-parent-v2','delay-candidate-v2']:
        result=json.loads((root/name/'outcome.json').read_text())
        require(result.get('passed') is False,'diagnostic intentionally ends at existing rejection')
        verify(Path(result['command'][-3]),result['prepared_sha'])
        log=(root/name/'stdout.log').read_text()
        require('Fatal: auxiliary healthy fault case=0 state=7 guard=01 bank=0' in log,'same rejection boundary')
        traces.append([line for line in log.splitlines() if line.startswith('DELAY_PROBE ')])
    require(len(traces[0])>=3 and traces[0]==traces[1],'parent/candidate rejection traces match')
    require(all(marker in traces[0][-1] for marker in ['ext=1','retained=1','output_control=1','output_request=0 ack=0']),'missing publication is rejected by existing controller')
    route=json.loads((root/'route-v1/audit.json').read_text())
    outcome=json.loads((root/'route-v1/outcome.json').read_text())
    require(outcome.get('returncode')==0 and outcome.get('sources_unchanged') is True and 'error' not in outcome,'terminal route')
    require(sha(root/'route-v1/route/retained_output_routed.dcp')==outcome['routed_dcp_sha'],'routed DCP pin')
    require(route['source_and_checkpoint_verified'] is True and route['routing_errors']==0,'routed observations')
    require(route['full_receiver_or_physical_signoff'] is False and route['deployment_eligible'] is False,'no deployment promotion')
    endpoints=json.loads((root/'endpoints-v1/outcome.json').read_text())
    require(endpoints.get('passed') is True and endpoints.get('sources_unchanged') is True,'actual endpoint observations')
    require(all(sha(Path(p))==value for p,value in endpoints['before'].items()),'endpoint source receipts')
    assessment={'endpoints':endpoints,'source_evidence':checked,'tests':total,'route':route,
                'rejected_auxiliary':rejected_aux,
                'parent_candidate_missing_publication_trace':traces[0],
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
    for folder in ['prepared-v1','aux-prepared-v1','aux-prepared-v2','aux-prepared-v3',
                   'delay-probe-prepared-v1','delay-parent-prepared-v2','delay-candidate-prepared-v2']:
        for p in sorted((root/folder).iterdir()):
            if p.is_file():add(folder+'/'+p.name,p)
    simulation_folders=['actual-v1','aux-v1','aux-v2','aux-v3','delay-probe-v1','delay-parent-v2','delay-candidate-v2']
    for folder in simulation_folders+['synth-v1','route-v1','endpoints-v1']:
        base=root/folder
        for p in sorted(base.iterdir()):
            if p.is_file():add(folder+'/'+p.name,p)
        if folder=='route-v1':
            for p in sorted((base/'route').iterdir()):
                if p.is_file():add(folder+'/route/'+p.name,p)
        if folder=='endpoints-v1':
            for p in sorted((base/'reports').iterdir()):
                if p.is_file():add(folder+'/reports/'+p.name,p)
        if folder in simulation_folders:
            sim=base/'project/staged_fft.sim/sim_1/behav/xsim'
            for name in ['simulate.log','buffered_words.csv','xvlog.log','xvhdl.log','elaborate.log']:
                add(folder+'/sim/'+name,sim/name)
            wrapper=base/'project/staged_fft.gen/sources_1/ip/starlink_pss_fft512_bfp18_rt_candidate/synth/starlink_pss_fft512_bfp18_rt_candidate.vhd'
            add(folder+'/generated_fft.vhd',wrapper)
    for folder in ['regression-v1','regression-v2','regression-v3','regression-v4','component-v1','component-v2','component-v3','protocol-v1']:
        add('tests/'+folder+'.xml',root/(folder+'.xml'))
        for p in sorted((root/folder).rglob('*')):
            if not p.is_file() or p.is_symlink() or any(parent.is_symlink() for parent in p.parents):continue
            relative=str(p.relative_to(root))
            if p.suffix in {'.csv','.dcp'}:
                omitted.append({'source':str(p),'sha256':sha(p),'bytes':p.stat().st_size});continue
            if p.suffix in {'.v','.sv','.svh','.py','.log','.json','.txt','.xml','.tcl','.mem'}:
                add('tests/'+relative,p)
    for pattern in ['tools/*output_retirement_receipt*','tools/output_retirement_delay_probe*.py',
                    'tests/test_starlink_output_retirement_receipt*.py','tests/test_starlink_output_retirement_protocol.py',
                    'docs/starlink-output-retirement-receipt-*.md']:
        for p in sorted(main.ROOT.glob(pattern)):add('source/'+str(p.relative_to(main.ROOT)),p)
    inventory=root/'omitted_regression_payload_inventory.json';require(not inventory.exists(),'no inventory overwrite')
    inventory.write_text(json.dumps({'reason':'Historical regression CSV/DCP payloads are retained locally; current actual numerical streams and route checkpoints are included in full.','omitted':omitted},indent=2)+'\n')
    add(inventory.name,inventory)
    return write_verified_archive(root/'20260911-output-retirement-receipt-evidence.tgz',sources)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path)
    print(json.dumps(record(parser.parse_args().root),indent=2))

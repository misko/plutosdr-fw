"""Retain functional rejection and actual parent reproduction, never promote."""
import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import local_fault_experiment as experiment
import audit_local_fault_v3 as audit
from staged_fft_experiment import sha,verify,require
from package_staged_fft_evidence import write_verified_archive

def record(root):
    main=root/'actual-v1';aux=root/'aux-actual-v1';synth=root/'synth-v1'
    for p in [main,aux,synth]:
        result=json.loads((p/'outcome.json').read_text())
        verify(Path(result['command'][-3]),result['prepared_sha'])
    healthy=json.loads((main/'local_fault_audit_v3.json').read_text())
    require(healthy['passed'] is True and healthy['audit_source_sha256']==sha(Path(audit.__file__)),'healthy audit source')
    require(healthy['numerical']==json.loads(json.dumps(experiment.base.base.main.audit(main))),'fresh actual numerics')
    mainlog=main/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log'
    require(sha(mainlog)==healthy['log_sha256'] and audit.witness(mainlog.read_text())==healthy['local_fault'],'healthy live witness')
    require(sha(main/'local_fault_outcome.json')==healthy['v1_receipt_sha256'],'failed parser provenance')
    failure=json.loads((aux/'outcome.json').read_text())
    require(failure.get('passed') is False and 'error' in failure,'retain failed auxiliary')
    log=(aux/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
    require('Fatal: local fault immediate veto' in log and 'LOCAL_FAULT_BOUNDARY_PASS boundary=0 ' in log and
            'LOCAL_FAULT_BOUNDARY_PASS boundary=1 ' not in log,'exact new boundary failure')
    require(not (root/'route-v1').exists(),'no route before functional acceptance')
    tests=ET.parse(root/'regression-v2.xml').getroot()
    require(len(list(tests.iter('testcase')))==1306 and not any(list(tests.iter(k)) for k in ['failure','error','skipped']),'1306 passing unit/regression tests')
    oldtests=ET.parse(root/'regression-v1.xml').getroot()
    require(len(list(oldtests.iter('failure')))==2,'preserve original parser failures')
    synthesis=json.loads((synth/'outcome.json').read_text())
    require(synthesis['passed'] is True and sha(synth/'staged_output_synth.dcp')==synthesis['dcp_sha256'],'synthesis identity')
    probes={}
    for variant in ['parent','candidate']:
        path=root/f'probe-{variant}-actual-v1';result=json.loads((path/'outcome.json').read_text())
        verify(Path(result['command'][-3]),result['prepared_sha'])
        raw=(path/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
        rows=[line for line in raw.splitlines() if line.startswith('STATUS_PROBE_')]
        require(result['completed'] is True and result['returncode']==0 and rows==result['observations'],'completed actual diagnostic')
        require(len(rows)==5 and rows[0]=='STATUS_PROBE_BEFORE request=0 committed=1 accept=1 position=511 last=1','real final RAM write')
        require(rows[1]=='STATUS_PROBE_CURRENT global=0 guard=0 current=1 external=0 vendor=0 commit=1 accept=1 request=0','inherited missing current veto')
        require(rows[2]==f'STATUS_PROBE_EDGE global={int(variant=="parent")} guard=1 commit=0 request=1 output=0','actual ownership transfer')
        require(re.fullmatch(r'STATUS_PROBE_SETTLED global=1 fault=1 reads=\s*0 releases=\s*0 output=0',rows[3]) is not None,'held-reader quarantine observation')
        probes[variant]=result
    assessment=dict(unit_tests=1306,healthy_actual=healthy,auxiliary_passed=False,failed_boundary=1,
        remaining_new_boundaries_unreached=[2,3,4,5],probes=probes,route_attempted=False,
        physical_signoff=False,deployment_eligible=False,radios_accessed=[],primary_hdl_promoted=False)
    destination=root/'assessment.json';require(not destination.exists(),'no assessment overwrite')
    destination.write_text(json.dumps(assessment,indent=2)+'\n')
    sources={};omitted=[]
    def add(name,path):
        require(name not in sources and path.is_file() and not path.is_symlink(),'regular unique archive member')
        sources[name]=path
    add('assessment.json',destination)
    for folder in ['prepared-v1','aux-prepared-v1','probe-parent-prepared-v1','probe-candidate-prepared-v1',
                   'actual-v1','aux-actual-v1','probe-parent-actual-v1','probe-candidate-actual-v1','synth-v1']:
        base=root/folder
        for p in sorted(base.iterdir()):
            if p.is_file():add(folder+'/'+p.name,p)
        if 'actual' in folder:
            sim=base/'project/staged_fft.sim/sim_1/behav/xsim'
            for name in ['simulate.log','buffered_words.csv','xvlog.log','xvhdl.log','elaborate.log']:add(folder+'/sim/'+name,sim/name)
            wrapper=base/'project/staged_fft.gen/sources_1/ip/starlink_pss_fft512_bfp18_rt_candidate/synth/starlink_pss_fft512_bfp18_rt_candidate.vhd'
            add(folder+'/generated_fft.vhd',wrapper)
    for folder in ['regression-v1','regression-v2','register-tests-v1']:
        add('tests/'+folder+'.xml',root/(folder+'.xml'))
        for p in sorted((root/folder).rglob('*')):
            if not p.is_file() or p.is_symlink() or any(parent.is_symlink() for parent in p.parents):continue
            if p.suffix in {'.csv','.dcp'}:
                omitted.append({'source':str(p),'sha256':sha(p),'bytes':p.stat().st_size});continue
            if p.suffix in {'.v','.sv','.svh','.py','.log','.json','.txt','.xml','.tcl','.mem'}:add('tests/'+str(p.relative_to(root)),p)
    worktree=Path(__file__).resolve().parents[1]
    for pattern in ['tools/*local_fault*.py','tools/probe_product_status_boundary.py','tests/test_starlink_local_fault*.py','docs/starlink-local-fault-*.md']:
        for p in sorted(worktree.glob(pattern)):add('source/'+str(p.relative_to(worktree)),p)
    inventory=root/'omitted_regression_payload_inventory.json';require(not inventory.exists(),'no inventory overwrite')
    inventory.write_text(json.dumps({'reason':'Historical regression CSV/DCP duplicates stay local; all current actual streams and synthesis checkpoint included.','omitted':omitted},indent=2)+'\n')
    add(inventory.name,inventory)
    return write_verified_archive(root/'20260911-local-fault-pipeline-rejection-evidence.tgz',sources)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path)
    print(json.dumps(record(parser.parse_args().root),indent=2))

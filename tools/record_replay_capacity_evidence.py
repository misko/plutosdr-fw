"""Archive three measured buffer variants, including rejected qualifications."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from staged_fft_experiment import require,sha,verify
from replay_local_fault_evidence import evidence
from write_evidence_archive_stream import write_verified_archive

ROOT=Path(__file__).resolve().parents[1]

def passing_xml(path,count):
    tree=ET.parse(path)
    require(len(list(tree.iter('testcase')))==count,'exact test count')
    require(not any(list(tree.iter(x)) for x in ['failure','error','skipped']),'passing test XML')

def pinned_receipt(folder):
    result=json.loads((folder/'outcome.json').read_text())
    require(result.get('returncode')==0 and result.get('sources_unchanged') is True,'terminal source-matched observation')
    require(all(sha(Path(p))==value for p,value in result['before'].items()),'unchanged observation inputs')
    return result

def record(root):
    qualified=evidence(root/'local-sim-v2',root/'local-synth-v2',root/'local-aux-v2')
    passing_xml(root/'regression-v1.xml',2151)
    passing_xml(root/'local-scoped-regression-v1/tests.xml',2181)
    passing_xml(root/'component-v2.xml',44)
    passing_xml(root/'local-component-v2.xml',22)
    passing_xml(root/'local-label-tests-v1.xml',8)
    regression=json.loads((root/'local-scoped-regression-v1/outcome.json').read_text())
    require(regression.get('passed') is True and regression['sources_unchanged'] is True,'scoped regression receipt')
    require(all(sha(Path(p))==value for p,value in regression['test_sources'].items()),'test sources unchanged')
    failed_ring=json.loads((root/'ring-aux-v1/private_status_outcome.json').read_text())
    require(failed_ring['passed'] is False and failed_ring['private_status_error']=="ValueError('private delta exercised')",'preserve ring qualification rejection')
    for folder in ['local-sim-v1','local-aux-v1']:
        rejected=json.loads((root/folder/'product_fence_outcome.json').read_text())
        require(rejected['passed'] is False and 'one local fault witness' in rejected['product_fence_error'],'preserve rejected marker collision')
    broad=ET.parse(root/'local-regression-v1.xml')
    require(len(list(broad.iter('error')))==3,'preserve broad collection errors')
    variants={}
    for label,route,endpoints in [
        ('head_tail','exploratory-route-v1','capacity-endpoints-v2'),
        ('ring','ring-exploratory-route-v1','ring-endpoints-v1'),
        ('local_fault_ring','local-exploratory-route-v2','local-endpoints-v2')]:
        receipt=pinned_receipt(root/route)
        require(receipt['exploratory_only'] is True and receipt['deployment_eligible'] is False,'no exploratory route promotion')
        require(sha(root/route/'route/retained_output_routed.dcp')==receipt['routed_dcp_sha'],'routed checkpoint identity')
        audit=json.loads((root/route/'audit.json').read_text())
        endpoint=pinned_receipt(root/endpoints)
        require(endpoint.get('passed') is True,'actual endpoint observation')
        require(audit['internal_timing_pass'] is False and audit['deployment_eligible'] is False,'retain failing physical gate')
        variants[label]=dict(route=audit,routed_dcp_sha=receipt['routed_dcp_sha'],endpoints=endpoint['endpoint_slack_ns'])
    assessment=dict(qualified_local_fault=qualified,variants=variants,tests=2181,
        test_scope=regression['scope'],complete_repository_suite=False,
        ring_auxiliary_qualified=False,ring_rejection=failed_ring['private_status_error'],
        earlier_local_runs_rejected='terminal marker collided with inherited strict LOCAL_FAULT_PASS parser; v2 changes only marker/helper',
        unqualified_endpoint_probe='capacity-endpoints-v1 inferred top from design_1 and omitted FIFO pins; v2 explicitly requires them',
        receiver_integrated=False,radios_accessed=[],deployment_eligible=False,
        omitted_payloads='Historical regression-generated payloads and Vivado caches/waveforms remain local; archive retains source snapshots, logs, numerical CSV, checkpoints, reports, XML and focused component artifacts.')
    with (root/'capacity-assessment.json').open('x') as output:output.write(json.dumps(assessment,indent=2)+'\n')
    sources={}
    def add(name,path):
        require(name not in sources and path.is_file() and not path.is_symlink(),'unique regular archive member')
        sources[name]=path
    add('capacity-assessment.json',root/'capacity-assessment.json')
    for name in ['regression-v1.xml','component-v1.xml','component-v2.xml','local-component-v1.xml','local-component-v2.xml',
                 'local-label-tests-v1.xml','local-regression-v1.xml']:
        add('tests/'+name,root/name)
    for path in (root/'local-scoped-regression-v1').iterdir():
        if path.is_file():add('tests/local-scoped-regression-v1/'+path.name,path)
    for name in ['component-v1','component-v2','local-component-v1','local-component-v2','local-label-tests-v1']:
        for path in sorted((root/name).rglob('*')):
            if path.is_file() and not path.is_symlink() and not any(p.is_symlink() for p in path.parents) and path.suffix in {'.v','.sv','.log'}:
                add('tests/'+str(path.relative_to(root)),path)
    for name in ['prepared-v1','aux-prepared-v1','smoke-prepared-v1','ring-prepared-v1','ring-smoke-prepared-v1','ring-aux-prepared-v1',
                 'local-prepared-v1','local-aux-prepared-v1','local-prepared-v2','local-aux-prepared-v2']:
        folder=root/name;verify(folder,sha(folder/'SHA256SUMS'))
        for path in sorted(folder.iterdir()):
            if path.is_file():add(name+'/'+path.name,path)
    simulations=['sim-v1','smoke-v1','ring-sim-v1','ring-smoke-v1','ring-aux-v1','local-sim-v1','local-aux-v1','local-sim-v2','local-aux-v2']
    routes=['exploratory-route-v1','ring-exploratory-route-v1','local-exploratory-route-v2']
    endpoints=['endpoints-v1','capacity-endpoints-v1','parent-capacity-endpoints-v1','capacity-endpoints-v2','parent-capacity-endpoints-v2','ring-endpoints-v1','local-endpoints-v2']
    for name in simulations+routes+endpoints+['synth-v1','ring-synth-v1','local-synth-v1','local-synth-v2']:
        folder=root/name
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.suffix in {'.json','.log','.sha256','.tcl','.py','.dcp'}:add(name+'/'+path.name,path)
        if name in routes+endpoints:
            child='route' if name in routes else 'reports'
            for path in sorted((folder/child).iterdir()):
                if path.is_file():add(name+'/'+child+'/'+path.name,path)
        if name in simulations:
            sim=folder/'project/staged_fft.sim/sim_1/behav/xsim'
            for filename in ['simulate.log','buffered_words.csv','xvlog.log','xvhdl.log','elaborate.log']:
                add(name+'/sim/'+filename,sim/filename)
            wrapper=folder/'project/staged_fft.gen/sources_1/ip/starlink_pss_fft512_bfp18_rt_candidate/synth/starlink_pss_fft512_bfp18_rt_candidate.vhd'
            add(name+'/generated_fft.vhd',wrapper)
    for pattern in ['tools/*replay_capacity*','tools/*replay_ring*','tools/*replay_local*',
                    'tests/test_starlink_replay_capacity*.py','tests/test_starlink_replay_local*.py',
                    'tools/*evidence_archive_stream.py','tools/run_replay_local_regression.py']:
        for path in sorted(ROOT.glob(pattern)):
            name='source/'+str(path.relative_to(ROOT))
            if name not in sources:add(name,path)
    return write_verified_archive(root/'20260912-replay-capacity-evidence.tgz',sources)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path)
    print(json.dumps(record(parser.parse_args().root),indent=2))

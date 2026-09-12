"""Archive source-matched local-framing evidence without promoting a receiver."""
import argparse
import json
from pathlib import Path
from staged_fft_experiment import require,sha,verify
from route_product_local_framing import evidence
from product_local_framing_experiment_v2 import witness
from record_private_replay_sequence_evidence import passing_tests,same_audit
from write_evidence_archive_stream import write_verified_archive
import buffered_forward_experiment as main

def record(root):
    checked=evidence(root/'sim-v1',root/'synth-v1',root/'aux-v2')
    total=passing_tests(root/'regression-v2.xml',2232)
    passing_tests(root/'regression-v1.xml',2210)
    passing_tests(root/'witness-tests-v1.xml',16)
    passing_tests(root/'stimulus-tests-v1.xml',93)
    passing_tests(root/'component-v3.xml',16)
    passing_tests(root/'route-tests-v1.xml',87)
    failed_aux=json.loads((root/'aux-v1/outcome.json').read_text())
    require(failed_aux.get('passed') is False and 'error' in failed_aux,'retain unmatched publication-delay stimulus failure')
    smoke=json.loads((root/'smoke-v2/smoke_outcome.json').read_text())
    require(smoke.get('passed') is True and smoke.get('full_campaign') is False,'focused smoke, not full campaign')
    verify(Path(smoke['command'][-3]),smoke['prepared_sha'])
    require(smoke['local_framing_protocol']==witness((root/'smoke-v2/project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text(),True),'fresh smoke publication proof')
    same_audit(main.audit(root/'smoke-v2'),smoke['audit'])
    route=json.loads((root/'route-v1/audit.json').read_text())
    outcome=json.loads((root/'route-v1/outcome.json').read_text())
    require(outcome.get('returncode')==0 and outcome.get('sources_unchanged') is True and 'error' not in outcome,'terminal route')
    require(all(sha(Path(p))==value for p,value in outcome['before'].items()),'route source receipts')
    require(sha(root/'route-v1/route/retained_output_routed.dcp')==outcome['routed_dcp_sha'],'actual routed checkpoint')
    require(route['source_and_checkpoint_verified'] is True and route['routing_errors']==0,'route observation')
    require(route['full_receiver_or_physical_signoff'] is False and route['deployment_eligible'] is False,'no receiver promotion')
    endpoints=json.loads((root/'endpoints-v1/outcome.json').read_text())
    require(endpoints.get('passed') is True and endpoints.get('sources_unchanged') is True,'physical endpoints')
    require(all(sha(Path(p))==value for p,value in endpoints['before'].items()),'endpoint source receipts')
    assessment=dict(source_evidence=checked,tests=total,focused_smoke=smoke,route=route,endpoints=endpoints,rejected_auxiliary=failed_aux,
        runtime_modules=43,unchanged_parent_modules=41,actual_auxiliary_cases=88,
        receiver_integrated=False,radios_accessed=[],deployment_eligible=False,
        regression_generated_payloads='Generated regression artifacts retained locally; archive includes full passing XML and focused bank source/log artifacts.',
        initial_test_harness_failures='component-v1: parameter token substitution and extra EOF newline; component-v2: exact EOF and absent valid-framing external-veto coverage at native width. Corrected before source preparation; failed XML/logs retained.')
    with (root/'assessment.json').open('x') as output:output.write(json.dumps(assessment,indent=2)+'\n')
    sources={}
    def add(name,path):
        require(name not in sources and path.is_file() and not path.is_symlink(),'regular unique member')
        sources[name]=path
    add('assessment.json',root/'assessment.json')
    for name in ['regression-v1','regression-v2','component-v1','component-v2','component-v3','route-tests-v1','witness-tests-v1','stimulus-tests-v1']:
        add('tests/'+name+'.xml',root/(name+'.xml'))
    for name in ['component-v1','component-v2','component-v3']:
        for path in sorted((root/name).rglob('*')):
            if path.is_file() and not path.is_symlink() and not any(p.is_symlink() for p in path.parents) and path.suffix in {'.sv','.v','.log'}:
                add('tests/'+str(path.relative_to(root)),path)
    for name in ['prepared-v1','smoke-prepared-v1','smoke-prepared-v2','aux-prepared-v1','aux-prepared-v2']:
        for path in sorted((root/name).iterdir()):
            if path.is_file():add(name+'/'+path.name,path)
    for name in ['sim-v1','smoke-v1','smoke-v2','aux-v1','aux-v2','synth-v1','route-v1','endpoints-v1']:
        folder=root/name
        for path in sorted(folder.iterdir()):
            if path.is_file():add(name+'/'+path.name,path)
        if name in ['route-v1','endpoints-v1']:
            child='route' if name=='route-v1' else 'reports'
            for path in sorted((folder/child).iterdir()):
                if path.is_file():add(name+'/'+child+'/'+path.name,path)
        if name in ['sim-v1','smoke-v1','smoke-v2','aux-v1','aux-v2']:
            sim=folder/'project/staged_fft.sim/sim_1/behav/xsim'
            for filename in ['simulate.log','buffered_words.csv','xvlog.log','xvhdl.log','elaborate.log']:
                add(name+'/sim/'+filename,sim/filename)
            wrapper=folder/'project/staged_fft.gen/sources_1/ip/starlink_pss_fft512_bfp18_rt_candidate/synth/starlink_pss_fft512_bfp18_rt_candidate.vhd'
            add(name+'/generated_fft.vhd',wrapper)
    for pattern in ['tools/*product_local_framing*','tests/test_starlink_product_local_framing*',
                    'tools/inspect_private_replay_sequence.py','tools/probe_private_replay_sequence.tcl',
                    'tools/*evidence_archive_stream.py','docs/starlink-product-local-framing-*.md']:
        for path in sorted(main.ROOT.glob(pattern)):add('source/'+str(path.relative_to(main.ROOT)),path)
    return write_verified_archive(root/'20260912-product-local-framing-evidence.tgz',sources)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path)
    print(json.dumps(record(parser.parse_args().root),indent=2))

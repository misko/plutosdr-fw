"""Source-bound assessment of the opt-in publication fence; not deployment."""
import argparse
import json
from pathlib import Path
import re
import sys
from staged_fft_experiment import ROOT, sha, require, verify, audit_replay_fence, verify_replay_fence_configuration
from route_starlink_staged_fft import verify_ack_auxiliary
from record_private_admission_evidence import passing_tests, receipt
from package_staged_fft_evidence import write_verified_archive

PIN='74a8ab46a668e51ee3d9b7e3f8a8f4e7a83180b7c9c3168b3ea4b71ab60800a9'
PARENT=Path('/dev/shm/starlink-replay-quiet.C5YGuYRF/prepared-v2')

def assess(root):
    prepared=root/'prepared-v1';verify(prepared,PIN)
    verify_replay_fence_configuration(prepared)
    require(sha(PARENT/'SHA256SUMS')=='4608ae9ac75663c6e5eee752ee2489d7ef79c38701172d0572218413860ec850','parent pin')
    sys.path.insert(0,str(ROOT))
    from tests.test_starlink_replay_quiet_fence import test_exact_runtime_bench_and_synthesis_profile_delta
    test_exact_runtime_bench_and_synthesis_profile_delta()
    names=(prepared/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    changed=[n for n in names if (prepared/n).read_bytes()!=(PARENT/n).read_bytes()]
    require(len(names)==22 and changed==['starlink_pss_fft_staged_output_impl.v'],'only publication top runtime changed')
    main=audit_replay_fence(root/'sim-v1');aux=verify_ack_auxiliary(root/'ack-v1',PIN,prepared)
    outcomes={}
    for mode in ['sim','ack','synth']:
        result=json.loads((root/(mode+'-v1')/'outcome.json').read_text())
        require(result.get('mode')==mode and result.get('returncode')==0 and result.get('sources_unchanged') is True and 'error' not in result,'successful terminal actual/synthesis')
        require(result['prepared_sha']==PIN and result['command'][-3]==str(prepared),'same frozen source')
        outcomes[mode]=result
    require(json.dumps(main,sort_keys=True)==json.dumps(outcomes['sim']['audit'],sort_keys=True),'main re-audit')
    require(main['numerical_rows']==64512 and main['sha256']=='7bb1a5ce3270d8bff21ff0f0d24d9a83a759f263a871abab509b9d8276b6782d','exact parent CSV')
    clocks=[int(c[1]) for c in main['contexts']]
    require(clocks==[3663,3663,4929,11729,3663,3663],'unchanged service')
    for name,count in [('preflight-v1.xml',71),('regression-v1.xml',820),('audit-v2.xml',19)]:passing_tests(root,name,count)
    route=json.loads((root/'route-v1/outcome.json').read_text())
    require(route.get('returncode')==0 and route.get('sources_unchanged') is True and 'error' not in route,'terminal route')
    require(route['prepared_sha']==PIN and all(sha(Path(p))==v for p,v in route['before'].items()),'route source pins')
    dcp=sha(root/'route-v1/route/retained_output_routed.dcp')
    require(dcp==route['routed_dcp_sha'],'routed DCP pin')
    for folder,script in [('structure-v1','inspect_reset_receipts.tcl'),('status-paths-v1','inspect_replay_fence_paths.tcl')]:
        r=receipt(root/folder/'receipt.txt')
        require(r['source_sha256']==dcp and r['script_sha256']==sha(ROOT/'tools'/script),'inspection pins')
        require(r['constraints_changed']==r['physical_signoff']==r['deployment_eligible']=='false','no release claim')
        if folder=='structure-v1':require(r['first_stage_fanout_clean']==r['purge_source_registered']=='true','reset structure retained')
    cdc=(root/'structure-v1/cdc.rpt').read_text()
    counts={rule:int(n) for rule,n in re.findall(r'^(CDC-\d+)\s+(?:Critical|Warning|Info)\s+(\d+)\s',cdc,re.M)}
    paths=receipt(root/'status-paths-v1/paths.txt')
    require(int(paths['status_registers'])>0,'status register inventory')
    for index in range(int(paths['status_registers'])):
        name='bit'+str(index)
        require(paths[name+'.path_count'] in {'0','1'},'bounded path query')
        if paths[name+'.path_count']=='1':
            report=(root/'status-paths-v1'/(name+'.rpt')).read_text()
            value=float(re.search(r'Slack \((?:MET|VIOLATED)\)\s*:\s*([-0-9.]+)ns',report)[1])
            require(value==float(paths[name+'.slack_ns']),'targeted slack agreement')
    timing=json.loads((root/'route-v1/audit.json').read_text())
    report=(root/'route-v1/route/timing_unqualified.rpt').read_text()
    values=re.search(r'\n\s*WNS\(ns\).*?\n\s*-+[^\n]*\n([^\n]+)',report,re.S)[1].split()
    require([timing['wns_ns'],timing['tns_ns'],timing['setup_failing_endpoints']]==[float(values[0]),float(values[1]),int(values[2])],'summary agreement')
    return {'prepared_sha':PIN,'runtime_modules':22,'runtime_changed':changed,'routed_dcp_sha':dcp,
      'numerical_rows':64512,'parent_csv_identical':True,'service_clocks':clocks,
      'main_replay_quiet':main['replay_quiet'],'aux_replay_quiet':aux['replay_quiet'],
      'replay_fence':main['replay_fence'],'targeted_status_paths':paths,'cdc_counts':counts,'timing':timing,
      'elapsed_s':{k:v['elapsed'] for k,v in outcomes.items()},'route_elapsed_s':route['elapsed'],
      'regression_tests':820,'new_evidence_tests':12,'distinct_tests':832,
      'constraints_changed':False,'physical_signoff':False,'deployment_eligible':False}

def package(root,output):
    require(assess(root)==json.loads((root/'assessment.json').read_text()),'assessment drift')
    sources={};suffixes={'.json','.log','.txt','.rpt','.tsv','.xml','.v','.sv','.vhd','.tcl','.xdc','.csv','.mem','.coe','.dcp','.sha256'}
    for p in sorted(root.rglob('*')):
        if not p.is_file() or p.is_symlink() or any(x.is_symlink() for x in p.parents) or '.Xil' in p.parts:continue
        relative=p.relative_to(root);folder=relative.parts[0]
        if folder.startswith(('regression-','audit-')) and p.suffix in {'.csv','.dcp'}:continue
        if p.suffix=='.vhd' and folder in {'sim-v1','ack-v1'}:
            reference=root/'synth-v1'/p.relative_to(root/folder)
            require(reference.exists() and sha(p)==sha(reference),'duplicate generated VHDL');continue
        if p.suffix in suffixes or p.name=='SHA256SUMS':sources[str(relative)]=p
    for folder,patterns in [('tools',['*.py','inspect*.tcl']),('tests',['test_*.py'])]:
        for pattern in patterns:
            for p in (ROOT/folder).glob(pattern):sources['current/'+str(p.relative_to(ROOT))]=p
    name='docs/starlink-replay-quiet-fence-20260911.md';sources['current/'+name]=ROOT/name
    for p in PARENT.iterdir():
        if p.is_file():sources['reference/quiet-shadow/'+p.name]=p
    return write_verified_archive(output,sources)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('--archive',type=Path)
    args=parser.parse_args()
    if args.archive:result=package(args.root,args.archive)
    else:
        result=assess(args.root);target=args.root/'assessment.json';require(not target.exists(),'no overwrite')
        target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

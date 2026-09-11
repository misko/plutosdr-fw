"""Pin and archive reset-release evidence without claiming receiver signoff."""
import argparse
import json
from pathlib import Path
import re
import sys
from staged_fft_experiment import ROOT, sha, require, verify, audit_monotonic_reset, verify_monotonic_reset_configuration
from route_starlink_staged_fft import verify_ack_auxiliary
from record_private_admission_evidence import passing_tests, receipt
from package_staged_fft_evidence import write_verified_archive

PIN='adb2543750adea239f66f5b187057aef1ecdbd112cbcf5faef2161f7f6ddb3f3'
PARENT=Path('/dev/shm/starlink-split-preflight.2BQ3zjL5/prepared-v1')

def assess(root):
    prepared=root/'prepared-v1';verify(prepared,PIN);verify_monotonic_reset_configuration(prepared)
    require(sha(PARENT/'SHA256SUMS')=='1bf6ac30a6f5e3ee45b5cf489d1adecaeef08ab8ecc93495c6281fff035293c1','parent source pin')
    sys.path.insert(0,str(ROOT))
    from tests.test_starlink_monotonic_reset_release import test_exact_barrier_delta, test_exact_integration_delta
    test_exact_barrier_delta();test_exact_integration_delta()
    names=(prepared/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    changed=[n for n in names if (prepared/n).read_bytes()!=(PARENT/n).read_bytes()]
    require(len(names)==22 and set(changed)=={'starlink_pss_reset_receipt_barrier.v','starlink_pss_fft_staged_output_impl.v'},'bounded runtime delta')
    main=audit_monotonic_reset(root/'sim-v1');aux=verify_ack_auxiliary(root/'ack-v1',PIN,prepared)
    outcomes={}
    for mode in ['sim','ack','synth']:
        result=json.loads((root/(mode+'-v1')/'outcome.json').read_text())
        require(result.get('mode')==mode and result.get('returncode')==0 and result.get('sources_unchanged') is True and 'error' not in result,'terminal actual/synthesis')
        require(result['prepared_sha']==PIN and result['command'][-3]==str(prepared),'same frozen source')
        outcomes[mode]=result
    require(json.dumps(main,sort_keys=True)==json.dumps(outcomes['sim']['audit'],sort_keys=True),'main re-audit')
    require(main['numerical_rows']==64512 and main['sha256']=='7bb1a5ce3270d8bff21ff0f0d24d9a83a759f263a871abab509b9d8276b6782d','exact parent numerical CSV')
    clocks=[int(c[1]) for c in main['contexts']];require(clocks==[3663,3663,4929,11729,3663,3663],'unchanged service')
    for name,count in [('component-v1.xml',36),('component-v2.xml',76),('regression-v1.xml',921),('mailbox-v1.xml',16),('audit-v1.xml',11)]:passing_tests(root,name,count)
    route=json.loads((root/'route-v1/outcome.json').read_text())
    require(route.get('returncode')==0 and route.get('sources_unchanged') is True and 'error' not in route,'terminal route')
    require(route['prepared_sha']==PIN and all(sha(Path(p))==v for p,v in route['before'].items()),'route source pins')
    dcp=sha(root/'route-v1/route/retained_output_routed.dcp');require(dcp==route['routed_dcp_sha'],'routed DCP pin')
    for folder,script in [('structure-v1','inspect_reset_receipts.tcl'),('reset-paths-v1','inspect_monotonic_reset_paths.tcl')]:
        r=receipt(root/folder/'receipt.txt')
        require(r['source_sha256']==dcp and r['script_sha256']==sha(ROOT/'tools'/script),'inspection source pins')
        require(r['constraints_changed']==r['physical_signoff']==r['deployment_eligible']=='false','no release claim')
        if folder=='structure-v1':require(r['first_stage_fanout_clean']==r['purge_source_registered']=='true','reset structure retained')
        else:require(r['reset_first_stage_fanout_clean']=='true','reset synchronization retained')
    cdc=(root/'structure-v1/cdc.rpt').read_text()
    counts={rule:int(n) for rule,n in re.findall(r'^(CDC-\d+)\s+(?:Critical|Warning|Info)\s+(\d+)\s',cdc,re.M)}
    paths=receipt(root/'reset-paths-v1/paths.txt')
    for name in ['reset_request','reset_rom','metadata_fault']:
        require(paths[name+'.path_count'] in {'0','1'},'bounded targeted query')
        if paths[name+'.path_count']=='1':
            report=(root/'reset-paths-v1'/(name+'.rpt')).read_text()
            require(float(re.search(r'Slack \((?:MET|VIOLATED)\)\s*:\s*([-0-9.]+)ns',report)[1])==float(paths[name+'.slack_ns']),'targeted slack agreement')
    timing=json.loads((root/'route-v1/audit.json').read_text())
    values=re.search(r'\n\s*WNS\(ns\).*?\n\s*-+[^\n]*\n([^\n]+)',(root/'route-v1/route/timing_unqualified.rpt').read_text(),re.S)[1].split()
    require([timing['wns_ns'],timing['tns_ns'],timing['setup_failing_endpoints']]==[float(values[0]),float(values[1]),int(values[2])],'summary agreement')
    return {'prepared_sha':PIN,'routed_dcp_sha':dcp,'runtime_modules':22,'runtime_changed':changed,
        'numerical_rows':64512,'parent_csv_identical':True,'service_clocks':clocks,
        'main_reset_witness':main['monotonic_reset'],'aux_reset_witness':aux['monotonic_reset'],
        'targeted_paths':paths,'cdc_counts':counts,'timing':timing,
        'elapsed_s':{k:v['elapsed'] for k,v in outcomes.items()},'route_elapsed_s':route['elapsed'],
        'regression_tests':921,'additional_mailbox_tests':16,'new_evidence_tests':11,'distinct_tests':948,
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
    name='docs/starlink-monotonic-reset-release-20260911.md';sources['current/'+name]=ROOT/name
    for p in PARENT.iterdir():
        if p.is_file():sources['reference/split-preflight/'+p.name]=p
    sources['reference/split-preflight-cdc.rpt']=PARENT.parent/'structure-v1/cdc.rpt'
    return write_verified_archive(output,sources)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('--archive',type=Path)
    args=parser.parse_args()
    if args.archive:result=package(args.root,args.archive)
    else:
        result=assess(args.root);target=args.root/'assessment.json';require(not target.exists(),'no overwrite')
        target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

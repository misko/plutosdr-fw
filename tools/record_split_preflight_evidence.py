"""Source-bound split preflight assessment; no receiver/deployment claim."""
import argparse
import json
from pathlib import Path
import re
import sys
from staged_fft_experiment import ROOT, sha, require, verify, audit_split_preflight, verify_split_preflight_configuration
from route_starlink_staged_fft import verify_ack_auxiliary
from record_private_admission_evidence import passing_tests, receipt
from package_staged_fft_evidence import write_verified_archive

PIN='1bf6ac30a6f5e3ee45b5cf489d1adecaeef08ab8ecc93495c6281fff035293c1'
PARENT=Path('/dev/shm/starlink-private-quarantine.tu8FkVR0/prepared-v1')

def assess(root):
    prepared=root/'prepared-v1';verify(prepared,PIN);verify_split_preflight_configuration(prepared)
    require(sha(PARENT/'SHA256SUMS')=='2f518556a5e04dc9e161aff35d3c079914a1ecb9d6d7ffb1c6d8064b5337fb25','parent source pin')
    sys.path.insert(0,str(ROOT))
    from tests.test_starlink_split_preflight_identity import test_exact_source_delta
    test_exact_source_delta()
    names=(prepared/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    changed=[n for n in names if (prepared/n).read_bytes()!=(PARENT/n).read_bytes()]
    require(len(names)==22 and changed==['starlink_pss_fft_staged_output_impl.v'],'bounded runtime delta')
    main=audit_split_preflight(root/'sim-v1');aux=verify_ack_auxiliary(root/'ack-v1',PIN,prepared)
    outcomes={}
    for mode in ['sim','ack','synth']:
        result=json.loads((root/(mode+'-v1')/'outcome.json').read_text())
        require(result.get('mode')==mode and result.get('returncode')==0 and result.get('sources_unchanged') is True and 'error' not in result,'terminal actual/synthesis')
        require(result['prepared_sha']==PIN and result['command'][-3]==str(prepared),'same frozen source')
        outcomes[mode]=result
    require(json.dumps(main,sort_keys=True)==json.dumps(outcomes['sim']['audit'],sort_keys=True),'main re-audit')
    require(main['numerical_rows']==64512 and main['sha256']=='7bb1a5ce3270d8bff21ff0f0d24d9a83a759f263a871abab509b9d8276b6782d','exact parent numerical CSV')
    clocks=[int(c[1]) for c in main['contexts']];require(clocks==[3663,3663,4929,11729,3663,3663],'unchanged service')
    for name,count in [('component-v1.xml',23),('regression-v1.xml',874),('audit-v1.xml',17)]:passing_tests(root,name,count)
    route=json.loads((root/'route-v1/outcome.json').read_text())
    require(route.get('returncode')==0 and route.get('sources_unchanged') is True and 'error' not in route,'terminal route')
    require(route['prepared_sha']==PIN and all(sha(Path(p))==v for p,v in route['before'].items()),'route source pins')
    dcp=sha(root/'route-v1/route/retained_output_routed.dcp');require(dcp==route['routed_dcp_sha'],'routed DCP pin')
    for folder,script in [('structure-v1','inspect_reset_receipts.tcl'),('preflight-paths-v1','inspect_split_preflight_paths.tcl')]:
        r=receipt(root/folder/'receipt.txt')
        require(r['source_sha256']==dcp and r['script_sha256']==sha(ROOT/'tools'/script),'inspection source pins')
        require(r['constraints_changed']==r['physical_signoff']==r['deployment_eligible']=='false','no release claim')
        if folder=='structure-v1':require(r['first_stage_fanout_clean']==r['purge_source_registered']=='true','reset structure retained')
    cdc=(root/'structure-v1/cdc.rpt').read_text()
    counts={rule:int(n) for rule,n in re.findall(r'^(CDC-\d+)\s+(?:Critical|Warning|Info)\s+(\d+)\s',cdc,re.M)}
    paths=receipt(root/'preflight-paths-v1/paths.txt')
    for name in ['metadata_fault','reset_rom']:
        require(paths[name+'.path_count'] in {'0','1'},'bounded targeted query')
        if paths[name+'.path_count']=='1':
            report=(root/'preflight-paths-v1'/(name+'.rpt')).read_text()
            require(float(re.search(r'Slack \((?:MET|VIOLATED)\)\s*:\s*([-0-9.]+)ns',report)[1])==float(paths[name+'.slack_ns']),'targeted slack agreement')
    timing=json.loads((root/'route-v1/audit.json').read_text())
    report=(root/'route-v1/route/timing_unqualified.rpt').read_text()
    values=re.search(r'\n\s*WNS\(ns\).*?\n\s*-+[^\n]*\n([^\n]+)',report,re.S)[1].split()
    require([timing['wns_ns'],timing['tns_ns'],timing['setup_failing_endpoints']]==[float(values[0]),float(values[1]),int(values[2])],'summary agreement')
    return {'prepared_sha':PIN,'routed_dcp_sha':dcp,'runtime_modules':22,'runtime_changed':changed,
      'numerical_rows':64512,'parent_csv_identical':True,'service_clocks':clocks,
      'main_split_preflight':main['split_preflight'],'aux_split_preflight':aux['split_preflight'],
      'targeted_preflight_paths':paths,'cdc_counts':counts,'timing':timing,
      'elapsed_s':{k:v['elapsed'] for k,v in outcomes.items()},'route_elapsed_s':route['elapsed'],
      'regression_tests':874,'new_evidence_tests':10,'distinct_tests':884,
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
    name='docs/starlink-split-preflight-identity-20260911.md';sources['current/'+name]=ROOT/name
    for p in PARENT.iterdir():
        if p.is_file():sources['reference/private-quarantine/'+p.name]=p
    sources['reference/private-quarantine-cdc.rpt']=PARENT.parent/'structure-v1/cdc.rpt'
    return write_verified_archive(output,sources)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('--archive',type=Path)
    args=parser.parse_args()
    if args.archive:result=package(args.root,args.archive)
    else:
        result=assess(args.root);target=args.root/'assessment.json';require(not target.exists(),'no overwrite')
        target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

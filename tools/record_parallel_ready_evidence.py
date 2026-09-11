"""Record matched parallel READY RTL/actual FFT/route; never infer deployment."""
import argparse
import json
from pathlib import Path
import re
import sys
from staged_fft_experiment import ROOT, sha, require, verify, audit_parallel_ready, verify_parallel_ready_configuration
from route_starlink_staged_fft import verify_ack_auxiliary
from record_private_admission_evidence import passing_tests, receipt
from package_staged_fft_evidence import write_verified_archive

PIN='5fb473217ce86afe71b36ae7ee879f314d54667c0909bcaa801dcf81364b3590'
PARENT=Path('/dev/shm/starlink-forward-capacity.tHq0mgHO/prepared-v2')
PHYSICAL_PARENT=Path('/dev/shm/starlink-monotonic-reset.pL4aOpKf')

def assess(root):
    prepared=root/'prepared-v1';verify(prepared,PIN);verify_parallel_ready_configuration(prepared)
    require(sha(PARENT/'SHA256SUMS')=='a00d28c144210551b42a63b64f204f9ad0707b4553345abbaa1d193f4323a08e','parent source pin')
    sys.path.insert(0,str(ROOT))
    from tests.test_starlink_parallel_kernel_ready import test_exact_runtime_and_profile_delta, CHANGED
    test_exact_runtime_and_profile_delta()
    names=(prepared/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    changed=[n for n in names if (prepared/n).read_bytes()!=(PARENT/n).read_bytes()]
    require(len(names)==22 and set(changed)==CHANGED,'bounded five-module runtime delta')
    main=audit_parallel_ready(root/'sim-v1');aux=verify_ack_auxiliary(root/'ack-v1',PIN,prepared)
    outcomes={}
    for mode in ['sim','ack','synth']:
        result=json.loads((root/(mode+'-v1')/'outcome.json').read_text())
        require(result.get('mode')==mode and result.get('returncode')==0 and result.get('sources_unchanged') is True and 'error' not in result,'terminal source-bound actual/synthesis')
        require(result['prepared_sha']==PIN and result['command'][-3]==str(prepared),'same frozen sources')
        outcomes[mode]=result
    require(json.dumps(main,sort_keys=True)==json.dumps(outcomes['sim']['audit'],sort_keys=True),'main re-audit')
    require(main['numerical_rows']==64512 and main['sha256']=='7bb1a5ce3270d8bff21ff0f0d24d9a83a759f263a871abab509b9d8276b6782d','exact parent numerical CSV')
    service=[int(c[1]) for c in main['contexts']];require(service==[3663,3663,4929,11729,3663,3663],'unchanged service')
    for name,count in [('component-v1.xml',17),('fourstate-v2.xml',6),('regression-v1.xml',971),('audit-v1.xml',11)]:passing_tests(root,name,count)
    route=json.loads((root/'route-v1/outcome.json').read_text())
    require(route.get('returncode')==0 and route.get('sources_unchanged') is True and 'error' not in route,'terminal route')
    require(route['prepared_sha']==PIN and all(sha(Path(p))==v for p,v in route['before'].items()),'route source pins')
    dcp=sha(root/'route-v1/route/retained_output_routed.dcp');require(dcp==route['routed_dcp_sha'],'routed checkpoint pin')
    for folder,script in [('structure-v1','inspect_reset_receipts.tcl'),('ready-paths-v1','inspect_parallel_ready_paths.tcl'),('release-replicas-v1','inspect_release_replicas.tcl')]:
        r=receipt(root/folder/'receipt.txt')
        require(r['source_sha256']==dcp and r['script_sha256']==sha(ROOT/'tools'/script),'inspection source pins')
        require(r['constraints_changed']==r['physical_signoff']==r['deployment_eligible']=='false','no release claim')
        if folder=='structure-v1':require(r['first_stage_fanout_clean']==r['purge_source_registered']=='true','reset structure retained')
    cdc=(root/'structure-v1/cdc.rpt').read_text()
    counts={rule:int(n) for rule,n in re.findall(r'^(CDC-\d+)\s+(?:Critical|Warning|Info)\s+(\d+)\s',cdc,re.M)}
    paths=receipt(root/'ready-paths-v1/paths.txt')
    replicas=receipt(root/'release-replicas-v1/paths.txt')
    require(int(replicas['source_count'])>=2 and replicas['release_protocol.path_count']=='1','all release replicas queried')
    for label in ['release_fault','release_rom','release_request','release_protocol']:
        require(replicas[label+'.path_count']=='1','replicated release path retained')
        report=(root/'release-replicas-v1'/(label+'.rpt')).read_text()
        require(float(re.search(r'Slack \((?:MET|VIOLATED)\)\s*:\s*([-0-9.]+)ns',report)[1])==float(replicas[label+'.slack_ns']),'replica slack agreement')
    for name in ['release_fault','release_rom','release_request','metadata_fault']:
        require(paths[name+'.path_count'] in {'0','1'},'bounded targeted query')
        if paths[name+'.path_count']=='1':
            report=(root/'ready-paths-v1'/(name+'.rpt')).read_text()
            require(float(re.search(r'Slack \((?:MET|VIOLATED)\)\s*:\s*([-0-9.]+)ns',report)[1])==float(paths[name+'.slack_ns']),'targeted slack agreement')
    timing=json.loads((root/'route-v1/audit.json').read_text())
    values=re.search(r'\n\s*WNS\(ns\).*?\n\s*-+[^\n]*\n([^\n]+)',(root/'route-v1/route/timing_unqualified.rpt').read_text(),re.S)[1].split()
    require([timing['wns_ns'],timing['tns_ns'],timing['setup_failing_endpoints']]==[float(values[0]),float(values[1]),int(values[2])],'timing summary agreement')
    return {'prepared_sha':PIN,'routed_dcp_sha':dcp,'runtime_modules':22,'runtime_changed':changed,
      'numerical_rows':64512,'parent_csv_identical':True,'service_clocks':service,
      'main_ready_witness':main['parallel_ready'],'aux_ready_witness':aux['parallel_ready'],
      'main_capacity_shadow':main['forward_capacity_shadow'],'aux_capacity_shadow':aux['forward_capacity_shadow'],
      'targeted_paths':paths,'replicated_release_paths':replicas,'cdc_counts':counts,'timing':timing,
      'elapsed_s':{k:v['elapsed'] for k,v in outcomes.items()},'route_elapsed_s':route['elapsed'],
      'regression_tests':971,'additional_fourstate_tests':6,'new_evidence_tests':11,'distinct_tests':988,
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
    name='docs/starlink-parallel-kernel-ready-20260911.md';sources['current/'+name]=ROOT/name
    for p in PARENT.iterdir():
        if p.is_file():sources['reference/forward-capacity/'+p.name]=p
    sources['reference/monotonic-reset-cdc.rpt']=PHYSICAL_PARENT/'structure-v1/cdc.rpt'
    sources['reference/monotonic-reset-timing.json']=PHYSICAL_PARENT/'route-v1/audit.json'
    return write_verified_archive(output,sources)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('--archive',type=Path)
    args=parser.parse_args()
    if args.archive:result=package(args.root,args.archive)
    else:
        result=assess(args.root);target=args.root/'assessment.json';require(not target.exists(),'no overwrite')
        target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

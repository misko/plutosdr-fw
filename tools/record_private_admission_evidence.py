"""Source-bound assessment/archive of private admission facts, not deployment."""
import argparse
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
from staged_fft_experiment import ROOT, sha, require, verify, audit_private_facts
from route_starlink_staged_fft import verify_ack_auxiliary
from package_staged_fft_evidence import write_verified_archive

PIN='e589b35765220ac3784105df0c96f38f40a1e276a746c79767bc7c57600ff203'
SIM=Path('project/staged_fft.sim/sim_1/behav/xsim')

def passing_tests(root,file,count):
    suites=ET.parse(root/file).getroot().findall('testsuite')
    require(sum(int(s.attrib['tests']) for s in suites)==count and
            all(int(s.attrib[k])==0 for s in suites for k in ['failures','errors','skipped']),file+' complete pass')

def receipt(path):return dict(line.split('=',1) for line in path.read_text().splitlines())

def assess(root):
    prepared=root/'prepared-v1';verify(prepared,PIN)
    sys.path.insert(0,str(ROOT))
    from tests.test_starlink_private_admission_facts import PARENT, test_exact_opt_in_delta_and_unchanged_runtime, test_exact_bench_delta
    require(sha(PARENT/'SHA256SUMS')=='579b4b69fee7eb67a20befbb901d53b0ff033dd7305603e57b532d950d47114c','parent pin')
    test_exact_opt_in_delta_and_unchanged_runtime();test_exact_bench_delta()
    main=audit_private_facts(root/'sim-v1');aux=verify_ack_auxiliary(root/'ack-v1',PIN,prepared)
    outcomes={}
    for mode in ['sim','ack','synth']:
        result=json.loads((root/(mode+'-v1')/'outcome.json').read_text())
        require(result.get('returncode')==0 and result.get('sources_unchanged') is True and 'error' not in result,'terminal actual/synthesis')
        require(result['prepared_sha']==PIN and result['command'][-3]==str(prepared),'same frozen source')
        outcomes[mode]=result
    require(json.dumps(main,sort_keys=True)==json.dumps(outcomes['sim']['audit'],sort_keys=True),'main re-audit')
    require(main['numerical_rows']==64512 and main['sha256']=='7bb1a5ce3270d8bff21ff0f0d24d9a83a759f263a871abab509b9d8276b6782d','exact parent CSV')
    require([int(x[1]) for x in main['contexts']]==[3663,3663,4929,11729,3663,3663],'unchanged service')
    for file,count in [('component-v1.xml',14),('preflight-v4.xml',76),('compatibility-v1.xml',55),('regression-v2.xml',745),('audit-v1.xml',16)]:
        passing_tests(root,file,count)
    route=json.loads((root/'route-v1/outcome.json').read_text())
    require(route.get('returncode')==0 and route.get('sources_unchanged') is True and 'error' not in route,'terminal route')
    require(route['prepared_sha']==PIN and all(sha(Path(p))==v for p,v in route['before'].items()),'route source pins')
    dcp=sha(root/'route-v1/route/retained_output_routed.dcp');require(dcp==route['routed_dcp_sha'],'DCP pin')
    for folder,script in [('structure-v1','inspect_reset_receipts.tcl'),('admission-paths-v2','inspect_private_admission_paths.tcl')]:
        r=receipt(root/folder/'receipt.txt')
        require(r['source_sha256']==dcp and r['script_sha256']==sha(ROOT/'tools'/script),'inspection pins')
        require(r['constraints_changed']==r['physical_signoff']==r['deployment_eligible']=='false','no release claim')
        if folder=='structure-v1':require(r['first_stage_fanout_clean']==r['purge_source_registered']=='true','reset structure retained')
        else:require(r['private_payload_control_local']=='true','local private payload controls')
    cdc=(root/'structure-v1/cdc.rpt').read_text()
    counts={rule:int(n) for rule,n in re.findall(r'^(CDC-\d+)\s+(?:Critical|Warning|Info)\s+(\d+)\s',cdc,re.M)}
    require(counts=={'CDC-3':9,'CDC-15':208},'unchanged CDC inventory')
    paths=receipt(root/'admission-paths-v2/paths.txt')
    require(paths['payload_reset.path_count']=='0','old private payload reset path absent')
    for name in ['payload_data','payload_reset','validity','consumed']:
        require(paths[name+'.path_count'] in {'0','1'},'bounded query')
        if paths[name+'.path_count']=='1':
            report=(root/'admission-paths-v2'/(name+'.rpt')).read_text()
            value=float(re.search(r'Slack \((?:MET|VIOLATED)\)\s*:\s*([-0-9.]+)ns',report)[1])
            require(value==float(paths[name+'.slack_ns']),'targeted slack agreement')
    timing=json.loads((root/'route-v1/audit.json').read_text())
    report=(root/'route-v1/route/timing_unqualified.rpt').read_text()
    values=re.search(r'\n\s*WNS\(ns\).*?\n\s*-+[^\n]*\n([^\n]+)',report,re.S)[1].split()
    require([timing['wns_ns'],timing['tns_ns'],timing['setup_failing_endpoints']]==[float(values[0]),float(values[1]),int(values[2])],'summary agreement')
    return {'prepared_sha':PIN,'routed_dcp_sha':dcp,'numerical_rows':64512,'parent_csv_identical':True,
      'service_clocks':[int(x[1]) for x in main['contexts']], 'main_private_facts':main['private_facts'],
      'aux_private_facts':aux['private_facts'],'targeted_paths':paths,'cdc_counts':counts,'timing':timing,
      'elapsed_s':{mode:r['elapsed'] for mode,r in outcomes.items()},'route_elapsed_s':route['elapsed'],
      'regression_tests':745,'new_evidence_tests':9,'constraints_changed':False,'deployment_eligible':False}

def package(root,output):
    require(assess(root)==json.loads((root/'assessment.json').read_text()),'assessment drift')
    sources={};suffixes={'.json','.log','.txt','.rpt','.tsv','.xml','.v','.sv','.vhd','.tcl','.xdc','.csv','.mem','.coe','.dcp','.sha256'}
    for p in sorted(root.rglob('*')):
        if not p.is_file() or p.is_symlink() or any(x.is_symlink() for x in p.parents) or '.Xil' in p.parts:continue
        relative=p.relative_to(root);folder=relative.parts[0]
        if folder.startswith(('regression-','audit-')) and p.suffix in {'.csv','.dcp'}:continue
        if p.suffix=='.vhd' and folder in {'sim-v1','ack-v1'}:
            reference=root/'synth-v1'/p.relative_to(root/folder)
            require(reference.exists() and sha(p)==sha(reference),'duplicate vendor VHDL')
            continue
        if p.suffix in suffixes or p.name=='SHA256SUMS':sources[str(relative)]=p
    for folder,patterns in [('tools',['*.py','inspect*.tcl']),('tests',['test_*.py'])]:
        for pattern in patterns:
            for p in (ROOT/folder).glob(pattern):sources['current/'+str(p.relative_to(ROOT))]=p
    name='docs/starlink-private-admission-facts-20260911.md';sources['current/'+name]=ROOT/name
    return write_verified_archive(output,sources)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('--archive',type=Path)
    args=parser.parse_args()
    if args.archive:result=package(args.root,args.archive)
    else:
        result=assess(args.root);target=args.root/'assessment.json';require(not target.exists(),'no overwrite')
        target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

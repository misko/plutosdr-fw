"""Preserve the measured completion-receipt experiment, including rejected V1."""
import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from staged_fft_experiment import ROOT, sha, require, verify, audit_completion_slot
from route_starlink_staged_fft import verify_ack_auxiliary
from package_staged_fft_evidence import write_verified_archive

PIN='579b4b69fee7eb67a20befbb901d53b0ff033dd7305603e57b532d950d47114c'
SIM=Path('project/staged_fft.sim/sim_1/behav/xsim')


def assess(root):
    prepared=root/'prepared-v2';verify(prepared,PIN)
    main=audit_completion_slot(root/'sim-v3')
    aux=verify_ack_auxiliary(root/'ack-v2',PIN,prepared)
    outcomes={}
    for mode in ['sim','ack','synth']:
        result=json.loads((root/('sim-v3' if mode=='sim' else mode+'-v2')/'outcome.json').read_text())
        require(result.get('returncode')==0 and result.get('sources_unchanged') is True and 'error' not in result,'terminal actual/synthesis')
        require(result['prepared_sha']==PIN and result['command'][-3]==str(prepared),'same prepared sources')
        outcomes[mode]=result
    require(json.dumps(main,sort_keys=True)==json.dumps(outcomes['sim']['audit'],sort_keys=True),'main re-audit')
    require(main['numerical_rows']==64512,'complete indexed numerical comparison')
    require([int(c[1]) for c in main['contexts']]==[3663,3663,4929,11729,3663,3663],'one-clock normal service cost')
    names=(prepared/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    require(len(names)==22 and all((prepared/n).read_bytes()==(root/'prepared-v1'/n).read_bytes() for n in names),'runtime unchanged by monitor correction')
    require(sha(root/'prepared-v1/SHA256SUMS')=='ae1a66db7b8c98f7832ebdc64b32ee247e9db4ef3faf27ac6577ce6d48a4e4eb','failed diagnostic pin')
    require('simulator failure' in json.loads((root/'sim-v1/outcome.json').read_text())['error'],'retain failed monitor diagnostic')
    require(not (root/'route-v1').exists(),'failed V1 not routed')
    log=(root/'sim-v3'/SIM/'simulate.log').read_text()
    require('actual final ownership missing' in (root/'sim-v1'/SIM/'simulate.log').read_text(),'retained original phase-based assertion failure')
    suites=ET.parse(root/'regression-v1.xml').getroot().findall('testsuite')
    require(sum(int(s.attrib['tests']) for s in suites)==720 and all(int(s.attrib[k])==0 for s in suites for k in ['failures','errors','skipped']),'720 regression tests')
    for file,count in [('preflight-v2.xml',40),('audit-v3.xml',18)]:
        suites=ET.parse(root/file).getroot().findall('testsuite')
        require(sum(int(s.attrib['tests']) for s in suites)==count and all(int(s.attrib[k])==0 for s in suites for k in ['failures','errors','skipped']),'post-correction tests')
    route=json.loads((root/'route-v2/outcome.json').read_text())
    require(route.get('returncode')==0 and route.get('sources_unchanged') is True and 'error' not in route,'terminal route')
    require(route['prepared_sha']==PIN and all(sha(Path(p))==s for p,s in route['before'].items()),'route source pins')
    dcp=sha(root/'route-v2/route/retained_output_routed.dcp');require(dcp==route['routed_dcp_sha'],'route DCP pin')
    receipt=dict(line.split('=',1) for line in (root/'structure-v2/receipt.txt').read_text().splitlines())
    require(receipt['source_sha256']==dcp and receipt['script_sha256']==sha(ROOT/'tools/inspect_reset_receipts.tcl'),'CDC inspection pins')
    require(receipt['first_stage_fanout_clean']==receipt['purge_source_registered']=='true','reset structure retained')
    require(receipt['constraints_changed']==receipt['physical_signoff']==receipt['deployment_eligible']=='false','no constraint or release claim')
    cdc=(root/'structure-v2/cdc.rpt').read_text()
    counts=dict((rule,int(count)) for rule,count in re.findall(r'^(CDC-\d+)\s+(?:Critical|Warning|Info)\s+(\d+)\s',cdc,re.M))
    require(counts=={'CDC-3':9,'CDC-15':208},'complete unchanged qualified control inventory')
    pair=dict(line.split('=',1) for line in (root/'completion-paths-v2/receipt.txt').read_text().splitlines())
    require(pair['source_sha256']==dcp and pair['script_sha256']==sha(ROOT/'tools/inspect_completion_stage_paths.tcl'),'targeted path pins')
    paths=dict(line.split('=',1) for line in (root/'completion-paths-v2/paths.txt').read_text().splitlines())
    for name,destination in [('phase','output_control/phase_reg[0]/D'),('pending','output_control/complete_pending_reg/D'),('publication_seen','output_control/publication_seen_reg/D')]:
        require(paths[name+'.source']=='output_descriptor_payload_reg[4]/C' and paths[name+'.destination']==destination,'exact old/new endpoint')
        require(paths[name+'.path_count'] in {'0','1'},'bounded path query')
        if paths[name+'.path_count']=='1':
            report=(root/'completion-paths-v2'/(name+'.rpt')).read_text()
            slack=float(re.search(r'Slack \((?:MET|VIOLATED)\)\s*:\s*([-0-9.]+)ns',report)[1])
            require(slack==float(paths[name+'.slack_ns']),'targeted path report agreement')
    timing=json.loads((root/'route-v2/audit.json').read_text())
    report=(root/'route-v2/route/timing_unqualified.rpt').read_text()
    values=re.search(r'\n\s*WNS\(ns\).*?\n\s*-+[^\n]*\n([^\n]+)',report,re.S)[1].split()
    require([timing['wns_ns'],timing['tns_ns'],timing['setup_failing_endpoints']]==[float(values[0]),float(values[1]),int(values[2])],'timing summary agreement')
    return {'prepared_sha':PIN,'routed_dcp_sha':dcp,'numerical_rows':64512,'numerical_csv_sha':main['sha256'],
      'service_clocks':[int(c[1]) for c in main['contexts']],
      'main_completion_slot':main['completion_slot'],'aux_completion_slot':aux['completion_slot'],
      'targeted_paths':paths,
      'elapsed_s':{m:r['elapsed'] for m,r in outcomes.items()},'route_elapsed_s':route['elapsed'],
      'cdc_counts':counts,'timing':timing,'constraints_changed':False,
      'full_receiver_signoff':False,'deployment_eligible':False}


def package(root,output):
    require(assess(root)==json.loads((root/'assessment.json').read_text()),'assessment drift')
    sources={};suffixes={'.json','.log','.txt','.rpt','.tsv','.xml','.v','.sv','.vhd','.tcl','.xdc','.csv','.mem','.coe','.dcp','.sha256'}
    for folder in ['prepared-v1','prepared-v2','sim-v1','sim-v2','sim-v3','ack-v1','ack-v2','synth-v1','synth-v2',
                   'route-v2','structure-v2','completion-paths-v2','component-v1','preflight-v1','preflight-v2','regression-v1','audit-v2','audit-v3']:
        for p in sorted((root/folder).rglob('*')):
            if p.is_symlink() or any(a.is_symlink() for a in p.parents) or '.Xil' in p.parts:continue
            if folder in {'regression-v1','audit-v2','audit-v3'} and p.suffix in {'.csv','.dcp'}:continue
            if p.suffix=='.vhd' and folder in {'sim-v1','sim-v2','sim-v3','ack-v1','ack-v2','synth-v1'}:
                reference=root/'synth-v2'/p.relative_to(root/folder)
                require(reference.exists() and sha(p)==sha(reference),'duplicate vendor source pin')
                continue
            if p.is_file() and (p.suffix in suffixes or p.name=='SHA256SUMS'):sources[str(p.relative_to(root))]=p
    for p in root.iterdir():
        if p.is_file() and p.suffix in {'.json','.xml','.log'}:sources[p.name]=p
    for folder,pattern in [('tools','*.py'),('tools','inspect*.tcl'),('tests','test_*completion*.py')]:
        for p in (ROOT/folder).glob(pattern):sources['current/'+str(p.relative_to(ROOT))]=p
    for name in ['tests/test_starlink_balanced_handoff.py','tests/test_starlink_preflight_publication.py',
                 'docs/starlink-completion-mailbox-stage-20260911.md']:
        sources['current/'+name]=ROOT/name
    return write_verified_archive(output,sources)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('--archive',type=Path)
    args=parser.parse_args()
    if args.archive:result=package(args.root,args.archive)
    else:
        result=assess(args.root);target=args.root/'assessment.json';require(not target.exists(),'no overwrite')
        target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

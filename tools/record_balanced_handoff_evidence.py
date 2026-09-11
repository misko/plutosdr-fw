"""Preserve the measured balanced-handoff experiment, including rejected V1."""
import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from staged_fft_experiment import ROOT, sha, require, verify, audit_balancedhandoff
from route_starlink_staged_fft import verify_ack_auxiliary
from package_staged_fft_evidence import write_verified_archive

PIN='c6b632215fbd08fa2c06150652f39a3967163566eeaac8c01138c7475c1c429e'
SIM=Path('project/staged_fft.sim/sim_1/behav/xsim')


def assess(root):
    prepared=root/'prepared-v2';verify(prepared,PIN)
    main=audit_balancedhandoff(root/'sim-v2')
    aux=verify_ack_auxiliary(root/'ack-v2',PIN,prepared)
    outcomes={}
    for mode in ['sim','ack','synth']:
        result=json.loads((root/(mode+'-v2')/'outcome.json').read_text())
        require(result.get('returncode')==0 and result.get('sources_unchanged') is True and 'error' not in result,'terminal actual/synthesis')
        require(result['prepared_sha']==PIN and result['command'][-3]==str(prepared),'same prepared sources')
        outcomes[mode]=result
    require(json.dumps(main,sort_keys=True)==json.dumps(outcomes['sim']['audit'],sort_keys=True),'main re-audit')
    require(main['sha256']=='14188bdee37e0e76d64c128ec7baf7efe33a70172e376fcb4ff735d0a1f50317','byte-exact parent numerical CSV')
    require([int(c[1]) for c in main['contexts']]==[3662,3662,4929,11729,3662,3662],'unchanged service')
    names=(prepared/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    require(len(names)==22 and all((prepared/n).read_bytes()==(root/'prepared-v1'/n).read_bytes() for n in names),'runtime unchanged by monitor correction')
    require(sha(root/'prepared-v1/SHA256SUMS')=='ccd6dc48b97cc486332d74ff785554c6bacbb7b34c84af584ca4c561c3b4add1','failed diagnostic pin')
    require('simulator failure' in json.loads((root/'sim-v1/outcome.json').read_text())['error'],'retain failed monitor diagnostic')
    require(not (root/'route-v1').exists(),'failed V1 not routed')
    log=(root/'sim-v2'/SIM/'simulate.log').read_text()
    require(re.search(r'^STAGED_HANDOFF_SETTLED_DELTA .*before=1 reference=0 settled=0$',log,re.M),'observed delta-cycle resolution')
    suites=ET.parse(root/'regression-v1.xml').getroot().findall('testsuite')
    require(sum(int(s.attrib['tests']) for s in suites)==682 and all(int(s.attrib[k])==0 for s in suites for k in ['failures','errors','skipped']),'682 regression tests')
    for file,count in [('preflight-v2.xml',28),('audit-v2.xml',15)]:
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
    pair=dict(line.split('=',1) for line in (root/'handoff-path-v2/receipt.txt').read_text().splitlines())
    require(pair['source_sha256']==dcp and pair['script_sha256']==sha(ROOT/'tools/inspect_balanced_handoff_path.tcl'),'targeted path pins')
    require(pair['from']=='owners[0].result_guard/return_exponent_reg[2]/C' and pair['to']=='output_bank/request_toggle_reg/D','same original endpoint pair')
    pair_report=(root/'handoff-path-v2/original_pair.rpt').read_text()
    pair_slack=float(re.search(r'Slack \((?:MET|VIOLATED)\)\s*:\s*([-0-9.]+)ns',pair_report)[1])
    require(pair_slack==float(pair['slack_ns']),'targeted path report agreement')
    timing=json.loads((root/'route-v2/audit.json').read_text())
    report=(root/'route-v2/route/timing_unqualified.rpt').read_text()
    values=re.search(r'\n\s*WNS\(ns\).*?\n\s*-+[^\n]*\n([^\n]+)',report,re.S)[1].split()
    require([timing['wns_ns'],timing['tns_ns'],timing['setup_failing_endpoints']]==[float(values[0]),float(values[1]),int(values[2])],'timing summary agreement')
    return {'prepared_sha':PIN,'routed_dcp_sha':dcp,'numerical_rows':64512,'numerical_csv_sha':main['sha256'],
      'service_clocks':[int(c[1]) for c in main['contexts']],
      'main_handoff':main['balancedhandoff'],'aux_handoff':aux['balancedhandoff'],
      'original_endpoint_pair_slack_ns':pair_slack,
      'original_endpoint_pair_logic_levels':int(re.search(r'Logic Levels:\s*(\d+)',pair_report)[1]),
      'elapsed_s':{m:r['elapsed'] for m,r in outcomes.items()},'route_elapsed_s':route['elapsed'],
      'cdc_counts':counts,'timing':timing,'constraints_changed':False,
      'full_receiver_signoff':False,'deployment_eligible':False}


def package(root,output):
    require(assess(root)==json.loads((root/'assessment.json').read_text()),'assessment drift')
    sources={};suffixes={'.json','.log','.txt','.rpt','.tsv','.xml','.v','.sv','.vhd','.tcl','.xdc','.csv','.mem','.coe','.dcp','.sha256'}
    for folder in ['prepared-v1','prepared-v2','sim-v1','sim-v2','ack-v1','ack-v2','synth-v1','synth-v2',
                   'route-v2','structure-v2','handoff-path-v2','preflight-v1','preflight-v2','regression-v1','audit-v2']:
        for p in sorted((root/folder).rglob('*')):
            if p.is_symlink() or any(a.is_symlink() for a in p.parents) or '.Xil' in p.parts:continue
            if folder in {'regression-v1','audit-v2'} and p.suffix in {'.csv','.dcp'}:continue
            if p.suffix=='.vhd' and folder in {'sim-v1','sim-v2','ack-v1','ack-v2','synth-v1'}:
                reference=root/'synth-v2'/p.relative_to(root/folder)
                require(reference.exists() and sha(p)==sha(reference),'duplicate vendor source pin')
                continue
            if p.is_file() and (p.suffix in suffixes or p.name=='SHA256SUMS'):sources[str(p.relative_to(root))]=p
    for p in root.iterdir():
        if p.is_file() and p.suffix in {'.json','.xml','.log'}:sources[p.name]=p
    for folder,pattern in [('tools','*.py'),('tools','inspect*.tcl'),('tests','test_*handoff*.py')]:
        for p in (ROOT/folder).glob(pattern):sources['current/'+str(p.relative_to(ROOT))]=p
    for name in ['tests/test_starlink_product_stage_integration.py','tests/test_starlink_reset_receipts.py',
                 'docs/starlink-balanced-handoff-20260911.md']:
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

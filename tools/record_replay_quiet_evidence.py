"""Record shadow publication contract evidence; runtime and physical route unchanged."""
import argparse
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
from staged_fft_experiment import ROOT,sha,require,verify,audit_replay_quiet
from package_staged_fft_evidence import write_verified_archive

PIN='4608ae9ac75663c6e5eee752ee2489d7ef79c38701172d0572218413860ec850'
PARENT=Path('/dev/shm/starlink-private-admission.jU5bmytc')

def assess(root):
    prepared=root/'prepared-v2';verify(prepared,PIN)
    require(sha(PARENT/'prepared-v1/SHA256SUMS')=='e589b35765220ac3784105df0c96f38f40a1e276a746c79767bc7c57600ff203','parent source pin')
    names=(prepared/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    require(len(names)==22 and all((prepared/n).read_bytes()==(PARENT/'prepared-v1'/n).read_bytes() for n in names),'all compiled runtime byte-identical')
    require(all((prepared/n).read_bytes()==(root/'prepared-v1'/n).read_bytes() for n in names),'runtime unchanged by shadow correction')
    require(sha(root/'prepared-v1/SHA256SUMS')=='e7afdc538ae644301e28d2900fb67613032f0487f038d5aa3086383674b83637','retained V1 source')
    failed=json.loads((root/'sim-v1/outcome.json').read_text())
    require(failed['sources_unchanged'] and 'simulator failure' in failed['error'],'retained failed shadow diagnostic')
    require('replay quiet publication decision differs' in (root/'sim-v1/project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text(),'retained forced-stall mismatch')
    sys.path.insert(0,str(ROOT))
    from tests.test_starlink_replay_quiet_contract import test_runtime_byte_identical_and_exact_additive_bench
    test_runtime_byte_identical_and_exact_additive_bench()
    results={}
    for mode in ['sim','ack']:
        result=json.loads((root/(mode+'-v2')/'outcome.json').read_text())
        require(result.get('returncode')==0 and result.get('sources_unchanged') is True and 'error' not in result,'successful terminal actual FFT')
        require(result['prepared_sha']==PIN and result['command'][-3]==str(prepared),'same frozen actual source')
        audited=audit_replay_quiet(root/(mode+'-v2'),auxiliary=mode=='ack')
        require(json.dumps(audited,sort_keys=True)==json.dumps(result['audit'],sort_keys=True),'complete actual re-audit')
        results[mode]=result
    main=results['sim']['audit']
    require(main['numerical_rows']==64512 and main['sha256']=='7bb1a5ce3270d8bff21ff0f0d24d9a83a759f263a871abab509b9d8276b6782d','exact parent CSV')
    require([int(c[1]) for c in main['contexts']]==[3663,3663,4929,11729,3663,3663],'unchanged service')
    for name,count in [('preflight-v1.xml',59),('preflight-v2.xml',59),('regression-v1.xml',767),('audit-v1.xml',18)]:
        suites=ET.parse(root/name).getroot().findall('testsuite')
        require(sum(int(s.attrib['tests']) for s in suites)==count and all(int(s.attrib[k])==0 for s in suites for k in ['failures','errors','skipped']),name+' complete tests')
    require(not (root/'route-v1').exists() and not (root/'synth-v1').exists(),'no new physical experiment claimed')
    dcp=PARENT/'route-v1/route/retained_output_routed.dcp'
    require(sha(dcp)=='456b3dbb87310f1c68a0188f4568d72552091b8b7e86b9ec81e52a90c7254d1e','inherited route checkpoint')
    timing=json.loads((PARENT/'route-v1/audit.json').read_text())
    require(timing['wns_ns']==-1.661 and timing['setup_failing_endpoints']==944 and timing['internal_timing_pass'] is False,'inherited failing route, not improvement')
    return {'prepared_sha':PIN,'runtime_modules_unchanged':22,'numerical_rows':64512,'parent_csv_identical':True,
      'service_clocks':[int(c[1]) for c in main['contexts']],
      'main_replay_quiet':main['replay_quiet'],'aux_replay_quiet':results['ack']['audit']['replay_quiet'],
      'elapsed_s':{k:v['elapsed'] for k,v in results.items()},'regression_tests':767,'new_evidence_tests':11,
      'inherited_routed_dcp_sha':sha(dcp),'inherited_timing':timing,'new_route_run':False,
      'publication_logic_changed':False,'physical_signoff':False,'deployment_eligible':False}

def package(root,output):
    require(assess(root)==json.loads((root/'assessment.json').read_text()),'assessment drift')
    sources={};suffixes={'.json','.log','.txt','.rpt','.tsv','.xml','.v','.sv','.vhd','.tcl','.xdc','.csv','.mem','.coe','.dcp','.sha256'}
    for p in sorted(root.rglob('*')):
        if not p.is_file() or p.is_symlink() or any(x.is_symlink() for x in p.parents) or '.Xil' in p.parts:continue
        relative=p.relative_to(root);folder=relative.parts[0]
        if folder.startswith(('regression-','audit-')) and p.suffix in {'.csv','.dcp'}:continue
        if p.suffix=='.vhd' and folder in {'sim-v1','ack-v1','ack-v2'}:
            reference=root/'sim-v2'/p.relative_to(root/folder)
            require(reference.exists() and sha(p)==sha(reference),'duplicate generated VHDL');continue
        if p.suffix in suffixes or p.name=='SHA256SUMS':sources[str(relative)]=p
    for folder,patterns in [('tools',['*.py']),('tests',['test_*.py'])]:
        for pattern in patterns:
            for p in (ROOT/folder).glob(pattern):sources['current/'+str(p.relative_to(ROOT))]=p
    for name in ['route-v1/outcome.json','route-v1/audit.json','route-v1/route/timing_unqualified.rpt','route-v1/route/retained_output_routed.dcp']:
        sources['inherited-parent/'+name]=PARENT/name
    name='docs/starlink-replay-quiet-contract-20260911.md';sources['current/'+name]=ROOT/name
    return write_verified_archive(output,sources)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('--archive',type=Path)
    args=parser.parse_args()
    if args.archive:result=package(args.root,args.archive)
    else:
        result=assess(args.root);target=args.root/'assessment.json';require(not target.exists(),'no overwrite')
        target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

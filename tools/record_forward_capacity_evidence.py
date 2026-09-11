"""Archive observational capacity proof, explicitly not a new routed design."""
import argparse
import json
from pathlib import Path
import sys
from staged_fft_experiment import ROOT, sha, require, verify, audit_forward_capacity
from record_private_admission_evidence import passing_tests
from package_staged_fft_evidence import write_verified_archive

PIN='a00d28c144210551b42a63b64f204f9ad0707b4553345abbaa1d193f4323a08e'
PARENT=Path('/dev/shm/starlink-monotonic-reset.pL4aOpKf')

def assess(root):
    prepared=root/'prepared-v2';verify(prepared,PIN)
    require(sha(PARENT/'prepared-v1/SHA256SUMS')=='adb2543750adea239f66f5b187057aef1ecdbd112cbcf5faef2161f7f6ddb3f3','parent source pin')
    sys.path.insert(0,str(ROOT))
    from tests.test_starlink_forward_capacity_contract import test_unchanged_runtime_and_exact_bench_delta
    test_unchanged_runtime_and_exact_bench_delta()
    names=(prepared/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    require(len(names)==22 and all((prepared/n).read_bytes()==(PARENT/'prepared-v1'/n).read_bytes() for n in names),'all runtime byte-identical')
    outcomes={};audits={}
    for mode in ['sim','ack']:
        result=json.loads((root/(mode+'-v2')/'outcome.json').read_text())
        require(result.get('mode')==mode and result.get('returncode')==0 and result.get('sources_unchanged') is True and 'error' not in result,'terminal source-bound actual run')
        require(result['prepared_sha']==PIN and result['command'][-3]==str(prepared),'same frozen source')
        audited=audit_forward_capacity(root/(mode+'-v2'),auxiliary=mode=='ack')
        require(json.dumps(audited,sort_keys=True)==json.dumps(result['audit'],sort_keys=True),'actual re-audit')
        outcomes[mode]=result;audits[mode]=audited
    main=audits['sim']
    require(main['numerical_rows']==64512 and main['sha256']=='7bb1a5ce3270d8bff21ff0f0d24d9a83a759f263a871abab509b9d8276b6782d','exact numerical reference')
    service=[int(row[1]) for row in main['contexts']]
    require(service==[3663,3663,4929,11729,3663,3663],'unchanged service')
    for name,count in [('component-v1.xml',8),('component-v2.xml',9),('regression-v1.xml',955),('regression-v2.xml',956),('audit-v1.xml',8)]:passing_tests(root,name,count)
    failed=json.loads((root/'ack-v1/outcome.json').read_text())
    require(failed['error']=='ValueError: auxiliary simulator failure' and failed['sources_unchanged'] is True,'preserved failed first auxiliary')
    require('Fatal: parallel capacity equation mismatch' in (root/'ack-v1/project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text(),'preserved failure cause')
    before=(root/'prepared-v1/tb_fft_staged_output.sv').read_text()
    old='!dut.product.arithmetic.sum_valid || !dut.product_valid;'
    new='!dut.product.arithmetic.sum_valid || !dut.product.arithmetic.output_valid;'
    require(before.count(old)==1 and before.replace(old,new,1)==(prepared/'tb_fft_staged_output.sv').read_text(),'only observation point changed between actual versions')
    require(all((root/'prepared-v1'/n).read_bytes()==(prepared/n).read_bytes() for n in names),'no runtime change after failed observation')
    dcp=PARENT/'route-v1/route/retained_output_routed.dcp'
    require(sha(dcp)=='97363f456b8fc8527d455e37f1348ab6f26bee232a6d42ed8c0c8236a8a9904d','inherited checkpoint pin')
    timing=json.loads((PARENT/'route-v1/audit.json').read_text())
    require(timing['wns_ns']==-1.399 and timing['same_domain_175_setup_ns']==-1.324 and timing['internal_timing_pass'] is False,'inherited failed timing')
    return {'prepared_sha':PIN,'runtime_modules':22,'runtime_byte_identical':True,
      'actual_shadows':{k:v['forward_capacity_shadow'] for k,v in audits.items()},
      'numerical_rows':64512,'parent_csv_identical':True,'service_clocks':service,
      'elapsed_s':{k:v['elapsed'] for k,v in outcomes.items()},
      'regression_tests':956,'new_evidence_tests':8,'distinct_tests':964,
      'first_auxiliary_failed':True,'first_failure':'shadow observed forced transport valid instead of owning register',
      'new_synthesis_or_route':False,'inherited_routed_dcp_sha':sha(dcp),
      'inherited_timing':timing,'production_interface_proven':False,
      'constraints_changed':False,'physical_signoff':False,'deployment_eligible':False}

def package(root,output):
    require(assess(root)==json.loads((root/'assessment.json').read_text()),'assessment drift')
    sources={};suffixes={'.json','.log','.txt','.rpt','.tsv','.xml','.v','.sv','.vhd','.tcl','.xdc','.csv','.mem','.coe','.dcp','.sha256'}
    for p in sorted(root.rglob('*')):
        if not p.is_file() or p.is_symlink() or any(x.is_symlink() for x in p.parents) or '.Xil' in p.parts:continue
        relative=p.relative_to(root);folder=relative.parts[0]
        if folder.startswith(('regression-','audit-')) and p.suffix in {'.csv','.dcp'}:continue
        if p.suffix=='.vhd' and folder in {'ack-v1','ack-v2','sim-v2'}:
            reference=root/'sim-v1'/p.relative_to(root/folder)
            require(reference.exists() and sha(p)==sha(reference),'duplicate actual VHDL');continue
        if p.suffix in suffixes or p.name=='SHA256SUMS':sources[str(relative)]=p
    for folder,patterns in [('tools',['*.py']),('tests',['test_*.py'])]:
        for pattern in patterns:
            for p in (ROOT/folder).glob(pattern):sources['current/'+str(p.relative_to(ROOT))]=p
    name='docs/starlink-forward-capacity-contract-20260911.md';sources['current/'+name]=ROOT/name
    for p in (PARENT/'prepared-v1').iterdir():
        if p.is_file():sources['reference/monotonic-reset/'+p.name]=p
    for relative in ['assessment.json','route-v1/audit.json','route-v1/outcome.json','route-v1/route/retained_output_routed.dcp','route-v1/route/island_175_island_175_max.rpt','structure-v1/cdc.rpt']:
        sources['inherited-not-rerun/'+relative]=PARENT/relative
    return write_verified_archive(output,sources)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('--archive',type=Path)
    args=parser.parse_args()
    if args.archive:result=package(args.root,args.archive)
    else:
        result=assess(args.root);target=args.root/'assessment.json';require(not target.exists(),'no overwrite')
        target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

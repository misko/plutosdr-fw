"""Source-bound component/actual-observer evidence, never receiver signoff."""
import argparse
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
from forward_return_bank_experiment import ROOT, RTL, BANK, PARENT, witness
from staged_fft_experiment import verify, sha, require, audit_parallel_ready
from record_private_admission_evidence import passing_tests, receipt
from package_staged_fft_evidence import write_verified_archive

PIN='947c2e9fe7a1b8a0acf449fdf32a69cceadef84a3e390a33c5d713bbf3d37824'

def assess(root):
    prepared=root/'prepared-v2';verify(prepared,PIN)
    sys.path.insert(0,str(ROOT))
    from tests.test_starlink_forward_return_evidence import test_prepared_observer_does_not_change_runtime_or_reference_stimulus
    test_prepared_observer_does_not_change_runtime_or_reference_stimulus()
    for name,count in [('component-v3.xml',31),('evidence-v1.xml',11),('regression-v1.xml',1077)]:
        passing_tests(root,name,count)
    outcomes={};observers={}
    for mode in ['sim','ack']:
        folder=root/(mode+'-v2');outcome=json.loads((folder/'outcome.json').read_text())
        require(outcome.get('returncode')==0 and outcome.get('sources_unchanged') is True and 'error' not in outcome,'terminal actual observer run')
        require(outcome['prepared_sha']==PIN and outcome['command'][-3]==str(prepared),'same source actual evidence')
        audit=audit_parallel_ready(folder,auxiliary=mode=='ack')
        require(json.dumps(audit,sort_keys=True)==json.dumps(outcome['audit'],sort_keys=True),'re-audited original campaigns')
        observed=witness((folder/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text())
        require(observed==json.loads((folder/'forward_return_observer.json').read_text()),'observer re-audit')
        observers[mode]=observed;outcomes[mode]=outcome
    main=outcomes['sim']['audit']
    require(main['numerical_rows']==64512 and main['sha256']=='7bb1a5ce3270d8bff21ff0f0d24d9a83a759f263a871abab509b9d8276b6782d','unchanged original numerical data')
    require([int(c[1]) for c in main['contexts']]==[3663,3663,4929,11729,3663,3663],'original service unchanged, not buffered service')
    route=root/'bank-route-v1';r=receipt(route/'receipt.txt')
    require(r['source_sha256']==sha(RTL/BANK)==sha(prepared/BANK),'actual/physical bank source match')
    require(r['script_sha256']==sha(ROOT/'tools/route_forward_return_bank.tcl')==sha(route/'runner.tcl'),'physical recipe match')
    require(r['routed_dcp_sha256']==sha(route/'routed.dcp'),'DCP source pin')
    require(r['ramb18']=='1' and r['capture_ready_decoupled']==r['ram_write_decoupled']=='true','local capture capacity structure')
    require(r['standalone_only']=='true' and r['receiver_integration']==r['physical_signoff']==r['deployment_eligible']=='false','scope explicitly standalone')
    ports=receipt(root/'ports-v1/receipt.txt')
    require(ports['source_sha256']==r['routed_dcp_sha256'] and ports['script_sha256']==sha(ROOT/'tools/inspect_forward_return_ports.tcl'),'complete port inspection pin')
    require(ports['sdp_write_controls_decoupled']=='true','write CE/address/data-valid capacity separation')
    report=(route/'timing_unqualified.rpt').read_text()
    values=re.search(r'\n\s*WNS\(ns\).*?\n\s*-+[^\n]*\n([^\n]+)',report,re.S)[1].split()
    wns,tns=float(values[0]),float(values[1]);fail=int(values[2])
    path=(route/'internal_paths.rpt').read_text()
    require(float(re.search(r'Slack \((?:MET|VIOLATED)\)\s*:\s*([-0-9.]+)ns',path)[1])==wns,'internal report agreement')
    utilization=(route/'utilization.rpt').read_text()
    def used(label):return int(re.search(r'\|\s*'+re.escape(label)+r'\s*\|\s*(\d+)\s*\|',utilization)[1])
    routing=(route/'route_status.rpt').read_text()
    def routes(label):return int(re.search(re.escape(label)+r'\.*\s*:\s*(\d+)',routing)[1])
    require(routes('# of fully routed nets')==routes('# of routable nets') and routes('# of nets with routing errors')==0,'complete route')
    return {'prepared_sha':PIN,'bank_source_sha':sha(RTL/BANK),'routed_dcp_sha':r['routed_dcp_sha256'],
        'regression_tests':1077,'original_runtime_modules':22,'original_runtime_unchanged':True,
        'original_csv_sha':main['sha256'],'actual_observers':observers,
        'actual_elapsed_s':{k:v['elapsed'] for k,v in outcomes.items()},
        'standalone':{'wns_ns':wns,'tns_ns':tns,'setup_failures':fail,'setup_endpoints':int(values[3]),
            'hold_slack_ns':float(values[4]),'hold_failures':int(values[6]),'pulse_slack_ns':float(values[8]),'pulse_failures':int(values[10]),
            'lut':used('Slice LUTs'),'ff':used('Slice Registers'),'ramb18':used('RAMB18'),'dsp':used('DSPs'),
            'fully_routed_nets':routes('# of fully routed nets'),'capture_ready_decoupled':True,'sdp_write_controls_decoupled':True},
        'receiver_integration':False,'buffered_service_budget_verified':False,'physical_signoff':False,'deployment_eligible':False}

def package(root,output):
    require(assess(root)==json.loads((root/'assessment.json').read_text()),'assessment drift')
    sources={};suffixes={'.json','.log','.txt','.rpt','.xml','.v','.sv','.svh','.vhd','.tcl','.xdc','.csv','.mem','.coe','.dcp','.sha256'}
    for p in sorted(root.rglob('*')):
        if not p.is_file() or p.is_symlink() or any(x.is_symlink() for x in p.parents) or '.Xil' in p.parts:continue
        if p.suffix in suffixes or p.name=='SHA256SUMS':sources[str(p.relative_to(root))]=p
    for folder,patterns in [('tools',['*.py','*forward_return*.tcl']),('tests',['test_*.py'])]:
        for pattern in patterns:
            for p in (ROOT/folder).glob(pattern):sources['current/'+str(p.relative_to(ROOT))]=p
    for name in [BANK,'tb_forward_return_bank.sv','forward_return_actual_observer.svh']:
        sources['current/rtl/'+name]=RTL/name
    for p in PARENT.iterdir():
        if p.is_file():sources['reference/scalar-fault/'+p.name]=p
    name='docs/starlink-forward-return-bank-20260911.md';sources['current/'+name]=ROOT/name
    return write_verified_archive(output,sources)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('--archive',type=Path)
    args=parser.parse_args()
    if args.archive:result=package(args.root,args.archive)
    else:
        result=assess(args.root);target=args.root/'assessment.json';require(not target.exists(),'no overwrite')
        target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

"""Require source-matched scalar/sticky and final-handshake evidence to route."""
import argparse
import json
from pathlib import Path
import re
import sys
from staged_fft_experiment import ROOT, verify, require, audit_parallel_ready
from route_starlink_staged_fft import verify_ack_auxiliary, run
from route_forward_final_commit import witness as final_witness

PIN='9cd61fa49b0dc1313c1c6c03679a5cf0fd757cb6ac76ad8c2b8325fcf5e40f50'
SIM=Path('project/staged_fft.sim/sim_1/behav/xsim')

def witness(text):
    rows=re.findall(r'^STAGED_STICKY_FAULT_PASS checks=(\d+) events=(\d+) resets=(\d+) seen=([0-9a-fA-F]{5}) scalar_exact=1 same_edge=1$',text,re.M)
    require(len(rows)==1 and text.count('STAGED_STICKY_FAULT_PASS')==1,'one complete sticky-fault witness required')
    checks,events,resets=map(int,rows[0][:3]);seen=int(rows[0][3],16)
    require(checks>=1000 and 10<=events<=checks and 10<=resets<=checks and 0<seen<=0x7ffff,'sticky-fault coverage incomplete')
    return {'checks':checks,'events':events,'resets':resets,'seen':seen,'scalar_exact':True,'same_edge':True}

def verify_pair(root):
    prepared=root/'prepared-v1';verify(prepared,PIN)
    sys.path.insert(0,str(ROOT))
    from tests.test_starlink_distributed_sticky_fault import test_one_runtime_module_and_additive_bench, undo_top, undo_bench, PARENT, TOP
    test_one_runtime_module_and_additive_bench()
    require(undo_top((prepared/TOP).read_text())==(PARENT/TOP).read_text(),'prepared top delta')
    require(undo_bench((prepared/'tb_fft_staged_output.sv').read_text())==(PARENT/'tb_fft_staged_output.sv').read_text(),'prepared bench delta')
    main=audit_parallel_ready(root/'sim-v1')
    aux=verify_ack_auxiliary(root/'ack-v1',PIN,prepared)
    result={}
    for mode,audited in [('sim',main),('ack',aux)]:
        folder=root/(mode+'-v1');outcome=json.loads((folder/'outcome.json').read_text())
        require(outcome.get('mode')==mode and outcome.get('returncode')==0 and outcome.get('sources_unchanged') is True and 'error' not in outcome,'successful actual run required')
        require(outcome['prepared_sha']==PIN and outcome['command'][-3]==str(prepared),'same frozen actual source')
        require(json.dumps(audited,sort_keys=True)==json.dumps(outcome['audit'],sort_keys=True),'actual re-audit mismatch')
        log=(folder/SIM/'simulate.log').read_text()
        result[mode]={'sticky':witness(log),'final_commit':final_witness(log)}
    return result

def route(root):
    verify_pair(root)
    return run(root/'sim-v1',root/'synth-v1',root/'route-v1',root/'ack-v1')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('--route',action='store_true')
    args=parser.parse_args()
    print(json.dumps(route(args.root) if args.route else verify_pair(args.root),indent=2))

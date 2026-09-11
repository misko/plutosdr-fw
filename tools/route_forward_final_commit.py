"""Require exact same-edge commit witnesses before routing the frozen pair."""
import argparse
import json
from pathlib import Path
import re
import sys
from staged_fft_experiment import ROOT, verify, require, audit_parallel_ready
from route_starlink_staged_fft import verify_ack_auxiliary, run

PIN='cb90644fc6c252e7a941bc57ef3c32c87f3b7b59d51d3b94c547114bee68c16a'
SIM=Path('project/staged_fft.sim/sim_1/behav/xsim')

def witness(text):
    rows=re.findall(r'^STAGED_FORWARD_FINAL_PASS checks=(\d+) accepts=(\d+) exact_current=1 inverse_unchanged=1$',text,re.M)
    require(len(rows)==1 and text.count('STAGED_FORWARD_FINAL_PASS')==1,'one complete forward-final witness required')
    checks,accepts=map(int,rows[0])
    require(checks>=1000 and accepts>=18,'forward-final coverage incomplete')
    return {'checks':checks,'accepts':accepts,'exact_current':True,'inverse_unchanged':True}

def verify_pair(root):
    prepared=root/'prepared-v1';verify(prepared,PIN)
    sys.path.insert(0,str(ROOT))
    from tests.test_starlink_forward_final_commit import test_exact_one_guard_delta, undo_guard, undo_bench, PARENT, GUARD
    test_exact_one_guard_delta()
    require(undo_guard((prepared/GUARD).read_text())==(PARENT/GUARD).read_text(),'prepared guard delta')
    require(undo_bench((prepared/'tb_fft_staged_output.sv').read_text())==(PARENT/'tb_fft_staged_output.sv').read_text(),'prepared bench delta')
    main=audit_parallel_ready(root/'sim-v1')
    aux=verify_ack_auxiliary(root/'ack-v1',PIN,prepared)
    result={}
    for mode,audited in [('sim',main),('ack',aux)]:
        folder=root/(mode+'-v1')
        outcome=json.loads((folder/'outcome.json').read_text())
        require(outcome.get('mode')==mode and outcome.get('returncode')==0 and outcome.get('sources_unchanged') is True and 'error' not in outcome,'successful actual run required')
        require(outcome['prepared_sha']==PIN and outcome['command'][-3]==str(prepared),'same frozen actual source')
        require(json.dumps(audited,sort_keys=True)==json.dumps(outcome['audit'],sort_keys=True),'actual re-audit mismatch')
        result[mode]=witness((folder/SIM/'simulate.log').read_text())
    return result

def route(root):
    verify_pair(root)
    return run(root/'sim-v1',root/'synth-v1',root/'route-v1',root/'ack-v1')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('--route',action='store_true')
    args=parser.parse_args()
    print(json.dumps(route(args.root) if args.route else verify_pair(args.root),indent=2))

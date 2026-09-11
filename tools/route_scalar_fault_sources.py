"""Route the flat cause expression only with the retained scalar-fault proof."""
import argparse
import json
from pathlib import Path
import re
import sys
from staged_fft_experiment import ROOT, verify, require, audit_parallel_ready
from route_starlink_staged_fft import verify_ack_auxiliary, run
from route_forward_final_commit import witness as final_witness

PIN='b7a4a2bc1d143a8d30d0207261de5a73dfc989550c30d65082bfc63f8e57abeb'
SIM=Path('project/staged_fft.sim/sim_1/behav/xsim')

from route_distributed_sticky_fault import witness

def verify_pair(root):
    prepared=root/'prepared-v1';verify(prepared,PIN)
    sys.path.insert(0,str(ROOT))
    from tests.test_starlink_scalar_fault_sources import test_exact_scalar_register_delta, undo_top, PARENT, TOP
    test_exact_scalar_register_delta()
    require(undo_top((prepared/TOP).read_text())==(PARENT/TOP).read_text(),'prepared top delta')
    require((prepared/'tb_fft_staged_output.sv').read_bytes()==(PARENT/'tb_fft_staged_output.sv').read_bytes(),'unchanged prepared bench')
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

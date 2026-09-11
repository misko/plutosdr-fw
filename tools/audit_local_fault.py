"""Re-audit frozen local-fault runs after correcting the v1 marker regex.

The v1 runner/source stays unchanged; failed receipts are never overwritten.
This audit is not another simulation.
"""
import argparse
import json
from pathlib import Path
import re
import local_fault_experiment as experiment
from staged_fft_experiment import sha,require,verify


def witness(log,auxiliary=False):
    require(not re.search(r'FATAL|ERROR|FAIL',log,re.I),'local fault simulator failure')
    rows=re.findall(r'^LOCAL_FAULT_PASS checks=(\d+) delayed_edges=(\d+) pending_checks=(\d+) exact_sources=1 bounded_abort=1 publication_fenced=1$',log,re.M)
    require(len(rows)==1 and log.count('LOCAL_FAULT_PASS')==1,'one local fault witness')
    checks,delays,pending=map(int,rows[0])
    require(checks>=10000,'nonvacuous local fault observer')
    if auxiliary:
        cases=re.findall(r'^LOCAL_FAULT_BOUNDARY_PASS boundary=(\d+) new_publications=0 fresh_reads=512 fresh_releases=1$',log,re.M)
        require(cases==list(map(str,range(6))),'six actual delayed-fault boundaries')
        require(log.count('LOCAL_FAULT_BOUNDARIES_PASS cases=6 delayed_fault_exercised=1 fresh_recovery=1')==1,'one local boundary terminal')
        require(delays>=6 and pending>=6,'delayed global fault exercised')
    else:require(delays==pending==0,'healthy main unexpectedly faulted')
    return dict(checks=checks,delayed_edges=delays,pending_checks=pending,auxiliary=auxiliary)

def audit(root,auxiliary=False):
    outcome=json.loads((root/'outcome.json').read_text())
    require(outcome.get('passed') is True and outcome.get('returncode')==0 and outcome.get('mode')=='sim','successful actual simulation')
    verify(Path(outcome['command'][-3]),outcome['prepared_sha'])
    numerical=experiment.base.base.main.audit(root)
    require(json.dumps(numerical,sort_keys=True)==json.dumps(outcome['audit'],sort_keys=True),'fresh numerical audit')
    logpath=root/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log'
    log=logpath.read_text()
    local=witness(log,auxiliary)
    registered=experiment.base.witness(log,auxiliary)
    identity=experiment.base.base.witness(log)
    if auxiliary:
        experiment.base.old_boundaries.witness(log)
        experiment.base.base.auxiliary.witness(log)
    result={'passed':True,'local_fault':local,'registered_abort':registered,
            'output_identity':identity,'numerical':numerical,'new_simulation':False,
            'prepared_sha':outcome['prepared_sha'],'log_sha256':sha(logpath),
            'v1_receipt_sha256':sha(root/'local_fault_outcome.json'),
            'audit_source_sha256':sha(Path(__file__).resolve())}
    path=root/'local_fault_audit_v2.json'
    require(not path.exists(),'no audit overwrite')
    path.write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('root',type=Path)
    parser.add_argument('--auxiliary',action='store_true')
    args=parser.parse_args()
    print(json.dumps(audit(args.root,args.auxiliary),indent=2))

"""Route current publication factoring only after actual source-matched verification."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import buffered_forward_experiment as main
import buffered_forward_auxiliary as auxiliary
import output_identity_experiment as identity
import output_identity_boundaries as boundaries
import registered_abort_experiment as abort
import product_current_fence_experiment as fence
import balanced_forward_identity_experiment as balanced
import forward_private_status_experiment as private_status
import parallel_product_identity_experiment as parallel
import product_retirement_receipt_experiment as retirement
import private_forward_descriptor_experiment as descriptor
import output_retirement_receipt_experiment_v5 as out_retirement
import private_replay_sequence_experiment_v3 as publication
from staged_fft_experiment import sha, verify, require, fresh

def inherited_evidence(actual,synthesis,aux):
    outcomes=[json.loads((p/'outcome.json').read_text()) for p in [actual,synthesis,aux]]
    for result,mode in zip(outcomes,['sim','synth','sim']):
        require(result.get('passed') is True and result.get('returncode')==0 and result['mode']==mode and 'error' not in result,'successful actual/synthesis evidence')
        verify(Path(result['command'][-3]),result['prepared_sha'])
    a,s,x=outcomes
    require(a['prepared_sha']==s['prepared_sha'] and a['command'][-3]==s['command'][-3],'main/synthesis exact source match')
    prepared=Path(a['command'][-3]);aux_prepared=Path(x['command'][-3])
    names=re.search(r'set runtime_names \{([^}]+)\}',(prepared/'profile.tcl').read_text())[1].split()
    require(len(names)==47 and (prepared/'profile.tcl').read_bytes()==(aux_prepared/'profile.tcl').read_bytes(),'exact runtime profiles')
    require(all((prepared/n).read_bytes()==(aux_prepared/n).read_bytes() for n in names),'auxiliary runtime matches routed design')
    for folder,result in [(actual,a),(aux,x)]:
        require(json.dumps(main.audit(folder),sort_keys=True)==json.dumps(result['audit'],sort_keys=True),'fresh numerical re-audit')
    extra=auxiliary.witness((aux/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text())
    saved=json.loads((aux/'auxiliary_outcome.json').read_text())
    require(saved.get('passed') is True and saved.get('auxiliary')==extra,'complete auxiliary proof')
    require(sha(synthesis/'staged_output_synth.dcp')==s['dcp_sha256'],'synthesis checkpoint identity')
    identity_evidence={}
    for folder in [actual,aux]:
        log=(folder/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
        receipt=json.loads((folder/'identity_outcome.json').read_text())
        identity_evidence[folder.name]=identity.witness(log)
        require(receipt.get('passed') is True and receipt.get('output_identity')==identity_evidence[folder.name],'actual output-word identity comparison')
    boundary_evidence=boundaries.witness((aux/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text())
    boundary_receipt=json.loads((aux/'boundary_outcome.json').read_text())
    require(boundary_receipt.get('passed') is True and boundary_receipt.get('output_boundaries')==boundary_evidence,'output publication cancellation proof')
    abort_evidence={}
    for folder,is_auxiliary in [(actual,False),(aux,True)]:
        log=(folder/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
        receipt=json.loads((folder/'abort_outcome.json').read_text())
        abort_evidence[folder.name]=abort.witness(log,is_auxiliary)
        require(receipt.get('passed') is True and receipt.get('registered_abort')==abort_evidence[folder.name],'registered abort publication and recovery proof')
    fence_evidence={}
    for folder,is_auxiliary in [(actual,False),(aux,True)]:
        log=(folder/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
        receipt=json.loads((folder/'product_fence_outcome.json').read_text())
        fence_evidence[folder.name]=fence.witness(log,is_auxiliary)
        require(receipt.get('passed') is True and receipt.get('product_current_fence')==fence_evidence[folder.name],'complete current product-fault publication proof')
    balanced_evidence={}
    for folder in [actual,aux]:
        log=(folder/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
        receipt=json.loads((folder/'balanced_identity_outcome.json').read_text())
        balanced_evidence[folder.name]=balanced.witness(log)
        require(receipt.get('passed') is True and receipt.get('balanced_forward_identity')==balanced_evidence[folder.name],'exact current bank identity proof')
    private_evidence={}
    for folder,is_auxiliary in [(actual,False),(aux,True)]:
        log=(folder/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
        receipt=json.loads((folder/'private_status_outcome.json').read_text())
        private_evidence[folder.name]=private_status.witness(log,is_auxiliary)
        require(receipt.get('passed') is True and receipt.get('forward_private_status')==private_evidence[folder.name],'current publication and registered private-status proof')
    parallel_evidence={}
    for folder in [actual,aux]:
        log=(folder/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
        receipt=json.loads((folder/'parallel_identity_outcome.json').read_text())
        parallel_evidence[folder.name]=parallel.witness(log)
        require(receipt.get('passed') is True and receipt.get('parallel_product_identity')==parallel_evidence[folder.name],'parallel comparison and same-edge certificate proof')
    retirement_evidence={}
    for folder,is_auxiliary in [(actual,False),(aux,True)]:
        log=(folder/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
        receipt=json.loads((folder/'retirement_outcome.json').read_text())
        retirement_evidence[folder.name]=retirement.witness(log,is_auxiliary)
        require(receipt.get('passed') is True and receipt.get('product_retirement_receipt')==retirement_evidence[folder.name],'registered retirement and actual publication proof')
    descriptor_evidence={}
    for folder,is_auxiliary in [(actual,False),(aux,True)]:
        log=(folder/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
        receipt=json.loads((folder/'private_descriptor_outcome.json').read_text())
        descriptor_evidence[folder.name]=descriptor.witness(log,is_auxiliary)
        require(receipt.get('passed') is True and receipt.get('private_forward_descriptor')==descriptor_evidence[folder.name],'private descriptor bank reference and quarantine proof')
    output_retirement_evidence={}
    for folder,is_auxiliary in [(actual,False),(aux,True)]:
        log=(folder/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
        receipt=json.loads((folder/'output_retirement_outcome.json').read_text())
        output_retirement_evidence[folder.name]=out_retirement.witness(log,is_auxiliary)
        require(receipt.get('passed') is True and receipt.get('output_retirement_receipt')==output_retirement_evidence[folder.name],'output receipt retirement and current publication proof')
    publication_evidence={}
    for folder,is_auxiliary in [(actual,False),(aux,True)]:
        log=(folder/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
        receipt=json.loads((folder/'private_replay_outcome.json').read_text())
        publication_evidence[folder.name]=publication.witness(log,is_auxiliary)
        require(receipt.get('passed') is True and receipt.get('private_replay_sequence')==publication_evidence[folder.name],'exact current publication cone and actual recovery proof')
    return {'private_replay_sequence':publication_evidence,'output_retirement_receipt':output_retirement_evidence,'private_forward_descriptor':descriptor_evidence,'product_retirement_receipt':retirement_evidence,'parallel_product_identity':parallel_evidence,'forward_private_status':private_evidence,'balanced_forward_identity':balanced_evidence,'product_current_fence':fence_evidence,'registered_abort':abort_evidence,'output_identity':identity_evidence,'output_boundaries':boundary_evidence,'main':a['audit'],'auxiliary':extra,'prepared':str(prepared),'prepared_sha':a['prepared_sha'],
            'aux_prepared':str(aux_prepared),'aux_prepared_sha':x['prepared_sha']}

import replay_local_fault_experiment_v2 as partition

def evidence(actual,synthesis,aux):
    result=inherited_evidence(actual,synthesis,aux)
    proof={}
    for folder,is_auxiliary in [(actual,False),(aux,True)]:
        receipt=json.loads((folder/'replay_local_fault_outcome.json').read_text())
        require(receipt.get('passed') is True,'terminal partition qualification')
        log=(folder/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
        proof[folder.name]=partition.witness(log,is_auxiliary)
        require(proof[folder.name]==receipt['replay_local_fault'],'fresh cancellation partition audit')
    result.update(replay_local_fault=proof,runtime_modules=47,auxiliary_cases=82,
        receiver_integrated=False,deployment_eligible=False)
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ['actual','synthesis','auxiliary','output']:parser.add_argument(name,type=Path)
    args=parser.parse_args()
    result=evidence(args.actual,args.synthesis,args.auxiliary)
    with args.output.open('x') as output:output.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

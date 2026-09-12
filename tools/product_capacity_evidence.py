"""Fresh actual arithmetic, changed handshake and all retained functional gates."""
import argparse
import json
from pathlib import Path
import re
from staged_fft_experiment import sha,verify,require
import product_registered_capacity_experiment_v2 as experiment
import buffered_forward_experiment as actual

def evidence(main,synth,aux):
    receipts=[json.loads((p/'product_capacity_outcome.json').read_text()) for p in [main,synth,aux]]
    a,s,x=receipts
    for receipt,mode in zip(receipts,['sim','synth','sim']):
        require(receipt.get('passed') is True and receipt.get('returncode')==0 and receipt['mode']==mode,'terminal qualified actual/synth')
        verify(Path(receipt['command'][-3]),receipt['prepared_sha'])
    require(a['prepared_sha']==s['prepared_sha'] and a['command'][-3]==s['command'][-3],'identical main/synthesis snapshot')
    prepared=Path(a['command'][-3]);aux_prepared=Path(x['command'][-3])
    profile=(prepared/'profile.tcl').read_bytes()
    require(profile==(aux_prepared/'profile.tcl').read_bytes(),'same runtime profile')
    names=re.search(r'set runtime_names \{([^}]+)\}',profile.decode())[1].split()
    require(len(names)==43 and all((prepared/n).read_bytes()==(aux_prepared/n).read_bytes() for n in names),'43 identical main/aux runtime modules')
    require(sha(synth/'staged_output_synth.dcp')==s['dcp_sha256'],'synthesis checkpoint identity')
    checked={}
    for folder,receipt,is_aux in [(main,a,False),(aux,x,True)]:
        numerical=actual.audit(folder)
        require(json.dumps(numerical,sort_keys=True)==json.dumps(receipt['audit'],sort_keys=True),'fresh independent numerical audit')
        log=(folder/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
        proof=experiment.qualification(log,is_aux)
        require(all(receipt.get(k)==v for k,v in proof.items()),'fresh complete functional qualification')
        checked[folder.name]=dict(numerical=numerical,proof=proof)
    return dict(checked=checked,runtime_modules=43,prepared=str(prepared),prepared_sha=a['prepared_sha'],
        aux_prepared=str(aux_prepared),aux_prepared_sha=x['prepared_sha'],synthesis_sha=s['dcp_sha256'],
        inherited_auxiliary_cases=82,changed_contract='no same-edge product refill; corruption injected at actual acceptance',
        continuous_rx=False,full_receiver_signoff=False,deployment_eligible=False)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ['actual','synthesis','auxiliary','output']:parser.add_argument(name,type=Path)
    args=parser.parse_args();result=evidence(args.actual,args.synthesis,args.auxiliary)
    with args.output.open('x') as output:output.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

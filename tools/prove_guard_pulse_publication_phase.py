"""Prove only a prospective phase simplification, not a new runtime or timing pass."""
import argparse
import json
from pathlib import Path
import subprocess
import time
from staged_fft_experiment import require,sha,fresh
ROOT=Path(__file__).resolve().parents[1]
TOP=ROOT/'hdl/library/starlink_pss_acquisition/staged_control/starlink_pss_fft_guard_pulse_impl.v'
BENCH=r"""
module tb;
reg preparing,fast_running,other_fault;
reg[5:0]events;
wire[5:0]preflight_events_now=fast_running && preparing ? events : 6'b0;
wire preparation_fault_now=|preflight_events_now;
wire old_accept=!preparing && !(other_fault || preparation_fault_now);
wire new_accept=__NEW__;
function four(input integer n);
case(n&3)0:four=0;1:four=1;2:four=1'bx;3:four=1'bz;endcase
endfunction
integer n,b,active_faults=0;
initial begin
 for(n=0;n<262144;n=n+1)begin
  preparing=four(n);fast_running=four(n>>2);other_fault=four(n>>4);
  for(b=0;b<6;b=b+1)events[b]=four(n>>(6+2*b));
  #1;
  if(old_accept!==new_accept)$fatal(1,"phase equivalence differs n=%0d",n);
  if(preparing===1 && preparation_fault_now===1)begin
   if(new_accept!==0)$fatal(1,"preflight permitted publication");
   active_faults=active_faults+1;
  end
 end
 if(active_faults==0)$fatal(1,"vacuous active preflight");
 $display("PUBLICATION_PHASE_PROOF_PASS vectors=262144 active_faults=%0d",active_faults);$finish;
end
endmodule
"""
def run(output):
    source=TOP.read_text()
    event=source.split('wire [5:0] preflight_events_now =',1)[1].split(';',1)[0]
    require(event.strip().startswith('REGISTERED_SCHEDULING && fast_running && preparing ?') and event.strip().endswith(": 6'b0"),'original phase-gated events')
    require('wire preparation_fault_now = |preflight_events_now;' in source,'literal fault reduction')
    context=source.split('wire replay_publication_context =',1)[1].split(';',1)[0]
    require('!preparing' in context,'publication requires inactive preflight')
    require('replay_publication_context && !replay_publication_fault;' in source,'actual quiet authorization composition')
    fault=source.split('wire replay_publication_fault =',1)[1].split(';',1)[0]
    require('preparation_fault_now' in fault,'current runtime still has the term')
    before={str(p):sha(p) for p in [TOP,Path(__file__).resolve()]}
    fresh(output);started=time.time();runs={}
    for name,expr in [('proof','!preparing && !other_fault'),
                      ('missing_context','!other_fault'),
                      ('missing_other_fault','!preparing')]:
        directory=output/name;directory.mkdir()
        bench=directory/'tb.sv';bench.write_text(BENCH.replace('__NEW__',expr))
        result=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(directory/'sim'),str(bench)],capture_output=True,text=True,timeout=30)
        (directory/'compile.log').write_text(result.stdout+result.stderr)
        require(result.returncode==0,'phase proof compilation')
        result=subprocess.run(['vvp',str(directory/'sim')],capture_output=True,text=True,timeout=60)
        (directory/'simulate.log').write_text(result.stdout+result.stderr)
        if name=='proof':require(result.returncode==0 and 'PUBLICATION_PHASE_PROOF_PASS vectors=262144' in result.stdout,'complete four-state proof')
        else:require(result.returncode!=0 and 'phase equivalence differs' in result.stdout,'unsafe phase mutant rejected')
        runs[name]=dict(returncode=result.returncode,log_sha256=sha(directory/'simulate.log'))
    require(before=={p:sha(Path(p)) for p in before},'proof inputs unchanged')
    receipt=dict(passed=True,prospective_only=True,runtime_changed=False,
        deployment_eligible=False,vectors=262144,before=before,runs=runs,
        elapsed=time.time()-started,sources_unchanged=True)
    (output/'outcome.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path)
    print(json.dumps(run(parser.parse_args().output),indent=2))

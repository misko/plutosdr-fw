"""Read-only actual-FFT reproduction of the late product status boundary.

This is a diagnostic experiment, not a passing functional or release gate.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import local_fault_experiment as candidate
import registered_abort_experiment as parent
from staged_fft_experiment import sha,verify,require,fresh

PROBE='''    auxiliary_active=1;mode=0;
    aux_reset;aux_ready=0;aux_send;
    while(!dut.staged_product_valid || !dut.staged_product_last || !dut.staged_product_ready)@(negedge fft_clk);
    $display("STATUS_PROBE_BEFORE request=%b committed=%b accept=%b position=%d last=%b",dut.product_bank.owner_request,
      dut.forward_committed,dut.product_bank.input_accept,dut.staged_product_position,dut.staged_product_last);
    aux_fault_expected=1;force dut.core_status_valid=1'b1;force dut.core_status_data=8'h80;
    #0.001;
    $display("STATUS_PROBE_CURRENT global=%b guard=%b current=%b external=%b vendor=%b commit=%b accept=%b request=%b",
      dut.fast_fault,dut.result_fault,dut.common_current_fault,dut.external_fault_now,dut.vendor_fault_now,
      dut.product_commit_authorized,dut.product_bank.input_accept,dut.product_bank.owner_request);
    @(posedge fft_clk);#0.001;
    $display("STATUS_PROBE_EDGE global=%b guard=%b commit=%b request=%b output=%b",dut.fast_fault,dut.result_fault,
      dut.product_commit_authorized,dut.product_bank.owner_request,output_valid);
    @(negedge fft_clk);release dut.core_status_valid;release dut.core_status_data;
    repeat(12)@(negedge fft_clk);
    $display("STATUS_PROBE_SETTLED global=%b fault=%b reads=%d releases=%d output=%b",dut.fast_fault,fault,aux_reads,aux_releases,output_valid);
    $fclose(log_file);$display("STATUS_PROBE_COMPLETE diagnostic_only=1");$finish;
'''

def prepare(path,use_candidate):
    (candidate if use_candidate else parent).prepare(path,True)
    manifest=json.loads((path/'snapshot.json').read_text())
    bench=path/'tb_fft_buffered_forward.sv';text=bench.read_text()
    start=text.index('    for(mode=0;mode<6;mode=mode+1)begin')
    end=text.index('  end\n  initial begin #',start)
    bench.write_text(text[:start]+PROBE+text[end:])
    source=Path(__file__).resolve();shutil.copyfile(source,path/source.name)
    manifest['sources'][str(source)]=sha(source)
    manifest['experiment']['diagnostic_product_status']=True
    manifest['files']={p.name:sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name,value in sorted(files.items())))
    pin=sha(path/'SHA256SUMS');verify(path,pin)
    return pin

def run(prepared,pin,output):
    verify(prepared,pin);fresh(output)
    command=['/opt/Xilinx/Vivado/2022.2/bin/vivado','-mode','batch','-nojournal','-log',str(output/'vivado.log'),
        '-source',str(prepared/'buffered_forward_experiment.tcl'),'-tclargs','sim',str(prepared),pin,str(output)]
    env=dict(os.environ)
    for key in ['PYTHONHOME','PYTHONPATH','PYTHONOPTIMIZE','LD_LIBRARY_PATH']:env.pop(key,None)
    env.update(LD_LIBRARY_PATH='/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE',TMPDIR=str(output))
    result=dict(command=command,prepared_sha=pin,diagnostic_only=True,started=time.time())
    (output/'command.json').write_text(json.dumps(result,indent=2)+'\n')
    with (output/'stdout.log').open('w') as log:
        process=subprocess.Popen(command,cwd=output,env=env,stdout=log,stderr=subprocess.STDOUT)
        (output/'process.json').write_text(json.dumps({'pid':process.pid})+'\n')
        result['returncode']=process.wait()
    verify(prepared,pin)
    log=(output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
    result['completed']=result['returncode']==0 and 'STATUS_PROBE_COMPLETE diagnostic_only=1' in log and 'Fatal:' not in log
    result['observations']=[line for line in log.splitlines() if line.startswith('STATUS_PROBE_')]
    result['elapsed']=time.time()-result['started']
    (output/'outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    require(result['completed'],'diagnostic did not complete')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('output',type=Path);p.add_argument('--candidate',action='store_true')
    p=sub.add_parser('run');p.add_argument('prepared',type=Path);p.add_argument('pin');p.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output,args.candidate) if args.command=='prepare' else run(args.prepared,args.pin,args.output),indent=2))

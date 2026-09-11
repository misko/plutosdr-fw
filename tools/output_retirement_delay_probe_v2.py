"""Focused actual-FFT diagnosis; never a replacement for the full campaign."""
import argparse
import json
from pathlib import Path
import shutil
import output_retirement_receipt_experiment_v2 as experiment
import buffered_forward_experiment as actual
from staged_fft_experiment import sha,require,verify

def prepare(path,parent=False):
    experiment.prepare(path,True)
    bench=(path/'tb_fft_buffered_forward.sv').read_text()
    require(bench.count('    run_buffered_auxiliary;')==1,'one full campaign call')
    bench=bench.replace('    run_buffered_auxiliary;','    auxiliary_active=1;output_retirement_boundary(0);',1)
    marker="        force dut.output_replay_accept=1'b0;"
    require(bench.count(marker)==1,'one delayed-publication injection')
    bench=bench.replace(marker,marker+'\n        delay_probe_active=1;#0.001;delay_probe_trace;',1)
    observer='''
  reg delay_probe_active=0;
  task automatic delay_probe_trace;
    begin
      $display("DELAY_PROBE time=%0t state=%0d ext=%b in_now=%b in_guard=%b slow=%b vendor=%b fast=%b kernel=%b overflow=%b product_bank=%b product_frame=%b handoff=%b cutover=%b cutover_reasons=%h retained=%b retained_reasons=%h out_ram=%b out_stage=%b out_frame=%b output_control=%b replay=%b descriptor=%b bank_ready=%b output_request=%b ack=%b",
        $time,dut.state,dut.external_fault_now,dut.input_fault_now,dut.input_guard_fault,dut.slow_faults_fast,
        dut.vendor_fault_now,dut.fast_fault,dut.kernel_fault,dut.product_overflow,dut.product_bank_fault,
        dut.product_bank_framing_fault_now,dut.handoff_fault_now,dut.cutover_fault_now,dut.cutover_reasons,
        dut.retained_fault_now,dut.retained_reasons,dut.output_bank_ram_fault,dut.output_stage_fault,
        dut.output_bank_framing_fault_now,dut.output_control.fault,dut.output_replay_valid,
        dut.output_descriptor_valid,dut.output_bank_ready,dut.output_request,dut.output_ack_sync);
    end
  endtask
  always @(negedge fft_clk)begin
    #0.002;if(delay_probe_active)delay_probe_trace;
  end
'''
    bench=bench.replace('\nendmodule','\n'+observer+'\nendmodule',1)
    if parent:
        require(bench.count(experiment.NEW+' #(')==1,'one diagnostic DUT')
        bench=bench.replace(experiment.NEW+' #(',experiment.base.NEW+' #(',1)
        original=(experiment.RTL/'output_retirement_receipt_observer.svh').read_text()
        require(bench.count(original)==1,'one output-only observer')
        bench=bench.replace(original,'',1).replace('    report_output_retirement_receipt;\n','',1)
        bench=bench.replace('dut.output_published_receipt',"((dut.output_request ^ dut.output_ack_sync) === 1'b1)")
        bench=bench.replace('dut.output_retire_ready','dut.output_stage_consume')
    (path/'tb_fft_buffered_forward.sv').write_text(bench)
    source=Path(__file__).resolve();shutil.copyfile(source,path/source.name)
    manifest=json.loads((path/'snapshot.json').read_text())
    manifest['sources'][str(source)]=sha(source)
    manifest['experiment']['focused_delay_diagnostic_not_qualification']=True
    manifest['files']={p.name:sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name,value in sorted(files.items())))
    pin=sha(path/'SHA256SUMS');verify(path,pin)
    return {'prepared':str(path),'sha256sums':pin,'qualification':False,'parent':parent}

if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('path',type=Path);p.add_argument('--parent',action='store_true')
    p=sub.add_parser('run');p.add_argument('path',type=Path);p.add_argument('pin');p.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.path,args.parent) if args.command=='prepare' else actual.run('sim',args.path,args.pin,args.output),indent=2))

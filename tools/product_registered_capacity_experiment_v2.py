"""Local product-slot capacity: measured bubble, unchanged publication gates."""
import argparse
import json
from pathlib import Path
import re
import shutil
import private_replay_sequence_experiment_v3 as base
import product_registered_capacity_transform as transform
import route_private_replay_sequence as proofs
import buffered_forward_experiment as actual
from staged_fft_experiment import sha,require,verify
RTL=base.RTL
NEW='starlink_pss_fft_product_registered_capacity_impl'
BANK='starlink_pss_product_identity_registered_capacity'
PARENT=Path('/dev/shm/starlink-private-replay.if3LELsS/prepared-v1')
PIN='7d38b9f58dee6e017d67415161ffb79d77cc16a1b0a59578751f54c79df2acc4'

def qualify_corruption_edge(bench):
    old='      else if(which==2)while(!dut.guard_commit[0])@(negedge fft_clk);'
    new=old+"""
      else if(which==3)while(!(dut.joiner.input_valid && dut.kernel_ready && dut.forward_buffer_position==100))@(negedge fft_clk);"""
    require(bench.count(old)==1,'one inherited replay corruption trigger')
    bench=bench.replace(old,new,1)
    old="        3:force dut.forward_buffer_position=9'd0;"
    new="""        3:begin
          if(dut.joiner.kernel_rom.input_accept!==1 || dut.joiner.input_bin_index!==100)
            $fatal(1,"corruption injection missed original acceptance edge");
          force dut.forward_buffer_position=9'd0;
          #0.001;
          if(dut.joiner.input_valid!==1 || dut.kernel_ready!==1 || dut.joiner.input_bin_index!==0)
            $fatal(1,"corruption did not reach accepting kernel interface");
          $display("PRODUCT_CAPACITY_CORRUPTION_OFFER accepted_edge=1 original_position=100 corrupted_position=0");
        end"""
    require(bench.count(old)==1,'one inherited corruption force')
    return bench.replace(old,new,1)


def prepare(path,auxiliary=False):
    require(sha(PARENT/'SHA256SUMS')==PIN,'lean private replay parent pin')
    for old,new,changes in [(base.NEW+'.v',NEW+'.v',transform.TOP_CHANGES),
        ('starlink_pss_product_identity_parallel_reference.v',BANK+'.v',transform.BANK_CHANGES),
        ('parallel_product_identity_observer.svh','product_registered_capacity_observer.svh',transform.OBSERVER_CHANGES)]:
        require(transform.transform((RTL/old).read_text(),changes)==(RTL/new).read_text(),'exact registered capacity delta')
    base.prepare(path,auxiliary)
    manifest=json.loads((path/'snapshot.json').read_text());profile=(path/'profile.tcl').read_text()
    names=re.search(r'set runtime_names \{([^}]+)\}',profile)[1].split()
    require(len(names)==41 and all((path/n).read_bytes()==(PARENT/n).read_bytes() for n in names),'41 parent runtime modules unchanged')
    (path/'profile.tcl').write_text(profile.replace('set runtime_names {','set runtime_names {'+NEW+'.v '+BANK+'.v ',1))
    for source in [RTL/(NEW+'.v'),RTL/(BANK+'.v'),RTL/'product_registered_capacity_observer.svh',Path(__file__).resolve(),Path(transform.__file__)]:
        shutil.copyfile(source,path/source.name);manifest['sources'][str(source)]=sha(source)
    bench=(path/'tb_fft_buffered_forward.sv').read_text()
    require(bench.count(base.NEW+' #(')==1,'one actual top')
    bench=bench.replace(base.NEW+' #(',NEW+' #(',1)
    old=(RTL/'parallel_product_identity_observer.svh').read_text()
    require(bench.count(old)==1,'one old refill comparison')
    bench=bench.replace(old,(RTL/'product_registered_capacity_observer.svh').read_text(),1)
    if auxiliary:bench=qualify_corruption_edge(bench)
    (path/'tb_fft_buffered_forward.sv').write_text(bench)
    tcl=(path/'buffered_forward_experiment.tcl').read_text()
    require(tcl.count('set_property top '+base.NEW+' ')==1,'synthesis top')
    (path/'buffered_forward_experiment.tcl').write_text(tcl.replace('set_property top '+base.NEW+' ','set_property top '+NEW+' ',1))
    manifest['experiment'].update(runtime_modules=43,parent_runtime_unchanged=41,registered_product_capacity=True,
        intended_handshake_change='No simultaneous nonfinal refill; downstream is elastic after full FFT capture/seal',
        observer_change='Require zero first-word refills and nonvacuous first retirement/capture; preserve exact comparator and publication checks')
    manifest['files']={p.name:sha(p) for p in path.iterdir() if p.is_file() and p.name not in {'snapshot.json','SHA256SUMS'}}
    (path/'snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files={**manifest['files'],'snapshot.json':sha(path/'snapshot.json')}
    (path/'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name,value in sorted(files.items())))
    pin=sha(path/'SHA256SUMS');verify(path,pin)
    return dict(prepared=str(path),sha256sums=pin,**manifest['experiment'])

def witness(log,auxiliary=False):
    require(not re.search(r'FATAL|ERROR|FAIL',log,re.I),'registered product capacity simulator failure')
    rows=re.findall(r'^REGISTERED_PRODUCT_CAPACITY_PASS checks=(\d+) captures=(\d+) first_refills=(\d+) first_retire=(\d+) first_capture=(\d+) four_state_exact=1 same_edge_capture=1$',log,re.M)
    require(len(rows)==1 and log.count('REGISTERED_PRODUCT_CAPACITY_PASS')==1,'one registered capacity witness')
    checks,captures,refills,retire,first=map(int,rows[0])
    require(checks>=10000 and captures>=9216 and retire>=18 and first>=18 and refills==0,'local capacity and exercised first-word reference')
    if not auxiliary:require(captures==9216 and retire==first==18,'healthy product inventory')
    return dict(checks=checks,captures=captures,first_refills=refills,first_retire=retire,first_capture=first,auxiliary=auxiliary)

def qualification(log,auxiliary=False):
    # Every inherited functional proof remains required except the deliberately
    # changed same-edge-refill coverage, replaced by witness() above.
    checked=dict(product_capacity=witness(log,auxiliary),output_identity=proofs.identity.witness(log),
        balanced_forward_identity=proofs.balanced.witness(log))
    for name,module in [('registered_abort',proofs.abort),('product_current_fence',proofs.fence),
        ('forward_private_status',proofs.private_status),('product_retirement_receipt',proofs.retirement),
        ('private_forward_descriptor',proofs.descriptor),('output_retirement_receipt',proofs.out_retirement),
        ('private_replay_sequence',proofs.publication)]:
        checked[name]=module.witness(log,auxiliary)
    if auxiliary:
        require(log.count('PRODUCT_CAPACITY_CORRUPTION_OFFER accepted_edge=1 original_position=100 corrupted_position=0')==1,'one accepted corruption injection')
        checked['auxiliary']=proofs.auxiliary.witness(log)
        checked['output_boundaries']=proofs.boundaries.witness(log)
    return checked

def run(mode,prepared,pin,output):
    result=actual.run('sim' if mode=='aux' else mode,prepared,pin,output)
    try:
        if mode!='synth':result.update(qualification((output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text(),mode=='aux'))
        result.update(qualification_scope='inherited functional gates plus explicit changed refill contract',deployment_eligible=False)
    except Exception as error:
        result.update(passed=False,product_capacity_error=repr(error));raise
    finally:(output/'product_capacity_outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('output',type=Path);p.add_argument('--auxiliary',action='store_true')
    p=sub.add_parser('run');p.add_argument('mode',choices=['sim','aux','synth']);p.add_argument('prepared',type=Path);p.add_argument('pin');p.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output,args.auxiliary) if args.command=='prepare' else run(args.mode,args.prepared,args.pin,args.output),indent=2))

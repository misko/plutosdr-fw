"""Full-dwell recorded-IQ RTL verification. No radio access or deployment claim."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools import starlink_coarse25 as base
from tools import starlink_coarse25_fixed as fixed


def summary(scores, first):
    totals=np.zeros(10000,dtype=np.int64)
    np.add.at(totals,(3*np.arange(len(scores)))%10000,scores)
    folded=np.roll(totals,1)+totals+np.roll(totals,-1)
    peak=int(np.argmax(folded))
    distance=base.circular_distance(np.arange(10000),peak,10000)
    background=folded[distance>150]
    total=sum(map(int,background)); squares=sum(int(v)**2 for v in background); n=len(background)
    delta=int(folded[peak])*n-total; variance=n*squares-total*total
    detected=int(delta>0 and delta*delta>=64*variance)
    return [first,peak,int(folded[peak]),total,squares,n,detected]


def run(output:Path, cases:list[str])->int:
    output.mkdir(parents=True,exist_ok=True)
    compiler,runner=shutil.which('iverilog'),shutil.which('vvp')
    if not compiler or not runner: raise RuntimeError('Icarus required')
    receipt_path=base.ROOT/'reports/coarse25-temporal-validation-20260912/result.json'
    receipt_bytes=receipt_path.read_bytes()
    items={item['case']:item for item in json.loads(receipt_bytes)['results']}
    lib=base.ROOT/'hdl/library/starlink_coarse25'
    sources=[lib/name for name in ('starlink_coarse25_mac.v','starlink_coarse25_score.v',
                                  'starlink_coarse25_datapath.v','starlink_coarse25_fold.v',
                                  'starlink_coarse25_detector.v')]
    sources.append(base.ROOT/'hdl/library/starlink_pss_acquisition/starlink_pss_score_divider.v')
    plan={'scope':'full recorded derivative dwell through RTL, not RF/IIO',
          'hardware_access':False,'source_receipt_sha256':base.digest(receipt_bytes),
          'cases':[items[case] for case in cases], 'numpy_version':np.__version__,
          'rtl_sha256':{str(p):base.digest(p.read_bytes()) for p in sources},
          'code_sha256':{str(Path(__file__)):base.digest(Path(__file__).read_bytes()),
                         str(Path(fixed.__file__)):base.digest(Path(fixed.__file__).read_bytes())},
          'coefficient_sha256':base.digest((lib/'coarse25_q15.mem').read_bytes()),
          'input_samples':300000,'clocks_per_sample':40,'groups':29,
          'expected_first_map_score_index':485,'map_scores':290000,
          'acceptance':'all integer map fields exact; positive detect and GLRT phase <=2 us; negatives no detect'}
    base.write_new(output/'plan.json',plan)
    tb=r'''
module tb;
 reg clk=0; always #5 clk=~clk;
 reg reset=1,valid=0;
 reg signed [15:0] xi=0,xq=0;
 reg [63:0] idx=0;
 wire initializing,fault,cv,detected;
 wire [63:0] first;
 wire [13:0] phase,n;
 wire [14:0] peak;
 wire [27:0] sum;
 wire [42:0] sumsq;
 reg [31:0] samples[0:299999];
 integer k;
 starlink_coarse25_detector dut(.clk(clk),.reset(reset),.sample_valid(valid),
 .sample_i(xi),.sample_q(xq),.sample_index(idx),.initializing(initializing),.fault(fault),
 .candidate_valid(cv),.detected(detected),.candidate_map_first_index(first),
 .candidate_phase(phase),.candidate_peak(peak),.candidate_background_sum(sum),
 .candidate_background_sumsq(sumsq),.candidate_background_count(n));
 always @(posedge clk) begin
  #1;
  if(fault) $fatal(1,"detector fault during full-rate replay");
  if(cv) $display("MAP %0d %0d %0d %0d %0d %0d %0d",first,phase,peak,sum,sumsq,n,detected);
 end
 initial begin
  $readmemh("input.mem",samples);
  repeat(3) @(negedge clk); reset=0;
  for(k=0;k<300000;k=k+1) begin
   {xq,xi}=samples[k]; idx=k; valid=1;
   @(negedge clk); valid=0;
   repeat(39) @(negedge clk);
  end
  repeat(40000) @(negedge clk);
  $finish;
 end
endmodule
'''
    (output/'tb.sv').write_text(tb)
    subprocess.run([compiler,'-g2012','-s','tb','-o',str(output/'sim'),
                    *map(str,sources),str(output/'tb.sv')],capture_output=True,check=True)
    results=[]
    for case in cases:
        item=items[case]
        iq_path=Path(item['iq_path'])
        payload=iq_path.read_bytes()
        if base.digest(payload)!=item['iq_sha256'] or len(payload)!=1200000:
            raise ValueError('recorded inspection bytes changed')
        iq=np.frombuffer(payload,dtype='<i2').reshape(-1,2)
        values=fixed.scores(iq)
        expected=summary(values[485:485+290000],485)
        directory=output/case; directory.mkdir()
        words=np.frombuffer(payload,dtype='<u4')
        (directory/'input.mem').write_text('\n'.join(f'{int(w):08x}' for w in words)+'\n')
        shutil.copyfile(lib/'coarse25_q15.mem',directory/'coarse25_q15.mem')
        started=time.monotonic()
        print(json.dumps({'case':case,'state':'running_full_120ms_rtl'}),flush=True)
        process=subprocess.run([runner,str(output/'sim')],cwd=directory,
                               capture_output=True,text=True,check=True,timeout=300)
        (directory/'simulation.log').write_text(process.stdout+process.stderr)
        actual=[list(map(int,line.split()[1:])) for line in process.stdout.splitlines()
                if line.startswith('MAP ')]
        exact=actual==[expected]
        phase_us=((item['first_canonical_center']+6*expected[0]+2*expected[1]
                   -base.TEMPLATE_FIRST_CENTER)%20000)/15
        difference=float(base.circular_distance(phase_us,item['glrt_phase_us'],4000/3))
        positive=case.startswith('positive')
        passed=exact and ((expected[-1]==1 and difference<=2) if positive else expected[-1]==0)
        entry={'case':case,'passed':passed,'integer_map_exact':exact,'expected':expected,'rtl':actual,
               'pss_phase_us':phase_us,'glrt_phase_difference_us':difference,
               'elapsed_seconds':time.monotonic()-started,'iq_sha256':item['iq_sha256']}
        results.append(entry)
        print(json.dumps(entry),flush=True)
    report={'plan_sha256':base.digest((output/'plan.json').read_bytes()),
            'passed':all(r['passed'] for r in results),'hardware_access':False,'results':results}
    base.write_new(output/'result.json',report)
    return 0 if report['passed'] else 2


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cases',nargs='+',choices=['positive_later_1','positive_later_2',
                        'negative_later_1','negative_later_2'],default=['positive_later_1','negative_later_1'])
    args=parser.parse_args()
    raise SystemExit(run(args.output.resolve(),args.cases))

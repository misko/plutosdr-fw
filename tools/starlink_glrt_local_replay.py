"""Autonomous full-grid RTL on pinned saved windows; no hardware or RF access."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--oracle-repo',type=Path,required=True,help='Independent numerical reference checkout, used only for verification')
parser.add_argument('--corpus',type=Path,required=True)
parser.add_argument('--roms',type=Path,required=True)
parser.add_argument('--pair',nargs=2,action='append',help='Two manifest window IDs; repeat for more pairs')
args=parser.parse_args()
HOST=args.oracle_repo.resolve()
FW=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HOST/'src'),str(FW)]
from leo.analysis.research.fixed_coarse_search import coarse_grid_ci16,retained_peaks
from leo.analysis.research.fixed_coarse_verification import acquire_fixed_ci16
from tests.starlink_glrt.test_local_search_rtl import BENCH

output=args.output.resolve()
corpus=args.corpus.resolve()
manifest=json.loads((corpus/'manifest.json').read_text())
windows={w['id']:w for w in manifest['windows']}
roms=args.roms.resolve()
rom_manifest=json.loads((roms/'manifest.json').read_text())
pairs=args.pair or [('source0-sample25000000','source0-sample32642991'),
       ('source0-sample117009806','source0-sample0'),('zero','noise-000')]
for pair in pairs:
    for identifier in pair:
        if identifier not in windows:parser.error(f'Unknown corpus window: {identifier}')
output.mkdir(exist_ok=False)
names=('local_search','coarse_search','coarse_window','coarse_mac6','coarse_norm','coarse_peaks',
       'verify_control','verify_window3','verify_mac3','verify_rotate3')
sources=[FW/f'hdl/library/starlink_glrt/starlink_glrt_{name}.v' for name in names]
tracked=[*sources,Path(__file__),FW/'tests/starlink_glrt/test_local_search_rtl.py',
         HOST/'src/leo/analysis/research/fixed_coarse_verification.py',
         HOST/'src/leo/analysis/research/fixed_coarse_search.py',corpus/'manifest.json',roms/'manifest.json',
         *(roms/name for name in rom_manifest['files'])]
digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
hashes={str(path):digest(path) for path in tracked}
snapshot=output/'source-snapshot';snapshot.mkdir()
for path in tracked:
    target=snapshot/path.name
    if target.exists() and target.read_bytes()!=path.read_bytes():
        target=snapshot/(path.parent.name+'-'+path.name)
    target.write_bytes(path.read_bytes())
for name,sha in rom_manifest['files'].items():
    assert digest(roms/name)==sha
    (snapshot/name).write_bytes((roms/name).read_bytes())
bench=BENCH.replace('.EPOCH_COUNT(64)','.EPOCH_COUNT(3333)')
bench=bench.replace('50000','250000').replace('64000','264000').replace('60000','260000')
bench=bench.replace('if(output_decision) decisions<=decisions+1;',
    'if(output_decision) begin decisions<=decisions+1;$display("DECISION_CYCLES %d %d",window_first_index,cycles);end')
for placeholder,name in (('COARSE','coarse_upper_q9.mem'),('COARSE_ENERGY','coarse_upper_energy.mem'),
                         ('PILOT','verify_upper_pilot_q9.mem'),('ENERGY','verify_upper_energy.mem'),('WAVE','verify_oscillator_q10.mem')):
    bench=bench.replace(f'"{placeholder}"',f'"{snapshot/name}"')
(output/'tb.sv').write_text(bench)
build=subprocess.run(['verilator','--binary','--timing','--top-module','tb','-Wno-fatal',
    '--Mdir',str(output/'obj'),'-o','sim','-j','4',str(output/'tb.sv'),*(str(snapshot/p.name) for p in sources)],
    capture_output=True,text=True,timeout=120)
(output/'build.log').write_text(build.stdout+build.stderr);build.check_returncode()
reason_bits={'no_acquisition_candidate':1,'insufficient_frame_support':2,'acquisition_score_below_minimum':4,
             'acquisition_margin_below_minimum':8,'acquisition_alias_or_transmitter_ambiguous':16}
results=[]
for pair_number,pair in enumerate(pairs):
    directory=output/f'pair-{pair_number}';directory.mkdir()
    inputs=[];expected=[];window_results=[]
    for index,identifier in enumerate(pair):
        entry=windows[identifier];path=corpus/entry['file']
        sha=digest(path);assert sha==entry['iq_sha256'];hashes[str(path)]=sha
        iq=np.fromfile(path,dtype='<i2').reshape(14000,2);inputs.append(iq)
        grid=coarse_grid_ci16(iq);candidates,reasons=acquire_fixed_ci16(iq,coarse_grid=grid)
        lookup={(c.epoch,c.coarse_cfo_hz):c for c in candidates}
        rows=[]
        for rank,(score,raw_epoch,cfo) in enumerate(retained_peaks(grid)):
            frequency=(cfo+400000)//80000
            epoch=raw_epoch-int(raw_epoch>0 and grid[frequency,raw_epoch-1]==score)
            c=lookup[(epoch,cfo)]
            rows.append([0,0,rank,epoch,frequency,score,c.cfo_hz//100,c.acquire_q16,c.verify_q16,
                         c.control_q16,c.conditioned_q16,c.frame_support])
        if rows:
            winner=candidates[0]
            row=next(r for r in rows if r[3]==winner.epoch and (r[4]-5)*80000==winner.coarse_cfo_hz)
            decision=[1,sum(reason_bits[r] for r in reasons),*row[2:]]
        else:decision=[1,1]+[0]*10
        rows.append(decision)
        expected.extend([[0x20000000000003+index*250000,*r] for r in rows])
        window_results.append({'id':identifier,'label':entry['label'],'iq_sha256':sha,
                               'candidate_count':len(candidates),'model_supported':not reasons,'reasons':list(reasons)})
    (directory/'iq.mem').write_text(''.join(f'{(int(i)&65535)|((int(q)&65535)<<16):08x}\n' for iq in inputs for i,q in iq))
    (directory/'expected.json').write_text(json.dumps(expected)+'\n')
    started=time.monotonic()
    run=subprocess.run([str(output/'obj/sim'),f'+INPUT={directory}/iq.mem','+GAP=0',
                        f'+OVERLAP={int(window_results[0]["candidate_count"]>0)}'],capture_output=True,text=True,timeout=120)
    (directory/'simulation.log').write_text(run.stdout+run.stderr);run.check_returncode()
    actual=[list(map(int,line.split()[1:])) for line in run.stdout.splitlines() if line.startswith('R ')]
    cycles=[list(map(int,line.split()[1:])) for line in run.stdout.splitlines() if line.startswith('DECISION_CYCLES ')]
    result={'windows':window_results,'output_records':len(actual),'expected_records':len(expected),
            'exact_match':actual==expected,'decision_cycles':cycles,'simulation_seconds':time.monotonic()-started}
    (directory/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True);results.append(result)
    assert 'PASS' in run.stdout and actual==expected
for name,sha in hashes.items():assert digest(Path(name))==sha
summary={'scope':'autonomous_full_grid_local_glrt_rtl_on_saved_iq_not_physical_radio',
         'window_count':len(pairs)*2,'cadence_ms':100,'clock_mhz':100,'sample_rate_hz':2500000,
         'coordinate_scope':'synthetic contiguous replay coordinates; capture IDs and IQ hashes identify original evidence',
         'exact_match':all(r['exact_match'] for r in results),'results':results,'sources':hashes}
(output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print('AUTONOMOUS_SAVED_RTL_PASS',flush=True)

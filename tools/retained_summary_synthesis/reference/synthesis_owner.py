"""Root-owned one-shot synthesis; immutable actual-qualified input, no route."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

root=Path(__file__).resolve().parent
assert len(sys.argv)==3
prepared=Path(sys.argv[1]);expected=sys.argv[2]
assert prepared.is_absolute() and '..' not in prepared.parts
assert not any(p.is_symlink() for p in (prepared,*prepared.parents))
output=root/'synthesis'
assert not output.exists() and not (root/'execution.json').exists()
python=Path('/home/mouse9911/.local/share/uv/python/cpython-3.11.16-linux-x86_64-gnu/bin/python3.11')
qualified=prepared/'qualified'
qualified_sha='7a9b32f10241d22c3f5a6d3967ca9841e2646bb94d714f4935c05f5e8d03635e'
cli=qualified/'source_snapshot/tools/prepare_starlink_retained_control_actual.py'
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(python)=='2874a0b9344d06b7767aebb1e6e25a759ffcbdb544e99400ecc74dc6092d1174'
assert sha(qualified/'manifest.json')==qualified_sha
assert sha(prepared/'SHA256SUMS')==expected
gate=json.loads((root/'preparation-gate.json').read_text())
assert gate['exit']==0 and gate['unchanged'] is True and gate['prepared_sha']==expected
assert gate['expected_tests']>0 and gate['counts']=={'tests':gate['expected_tests'],'failures':0,'errors':0,'skipped':0}
assert gate['runner_sha']==sha(prepared/'synthesize_retained_control.tcl')
assert gate['copier_sha']==sha(prepared/'prepare.py')
actual=root.parent/'retained-control-actual-parent.HbyLZ8I2'
actual_receipt=json.loads((actual/'outcome.json').read_text())
assert actual_receipt['vendor_exit']==0 and not actual_receipt['timed_out']
assert actual_receipt['original_check_exit']==actual_receipt['copied_check_exit']==0
assert actual_receipt['functional_accepted'] and actual_receipt['independent_result_exit']==0
assert json.loads((actual/'audit.json').read_text())['csv_sha256']=='07321b026a637e5922c56a84a955e58549056337198c952a9d73b1245cb4efaa'
assert json.loads((prepared/'actual_result.json').read_text())==json.loads((actual/'run/results.json').read_text())
assert sha(prepared/'clocks.xdc')=='bac30eff84cc71d1f273104b716b388b55e51d33be10f9beaf1901232193ba3f'
assert sha(prepared/'threads.tcl')=='aec974f2800f01285e888d1b188cd089534941922531914926a8e1b568d4c227'
pins={}
for line in (prepared/'SHA256SUMS').read_text().splitlines():
    digest,name=line.split('  ',1)
    assert name not in pins and not Path(name).is_absolute() and '..' not in Path(name).parts
    assert not (prepared/name).is_symlink()
    pins[name]=digest
assert {str(p.relative_to(prepared)) for p in prepared.rglob('*') if p.is_file()}==set(pins)|{'SHA256SUMS'}
assert all(sha(prepared/name)==digest for name,digest in pins.items())
(root/'input-pins.json').write_text(json.dumps(pins,indent=2))
env={k:v for k,v in os.environ.items() if k not in {'PYTHONHOME','PYTHONPATH','PYTHONOPTIMIZE','LD_LIBRARY_PATH'}}
def verify(path,logname):
    p=subprocess.run([str(python),'-B',str(cli),'verify',str(path),'--expected',qualified_sha,'--live'],
                     cwd='/',env=env,capture_output=True,text=True,timeout=30)
    (root/logname).write_text(p.stdout+p.stderr)
    return p.returncode
assert verify(qualified,'qualified-before.log')==0
env['LD_LIBRARY_PATH']='/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE'
cmd=['/opt/Xilinx/Vivado/2022.2/bin/vivado','-mode','batch','-notrace',
     '-log',str(root/'vivado.log'),'-journal',str(root/'vivado.jou'),
     '-source',str(prepared/'synthesize_retained_control.tcl'),'-tclargs',expected,str(output)]
(root/'command.json').write_text(json.dumps({'command':cmd,'cwd':str(root),'wall_limit_seconds':1200,
 'prepared_sha256':expected,'qualified_actual_manifest_sha256':qualified_sha,
 'kind':'ISOLATED_OOC_SYNTHESIS_ONLY_NOT_TIMING_OR_RECEIVER_QUALIFICATION'},indent=2))
started=time.monotonic();timed_out=False
with (root/'stdout.log').open('x') as out:
    process=subprocess.Popen(cmd,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
    (root/'process.json').write_text(json.dumps({'pid':process.pid,'process_group':process.pid}))
    print(f'Root synthesis process started; pid={process.pid}',flush=True)
    try:
        code=process.wait(timeout=1200)
    except subprocess.TimeoutExpired:
        timed_out=True
        os.killpg(process.pid,signal.SIGTERM)
        try: code=process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);code=process.wait(timeout=15)
env.pop('LD_LIBRARY_PATH',None)
changed=[name for name,digest in pins.items() if not (prepared/name).is_file() or sha(prepared/name)!=digest]
assert sha(prepared/'SHA256SUMS')==expected
original=verify(qualified,'qualified-after.log')
copied=verify(output/'inputs','copied-after.log') if (output/'inputs/manifest.json').is_file() else None
dcp=output/'retained_output_synth.dcp'
receipt={'vendor_exit':code,'timed_out':timed_out,'wall_seconds':time.monotonic()-started,
 'changed_prepared_files':changed,'qualified_source_check_exit':original,'copied_source_check_exit':copied,
 'dcp_sha256':sha(dcp) if dcp.is_file() else None,'physical_timing_qualified':False}
(root/'execution.json').write_text(json.dumps(receipt,indent=2))
print('\n'.join((root/'stdout.log').read_text().splitlines()[-25:]),flush=True)
print(json.dumps(receipt),flush=True)
assert code==0 and not timed_out and not changed and original==copied==0 and receipt['dcp_sha256'],receipt

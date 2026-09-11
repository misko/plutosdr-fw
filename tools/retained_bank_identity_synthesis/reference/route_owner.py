"""One diagnostic route of the independently audited retained synthesis DCP."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

root=Path(__file__).resolve().parent
assert len(sys.argv)==3
runner=Path(sys.argv[1]);runner_sha=sys.argv[2]
assert runner.is_absolute() and '..' not in runner.parts
assert not any(p.is_symlink() for p in (runner,*runner.parents))
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(runner)==runner_sha
synthesis=root.parent/'retained-summary-synth-parent.39BysdkS'
source=synthesis/'synthesis/retained_output_synth.dcp'
receipt=json.loads((synthesis/'execution.json').read_text())
audit=json.loads((synthesis/'audit.json').read_text())
assert receipt['vendor_exit']==0 and not receipt['timed_out']
assert receipt['changed_prepared_files']==[] and receipt['qualified_source_check_exit']==receipt['copied_source_check_exit']==0
expected=receipt['dcp_sha256']
assert sha(source)==expected==audit['dcp_sha256']
assert audit['source_hierarchy_resources_verified'] is True
assert audit['constraints_verified'] is True
gate=json.loads((root/'preparation-gate.json').read_text())
assert gate['exit']==0 and gate['unchanged'] is True and gate['runner_sha']==runner_sha
assert gate['expected_tests']>0 and gate['counts']=={'tests':gate['expected_tests'],'failures':0,'errors':0,'skipped':0}
output=root/'route'
assert not output.exists() and not (root/'execution.json').exists()
frozen=root/'frozen_route.tcl'
assert not frozen.exists()
shutil.copyfile(runner,frozen)
assert sha(frozen)==runner_sha
env={k:v for k,v in os.environ.items() if k not in {'PYTHONHOME','PYTHONPATH','PYTHONOPTIMIZE','LD_LIBRARY_PATH'}}
env['LD_LIBRARY_PATH']='/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE'
cmd=['/opt/Xilinx/Vivado/2022.2/bin/vivado','-mode','batch','-notrace',
     '-log',str(root/'vivado.log'),'-journal',str(root/'vivado.jou'),
     '-source',str(frozen),'-tclargs',str(source),expected,str(output)]
(root/'command.json').write_text(json.dumps({'command':cmd,'cwd':str(root),'wall_limit_seconds':1200,
 'source_dcp_sha256':expected,'runner_sha256':runner_sha,
 'kind':'ISOLATED_OOC_ROUTE_DIAGNOSTIC_NOT_RECEIVER_QUALIFICATION'},indent=2))
started=time.monotonic();timed_out=False
with (root/'stdout.log').open('x') as out:
    process=subprocess.Popen(cmd,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
    (root/'process.json').write_text(json.dumps({'pid':process.pid,'process_group':process.pid}))
    print(f'Root diagnostic route started; pid={process.pid}',flush=True)
    try:
        code=process.wait(timeout=1200)
    except subprocess.TimeoutExpired:
        timed_out=True
        os.killpg(process.pid,signal.SIGTERM)
        try: code=process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);code=process.wait(timeout=15)
routed=output/'retained_output_routed.dcp'
result={'vendor_exit':code,'timed_out':timed_out,'wall_seconds':time.monotonic()-started,
 'source_dcp_unchanged':sha(source)==expected,'original_runner_unchanged':sha(runner)==runner_sha,
 'frozen_runner_unchanged':sha(frozen)==runner_sha,'routed_dcp_sha256':sha(routed) if routed.is_file() else None,
 'timing_pass_not_inferred_from_tool_exit':True,'deployment_eligible':False}
(root/'execution.json').write_text(json.dumps(result,indent=2))
print('\n'.join((root/'stdout.log').read_text().splitlines()[-25:]),flush=True)
print(json.dumps(result),flush=True)
assert code==0 and not timed_out and all(result[k] for k in ('source_dcp_unchanged','original_runner_unchanged','frozen_runner_unchanged')) and result['routed_dcp_sha256'],result

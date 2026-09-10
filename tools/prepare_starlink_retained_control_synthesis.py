#!/usr/bin/env python3
"""Candidate-only copier; frozen candidate CLI and completed actual result required."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PYTHON = '/home/mouse9911/.local/share/uv/python/cpython-3.11.16-linux-x86_64-gnu/bin/python3.11'
EXPECTED = '7a9b32f10241d22c3f5a6d3967ca9841e2646bb94d714f4935c05f5e8d03635e'
BASE = 'hdl/library/starlink_pss_acquisition/'
ASSETS = {
    'synthesize_retained_control.tcl': BASE+'retained_control_actual/synthesize_retained_control.tcl',
    'clocks.xdc': BASE+'fft_bank_owned_resource_probe.xdc',
    'threads.tcl': BASE+'fft_bank_owned_synth_threads.tcl',
    'prepare.py': 'tools/prepare_starlink_retained_control_synthesis.py',
    'offline_tests.py': 'tests/test_starlink_retained_control_synthesis.py',
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe(path):
    if not path.is_absolute() or '..' in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('absolute non-symlink path required')
    return path


def prepare(qualified, actual, output):
    qualified, actual, output = map(safe, (qualified, actual, output))
    if output.exists():
        raise ValueError('refusing preparation overwrite')
    if any(output.is_relative_to(parent) for parent in (qualified, actual, ROOT)):
        raise ValueError('output must be outside qualified, actual and source roots')
    assert digest(qualified/'manifest.json') == EXPECTED
    assert digest(ROOT/ASSETS['clocks.xdc']) == 'bac30eff84cc71d1f273104b716b388b55e51d33be10f9beaf1901232193ba3f'
    assert digest(ROOT/ASSETS['threads.tcl']) == 'aec974f2800f01285e888d1b188cd089534941922531914926a8e1b568d4c227'
    assert digest(Path(PYTHON)) == '2874a0b9344d06b7767aebb1e6e25a759ffcbdb544e99400ecc74dc6092d1174'
    cli=qualified/'source_snapshot/tools/prepare_starlink_retained_control_actual.py'
    env={k:v for k,v in os.environ.items() if k not in {'PYTHONHOME','PYTHONPATH','PYTHONOPTIMIZE','LD_LIBRARY_PATH'}}
    def invoke(action, path):
        command=[PYTHON,'-B',str(cli),action,str(path),'--expected',EXPECTED]
        if action=='verify':command.append('--live')
        return subprocess.check_output(command,env=env,cwd='/',text=True,timeout=30)
    verified=invoke('verify',qualified);result=invoke('results',actual)
    assert json.loads(result) == json.loads((actual/'results.json').read_text())
    output.mkdir(parents=True)
    shutil.copytree(qualified,output/'qualified')
    before={name:digest(ROOT/path) for name,path in ASSETS.items()}
    for name,path in ASSETS.items():shutil.copyfile(ROOT/path,output/name)
    (output/'actual_result.json').write_text(result)
    (output/'qualified_before.json').write_text(verified)
    (output/'qualified_copy.json').write_text(invoke('verify',output/'qualified'))
    assert before=={name:digest(ROOT/path) for name,path in ASSETS.items()}
    (output/'qualified_after.json').write_text(invoke('verify',qualified))
    rows=[]
    for path in sorted(output.rglob('*')):
        if path.is_symlink():raise ValueError('symlink in copied preparation')
        if path.is_file():rows.append(f'{digest(path)}  {path.relative_to(output).as_posix()}\n')
    (output/'SHA256SUMS').write_text(''.join(rows))
    return {'files':len(rows),'inventory_sha256':digest(output/'SHA256SUMS'),'vendor_invoked':False}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('qualified',type=Path);p.add_argument('actual',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();print(json.dumps(prepare(a.qualified,a.actual,a.output),sort_keys=True))

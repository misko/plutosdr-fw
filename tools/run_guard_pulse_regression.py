"""Rerun the pinned prior experiment's exact test modules plus additive tests."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from staged_fft_experiment import sha,require,fresh

def run(baseline,output):
    root=Path(__file__).resolve().parents[1]
    before_sha=sha(baseline);tree=ET.parse(baseline)
    require(not any(list(tree.iter(x)) for x in ['failure','error','skipped']),'passing baseline XML')
    cases=list(tree.iter('testcase'));require(len(cases)==2360,'exact inherited regression scope')
    names=sorted({x.attrib['classname'] for x in cases})
    require(len(names)==133 and all(n.startswith('tests.test_') for n in names),'exact prior modules')
    paths=[root/(n.replace('.','/')+'.py') for n in names]
    paths += [root/'tests'/name for name in ['test_starlink_guard_pulse.py']]
    require(all(p.is_file() for p in paths),'all inherited modules present')
    hashes={str(p):sha(p) for p in paths};fresh(output)
    command=[sys.executable,'-B','-m','pytest','-q',*[str(p) for p in paths],
        '--basetemp='+str(output/'tests'),'--junitxml='+str(output/'tests.xml')]
    receipt=dict(command=command,baseline=str(baseline),baseline_sha256=before_sha,
        test_sources=hashes,started=time.time(),scope='133 inherited modules plus 1 guard-pulse module; not entire repository')
    (output/'command.json').write_text(json.dumps(receipt,indent=2)+'\n')
    with (output/'stdout.log').open('w') as log:
        process=subprocess.Popen(command,cwd=root,stdout=log,stderr=subprocess.STDOUT)
        (output/'process.json').write_text(json.dumps({'pid':process.pid})+'\n')
        receipt['returncode']=process.wait()
    receipt['elapsed_seconds']=time.time()-receipt['started']
    result=ET.parse(output/'tests.xml');receipt['tests']=len(list(result.iter('testcase')))
    receipt['sources_unchanged']=sha(baseline)==before_sha and hashes=={str(p):sha(p) for p in paths}
    receipt['passed']=receipt['returncode']==0 and receipt['tests']==2383 and receipt['sources_unchanged'] and not any(list(result.iter(x)) for x in ['failure','error','skipped'])
    (output/'outcome.json').write_text(json.dumps(receipt,indent=2)+'\n')
    require(receipt['passed'],'scoped regression failed')
    return dict(passed=True,tests=receipt['tests'],elapsed_seconds=receipt['elapsed_seconds'],scope=receipt['scope'])

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('baseline',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();print(json.dumps(run(args.baseline,args.output),indent=2))

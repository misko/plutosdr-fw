#!/usr/bin/env python3
"""Fixed terminal/source/test collector. No simulation, synthesis or input edits."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile

from package_starlink_retained_frame_actual import encoded, receipt

RECOVERY=Path('/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz')
ACTUAL=RECOVERY/'retained-summary-actual-parent.XYAbt6Np'
PREPARED=RECOVERY/'retained-summary-actual-prelaunch-v1'
ROOTS={
 'actual':ACTUAL,
 'prepared':PREPARED,
 'parent67':RECOVERY/'retained-summary-actual-prep-parent.ZLxFAi3v',
 'parent_script':RECOVERY/'retained-summary-script-parent.jVE5ixKt',
}
EXPECTED='b5d112562b7db31164dc4a6ff92404de8e7d7d5d96b1c1b23e1a7dbac9d2c368'
PYTHON='/home/mouse9911/.local/share/uv/python/cpython-3.11.16-linux-x86_64-gnu/bin/python3.11'


def inventory(root):
    files={};aliases={}
    for p in sorted(root.rglob('*')):
        name=p.relative_to(root).as_posix()
        if p.is_symlink():aliases[name]=str(p.readlink())
        elif p.is_file():files[name]=receipt(p)
    if len(files)>10000 or sum(r['bytes'] for r in files.values())>1_000_000_000:
        raise ValueError('bounded terminal evidence exceeded')
    return files,aliases


def main():
    output=RECOVERY/'retained-summary-actual-result-package-v1'
    if output.exists():raise ValueError('no overwrite')
    run=ACTUAL/'run';inputs=run/'inputs'
    assert receipt(inputs/'manifest.json')['sha256']==EXPECTED
    status=json.loads((ACTUAL/'outcome.json').read_text())
    assert status['vendor_exit']==status['original_check_exit']==status['copied_check_exit']==status['independent_result_exit']==0
    assert status['timed_out'] is False and status['physical_qualified'] is False and status['functional_accepted'] is True
    env={k:v for k,v in os.environ.items() if k not in {'PYTHONHOME','PYTHONPATH','PYTHONOPTIMIZE','LD_LIBRARY_PATH'}}
    cli=inputs/'source_snapshot/tools/prepare_starlink_retained_summary_actual.py'
    original_verified=json.loads(subprocess.check_output([PYTHON,'-B',str(cli),'verify',str(PREPARED),'--expected',EXPECTED,'--live'],env=env,cwd='/',text=True,timeout=30))
    assert original_verified['sources']==116 and original_verified['files']==119
    manifest=json.loads((inputs/'manifest.json').read_text())
    live_root=Path(manifest['source_root'])
    live_before={n:receipt(live_root/n) for n in manifest['sources']}
    assert live_before==manifest['sources']
    result=json.loads(subprocess.check_output([PYTHON,'-B',str(cli),'results',str(run),'--expected',EXPECTED],env=env,cwd='/',text=True,timeout=30))
    assert result==json.loads((run/'results.json').read_text())
    baseline=json.loads((RECOVERY/'retained-control-actual-parent.HbyLZ8I2/run/results.json').read_text())
    assert {k:v for k,v in result.items() if k!='offer_summary'}==baseline
    sim=run/'project/retained_output_actual.sim/sim_1/behav/xsim'
    baseline_csv=RECOVERY/'retained-control-actual-parent.HbyLZ8I2/run/project/retained_output_actual.sim/sim_1/behav/xsim/actual_words.csv'
    assert (sim/'actual_words.csv').read_bytes()==baseline_csv.read_bytes()
    assert receipt(sim/'actual_words.csv')['sha256']=='07321b026a637e5922c56a84a955e58549056337198c952a9d73b1245cb4efaa'
    ip=(run/'generated_ip_before.txt').read_bytes()
    assert ip==(run/'generated_ip_after.txt').read_bytes()
    ip_hash,ip_path=ip.decode().strip().split(maxsplit=1)
    assert ip_hash=='a3a650654118016012bdfb8553114ee4a89866466d8ca774fa0f281640168a68'
    assert receipt(Path(ip_path))['sha256']==ip_hash
    before={name:inventory(root) for name,root in ROOTS.items()}
    selected={}
    for label,root in ROOTS.items():
        for name in before[label][0]:
            path=root/name
            if label=='actual':
                take=(len(Path(name).parts)==1 or name.startswith('run/inputs/') or
                      (path.parent==run) or (path.parent==sim and path.suffix in ('.log','.csv','.prj','.sh','.ini','.mem')))
            elif label=='prepared':take=True
            else:
                # Duplicated source snapshots already occur in the actual bundle.
                # Every omitted file still has an exact full raw inventory receipt.
                take=('source_snapshot' not in Path(name).parts and path.suffix not in ('.vvp','.pyc'))
            if take:selected[label+'/'+name]=path
    selected['generated_ip/synthesis_wrapper.vhd']=Path(ip_path)
    selected['previous_control_actual/result.json']=RECOVERY/'retained-control-actual-parent.HbyLZ8I2/run/results.json'
    selected['report.md']=Path(__file__).resolve().parents[1]/'docs/starlink-retained-summary-actual-result-20260910.md'
    selected['collector.py']=Path(__file__).resolve()
    selected['collector_receipt_helpers.py']=Path(__file__).with_name('package_starlink_retained_frame_actual.py')
    selected_before={n:receipt(p) for n,p in selected.items()}
    payload={n:p.read_bytes() for n,p in selected.items()}
    payload['full_raw_inventory.json']=encoded({name:{'root':str(ROOTS[name]),'files':files,'excluded_symlink_aliases':aliases}
        for name,(files,aliases) in before.items()})
    payload['collector_audit.json']=encoded({'original_result_equal':True,'actual_csv_equal':True,
        'parent_original_process':84113,'vendor_invoked_by_collector':False,'physical_qualified':False,
        'selected_before':selected_before,'selection':'actual inputs/top receipts/numerical/logs; complete frozen preparation; tests except duplicate source_snapshot and vvp/pyc; all omissions remain in place and fully inventoried'})
    files={n:{'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)} for n,data in payload.items()}
    payload['receipt.json']=encoded({'files':files,'actual_manifest_sha256':EXPECTED})
    output.mkdir();archive=output/'retained-summary-actual-v1.tar.gz'
    with tarfile.open(archive,'w:gz') as tar:
        for name,data in sorted(payload.items()):
            member=tarfile.TarInfo(name);member.size=len(data);member.mode=0o644;member.mtime=0
            tar.addfile(member,io.BytesIO(data))
    assert before=={n:inventory(r) for n,r in ROOTS.items()}
    assert selected_before=={n:receipt(p) for n,p in selected.items()}
    assert live_before=={n:receipt(live_root/n) for n in manifest['sources']}
    with tarfile.open(archive) as tar:
        assert len(tar.getmembers())==len(payload)
        for m in tar:
            assert m.isfile() and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts
            assert tar.extractfile(m).read()==payload[m.name]
    result={'archive':receipt(archive),'members':len(payload),'file_receipts':len(files),
        'all_raw_regular_files':sum(len(x[0]) for x in before.values()),
        'actual_raw_files':len(before['actual'][0]),'actual_raw_bytes':sum(x['bytes'] for x in before['actual'][0].values()),
        'all_before_after_equal':True}
    (output/'package-receipt.json').write_bytes(encoded(result));print(json.dumps(result))


if __name__=='__main__':main()

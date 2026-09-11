"""Source/implicit-net preflight only; missing vendor IP is allowed for lint."""
import importlib.util
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('staged_fft_experiment',ROOT/'tools/staged_fft_experiment.py')
experiment=importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)

def test_frozen_sources_have_no_implicit_wires(tmp_path):
    prepared=tmp_path/'inputs'
    receipt=experiment.prepare(prepared)
    experiment.verify(prepared,receipt['sha256sums'])
    run=subprocess.run(['iverilog','-g2012','-i','-s','starlink_pss_fft_staged_output_impl',
                        '-tnull','-Wall',*map(str,sorted(prepared.glob('*.v')))],
                       capture_output=True,text=True,timeout=30)
    (tmp_path/'lint.log').write_text(run.stdout+run.stderr)
    assert run.returncode==0 and run.stdout=='' and run.stderr=='',run.stdout+run.stderr
    experiment.verify(prepared,receipt['sha256sums'])

def test_generated_scope_readiness_typo_is_rejected(tmp_path):
    prepared=tmp_path/'inputs';experiment.prepare(prepared)
    path=prepared/'starlink_pss_fft_staged_output_impl.v'
    source=path.read_text()
    before='.mailbox_input_ready(OWNER == 1 ? inverse_guard_ready :'
    assert source.count(before)==1
    path.write_text(source.replace(before,'.mailbox_input_ready(OWNER == 1 ? inverse_guard_read_y :',1))
    run=subprocess.run(['iverilog','-g2012','-i','-s','starlink_pss_fft_staged_output_impl',
                        '-tnull','-Wall',*map(str,sorted(prepared.glob('*.v')))],
                       capture_output=True,text=True,timeout=30)
    (tmp_path/'lint.log').write_text(run.stdout+run.stderr)
    assert run.returncode!=0 and 'inverse_guard_read_y' in run.stderr,run.stdout+run.stderr

"""Private validation stage, not integrated FFT/receiver qualification."""
import hashlib
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
RTL = ROOT / 'hdl/library/starlink_pss_acquisition/staged_control'
MODULE = RTL / 'starlink_pss_input_identity_stage.v'
BENCH = RTL / 'tb_input_identity_stage.sv'


def run(tmp_path, mutant=None):
    text = MODULE.read_text()
    replacements = {
        'lost_refill': ('if (take_input) begin', 'if (take_input && !take_output) begin'),
        'corrupt_data': ('output_data<=input_data;', 'output_data<=~input_data;'),
        'skip_identity': ("(input_metadata == job_descriptor) === 1'b1", "1'b1"),
        'unknown_equal': ("(input_metadata == job_descriptor) === 1'b1", '(input_metadata === job_descriptor)'),
        'lost_reset': ('full<=0;fault_q<=0;', 'full<=1;fault_q<=0;'),
        'lost_abort': ("(abort_epoch !== 1'b0) ||", "1'b0 ||"),
    }
    if mutant:
        before, after = replacements[mutant]
        assert text.count(before) == 1
        text = text.replace(before, after)
    source = tmp_path / MODULE.name
    source.write_text(text)
    executable = tmp_path / 'stage.vvp'
    compiled = subprocess.run(['iverilog', '-g2012', '-s', 'tb_input_identity_stage',
                               '-o', str(executable), str(source), str(BENCH)],
                              capture_output=True, text=True, timeout=30)
    (tmp_path / 'compile.log').write_text(compiled.stdout + compiled.stderr)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    result = subprocess.run(['vvp', str(executable)], capture_output=True,
                            text=True, timeout=30)
    (tmp_path / 'simulate.log').write_text(result.stdout + result.stderr)
    return result


def test_stage_stream_identity_ownership_and_reset(tmp_path):
    result = run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    for marker in ['INPUT_STAGE_STREAM_PASS words=512 refills=511 final_stall=200',
                   'INPUT_STAGE_IDENTITY_PASS bits=70 cases=350 unknown_equal_rejected=1',
                   'INPUT_STAGE_RANDOM_PASS cycles=4096 conservation=1',
                   'abort_cases=7 no_fft_or_route_claim']:
        assert marker in result.stdout
    assert result.stdout.count('INPUT_STAGE_PASS ') == 1


@pytest.mark.parametrize('mutant', ['lost_refill', 'corrupt_data', 'skip_identity',
                                   'unknown_equal', 'lost_reset', 'lost_abort'])
def test_unsafe_stage_mutants_rejected(tmp_path, mutant):
    result = run(tmp_path, mutant)
    assert result.returncode != 0 and 'FATAL' in result.stdout, result.stdout


def test_existing_integrated_top_unchanged():
    top = RTL / 'starlink_pss_fft_staged_output_impl.v'
    assert hashlib.sha256(top.read_bytes()).hexdigest() == (
        'b3511a70b97b91e3e9b4106ea0c9bab8df4f7a43a07ff30a5447cd522dc5d143')
    assert 'starlink_pss_input_identity_stage' not in top.read_text()


def test_checker_changes_only_identity_input():
    parent = ROOT.parent / 'staged-preflightpublication-prepared-v1/starlink_pss_realtime_input_guard_local_admission.v'
    old = parent.read_text()
    assert hashlib.sha256(old.encode()).hexdigest() == (
        '55438743eede0d346cec67351e079eb6ae21da437d4088a131a2a258b43ff233')
    new = (RTL / 'starlink_pss_realtime_input_guard_staged_identity.v').read_text()
    new = new.replace('starlink_pss_realtime_input_guard_staged_identity #(',
                      'starlink_pss_realtime_input_guard_local_admission #(', 1)
    new = new.replace('  // Must accompany the exact buffered beat, checked against this job at capture.\n  input wire input_identity_good,\n', '', 1)
    begin = old.index('  generate if (BALANCED_IDENTITY_EQ)')
    end = old.index('  end endgenerate\n', begin) + len('  end endgenerate\n')
    begin_new = new.index('  // Wide comparison was performed before')
    end_new = new.index("  assign identity_matches = input_identity_good === 1'b1;\n", begin_new) + len("  assign identity_matches = input_identity_good === 1'b1;\n")
    assert new[:begin_new] + old[begin:end] + new[end_new:] == old


def test_buffer_with_actual_input_checker(tmp_path):
    executable = tmp_path / 'checker.vvp'
    sources = [MODULE, RTL / 'starlink_pss_realtime_input_guard_staged_identity.v',
               RTL / 'tb_input_identity_checker.sv']
    result = subprocess.run(['iverilog', '-g2012', '-s', 'tb_input_identity_checker',
                             '-o', str(executable), *map(str, sources)],
                            capture_output=True, text=True, timeout=30)
    (tmp_path / 'compile.log').write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run(['vvp', str(executable)], capture_output=True,
                            text=True, timeout=30)
    (tmp_path / 'simulate.log').write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'INPUT_CHECKER_REJECTION_PASS malformed=8 gap=1 exact_prefix=1' in result.stdout
    assert 'healthy_jobs=3 rejected_jobs=9 final_reset=1 no_actual_fft_or_route_claim' in result.stdout

"""Fixture/byte expectations using Icarus only; XSim crash cause is not asserted."""
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
RTL = ROOT / 'hdl/library/starlink_pss_acquisition/retained_output_actual'
BENCH = RTL / 'logger_repro/tb_retained_logger_repro.sv'


def test_original_automatic_string_task_is_byte_identical():
    def task(path):
        text = path.read_text()
        start = text.index('task automatic actual_word(')
        return text[start:text.index('endtask', start) + len('endtask')]
    assert task(BENCH) == task(RTL / 'witness.svh')


@pytest.mark.parametrize('case', range(12))
def test_exact_logger_rows_offline_only(tmp_path, case):
    compile_run = subprocess.run(['iverilog', '-g2012', '-s', 'tb', f'-Ptb.CASE={case}',
                                  '-o', str(tmp_path / 'sim.vvp'), str(BENCH)],
                                 capture_output=True, text=True, timeout=10)
    (tmp_path / 'compile.log').write_text(compile_run.stdout + compile_run.stderr)
    assert compile_run.returncode == 0
    result = subprocess.run(['vvp', str(tmp_path / 'sim.vvp')], cwd=tmp_path,
                            capture_output=True, text=True, timeout=10)
    (tmp_path / 'simulation.log').write_text(result.stdout + result.stderr)
    assert result.returncode == 0 and f'LOGGER_REPRO_COMPLETED case={case} rows=2' in result.stdout
    stream = ('input' if case < 6 else 'raw') + ('I' if case % 2 else 'F')
    expected = ('context,stream,job,position,data,start,exponent,fast,slow,time_fs\n'
                '0,source,0,0,123456789abc,00000000000003e8,003,939,536,2000000\n'
                f'0,{stream},0,0,123456789abc,00000000000003e8,003,939,536,3000000\n')
    assert (tmp_path / 'logger_rows.csv').read_bytes() == expected.encode()

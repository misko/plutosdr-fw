"""Control-flow tests with Tcl stubs only; never loads or advances an HDL design."""
from pathlib import Path
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / 'tools/diagnostics/retained_output_startup.tcl'


@pytest.mark.parametrize('kind', ['complete', 'missing', 'duplicate', 'run_error'])
def test_targeted_diagnostic_control_flow(tmp_path, kind):
    driver = tmp_path / 'stub.tcl'
    driver.write_text('''# OFFLINE TCL STUBS; NO VENDOR/HDL SIMULATION.
set logged {}
set run_calls 0
proc get_objects args {
  global names
  if {$args ne {-r *}} {error DISCOVERY_ARGUMENTS}
  set objects $names
''' + {'missing': '  set objects [lrange $objects 0 end-1]\n',
       'duplicate': '  lappend objects [lindex $objects 0]\n'}.get(kind, '') + '''
  lappend objects {/tb/dut/retained/island/fast_running}
  lappend objects {/tb/dut/\\retained.island /unrequested_payload}
  return $objects
}
proc log_wave object {global logged;lappend logged $object}
proc get_value args {
  if {[lrange $args 0 1] ne {-radix bin}} {error RADIX}
  return X
}
proc run args {
  global run_calls logged names
  if {$args ne {250 ns} || $logged ne $names} {error RUN_OR_WAVE_SCOPE}
  incr run_calls
''' + ('  error ORIGINAL_STUB_RUN_ERROR\n' if kind == 'run_error' else '') + '''
}
set status [catch {source {''' + str(SCRIPT) + '''}} message]
set f [open stub_result.txt {WRONLY CREAT EXCL}]
puts $f "status=$status run_calls=$run_calls logged=[llength $logged]"
puts $f $message
close $f
''')
    run = subprocess.run(['tclsh', str(driver)], cwd=tmp_path, capture_output=True, text=True, timeout=10)
    (tmp_path / 'stub.log').write_text(run.stdout + run.stderr)
    assert run.returncode == 0, run.stdout + run.stderr
    result = (tmp_path / 'stub_result.txt').read_text()
    if kind in ('missing', 'duplicate'):
        assert result.startswith('status=1 run_calls=0 logged=0\n')
        assert 'missing/duplicate' in result
        assert not (tmp_path / 'startup_values.tsv').exists()
    else:
        assert result.startswith(f'status={1 if kind == "run_error" else 0} run_calls=1 logged=66\n')
        values = (tmp_path / 'startup_values.tsv').read_text().splitlines()
        assert len(values) == 133
        assert sum(line.startswith('before\t') for line in values) == 66
        assert sum(line.startswith('after\t') for line in values) == 66
        assert all(line.endswith('\tX') for line in values[1:])
        if kind == 'run_error':
            assert 'ORIGINAL_STUB_RUN_ERROR' in result

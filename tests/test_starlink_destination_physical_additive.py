"""Additional destination-specific recipe checks; Tcl mocks are not vendor runs."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('destination_physical_inherited', ROOT/'tests/test_starlink_retained_destination_synthesis.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)

def test_selected_actual_runtime_excludes_observational_owner(tmp_path):
    manifest = json.loads((Path(old.g.ACCEPTED_ACTUAL['qualified'])/'manifest.json').read_text())
    text = (old.ASSETS/'synthesize_retained_destination.tcl').read_text()
    fragment = text[text.index('  set rtl_names {}'):text.index('  set kernels ')]
    run = old.tcl_run(tmp_path, 'set compiled_names {'+' '.join(manifest['compiled'])+'}\n'+fragment+'puts [join $rtl_names "\\n"]\n')
    assert run.returncode == 0, run.stderr
    pins = json.loads((old.ASSETS/'source_pins.json').read_text())['runtime']
    assert set(run.stdout.splitlines()) == {'source_snapshot/'+n for n in pins}
    assert sum('/retained_destination_candidate/' in n for n in pins) == 3
    assert not any(n.endswith('/starlink_pss_retained_output_owner.v') for n in pins)
    for n, digest in pins.items():
        source = Path(old.g.ACCEPTED_ACTUAL['qualified'])/'source_snapshot'/n
        assert hashlib.sha256(source.read_bytes()).hexdigest() == digest

@pytest.mark.parametrize('replacement', ['', 'CONTEXTUAL_DESTINATION_SUMMARY=0', "CONTEXTUAL_DESTINATION_SUMMARY=1'bx", "CONTEXTUAL_DESTINATION_SUMMARY=1'bz", 'CONTEXTUAL_DESTINATION_SUMMARY=1 EXTRA=1'])
def test_destination_option_readback_rejects_mutation(tmp_path, replacement):
    text = (old.ASSETS/'synthesize_retained_destination.tcl').read_text()
    fragment = text[text.index('  set generics [list '):text.index('  set_property STEPS.SYNTH_DESIGN.ARGS.FLATTEN_HIERARCHY')]
    assert 'CONTEXTUAL_DESTINATION_SUMMARY=1]' in fragment
    script = '''set kernel /MOCK_ONLY/kernel.mem
proc get_filesets args {return sources_1}
proc set_property {n value target} {global actual;set actual $value}
proc get_property args {global actual;return [string map [list CONTEXTUAL_DESTINATION_SUMMARY=1 {'''+replacement+'''}] $actual]}
'''+fragment
    run = old.tcl_run(tmp_path, script)
    assert run.returncode != 0 and 'contextual-destination generics' in run.stderr

def test_real_accepted_actual_is_read_only_admitted():
    binding = old.g.ACCEPTED_ACTUAL
    result = old.g.admit(Path(binding['qualified']), Path(binding['actual']), old.g.EXPECTED)
    assert result['runtime_files'] == 16 and result['vendor_invoked'] is False

@pytest.mark.parametrize('kind', ['admission', 'tests'])
def test_additional_complete_source_inverse_rejects_edits(kind):
    target, original, _, _ = old.d.recipe(kind)
    assert old.d.inverse(kind, target.read_text()) == original
    with pytest.raises(ValueError, match='inverse'):
        old.d.inverse(kind, target.read_text()+'\n# UNREVIEWED\n')

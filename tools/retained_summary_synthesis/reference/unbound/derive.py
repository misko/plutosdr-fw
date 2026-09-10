"""Strict literal derivation; preparation-only, never launches a vendor tool."""
import argparse
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
UNBOUND = 'UNBOUND_PENDING_ACCEPTED_SUMMARY_ACTUAL'
GATE_IMPORT = '''import sys
import importlib.util
gate_path = Path(__file__).resolve().parent/'retained_summary_synthesis/admission.py'
gate_spec = importlib.util.spec_from_file_location('summary_synthesis_admission', gate_path)
gate = importlib.util.module_from_spec(gate_spec)
gate_spec.loader.exec_module(gate)
if sys.flags.optimize:
    raise SystemExit('unoptimized source-bound preparation required')
'''

HELPER_EDITS = [
 ('Candidate-only copier; frozen candidate CLI and completed actual result required.',
  'Offered-summary copier; UNBOUND until original actual owner is accepted.'),
 ('ROOT = Path(__file__).resolve().parents[1]', GATE_IMPORT+'\nROOT = Path(__file__).resolve().parents[1]'),
 ("EXPECTED = '7a9b32f10241d22c3f5a6d3967ca9841e2646bb94d714f4935c05f5e8d03635e'", 'EXPECTED = gate.EXPECTED'),
 ("'synthesize_retained_control.tcl': BASE+'retained_control_actual/synthesize_retained_control.tcl'",
  "'synthesize_retained_summary.tcl': 'tools/retained_summary_synthesis/synthesize_retained_summary.tcl'"),
 ("BASE+'fft_bank_owned_resource_probe.xdc'", "'tools/retained_summary_synthesis/clocks.xdc'"),
 ("BASE+'fft_bank_owned_synth_threads.tcl'", "'tools/retained_summary_synthesis/threads.tcl'"),
 ('prepare_starlink_retained_control_synthesis.py', 'prepare_starlink_retained_summary_synthesis.py'),
 ('test_starlink_retained_control_synthesis.py', 'test_starlink_retained_summary_synthesis.py'),
 ("    'offline_tests.py': 'tests/test_starlink_retained_summary_synthesis.py',",
  "    'offline_tests.py': 'tests/test_starlink_retained_summary_synthesis.py',\n"
  "    'admission.py': 'tools/retained_summary_synthesis/admission.py',\n"
  "    'source_pins.json': 'tools/retained_summary_synthesis/source_pins.json',\n"
  "    'derive.py': 'tools/retained_summary_synthesis/derive.py',\n"
  "    'route_retained_output.tcl': 'tools/retained_summary_synthesis/route_retained_output.tcl',"),
 ("    assert digest(qualified/'manifest.json') == EXPECTED",
  "    gate.admit(qualified, actual, EXPECTED)\n    assert digest(qualified/'manifest.json') == EXPECTED"),
 ('prepare_starlink_retained_control_actual.py', 'prepare_starlink_retained_summary_actual.py'),
 ("    assert json.loads(result) == json.loads((actual/'results.json').read_text())",
  "    assert json.loads(result) == json.loads((actual/'results.json').read_text())\n"
  "    gate.check_result(actual, result)"),
 ("    (output/'qualified_after.json').write_text(invoke('verify',qualified))",
  "    (output/'qualified_after.json').write_text(invoke('verify',qualified))\n"
  "    gate.admit(qualified, actual, EXPECTED)"),
]
TCL_EDITS = [
 ('# Exact candidate runtime; requires separately approved actual result.',
  '# Exact offered-summary runtime; unbound until reviewed original actual success.'),
 ('synthesize_retained_control.tcl', 'synthesize_retained_summary.tcl'),
 ('prepare_starlink_retained_control_actual.py', 'prepare_starlink_retained_summary_actual.py'),
 ('7a9b32f10241d22c3f5a6d3967ca9841e2646bb94d714f4935c05f5e8d03635e', UNBOUND),
 ('set py [list env',
  'if {![regexp {^[0-9a-f]{64}$} $qualified_sha]} { error "unbound reviewed actual source" }\nset py [list env'),
 ('*/retained_output_closed_candidate/*.v', '*/retained_output_summary_candidate/*.v'),
 ('CLOSED_INPUT_CUTOVER=1]', 'CLOSED_INPUT_CUTOVER=1 INPUT_OFFER_FAULT_SUMMARY=1]'),
 ('exact retained/R1/B1/O1/L1/private-offer/closed-input generics',
  'exact retained/R1/B1/O1/L1/private-offer/closed-input/offered-summary generics'),
 ('RETAINED_CONTROL_SYNTHESIS_RECORDED_NOT_TIMING_OR_DEPLOYMENT_PASS',
  'RETAINED_SUMMARY_SYNTHESIS_RECORDED_NOT_TIMING_OR_DEPLOYMENT_PASS'),
]
CASES = {
 'helper': ('reference/prepare_starlink_retained_control_synthesis.py',
  '81d418d1659a276a7a93609b44c611b669529f655d7e189b0c4856e742a28e4d',
  ROOT/'tools/prepare_starlink_retained_summary_synthesis.py', HELPER_EDITS),
 'tcl': ('reference/synthesize_retained_control.tcl',
  '767ecdfb05f7fc967855196f92a08d8f1fafc6225ea6ef871d12ac8b1e8ed8fc',
  HERE/'synthesize_retained_summary.tcl', TCL_EDITS),
}


def recipe(kind):
    reference, expected, target, edits = CASES[kind]
    raw = (HERE/reference).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('original reference identity')
    original = raw.decode()
    text = original
    counts = []
    for old, new in edits:
        count = text.count(old)
        if count < 1 or new in text:
            raise ValueError('forward literal anchor')
        counts.append(count)
        text = text.replace(old, new)
    return target, original, text, list(zip(edits, counts, strict=True))


def inverse(kind, candidate):
    _, original, _, edits = recipe(kind)
    for (old, new), count in reversed(edits):
        if candidate.count(new) != count:
            raise ValueError('inverse literal count')
        candidate = candidate.replace(new, old)
    if candidate != original:
        raise ValueError('whole-source inverse')
    return candidate


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    for name in CASES:
        target, _, candidate, edits = recipe(name)
        if args.write:
            with target.open('x') as handle:
                handle.write(candidate)
        inverse(name, target.read_text())
        print(name, len(edits), hashlib.sha256(target.read_bytes()).hexdigest())

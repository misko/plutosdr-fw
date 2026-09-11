"""Bind a separate physical-preparation tree to one reviewed actual FFT run.

Original unbound sources remain unchanged. This only exports source files;
it never invokes the actual copier, synthesis or any radio operation.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
RECOVERY = Path('/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz')
SOURCE_RECEIPT = RECOVERY/'bank-physical-prep-parent.uhVRRMbq/before.json'
SOURCE_RECEIPT_SHA = 'd13a80c124f042e9352d1100392051fbb1e200e9caac5305c2f75c4b0dd0ecab'
MANIFEST = 'e83b111be699f6391a0ac03f961846d8798d2ee109fcc69f8ce175e4ec7b25f5'
OWNER = RECOVERY/'bank-identity-actual-parent.eL66fuq9'
BINDING = {
    'manifest_sha256': MANIFEST,
    'qualified': str(RECOVERY/'bank-identity-actual-prelaunch-parent-v1'),
    'actual': str(OWNER/'run'), 'owner': str(OWNER),
    'owner_files': {
        'owner.py': '996b697080dd5591cd8a4d951b777c857d544b7fa9f34a30752557481dc367db',
        'execution.json': '964de2b852688ba3581a01c387a4f251d284a2b24edeac1378623902e1483378',
        'outcome.json': 'b84f801993b1c84a9f1ece0a9dc7b50bccf4d504f49f5d3f0ff298e0ef24ac78',
        'command.json': '68d14425807f089a488c0958fe7f490c13732be244cabf33a3d5610efee9011e',
        'stdout.log': '4da9d6123d2fcc1dfab8be1c1a176344f3d03efc04644951405eb0da9f286cf7',
        'run/run_outcome.txt': '73b60a51ec3a0c5eb80df3634613b4f4e1f4206a2804bdd45cc9fed911dbed92',
    },
    'results_sha256': 'e8a984ae215a494f9d1d5dd210289c6643be0ef94afce93bdd4f310b51a3285a',
    'cli_sha256': 'c1c53931f9071a8bd805e86e0a8fc67137625b0e35f26798c9633c1f851879b1',
}
PREFIX = 'tools/retained_bank_identity_synthesis/'
EDITS = {
    PREFIX+'admission.py': (
        "EXPECTED = 'UNBOUND_PENDING_ACCEPTED_BANK_IDENTITY_ACTUAL'\nACCEPTED_ACTUAL = None",
        'EXPECTED = '+repr(MANIFEST)+'\nACCEPTED_ACTUAL = '+repr(BINDING)),
    PREFIX+'synthesize_retained_bank_identity.tcl': (
        'set qualified_sha UNBOUND_PENDING_ACCEPTED_BANK_IDENTITY_ACTUAL',
        'set qualified_sha '+MANIFEST),
}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def require(ok, message):
    if not ok:
        raise ValueError(message)

def safe(path):
    require(path.is_absolute() and '..' not in path.parts and
            not any(p.is_symlink() for p in (path, *path.parents)), 'absolute non-symlink path')
    return path

def source_pins():
    require(sha(SOURCE_RECEIPT) == SOURCE_RECEIPT_SHA, 'independent80 source receipt')
    pins = json.loads(SOURCE_RECEIPT.read_text())
    require(len(pins) == 24, 'complete unbound24 closure')
    for name, expected in pins.items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'relative source')
        require(sha(safe(ROOT/name)) == expected, 'unchanged unbound source '+name)
    return pins

def restored(name, text):
    before, after = EDITS[name]
    require(text.count(after) == 1, 'bound inverse boundary')
    original = text.replace(after, before, 1)
    require(original == (ROOT/name).read_text(), 'bound whole-source inverse')
    return original

def export(output):
    require(not sys.flags.optimize, 'unoptimized binding required')
    output = safe(output)
    require(not output.exists(), 'no binding overwrite')
    require(not any(output.is_relative_to(p) for p in
                    (ROOT, OWNER, Path(BINDING['qualified']))), 'outside protected source/actual')
    pins = source_pins()
    output.mkdir(parents=True)
    for name in pins:
        text = (ROOT/name).read_text()
        if name in EDITS:
            before, after = EDITS[name]
            require(text.count(before) == 1, 'binding literal source boundary')
            text = text.replace(before, after, 1)
            restored(name, text)
        target = output/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    require(source_pins() == pins, 'unbound source changed')
    spec = importlib.util.spec_from_file_location('bound_bank_admission', output/PREFIX/'admission.py')
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    gate.admit(Path(BINDING['qualified']), Path(BINDING['actual']), MANIFEST)
    gate.check_result(Path(BINDING['actual']), (OWNER/'run/results.json').read_text())
    receipt = {'source_pins': pins, 'binding': BINDING, 'edits': EDITS,
               'bound_files': {n: sha(output/n) for n in pins},
               'changed_files': sorted(EDITS), 'unbound_sources_unchanged': True,
               'vendor_invoked': False, 'physical_qualified': False}
    (output/'binding.json').write_text(json.dumps(receipt, indent=2)+'\n')
    return receipt

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(json.dumps(export(args.output), sort_keys=True))

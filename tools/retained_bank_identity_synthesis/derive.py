"""Source-specific mechanical preparation derivation; never invokes Vivado."""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
UNBOUND = 'UNBOUND_PENDING_ACCEPTED_BANK_IDENTITY_ACTUAL'
ACTUAL_MANIFEST = UNBOUND
OLD_MANIFEST = 'b5d112562b7db31164dc4a6ff92404de8e7d7d5d96b1c1b23e1a7dbac9d2c368'
REPLACEMENTS = {
    'starlink_pss_fft_bank_owned_retained_output_probe.v': '42b6f902aef4235d1ddfae3e38135f73deab3fe06ff8b57f4ff32c9684792489',
    'starlink_pss_fft_retained_output_impl.v': 'c41ecec9ae2f6072c6725ec452edd999120947647caaa6648f69d4c5a153d07b',
    'starlink_pss_realtime_input_guard_local_admission.v': '1197df519574ceceaa1b17b5b972bd3fc38a1caedd18ede492dd3ec1e056b005',
}
HELPER_EDITS = [
    ('Offered-summary copier; UNBOUND until original actual owner is accepted.',
     'Bank-local identity copier; UNBOUND until new original actual owner is accepted.'),
    ('retained_summary_synthesis', 'retained_bank_identity_synthesis'),
    ('synthesize_retained_summary.tcl', 'synthesize_retained_bank_identity.tcl'),
    ('summary_synthesis_admission', 'bank_identity_synthesis_admission'),
    ('prepare_starlink_retained_summary_actual.py', 'prepare_starlink_retained_bank_identity_actual.py'),
    ("    'derive.py': 'tools/retained_bank_identity_synthesis/derive.py',",
     "    'derive.py': 'tools/retained_bank_identity_synthesis/derive.py',\n"
     "    'inspect_bank_identity.tcl': 'tools/retained_bank_identity_synthesis/inspect_bank_identity.tcl',"),
    ("\n\ndef digest(path):", "\n\nfor name in json.loads((gate_path.parent/'source_pins.json').read_text())['reference_assets']:\n"
     "    if name.startswith('reference/'):\n"
     "        ASSETS[name] = 'tools/retained_bank_identity_synthesis/'+name\n\n\ndef digest(path):"),
    ("    for name,path in ASSETS.items():shutil.copyfile(ROOT/path,output/name)",
     "    for name,path in ASSETS.items():\n"
     "        (output/name).parent.mkdir(parents=True, exist_ok=True)\n"
     "        shutil.copyfile(ROOT/path,output/name)"),
]
TCL_EDITS = [
    ('# Exact offered-summary runtime; unbound until reviewed original actual success.',
     '# Exact bank-local identity runtime; unbound until new reviewed original actual success.'),
    ('synthesize_retained_summary.tcl', 'synthesize_retained_bank_identity.tcl'),
    ('prepare_starlink_retained_summary_actual.py', 'prepare_starlink_retained_bank_identity_actual.py'),
    (OLD_MANIFEST, UNBOUND),
    ('*/retained_output_summary_candidate/*.v $name]',
     '*/retained_output_summary_candidate/*.v $name] || [string match */retained_output_bank_identity_candidate/*.v $name]'),
    ('INPUT_OFFER_FAULT_SUMMARY=1]', 'INPUT_OFFER_FAULT_SUMMARY=1 BANK_LOCAL_IDENTITY_EQ=1]'),
    ('private-offer/closed-input/offered-summary generics',
     'private-offer/closed-input/offered-summary/bank-local-identity generics'),
    ('synthesize_retained_bank_identity.tcl clocks.xdc threads.tcl SHA256SUMS',
     'synthesize_retained_bank_identity.tcl clocks.xdc threads.tcl inspect_bank_identity.tcl SHA256SUMS'),
    ('  report_cdc -details -file [file join $output cdc_unqualified.rpt]',
     '  report_cdc -details -file [file join $output cdc_unqualified.rpt]\n'
     '  source [file join $output inspect_bank_identity.tcl]\n'
     '  pss_bank_identity_inspect $output'),
    ('RETAINED_SUMMARY_SYNTHESIS_RECORDED_NOT_TIMING_OR_DEPLOYMENT_PASS',
     'RETAINED_BANK_IDENTITY_SYNTHESIS_RECORDED_NOT_TIMING_OR_DEPLOYMENT_PASS'),
]
ADMISSION_PREFIX = '''"""UNBOUND bank-local identity admission, requiring a NEW successful actual owner.

Old offered-summary actual evidence is not authority for these three runtime
replacements. Only a separately reviewed source edit can bind a future original
owner/result/manifest. MOCK_ONLY tests cannot establish real admission.
"""
'''


def admission_edits(original):
    begin = original.index('"""')
    end = original.index('"""', begin + 3) + 4
    binding = original[original.index("EXPECTED = '"):original.index("BASE = '")]
    return [
        (original[begin:end], ADMISSION_PREFIX),
        (binding, f"EXPECTED = '{UNBOUND}'\nACCEPTED_ACTUAL = None\n"),
        ('RETAINED_SUMMARY_ACTUAL_VERIFIED', 'RETAINED_BANK_IDENTITY_ACTUAL_VERIFIED'),
        ('original offered-summary actual success', 'new original bank-local identity actual success'),
        ("'/retained_output_summary_candidate/' in name)",
         "'/retained_output_summary_candidate/' in name or '/retained_output_bank_identity_candidate/' in name)"),
        ('prepare_starlink_retained_summary_actual.py', 'prepare_starlink_retained_bank_identity_actual.py'),
    ]


CASES = {
    'helper': ('prepare_starlink_retained_summary_synthesis.py',
        '26a4e81835ca8504873e85699645e73b193e2c3e4fd5e5573a9fa18925a3858b',
        ROOT/'tools/prepare_starlink_retained_bank_identity_synthesis.py', HELPER_EDITS),
    'tcl': ('synthesize_retained_summary.tcl',
        'd233ce418555b626fe4dbeb822c46a4d1c3d1ea9e0daadb748f4d2450c688d6b',
        HERE/'synthesize_retained_bank_identity.tcl', TCL_EDITS),
    'admission': ('admission.py',
        '6d9dadfdf9fb3ad3df87a771bc151e854b65c19ab518e6dd501b1ed0f0f9cc84',
        HERE/'admission.py', admission_edits),
}


def recipe(kind):
    name, expected, target, changes = CASES[kind]
    raw = (HERE/'reference'/name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('original reference identity')
    original = raw.decode()
    changes = changes(original) if callable(changes) else changes
    text = original
    counted = []
    for before, after in changes:
        count = text.count(before)
        if count < 1 or after in text:
            raise ValueError('forward literal anchor '+before)
        counted.append(((before, after), count))
        text = text.replace(before, after)
    return target, original, text, counted


def inverse(kind, text):
    _, original, _, counted = recipe(kind)
    for (before, after), count in reversed(counted):
        if text.count(after) != count:
            raise ValueError('inverse literal count')
        text = text.replace(after, before)
    if text != original:
        raise ValueError('whole-source inverse')
    return text


def pins():
    path = HERE/'reference/summary_source_pins.json'
    if hashlib.sha256(path.read_bytes()).hexdigest() != 'f82a7d486ac37afff6a80953a3d8517166e02b615ad0ed44503931fa5e5bca1c':
        raise ValueError('original runtime inventory')
    previous = json.loads(path.read_text())['runtime']
    runtime = {}
    for name, digest in previous.items():
        leaf = Path(name).name
        if leaf in REPLACEMENTS:
            name = 'hdl/library/starlink_pss_acquisition/retained_output_bank_identity_candidate/'+leaf
            digest = REPLACEMENTS[leaf]
        runtime[name] = digest
    references = {p.relative_to(HERE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted((HERE/'reference').rglob('*')) if p.is_file()}
    for name in ('clocks.xdc','threads.tcl','route_retained_output.tcl'):
        references[name] = hashlib.sha256((HERE/name).read_bytes()).hexdigest()
    return {'kind':'UNBOUND_BANK_LOCAL_IDENTITY_PHYSICAL_RECIPE',
            'previous_physical_inventory':'1760f6d51c2438bd22ff12dfeccb18aa83a528b54ac0b71992efa27c32160a2b',
            'runtime_hdl_pin':'7e8898af9', 'actual_execution_accepted':False,
            'reference_assets':references, 'runtime':runtime}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    for kind in CASES:
        target, _, candidate, changes = recipe(kind)
        if args.write:
            with target.open('x') as stream:
                stream.write(candidate)
        inverse(kind, target.read_text())
        print(kind, len(changes), hashlib.sha256(target.read_bytes()).hexdigest())
    if args.write:
        with (HERE/'source_pins.json').open('x') as stream:
            json.dump(pins(),stream,indent=2,sort_keys=True);stream.write('\n')

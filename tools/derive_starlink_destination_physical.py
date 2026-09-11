"""Source-specific mechanical derivation of the independent destination experiment.

No vendor invocation. Original complete files are retained with whole inverses.
The accepted actual run is fixed, not a user-overridable admission shortcut.
"""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
RECOVERY = ROOT.parent
OLD = RECOVERY/'retained-summary-publish-worktree-v1'
HERE = ROOT/'tools/retained_destination_synthesis'
ACTUAL = RECOVERY/'destination-actual-parent.LQnQo9ny'
BUNDLE = RECOVERY/'destination-actual-prelaunch-parent-v1'
MANIFEST = '183a0ccce954efc48d30f598d4965459695e756e20e8ca32ba47c7ee21bf3363'
BASE = 'hdl/library/starlink_pss_acquisition/'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def put(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as handle:
        handle.write(content)

def main():
    assert not HERE.exists()
    assert sha(BUNDLE/'manifest.json') == MANIFEST
    audit = json.loads((ACTUAL/'audit.json').read_text())
    assert audit['entire_previous_result_equal'] and audit['numerical_words'] == 77953
    assert json.loads((ACTUAL/'outcome.json').read_text())['functional_accepted'] is True
    references = {
        'helper': ('tools/prepare_starlink_retained_summary_synthesis.py', '26a4e81835ca8504873e85699645e73b193e2c3e4fd5e5573a9fa18925a3858b'),
        'tcl': ('tools/retained_summary_synthesis/synthesize_retained_summary.tcl', 'd233ce418555b626fe4dbeb822c46a4d1c3d1ea9e0daadb748f4d2450c688d6b'),
        'admission': ('tools/retained_summary_synthesis/admission.py', '6d9dadfdf9fb3ad3df87a771bc151e854b65c19ab518e6dd501b1ed0f0f9cc84'),
        'tests': ('tests/test_starlink_retained_summary_synthesis.py', '1ea6534987113cc0045315efa8d42837921044cda890355c7487dcc13fbf848a'),
    }
    originals = {}
    for kind, (name, digest) in references.items():
        assert sha(OLD/name) == digest
        originals[kind] = (OLD/name).read_text()
    old_binding = originals['admission'].split('ACCEPTED_ACTUAL = ', 1)[1].split('\nBASE = ', 1)[0]
    binding = dict(manifest_sha256=MANIFEST, qualified=str(BUNDLE), actual=str(ACTUAL/'run'), owner=str(ACTUAL),
                   owner_files={name:sha(ACTUAL/name) for name in ('owner.py','execution.json','outcome.json','command.json','stdout.log','run/run_outcome.txt')},
                   results_sha256=sha(ACTUAL/'run/results.json'),
                   cli_sha256=sha(BUNDLE/'source_snapshot/tools/prepare_starlink_retained_destination_actual.py'))
    edits = {
        'helper': [
            ('Offered-summary copier; UNBOUND until original actual owner is accepted.', 'Destination copier; bound to the independently accepted actual run.'),
            ('retained_summary_synthesis', 'retained_destination_synthesis'),
            ('synthesize_retained_summary.tcl', 'synthesize_retained_destination.tcl'),
            ('prepare_starlink_retained_summary_actual.py', 'prepare_starlink_retained_destination_actual.py'),
            ("    'derive.py': 'tools/retained_destination_synthesis/derive.py',", "    'derive.py': 'tools/retained_destination_synthesis/derive.py',\n    'recipes.json': 'tools/retained_destination_synthesis/recipes.json',"),
        ],
        'tcl': [
            ('Exact offered-summary runtime; unbound until reviewed original actual success.', 'Exact contextual-destination runtime; independently accepted actual source.'),
            ('synthesize_retained_summary.tcl', 'synthesize_retained_destination.tcl'),
            ('prepare_starlink_retained_summary_actual.py', 'prepare_starlink_retained_destination_actual.py'),
            ('b5d112562b7db31164dc4a6ff92404de8e7d7d5d96b1c1b23e1a7dbac9d2c368', MANIFEST),
            ('[string match */retained_output_summary_candidate/*.v $name]) && ![string match */tb/* $name]', '[string match */retained_output_summary_candidate/*.v $name] || [string match */retained_destination_candidate/*.v $name]) && ![string match */tb/* $name] && ![string match */retained_output/starlink_pss_retained_output_owner.v $name]'),
            ('starlink_pss_fft_bank_owned_retained_output_probe', 'starlink_pss_fft_bank_owned_retained_destination_probe'),
            ('INPUT_OFFER_FAULT_SUMMARY=1]', 'INPUT_OFFER_FAULT_SUMMARY=1 CONTEXTUAL_DESTINATION_SUMMARY=1]'),
            ('closed-input/offered-summary generics', 'closed-input/offered-summary/contextual-destination generics'),
            ('RETAINED_SUMMARY_SYNTHESIS_RECORDED', 'RETAINED_DESTINATION_SYNTHESIS_RECORDED'),
        ],
        'admission': [
            ('ACCEPTED_ACTUAL = '+old_binding, 'ACCEPTED_ACTUAL = '+repr(binding)),
            ("EXPECTED = 'b5d112562b7db31164dc4a6ff92404de8e7d7d5d96b1c1b23e1a7dbac9d2c368'", "EXPECTED = '"+MANIFEST+"'"),
            ("('/retained_output/' in name or '/retained_output_summary_candidate/' in name)", "('/retained_output/' in name or '/retained_output_summary_candidate/' in name or '/retained_destination_candidate/' in name) and not name.endswith('/retained_output/starlink_pss_retained_output_owner.v')"),
            ('RETAINED_SUMMARY_ACTUAL_VERIFIED', 'RETAINED_DESTINATION_ACTUAL_VERIFIED'),
            ('prepare_starlink_retained_summary_actual.py', 'prepare_starlink_retained_destination_actual.py'),
            ('offered-summary actual', 'contextual-destination actual'),
        ],
        'tests': [
            ('retained_summary_synthesis', 'retained_destination_synthesis'),
            ('synthesize_retained_summary.tcl', 'synthesize_retained_destination.tcl'),
            ('prepare_starlink_retained_summary_actual.py', 'prepare_starlink_retained_destination_actual.py'),
            ('assert len(four)==4', 'assert len(four)==2'),
            ('RETAINED_SUMMARY_SYNTHESIS_RECORDED', 'RETAINED_DESTINATION_SYNTHESIS_RECORDED'),
        ],
    }
    targets = {'helper':ROOT/'tools/prepare_starlink_retained_destination_synthesis.py',
               'tcl':HERE/'synthesize_retained_destination.tcl', 'admission':HERE/'admission.py',
               'tests':ROOT/'tests/test_starlink_retained_destination_synthesis.py'}
    recipes = {}
    for kind, original in originals.items():
        text = original
        counts = []
        for before, after in edits[kind]:
            count = text.count(before)
            assert count > 0 and after not in text, (kind, before)
            counts.append(count)
            text = text.replace(before, after)
        inverse = text
        for (before, after), count in reversed(list(zip(edits[kind], counts))):
            assert inverse.count(after) == count
            inverse = inverse.replace(after, before)
        assert inverse == original
        reference = HERE/'reference'/Path(references[kind][0]).name
        put(reference, original)
        put(targets[kind], text)
        recipes[kind] = dict(reference=str(reference.relative_to(HERE)), sha256=references[kind][1],
                             target=str(targets[kind].relative_to(ROOT)), edits=edits[kind], counts=counts)
    put(HERE/'recipes.json', json.dumps(recipes, indent=2)+'\n')
    oldpins = json.loads((OLD/'tools/retained_summary_synthesis/source_pins.json').read_text())
    pins = dict(kind='SOURCE_MATCHED_DESTINATION_PHYSICAL_RECIPE', reference_assets={}, runtime=dict(oldpins['runtime']))
    replacements = {
        BASE+'retained_output_summary_candidate/starlink_pss_fft_bank_owned_retained_output_probe.v': 'starlink_pss_fft_bank_owned_retained_destination_probe.v',
        BASE+'retained_output_summary_candidate/starlink_pss_fft_retained_output_impl.v': 'starlink_pss_fft_retained_destination_impl.v',
        BASE+'retained_output/starlink_pss_retained_output_owner.v': 'starlink_pss_retained_destination_owner.v',
    }
    for old, new in replacements.items():
        del pins['runtime'][old]
        path = BASE+'retained_destination_candidate/'+new
        pins['runtime'][path] = sha(BUNDLE/'source_snapshot'/path)
    assert len(pins['runtime']) == 16
    for name in ('clocks.xdc','threads.tcl','route_retained_output.tcl','reference/create_shared_realtime_xfft_ip.tcl'):
        source = OLD/'tools/retained_summary_synthesis'/name
        target = HERE/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        assert sha(target) == oldpins['reference_assets'][name]
    for name, digest in pins['runtime'].items():
        source = BUNDLE/'source_snapshot'/name
        assert sha(source) == digest
        if '/retained_output_summary_candidate/' in name or '/retained_destination_candidate/' in name:
            target = HERE/'reference/runtime'/Path(name).name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    for path in sorted(HERE.rglob('*')):
        if path.is_file() and (path.is_relative_to(HERE/'reference') or path.name in ('clocks.xdc','threads.tcl','route_retained_output.tcl')):
            pins['reference_assets'][str(path.relative_to(HERE))] = sha(path)
    put(HERE/'source_pins.json', json.dumps(pins, indent=2)+'\n')
    print(json.dumps(dict(whole_inverses=True, runtime_files=16, recipes=list(recipes), vendor_invoked=False)))

if __name__ == '__main__':
    main()

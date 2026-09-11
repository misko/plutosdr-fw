"""Read-only gate bound to the reviewed original offered-summary actual run.

No CLI can provide/override this binding. Original owner/result/source pins are
fixed here; real physical preparation and vendor execution still need review.
Tests may monkeypatch this module inside explicitly marked MOCK_ONLY fixtures;
that is not a real accepted run or an executable physical preparation.
"""
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
EXPECTED = 'b5d112562b7db31164dc4a6ff92404de8e7d7d5d96b1c1b23e1a7dbac9d2c368'
ACCEPTED_ACTUAL = {
    'manifest_sha256': 'b5d112562b7db31164dc4a6ff92404de8e7d7d5d96b1c1b23e1a7dbac9d2c368',
    'qualified': '/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-summary-actual-prelaunch-v1',
    'actual': '/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-summary-actual-parent.XYAbt6Np/run',
    'owner': '/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-summary-actual-parent.XYAbt6Np',
    'owner_files': {
        'owner.py': 'e60edf3106189468601f4d5def0e0aaefca6cd442ac42c4dc27ea50e3889717f',
        'execution.json': '3e87e9cfcb1fc2bca476ae27a8f47552355e55d6e9ba518c470d2bb548ff6783',
        'outcome.json': 'cdc5bdae42a199ad0d604ff9ee9b0e27b3c29207f942e6b3f8792605b7d451ac',
        'command.json': 'a41db3307f827367d8761e73f9f366fb30586c7d62ab83f21774641e380c4351',
        'stdout.log': 'a8e2dfb9f00edd946d4b851a109dc7df4cbc25f65315a7b827f4892df29b6cee',
        'run/run_outcome.txt': '9c8daa782fbaed9a06a183e16209ce4389d3a27726c283bfb590a39c65716b88',
    },
    'results_sha256': '6605a2db8c69ffb94bea47e421f76fae5af9a473c5f05d81f5a344329eb2185e',
    'cli_sha256': 'e0d91e6c5942e6a6d6d2a358e6e9f0c485c7e6d7ea3078eba2874f25f3107875',
}
BASE = 'hdl/library/starlink_pss_acquisition/'
WRAPPER = 'a3a650654118016012bdfb8553114ee4a89866466d8ca774fa0f281640168a68'
MARKER = 'RETAINED_SUMMARY_ACTUAL_VERIFIED_SEVEN_CONTEXTS_NO_CONTINUOUS_OR_PHYSICAL_CLAIM'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe(path):
    require(path.is_absolute() and '..' not in path.parts and
            not any(p.is_symlink() for p in (path, *path.parents)), 'absolute non-symlink identity')
    return path


def load_binding(expected):
    require(ACCEPTED_ACTUAL is not None and re.fullmatch('[0-9a-f]{64}', expected) is not None,
            'UNBOUND: no reviewed original offered-summary actual success')
    require(expected == EXPECTED == ACCEPTED_ACTUAL['manifest_sha256'], 'accepted actual manifest binding')
    require(set(ACCEPTED_ACTUAL) == {'manifest_sha256','qualified','actual','owner',
            'owner_files','results_sha256','cli_sha256'}, 'source-specific binding fields')
    require(set(ACCEPTED_ACTUAL['owner_files']) == {'owner.py','execution.json','outcome.json',
            'command.json','stdout.log','run/run_outcome.txt'}, 'complete original owner receipt binding')
    return ACCEPTED_ACTUAL


def check_result(actual, result):
    binding = load_binding(EXPECTED)
    require(str(safe(actual)) == binding['actual'], 'accepted original actual path')
    require(digest(actual/'results.json') == binding['results_sha256'], 'accepted complete result bytes')
    require(json.loads(result) == json.loads((actual/'results.json').read_text()), 'full numerical/service result equality')


def admit(qualified, actual, expected):
    binding = load_binding(expected)
    qualified, actual = safe(qualified), safe(actual)
    require(str(qualified) == binding['qualified'] and str(actual) == binding['actual'],
            'original qualified/actual path binding')
    owner = safe(Path(binding['owner']))
    require(actual == owner/'run', 'original owner/run join')
    pins = json.loads((HERE/'source_pins.json').read_text())
    require(digest(qualified/'manifest.json') == expected and
            digest(actual/'inputs/manifest.json') == expected, 'original and executed manifest identity')
    manifest = json.loads((qualified/'manifest.json').read_text())
    require(manifest.get('actual_execution') is False and manifest.get('source_before_after_equal') is True,
            'qualified source manifest flags')
    compiled = manifest['compiled']
    runtime = [name for name in compiled if name.endswith('.v') and '/tb/' not in name and
               ('/retained_output/' in name or '/retained_output_summary_candidate/' in name)]
    expected_runtime = {'source_snapshot/'+name: value for name, value in pins['runtime'].items()}
    require(len(runtime) == 16 and set(runtime) == set(expected_runtime), 'exact sixteen actual runtime paths')
    for name, value in expected_runtime.items():
        require(digest(safe(qualified/name)) == value and digest(safe(actual/'inputs'/name)) == value,
                'source-matched actual runtime '+name)
    for name, value in binding['owner_files'].items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'owner receipt relative path')
        require(digest(safe(owner/name)) == value, 'accepted owner receipt hash '+name)
    execution = json.loads((owner/'execution.json').read_text())
    outcome = json.loads((owner/'outcome.json').read_text())
    for record in (execution, outcome):
        require(type(record.get('vendor_exit')) is int and record['vendor_exit'] == 0 and
                record.get('timed_out') is False and record.get('interruption') is None,
                'original owner terminal failure')
    require(all(type(outcome.get(key)) is int and outcome[key] == 0 for key in
                ('original_check_exit', 'copied_check_exit', 'independent_result_exit')),
            'original actual verification failure')
    require(outcome.get('functional_accepted') is True and
            outcome.get('generated_wrapper_matches_known') is True and
            outcome.get('generated_wrapper_sha256') == WRAPPER and
            outcome.get('physical_qualified') is False and outcome.get('deployment_eligible') is False,
            'actual acceptance/source scope')
    wrapper = actual/'project/retained_output_actual.gen/sources_1/ip/starlink_pss_fft512_bfp18_rt_candidate/synth/starlink_pss_fft512_bfp18_rt_candidate.vhd'
    require(digest(safe(wrapper)) == WRAPPER, 'original generated FFT source bytes')
    command = json.loads((owner/'command.json').read_text())['command']
    position = command.index('-tclargs')
    require(command[position+1] == str(qualified) and command[position+3] == expected and
            command[position+4] == str(actual), 'original launch source/manifest/output join')
    require((owner/'stdout.log').read_text().splitlines().count(MARKER) == 1,
            'unique original automation completion')
    outcome_text = (actual/'run_outcome.txt').read_text()
    require(re.findall(r'^run_status=(.*)$', outcome_text, re.M) == ['0'], 'original runner success')
    require(digest(actual/'results.json') == binding['results_sha256'], 'accepted complete result bytes')
    require(digest(qualified/'source_snapshot/tools/prepare_starlink_retained_summary_actual.py') ==
            binding['cli_sha256'], 'accepted frozen actual CLI')
    return {'manifest_sha256': expected, 'actual': str(actual), 'runtime_files': 16,
            'vendor_invoked': False, 'actual_success_reused_not_rewritten': True}

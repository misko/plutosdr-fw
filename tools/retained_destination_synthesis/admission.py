"""Read-only gate bound to the reviewed original contextual-destination actual run.

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
EXPECTED = '183a0ccce954efc48d30f598d4965459695e756e20e8ca32ba47c7ee21bf3363'
ACCEPTED_ACTUAL = {'manifest_sha256': '183a0ccce954efc48d30f598d4965459695e756e20e8ca32ba47c7ee21bf3363', 'qualified': '/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/destination-actual-prelaunch-parent-v1', 'actual': '/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/destination-actual-parent.LQnQo9ny/run', 'owner': '/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/destination-actual-parent.LQnQo9ny', 'owner_files': {'owner.py': 'f107ba2380e51f0cb744b387c014944b40b6038c00425a431eaa7043041a40b9', 'execution.json': 'f1be2f4d5fcb4bda75a36c60876082bb40556090ceaa0d11c4da296dde9200db', 'outcome.json': '9209dd7026d01549c9d946032cf7724a5f21db047c110694dece549f9fb396d4', 'command.json': '033fbb5fa9028f93814854d770953dc7f9319e17d7d2f8c092d5269ac223ac82', 'stdout.log': '30fd9474f26089e9fc1fdfece4239125fbf18b8b7182e7626ae5039f644ee85e', 'run/run_outcome.txt': '578abe39508efcfe313dceea39ce5c20218dcdd2b44fda221758c79b4e7efc02'}, 'results_sha256': '54bb594b9835fd080a66a96c9bdf061ef0106889063d0210bfd5416dba189906', 'cli_sha256': 'dc7b05033cfc1c6d8b799e483978c4c9a9671d6986b392a135e1916f5885fe0f'}
BASE = 'hdl/library/starlink_pss_acquisition/'
WRAPPER = 'a3a650654118016012bdfb8553114ee4a89866466d8ca774fa0f281640168a68'
MARKER = 'RETAINED_DESTINATION_ACTUAL_VERIFIED_SEVEN_CONTEXTS_NO_CONTINUOUS_OR_PHYSICAL_CLAIM'


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
            'UNBOUND: no reviewed original contextual-destination actual success')
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
               ('/retained_output/' in name or '/retained_output_summary_candidate/' in name or '/retained_destination_candidate/' in name) and not name.endswith('/retained_output/starlink_pss_retained_output_owner.v')]
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
    require(digest(qualified/'source_snapshot/tools/prepare_starlink_retained_destination_actual.py') ==
            binding['cli_sha256'], 'accepted frozen actual CLI')
    return {'manifest_sha256': expected, 'actual': str(actual), 'runtime_files': 16,
            'vendor_invoked': False, 'actual_success_reused_not_rewritten': True}

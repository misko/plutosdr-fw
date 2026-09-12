"""Curated actual-FFT and physical evidence; no full receiver promotion."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from staged_fft_experiment import require, sha, verify
from route_private_replay_sequence import evidence
from write_evidence_archive_stream import write_verified_archive
from private_replay_sequence_experiment_v3 import witness
import buffered_forward_experiment as main


def passing_tests(path, count):
    tree = ET.parse(path)
    require(len(list(tree.iter('testcase'))) == count, 'exact test count')
    require(not any(list(tree.iter(tag)) for tag in ['failure', 'error', 'skipped']), 'all tests pass')
    return count


def same_audit(actual, saved):
    # JSON round-tripping turns context tuples into lists; compare serialized
    # values, not Python container identities. Numerical content stays exact.
    require(json.dumps(actual, sort_keys=True) == json.dumps(saved, sort_keys=True), 're-audited smoke arithmetic')


def record(root):
    checked = evidence(root/'actual-v1', root/'synth-v1', root/'aux-v3')
    total = passing_tests(root/'regression-v3.xml', 2107)
    passing_tests(root/'regression-v2.xml', 2103)
    passing_tests(root/'regression-v1.xml', 2101)
    passing_tests(root/'component-v1.xml', 24)
    passing_tests(root/'component-v2.xml', 36)
    passing_tests(root/'route-tests-v1.xml', 79)
    passing_tests(root/'reporting-tests-v1.xml', 81)
    passing_tests(root/'stimulus-tests-v1.xml', 83)
    failed = json.loads((root/'smoke-v1/outcome.json').read_text())
    require(failed.get('passed') is False and 'error' in failed, 'retain rejected early slow-fault assertion')
    failed_aux = json.loads((root/'aux-v2/outcome.json').read_text())
    require(failed_aux.get('passed') is False and 'error' in failed_aux, 'retain unmatched forced-ready stimulus failure')
    smoke = json.loads((root/'smoke-v3/smoke_outcome.json').read_text())
    require(smoke.get('passed') is True and smoke.get('full_campaign') is False, 'focused actual smoke passed')
    verify(Path(smoke['command'][-3]), smoke['prepared_sha'])
    require(smoke['private_replay_protocol'] == witness((root/'smoke-v3/project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text(), True), 're-audited focused witness')
    same_audit(main.audit(root/'smoke-v3'), smoke['audit'])
    route = json.loads((root/'route-v1/audit.json').read_text())
    outcome = json.loads((root/'route-v1/outcome.json').read_text())
    require(outcome.get('returncode') == 0 and outcome.get('sources_unchanged') is True and 'error' not in outcome, 'terminal route')
    require(all(sha(Path(p)) == value for p,value in outcome['before'].items()), 'route source receipts')
    require(sha(root/'route-v1/route/retained_output_routed.dcp') == outcome['routed_dcp_sha'], 'actual routed checkpoint')
    require(route['source_and_checkpoint_verified'] is True and route['routing_errors'] == 0, 'route observation')
    require(route['full_receiver_or_physical_signoff'] is False and route['deployment_eligible'] is False, 'no receiver promotion')
    endpoints = json.loads((root/'endpoints-v1/outcome.json').read_text())
    require(endpoints.get('passed') is True and endpoints.get('sources_unchanged') is True, 'physical endpoints observed')
    require(all(sha(Path(p)) == value for p,value in endpoints['before'].items()), 'endpoint source receipts')
    parent_endpoints = json.loads((root/'parent-endpoints-v1/outcome.json').read_text())
    require(parent_endpoints.get('passed') is True and parent_endpoints.get('sources_unchanged') is True, 'parent endpoints observed')
    require(all(sha(Path(p)) == value for p,value in parent_endpoints['before'].items()), 'parent endpoint receipts')
    assessment = dict(source_evidence=checked, tests=total, focused_smoke=smoke, route=route, endpoints=endpoints,
        parent_endpoints=parent_endpoints, rejected_smoke=failed, rejected_auxiliary=failed_aux,
        runtime_modules=41, unchanged_parent_modules=39, actual_auxiliary_cases=82,
        receiver_integrated=False, radios_accessed=[], deployment_eligible=False,
        regression_generated_payloads='Retained in local regression-v1/v2/v3; archive includes passing XML and focused component artifacts, not historical generated regression payloads.')
    with (root/'assessment.json').open('x') as output:
        output.write(json.dumps(assessment, indent=2)+'\n')
    sources = {}
    def add(name, path):
        require(name not in sources and path.is_file() and not path.is_symlink(), 'regular unique archive member')
        sources[name] = path
    add('assessment.json', root/'assessment.json')
    for name in ['regression-v1', 'regression-v2', 'regression-v3', 'component-v1', 'component-v2', 'route-tests-v1', 'reporting-tests-v1', 'stimulus-tests-v1']:
        add('tests/'+name+'.xml', root/(name+'.xml'))
    for name in ['component-v1', 'component-v2']:
        for path in sorted((root/name).rglob('*')):
            if path.is_file() and not path.is_symlink() and not any(p.is_symlink() for p in path.parents) and path.suffix in {'.sv', '.v', '.log'}:
                add('tests/'+str(path.relative_to(root)), path)
    for name in ['prepared-v1', 'smoke-prepared-v1', 'smoke-prepared-v2', 'smoke-prepared-v3', 'aux-prepared-v2', 'aux-prepared-v3']:
        for path in sorted((root/name).iterdir()):
            if path.is_file(): add(name+'/'+path.name, path)
    for name in ['actual-v1', 'smoke-v1', 'smoke-v2', 'smoke-v3', 'aux-v2', 'aux-v3', 'synth-v1', 'route-v1', 'endpoints-v1', 'parent-endpoints-v1']:
        folder = root/name
        for path in sorted(folder.iterdir()):
            if path.is_file(): add(name+'/'+path.name, path)
        if name in ['route-v1', 'endpoints-v1', 'parent-endpoints-v1']:
            child = 'route' if name == 'route-v1' else 'reports'
            for path in sorted((folder/child).iterdir()):
                if path.is_file(): add(name+'/'+child+'/'+path.name, path)
        if name in ['actual-v1', 'smoke-v1', 'smoke-v2', 'smoke-v3', 'aux-v2', 'aux-v3']:
            sim = folder/'project/staged_fft.sim/sim_1/behav/xsim'
            for filename in ['simulate.log', 'buffered_words.csv', 'xvlog.log', 'xvhdl.log', 'elaborate.log']:
                add(name+'/sim/'+filename, sim/filename)
            wrapper = folder/'project/staged_fft.gen/sources_1/ip/starlink_pss_fft512_bfp18_rt_candidate/synth/starlink_pss_fft512_bfp18_rt_candidate.vhd'
            add(name+'/generated_fft.vhd', wrapper)
    for pattern in ['tools/*private_replay_sequence*', 'tests/test_starlink_private_replay_sequence*', 'tests/test_starlink_private_replay_fault_reporting.py', 'tests/test_starlink_private_replay_stimulus.py',
                    'tools/*evidence_archive_stream.py', 'tests/test_evidence_archive_stream*.py', 'tests/test_record_product_publication_cone.py',
                    'docs/starlink-private-replay-sequence-*.md']:
        for path in sorted(main.ROOT.glob(pattern)):
            add('source/'+str(path.relative_to(main.ROOT)), path)
    return write_verified_archive(root/'20260912-private-replay-sequence-evidence.tgz', sources)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    print(json.dumps(record(parser.parse_args().root), indent=2))

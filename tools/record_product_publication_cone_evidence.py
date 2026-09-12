"""Curated actual-FFT and physical evidence; no full receiver promotion."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from staged_fft_experiment import require, sha, verify
from route_product_publication_cone import evidence
from write_evidence_archive_stream import write_verified_archive
from product_publication_cone_experiment import witness
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
    checked = evidence(root/'actual-v1', root/'synth-v1', root/'aux-v1')
    total = passing_tests(root/'regression-v1.xml', 1977) + passing_tests(root/'archive-tests-v1.xml', 7) + passing_tests(root/'recorder-tests-v1.xml', 2)
    passing_tests(root/'component-v1.xml', 8)
    passing_tests(root/'component-v2.xml', 22)
    passing_tests(root/'route-tests-v1.xml', 79)
    smoke = json.loads((root/'smoke-v1/smoke_outcome.json').read_text())
    require(smoke.get('passed') is True and smoke.get('full_campaign') is False, 'focused actual smoke passed')
    verify(Path(smoke['command'][-3]), smoke['prepared_sha'])
    require(smoke['publication_protocol'] == witness((root/'smoke-v1/project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text(), True), 're-audited focused witness')
    same_audit(main.audit(root/'smoke-v1'), smoke['audit'])
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
    source_paths = {}
    for name in ['parent-sources-v1', 'candidate-sources-v1']:
        source_paths[name] = json.loads((root/name/'outcome.json').read_text())
        observation = source_paths[name]
        require(observation.get('passed') is True and observation.get('sources_unchanged') is True, 'source-specific observation')
        require(all(sha(Path(p)) == value for p,value in observation['before'].items()), 'source-specific receipts')
    assessment = dict(source_evidence=checked, tests=total, focused_smoke=smoke, route=route, endpoints=endpoints,
        source_specific_paths=source_paths,
        runtime_modules=40, unchanged_parent_modules=39, actual_auxiliary_cases=79,
        receiver_integrated=False, radios_accessed=[], deployment_eligible=False,
        regression_generated_payloads='Retained in local regression-v1; archive includes passing XML and focused component artifacts, not historical generated regression payloads.')
    with (root/'assessment.json').open('x') as output:
        output.write(json.dumps(assessment, indent=2)+'\n')
    sources = {}
    def add(name, path):
        require(name not in sources and path.is_file() and not path.is_symlink(), 'regular unique archive member')
        sources[name] = path
    add('assessment.json', root/'assessment.json')
    for name in ['regression-v1', 'component-v1', 'component-v2', 'route-tests-v1', 'archive-tests-v1', 'recorder-tests-v1']:
        add('tests/'+name+'.xml', root/(name+'.xml'))
    for name in ['component-v1', 'component-v2']:
        for path in sorted((root/name).rglob('*')):
            if path.is_file() and not path.is_symlink() and not any(p.is_symlink() for p in path.parents) and path.suffix in {'.sv', '.v', '.log'}:
                add('tests/'+str(path.relative_to(root)), path)
    for name in ['prepared-v1', 'smoke-prepared-v1', 'aux-prepared-v1']:
        for path in sorted((root/name).iterdir()):
            if path.is_file(): add(name+'/'+path.name, path)
    for name in ['actual-v1', 'smoke-v1', 'aux-v1', 'synth-v1', 'route-v1', 'endpoints-v1', 'inspection-v1', 'parent-sources-v1', 'candidate-sources-v1']:
        folder = root/name
        for path in sorted(folder.iterdir()):
            if path.is_file(): add(name+'/'+path.name, path)
        if name in ['route-v1', 'endpoints-v1', 'inspection-v1', 'parent-sources-v1', 'candidate-sources-v1']:
            child = 'route' if name == 'route-v1' else 'reports'
            for path in sorted((folder/child).iterdir()):
                if path.is_file(): add(name+'/'+child+'/'+path.name, path)
        if name in ['actual-v1', 'smoke-v1', 'aux-v1']:
            sim = folder/'project/staged_fft.sim/sim_1/behav/xsim'
            for filename in ['simulate.log', 'buffered_words.csv', 'xvlog.log', 'xvhdl.log', 'elaborate.log']:
                add(name+'/sim/'+filename, sim/filename)
            wrapper = folder/'project/staged_fft.gen/sources_1/ip/starlink_pss_fft512_bfp18_rt_candidate/synth/starlink_pss_fft512_bfp18_rt_candidate.vhd'
            add(name+'/generated_fft.vhd', wrapper)
    for pattern in ['tools/*product_publication_cone*', 'tests/test_starlink_product_publication_cone*',
                    'tools/*evidence_archive_stream.py', 'tests/test_evidence_archive_stream*.py', 'tests/test_record_product_publication_cone.py',
                    'docs/starlink-product-publication-cone-*.md']:
        for path in sorted(main.ROOT.glob(pattern)):
            add('source/'+str(path.relative_to(main.ROOT)), path)
    return write_verified_archive(root/'20260912-product-publication-cone-evidence.tgz', sources)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    print(json.dumps(record(parser.parse_args().root), indent=2))

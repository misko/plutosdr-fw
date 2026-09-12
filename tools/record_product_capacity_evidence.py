"""Curated route and functional evidence for a deliberately slower product slot."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from staged_fft_experiment import require,sha,verify
from product_capacity_evidence import evidence
from write_evidence_archive_stream import write_verified_archive

ROOT=Path(__file__).resolve().parents[1]

def record(root):
    checked=evidence(root/'actual-v1',root/'synth-v1',root/'aux-v2')
    regression=json.loads((root/'regression-v1/outcome.json').read_text())
    require(regression.get('passed') is True and regression['tests']==2229,'full scoped regression')
    require(all(sha(Path(p))==v for p,v in regression['test_sources'].items()),'unchanged regression source')
    for file,count in [('component-v1.xml',15),('component-v3.xml',33),('component-v5.xml',40),('regression-v1/tests.xml',2229)]:
        tree=ET.parse(root/file)
        require(len(list(tree.iter('testcase')))==count and not any(list(tree.iter(t)) for t in ['failure','error','skipped']),'passing scoped tests')
    for file,count in [('component-v2.xml',2),('component-v4.xml',1)]:
        require(len(list(ET.parse(root/file).iter('failure')))==count,'retain rejected test-count assumptions')
    failed=json.loads((root/'aux-v1/outcome.json').read_text())
    require(failed.get('passed') is False and failed['error']=="ValueError('simulation failure')",'retain missed corruption failure')
    log=(root/'aux-v1/project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
    require('fault not quarantined case=3' in log,'exact failed fault injection')
    route=json.loads((root/'route-v1/outcome.json').read_text());endpoint=json.loads((root/'endpoints-v1/outcome.json').read_text())
    for receipt in [route,endpoint]:
        require(receipt.get('returncode')==0 and receipt.get('sources_unchanged') is True,'completed physical observation')
        require(all(sha(Path(p))==v for p,v in receipt['before'].items()),'physical inputs unchanged')
    require(sha(root/'route-v1/route/retained_output_routed.dcp')==route['routed_dcp_sha'],'routed checkpoint identity')
    require(route['exploratory_only'] is True and route['deployment_eligible'] is False and endpoint.get('passed') is True,'unpromoted route scope')
    audit=json.loads((root/'route-v1/audit.json').read_text())
    require(audit['internal_timing_pass'] is False and audit['deployment_eligible'] is False,'timing still fails')
    assessment=dict(qualified=checked,route=audit,endpoints=endpoint['endpoint_slack_ns'],tests=2229,
        regression_scope=regression['scope'],whole_repository_suite=False,
        rejected_auxiliary=failed,radio_access=[],primary_hdl_promoted=False,deployment_eligible=False)
    sources={}
    def add(name,path):
        require(name not in sources and path.is_file() and not path.is_symlink(),'unique regular evidence source')
        sources[name]=path
    for name in ['prepared-v1','aux-prepared-v1','aux-prepared-v2']:
        folder=root/name;verify(folder,sha(folder/'SHA256SUMS'))
        for path in sorted(folder.iterdir()):
            if path.is_file():add(name+'/'+path.name,path)
    for name in ['actual-v1','aux-v1','aux-v2','synth-v1','route-v1','endpoints-v1']:
        folder=root/name
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.suffix in {'.json','.log','.sha256','.dcp','.py','.tcl'}:add(name+'/'+path.name,path)
        if name in ['route-v1','endpoints-v1']:
            child='route' if name=='route-v1' else 'reports'
            for path in sorted((folder/child).iterdir()):
                if path.is_file():add(name+'/'+child+'/'+path.name,path)
        if name in ['actual-v1','aux-v1','aux-v2']:
            sim=folder/'project/staged_fft.sim/sim_1/behav/xsim'
            for f in ['simulate.log','buffered_words.csv','xvlog.log','xvhdl.log','elaborate.log']:add(name+'/sim/'+f,sim/f)
            wrapper=folder/'project/staged_fft.gen/sources_1/ip/starlink_pss_fft512_bfp18_rt_candidate/synth/starlink_pss_fft512_bfp18_rt_candidate.vhd'
            add(name+'/generated_fft.vhd',wrapper)
    for name in ['component-v1','component-v2','component-v3','component-v4','component-v5']:
        add('tests/'+name+'.xml',root/(name+'.xml'))
        for path in sorted((root/name).rglob('*')):
            if path.is_file() and not path.is_symlink() and not any(p.is_symlink() for p in path.parents) and path.suffix in {'.v','.sv','.log'}:
                add('tests/'+str(path.relative_to(root)),path)
    for path in (root/'regression-v1').iterdir():
        if path.is_file():add('tests/regression-v1/'+path.name,path)
    for pattern in ['tools/*product*capacity*.py','tests/test_starlink_product*capacity*.py',
                    'tools/*evidence_archive_stream.py']:
        for path in ROOT.glob(pattern):
            name='source/'+str(path.relative_to(ROOT))
            if name not in sources:add(name,path)
    with (root/'product-capacity-assessment.json').open('x') as output:output.write(json.dumps(assessment,indent=2)+'\n')
    add('product-capacity-assessment.json',root/'product-capacity-assessment.json')
    return write_verified_archive(root/'20260912-product-registered-capacity-evidence.tgz',sources)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path)
    print(json.dumps(record(parser.parse_args().root),indent=2))

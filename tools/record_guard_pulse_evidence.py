"""Archive measured guard-pulse work without claiming receiver signoff."""
import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import buffered_forward_experiment as actual
import guard_pulse_experiment as healthy
import guard_pulse_experiment_v3 as extended
from staged_fft_experiment import require,sha,verify
from write_evidence_archive_stream import write_verified_archive
ROOT=Path(__file__).resolve().parents[1]

def record(root,auxiliary,regression_name):
    receipts={}
    for name in ['actual-v1','synth-v1',auxiliary]:
        receipt=json.loads((root/name/'guard_pulse_outcome.json').read_text())
        require(receipt.get('passed') is True and receipt['returncode']==0,'terminal passing actual FFT evidence')
        prepared=Path(receipt['command'][-3]);verify(prepared,receipt['prepared_sha'])
        require(all(sha(Path(p))==v for p,v in json.loads((prepared/'snapshot.json').read_text())['sources'].items()),'pinned sources unchanged')
        receipts[name]=receipt
    main=Path(receipts['actual-v1']['command'][-3])
    synth=Path(receipts['synth-v1']['command'][-3])
    aux=Path(receipts[auxiliary]['command'][-3])
    require(main==synth and receipts['actual-v1']['prepared_sha']==receipts['synth-v1']['prepared_sha'],'same synthesized healthy source')
    names=re.search(r'set runtime_names \{([^}]+)\}',(main/'profile.tcl').read_text())[1].split()
    require(len(names)==45 and all((main/n).read_bytes()==(aux/n).read_bytes() for n in names),'same 45 runtime files for full fault campaign')
    for name,checker,is_aux in [('actual-v1',healthy,False),(auxiliary,extended,True)]:
        require(json.dumps(actual.audit(root/name),sort_keys=True)==json.dumps(receipts[name]['audit'],sort_keys=True),'fresh numerical audit')
        log=(root/name/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
        require(checker.witness(log,is_aux)==receipts[name]['guard_pulse'],'fresh original-guard witnesses')
        require(checker.base.witness(log,is_aux)==receipts[name]['retry_admission'],'fresh original admission and all ten direct boundaries')
    reg=json.loads((root/regression_name/'outcome.json').read_text())
    require(reg.get('passed') is True and reg['tests']==2390,'complete inherited scoped regression plus new tests')
    require(all(sha(Path(p))==v for p,v in reg['test_sources'].items()),'regression sources unchanged')
    tree=ET.parse(root/regression_name/'tests.xml')
    require(len(list(tree.iter('testcase')))==2390 and not any(list(tree.iter(t)) for t in ['failure','error','skipped']),'passing test XML')
    for name in ['route-v1','endpoints-v1','admission-endpoints-v1','parent-admission-endpoints-v1']:
        receipt=json.loads((root/name/'outcome.json').read_text())
        require(receipt['returncode']==0 and receipt['sources_unchanged'] is True,'completed physical observation')
        require(all(sha(Path(p))==v for p,v in receipt['before'].items()),'physical inputs unchanged')
    route=json.loads((root/'route-v1/outcome.json').read_text())
    require(sha(root/'route-v1/route/retained_output_routed.dcp')==route['routed_dcp_sha'],'routed checkpoint')
    audit=json.loads((root/'route-v1/audit.json').read_text())
    require(audit['internal_timing_pass'] is False and audit['deployment_eligible'] is False,'this is an unpromoted failed-timing experiment')
    # Verify the tested full-frame template and unmutated candidate copies,
    # rather than relying only on test-module hashes.
    rtl=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
    template=(rtl/'tb_guard_commit_pulse.sv').read_text()
    candidate=(rtl/'starlink_pss_result_guard_commit_pulse.v').read_bytes()
    matched=[]
    for folder in (root/'component-v4').iterdir():
        log=folder/'simulate.log'
        if folder.is_symlink() or not log.is_file():continue
        if 'GUARD_PULSE_COMPONENT_PASS' not in log.read_text():continue
        require((folder/'guard.v').read_bytes()==candidate,'unmutated tested guard')
        modes=[mode for mode in [0,1] if (folder/'tb.sv').read_text()==template.replace('__PRIVATE_ACK__',str(mode))]
        require(len(modes)==1,'exact tested frame/unknown/ACK template')
        matched+=modes
    require(sorted(matched)==[0,1],'both actual private-ACK modes proved')
    phase=json.loads((root/'component-phase-v1/outcome.json').read_text())
    require(phase['passed'] is True and phase['runtime_changed'] is False and phase['vectors']==262144,'prospective phase proof')
    require(all(sha(Path(p))==v for p,v in phase['before'].items()),'phase proof source identity')
    for name,run in phase['runs'].items():
        require(sha(root/'component-phase-v1'/name/'simulate.log')==run['log_sha256'],'phase proof log identity')
    assessment=dict(actual=receipts,route=audit,scoped_tests=2390,whole_repository_suite=False,
                    actual_fault_cases=92,radio_access=[],primary_hdl_promoted=False,deployment_eligible=False)
    with (root/'guard-pulse-assessment.json').open('x') as out:out.write(json.dumps(assessment,indent=2)+'\n')
    sources={}
    def add(name,path):
        require(name not in sources and path.is_file() and not path.is_symlink(),'unique regular source')
        sources[name]=path
    for folder in sorted(root.iterdir()):
        if not folder.is_dir():continue
        if folder.name.startswith(('prepared-','aux-prepared-')):
            for p in sorted(folder.iterdir()):
                if p.is_file():add(folder.name+'/'+p.name,p)
        elif folder.name.startswith(('actual-','aux-v','synth-','route-','endpoints-','admission-endpoints-','parent-admission-endpoints-')):
            for p in sorted(folder.iterdir()):
                if p.is_file() and p.suffix in {'.json','.log','.sha256','.dcp','.py','.tcl'}:add(folder.name+'/'+p.name,p)
            for child in ['route','reports']:
                if (folder/child).is_dir():
                    for p in sorted((folder/child).iterdir()):
                        if p.is_file():add(folder.name+'/'+child+'/'+p.name,p)
            sim=folder/'project/staged_fft.sim/sim_1/behav/xsim'
            if sim.is_dir():
                for name in ['simulate.log','buffered_words.csv','xvlog.log','xvhdl.log','elaborate.log']:
                    if (sim/name).is_file():add(folder.name+'/sim/'+name,sim/name)
        elif folder.name.startswith('regression-'):
            for p in sorted(folder.iterdir()):
                if p.is_file() and p.suffix in {'.json','.xml','.log'}:add('tests/'+str(p.relative_to(root)),p)
        elif folder.name.startswith('component-'):
            for p in sorted(folder.rglob('*')):
                if p.is_file() and not p.is_symlink() and not any(q.is_symlink() for q in p.parents) and p.suffix in {'.json','.xml','.log','.sv','.v'}:
                    add('tests/'+str(p.relative_to(root)),p)
    for p in root.glob('component-*.xml'):add('tests/'+p.name,p)
    add('source/tb_guard_commit_pulse.sv',rtl/'tb_guard_commit_pulse.sv')
    add('guard-pulse-assessment.json',root/'guard-pulse-assessment.json')
    for pattern in ['tools/*guard_pulse*','tests/test_starlink_guard_pulse*',
                    'tools/*evidence_archive_stream.py']:
        for p in ROOT.glob(pattern):
            if p.is_file():add('source/'+str(p.relative_to(ROOT)),p)
    return write_verified_archive(root/'20260912-guard-pulse-evidence.tgz',sources)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path)
    parser.add_argument('--auxiliary',default='aux-v3');parser.add_argument('--regression',default='regression-v2')
    args=parser.parse_args();print(json.dumps(record(args.root,args.auxiliary,args.regression),indent=2))

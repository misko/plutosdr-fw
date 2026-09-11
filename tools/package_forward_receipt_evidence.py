"""Preserve RAM-backed receipt experiment with explicit pinned parent dependency."""
import argparse
import json
from pathlib import Path

from package_staged_fft_evidence import write_verified_archive
from staged_fft_experiment import ROOT, audit_forwardreceipt, audit_productstage, audit_finalcapacity, audit_splitcapacity, require, sha, verify
from route_starlink_staged_fft import verify_ack_auxiliary


def package(artifacts,output,campaign='forwardreceipt'):
    require(artifacts.is_absolute() and artifacts.is_dir(),'absolute artifact root required')
    require(campaign in {'forwardreceipt','productstage','finalcapacity','splitcapacity'},'explicit supported campaign')
    product=campaign=='productstage';split=campaign=='splitcapacity'
    final=campaign in {'finalcapacity','splitcapacity'};version=2 if product else 1
    main=artifacts/f'sim-v{version}';aux=artifacts/f'ack-v{version}';prepared=artifacts/f'prepared-v{version}'
    synthesis=artifacts/f'synth-v{version}';route=artifacts/f'route-v{version}'
    expected=('b84f82584aa9adfd144efb9a1e82ca1731af4cb00425d82e9cb491e577969e84' if product else
              '0d222aa4968145b0026ac4e8c9288c9b1ad5fc9f8f9b1bdd07a6d3eda4f1af8b')
    if final:expected='408204bad0b135494839b37ce242f2cc720e9e918e293aaedcdc0d6a0105a0f6'
    if split:expected='d60c44681da7625f756b05315b626577a165eb29da9761d528e126508c9155f4'
    verify(prepared,expected)
    for folder,mode in [(main,'sim'),(aux,'ack'),(synthesis,'synth')]:
        outcome=json.loads((folder/'outcome.json').read_text())
        require(outcome.get('returncode')==0 and outcome.get('sources_unchanged') is True and
                'error' not in outcome and outcome['mode']==mode and outcome['prepared_sha']==expected and
                outcome['command'][-3]==str(prepared),'terminal same-source campaign required')
    audited=audit_productstage(main) if product else audit_forwardreceipt(main)
    if final:audited=audit_finalcapacity(main)
    if split:audited=audit_splitcapacity(main)
    require(json.dumps(audited,sort_keys=True)==json.dumps(json.loads((main/'outcome.json').read_text())['audit'],sort_keys=True),
            'main re-audit mismatch')
    verify_ack_auxiliary(aux,expected,prepared)
    outcome=json.loads((route/'outcome.json').read_text())
    require(outcome.get('returncode')==0 and outcome.get('sources_unchanged') is True and 'error' not in outcome,
            'terminal route required, not timing-pass claim')
    require(all(sha(Path(p))==value for p,value in outcome['before'].items()),'route source receipts changed')
    require(sha(route/'route/retained_output_routed.dcp')==outcome['routed_dcp_sha'],'routed checkpoint changed')
    require((route/'audit.json').is_file(),'independent route audit required')
    sources={}
    def add(name,path):
        require(name not in sources,'duplicate member');sources[name]=path
    def tree(prefix,folder,suffixes=None):
        require(folder.is_dir(),'required folder '+str(folder))
        for path in sorted(folder.rglob('*')):
            if not path.is_symlink() and path.is_file() and (suffixes is None or path.suffix in suffixes):
                add(prefix+'/'+str(path.relative_to(folder)),path)
    tree('prepared',prepared)
    for label,folder in [('main',main),('auxiliary',aux)]:
        for name in ['command.json','process.json','outcome.json','stdout.log','vivado.log','generated_fft.sha256']:
            add(label+'/'+name,folder/name)
        for name in ['simulate.log','staged_words.csv','xvlog.log','xvhdl.log','elaborate.log']:
            add(label+'/sim/'+name,folder/'project/staged_fft.sim/sim_1/behav/xsim'/name)
    for label,folder in [('synthesis',synthesis),('route',route)]:
        for path in sorted(folder.iterdir()):
            if path.is_file():add(label+'/'+path.name,path)
    tree('route/reports',route/'route')
    if product:
        # Preserve the rejected bubble implementation, not just the succeeding
        # final sources. Its simulations failed before a route was authorized.
        tree('rejected-v1/prepared',artifacts/'prepared-v1')
        for kind in ['sim','ack']:
            folder=artifacts/f'{kind}-v1'
            for name in ['command.json','process.json','outcome.json','stdout.log','vivado.log','generated_fft.sha256']:
                add(f'rejected-v1/{kind}/{name}',folder/name)
            for name in ['simulate.log','staged_words.csv','xvlog.log','xvhdl.log','elaborate.log']:
                add(f'rejected-v1/{kind}/sim/{name}',folder/'project/staged_fft.sim/sim_1/behav/xsim'/name)
        for path in sorted((artifacts/'synth-v1').iterdir()):
            if path.is_file():add('rejected-v1/synthesis/'+path.name,path)
    test_runs=(['preflight-v1','regression-v1','preflight-v2','regression-v2','audit-v2'] if product else
               ['component-v1','component-v2','component-v3','regression-v1','audit-v1','packaging-v1'])
    if final:test_runs=['preflight-v1','regression-v1','audit-v1']
    if split:test_runs=['preflight-v1','preflight-v2','regression-v1','audit-v1']
    for name in test_runs:
        # V1 stopped at collection before pytest needed a scratch directory.
        if name!='component-v1' or (artifacts/name).is_dir():
            tree('tests/'+name,artifacts/name,{'.py','.sv','.v','.log','.xml','.json','.txt','.tcl','.xdc'})
        add('tests/'+name+'.xml',artifacts/(name+'.xml'))
    tree('current/tests',ROOT/'tests',{'.py'})
    for name in ['staged_fft_experiment.py','staged_fft_experiment.tcl','route_starlink_staged_fft.py',
                 'audit_staged_fft_route.py','package_staged_fft_evidence.py','package_forward_receipt_evidence.py']:
        add('current/tools/'+name,ROOT/'tools'/name)
    document=('starlink-final-capacity-20260911.md' if final else
              'starlink-product-identity-integrated-20260911.md' if product else
              'starlink-forward-completion-receipt-20260911.md')
    if split:document='starlink-split-product-capacity-20260911.md'
    add('current/docs/experiment.md',ROOT/'docs'/document)
    if product or final:
        add('current/rtl/tb_product_identity_stage.sv',ROOT/'hdl/library/starlink_pss_acquisition/staged_control/tb_product_identity_stage.sv')
    parent=Path('/dev/shm/starlink-forward-receipt.7z0zKX/prepared-v1') if product else ROOT.parent/'staged-ackcombined-prepared-v1'
    if final:parent=Path('/dev/shm/starlink-product-integrated.1FSkuP/prepared-v2')
    if split:parent=Path('/dev/shm/starlink-final-capacity.vMIiHM/prepared-v1')
    parent_names=['SHA256SUMS','starlink_pss_fft_staged_output_impl.v','tb_fft_staged_output.sv']
    if final:parent_names+=['profile.tcl','starlink_pss_product_identity_stage.v']
    for name in parent_names:
        add('reference/parent/'+name,parent/name)
    # Historical regression fixtures remain a pinned, already-pushed dependency;
    # do not duplicate that 16 MB archive inside each subsequent experiment.
    reports=Path('/home/mouse9911/gits/plutosdr-fw-starlink-rx-only/reports/experiments')
    receipt=reports/('20260911-staged-forwardreceipt-evidence.json' if product else '20260911-staged-ackcombined-evidence.json')
    if final:receipt=reports/'20260911-staged-productidentity-evidence.json'
    if split:receipt=reports/'20260911-staged-finalcapacity-evidence.json'
    parent_receipt=json.loads(receipt.read_text())
    parent_sha=('3fba1792846ac692727c2896e6637dad85571d999aeb2e905b39de04804672e5' if final else
                'bad3215fc8a636d16a242111151f4f53f415f20d14733b081e261c36134bffcd' if product else
                'afbc76a605af0b9c16bda45e46cef498eac793b8dbb342023f39d6bccd71fdd9')
    if split:parent_sha='2d6cbccd814457936228571176ccbac0619af9324c032ab542e42a4f2b4ce847'
    require(parent_receipt['sha256']==parent_sha,
            'pinned historical fixture dependency')
    add('reference/parent-archive-receipt.json',receipt)
    if product:
        component=reports/'20260911-product-identity-components-evidence.json'
        require(json.loads(component.read_text())['sha256']=='84108474bab4cdffd0f03ea0cf8d6f9b2f12fdcdf2a160a153bf23e9dd29b102','component dependency pin')
        add('reference/component-archive-receipt.json',component)
    return write_verified_archive(output,sources)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('artifacts',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--campaign',choices=['forwardreceipt','productstage','finalcapacity','splitcapacity'],default='forwardreceipt')
    args=parser.parse_args();print(json.dumps(package(args.artifacts,args.output,args.campaign),indent=2))

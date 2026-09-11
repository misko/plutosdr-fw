"""Curate and read-back verify staged FFT sources, numerical evidence and route."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parents[1]
RECOVERY=ROOT.parent

def digest(data):return hashlib.sha256(data).hexdigest()

def package(output,campaign='output',test_root=None):
    if test_root is not None and (campaign!='enginecapture' or not test_root.is_absolute() or not test_root.is_dir()):
        raise ValueError('existing absolute engine-capture test root required')
    test_root=test_root or RECOVERY
    if output.exists():raise ValueError('no artifact overwrite')
    if campaign not in {'output','handover','admission','completion','replay','capture','finalcapture','sequence','certification','guardfacts','preflightpublication','inputidentity','enginecapture'}:raise ValueError('explicit campaign required')
    final_version={'output':5,'handover':4,'admission':3,'completion':2,'replay':2,'capture':1,'finalcapture':1,'sequence':1,'certification':1,'guardfacts':1,'preflightpublication':1,'inputidentity':2,'enginecapture':1}[campaign]
    sources={}
    def add(name,path):
        if name in sources or path.is_symlink() or not path.is_file():raise ValueError('invalid artifact member '+name)
        sources[name]=path
    for version in range(1,final_version+1):
        folder=RECOVERY/f'staged-{campaign}-prepared-v{version}'
        for p in sorted(folder.iterdir()):
            if p.is_file():add(f'prepared-v{version}/{p.name}',p)
        folder=RECOVERY/f'staged-{campaign}-actual-v{version}'
        for name in ['command.json','process.json','outcome.json','stdout.log','vivado.log','generated_fft.sha256']:
            if (folder/name).is_file():add(f'actual-v{version}/{name}',folder/name)
        sim=folder/'project/staged_fft.sim/sim_1/behav/xsim'
        for name in ['simulate.log','staged_words.csv','xvlog.log','xvhdl.log','elaborate.log']:
            if (sim/name).is_file():add(f'actual-v{version}/sim/{name}',sim/name)
    for version in ({'output':[5],'handover':[2,4],'admission':[1,2,3],'completion':[1,2],'replay':[1,2],'capture':[1],'finalcapture':[1],'sequence':[1],'certification':[1],'guardfacts':[1],'preflightpublication':[1],'inputidentity':[2],'enginecapture':[1]}[campaign]):
        for kind in ['synth','route']:
            if campaign=='admission' and version==1 and kind=='route':continue
            measured_campaign='guardfacts' if campaign=='preflightpublication' else campaign
            folder=RECOVERY/f'staged-{measured_campaign}-{kind}-v{version}'
            prefix=('inherited-'+kind if campaign=='preflightpublication' else
                    kind if campaign=='output' else f'{kind}-v{version}')
            for p in sorted(folder.iterdir()):
                if p.is_file():add(f'{prefix}/{p.name}',p)
            if kind=='route':
                for p in sorted((folder/'route').iterdir()):
                    if p.is_file():add(f'{prefix}/reports/{p.name}',p)
    for name in ['staged-mailbox-parent.Tc4Uke1L','staged-adapter-parent.qSJUuasQ']:
        folder=RECOVERY/name
        for p in sorted(folder.rglob('*')):
            if p.is_file() and (p.suffix in {'.xml','.log','.json','.sv','.v','.txt'}):
                add('tests/'+name+'/'+str(p.relative_to(folder)),p)
    if campaign=='handover':
        for name in ['staged-handover-tests-v1','staged-handover-regression-v2','staged-handover-regression-v4',
                     'staged-handover-route-audit-tests-v4']:
            folder=RECOVERY/name
            for p in sorted(folder.rglob('*')):
                if p.is_file() and p.suffix in {'.xml','.log','.json','.sv','.v','.txt'}:
                    add('tests/'+name+'/'+str(p.relative_to(folder)),p)
            add('tests/'+name+'.xml',RECOVERY/(name+'.xml'))
    if campaign=='admission':
        for name in ['staged-admission-lint-v1','staged-admission-unit-v1','staged-admission-unit-v2',
                     'staged-admission-regression-v2','staged-admission-audit-v2','staged-admission-regression-v3']:
            folder=RECOVERY/name
            for p in sorted(folder.rglob('*')):
                if p.is_file() and p.suffix in {'.xml','.log','.json','.sv','.v','.txt'}:
                    add('tests/'+name+'/'+str(p.relative_to(folder)),p)
            add('tests/'+name+'.xml',RECOVERY/(name+'.xml'))
    if campaign=='completion':
        for name in ['staged-completion-lint-v1','staged-completion-unit-v1','staged-completion-regression-v1',
                     'staged-completion-lint-v2','staged-completion-private-rom-v2','staged-completion-regression-v2']:
            folder=RECOVERY/name
            for p in sorted(folder.rglob('*')):
                if p.is_file() and p.suffix in {'.xml','.log','.json','.sv','.v','.txt'}:
                    add('tests/'+name+'/'+str(p.relative_to(folder)),p)
            add('tests/'+name+'.xml',RECOVERY/(name+'.xml'))
    if campaign in {'replay','capture','finalcapture','sequence','certification','guardfacts','preflightpublication','inputidentity','enginecapture'}:
        names=(['staged-enginecapture-preflight-v1','staged-enginecapture-regression-v1','staged-enginecapture-audit-v1'] if campaign=='enginecapture' else
               ['staged-inputidentity-preflight-v1','staged-inputidentity-regression-v2','staged-inputidentity-audit-v2','staged-inputidentity-boundary-inverse-v2'] if campaign=='inputidentity' else
               ['staged-preflightpublication-unit-v1','staged-preflightpublication-regression-v1'] if campaign=='preflightpublication' else
               ['staged-replay-preflight-v1','staged-replay-unit-v1','staged-replay-regression-v1',
                'staged-replay-preflight-v2','staged-replay-regression-v2'] if campaign=='replay' else
               ['staged-guardfacts-unit-v1','staged-guardfacts-preflight-v1','staged-guardfacts-regression-v1'] if campaign=='guardfacts' else
               ['staged-certification-unit-v1','staged-certification-preflight-v1','staged-certification-regression-v1'] if campaign=='certification' else
               ['staged-sequence-unit-v1','staged-sequence-preflight-v1','staged-sequence-regression-v1'] if campaign=='sequence' else
               ['staged-finalcapture-unit-v1','staged-finalcapture-preflight-v1','staged-finalcapture-regression-v1'] if campaign=='finalcapture' else
               ['staged-capture-preflight-v1','staged-capture-unit-v1','staged-capture-unit-v2','staged-capture-regression-v1'])
        for name in names:
            folder=(test_root if campaign=='enginecapture' else RECOVERY)/name
            for p in sorted(folder.rglob('*')):
                if p.is_file() and p.suffix in {'.xml','.log','.json','.sv','.v','.txt'}:
                    add('tests/'+name+'/'+str(p.relative_to(folder)),p)
            add('tests/'+name+'.xml',(test_root if campaign=='enginecapture' else RECOVERY)/(name+'.xml'))
    for p in sorted((ROOT/'tests').glob('test_starlink*')):
        if p.name in {'test_starlink_descriptor_commands_mailbox.py','test_starlink_staged_mailbox_control.py',
                      'test_starlink_staged_fft_lint.py','test_starlink_staged_fft_audit.py','test_starlink_handover_audit.py',
                      'test_starlink_route_report_audit.py','test_starlink_admission_certificate.py',
                      'test_starlink_admission_audit.py','test_starlink_completion_audit.py','test_starlink_private_kernel_payload.py',
                      'test_starlink_private_replay.py','test_starlink_replay_audit.py','test_starlink_writer_audit.py',
                      'test_starlink_private_descriptor_capture.py','test_starlink_capture_audit.py',
                      'test_starlink_private_final_capture.py','test_starlink_finalcapture_audit.py',
                      'test_starlink_private_kernel_sequence.py','test_starlink_sequence_audit.py',
                      'test_starlink_private_certification.py','test_starlink_certification_audit.py',
                      'test_starlink_guard_facts.py','test_starlink_guardfacts_audit.py',
                      'test_starlink_preflight_publication.py','test_starlink_preflightpublication_audit.py','test_starlink_input_identity_stage.py','test_starlink_inputstage_audit.py','test_starlink_private_engine_descriptor.py','test_starlink_enginecapture_audit.py'}:
            add('current/tests/'+p.name,p)
    for name in ['staged_fft_experiment.py','staged_fft_experiment.tcl','route_starlink_staged_fft.py','audit_staged_fft_route.py','package_staged_fft_evidence.py']:
        add('current/tools/'+name,ROOT/'tools'/name)
    add('current/docs/starlink-staged-output-integration-20260911.md',ROOT/'docs/starlink-staged-output-integration-20260911.md')
    if campaign in {'handover','admission','completion','replay','capture','finalcapture','sequence','certification','guardfacts','preflightpublication','inputidentity','enginecapture'}:
        add('current/docs/starlink-staged-handover-20260911.md',ROOT/'docs/starlink-staged-handover-20260911.md')
        add('reference/actual_words.csv',RECOVERY/'destination-actual-parent.LQnQo9ny/run/project/retained_output_actual.sim/sim_1/behav/xsim/actual_words.csv')
    if campaign in {'admission','completion','replay','capture','finalcapture','sequence','certification','guardfacts','preflightpublication','inputidentity','enginecapture'}:
        add('current/docs/starlink-staged-admission-20260911.md',ROOT/'docs/starlink-staged-admission-20260911.md')
    if campaign in {'completion','replay','capture','finalcapture','sequence','certification','guardfacts','preflightpublication','inputidentity','enginecapture'}:
        add('current/docs/starlink-staged-completion-20260911.md',ROOT/'docs/starlink-staged-completion-20260911.md')
    if campaign in {'replay','capture','finalcapture','sequence','certification','guardfacts','preflightpublication','inputidentity','enginecapture'}:
        add('current/docs/starlink-staged-replay-20260911.md',ROOT/'docs/starlink-staged-replay-20260911.md')
    if campaign in {'capture','finalcapture','sequence','certification','guardfacts','preflightpublication','inputidentity','enginecapture'}:
        add('current/docs/starlink-staged-capture-20260911.md',ROOT/'docs/starlink-staged-capture-20260911.md')
        add('reference/qualified_capture.v',RECOVERY/'staged-replay-prepared-v2/starlink_pss_fft_staged_output_impl.v')
    if campaign in {'finalcapture','sequence','certification','guardfacts','preflightpublication','inputidentity','enginecapture'}:
        add('current/docs/starlink-private-final-capture-20260911.md',ROOT/'docs/starlink-private-final-capture-20260911.md')
        add('reference/original_adapter.v',RECOVERY/'staged-capture-prepared-v1/starlink_pss_staged_mailbox_control.v')
        add('current/hdl/tb_staged_mailbox_control.sv',ROOT/'hdl/library/starlink_pss_acquisition/staged_control/tb_staged_mailbox_control.sv')
    if campaign in {'sequence','certification','guardfacts','preflightpublication','inputidentity','enginecapture'}:
        add('current/docs/starlink-private-kernel-sequence-20260911.md',ROOT/'docs/starlink-private-kernel-sequence-20260911.md')
        add('reference/original_kernel.v',RECOVERY/'staged-completion-prepared-v1/starlink_pss_kernel_rom.v')
    if campaign in {'certification','guardfacts','preflightpublication','inputidentity','enginecapture'}:
        add('current/docs/starlink-private-certification-20260911.md',ROOT/'docs/starlink-private-certification-20260911.md')
        add('reference/original_certification.v',RECOVERY/'staged-sequence-prepared-v1/starlink_pss_fft_staged_output_impl.v')
    if campaign in {'guardfacts','preflightpublication','inputidentity','enginecapture'}:
        add('current/docs/starlink-guard-facts-20260911.md',ROOT/'docs/starlink-guard-facts-20260911.md')
        for name in ['starlink_pss_fft_staged_output_impl.v','starlink_pss_result_guard_owner_view.v']:
            add('reference/certification/'+name,RECOVERY/'staged-certification-prepared-v1'/name)
    if campaign=='preflightpublication':
        add('current/docs/starlink-preflight-publication-proof-20260911.md',ROOT/'docs/starlink-preflight-publication-proof-20260911.md')
        current=RECOVERY/'staged-preflightpublication-prepared-v1'
        parent=RECOVERY/'staged-guardfacts-prepared-v1'
        runtime_names=(current/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
        if len(runtime_names)!=17:raise ValueError('exact inherited runtime inventory')
        for name in runtime_names:
            if (current/name).read_bytes()!=(parent/name).read_bytes():raise ValueError('runtime changed '+name)
            add('reference/guardfacts-runtime/'+name,parent/name)
    if campaign=='inputidentity':
        add('tests/staged-inputidentity-regression-v1.xml',RECOVERY/'staged-inputidentity-regression-v1.xml')
        add('current/docs/starlink-input-identity-integrated-20260911.md',ROOT/'docs/starlink-input-identity-integrated-20260911.md')
        for name in ['starlink_pss_fft_staged_output_impl.v','starlink_pss_realtime_input_guard_local_admission.v']:
            add('reference/preflight-runtime/'+name,RECOVERY/'staged-preflightpublication-prepared-v1'/name)
        for name in ['tb_input_identity_stage.sv','tb_input_identity_checker.sv']:
            add('current/hdl/'+name,ROOT/'hdl/library/starlink_pss_acquisition/staged_control'/name)
    if campaign=='enginecapture':
        add('current/docs/starlink-private-engine-descriptor-20260911.md',ROOT/'docs/starlink-private-engine-descriptor-20260911.md')
        add('reference/input-stage-top.v',RECOVERY/'staged-inputidentity-prepared-v2/starlink_pss_fft_staged_output_impl.v')
    manifest={name:{'source':str(path),'sha256':digest(path.read_bytes()),'bytes':path.stat().st_size} for name,path in sources.items()}
    def insert(archive,name,data):
        info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;archive.addfile(info,io.BytesIO(data))
    with tarfile.open(output,'w:gz') as archive:
        insert(archive,'manifest.json',(json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode())
        for name,path in sorted(sources.items()):
            data=path.read_bytes()
            if digest(data)!=manifest[name]['sha256']:raise ValueError('source changed '+name)
            insert(archive,name,data)
    with tarfile.open(output,'r:gz') as archive:
        members=archive.getmembers()
        if {m.name for m in members}!=set(manifest)|{'manifest.json'} or len(members)!=len(manifest)+1:
            raise ValueError('archive member inventory')
        if not all(m.isfile() for m in members):raise ValueError('non-regular archive member')
        if json.load(archive.extractfile('manifest.json'))!=manifest:raise ValueError('manifest read-back')
        for name,value in manifest.items():
            data=archive.extractfile(name).read()
            if len(data)!=value['bytes'] or digest(data)!=value['sha256']:raise ValueError('archive read-back '+name)
    receipt={'path':str(output),'bytes':output.stat().st_size,'sha256':digest(output.read_bytes()),
             'members':len(manifest)+1,'all_members_verified':True,'full_receiver_or_deployment_claim':False}
    receipt_path=output.with_suffix('.json')
    if receipt_path.exists():raise ValueError('no receipt overwrite')
    receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path)
    parser.add_argument('--campaign',choices=['output','handover','admission','completion','replay','capture','finalcapture','sequence','certification','guardfacts','preflightpublication','inputidentity','enginecapture'],default='output')
    parser.add_argument('--test-root',type=Path)
    args=parser.parse_args();print(json.dumps(package(args.output,args.campaign,args.test_root),indent=2))

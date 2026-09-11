"""Frozen actual-XFFT/route experiment. Never loads a radio or receiver build."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
RECOVERY=ROOT.parent
BASE=RECOVERY/'retained-summary-actual-prelaunch-v1'
ACQ='hdl/library/starlink_pss_acquisition/'
NEW=ROOT/ACQ/'staged_control'
BASE_SHA='b5d112562b7db31164dc4a6ff92404de8e7d7d5d96b1c1b23e1a7dbac9d2c368'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def require(ok,message):
    if not ok:raise ValueError(message)
def fresh(path):
    require(path.is_absolute() and not path.exists() and '..' not in path.parts,'new absolute output required')
    require(not path.is_relative_to(ROOT) and not path.is_relative_to(BASE),'output outside source trees')
    path.mkdir(parents=True)

def prepare(path):
    require(sha(BASE/'manifest.json')==BASE_SHA,'reference manifest changed')
    manifest=json.loads((BASE/'manifest.json').read_text())
    profile=(BASE/'profile.tcl').read_text()
    names=re.search(r'set compiled_names \{([^}]+)\}',profile)[1].split()
    vectors=re.search(r'set vector_names \{([^}]+)\}',profile)[1].split()
    removed={'starlink_pss_fft_bank_owned_retained_output_probe.v','starlink_pss_fft_retained_output_impl.v','starlink_pss_retained_output_owner.v',
             'starlink_pss_core_job_cutover.v','starlink_pss_result_guard_owner_view.v',
             'starlink_pss_kernel_rom.v','starlink_pss_forward_kernel_join.v'}
    runtime=[BASE/name for name in names if name.endswith('.v') and
             '/retained_output_actual/' not in name and Path(name).name not in removed]
    require(len(runtime)==9,'exact inherited runtime count')
    support=[BASE/name for name in vectors]
    support.append(BASE/'source_snapshot'/ACQ/'retained_output_actual/reference/create_shared_realtime_xfft_ip.tcl')
    support.append(BASE/'source_snapshot'/ACQ/'retained_output_actual/run_retained_output_actual.tcl')
    for source in runtime+support:
        relative=str(source.relative_to(BASE/'source_snapshot'))
        require(sha(source)==manifest['sources'][relative]['sha256'],'reference source changed: '+relative)
    runtime.extend(NEW/name for name in ['starlink_pss_descriptor_commands.v','starlink_pss_staged_mailbox_control.v','starlink_pss_fft_staged_output_impl.v',
                                       'starlink_pss_core_job_cutover.v','starlink_pss_result_guard_owner_view.v','starlink_pss_admission_certificate.v',
                                       'starlink_pss_kernel_rom.v','starlink_pss_forward_kernel_join.v',
                                       'starlink_pss_input_identity_stage.v','starlink_pss_realtime_input_guard_staged_identity.v',
                                       'starlink_pss_product_identity_split_capacity.v','starlink_pss_product_mailbox_staged_identity.v'])
    support.extend([NEW/'tb_fft_staged_output.sv',ROOT/'tools/staged_fft_experiment.tcl',Path(__file__).resolve(),
                    ROOT/'tools/retained_destination_synthesis/clocks.xdc',ROOT/'tools/retained_destination_synthesis/threads.tcl'])
    sources=runtime+support
    require(len({p.name for p in sources})==len(sources),'flat snapshot collision')
    before={str(p):sha(p) for p in sources}
    fresh(path)
    for p in sources:shutil.copyfile(p,path/p.name)
    (path/'profile.tcl').write_text('set runtime_names {'+' '.join(p.name for p in runtime)+'}\nset vector_names {'+' '.join(Path(v).name for v in vectors)+'}\n')
    require(before=={str(p):sha(p) for p in sources},'sources changed during copy')
    files={p.name:sha(p) for p in path.iterdir() if p.is_file()}
    (path/'snapshot.json').write_text(json.dumps({'sources':before,'files':files,'reference':BASE_SHA},indent=2)+'\n')
    files['snapshot.json']=sha(path/'snapshot.json')
    (path/'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name,digest in sorted(files.items())))
    return {'prepared':str(path),'sha256sums':sha(path/'SHA256SUMS'),'files':len(files)}

def verify(path,expected):
    require(sha(path/'SHA256SUMS')==expected,'external source inventory digest')
    subprocess.run(['sha256sum','-c','SHA256SUMS','--quiet'],cwd=path,check=True)
    m=json.loads((path/'snapshot.json').read_text())
    require(all(sha(Path(p))==value for p,value in m['sources'].items()),'live sources changed')
    require(all(sha(path/p)==value for p,value in m['files'].items()),'copied sources changed')

def audit_sim(output,contexts=4):
    sim=output/'project/staged_fft.sim/sim_1/behav/xsim'
    text=(sim/'simulate.log').read_text()
    require(not re.search(r'FATAL|ERROR|FAIL',text,re.I),'simulator failure')
    rows=re.findall(r'^STAGED_FFT_CONTEXT_PASS mode=(\d+) reads=1536 inputs=3072 raw=3072 status=6 publications=3 releases=3 max_service=(\d+) overlap_inputs=(\d+) overlap_reads=(\d+)$',text,re.M)
    require(contexts in (4,6),'explicit supported numerical campaign')
    require(len(rows)==contexts and [int(r[0]) for r in rows]==list(range(contexts)),'complete numerical contexts')
    require(all(int(r[2])>0 and (int(r[0])>=2 or int(r[3])>0) for r in rows),'actual overlap')
    require(all(int(r[1])<=5215 for r in rows if int(r[0])!=3),'coarse service deadline')
    require(text.count(f'STAGED_FFT_PASS contexts={contexts} no_continuous_or_physical_claim')==1,'one terminal success')
    # Independently compare every recorded numerical field against prior actual
    # generated FFT evidence, not merely the candidate bench's PASS marker.
    old=RECOVERY/'destination-actual-parent.LQnQo9ny/run/project/retained_output_actual.sim/sim_1/behav/xsim/actual_words.csv'
    require(sha(old)=='07321b026a637e5922c56a84a955e58549056337198c952a9d73b1245cb4efaa','old numerical authority')
    reference={}
    with old.open() as f:
        for r in csv.DictReader(f):
            if r['context']=='0' and r['stream'] in {'inputF','inputI','rawF','rawI','product','privateI','read'}:
                key=(r['stream'],r['job'],r['position'])
                require(key not in reference,'duplicate old word')
                reference[key]=(r['data'],r['exponent'])
    require(len(reference)==10752,'complete old seven-stream numerical reference')
    seen=set()
    with (sim/'staged_words.csv').open() as f:
        for r in csv.DictReader(f):
            key=(r['stream'],r['job'],r['position']);identity=(r['context'],*key)
            require(r['context'] in {str(n) for n in range(contexts)} and identity not in seen,'duplicate/unknown new word')
            require(reference.get(key)==(r['data'],r['exponent']),'old/new exact numerical mismatch: '+str(identity))
            seen.add(identity)
    require(len(seen)==10752*contexts,'all complete numerical inventories')
    return {'contexts':rows,'numerical_rows':len(seen),'sha256':sha(sim/'staged_words.csv'),
            'actual_fft':True,'continuous_rx':False,'physical_signoff':False}

def audit_handover_sim(output,fault_cases=6):
    require(fault_cases in (6,7),'explicit supported fault campaign')
    result=audit_sim(output,contexts=6)
    sim=output/'project/staged_fft.sim/sim_1/behav/xsim'
    text=(sim/'simulate.log').read_text()
    timestamps=re.findall(r'^STAGED_TIMESTAMP_PASS mode=(\d+) base=([0-9a-f]{16}) words=1536$',text,re.M)
    require(timestamps==[('4','a5a5a5a5a5a5a000'),('5','5a5a5a5a5a5a5000')],'full-width reader timestamp contexts')
    resets=re.findall(r'^STAGED_RESET_PASS side=(\d+) old_unread=512 aborted_forward_prefix=(\d+) fresh_reads=512 slow_purge_edges=(\d+)$',text,re.M)
    require(len(resets)==2 and [int(r[0]) for r in resets]==[1,2] and
            all(64<=int(r[1])<512 and int(r[2])>=4 for r in resets),'both stopped-reader reset epochs')
    faults=re.findall(r'^STAGED_FAULT_PASS boundary=(\d+) no_late_publication=1 releases=0 reads=(\d+)$',text,re.M)
    require(len(faults)==fault_cases and [(int(r[0]),int(r[1])) for r in faults]==[(n,512 if n==5 else 0) for n in range(fault_cases)],
            'all fault/quarantine boundaries')
    handover=re.findall(rf'^STAGED_HANDOVER_PASS admissions=(\d+) completions=(\d+) reset_cases=2 fault_cases={fault_cases}$',text,re.M)
    require(len(handover)==1 and all(int(n)>=36 for n in handover[0]),'terminal registered handover coverage')
    result['handover']={'resets':resets,'faults':faults,'timestamps':timestamps,'admissions':int(handover[0][0]),'completions':int(handover[0][1])}
    return result

def audit_admission_sim(output):
    result=audit_handover_sim(output,fault_cases=7)
    text=(output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
    rows=re.findall(r'^STAGED_ADMISSION_CASE_PASS boundary=(\d+) starts_after_cancel=0 publications=0 releases=0$',text,re.M)
    require(rows==list(map(str,range(6))),'complete admission cancellation boundaries')
    require(text.count('STAGED_ADMISSION_PASS cases=6 partition_checked=1')==1,'partition/cancellation terminal evidence')
    result['admission']={'boundaries':rows,'partition_checked':True}
    return result

def audit_completion_sim(output):
    result=audit_admission_sim(output)
    text=(output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
    rows=re.findall(r'^STAGED_COMPLETION_CASE_PASS boundary=(\d+) phase=(\d+) reuse_after_cancel=0 publications=0 releases=0$',text,re.M)
    require(rows==[(str(n),str(n//3 if n<6 else int(n>=8))) for n in range(10)],'complete producer cancellation boundaries')
    require(text.count('STAGED_COMPLETION_PASS cases=10 partition_checked=1')==1,'completion partition terminal evidence')
    result['completion']={'boundaries':rows,'partition_checked':True}
    return result

def audit_replay_sim(output):
    result=audit_completion_sim(output)
    text=(output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
    rows=re.findall(r'^STAGED_REPLAY_CASE_PASS boundary=(\d+) private_step=(\d+) publications=0 releases=0$',text,re.M)
    require(rows==[(str(n),str(int(n<3))) for n in range(5)],'complete replay cancellation boundaries')
    require(text.count('STAGED_REPLAY_PASS cases=5 actual_authorization_checked=1')==1,'replay authorization terminal evidence')
    result['replay']={'boundaries':rows,'actual_authorization_checked':True}
    return result

def audit_writer_sim(output):
    result=audit_replay_sim(output)
    text=(output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
    rows=re.findall(r'^STAGED_WRITER_CASE_PASS boundary=(\d+) publications=0 releases=0$',text,re.M)
    require(rows==list(map(str,range(4))),'complete writer validation cancellation boundaries')
    require(text.count('STAGED_WRITER_PASS cases=4 pending_fenced=1')==1,'pending writer fence terminal evidence')
    result['writer']={'boundaries':rows,'pending_fenced':True}
    return result

def audit_capture_sim(output):
    result=audit_writer_sim(output)
    text=(output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
    rows=re.findall(r'^STAGED_CAPTURE_CASE_PASS boundary=(\d+) reads=(\d+) releases=(\d+)$',text,re.M)
    require(rows==[('0','512','1'),('1','512','1'),('2','0','0')],'complete private capture/churn/release boundaries')
    counts=re.findall(r'^STAGED_CAPTURE_CYCLES_PASS loads=(\d+) holds=(\d+) accepts=(\d+)$',text,re.M)
    require(len(counts)==1,'private capture cycle evidence')
    loads,holds,accepts=map(int,counts[0])
    require(loads>=1000 and holds>=1000 and accepts==18,'private capture load/hold/accept coverage')
    require(text.count('STAGED_CAPTURE_PASS cases=3 private_load_checked=1 held_until_release=1')==1,'capture ownership terminal evidence')
    result['capture']={'boundaries':rows,'loads':loads,'holds':holds,'accepts':accepts,
                       'private_load_checked':True,'held_until_release':True}
    return result

def audit_finalcapture_sim(output):
    result=audit_capture_sim(output)
    text=(output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
    counts=re.findall(r'^STAGED_FINALCAPTURE_PASS loads=(\d+) holds=(\d+) accepts=(\d+) fault_loads=(\d+) original_payload_checked=1$',text,re.M)
    require(len(counts)==1,'one original/private final payload terminal')
    loads,holds,accepts,fault_loads=map(int,counts[0])
    require(loads>=1000 and holds>=1000 and accepts>=18 and fault_loads>=100,'private final load/hold/accept/fault coverage')
    result['finalcapture']={'loads':loads,'holds':holds,'accepts':accepts,'fault_loads':fault_loads,'original_payload_checked':True}
    return result

def audit_sequence_sim(output):
    result=audit_finalcapture_sim(output)
    text=(output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
    rows=re.findall(r'^STAGED_SEQUENCE_CASE_PASS boundary=(\d+) private_advance=1 final=(\d+) reads=(\d+) releases=(\d+)$',text,re.M)
    expected=[(str(n),str(int(n>=3)),'512' if n in (3,4) else '0','1' if n in (3,4) else '0') for n in range(6)]
    require(rows==expected,'complete private sequence mid/final fault and late/stalled final cases')
    counts=re.findall(r'^STAGED_SEQUENCE_CYCLES_PASS advances=(\d+) holds=(\d+) finals=(\d+)$',text,re.M)
    require(len(counts)==1,'one private sequence cycle receipt')
    advances,holds,finals=map(int,counts[0])
    require(advances==9216 and holds>=1000 and finals==18,'healthy private sequence cycle coverage')
    require(text.count('STAGED_SEQUENCE_PASS cases=6 public_acceptance_preserved=1 next_block_checked=1 quarantine_checked=1')==1,'one full sequence terminal')
    result['sequence']={'boundaries':rows,'advances':advances,'holds':holds,'finals':finals,'next_block_checked':True,'quarantine_checked':True}
    return result

def audit_certification_sim(output):
    result=audit_sequence_sim(output)
    text=(output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
    rows=re.findall(r'^STAGED_CERTIFICATION_CASE_PASS boundary=(\d+) stale_starts=0 stale_reads=0 fresh_reads=512 fresh_releases=1$',text,re.M)
    require(rows==[str(n) for n in range(6)],'complete private descriptor snapshot cancellation and recovery cases')
    counts=re.findall(r'^STAGED_CERTIFICATION_CYCLES_PASS checks=(\d+) private_differences=(\d+)$',text,re.M)
    require(len(counts)==1,'one private descriptor cycle receipt')
    checks,differences=map(int,counts[0])
    require(checks>=1000 and differences>=2,'original/private descriptor coverage')
    require(text.count('STAGED_CERTIFICATION_PASS cases=6 snapshot_cancelled=1 consume_cancelled=1 fresh_recovery=1')==1,'one complete descriptor terminal')
    result['certification']={'boundaries':rows,'checks':checks,'private_differences':differences,'snapshot_cancelled':True,'consume_cancelled':True,'fresh_recovery':True}
    return result

def audit_guardfacts_sim(output):
    result=audit_certification_sim(output)
    text=(output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
    rows=re.findall(r'^STAGED_GUARDFACTS_CASE_PASS gate=(\d+) owner=(\d+) fact=(\d+) starts=0 reads=0 releases=0$',text,re.M)
    require(rows==[(str(g),str(o),str(f)) for g in range(2) for o in range(2) for f in range(8)],'all independently clocked guard facts exercised')
    cycles=re.findall(r'^STAGED_GUARDFACTS_PASS cases=32 cycles=(\d+) exact_certificates=1 fresh_reads=512 fresh_releases=1$',text,re.M)
    require(len(cycles)==1 and int(cycles[0])>=1000,'exact certificate state and fresh recovery coverage')
    result['guardfacts']={'boundaries':rows,'cycles':int(cycles[0]),'exact_certificates':True,'fresh_recovery':True}
    return result

def audit_preflightpublication_sim(output):
    result=audit_guardfacts_sim(output)
    text=(output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
    rows=re.findall(r'^STAGED_PREFLIGHT_PUBLICATION_CASE_PASS boundary=(\d+) paused=(\d+) queued=1 fresh_reads=512 fresh_releases=1$',text,re.M)
    require(len(rows)==3 and [int(r[0]) for r in rows]==list(range(3)) and
            all(int(r[1])>=128 for r in rows),'queued publication pause and recovery cases')
    counts=re.findall(r'^STAGED_PREFLIGHT_PUBLICATION_PASS cases=3 checks=(\d+) replay=(\d+) unread=(\d+) phase_exact=1$',text,re.M)
    require(len(counts)==1,'one publication/preflight phase witness')
    checks,replay,unread=map(int,counts[0])
    require(checks>=1000 and replay>=384 and unread>=2,'both unpublished and published/unread phase coverage')
    result['preflightpublication']={'boundaries':rows,'checks':checks,'replay':replay,'unread':unread,'phase_exact':True}
    return result

def audit_inputstage_sim(output):
    result=audit_preflightpublication_sim(output)
    text=(output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
    rows=re.findall(r'^STAGED_INPUT_IDENTITY_PASS pushes=(\d+) pops=(\d+) checks=(\d+) final_holds=(\d+) exact_payload=1 admitted_descriptor=1$',text,re.M)
    require(len(rows)==1,'one actual staged input receipt')
    pushes,pops,checks,final_holds=map(int,rows[0])
    require(min(pushes,pops,checks)>=18432 and final_holds>=36,'actual staged input coverage')
    boundaries=re.findall(r'^STAGED_INPUT_IDENTITY_CASE_PASS boundary=(\d+) stale_reads=0 publications=0 fresh_reads=512 fresh_releases=1$',text,re.M)
    require(boundaries==[str(n) for n in range(6)],'all staged identity/reset cancellations and fresh recoveries')
    result['inputstage']={'pushes':pushes,'pops':pops,'checks':checks,'final_holds':final_holds,
                          'exact_payload':True,'admitted_descriptor':True,'boundaries':boundaries}
    return result

def audit_enginecapture_sim(output):
    result=audit_inputstage_sim(output)
    text=(output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
    rows=re.findall(r'^STAGED_ENGINE_CAPTURE_CASE_PASS boundary=(\d+) extra_private=1 stale_reads=0 fresh_reads=512 fresh_releases=1$',text,re.M)
    require(rows==[str(n) for n in range(6)],'all private engine capture boundaries and recoveries')
    counts=re.findall(r'^STAGED_ENGINE_CAPTURE_PASS checks=(\d+) private_differences=(\d+) owned_exact=1 cases=6$',text,re.M)
    require(len(counts)==1 and int(counts[0][0])>=1000 and int(counts[0][1])>=8,'owned descriptor comparison and private-only differences')
    result['enginecapture']={'boundaries':rows,'checks':int(counts[0][0]),'private_differences':int(counts[0][1]),'owned_exact':True}
    return result

def audit_ackcombined_sim(output):
    result=audit_enginecapture_sim(output)
    text=(output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
    rows=re.findall(r'^STAGED_ACKCOMBINED_MAIN_PASS checks=(\d+) public_exact=1$',text,re.M)
    require(len(rows)==1 and int(rows[0])>=1000,'combined main original ACK witness')
    result['ackcombined']={'checks':int(rows[0]),'public_exact':True,'auxiliary_required':True}
    return result

def audit_ackcombined_aux(output):
    text=(output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
    require(not re.search(r'FATAL|ERROR|FAIL',text,re.I),'auxiliary simulator failure')
    rows=re.findall(r'^STAGED_PRIVATEACK_CASE_PASS boundary=(\d+) fresh_reads=512 fresh_releases=1$',text,re.M)
    require(rows==[str(n) for n in range(6)],'all combined ACK real-reader boundaries and fresh recovery')
    counts=re.findall(r'^STAGED_ACKCOMBINED_AUX_PASS cases=6 checks=(\d+) quarantined=(\d+) public_exact=1 fresh_recovery=1$',text,re.M)
    require(len(counts)==1 and int(counts[0][0])>=1000 and int(counts[0][1])>=300,'combined ACK public equivalence and quarantine coverage')
    return {'boundaries':rows,'checks':int(counts[0][0]),'quarantined':int(counts[0][1]),
            'public_exact':True,'fresh_recovery':True,'actual_fft':True,'main_numerical_campaign_required':True,
            'physical_signoff':False,'continuous_rx':False}

def forward_receipt_compiled(prepared):
    return '// BEGIN FORWARD RECEIPT WITNESS' in (prepared/'tb_fft_staged_output.sv').read_text()

def audit_forwardreceipt(output,auxiliary=False):
    result=audit_ackcombined_aux(output) if auxiliary else audit_ackcombined_sim(output)
    text=(output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
    counts=re.findall(r'^STAGED_FORWARD_RECEIPT_PASS checks=(\d+) pending=(\d+) ack_exact=1 publication_subset=1$',text,re.M)
    require(len(counts)==1 and int(counts[0][0])>=1000 and int(counts[0][1])>=10,
            'qualified forward receipt and actual ACK interlock coverage')
    cases=re.findall(r'^STAGED_FORWARD_RECEIPT_CASE_PASS boundary=(\d+) fresh_reads=512 fresh_releases=1$',text,re.M)
    require(cases==([str(n) for n in range(12)] if auxiliary else []),'forward receipt boundary inventory')
    result['forwardreceipt']={'checks':int(counts[0][0]),'pending':int(counts[0][1]),
        'ack_exact':True,'publication_subset':True,'boundaries':cases,'auxiliary_required':not auxiliary}
    return result

def product_stage_compiled(prepared):
    return '// BEGIN ACTUAL PRODUCT STAGE WITNESS' in (prepared/'tb_fft_staged_output.sv').read_text()

def audit_productstage(output,auxiliary=False):
    result=audit_forwardreceipt(output,auxiliary)
    text=(output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
    rows=re.findall(r'^STAGED_PRODUCT_STAGE_PASS pushes=(\d+) pops=(\d+) checks=(\d+) updates=(\d+) holds=(\d+) original_identity=1 private_conservation=1$',text,re.M)
    require(len(rows)==1,'one actual product identity/conservation receipt')
    pushes,pops,checks,updates,holds=map(int,rows[0])
    require(min(pushes,pops)>=6144 and checks>=1000 and updates>=12 and pushes>=pops,'actual product stage coverage')
    if auxiliary:require(holds>=96,'held product LAST coverage')
    cases=re.findall(r'^STAGED_PRODUCT_STAGE_CASE_PASS boundary=(\d+) fresh_reads=512 fresh_releases=1$',text,re.M)
    require(cases==([str(n) for n in range(12)] if auxiliary else []),'actual product stage boundary inventory')
    result['productstage']={'pushes':pushes,'pops':pops,'checks':checks,'updates':updates,'holds':holds,
        'original_identity':True,'private_conservation':True,'boundaries':cases,'auxiliary_required':not auxiliary}
    return result

def final_capacity_compiled(prepared):
    return '// BEGIN FINAL CAPACITY WITNESS' in (prepared/'tb_fft_staged_output.sv').read_text()

def audit_finalcapacity(output,auxiliary=False):
    result=audit_productstage(output,auxiliary)
    text=(output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
    rows=re.findall(r'^STAGED_FINAL_CAPACITY_PASS finals=(\d+) starts=(\d+) no_refill=1 producer_quiet=1 actual_bank_return=1$',text,re.M)
    require(len(rows)==1 and min(map(int,rows[0]))>=12,'actual final capacity and bank return coverage')
    result['finalcapacity']={'finals':int(rows[0][0]),'starts':int(rows[0][1]),'no_refill':True,
        'producer_quiet':True,'actual_bank_return':True}
    return result

def split_capacity_compiled(prepared):
    return '// BEGIN SPLIT CAPACITY WITNESS' in (prepared/'tb_fft_staged_output.sv').read_text()

def audit_splitcapacity(output,auxiliary=False):
    result=audit_finalcapacity(output,auxiliary)
    text=(output/'project/staged_fft.sim/sim_1/behav/xsim/simulate.log').read_text()
    rows=re.findall(r'^STAGED_SPLIT_CAPACITY_PASS checks=(\d+) nonfinal=(\d+) input_ready_exact=1 current_retirement_exact=1$',text,re.M)
    require(len(rows)==1 and int(rows[0][0])>=1000 and int(rows[0][1])>=6144,'split capacity exact acceptance and retirement coverage')
    result['splitcapacity']={'checks':int(rows[0][0]),'nonfinal':int(rows[0][1]),
        'input_ready_exact':True,'current_retirement_exact':True}
    return result

def run(mode,prepared,expected,output):
    verify(prepared,expected);fresh(output)
    env=dict(os.environ)
    for key in ['PYTHONHOME','PYTHONPATH','PYTHONOPTIMIZE','LD_LIBRARY_PATH']:env.pop(key,None)
    env.update(LD_LIBRARY_PATH='/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE',TMPDIR=str(output))
    cmd=['/opt/Xilinx/Vivado/2022.2/bin/vivado','-mode','batch','-nojournal','-log',str(output/'vivado.log'),
         '-source',str(prepared/'staged_fft_experiment.tcl'),'-tclargs',mode,str(prepared),expected,str(output)]
    started=time.time();result={'mode':mode,'command':cmd,'prepared_sha':expected,'started':started}
    (output/'command.json').write_text(json.dumps(result,indent=2)+'\n')
    try:
        with (output/'stdout.log').open('w') as log:
            p=subprocess.Popen(cmd,cwd=output,env=env,stdout=log,stderr=subprocess.STDOUT)
            (output/'process.json').write_text(json.dumps({'pid':p.pid,'started':started})+'\n')
            try:result['returncode']=p.wait(timeout=660)
            except subprocess.TimeoutExpired:
                p.terminate();p.wait(timeout=30);raise
        require(result['returncode']==0,'vendor command failed; see '+str(output/'stdout.log'))
        if mode=='sim':result['audit']=audit_finalcapacity(output) if final_capacity_compiled(prepared) else (audit_productstage(output) if product_stage_compiled(prepared) else (audit_forwardreceipt(output) if forward_receipt_compiled(prepared) else audit_ackcombined_sim(output)))
        elif mode=='ack':result['audit']=audit_finalcapacity(output,auxiliary=True) if final_capacity_compiled(prepared) else (audit_productstage(output,auxiliary=True) if product_stage_compiled(prepared) else (audit_forwardreceipt(output,auxiliary=True) if forward_receipt_compiled(prepared) else audit_ackcombined_aux(output)))
        if mode in {'sim','ack'} and split_capacity_compiled(prepared):
            result['audit']=audit_splitcapacity(output,auxiliary=mode=='ack')
    except Exception as exc:
        result['error']=f'{type(exc).__name__}: {exc}'
        raise
    finally:
        result['elapsed']=time.time()-started
        try:verify(prepared,expected);result['sources_unchanged']=True
        finally:(output/'outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('output',type=Path)
    run_parser=sub.add_parser('run');run_parser.add_argument('mode',choices=['sim','ack','synth'])
    run_parser.add_argument('prepared',type=Path);run_parser.add_argument('expected');run_parser.add_argument('output',type=Path)
    a=parser.parse_args()
    print(json.dumps(prepare(a.output) if a.command=='prepare' else run(a.mode,a.prepared,a.expected,a.output),indent=2))

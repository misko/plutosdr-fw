"""Source-bound reset CDC evidence; structural success is not timing signoff."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from staged_fft_experiment import ROOT, require, sha, verify, audit_outputmetadata
from route_starlink_staged_fft import verify_ack_auxiliary
from package_staged_fft_evidence import write_verified_archive

PIN='28b4f9dbf7e61175b9dba8b87136438f6a134b88f111f0afb23e03ea344c736a'
DCP_PIN='6ac76c672827b6b227db586d316bf81921241cb6d15debd540f132c9ee6ee741'
SIM=Path('project/staged_fft.sim/sim_1/behav/xsim')


def assess(root):
    prepared=root/'prepared-v1';verify(prepared,PIN)
    names=(prepared/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    require(len(names)==22 and all(n in names for n in ['starlink_pss_mailbox_reset_receipt.v',
        'starlink_pss_output_reset_receipt.v','starlink_pss_reset_receipt_barrier.v']),'compiled reset variants')
    main=audit_outputmetadata(root/'sim-v1')
    aux=verify_ack_auxiliary(root/'ack-v1',PIN,prepared)
    outcomes={}
    for mode in ['sim','ack','synth']:
        result=json.loads((root/(mode+'-v1')/'outcome.json').read_text())
        require(result.get('returncode')==0 and result.get('sources_unchanged') is True and 'error' not in result,'terminal actual/synthesis')
        require(result['prepared_sha']==PIN and result['command'][-3]==str(prepared),'source-matched actual/synthesis')
        outcomes[mode]=result
    require(json.dumps(main,sort_keys=True)==json.dumps(outcomes['sim']['audit'],sort_keys=True),'main re-audit')
    route=json.loads((root/'route-v1/outcome.json').read_text())
    require(route.get('returncode')==0 and route.get('sources_unchanged') is True and 'error' not in route,'terminal route')
    require(route['prepared_sha']==PIN and all(sha(Path(p))==s for p,s in route['before'].items()),'route source pins')
    require(sha(root/'route-v1/route/retained_output_routed.dcp')==route['routed_dcp_sha']==DCP_PIN,'routed DCP pin')
    receipt=dict(line.split('=',1) for line in (root/'structure-v1/receipt.txt').read_text().splitlines())
    require(receipt['source_sha256']==DCP_PIN and receipt['script_sha256']==sha(ROOT/'tools/inspect_reset_receipts.tcl'),'inspection pins')
    require(receipt['first_stage_fanout_clean']==receipt['purge_source_registered']=='true','structural gate')
    require(receipt['constraints_changed']==receipt['physical_signoff']==receipt['deployment_eligible']=='false','no constraint/deployment claim')
    for name,marker in [('structure-v1','RESET_RECEIPT_STRUCTURE_PASS_NO_CONSTRAINT_OR_DEPLOYMENT_CHANGE'),
                        ('metadata-v1','OUTPUT_METADATA_CDC_INSPECTION_PASS_NO_CONSTRAINT_OR_DEPLOYMENT_CHANGE')]:
        log=(root/(name+'.log')).read_text()
        require(len(re.findall('^'+marker+'$',log,re.M))==1 and not re.search(r'^ERROR:',log,re.M),'completed vendor inspection')
    controls=dict(line.split('=',1) for line in (root/'structure-v1/controls.txt').read_text().splitlines())
    for bank in ['source_bank','output_bank']:
        for name in ['request_sync','acknowledge_sync']:
            require(controls[bank+'.'+name+'.endpoints']=='{'+bank+'/'+name+'_reg[1]/D}', 'exclusive first-stage fanout')
    require(controls['purge.source']=='epoch_barrier/slow_purged_reg','registered purge source')
    cdc=(root/'structure-v1/cdc.rpt').read_text()
    counts=dict((rule,int(count)) for rule,count in re.findall(r'^(CDC-\d+)\s+(?:Critical|Warning|Info)\s+(\d+)\s',cdc,re.M))
    require(counts=={'CDC-3':9,'CDC-15':208},'complete CDC summary; no hidden critical finding')
    with (root/'metadata-v1/paths.tsv').open() as f:bits=list(csv.DictReader(f,delimiter='\t'))
    require(len(bits)==37 and [int(v['bit']) for v in bits]==list(range(37)),'all metadata bits')
    for bit,row in enumerate(bits):
        require(row['source']==f'output_bank/metadata_in_hold_reg[{bit}]/Q' and row['destination']==f'output_bank/metadata_out_hold_reg[{bit}]/D','same-bit paths')
        require(row['source_clock']=='island_175' and row['destination_clock']=='source_100','metadata clocks')
        report=(root/f'metadata-v1/bit_{bit}_max.rpt').read_text()
        require(float(re.search(r'Data Path Delay:\s*([0-9.]+)ns',report)[1])==float(row['data_delay_ns']),'independent bit delay agreement')
    suites=ET.parse(root/'regression-v1.xml').getroot().findall('testsuite')
    require(sum(int(s.attrib['tests']) for s in suites)==670 and all(int(s.attrib[k])==0 for s in suites for k in ['failures','errors','skipped']),'complete regression')
    parent=Path('/dev/shm/starlink-output-metadata.MB5fY8/sim-v3')/SIM/'staged_words.csv'
    require(sha(parent)=='210d9e1f5b5e8f39d48e299f0fdaf6708faa7d553913f819f558f59e576d5b44','parent numerical pin')
    with parent.open() as f:old=list(csv.reader(f))
    with (root/'sim-v1'/SIM/'staged_words.csv').open() as f:new=list(csv.reader(f))
    require(len(old)==len(new)==64513 and Counter(map(tuple,old))==Counter(map(tuple,new)),'all indexed records exact')
    timing=json.loads((root/'route-v1/audit.json').read_text())
    report=(root/'route-v1/route/timing_unqualified.rpt').read_text()
    values=re.search(r'\n\s*WNS\(ns\).*?\n\s*-+[^\n]*\n([^\n]+)',report,re.S)[1].split()
    require([timing['wns_ns'],timing['tns_ns'],timing['setup_failing_endpoints']]==
            [float(values[0]),float(values[1]),int(values[2])],'timing summary agreement')
    paths=dict(line.split('=',1) for line in (root/'route-v1/route/paths.txt').read_text().splitlines())
    require(timing['same_domain_175_setup_ns']==float(paths['island_175.island_175.max.slack']),'same-domain timing agreement')
    require(timing['internal_timing_pass'] is False and timing['deployment_eligible'] is False,'known failing route is not a release')
    return {'prepared_sha':PIN,'routed_dcp_sha':DCP_PIN,'tests':670,'numerical_records':64512,
       'changed_chronological_positions':sum(a!=b for a,b in zip(old,new)),
       'service_clocks':[int(c[1]) for c in main['contexts']],
       'actual_elapsed_s':{mode:r['elapsed'] for mode,r in outcomes.items()},
       'route_elapsed_s':route['elapsed'],'cdc_counts':counts,'first_stage_fanout_clean':True,
       'purge_source_registered':True,'output_metadata_max_delay_ns':max(float(v['data_delay_ns']) for v in bits),
       'output_metadata_min_delay_ns':min(float(v['data_delay_ns']) for v in bits),'timing':timing,
       'constraints_changed':False,'analog_metastability_proven':False,'full_receiver_signoff':False,
       'deployment_eligible':False}


def package(root,output):
    result=assess(root)
    require(result==json.loads((root/'assessment.json').read_text()),'saved assessment mismatch')
    sources={}
    suffixes={'.json','.log','.txt','.rpt','.tsv','.xml','.v','.sv','.vhd','.tcl','.xdc','.csv','.mem','.coe','.dcp','.sha256'}
    for folder in ['prepared-v1','sim-v1','ack-v1','synth-v1','route-v1','structure-v1','metadata-v1',
                   'component-v1','preflight-v1','regression-v1','audit-v1']:
        for p in sorted((root/folder).rglob('*')):
            if p.is_symlink() or any(a.is_symlink() for a in p.parents) or '.Xil' in p.parts:continue
            # Inherited verifier tests copy/mutate large numerical fixtures and
            # checkpoints. Preserve their scripts/reports, not duplicate binary
            # inputs. Actual campaign CSVs and synth/routed DCPs remain included.
            if folder in {'regression-v1','audit-v1'} and p.suffix in {'.csv','.dcp'}:continue
            if p.is_file() and (p.suffix in suffixes or p.name=='SHA256SUMS'):sources[str(p.relative_to(root))]=p
    for p in root.iterdir():
        if p.is_file() and p.suffix in {'.json','.xml','.log'}:sources[p.name]=p
    for folder,pattern in [('tools','*.py'),('tools','inspect*.tcl'),('tests','test_*reset*.py')]:
        for p in (ROOT/folder).glob(pattern):sources['current/'+str(p.relative_to(ROOT))]=p
    for name in ['tests/test_starlink_split_output_metadata.py','tests/test_starlink_preflight_publication.py',
                 'tests/test_starlink_output_metadata_cdc.py','tests/fixtures/tb_output_metadata_cdc.sv',
                 'docs/starlink-reset-receipts-20260911.md']:
        sources['current/'+name]=ROOT/name
    return write_verified_archive(output,sources)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('--archive',type=Path)
    args=parser.parse_args()
    if args.archive:result=package(args.root,args.archive)
    else:
        result=assess(args.root);target=args.root/'assessment.json';require(not target.exists(),'no overwrite')
        target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

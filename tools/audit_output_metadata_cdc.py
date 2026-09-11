"""Join bounded RTL evidence with routed paths; never infer CDC qualification."""
import argparse
import csv
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from staged_fft_experiment import ROOT, require, sha
from inspect_output_metadata_cdc import DCP, PIN


def assess(root):
    inspected=root/'inspection-v1';files=inspected/'inspection'
    outcome=json.loads((inspected/'outcome.json').read_text())
    require(outcome.get('returncode')==0 and outcome.get('sources_unchanged') is True and 'error' not in outcome,'terminal source-bound inspection')
    require(outcome.get('constraints_changed') is False and sha(DCP)==PIN,'unchanged routed checkpoint')
    require(all(sha(Path(name))==value for name,value in outcome['before'].items()),'inspection source pins')
    with (files/'paths.tsv').open() as stream:rows=list(csv.DictReader(stream,delimiter='\t'))
    require(len(rows)==37 and [int(row['bit']) for row in rows]==list(range(37)),'complete exact 37-bit bundle')
    delays=[]
    for row in rows:
        bit=int(row['bit'])
        require(row['source']==f'output_bank/metadata_in_hold_reg[{bit}]/Q' and
                row['destination']==f'output_bank/metadata_out_hold_reg[{bit}]/D','exact same-bit endpoints')
        require(row['source_clock']=='island_175' and row['destination_clock']=='source_100','exact clocks')
        report=(files/f'bit_{bit}_max.rpt').read_text()
        delay=float(re.search(r'Data Path Delay:\s*([0-9.]+)ns',report)[1])
        slack=float(re.search(r'Slack \((?:MET|VIOLATED)\)\s*:\s*([-0-9.]+)ns',report)[1])
        require(delay==float(row['data_delay_ns']) and slack==float(row['slack_ns']),'per-bit report agreement')
        delays.append(delay)
    receipt=dict(line.split('=',1) for line in (root/'fanout-v1/receipt.txt').read_text().splitlines())
    require(receipt['source_sha256']==PIN and receipt['script_sha256']==sha(ROOT/'tools/inspect_metadata_control_fanout.tcl'), 'fanout source pins')
    require(all(receipt[key]=='false' for key in ['constraints_changed','runtime_changed','physical_signoff']),'read-only fanout inspection')
    fanout=dict(line.split('=',1) for line in (root/'fanout-v1/control_fanout.txt').read_text().splitlines())
    extras={}
    for bank in ['source_bank','output_bank']:
        for name in ['request_sync','acknowledge_sync']:
            key=bank+'.'+name
            require(fanout[key+'.stage0_async_reg']==fanout[key+'.stage1_async_reg']=='1','both ASYNC_REG stages required')
            endpoints=re.findall(r'\{([^}]+)\}',fanout[key+'.endpoints'])
            required=f'{bank}/{name}_reg[1]/D'
            require(required in endpoints,'missing actual second-stage connection')
            extra=sorted(set(endpoints)-{required})
            if extra:extras[key]=extra
    summary=(files/'cdc.rpt').read_text()
    cdc1=int(re.search(r'^CDC-1\s+Critical\s+(\d+)',summary,re.M)[1])
    cdc10=int(re.search(r'^CDC-10\s+Critical\s+(\d+)',summary,re.M)[1])
    suites=ET.parse(root/'contract-v1.xml').getroot().findall('testsuite')
    require(sum(int(s.attrib['tests']) for s in suites)==17 and
            all(int(s.attrib['failures'])==int(s.attrib['errors'])==int(s.attrib['skipped'])==0 for s in suites),'complete 17-test RTL contract')
    observations=[]
    for log in sorted((root/'contract-v1').glob('test_actual_bundle*/simulate.log')):
        if log.parent.is_symlink():continue
        text=log.read_text();require(not re.search(r'FATAL|ERROR|FAIL',text,re.I),'failed RTL contract')
        lines=re.findall(r'^OUTPUT_CDC_CONTRACT_PASS (.*)$',text,re.M)
        require(len(lines)==1,'one bounded contract receipt')
        fields=dict((key,int(value)) for key,value in (part.split('=') for part in lines[0].split()))
        require(fields['completed']==13 and fields['resets']==10 and fields['reset_checks']==80,'complete reset/reader inventory')
        require(fields['min_publish_capture_ps']>=2*fields['reader_period_ps']-2 and
                fields['min_first_capture_ps']>=511*fields['writer_period_ps']+2*fields['reader_period_ps']-2 and
                fields['min_ack_rewrite_ps']>=2*fields['writer_period_ps']-2,'contract timing bounds')
        observations.append(fields)
    expected={(w,r,p) for w,r in [(5714,10000),(5000,10000),(10000,5714)] for p in [0,1,1234,4999]}
    require(len(observations)==12 and {(v['writer_period_ps'],v['reader_period_ps'],v['phase_ps']) for v in observations}==expected,'exact clock/phase coverage')
    return {'routed_checkpoint_sha256':PIN,'metadata_bits':37,'max_data_delay_ns':max(delays),
            'min_data_delay_ns':min(delays),'first_stage_extra_endpoints':extras,
            'cdc1_critical_count':cdc1,'cdc10_critical_count':cdc10,'digital_contract_pass':True,
            'bounded_clock_phase_runs':12,'complete_reader_blocks':sum(v['completed'] for v in observations),
            'reset_cases':sum(v['resets'] for v in observations),'observations':observations,
            'proposed_output_datapath_limit_ns':10.0,'proposed_limit_applied':False,
            'control_structure_qualified':not extras and cdc1==0 and cdc10==0,
            'constraint_change_authorized':False,'analog_metastability_proven':False,
            'full_receiver_or_board_signoff':False,'deployment_eligible':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path)
    args=parser.parse_args();result=assess(args.root)
    destination=args.root/'cdc_assessment.json';require(not destination.exists(),'no assessment overwrite')
    destination.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

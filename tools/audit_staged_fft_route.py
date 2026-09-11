"""Cross-check source receipts, routed checkpoint and independent report views."""
import argparse
import json
from pathlib import Path
import re

from staged_fft_experiment import require, sha

def audit(root):
    outcome=json.loads((root/'outcome.json').read_text())
    require(outcome.get('returncode')==0 and outcome.get('sources_unchanged') is True and 'error' not in outcome,'terminal route success')
    require(all(sha(Path(p))==value for p,value in outcome['before'].items()),'source receipt mismatch')
    reports=root/'route'
    require(sha(reports/'retained_output_routed.dcp')==outcome['routed_dcp_sha'],'routed checkpoint mismatch')
    require(sha(reports/'probe.tcl')==sha(root/'route.tcl')=='034d1eaa197757b762644acd0cad9dc267338ae23fd5d757290c8485d0f1ac9a','route recipe mismatch')
    text=(reports/'timing_unqualified.rpt').read_text()
    summary=re.search(r'\n\s*WNS\(ns\).*?\n\s*-+[^\n]*\n([^\n]+)',text,re.S)
    require(summary is not None,'timing summary missing')
    values=summary[1].split();require(len(values)==12,'complete setup/hold/pulse summary')
    wns,tns=float(values[0]),float(values[1]);setup_fail=int(values[2]);setup_total=int(values[3])
    whs=float(values[4]);hold_fail=int(values[6]);pulse=float(values[8]);pulse_fail=int(values[10])
    paths=dict(line.split('=',1) for line in (reports/'paths.txt').read_text().splitlines())
    setup=[]
    for source in ['source_100','island_175']:
        for destination in ['source_100','island_175']:
            for kind in ['max','min']:
                key=f'{source}.{destination}.{kind}'
                report=(reports/f'{source}_{destination}_{kind}.rpt').read_text()
                match=re.search(r'Slack \((?:VIOLATED|MET)\)\s*:\s*([-\d.]+)ns',report)
                require(match is not None and float(match[1])==float(paths[key+'.slack']),'timing pair disagreement')
                if kind=='max':setup.append((float(match[1]),source,destination))
    worst_slack,worst_source,worst_destination=min(setup)
    require(worst_slack==wns,'summary/clock-pair worst slack disagreement')
    route=(reports/'route_status.rpt').read_text()
    def route_count(label):return int(re.search(re.escape(label)+r'\.*\s*:\s*(\d+)',route)[1])
    nets=route_count('# of fully routed nets')
    require(nets==route_count('# of routable nets') and route_count('# of nets with routing errors')==0,'incomplete/error routing')
    utilization=(reports/'utilization.rpt').read_text()
    def used(label):return int(re.search(r'\|\s*'+re.escape(label)+r'\s*\|\s*(\d+)\s*\|',utilization)[1])
    worst=(reports/f'{worst_source}_{worst_destination}_max.rpt').read_text()
    first=re.split(r'Slack \((?:VIOLATED|MET)\)',worst,maxsplit=2)[1]
    worst_key=f'{worst_source}.{worst_destination}.max'
    result={'wns_ns':wns,'tns_ns':tns,'setup_failing_endpoints':setup_fail,'setup_total_endpoints':setup_total,
            'hold_slack_ns':whs,'hold_failures':hold_fail,'pulse_slack_ns':pulse,'pulse_failures':pulse_fail,
            'fully_routed_nets':nets,'routing_errors':0,'lut':used('Slice LUTs'),'ff':used('Slice Registers'),
            'dsp':used('DSPs'),'ramb18':used('RAMB18'),'ramb36':used('RAMB36/FIFO*'),
            'worst_start':paths[worst_key+'.start'],'worst_end':paths[worst_key+'.end'],
            'worst_clock_pair':[worst_source,worst_destination],
            'same_domain_175_setup_ns':float(paths['island_175.island_175.max.slack']),
            'logic_levels':int(re.search(r'Logic Levels:\s*(\d+)',first)[1]),
            'data_delay_ns':float(re.search(r'Data Path Delay:\s*([\d.]+)ns',first)[1]),
            'internal_timing_pass':wns>=0 and setup_fail==0 and whs>=0 and hold_fail==0 and pulse_fail==0,
            'unconstrained_inputs':int(re.search(r'checking no_input_delay \((\d+)\)',text)[1]),
            'unconstrained_outputs':int(re.search(r'checking no_output_delay \((\d+)\)',text)[1]),
            'source_and_checkpoint_verified':True,'full_receiver_or_physical_signoff':False,'deployment_eligible':False}
    destination=root/'audit.json';require(not destination.exists(),'no audit overwrite')
    destination.write_text(json.dumps(result,indent=2)+'\n');return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path)
    print(json.dumps(audit(parser.parse_args().root),indent=2))

"""Cross-check a registered-boundary descriptor-table experiment, not board signoff."""
import argparse
import hashlib
import json
from pathlib import Path
import re

def audit(root):
    run=root/'run'
    execution=json.loads((root/'execution.json').read_text())
    assert execution['vendor_exit']==0 and execution['timed_out'] is False and execution['sources_unchanged'] is True
    def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    assert sha(run/'descriptor_commands_routed.dcp')==execution['dcp_sha256']
    pins=json.loads((root/'before.json').read_text())
    assert len(pins)==4 and pins=={n:sha(root/'source_snapshot'/n) for n in pins}
    for name in pins:
        if name.endswith(('.v','.tcl')):
            assert sha(run/Path(name).name)==pins[name]
    text=(run/'timing.rpt').read_text()
    pattern=r'^\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+)\s+(\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+)\s+(\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+)\s+(\d+)\s*$'
    rows=re.findall(pattern,text,re.M)
    assert len(rows)==1
    v=rows[0]
    wns,whs,pulse=float(v[0]),float(v[4]),float(v[8])
    for name,expected in [('internal_setup.rpt',wns),('internal_hold.rpt',whs)]:
        values=re.findall(r'^Slack \([^\n]*?\)\s*:\s*(-?\d+\.\d+)ns',(run/name).read_text(),re.M)
        assert len(values)==20 and float(values[0])==expected
    counts=dict(setup=int(v[2]),hold=int(v[6]),pulse=int(v[10]))
    internal_pass=min(wns,whs,pulse)>=0 and not any(counts.values())
    assert ('Timing constraints are not met.' in text)==(not internal_pass)
    checks=(run/'check_timing.rpt').read_text()
    for item in ('no_clock','unconstrained_internal_endpoints','loops','latch_loops'):
        assert f'checking {item} (0)' in checks
    assert 'checking no_input_delay (141)' in checks and 'checking no_output_delay (114)' in checks
    commands=[s.strip() for s in (run/'constraints.xdc').read_text().splitlines() if s.strip() and not s.lstrip().startswith('#')]
    assert commands==['create_clock -period 5.714 -name island_175 [get_ports clk]','current_instance -quiet'],commands
    hierarchy={}
    for row in (run/'hierarchy.rpt').read_text().splitlines():
        cols=[c.strip() for c in row.split('|')[1:-1]]
        if len(cols)==10 and cols[2].isdigit():
            hierarchy[cols[0]]=dict(lut=int(cols[2]),ff=int(cols[6]),ram36=int(cols[7]),ram18=int(cols[8]),dsp=int(cols[9]))
    top=hierarchy['descriptor_commands_timing_probe'];slots=hierarchy['commands']
    assert top['ff']==slots['ff']+254 and top['ff']==638 and top['ram36']==top['ram18']==top['dsp']==0
    status=(run/'route_status.rpt').read_text()
    def nets(label):
        values=re.findall(re.escape(label)+r'\.+\s*:\s*(\d+)\s*:',status)
        assert len(values)==1
        return int(values[0])
    routed=nets('fully routed nets');errors=nets('nets with routing errors')
    assert routed>0 and errors==0
    report=dict(dcp_sha256=execution['dcp_sha256'],source_snapshot_verified=True,
        internal_timing_pass=internal_pass,wns_ns=wns,tns_ns=float(v[1]),whs_ns=whs,pulse_ns=pulse,
        failing_endpoints=counts,total_setup_endpoints=int(v[3]),table_resources=slots,probe_resources=top,
        fully_routed_nets=routed,routing_errors=errors,unconstrained_io=dict(inputs=141,outputs=114),
        physical_clock_source_qualified=False,complete_receiver_qualified=False,deployment_eligible=False)
    with (root/'audit.json').open('x') as handle:json.dump(report,handle,indent=2)
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root',type=Path)
    print(json.dumps(audit(parser.parse_args().root)))

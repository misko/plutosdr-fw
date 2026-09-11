"""Quarantined private occupancy must never become public authority."""
from pathlib import Path
import re
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
PARENT=Path('/dev/shm/starlink-replay-fence.I2dOca4T/prepared-v1')
GUARD='starlink_pss_result_guard_owner_view.v'
TOP='starlink_pss_fft_staged_output_impl.v'

def remove_block(text,label,replacement=''):
    text,count=re.subn(r' *// BEGIN '+label+r'\n.*? *// END '+label+r'\n',lambda _:replacement,text,flags=re.S)
    assert count==1;return text

def undo_guard(text):
    text=remove_block(text,'PRIVATE QUARANTINE OFFER','  assign mailbox_private_valid = resetn && active && !protocol_fault && return_valid;\n')
    line='  parameter integer PRIVATE_QUARANTINE_OFFER = 0,\n'
    assert text.count(line)==1;return text.replace(line,'',1)

def undo_top(text):
    if '// BEGIN SPLIT PREFLIGHT PROFILE' in text:
        from tests.test_starlink_split_preflight_identity import undo_top as undo_split
        text=undo_split(text)
    text=remove_block(text,'PRIVATE QUARANTINE PROFILE')
    before='  parameter integer REPLAY_QUIET_PUBLICATION = 0,\n  parameter integer PRIVATE_QUARANTINE_OFFER = 0'
    assert text.count(before)==1;text=text.replace(before,'  parameter integer REPLAY_QUIET_PUBLICATION = 0',1)
    line='    .PRIVATE_QUARANTINE_OFFER(PRIVATE_QUARANTINE_OFFER && OWNER==1),\n'
    assert text.count(line)==1;return text.replace(line,'',1)

def undo_bench(text):
    if '// BEGIN SPLIT PREFLIGHT WITNESS' in text:
        from tests.test_starlink_split_preflight_identity import undo_bench as undo_split
        text=undo_split(text)
    text=remove_block(text,'PRIVATE QUARANTINE WITNESS')
    text=text.replace('      report_private_quarantine; // PRIVATE QUARANTINE REPORT\n','',1)
    text=text.replace(',.PRIVATE_QUARANTINE_OFFER(1)) dut',') dut',1)
    for prefix in ['dut.owners[1].result_guard','original_inverse_ack']:
        line=prefix+'.mailbox_input_valid,\n'
        assert text.count(line)==1
        text=text.replace(line,prefix+'.mailbox_input_valid,'+prefix+'.mailbox_private_valid,\n',1)
    return text

def test_exact_opt_in_source_delta():
    assert undo_guard((RTL/GUARD).read_text())==(PARENT/GUARD).read_text()
    assert undo_top((RTL/TOP).read_text())==(PARENT/TOP).read_text()
    name='tb_fft_staged_output.sv';assert undo_bench((RTL/name).read_text())==(PARENT/name).read_text()
    assert (ROOT/'tools/staged_fft_experiment.tcl').read_text().replace(' PARALLEL_KERNEL_READY=1','',1).replace(' MONOTONIC_OUTER_RESET=1','',1).replace(' SPLIT_PREFLIGHT_IDENTITY=1','',1).replace(' PRIVATE_QUARANTINE_OFFER=1','',1)==(PARENT/'staged_fft_experiment.tcl').read_text()

def run(tmp_path,mode=1,mutation=None):
    source=(RTL/GUARD).read_text()
    if mutation=='drop_reset':source=source.replace('(resetn && active_private && return_occupied)','(active_private && return_occupied)',1)
    if mutation=='drop_occupancy':source=source.replace('(resetn && active_private && return_occupied)','(resetn && active_private)',1)
    if mutation=='leak_public':source=source.replace('assign mailbox_input_valid = resetn && active && !protocol_fault && return_valid &&','assign mailbox_input_valid = mailbox_private_valid || resetn && active && !protocol_fault && return_valid &&',1)
    candidate=tmp_path/'candidate.v';candidate.write_text(source)
    reference=tmp_path/'reference.v';reference.write_text((PARENT/GUARD).read_text().replace('module starlink_pss_result_guard_owner_view #','module reference_guard #',1))
    ports=source.split(') (',1)[1].split(');',1)[0]
    decl=[];connections=[]
    for width,names in re.findall(r'input wire\s*(\[[^\]]+\])?\s*([^\n]+)',ports):
        for name in names.split(','):
            name=name.strip()
            if name:
                assert re.fullmatch(r'\w+',name)
                decl.append(f"reg {width or ''} {name}='0;");connections.append(f'.{name}({name})')
    outputs=[]
    for width,names in re.findall(r'output (?:wire|reg)\s*(\[[^\]]+\])?\s*([^\n]+)',ports):
        for name in names.split(','):
            name=name.strip()
            if name and name!='mailbox_private_valid':outputs.append(name)
    comparison=' || '.join('dut.'+n+'!==refguard.'+n for n in outputs)
    bench='`timescale 1ns/1ps\nmodule tb;\n'+'\n'.join(decl)+'\n'
    bench+='starlink_pss_result_guard_owner_view #(.CERTIFIED_PRIVATE_ADMISSION(1),.PRIVATE_QUARANTINE_OFFER('+str(mode)+')) dut('+','.join(connections)+');\n'
    bench+='reference_guard #(.CERTIFIED_PRIVATE_ADMISSION(1)) refguard('+','.join(connections)+');\n'
    bench+='''integer checks=0,differences=0,n;reg [31:0] rng=32'h516dde08;
task check;begin #0.001;
 if(__COMPARE__)$fatal(1,"public/reference mismatch");
 if(dut.mailbox_private_valid!==refguard.mailbox_private_valid)begin
   if(__MODE__!=1 || dut.protocol_fault!==1 || dut.mailbox_private_valid!==1 ||
      refguard.mailbox_private_valid!==0 || dut.mailbox_input_valid!==0 ||
      dut.mailbox_commit_valid!==0 || dut.job_ready!==0 || dut.owner_ack_accept!==0)
     $fatal(1,"unfenced private difference");
   differences=differences+1;
 end
 if(dut.mailbox_private_valid!==((__MODE__==1) ? (resetn && dut.active_private && dut.return_occupied) : refguard.mailbox_private_valid))
   $fatal(1,"private occupancy/reset mismatch");
 checks=checks+1;
end endtask
task tick;begin clk=0;#1;check;clk=1;#1;check;clk=0;end endtask
task reset_epoch;begin
 resetn=0;job_valid=0;core_output_tvalid=0;core_status_tvalid=0;external_fault_now=0;
 certified_input_beat=0;certified_input_complete=0;core_event_frame_started=0;
 mailbox_input_fault=0;tick;resetn=1;tick;
end endtask
initial begin
 input_bank_reserved=1;output_bank_reserved=1;mailbox_input_ready=1;
 for(n=0;n<32;n=n+1)begin
   reset_epoch;job_valid=1;tick;job_valid=0;tick;
   if(dut.active!==1)$fatal(1,"job did not admit");
   core_output_tdata=n;core_output_tuser=n;core_output_tvalid=1;tick;
   core_output_tvalid=0;tick;tick;
   if(dut.protocol_fault!==1 || dut.active_private!==0)$fatal(1,"quarantine did not clear private occupancy");
 end
 reset_epoch;
 for(n=0;n<4096;n=n+1)begin
   rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);
   resetn=(n%19)!=0;job_valid=rng[0];core_output_tvalid=rng[1];core_status_tvalid=rng[2];
   external_fault_now=rng[3];core_output_tuser=rng;core_output_tdata={rng,rng[15:0]};
   mailbox_input_ready=rng[4];mailbox_input_fault=rng[5];tick;
 end
 if(__MODE__==1 && differences<32)$fatal(1,"missing quarantined differences");
 if(__MODE__==0 && differences!=0)$fatal(1,"default changed");
 $display("PRIVATE_QUARANTINE_COMPONENT_PASS checks=%0d differences=%0d",checks,differences);$finish;
end
endmodule
'''.replace('__COMPARE__',comparison).replace('__MODE__',str(mode))
    path=tmp_path/'bench.sv';path.write_text(bench)
    result=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(candidate),str(reference),str(path)],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr);return result

@pytest.mark.parametrize('mode',[0,1])
def test_full_guard_public_reference_and_quarantine(tmp_path,mode):
    result=run(tmp_path,mode);assert result.returncode==0 and 'PRIVATE_QUARANTINE_COMPONENT_PASS' in result.stdout,result.stdout+result.stderr

@pytest.mark.parametrize('mutation',['drop_reset','drop_occupancy','leak_public'])
def test_unsafe_private_offers_rejected(tmp_path,mutation):
    result=run(tmp_path,mutation=mutation);assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout+result.stderr

@pytest.mark.parametrize('mode',[2,"32'bx","32'bz"])
def test_unknown_or_unsupported_mode_rejected(tmp_path,mode):
    result=run(tmp_path,mode);assert result.returncode!=0 and 'private quarantine offer requires a known mode' in result.stdout,result.stdout+result.stderr

@pytest.mark.parametrize('mode',[0,1])
def test_extracted_four_state_private_boundary(tmp_path,mode):
    source=(RTL/GUARD).read_text()
    assignment=re.search(r'  assign mailbox_private_valid = .*?;',source,re.S)[0]
    bench='''`timescale 1ns/1ps
module tb;
localparam PRIVATE_QUARANTINE_OFFER=__MODE__;
reg resetn,active_private,return_occupied,protocol_fault;
wire active=active_private && !protocol_fault;
wire return_valid=return_occupied && active;
wire original=resetn && active && !protocol_fault && return_valid;
wire mailbox_private_valid;
__ASSIGN__
function val(input integer n);case(n)0:val=0;1:val=1;2:val=1'bx;3:val=1'bz;endcase endfunction
integer n;
initial begin
 for(n=0;n<256;n=n+1)begin
   resetn=val(n&3);active_private=val((n>>2)&3);return_occupied=val((n>>4)&3);protocol_fault=val((n>>6)&3);#1;
   if(__MODE__==0 && mailbox_private_valid!==original)$fatal(1,"default four-state mismatch");
   if(protocol_fault===0 && mailbox_private_valid!==original)$fatal(1,"healthy four-state mismatch");
   if(original===1 && mailbox_private_valid!==1)$fatal(1,"lost original offer");
   if(mailbox_private_valid===1 && original!==1 && protocol_fault===0)$fatal(1,"healthy new offer");
   if(resetn===0 && mailbox_private_valid!==0)$fatal(1,"reset not fenced");
 end
 $display("PRIVATE_QUARANTINE_FOUR_STATE_PASS cases=256");$finish;
end
endmodule
'''.replace('__MODE__',str(mode)).replace('__ASSIGN__',assignment)
    path=tmp_path/'bench.sv';path.write_text(bench)
    result=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(path)],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr);assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0 and 'PRIVATE_QUARANTINE_FOUR_STATE_PASS cases=256' in result.stdout,result.stdout+result.stderr

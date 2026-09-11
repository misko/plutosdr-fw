"""Parallel metadata comparisons preserve the original mailbox's current checks."""
import hashlib
from pathlib import Path
import re
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
PARENT=Path('/dev/shm/starlink-split-capacity.URCQhd/prepared-v1')
OLD=PARENT/'starlink_pss_mailbox_owner_view.v'
NEW=RTL/'starlink_pss_mailbox_split_metadata_view.v'


def undo_output_top(text):
    before='starlink_pss_mailbox_split_metadata_view #(.METADATA_WIDTH(37), .RESET_RELEASE_EXTERNAL(1),'
    assert text.count(before)==1
    text=text.replace(before,'starlink_pss_mailbox_owner_view #(.METADATA_WIDTH(37), .RESET_RELEASE_EXTERNAL(1),',1)
    before=('    .input_metadata_select(output_publication_busy),\n'
            '    .input_metadata_live({inverse_tag,guard_return_metadata[1][4:0]}),\n'
            '    .input_metadata_replay({output_replay_tag,output_descriptor_payload[4:0]}), .input_fault(output_bank_fault),\n')
    after=('    .input_metadata(output_publication_busy ? {output_replay_tag,output_descriptor_payload[4:0]} :\n'
           '      {inverse_tag,guard_return_metadata[1][4:0]}), .input_fault(output_bank_fault),\n')
    assert text.count(before)==1
    return text.replace(before,after,1)


def test_exact_mailbox_and_top_inverse():
    assert hashlib.sha256((PARENT/'SHA256SUMS').read_bytes()).hexdigest()=='d60c44681da7625f756b05315b626577a165eb29da9761d528e126508c9155f4'
    assert hashlib.sha256(OLD.read_bytes()).hexdigest()=='de060a7930be1d65cc91903da447e51ead3efad4ebed4b61e4f257e45d76d2d6'
    old=OLD.read_text();text=NEW.read_text()
    text=text.replace('module starlink_pss_mailbox_split_metadata_view #(','module starlink_pss_mailbox_owner_view #(',1)
    text=text.replace('  input wire [METADATA_WIDTH-1:0] input_metadata_live, input_metadata_replay,\n  input wire input_metadata_select,',
                      '  input wire [METADATA_WIDTH-1:0] input_metadata,',1)
    compare=old[old.index('  wire metadata_matches;'):old.index('  wire input_framing_valid')]
    text,count=re.subn(r'  // BEGIN SPLIT METADATA COMPARISON\n.*?  // END SPLIT METADATA COMPARISON\n',lambda _:compare,text,flags=re.S)
    assert count==1 and text==old
    names=(PARENT/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    assert len(names)==21
    for name in names:
        if (RTL/name).exists():
            current=(RTL/name).read_text()
            if name=='starlink_pss_fft_staged_output_impl.v':current=undo_output_top(current)
            assert current==(PARENT/name).read_text(),name


def run(tmp_path,mutant=None):
    source=NEW.read_text()
    if mutant=='ignore_replay':source=source.replace('assign branch_matches[branch] = &group_equal;',"assign branch_matches[branch] = branch == 1 ? 1'b1 : &group_equal;",1)
    elif mutant=='always_live':source=source.replace("input_metadata_select === 1'b1 ? branch_matches[1]", "input_metadata_select === 1'b1 ? branch_matches[0]",1)
    elif mutant=='skip_top_bit':source=source.replace('assign branch_matches[branch] = &group_equal;', 'assign branch_matches[branch] = &leaf_equal[LEAF_COUNT-2:0];',1)
    elif mutant=='unknown_merge':source=source.replace('(input_metadata == metadata_in_hold);','(input_metadata_select ? branch_matches[1] : branch_matches[0]);',1)
    bench=r'''`timescale 1ns/1ps
module tb;
reg clk=0,resetn=0,valid=0,last=0,authorize=0,consume=0,select_replay=0,force_comparison=0;
reg [35:0] data=0;
reg [1:0] position=0;
reg [36:0] live_metadata=37'h123456789,replay_metadata=37'h123456789;
wire [36:0] selected_metadata=select_replay ? replay_metadata : live_metadata;
wire a_ready,a_fault,a_framing,a_valid,a_last,a_request,a_ack,a_writer_idle,a_reader_idle;
wire b_ready,b_fault,b_framing,b_valid,b_last,b_request,b_ack,b_writer_idle,b_reader_idle;
wire [35:0] a_data,b_data;wire [1:0] a_position,b_position;wire [36:0] a_metadata,b_metadata;
__INSTANCES__
integer checks=0,reads=0,bad_cases=0,n,bitno,kind,side,where;
task compare;begin
 if({a_ready,a_fault,a_framing,a_valid,a_last,a_request,a_ack,a_writer_idle,a_reader_idle} !==
    {b_ready,b_fault,b_framing,b_valid,b_last,b_request,b_ack,b_writer_idle,b_reader_idle})
   $fatal(1,"public mailbox mismatch at %0d",checks);
 if((original.write_position!=0 || force_comparison) &&
    original.metadata_matches!==candidate.metadata_matches)$fatal(1,"current equality mismatch at %0d",checks);
 if(a_valid && {a_data,a_position,a_metadata}!=={b_data,b_position,b_metadata})$fatal(1,"reader payload mismatch");
 checks=checks+1;
end endtask
task tick;begin #1;compare;clk=1;#1;compare;clk=0;#1;end endtask
task restart;begin
 resetn=0;valid=0;consume=0;authorize=0;select_replay=0;
 live_metadata=37'h123456789;replay_metadata=37'h123456789;tick;tick;resetn=1;tick;
end endtask
task word(input integer p);begin valid=1;position=p;last=(p==3);data=p+100;tick;end endtask
task healthy;begin
 restart;for(n=0;n<4;n=n+1)word(n);
 // Unpublished LAST is held and rewritten, then replay chooses the same
 // descriptor and receives actual authorization. Reader must see all words.
 select_replay=1;repeat(4)tick;authorize=1;tick;valid=0;authorize=0;
 repeat(4)tick;consume=1;reads=0;
 repeat(12)begin if(a_valid)begin if(a_data!==a_position+100)$fatal(1,"wrong stored word");reads=reads+1;end tick;end
 if(reads!=4 || !a_ready || a_fault)$fatal(1,"healthy ownership did not recover");
end endtask
initial begin
 restart;healthy;
 // Each of 37 bits, both source branches, nonfinal and final positions,
 // known inversion/X/Z: no corrupted selected descriptor may publish.
 for(side=0;side<2;side=side+1)for(where=1;where<4;where=where+2)
 for(bitno=0;bitno<37;bitno=bitno+1)for(kind=0;kind<3;kind=kind+1)begin
  restart;for(n=0;n<where;n=n+1)word(n);
  select_replay=side;
  if(side==0)case(kind)0:live_metadata[bitno]=~live_metadata[bitno];1:live_metadata[bitno]=1'bx;2:live_metadata[bitno]=1'bz;endcase
  else case(kind)0:replay_metadata[bitno]=~replay_metadata[bitno];1:replay_metadata[bitno]=1'bx;2:replay_metadata[bitno]=1'bz;endcase
  authorize=1;word(where);valid=0;repeat(4)tick;
  if(a_request!==0 || b_request!==0)$fatal(1,"corruption published");bad_cases=bad_cases+1;
 end
 // Nonselected corruption cannot corrupt the currently selected transfer;
 // switching to it must restore the exact original failure predicate.
 restart;word(0);replay_metadata=0;word(1);select_replay=1;word(2);
 // Four-state selector is NOT distributive through equality. In particular
 // live=0/replay=3/held=1 produces X, not the merged equality result 0.
 restart;force_comparison=1;force original.metadata_in_hold=37'd1;force candidate.metadata_in_hold=37'd1;
 for(side=0;side<2;side=side+1)begin
  select_replay=side==0 ? 1'bx : 1'bz;
  live_metadata=0;replay_metadata=3;#1;compare;
  live_metadata=1;replay_metadata=1;#1;compare;
  live_metadata=1;replay_metadata=3;#1;compare;
 end
 release original.metadata_in_hold;release candidate.metadata_in_hold;force_comparison=0;
 healthy;
 // Reset cancels an unpublished final and returns both original ownership
 // views; new selected-first metadata is retained identically.
 restart;select_replay=1;live_metadata=0;for(n=0;n<4;n=n+1)word(n);restart;healthy;
 if(bad_cases!=444 || checks<5000)$fatal(1,"short split metadata campaign");
 $display("SPLIT_METADATA_MAILBOX_PASS checks=%0d corruptions=%0d exact_current=1 four_state=1 ownership=1 fresh_recovery=1",checks,bad_cases);$finish;
end
endmodule
'''
    instances=[]
    for prefix,module,name,metadata in [('a','starlink_pss_mailbox_owner_view','original','.input_metadata(selected_metadata)'),
                                       ('b','starlink_pss_mailbox_split_metadata_view','candidate','.input_metadata_live(live_metadata),.input_metadata_replay(replay_metadata),.input_metadata_select(select_replay)')]:
        instances.append(f'''{module} #(.ADDRESS_WIDTH(2),.METADATA_WIDTH(37),.RESET_RELEASE_EXTERNAL(1),.EXPLICIT_COMMIT(1)) {name} (
 .input_clk(clk),.input_resetn(resetn),.input_valid(valid),.input_commit_authorized(authorize && !{prefix}_framing),.input_ready({prefix}_ready),
 .input_data(data),.input_position(position),.input_last(last),{metadata},.input_fault({prefix}_fault),.input_framing_fault_now({prefix}_framing),
 .output_clk(clk),.output_resetn(resetn),.output_valid({prefix}_valid),.output_ready(consume),.output_data({prefix}_data),
 .output_position({prefix}_position),.output_last({prefix}_last),.output_metadata({prefix}_metadata),.owner_request({prefix}_request),
 .owner_ack_sync({prefix}_ack),.writer_reset_idle({prefix}_writer_idle),.reader_reset_idle({prefix}_reader_idle));''')
    bench=bench.replace('__INSTANCES__','\n'.join(instances))
    files=[]
    for name,text in [('old.v',OLD.read_text()),('new.v',source),('tb.sv',bench)]:
        path=tmp_path/name;path.write_text(text);files.append(str(path))
    result=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),*files],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result


def test_actual_mailbox_equivalence_corruption_and_recovery(tmp_path):
    result=run(tmp_path)
    assert result.returncode==0 and 'SPLIT_METADATA_MAILBOX_PASS' in result.stdout,result.stdout+result.stderr


@pytest.mark.parametrize('mutant',['ignore_replay','always_live','skip_top_bit','unknown_merge'])
def test_unsafe_comparator_mutations_rejected(tmp_path,mutant):
    result=run(tmp_path,mutant)
    assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout+result.stderr

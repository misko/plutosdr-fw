"""One-entry private completion receipt retains real publication/ACK authority."""
from pathlib import Path
import re
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
PARENT=Path('/dev/shm/starlink-balanced-handoff.5K7fHIYq/prepared-v2')
NAME='starlink_pss_completion_mailbox_stage'


def undo_adapter_top(text):
    if 'PRIVATE_FACT_CAPTURE(1)' in text:
        from tests.test_starlink_private_admission_facts import undo_top
        text=undo_top(text)
    assert text.count(NAME)==1
    return text.replace(NAME,'starlink_pss_staged_mailbox_control',1)


def undo_completion_bench(text):
    if '// BEGIN PRIVATE ADMISSION FACTS WITNESS' in text:
        from tests.test_starlink_private_admission_facts import undo_bench
        text=undo_bench(text)
    for before,after in [
      ('final_open=!dut.output_publication_busy;','final_open=dut.output_control.phase==0;'),
      ('if(dut.output_publication_busy &&\n           {dut.output_control.active_tag',
       'if(dut.output_control.phase!=0 &&\n           {dut.output_control.active_tag'),
      ('if(final_accept && !dut.output_publication_busy)', 'if(final_accept && dut.output_control.phase==0)')]:
        assert text.count(before)==1
        text=text.replace(before,after,1)
    for label in ['WITNESS','BOUNDARIES','AUXILIARY']:
        text,count=re.subn(r' *// BEGIN COMPLETION MAILBOX '+label+r'\n.*? *// END COMPLETION MAILBOX '+label+r'\n','',text,flags=re.S)
        assert count==1
    for spaces,mode in [(6,'AUXILIARY'),(4,'MAIN')]:
        line=' '*spaces+'report_completion_slot; // COMPLETION MAILBOX '+mode+'\n'
        assert text.count(line)==1;text=text.replace(line,'',1)
    return text


def test_exact_bench_delta_preserves_existing_cases():
    name='tb_fft_staged_output.sv'
    assert undo_completion_bench((RTL/name).read_text())==(PARENT/name).read_text()


def test_exact_adapter_delta_and_other_runtime_preserved():
    old=(PARENT/'starlink_pss_staged_mailbox_control.v').read_text()
    expected=old.replace('module starlink_pss_staged_mailbox_control','module '+NAME)
    pairs=[
      ('  reg publication_seen, published_pending;','  reg publication_seen, published_pending;\n  // One-entry receipt: reserves/fixes payload immediately, sequences next edge.\n  reg complete_pending;'),
      ('assign allocate_ready = live && command_state==C_IDLE && allocation_room &&','assign allocate_ready = live && !complete_pending && command_state==C_IDLE && allocation_room &&'),
      ('assign complete_ready = live && phase==P_EMPTY &&','assign complete_ready = live && phase==P_EMPTY && !complete_pending &&'),
      ('assign publication_busy = phase!=P_EMPTY;','assign publication_busy = phase!=P_EMPTY || complete_pending;'),
      ('PRIVATE_FINAL_CAPTURE ? phase==P_EMPTY :','PRIVATE_FINAL_CAPTURE ? (phase==P_EMPTY && !complete_pending) :'),
      ('publication_seen<=0;published_pending<=0;','publication_seen<=0;published_pending<=0;complete_pending<=0;'),
      ('        phase<=P_COMMIT;publication_seen<=0;','        complete_pending<=1;publication_seen<=0;'),
      ('      if (phase==P_REPLAY && replay_ready) phase<=P_ACK;',
       '      // Fault holds this private receipt occupied; reset alone purges it.\n'
       '      // No publication/release is authorized merely by consuming the receipt.\n'
       '      if (complete_pending) begin phase<=P_COMMIT;complete_pending<=0;end\n'
       '      if (phase==P_REPLAY && replay_ready) phase<=P_ACK;')]
    for before,after in pairs:
        assert expected.count(before)==1
        expected=expected.replace(before,after,1)
    assert expected==(RTL/(NAME+'.v')).read_text()
    top='starlink_pss_fft_staged_output_impl.v'
    assert undo_adapter_top((RTL/top).read_text())==(PARENT/top).read_text()
    names=(PARENT/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    assert len(names)==22
    for name in names:
        if name!=top and (RTL/name).exists():
            from tests.test_starlink_private_admission_facts import parent_runtime_bytes
            assert parent_runtime_bytes(RTL/name)==(PARENT/name).read_bytes(),name


def run(tmp_path,cancel=0,stall=37,private=1,mutant=None):
    source=(RTL/(NAME+'.v')).read_text()
    mutations={
      'ignore_pending_busy':('phase!=P_EMPTY || complete_pending','phase!=P_EMPTY'),
      'reopen_payload':('(phase==P_EMPTY && !complete_pending)','phase==P_EMPTY'),
      'early_room':('phase==P_EMPTY && !complete_pending &&','phase==P_EMPTY &&'),
      'skip_receipt':('if (complete_pending) begin phase<=P_COMMIT;complete_pending<=0;end','if (1\'b0) begin phase<=P_COMMIT;complete_pending<=0;end')}
    if mutant:
        before,after=mutations[mutant];assert source.count(before)==1;source=source.replace(before,after,1)
    bench=(RTL/'tb_staged_mailbox_control.sv').read_text()
    bench=bench.replace('starlink_pss_staged_mailbox_control dut(.*);',f'{NAME} #(.PRIVATE_FINAL_CAPTURE({private})) dut(.*);')
    bench=bench.replace('    complete_block(0);\n    if(CANCEL_CASE!=0)',
      '''    complete_block(0);
    if(dut.complete_pending!==1 || !publication_busy || complete_ready || allocate_ready)
      $fatal(1,"pending receipt did not reserve private ownership");
    complete_tag=32'hdeadbeef;complete_final_data=36'hf12345678;
    if(CANCEL_CASE!=0)''',1)
    bench=bench.replace('else if(CANCEL_CASE>=3) await_replay;','else if(CANCEL_CASE>=3 && CANCEL_CASE!=5) await_replay;',1)
    bench=bench.replace('      abort_epoch=1;#0.1;','      if(CANCEL_CASE==5) resetn=0;else abort_epoch=1;#0.1;',1)
    bench=bench.replace('if(!fault || replay_valid || allocated_valid','if((resetn && !fault) || replay_valid || allocated_valid',1)
    witness='''
  reg receipt_held=0;reg [31:0] receipt_tag;reg [35:0] receipt_data;
  integer receipt_checks=0;
  always @(posedge clk)begin
    if(!resetn)receipt_held=0;
    else begin
      if(complete_valid && complete_ready)begin
        receipt_held=1;receipt_tag=complete_tag;receipt_data=complete_final_data;
      end
      #0.001;
      if(receipt_held && publication_busy)begin
        if(dut.active_tag!==receipt_tag || dut.final_data!==receipt_data)
          $fatal(1,"pending or owned receipt payload changed");
        receipt_checks=receipt_checks+1;
      end
      if(!publication_busy)receipt_held=0;
    end
  end
'''
    bench=bench.replace('  initial begin #1000000;',witness+'  initial begin #1000000;',1)
    files=[]
    for name,text in [('adapter.v',source),('tb.sv',bench)]:
        path=tmp_path/name;path.write_text(text);files.append(str(path))
    files.append(str(RTL/'starlink_pss_descriptor_commands.v'))
    # The original concrete test bank remains the reference; it is not the
    # product-identity variant, which has a different input contract.
    files.append('/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-summary-actual-prelaunch-v1/source_snapshot/hdl/library/starlink_pss_acquisition/retained_output/starlink_pss_mailbox_owner_view.v')
    result=subprocess.run(['iverilog','-g2012','-s','tb',f'-Ptb.CANCEL_CASE={cancel}',f'-Ptb.STALL_CYCLES={stall}','-o',str(tmp_path/'sim'),*files],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr);assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result


@pytest.mark.parametrize('cancel',range(6))
@pytest.mark.parametrize('stall',[1,37])
@pytest.mark.parametrize('private',[0,1])
def test_real_bank_pending_completion_cancellation_recovery(tmp_path,cancel,stall,private):
    result=run(tmp_path,cancel,stall,private)
    assert result.returncode==0,result.stdout+result.stderr
    assert f'STAGED_ADAPTER_PASS cancel={cancel}' in result.stdout


@pytest.mark.parametrize('mutant',['ignore_pending_busy','reopen_payload','early_room','skip_receipt'])
def test_unsafe_receipt_mutants_rejected(tmp_path,mutant):
    result=run(tmp_path,mutant=mutant)
    assert result.returncode!=0 and 'FATAL' in result.stdout and 'watchdog' not in result.stdout,result.stdout

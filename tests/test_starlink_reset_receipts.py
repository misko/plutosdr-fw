"""Reset-receipt delta and real mailbox/barrier recovery, without CDC waivers."""
import hashlib
from pathlib import Path
import re

import pytest
from tests import test_starlink_output_metadata_cdc as contract

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
PARENT=Path('/dev/shm/starlink-output-metadata.MB5fY8/prepared-v3')
PAIRS={
 'starlink_pss_mailbox_reset_receipt':'starlink_pss_mailbox_owner_view',
 'starlink_pss_output_reset_receipt':'starlink_pss_mailbox_split_metadata_view',
 'starlink_pss_reset_receipt_barrier':'starlink_pss_retained_epoch_barrier',
}


def undo_top(text):
    for new,old in PAIRS.items():
        assert text.count(new)==1
        text=text.replace(new,old,1)
    return text


def undo_mailbox(text):
    text=re.sub(r'  // Reset receipts only.*?  // BEGIN RETAINED MAILBOX OBSERVATIONS: local reset qualification\.',
      '  // BEGIN RETAINED MAILBOX OBSERVATIONS: no state or control changes.',text,flags=re.S)
    text=text.replace("!in_running && writer_reset_applied === 1'b1 &&\n    request_toggle === 1'b0 && acknowledge_sync[1] === 1'b0 &&",
                      "request_toggle === 1'b0 && acknowledge_sync === 2'b0 &&")
    text=text.replace("!out_running && reader_reset_applied === 1'b1 &&\n    acknowledge_toggle === 1'b0 && request_sync[1] === 1'b0 &&",
                      "acknowledge_toggle === 1'b0 && request_sync === 2'b0 &&")
    return text


def test_exact_runtime_delta():
    assert hashlib.sha256((PARENT/'SHA256SUMS').read_bytes()).hexdigest()==contract.PIN
    for new,old in list(PAIRS.items())[:2]:
        text=(RTL/(new+'.v')).read_text()
        assert undo_mailbox(text.replace('module '+new,'module '+old,1))==(PARENT/(old+'.v')).read_text()
        # Each first tap appears only in the next-stage shift assignment.
        for name in ['request_sync','acknowledge_sync']:
            assert text.count(name+'[0]')==1
    top='starlink_pss_fft_staged_output_impl.v'
    assert undo_top((RTL/top).read_text())==(PARENT/top).read_text()
    for name in (PARENT/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split():
        if name!=top and (RTL/name).exists():
            assert (RTL/name).read_bytes()==(PARENT/name).read_bytes(),name


def test_exact_barrier_delta():
    old=(PARENT/'starlink_pss_retained_epoch_barrier.v').read_text()
    expected=old.replace('module starlink_pss_retained_epoch_barrier','module starlink_pss_reset_receipt_barrier')
    expected=expected.replace('// Nine state bits.','// Ten state bits: the slow-purge source is now registered.')
    expected=expected.replace('wire slow_purged = slow_purge_count == 2;','reg slow_purged;')
    expected=expected.replace('begin slow_purge_count <= 0; fast_release_slow <= 0; end',
                              'begin slow_purge_count <= 0; slow_purged <= 0; fast_release_slow <= 0; end')
    expected=expected.replace('if (!outer_slow_running) slow_purge_count <= 0;',
                              'if (!outer_slow_running) begin slow_purge_count <= 0; slow_purged <= 0; end')
    expected=expected.replace('else if (!slow_purged && slow_mailboxes_reset_idle',
                              'else if (slow_purge_count != 2 && slow_mailboxes_reset_idle')
    expected=expected.replace('slow_purge_count <= slow_purge_count + 1\'b1;',
      "slow_purge_count <= slow_purge_count + 1'b1;\n"
      '      // A registered monotonic receipt crosses clocks, never the counter decode.\n'
      "      if (outer_slow_running && slow_purge_count == 2) slow_purged <= 1;")
    assert expected==(RTL/'starlink_pss_reset_receipt_barrier.v').read_text()


def configure(tmp_path,monkeypatch):
    text=contract.BENCH.read_text()
    text=text.replace('starlink_pss_retained_epoch_barrier','starlink_pss_reset_receipt_barrier')
    text=text.replace('starlink_pss_mailbox_split_metadata_view','starlink_pss_output_reset_receipt')
    before='  fast_enable=1;slow_enable=1;\n  repeat(8)@(negedge fast_clk);'
    after='''  // Release raw reset BEFORE restarting a stopped clock. No epoch may
  // escape while that domain still retains its old synchronous state.
  if(!fast_enable || !slow_enable)begin
   resetn=1;fft_resetn=1;
   repeat(8)begin #10001;
    if(fast_running || slow_running || valid || ready)
     $fatal(1,"epoch released while a clock remained stopped");
   end
  end
  fast_enable=1;slow_enable=1;
  repeat(8)@(negedge fast_clk);'''
    assert text.count(before)==1
    text=text.replace(before,after,1)
    bench=tmp_path/'receipt_tb.sv';bench.write_text(text)
    monkeypatch.setattr(contract,'RTL',RTL/'starlink_pss_output_reset_receipt.v')
    monkeypatch.setattr(contract,'BARRIER',RTL/'starlink_pss_reset_receipt_barrier.v')
    monkeypatch.setattr(contract,'BENCH',bench)


@pytest.mark.parametrize('writer,reader',[(2857,5000),(2500,5000),(5000,2857)])
@pytest.mark.parametrize('phase',[0,1,1234,4999])
def test_reset_release_with_stopped_clock(tmp_path,monkeypatch,writer,reader,phase):
    configure(tmp_path,monkeypatch)
    result=contract.run(tmp_path,writer,reader,phase)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'completed=13 resets=10' in result.stdout
    assert 'OUTPUT_CDC_CONTRACT_PASS' in result.stdout


@pytest.mark.parametrize('mutant',['short_request_sync','early_ack','offered_metadata_write','capture_live_bus'])
def test_unsafe_data_mutants_still_rejected(tmp_path,monkeypatch,mutant):
    configure(tmp_path,monkeypatch)
    result=contract.run(tmp_path,phase=1234,mutant=mutant)
    assert result.returncode!=0
    assert 'FATAL' in result.stdout and 'absolute deadline' not in result.stdout

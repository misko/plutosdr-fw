"""Bounded digital CDC contract tests; not analog metastability or board signoff."""
import hashlib
from pathlib import Path
import re
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
PREPARED=Path('/dev/shm/starlink-output-metadata.MB5fY8/prepared-v3')
PIN='dc97c80ce1999e9a18053524c3dcd325d029705560c2425aef2e0fe05f20d1b7'
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control/starlink_pss_mailbox_split_metadata_view.v'
BARRIER=PREPARED/'starlink_pss_retained_epoch_barrier.v'
BENCH=ROOT/'tests/fixtures/tb_output_metadata_cdc.sv'


def test_runtime_and_reset_contract_source_identity():
    assert hashlib.sha256((PREPARED/'SHA256SUMS').read_bytes()).hexdigest()==PIN
    pins=dict((name,digest) for digest,name in (line.split() for line in (PREPARED/'SHA256SUMS').read_text().splitlines()))
    assert hashlib.sha256(RTL.read_bytes()).hexdigest()==pins[RTL.name]
    assert hashlib.sha256(BARRIER.read_bytes()).hexdigest()==pins[BARRIER.name]
    top=(PREPARED/'starlink_pss_fft_staged_output_impl.v').read_text()
    assert '.input_clk(fft_clk), .input_resetn(fast_running)' in top
    assert '.output_clk(clk), .output_resetn(slow_running)' in top
    assert '.slow_clk(clk), .fast_clk(fft_clk), .resetn(resetn), .fft_resetn(fft_resetn)' in top
    # The isolated bench gives the real barrier the real output mailbox's idle
    # observations; other full-receiver mailbox/descriptor gates are out of scope.
    assert '.slow_mailboxes_reset_idle(reader_idle),.fast_mailboxes_reset_idle(writer_idle)' in BENCH.read_text()
    # Preserve the four real raw-reset synchronizers, modulo local clock names
    # and insignificant formatting. This test does not replace the real barrier.
    start=top.index('  always @(posedge fft_clk or negedge resetn)')
    end=top.index('  wire outer_fast_running',start)
    expected=top[start:end].replace('fft_clk','fast_clk').replace('posedge clk','posedge slow_clk')
    normalize=lambda text:re.sub(r'\s+','',text)
    assert normalize(expected) in normalize(BENCH.read_text())


def run(tmp_path,writer=2857,reader=5000,phase=0,mutant=None):
    source=RTL.read_text()
    if mutant=='short_request_sync':source=source.replace('!reading && request_sync[1] != acknowledge_toggle',
                                                        '!reading && request_sync[0] != acknowledge_toggle',1)
    elif mutant=='early_ack':source=source.replace('if (output_accept && output_last) begin','if (output_accept) begin',1)
    elif mutant=='offered_metadata_write':source=source.replace('if (metadata_load)\n      metadata_in_hold <= input_metadata;',
                                                               'if (input_valid)\n      metadata_in_hold <= input_metadata;',1)
    elif mutant=='capture_live_bus':source=source.replace('metadata_out_hold <= metadata_in_hold;','metadata_out_hold <= input_metadata;',1)
    files=[]
    for name,text in [('mailbox.v',source),('barrier.v',BARRIER.read_text()),('tb.sv',BENCH.read_text())]:
        path=tmp_path/name;path.write_text(text);files.append(str(path))
    command=['iverilog','-g2012','-s','tb',f'-Ptb.WRITER_HALF={writer}',f'-Ptb.READER_HALF={reader}',
             f'-Ptb.READER_PHASE={phase}','-o',str(tmp_path/'sim'),*files]
    result=subprocess.run(command,capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'simulate.log').write_text(result.stdout+result.stderr)
    return result


@pytest.mark.parametrize('writer,reader',[(2857,5000),(2500,5000),(5000,2857)])
@pytest.mark.parametrize('phase',[0,1,1234,4999])
def test_actual_bundle_across_clock_phases_stalls_and_resets(tmp_path,writer,reader,phase):
    result=run(tmp_path,writer,reader,phase)
    assert result.returncode==0,result.stdout+result.stderr
    matches=re.findall(r'^OUTPUT_CDC_CONTRACT_PASS (.*)$',result.stdout,re.M)
    assert len(matches)==1
    fields=dict((key,int(value)) for key,value in (part.split('=') for part in matches[0].split()))
    assert fields['completed']==13 and fields['resets']==10 and fields['reset_checks']==80
    assert fields['min_publish_capture_ps']>=4*reader-2
    assert fields['min_first_capture_ps']>=1022*writer+4*reader-2
    assert fields['min_ack_rewrite_ps']>=4*writer-2


@pytest.mark.parametrize('mutant',['short_request_sync','early_ack','offered_metadata_write','capture_live_bus'])
def test_unsafe_cdc_mutants_rejected(tmp_path,mutant):
    result=run(tmp_path,phase=1234,mutant=mutant)
    assert result.returncode!=0 and 'FATAL' in result.stdout,result.stdout+result.stderr
    assert 'absolute deadline' not in result.stdout,result.stdout

"""Exact additive interfaces, original-ROM behavior and parallel ready contract."""
from pathlib import Path
import re
from unittest.mock import patch
import pytest
from tests import test_starlink_private_kernel_payload as kernel

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
PARENT=Path('/dev/shm/starlink-forward-capacity.tHq0mgHO/prepared-v2')
TOP='starlink_pss_fft_staged_output_impl.v'
CHANGED={TOP,'starlink_pss_kernel_rom.v','starlink_pss_forward_kernel_join.v',
 'starlink_pss_spectrum_product_bank_arithmetic.v','starlink_pss_spectrum_product_operand_register.v'}

def replace(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new,1)

def block(text,label,replacement=''):
    text,n=re.subn(r'  // BEGIN '+label+r'\n.*?  // END '+label+r'\n',lambda _:replacement,text,flags=re.S)
    assert n==1,label
    return text

def undo_runtime(text,name):
    if name=='starlink_pss_result_guard_owner_view.v':
        from tests.test_starlink_forward_final_commit import undo_guard
        text=undo_guard(text)
    if name not in CHANGED:return text
    if name==TOP:
        if '// BEGIN PARALLEL KERNEL CAPACITY' not in text:return text
        text=block(text,'PARALLEL KERNEL CAPACITY')
        text=replace(text,'  parameter integer MONOTONIC_OUTER_RESET = 0,\n  parameter integer PARALLEL_KERNEL_READY = 0','  parameter integer MONOTONIC_OUTER_RESET = 0')
        text=replace(text,'.BALANCED_BLOCK_IDENTITY_EQ(REGISTERED_SCHEDULING),\n    .PARALLEL_INPUT_CAPACITY(PARALLEL_KERNEL_READY)) joiner (','.BALANCED_BLOCK_IDENTITY_EQ(REGISTERED_SCHEDULING)) joiner (')
        text=replace(text,'.idle(product_identity_idle), .fault(product_stage_fault)','.idle(), .fault(product_stage_fault)')
    elif name in {'starlink_pss_kernel_rom.v','starlink_pss_forward_kernel_join.v'}:
        if 'parameter integer PARALLEL_INPUT_CAPACITY' not in text:return text
        text=replace(text,'  parameter integer BALANCED_BLOCK_IDENTITY_EQ = 0,\n  parameter integer PARALLEL_INPUT_CAPACITY = 0','  parameter integer BALANCED_BLOCK_IDENTITY_EQ = 0')
        if name=='starlink_pss_kernel_rom.v':
            text=block(text,'PARALLEL KERNEL READY','  assign input_ready = resetn && !flush && !protocol_fault &&\n                       output_stage_ready;\n')
        else:
            text=replace(text,'.BALANCED_BLOCK_IDENTITY_EQ(BALANCED_BLOCK_IDENTITY_EQ),\n    .PARALLEL_INPUT_CAPACITY(PARALLEL_INPUT_CAPACITY)','.BALANCED_BLOCK_IDENTITY_EQ(BALANCED_BLOCK_IDENTITY_EQ)')
    elif name=='starlink_pss_spectrum_product_bank_arithmetic.v':
        if '// BEGIN PARALLEL READY ARITHMETIC OBSERVATION' not in text:return text
        text=block(text,'PARALLEL READY ARITHMETIC OBSERVATION')
    text=re.sub(r'^.*// PARALLEL READY (?:INPUT|OCCUPANCY)\n','',text,flags=re.M)
    return text

def undo_bench(text):
    from tests.test_starlink_forward_final_commit import undo_bench as undo_final
    text=undo_final(text)
    text=block(text,'PARALLEL READY WITNESS')
    for line in ['      report_parallel_ready; // PARALLEL READY REPORT\n',',.PARALLEL_KERNEL_READY(1)']:
        text=replace(text,line,'')
    text=replace(text,'unexplained=%0d runtime_unchanged=0','unexplained=%0d runtime_unchanged=1')
    return text

def test_exact_runtime_and_profile_delta():
    names=(PARENT/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    assert len(names)==22
    changes=[]
    for name in names:
        if (RTL/name).exists():
            text=(RTL/name).read_text()
            if name=='starlink_pss_result_guard_owner_view.v':
                from tests.test_starlink_forward_final_commit import undo_guard
                text=undo_guard(text)
            if text!=(PARENT/name).read_text():changes.append(name)
            assert undo_runtime(text,name)==(PARENT/name).read_text(),name
    assert set(changes)==CHANGED
    assert undo_bench((RTL/'tb_fft_staged_output.sv').read_text())==(PARENT/'tb_fft_staged_output.sv').read_text()
    assert (ROOT/'tools/staged_fft_experiment.tcl').read_text().replace(' PARALLEL_KERNEL_READY=1','',1)==(PARENT/'staged_fft_experiment.tcl').read_text()

def enabled_bench(mode=1,wrong_hint=False):
    text=kernel.bench()
    # Keep the original golden ROM untouched. Both candidate configurations
    # get the same current output capacity; no pipeline/control is bypassed.
    for n in [1,2]:
        start=text.index('starlink_pss_kernel_rom #',text.index(') d0(')) if n==1 else text.index('starlink_pss_kernel_rom #',text.index(') d1('))
        end=text.index(';',start)+1
        instance=text[start:end]
        changed=instance.replace(f') d{n}(',f',.PARALLEL_INPUT_CAPACITY({mode})) d{n}(',1)
        changed=changed.replace('.output_ready(oready)',".output_ready(oready),.downstream_capacity("+("1'b1" if wrong_hint else 'oready')+')',1)
        text=text[:start]+changed+text[end:]
    return text

@pytest.mark.parametrize('mode',[0,1])
def test_original_rom_public_contract(tmp_path,mode):
    bench=enabled_bench(mode)
    with patch.object(kernel,'bench',return_value=bench):result=kernel.execute(tmp_path,(RTL/'starlink_pss_kernel_rom.v').read_text())
    assert result.returncode==0 and 'healthy=4096 malformed=4 flush=1' in result.stdout,result.stdout+result.stderr

def test_false_capacity_rejected(tmp_path):
    bench=enabled_bench(wrong_hint=True)
    with patch.object(kernel,'bench',return_value=bench):result=kernel.execute(tmp_path,(RTL/'starlink_pss_kernel_rom.v').read_text())
    assert result.returncode!=0 and 'public control differs' in result.stdout,result.stdout+result.stderr

@pytest.mark.parametrize('mode',['2',"32'bx","32'bz"])
def test_unknown_mode_rejected(tmp_path,mode):
    bench=enabled_bench(mode)
    with patch.object(kernel,'bench',return_value=bench):result=kernel.execute(tmp_path,(RTL/'starlink_pss_kernel_rom.v').read_text())
    assert result.returncode!=0 and 'parallel input capacity requires a known mode' in result.stdout,result.stdout+result.stderr

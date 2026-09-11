"""Only two KEEP attributes may change; no logic/clock/profile modification."""
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control'
PARENT=Path('/dev/shm/starlink-parallel-ready.uE2Iyp1W/prepared-v1')
TARGETS={'starlink_pss_fft_staged_output_impl.v':'forward_parallel_capacity',
         'starlink_pss_kernel_rom.v':'parallel_input_room'}

def current_runtime():
    names=(PARENT/'profile.tcl').read_text().split('set runtime_names {')[1].split('}')[0].split()
    assert len(names)==22
    return {name:(RTL/name).read_text() if (RTL/name).exists() else (PARENT/name).read_text() for name in names}

def verify_runtime(sources):
    changed=[]
    for name,text in sources.items():
        if name=='starlink_pss_fft_staged_output_impl.v':
            from tests.test_starlink_distributed_sticky_fault import undo_top
            text=undo_top(text)
        if name=='starlink_pss_result_guard_owner_view.v':
            from tests.test_starlink_forward_final_commit import undo_guard
            text=undo_guard(text)
        original=(PARENT/name).read_text()
        if text!=original:changed.append(name)
        if name in TARGETS:
            plain='  wire '+TARGETS[name]+' ='
            kept='  (* keep = "true" *) wire '+TARGETS[name]+' ='
            assert text.count(plain)==1 and kept not in text
            text=text.replace(plain,kept,1)
        assert text==original,name
    assert set(changed)==set(TARGETS)

def test_exact_two_attribute_delta():
    verify_runtime(current_runtime())
    for name,path in [('tb_fft_staged_output.sv',RTL/'tb_fft_staged_output.sv'),
                      ('staged_fft_experiment.tcl',ROOT/'tools/staged_fft_experiment.tcl'),
                      ('staged_fft_experiment.py',ROOT/'tools/staged_fft_experiment.py')]:
        text=path.read_text()
        if name=='tb_fft_staged_output.sv':
            from tests.test_starlink_forward_final_commit import undo_bench
            text=undo_bench(text)
        assert text==(PARENT/name).read_text(),name

@pytest.mark.parametrize('mutation',['fault_gate','capacity_logic','extra_state'])
def test_behavioral_changes_rejected(mutation):
    sources=current_runtime()
    if mutation=='fault_gate':
        name='starlink_pss_kernel_rom.v';sources[name]=sources[name].replace('resetn && !flush && !protocol_fault &&','resetn && !flush &&',1)
    elif mutation=='capacity_logic':
        name='starlink_pss_fft_staged_output_impl.v';sources[name]=sources[name].replace('wire forward_parallel_capacity = !product_pipeline_full ||','wire forward_parallel_capacity = product_pipeline_full ||',1)
    else:
        name='starlink_pss_kernel_rom.v';sources[name]=sources[name].replace('  wire output_stage_ready;','  reg extra_state;\n  wire output_stage_ready;',1)
    with pytest.raises(AssertionError):verify_runtime(sources)

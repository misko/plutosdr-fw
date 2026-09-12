"""Source-derived four-state equivalence, including gates and every metadata bit."""
from pathlib import Path
import re
import sys
import pytest
from tests.test_starlink_balanced_forward_identity import compile_run

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import product_publication_cone_transform as transform
import product_publication_cone_experiment as experiment
RTL = ROOT / 'hdl/library/starlink_pss_acquisition/staged_control'
PARENT = 'starlink_pss_fft_output_retirement_receipt_impl'
NEW = 'starlink_pss_fft_product_publication_cone_impl'


def test_exact_delta():
    a = (RTL / (PARENT + '.v')).read_text()
    b = (RTL / (NEW + '.v')).read_text()
    assert transform.transform(a) == b
    assert transform.undo(b) == a


def fragment():
    source = (RTL / (NEW + '.v')).read_text()
    start = source.index('  wire handoff_fault_enabled =')
    end = source.index('  wire external_fault_now =', start)
    return source[start:end]


@pytest.mark.parametrize('mutation', ['none', 'omit_tail', 'wrong_slice', 'omit_enable', 'omit_position', 'omit_last'])
def test_four_state_factoring(tmp_path, mutation):
    candidate = fragment()
    changes = {
        'omit_tail': ('(|handoff_identity_fault)', '(|handoff_identity_fault[3:0])'),
        'wrong_slice': ('5*fault_group +: LEAVES', '4*fault_group +: LEAVES'),
        'omit_enable': ('handoff_fault_enabled &&\n', "1'b1 &&\n"),
        'omit_position': ('product_bank_position != 0', "1'b0"),
        'omit_last': ('|| product_bank_last', "|| 1'b0"),
    }
    if mutation != 'none':
        before, after = changes[mutation]
        assert candidate.count(before) == 1
        candidate = candidate.replace(before, after)
    bench = '''`timescale 1ns/1ps
module tb;
reg [23:0] handoff_leaf_equal;
reg next_inverse,forward_committed,product_bank_valid,product_bank_last;
reg [8:0] product_bank_position;
wire forward_handoff_identity = &handoff_leaf_equal;
integer n,j,k,checks=0;
function automatic four(input integer digit);
  case(digit)0:four=0;1:four=1;2:four=1'bx;3:four=1'bz;endcase
endfunction
''' + candidate + '''
wire reference_fault = !next_inverse && forward_committed && product_bank_valid &&
  (!forward_handoff_identity || product_bank_position != 0 || product_bank_last);
initial begin
  for(n=0;n<1048576;n=n+1)begin
    k=n;handoff_leaf_equal='1;
    for(j=0;j<5;j=j+1)begin handoff_leaf_equal[5*j]=four(k%4);k=k/4;end
    next_inverse=four(k%4);k=k/4;
    forward_committed=four(k%4);k=k/4;
    product_bank_valid=four(k%4);k=k/4;
    product_bank_position=0;product_bank_position[0]=four(k%4);k=k/4;
    product_bank_last=four(k%4);
    #1;
    if(handoff_fault_now!==reference_fault)$fatal(1,"four-state fault mismatch vector=%0d",n);
    checks=checks+1;
  end
  $display("PUBLICATION_FACTOR_PASS checks=%0d",checks);$finish;
end
endmodule
'''
    result = compile_run(tmp_path, bench)
    if mutation == 'none':
        assert result.returncode == 0 and 'PUBLICATION_FACTOR_PASS checks=1048576' in result.stdout, result.stdout
    else:
        assert result.returncode != 0 and 'four-state fault mismatch' in result.stdout, result.stdout


def test_native_metadata_all_bits(tmp_path):
    source = (RTL / (NEW + '.v')).read_text()
    start = source.index('  // BEGIN BALANCED HANDOFF IDENTITY')
    end = source.index('  wire external_fault_now =', start)
    candidate = source[start:end]
    bench = '''`timescale 1ns/1ps
module tb;
reg [69:0] engine_metadata,product_bank_metadata;
reg [74:0] return_metadata;
reg next_inverse,forward_committed,product_bank_valid,product_bank_last;
reg [8:0] product_bank_position;
integer bit_index,a,b,c,n,seed=32'h2819af35,checks=0;
function automatic four(input integer digit);
  case(digit)0:four=0;1:four=1;2:four=1'bx;3:four=1'bz;endcase
endfunction
''' + candidate + '''
wire reference_identity = product_bank_metadata == {1'b1,engine_metadata[68:5],return_metadata[4:0]};
wire reference_fault = !next_inverse && forward_committed && product_bank_valid &&
  (!reference_identity || product_bank_position != 0 || product_bank_last);
task automatic compare;
begin
  #1;
  if(forward_handoff_identity!==reference_identity || handoff_fault_now!==reference_fault)
    $fatal(1,"native metadata predicate mismatch");
  checks=checks+1;
end
endtask
initial begin
  product_bank_position=0;product_bank_last=0;
  for(bit_index=0;bit_index<70;bit_index=bit_index+1)
    for(a=0;a<4;a=a+1)for(b=0;b<4;b=b+1)for(c=0;c<64;c=c+1)begin
      engine_metadata=0;return_metadata=0;
      if(bit_index<5)return_metadata[bit_index]=four(a);
      else if(bit_index<69)engine_metadata[bit_index]=four(a);
      product_bank_metadata={1'b1,engine_metadata[68:5],return_metadata[4:0]};
      product_bank_metadata[bit_index]=four(b);
      next_inverse=four(c%4);forward_committed=four((c/4)%4);product_bank_valid=four((c/16)%4);
      compare;
    end
  for(n=0;n<20000;n=n+1)begin
    engine_metadata={$random(seed),$random(seed),$random(seed)};
    return_metadata={$random(seed),$random(seed),$random(seed)};
    product_bank_metadata={1'b1,engine_metadata[68:5],return_metadata[4:0]};
    if(n%2)product_bank_metadata[n%70]=four((n/2)%4);
    product_bank_position=(n%3==0)?0:$random(seed);product_bank_last=four(n%4);
    next_inverse=four((n/4)%4);forward_committed=four((n/16)%4);product_bank_valid=four((n/64)%4);
    compare;
  end
  $display("PUBLICATION_METADATA_PASS checks=%0d",checks);$finish;
end
endmodule
'''
    result = compile_run(tmp_path, bench)
    assert result.returncode == 0 and 'PUBLICATION_METADATA_PASS checks=91680' in result.stdout, result.stdout


GOOD = 'PUBLICATION_CONE_PASS checks=10000 enabled=18 faults=0 current_exact=1 four_state_exact=1\n'
AUX = GOOD.replace('faults=0', 'faults=8') + ''.join(
    f'PUBLICATION_CONE_BOUNDARY_PASS boundary={n} fresh_reads=512 fresh_releases=1\n' for n in range(8)
) + 'PUBLICATION_CONE_BOUNDARIES_PASS cases=8 metadata_groups=5 tail_bit=1 position=1 last=1\n'


def test_actual_witness():
    assert experiment.witness(GOOD)['faults'] == 0
    assert experiment.witness(AUX, True)['faults'] == 8


@pytest.mark.parametrize('log,aux', [('', False), (GOOD + GOOD, False), (GOOD + 'FATAL', False),
    (GOOD.replace('10000', '9999'), False), (GOOD.replace('enabled=18', 'enabled=17'), False),
    (GOOD.replace('faults=0', 'faults=1'), False), (GOOD.replace('four_state_exact=1', 'four_state_exact=0'), False),
    (AUX.replace('faults=8', 'faults=0'), True), (AUX.replace('boundary=7', 'boundary=6'), True),
    (AUX.replace('fresh_reads=512', 'fresh_reads=511'), True), (AUX.replace('cases=8', 'cases=7'), True)])
def test_incomplete_witness_rejected(log, aux):
    with pytest.raises(ValueError):
        experiment.witness(log, aux)


def test_focused_injection_uses_data_not_computed_certificate():
    fragment = (RTL / 'product_publication_cone_boundaries.svh').read_text()
    assert 'force dut.product_bank_metadata=publication_bad_metadata;' in fragment
    assert 'bad_bit=boundary==5?69:15*boundary;' in fragment
    assert 'force dut.handoff_fault_now' not in fragment
    assert 'force dut.forward_handoff_identity' not in fragment
    assert 'aux_recover;' in fragment
    smoke = (ROOT / 'tools/product_publication_cone_smoke.py').read_text()
    assert 'auxiliary_active=1;run_publication_cone_boundaries;' in smoke


def test_no_recursive_task_insertion():
    helper = Path(experiment.__file__).read_text()
    assert 'run_publication_cone_boundaries;' in helper
    fragment = (RTL / 'product_publication_cone_boundaries.svh').read_text()
    bodies = re.findall(r'task automatic (\w+).*?;(.*?)endtask', fragment, re.S)
    assert len(bodies) == 2
    for name, body in bodies:
        assert not re.search(r'\b' + re.escape(name) + r'\s*[;(]', body)

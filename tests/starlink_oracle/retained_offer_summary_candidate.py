"""Source-specific offered fault summary, never a delivery/certificate substitute."""
import hashlib
import json
import re
from pathlib import Path

from tests.starlink_oracle import retained_closed_input_candidate as closed
from tests.starlink_oracle import retained_output_prototype as old

RTL = old.RTL.parent / 'retained_output_summary_candidate'
PINS = {
    'starlink_pss_fft_bank_owned_retained_output_probe.v': '62f7941bc76ac320bfdee235aeae9a5f3c3bd86e251e92f571162f8183a0abec',
    'starlink_pss_fft_retained_output_impl.v': '1d01972d11486772b627a3afdd594f06e41c0f98b830288e93b371af0506ef1e',
    'starlink_pss_core_job_cutover.v': '6f3a42178b824c28f0f6bfe3c4aeb56a2c23b84fc9aa38ab3be0d5609c4cba19',
    'starlink_pss_result_guard_owner_view.v': '53c336df4dd378a27b12f7c4d382d25290c81c0881b8e6c4f914faa67482d320',
}
PATCHES = json.loads(Path(__file__).with_name('retained_offer_summary_inverse.json').read_text())


def inverse(name, text):
    for before, after in reversed(PATCHES[name]):
        if text.count(after) != 1:
            raise ValueError('offered summary inverse boundary')
        text = text.replace(after, before, 1)
    if hashlib.sha256(text.encode()).hexdigest() != PINS[name]:
        raise ValueError('offered summary whole-source inverse')
    return text


def sources():
    for name, pin in PINS.items():
        assert hashlib.sha256((closed.RTL / name).read_bytes()).hexdigest() == pin
        inverse(name, (RTL / name).read_text())
    return [RTL / p.name if p.parent == closed.RTL and p.name in PINS else p
            for p in closed.sources()]


def composition(mode=1, private=1, completed=1):
    """Original full arithmetic/guard shadows and exact source/stall/reset script."""
    text = closed.composition(private, completed)
    extra = f'  defparam dut.INPUT_OFFER_FAULT_SUMMARY={mode};\n' + '''
  integer summary_checks=0,summary_zero_checks=0,summary_fault_checks=0,summary_ack_checks=0;
  task summary_check;
    begin
      if(dut.retained.island.fast_running)begin
        if(dut.retained.island.input_fault_now===1'b0)begin
          if({dut.retained.island.summary_offer_beat,dut.retained.island.summary_offer_complete}!==
             {dut.retained.island.certified_input_beat,dut.retained.island.certified_input_complete})
            $fatal(1,"composition offered premise mismatch");
          summary_zero_checks=summary_zero_checks+1;
        end
        if(''' + str(mode) + ''')begin
          if(dut.retained.island.input_fault_now===1'b0 || dut.retained.island.input_fault_now===1'b1)begin
            if(dut.retained.island.common_current_fault!==dut.retained.island.original_common_current_fault)
              $fatal(1,"known input fault common summary mismatch");
          end else if(dut.retained.island.common_current_fault!==1'b1)
            $fatal(1,"unknown input fault not fail closed");
        end else if(dut.retained.island.common_current_fault!==dut.retained.island.original_common_current_fault)
          $fatal(1,"disabled common summary changed");
        if(dut.retained.island.input_fault_now!==1'b0)begin
          if(dut.retained.island.reader_release!==0 || dut.retained.island.job_accept!==0)
            $fatal(1,"direct input fault lost global release/admission veto");
          summary_fault_checks=summary_fault_checks+1;
        end
        if(dut.retained.island.reader_release)summary_ack_checks=summary_ack_checks+1;
        summary_checks=summary_checks+1;
      end
    end
  endtask
  always @(posedge fft_clk)begin summary_check();#0.001;summary_check();end
  final begin
    if(summary_checks<1000||summary_zero_checks<1000)$fatal(1,"summary witness inventory");
    $display("OFFER_SUMMARY_WITNESS checks=%0d known_zero=%0d direct_fault=%0d real_ack=%0d",
      summary_checks,summary_zero_checks,summary_fault_checks,summary_ack_checks);
  end
'''
    assert text.count('endmodule') == 1
    return text.replace('endmodule', extra + 'endmodule')


def guard_equivalence(mode=1):
    """Untouched 23 healthy/37 rejection/12 reset guard stimulus; full shadows."""
    text = old.guard_equivalence_bench()
    before = '.WATCHDOG_CYCLES(2048)) shadow('
    after = f'''.WATCHDOG_CYCLES(2048),.ENABLE_OFFERED_FAULT_SUMMARY({mode})) shadow(
    .offered_input_beat(stimulus.dut.certified_input_beat),
    .offered_input_complete(stimulus.dut.certified_input_complete),'''
    assert text.count(before) == 1
    text = text.replace(before, after)
    extra = '''
  integer local_summary_checks=0;
  always @(posedge stimulus.clk or negedge stimulus.clk)begin
    #0.001;
    if(''' + str(mode) + ''')begin
      if(shadow.owner_fault_now !== (shadow.external_fault_now || shadow.offered_local_fault_now))
        $fatal(1,"guard local fault decomposition mismatch");
    end else if(shadow.offered_local_fault_now!==0)$fatal(1,"disabled summary not zero");
    local_summary_checks=local_summary_checks+1;
  end
  final begin
    if(local_summary_checks<10000)$fatal(1,"local summary inventory");
    $display("LOCAL_SUMMARY_WITNESS checks=%0d",local_summary_checks);
  end
'''
    return text.replace('endmodule', extra + 'endmodule')


def cutover_algebra():
    """Real module combinational outputs, forced state only: not reachability."""
    return '''`timescale 1ns/1ps
module tb;
  reg clk=0,resetn,core_resetn,raw_frame,raw_output,raw_status,input_beat,input_complete;
  reg[2:0]raw_vendor_faults;
  reg owner_open,configured,reset_flushed,fresh_frame,fresh_full;
  starlink_pss_core_job_cutover #(.ENABLE_OFFERED_FAULT_SUMMARY(1)) dut(
    .clk(clk),.resetn(resetn),.core_resetn(core_resetn),.job_accept(1'b0),.job_inverse(1'b0),
    .producer_closed(1'b0),.config_accept(1'b0),.input_beat(input_beat),.input_complete(input_complete),
    .offered_input_beat(input_beat),.offered_input_complete(input_complete),
    .raw_frame(raw_frame),.raw_output(raw_output),.raw_status(raw_status),.raw_vendor_faults(raw_vendor_faults));
  reg[14:0]values;integer n,k,checks=0;
  task check;
    begin
      {resetn,core_resetn,owner_open,configured,reset_flushed,fresh_frame,fresh_full,
        raw_frame,raw_output,raw_status,raw_vendor_faults,input_beat,input_complete}=values;
      #0.001;
      if(dut.offered_fault_now!==dut.fault_now)$fatal(1,"cutover offered literal predicate mismatch");
      checks=checks+1;
    end
  endtask
  initial begin
    force dut.owner_open=owner_open;force dut.configured=configured;force dut.reset_flushed=reset_flushed;
    force dut.fresh_frame=fresh_frame;force dut.fresh_full=fresh_full;
    for(n=0;n<32768;n=n+1)begin
      values=n;check();
      for(k=0;k<15;k=k+1)begin values=n;values[k]=1'bx;check();values[k]=1'bz;check();end
    end
    if(checks!=1015808)$fatal(1,"cutover algebra inventory");
    $display("OFFLINE_PASS cutover summary algebra checks=%0d forced_state_not_reachability",checks);$finish;
  end
endmodule
'''


def assert_literal_summary_partition():
    """Whole expressions, not Boolean simplification or a general graph parser."""
    guard = (RTL / 'starlink_pss_result_guard_owner_view.v').read_text()
    original = guard[guard.index('  wire effective_input_full ='):guard.index('  // No inherited external-fault echo.')]
    summary = guard[guard.index('  wire summary_effective_input_full ='):guard.index('  assign offered_local_fault_now =')]
    names = re.findall(r'wire (?:\[[^]]+\] )?(\w+)\s*=', original)
    expected = re.sub(r'\bcertified_input_beat\b', 'offered_input_beat', original)
    expected = re.sub(r'\bcertified_input_complete\b', 'offered_input_complete', expected)
    expected = re.sub(r'\bexternal_fault_now\b', "1'b0", expected)
    for name in names:
        expected = re.sub(r'\b' + name + r'\b', 'summary_' + name, expected)
    assert summary == expected
    assert len(names) == 12
    top = (RTL / 'starlink_pss_fft_retained_output_impl.v').read_text()
    external = top[top.index('  wire external_fault_now ='):top.index('  // Direct unknown input fault')]
    summary_external = top[top.index('  wire offered_external_fault_now ='):top.index('  wire forward_handoff_ack')]
    expected = external.replace('wire external_fault_now', 'wire offered_external_fault_now')
    expected = expected.replace('= input_fault_now ||', "= (input_fault_now !== 1'b0) ||")
    expected = expected.replace('cutover_fault_now', 'cutover_offered_fault_now')
    assert expected == summary_external
    assert '.offered_input_beat(summary_offer_beat && this_raw_owner)' in top
    assert '.offered_input_complete(summary_offer_complete && this_raw_owner)' in top
    return names


def common_algebra_bench(top=None):
    """Actual top scalar expressions; guard-local equivalence is a separate gate."""
    if top is None:
        top = (RTL / 'starlink_pss_fft_retained_output_impl.v').read_text()
    expressions = '\n'.join(re.search(r'  wire ' + name + r' =.*?;', top, re.S).group(0)
                            for name in ('external_fault_now', 'offered_external_fault_now',
                                         'original_common_current_fault', 'offered_common_current_fault'))
    roots = ['input_guard_fault', 'source_fault_fast[1]', 'vendor_fault_now', 'fast_fault',
             'kernel_fault', 'product_overflow', 'product_bank_fault', 'product_bank_framing_fault_now',
             'handoff_fault_now', 'cutover_fault_now', 'cutover_reasons[0]', 'retained_fault_now',
             'retained_reasons[0]', 'output_bank_fault', 'output_bank_framing_fault_now',
             'preparation_fault_now', 'result_fault']
    root_clear = ''.join(name + '=0;' for name in roots)
    root_cases = '\n'.join(f'{i}:{name}=q(value);' for i, name in enumerate(roots))
    return '''`timescale 1ns/1ps
module tb;
  reg input_fault_now,input_guard_fault,vendor_fault_now,fast_fault,kernel_fault,product_overflow;
  reg product_bank_fault,product_bank_framing_fault_now,handoff_fault_now,cutover_fault_now,retained_fault_now;
  reg output_bank_fault,output_bank_framing_fault_now,preparation_fault_now,result_fault;
  reg[1:0]source_fault_fast=0;reg[7:0]cutover_reasons=0,retained_reasons=0;
  reg[1:0]original_local,alternative_local;reg alternative_cutover;
  wire[1:0]guard_offered_local_fault=(input_fault_now===0)?original_local:alternative_local;
  wire cutover_offered_fault_now=(input_fault_now===0)?cutover_fault_now:alternative_cutover;
  wire forward_fault_now=external_fault_now||original_local[0];
  wire inverse_fault_now=external_fault_now||original_local[1];
''' + expressions + '''
  function automatic q(input integer x);
    case(x%4)0:q=0;1:q=1;2:q=1'bx;3:q=1'bz;endcase
  endfunction
  integer n,i,value,checks=0,known_checks=0,unknown_checks=0;
  reg counter_i,counter_l;
  wire original_counter=counter_i||(!counter_i&&counter_l);
  wire absorbed_counter=counter_i||counter_l;
  task check;
    begin
      #0.001;
      if(input_fault_now===0||input_fault_now===1)begin
        if(offered_common_current_fault!==original_common_current_fault)
          $fatal(1,"common independent root/decomposition mismatch root=%0d",i);
        known_checks=known_checks+1;
      end else begin
        if(offered_common_current_fault!==1)$fatal(1,"unknown direct input fault not known-one");
        if(original_common_current_fault===0)$fatal(1,"unknown input fault old predicate unexpectedly zero");
        unknown_checks=unknown_checks+1;
      end
      checks=checks+1;
    end
  endtask
  initial begin
''' + root_clear + '''
    original_local=0;alternative_local=0;alternative_cutover=0;input_fault_now=0;
    for(i=0;i<17;i=i+1)for(value=0;value<4;value=value+1)begin
''' + root_clear + '\n      case(i)\n' + root_cases + '''
      endcase
      check();
    end
''' + root_clear + '''
    for(n=0;n<16384;n=n+1)begin
      input_fault_now=q(n);original_local[0]=q(n/4);original_local[1]=q(n/16);
      alternative_local[0]=q(n/64);alternative_local[1]=q(n/256);
      cutover_fault_now=q(n/1024);alternative_cutover=q(n/4096);check();
    end
    counter_i=1'bx;counter_l=1;#0.001;
    if(original_counter!==1'bx||absorbed_counter!==1)$fatal(1,"four-state absorption counterexample missing");
    if(checks!=16452||known_checks!=8260||unknown_checks!=8192)$fatal(1,"common summary algebra inventory");
    $display("OFFLINE_PASS common actual expressions roots17 checks=%0d known=%0d unknown_tightening=%0d absorption_X_vs_1",checks,known_checks,unknown_checks);$finish;
  end
endmodule
'''

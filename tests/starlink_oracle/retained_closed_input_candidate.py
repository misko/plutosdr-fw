"""Source-specific closed-input view; no global fault delay or ACK substitution."""
import hashlib
import json
from pathlib import Path

from tests.starlink_oracle import retained_control_candidate as private
from tests.starlink_oracle import retained_output_prototype as old

RTL=old.RTL.parent/'retained_output_closed_candidate'
PINS={
    'starlink_pss_fft_bank_owned_retained_output_probe.v':'f4a0e7a3e4248cc1ec3cedee796ce591cab746c87ba25e4a1286befb46c9215e',
    'starlink_pss_fft_retained_output_impl.v':'d72a34b765d32c82ba3dfd789c335397467ed1ac40765b42f4581121963198e6',
    'starlink_pss_result_guard_owner_view.v':'71e9d5d2312833f0a9b12f5060a49f0c8b8529d9b9e43fca1e9959ecf5561a76',
    'starlink_pss_core_job_cutover.v':'6e945c035c930b9178b3d5665a6632c16ccb6ebf0b49790066164c3ad8338352',
}
PATCHES=json.loads(Path(__file__).with_name('retained_closed_input_inverse.json').read_text())


def inverse(name,text):
    for before,after in reversed(PATCHES[name]):
        if text.count(after)!=1:raise ValueError('closed-input inverse boundary')
        text=text.replace(after,before,1)
    if hashlib.sha256(text.encode()).hexdigest()!=PINS[name]:raise ValueError('closed-input whole-source inverse')
    return text


def sources():
    for name in PINS:inverse(name,(RTL/name).read_text())
    return [RTL/p.name if p.name in PINS else p for p in private.sources()]


def composition(offer=0,closed=1):
    text=private.composition(offer)
    extra=f'  defparam dut.CLOSED_INPUT_CUTOVER={closed};\n'+'''
  integer closed_checks=0,final_edges=0;
  always @(posedge fft_clk)begin
    if(`D.fast_running && `D.certified_input_complete===1'b1)begin
      if(`D.checked_input_complete!==1'b0)$fatal(1,"final input premature closed certificate");
      if(`D.guard_valid_out!==2'b0 || `D.guard_commit_out!==2'b0 || `D.forward_retirement_valid!==0)
        $fatal(1,"final input used closed public-return phase");
      final_edges=final_edges+1;
    end
    #0.001;
    if(`D.fast_running && `D.checked_input_complete===1'b1)begin
      if({`D.certified_input_beat,`D.certified_input_complete}!==2'b0)
        $fatal(1,"registered closed input has live certified strobe");
      if(`D.cutover.closed_input_fault_now!==`D.cutover.fault_now && '''+str(closed)+''')
        $fatal(1,"closed cutover predicate differs on use");
      closed_checks=closed_checks+1;
    end
  end
  final begin
    if(closed_checks<1000||final_edges<6)$fatal(1,"closed input composition inventory");
    $display("CLOSED_INPUT_WITNESS closed=%0d final_edges=%0d",closed_checks,final_edges);
  end
'''
    assert text.count('endmodule')==1
    return text.replace('endmodule',extra.replace('`D','dut.retained.island')+'endmodule')


def algebra_bench():
    """Literal source expressions, all8192 binary valuations + every single X/Z replacement."""
    import re
    original=(old.RTL/'starlink_pss_core_job_cutover.v').read_text()
    candidate=(RTL/'starlink_pss_core_job_cutover.v').read_text()
    begin=original.index('  wire known =')
    end=original.index('  assign routed_inverse =')
    full=original[begin:end]
    golden=re.sub(r'\b(input_beat|input_complete)\b',"1'b0",full)
    for name in ('known','any_raw','configured_owner','orphan','premature_reset','early_result','fault_now'):
        golden=re.sub(r'\b'+name+r'\b','gold_'+name,golden)
    cb=candidate.index('  wire closed_known =')
    ce=candidate.index('  assign routed_inverse =',cb)
    closed=candidate[cb:ce]
    expected_known=full[full.index('  wire known ='):full.index('  wire any_raw =')]
    expected_known=re.sub(r'\b(input_beat|input_complete)\b',"1'b0",expected_known).replace('wire known =','wire closed_known =')
    assert closed.startswith(expected_known)
    return '''`timescale 1ns/1ps
module tb;
  localparam ENABLE_CLOSED_INPUT_VIEW=1;
  reg resetn,core_resetn,owner_open,configured,reset_flushed,fresh_frame,fresh_full;
  reg raw_frame,raw_output,raw_status;reg[2:0]raw_vendor_faults;
  wire input_beat=0,input_complete=0;
  wire fault_now,gold_fault_now,closed_input_fault_now;
'''+full+golden+closed+'''
  reg[12:0]values;integer n,k,checks=0;
  task check;
    begin
      {resetn,core_resetn,owner_open,configured,reset_flushed,fresh_frame,fresh_full,
        raw_frame,raw_output,raw_status,raw_vendor_faults}=values;
      #1;
      if(closed_input_fault_now!==gold_fault_now || fault_now!==gold_fault_now)
        $fatal(1,"literal closed predicate four-state mismatch values=%b",values);
      checks=checks+1;
    end
  endtask
  initial begin
    for(n=0;n<8192;n=n+1)begin
      values=n;check();
      for(k=0;k<13;k=k+1)begin values=n;values[k]=1'bx;check();values[k]=1'bz;check();end
    end
    if(checks!=221184)$fatal(1,"algebra inventory");
    $display("OFFLINE_PASS literal closed predicate checks=%0d binary8192 single_XZ212992",checks);$finish;
  end
endmodule
'''


def visibility_bench():
    """Reach real held-return states without force; classify X/Z, never treat X as valid."""
    import re
    source=(old.BASELINE/'starlink_pss_realtime_result_guard.v').read_text()
    ports=source[source.index(') (\n')+4:source.index('\n);')]
    inputs=re.findall(r'input wire (?:\[[^]]+\] )?(\w+)',ports)
    assert len(inputs)==25
    instances=''
    for name,mode in [('reference',None),('naive',0),('hardened',1)]:
        module='starlink_pss_realtime_result_guard' if mode is None else 'starlink_pss_result_guard_owner_view'
        extra='' if mode is None else f',.REQUIRE_KNOWN_COMPLETED_INPUT({mode})'
        connections=','.join(f'.{p}('+('full_fault' if name=='reference' else 'closed_fault')+')'
            if p=='completed_input_fault_now' else f'.{p}({p})' for p in inputs)
        instances+=f'{module} #(.USE_COMPLETED_INPUT_FAULT(1),.USE_FORWARD_RETIREMENT(1){extra}) {name}({connections});\n'
    return '''`timescale 1ns/1ps
module tb;
  reg clk=0,resetn=0,job_valid=0;
  reg[69:0]job_descriptor=70'h12345;
  reg input_bank_reserved=1,output_bank_reserved=1;
  reg certified_input_beat=0,certified_input_complete=0,final_fence_certified=0;
  reg external_fault_now=0,phase_input_fault_now=0,completed_input_certified=1;
  reg full_fault=0,closed_fault=0,preflight_fault_evidence_now=0;
  reg core_event_frame_started=0,core_output_tvalid=0,core_output_tlast=0;
  reg[47:0]core_output_tdata=0;reg[23:0]core_output_tuser=0;
  reg[7:0]core_status_tdata=0;reg core_status_tvalid=0;
  reg mailbox_input_ready=1,mailbox_input_fault=0,inverse_phase=0,forward_mailbox_fault=0;
'''+instances+'''
  integer n,q,f,checks=0,zero_to_x=0,x_to_zero=0,known_equal=0,raw_checks=0;
  task tick;begin #5;clk=1;#0.001;#4.999;clk=0;end endtask
  task probe;
    begin
      for(q=0;q<4;q=q+1)for(f=0;f<2;f=f+1)begin
        case(q)0:completed_input_certified=0;1:completed_input_certified=1;
          2:completed_input_certified=1'bx;3:completed_input_certified=1'bz;endcase
        external_fault_now=f;full_fault=f;closed_fault=(q<2)?f:0;
        #1;
        if(reference.faults_now!==hardened.faults_now || reference.faults_now!==naive.faults_now)
          $fatal(1,"unrestricted diagnostics changed");
        if(reference.mailbox_private_valid!==1 || hardened.mailbox_private_valid!==1)
          $fatal(1,"private storage changed into public certificate gate");
        if(q<2)begin
          if({reference.mailbox_input_valid,reference.mailbox_commit_valid,reference.forward_retirement_valid}!==
             {hardened.mailbox_input_valid,hardened.mailbox_commit_valid,hardened.forward_retirement_valid})
            $fatal(1,"known certificate public behavior changed");
          known_equal=known_equal+1;
        end else begin
          if({hardened.mailbox_input_valid,hardened.mailbox_commit_valid,hardened.forward_retirement_valid}!==3'b0)
            $fatal(1,"unknown complete certificate gained public visibility");
          if(f==0)begin
            if(reference.mailbox_input_valid!==1'bx)$fatal(1,"missing original X visibility specimen");
            x_to_zero=x_to_zero+1;
          end else begin
            if(reference.mailbox_input_valid!==0 || naive.mailbox_input_valid!==1'bx)
              $fatal(1,"missing naive zero-to-X counterexample");
            zero_to_x=zero_to_x+1;
          end
        end
        checks=checks+1;
      end
      completed_input_certified=1;external_fault_now=0;full_fault=0;closed_fault=0;
      // Actual raw flags and independent faults remain immediate public vetoes.
      for(q=0;q<6;q=q+1)begin
        case(q)0:external_fault_now=1;1:mailbox_input_fault=1;2:output_bank_reserved=0;
          3:core_event_frame_started=1;4:core_status_tvalid=1;5:core_output_tvalid=1;endcase
        full_fault=external_fault_now;closed_fault=full_fault;#1;
        if(reference.faults_now!==hardened.faults_now ||
           {reference.mailbox_input_valid,reference.mailbox_commit_valid,reference.forward_retirement_valid}!==
           {hardened.mailbox_input_valid,hardened.mailbox_commit_valid,hardened.forward_retirement_valid})
          $fatal(1,"current raw fault public equivalence");
        raw_checks=raw_checks+1;
        external_fault_now=0;mailbox_input_fault=0;output_bank_reserved=1;
        core_event_frame_started=0;core_status_tvalid=0;core_output_tvalid=0;
        full_fault=0;closed_fault=0;
      end
    end
  endtask
  initial begin
    tick();resetn=1;job_valid=1;tick();job_valid=0;
    for(n=0;n<512;n=n+1)begin
      certified_input_beat=1;certified_input_complete=(n==511);core_event_frame_started=(n==0);tick();
    end
    certified_input_beat=0;certified_input_complete=0;core_event_frame_started=0;
    core_output_tvalid=1;core_status_tvalid=1;tick();core_output_tvalid=0;core_status_tvalid=0;
    probe();
    for(n=1;n<512;n=n+1)begin
      core_output_tvalid=1;core_output_tuser=n;core_output_tlast=(n==511);tick();
    end
    core_output_tvalid=0;core_output_tlast=0;final_fence_certified=1;
    probe();tick();
    if(reference.awaiting_ack!==1 || hardened.awaiting_ack!==1)$fatal(1,"healthy final publication");
    // A retained old inverse's ACK must not depend on next job's complete flag.
    completed_input_certified=0;#1;
    if(hardened.owner_ack_accept!==1 || reference.idle_fault_now!==0)
      $fatal(1,"ACK incorrectly tied to shared completed-input certificate");
    tick();if(hardened.awaiting_ack!==0 || reference.awaiting_ack!==0)$fatal(1,"ACK not retired");
    external_fault_now=1;tick();
    if(reference.fault_reasons!==hardened.fault_reasons || hardened.protocol_fault!==1)
      $fatal(1,"full current diagnostic not sticky");
    resetn=0;tick();
    if(reference.fault_reasons!==0 || hardened.fault_reasons!==0)$fatal(1,"diagnostic reset changed");
    if(checks!=16||zero_to_x!=4||x_to_zero!=4||known_equal!=8||raw_checks!=12)
      $fatal(1,"visibility specimen inventory");
    $display("OFFLINE_PASS visibility known_equal8 original_X_to_zero4 naive_zero_to_X4 raw12 real_ACK_complete0");$finish;
  end
endmodule
'''

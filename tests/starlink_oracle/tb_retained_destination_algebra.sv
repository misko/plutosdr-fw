// OFFLINE combinational proof, not a controller reachability or timing proof.
`timescale 1ns/1ps
module tb;
  reg fast_running=0, input_fault=0, request_toggle=0;
  reg [1:0] acknowledge_sync=0;
  wire in_running=fast_running;
  wire input_ready;
@@MAILBOX_READY@@
  wire output_bank_ready=input_ready;
  reg next_inverse=0, product_bank_ready=1;
  reg REGISTERED_SCHEDULING=1, INPUT_OFFER_FAULT_SUMMARY=1, preparing=1;
  reg [5:0] preparation_age=0;
  reg [1:0] preflight_identity_equal=3;
  reg descriptor_header_valid=1;
  reg [1:0] preflight_lease=0, held_lease=0;
  reg [8:0] preflight_position=0;
  reg preflight_last=0, preflight_valid=1;
  reg input_fault_now=0,input_guard_fault=0,vendor_fault_now=0,fast_fault=0,kernel_fault=0;
  reg product_overflow=0,product_bank_fault=0,product_bank_framing_fault_now=0,handoff_fault_now=0;
  reg cutover_fault_now=0,cutover_offered_fault_now=0,forward_fault_now=0,inverse_fault_now=0;
  reg output_bank_fault=0,output_bank_framing_fault_now=0,result_fault=0;
  reg [1:0] source_fault_fast=0,guard_offered_local_fault=0;
  reg [7:0] cutover_reasons=0;
  wire retained_fault_now,retained_reusable,retained_reserved;
  wire [7:0] retained_reasons;
  wire common_current_fault;
  starlink_pss_retained_output_owner owner(
    .clk(1'b0),.resetn(fast_running),.inverse_admit(1'b0),.inverse_publication(1'b0),
    .inverse_guard_ack(1'b0),.transfer_consumed(1'b0),.bank_ready(output_bank_ready),
    .bank_request(request_toggle),.bank_ack_sync(acknowledge_sync[1]),
    .common_current_fault(common_current_fault),.reusable(retained_reusable),
    .reservation(retained_reserved),.fault_now(retained_fault_now),.fault_reasons(retained_reasons));
@@ORIGINALS@@
@@SCALAR_EXTERNALS@@

  // FROZEN BEFORE EVALUATION. Only parallel common aggregate changes.
  // A: proposed raw scalar. Unknown/nonrunning reset uses original verbatim.
  wire scalar_destination = next_inverse ? output_bank_ready : product_bank_ready;
  // B: separately declared tightening. Requires a NEW observational private-Q
  // knownness seam; not a claim this port exists or that synthesis preserves X.
  wire reserved_known = owner.reserved === 1'b0 || owner.reserved === 1'b1;
  wire tight_destination = next_inverse ?
    (output_bank_ready && reserved_known) : product_bank_ready;
  wire scalar_destination_event = REGISTERED_SCHEDULING && fast_running && preparing ?
    !scalar_destination : 1'b0;
  wire tight_destination_event = REGISTERED_SCHEDULING && fast_running && preparing ?
    !tight_destination : 1'b0;
  wire [5:0] scalar_events = {preflight_events_now[5],scalar_destination_event,preflight_events_now[3:0]};
  wire [5:0] tight_events = {preflight_events_now[5],tight_destination_event,preflight_events_now[3:0]};
  wire scalar_original = scalar_external_fault_now || forward_fault_now || inverse_fault_now ||
    output_bank_fault || output_bank_framing_fault_now || (|scalar_events) || result_fault;
  wire scalar_offered = scalar_offered_external_fault_now || guard_offered_local_fault[0] ||
    guard_offered_local_fault[1] || output_bank_fault || output_bank_framing_fault_now ||
    (|scalar_events) || result_fault;
  wire tight_original = external_fault_now || forward_fault_now || inverse_fault_now ||
    output_bank_fault || output_bank_framing_fault_now || (|tight_events) || result_fault;
  wire tight_offered = offered_external_fault_now || guard_offered_local_fault[0] ||
    guard_offered_local_fault[1] || output_bank_fault || output_bank_framing_fault_now ||
    (|tight_events) || result_fault;
  wire scalar_common = (fast_running === 1'b1) ?
    (INPUT_OFFER_FAULT_SUMMARY ? scalar_offered : scalar_original) : common_current_fault;
  wire tight_common = (fast_running === 1'b1) ?
    (INPUT_OFFER_FAULT_SUMMARY ? tight_offered : tight_original) : common_current_fault;
  // C: parent-selected exact contextual variant, also frozen before execution.
  // No unknown state is silently treated as healthy; fallback is full original.
  wire contextual_common = (fast_running === 1'b1 && reserved_known) ?
    (INPUT_OFFER_FAULT_SUMMARY ? scalar_offered : scalar_original) : common_current_fault;

  function automatic val(input integer x);
    case(x) 0:val=0; 1:val=1; 2:val=1'bx; 3:val=1'bz; endcase
  endfunction
  function automatic integer code(input x);
    case(x) 0:code=0; 1:code=1; 1'bx:code=2; 1'bz:code=3; endcase
  endfunction
  integer owners=0,contexts=0,signatures=0,known_equal=0,fallback_equal=0;
  integer raw_differences=0,tightened=0,clean_equal=0,root_checks=0,lemmas=0;
  reg [32767:0] seen=0;
  integer signature,n,lease_case,reason_case,p,g,b,o,c,m,j,k,v,t,aa,dd;
  reg [5:0] lemma_bits,lemma_masked,lemma_parallel;
  reg lemma_gate;
  reg [7:0] root_saved;

  task check;
    begin
      contexts=contexts+1;
      if(contextual_common!==common_current_fault)
        $fatal(1,"DESTINATION_CONTEXTUAL_EQUIVALENCE_FAILED old=%b new=%b",common_current_fault,contextual_common);
      if(fast_running!==1'b1)begin
        if(scalar_common!==common_current_fault || tight_common!==common_current_fault)
          $fatal(1,"DESTINATION_RESET_FALLBACK_CHANGED");
        fallback_equal=fallback_equal+1;
      end
      if(reserved_known)begin
        if(scalar_common!==common_current_fault)
          $fatal(1,"DESTINATION_KNOWN_STATE_EQUIVALENCE_FAILED R=%b B=%b reserve=%b fault=%b reason=%h old=%b new=%b",fast_running,output_bank_ready,owner.reserved,retained_fault_now,retained_reasons,common_current_fault,scalar_common);
        known_equal=known_equal+1;
      end
      if(scalar_common!==common_current_fault)begin
        if(raw_differences==0)
          $display("DESTINATION_RAW_COUNTEREXAMPLE R=%b B=%b request=%b ack=%b reserve=%b published=%b expected=%b lease=%b held=%b reason=%h current=%b phase=%b preparing=%b P=%b old_vector=%b old=%b raw=%b tight=%b",fast_running,output_bank_ready,request_toggle,acknowledge_sync[1],owner.reserved,owner.published,owner.expected_request,owner.lease,owner.held_lease,retained_reasons,retained_fault_now,next_inverse,preparing,product_bank_ready,preflight_events_now,common_current_fault,scalar_common,tight_common);
        raw_differences=raw_differences+1;
      end
      if(tight_common!==common_current_fault)begin
        if(common_current_fault!==1'bx || tight_common!==1'b1)
          $fatal(1,"DESTINATION_TIGHTENING_WEAKER old=%b tight=%b",common_current_fault,tight_common);
        tightened=tightened+1;
      end else if(common_current_fault===1'b0) clean_equal=clean_equal+1;
    end
  endtask

  task contexts_for_owner;
    begin
      for(p=0;p<4;p=p+1)for(g=0;g<4;g=g+1)for(b=0;b<4;b=b+1)
      for(o=0;o<3;o=o+1)for(c=0;c<3;c=c+1)for(m=0;m<4;m=m+1)begin
        next_inverse=val(p); preparing=val(g); product_bank_ready=val(b);
        preflight_valid=!val(o); input_guard_fault=val(c); INPUT_OFFER_FAULT_SUMMARY=val(m);
        #1; check();
      end
      next_inverse=0;preparing=1;product_bank_ready=1;preflight_valid=1;
      input_guard_fault=0;INPUT_OFFER_FAULT_SUMMARY=1;
    end
  endtask

  task set_root(input integer index,input value);
    begin
      case(index)
        0:input_fault_now=value; 1:input_guard_fault=value; 2:source_fault_fast[1]=value;
        3:vendor_fault_now=value;4:fast_fault=value;5:kernel_fault=value;
        6:product_overflow=value;7:product_bank_fault=value;8:product_bank_framing_fault_now=value;
        9:handoff_fault_now=value;10:cutover_fault_now=value;11:cutover_offered_fault_now=value;
        12:forward_fault_now=value;13:inverse_fault_now=value;14:guard_offered_local_fault[0]=value;
        15:guard_offered_local_fault[1]=value;16:output_bank_fault=value;
        17:output_bank_framing_fault_now=value;18:result_fault=value;
        default:cutover_reasons[index-19]=value;
      endcase
    end
  endtask

  initial begin
    // Lemma: unchanged other five reasons may be reduced independently, even
    // with an X/Z conditional gate. Enumerate all 3^6 logical cause vectors.
    for(n=0;n<729;n=n+1)for(g=0;g<4;g=g+1)begin
      t=n;for(j=0;j<6;j=j+1)begin lemma_bits[j]=val(t%3);t=t/3;end
      lemma_gate=val(g);lemma_masked=lemma_gate?lemma_bits:6'b0;
      lemma_parallel=lemma_gate?{lemma_bits[5],1'b0,lemma_bits[3:0]}:6'b0;
      if((|lemma_masked)!==((|lemma_parallel)||(lemma_gate?lemma_bits[4]:1'b0)))
        $fatal(1,"DESTINATION_VECTOR_DECOMPOSITION_FAILED");
      lemmas=lemmas+1;
    end
    // Exact source owner, arbitrary four-state scalar controls AND state.
    // !== reduces both 2-bit leases to a known Boolean; all256 pairs below.
    for(n=0;n<16384;n=n+1)for(lease_case=0;lease_case<2;lease_case=lease_case+1)
    for(reason_case=0;reason_case<3;reason_case=reason_case+1)begin
      fast_running=val(n%4);input_fault=val((n/4)%4);request_toggle=val((n/16)%4);
      acknowledge_sync[1]=val((n/64)%4);#1;
      owner.reserved=val((n/256)%4);owner.published=val((n/1024)%4);
      owner.expected_request=val((n/4096)%4);owner.lease=0;owner.held_lease=lease_case;
      owner.fault_reasons={7'b0,val(reason_case)};#1;owners=owners+1;
      signature=code(fast_running)+4*code(output_bank_ready)+16*code(retained_fault_now)+
        64*code(|retained_reasons)+256*code(retained_reserved)+1024*code(retained_reusable)+
        4096*code(reserved_known);
      if(!seen[signature])begin seen[signature]=1;signatures=signatures+1;contexts_for_owner();end
    end
    // Full lease encodings and all4^8 reason patterns establish reduction
    // coverage, not an assumption that reason/lease bits are binary.
    fast_running=1;input_fault=0;request_toggle=0;acknowledge_sync=0;#1;
    owner.reserved=1;owner.published=0;owner.expected_request=0;
    next_inverse=1;preparing=1;product_bank_ready=1;
    for(n=0;n<256;n=n+1)begin
      owner.lease={val(n%4),val((n/4)%4)};owner.held_lease={val((n/16)%4),val((n/64)%4)};
      owner.fault_reasons=0;#1;check();
      if(owner.lease_bad !== (owner.held_lease !== owner.lease))$fatal(1,"LEASE_REDUCTION");
    end
    owner.lease=0;owner.held_lease=0;
    for(n=0;n<65536;n=n+1)begin
      t=n;for(j=0;j<8;j=j+1)begin owner.fault_reasons[j]=val(t%4);t=t/4;end
      #1;check();
    end
    // Each independently ORed root, every X/Z value, both original/offered
    // paths and the source option's X/Z mux. Pair each with each reason bit.
    for(j=0;j<27;j=j+1)for(v=0;v<4;v=v+1)for(k=0;k<8;k=k+1)
    for(aa=0;aa<4;aa=aa+1)for(m=0;m<4;m=m+1)begin
      owner.fault_reasons=0;owner.fault_reasons[k]=val(aa);
      set_root(j,val(v));INPUT_OFFER_FAULT_SUMMARY=val(m);#1;check();
      root_checks=root_checks+1;set_root(j,0);
    end
    if(owners!=98304 || raw_differences==0 || tightened==0 || clean_equal==0 ||
       fallback_equal==0 || known_equal==0 || lemmas!=2916 || root_checks!=13824)
      $fatal(1,"DESTINATION_COVERAGE_MISSING");
    $display("DESTINATION_ALGEBRA_PASS owners=%0d signatures=%0d contexts=%0d known_equal=%0d fallback_equal=%0d raw_differences=%0d tightened=%0d clean_equal=%0d roots=%0d lemmas=%0d",owners,signatures,contexts,known_equal,fallback_equal,raw_differences,tightened,clean_equal,root_checks,lemmas);
    $finish;
  end
endmodule

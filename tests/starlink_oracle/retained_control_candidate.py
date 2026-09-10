"""Additive source-specific candidate; original runtime and tests are untouched."""
import hashlib
import json

from tests.starlink_oracle import retained_output_prototype as old

CANDIDATE = old.RTL.parent / 'retained_output_candidate'
PINS = {
    'starlink_pss_result_guard_owner_view.v': 'c837ff759939332096787cd7a985c46ab8447c2a91b9476eaccdd39ff6b2b557',
    'starlink_pss_fft_retained_output_impl.v': '2f11bc7e08e907209336775877155839becf45f8015126bd99769c2dccc550d4',
    'starlink_pss_fft_bank_owned_retained_output_probe.v': '2765b35492cc99555a40c122208c1bcb104f5c33829f1822c78b17f70c9f1d83',
}
PATCHES = json.loads(__import__('pathlib').Path(__file__).with_name('retained_private_offer_inverse.json').read_text())


def inverse(name, text):
    for before, after in reversed(PATCHES[name]):
        if text.count(after) != 1:
            raise ValueError('private offer inverse boundary')
        text = text.replace(after, before, 1)
    if hashlib.sha256(text.encode()).hexdigest() != PINS[name]:
        raise ValueError('private offer whole-source inverse')
    return text


def sources():
    for name, pin in PINS.items():
        assert hashlib.sha256((old.RTL / name).read_bytes()).hexdigest() == pin
        inverse(name, (CANDIDATE / name).read_text())
    return [CANDIDATE / p.name if p.parent == old.RTL and p.name in PINS else p
            for p in old.composition_sources()]


def composition(mode=1):
    """All old arithmetic/retirement/two-guard shadows remain literal."""
    text = old.composition_bench()
    extra = f'  defparam dut.PRIVATE_DESCRIPTOR_OFFER={mode};\n'
    for owner in range(2):
        g = f'dut.retained.island.owners[{owner}].result_guard'
        extra += f'''
  reg [69:0] saved_descriptor_{owner};
  reg owned_before_{owner},accepted_before_{owner},running_before_{owner};
  reg [69:0] offered_descriptor_{owner};
  integer accepted_checks_{owner}=0,held_checks_{owner}=0,ack_checks_{owner}=0;
  always @(posedge fft_clk)begin
    running_before_{owner}=dut.retained.island.fast_running;
    owned_before_{owner}={g}.active || {g}.awaiting_ack;
    accepted_before_{owner}={g}.job_accept;
    offered_descriptor_{owner}={g}.job_descriptor;
    saved_descriptor_{owner}={g}.descriptor;
    if(running_before_{owner} && accepted_before_{owner})begin
      if({g}.private_descriptor_offer!==1'b1)$fatal(1,"accepted job missing private offer");
      accepted_checks_{owner}=accepted_checks_{owner}+1;
    end
    if(running_before_{owner} && {g}.owner_ack_accept)ack_checks_{owner}=ack_checks_{owner}+1;
    #0.000001;
    if(running_before_{owner} && dut.retained.island.fast_running)begin
      if(owned_before_{owner})begin
        if({g}.descriptor!==saved_descriptor_{owner})$fatal(1,"active/parked/ACK descriptor overwrite");
        held_checks_{owner}=held_checks_{owner}+1;
      end
      if(accepted_before_{owner} && {g}.descriptor!==offered_descriptor_{owner})
        $fatal(1,"accepted descriptor same-edge mismatch");
    end
  end
  final begin
    if(accepted_checks_{owner}<3 || held_checks_{owner}<1000 || ack_checks_{owner}<3)
      $fatal(1,"private descriptor witness inventory");
    $display("PRIVATE_OFFER_WITNESS owner={owner} accepted=%0d held=%0d real_ack=%0d",accepted_checks_{owner},held_checks_{owner},ack_checks_{owner});
  end
'''
    assert text.count('endmodule') == 1
    return text.replace('endmodule', extra + 'endmodule')


def guard_boundary_bench(mode=1, missing_offer=False):
    """Original 23 healthy/37 rejection/12 reset stimuli; independent private-state model."""
    text = old.guard_equivalence_bench()
    text = text.replace('.WATCHDOG_CYCLES(2048)) shadow(',
        f'.WATCHDOG_CYCLES(2048),.USE_PRIVATE_DESCRIPTOR_OFFER({mode})) shadow(.private_descriptor_offer(private_offer),', 1)
    text = text.replace('  integer comparisons=0;', '''
  reg [69:0] expected_private=0;
  integer private_changes=0,private_accepted=0,private_held=0,private_acks=0;
  wire private_offer = ''' + ("1'b0" if missing_offer else "1'b1") + ''';
  always @(posedge stimulus.clk or negedge stimulus.resetn)begin
    if(!stimulus.resetn)expected_private=0;
    else begin
      if(stimulus.dut.job_accept)begin
        if(private_offer!==1'b1)$fatal(1,"accepted job missing private offer");
        private_accepted=private_accepted+1;
      end
      if(shadow.active || shadow.awaiting_ack)private_held=private_held+1;
      if(shadow.owner_ack_accept)private_acks=private_acks+1;
      if(!shadow.active && !shadow.awaiting_ack && !shadow.protocol_fault &&
         (''' + str(mode) + ''' ? private_offer : stimulus.dut.job_valid))begin
        expected_private=stimulus.dut.job_descriptor;
        private_changes=private_changes+1;
      end
    end
    #0.001;
    if(shadow.descriptor!==expected_private)$fatal(1,"independent private descriptor model");
  end
  final begin
    if(private_accepted<23||private_held<1000||private_acks<23||private_changes<23)
      $fatal(1,"private boundary inventory");
    $display("PRIVATE_BOUNDARY accepted=%0d held=%0d ack=%0d loads=%0d",private_accepted,private_held,private_acks,private_changes);
  end
  integer comparisons=0;''', 1)
    # Original full equivalence remains the default test. In the opt-in test
    # only invalid descriptor and its concatenated invalid output may differ;
    # their values are checked above, never accepted as unconstrained state.
    if mode:
        for name in ('descriptor', 'mailbox_input_metadata'):
            before = f'if(shadow.{name} !== stimulus.dut.{name})'
            assert text.count(before) == 1
            text = text.replace(before, f'if((shadow.active || shadow.awaiting_ack) && shadow.{name} !== stimulus.dut.{name})', 1)
    return text

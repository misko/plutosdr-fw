"""Literal inverse of ONLY the new per-cause CDC option."""

BASE = "2ccfac2e70da2689d97eee75cbfc78e2589813a2"
LEGACY = """  always @(posedge clk)
    if (!slow_running) fast_fault_slow <= 0;
    else fast_fault_slow <= {fast_fault_slow[0], fast_fault};
"""
CDC_BODY = (
    """  // BEGIN PER_CAUSE_FAULT_CDC: independent sticky event levels, not a data bus.
  // Fast-domain quarantine/publication fences still consume fast_fault exactly
  // as before. Only its slow-domain observation is factored across the two
  // synchronization stages; both aggregate stage names remain observable.
  generate if (PER_CAUSE_FAULT_CDC && DISTRIBUTED_FAST_FAULT) begin : per_cause_fault_cdc
    wire [11:0] first_stage, second_stage;
    for (genvar cause_index = 0; cause_index < 12; cause_index = cause_index + 1) begin : causes
      (* ASYNC_REG = "TRUE" *) reg [1:0] cause_sync;
      always @(posedge clk)
        if (!slow_running) cause_sync <= 0;
        else cause_sync <= {cause_sync[0], distributed_fast_fault.cause_sticky[cause_index]};
      assign first_stage[cause_index] = cause_sync[0];
      assign second_stage[cause_index] = cause_sync[1];
    end
    always @* fast_fault_slow = {|second_stage, |first_stage};
  end else begin : aggregate_fault_cdc
"""
    + LEGACY
    + """  end endgenerate
  // END PER_CAUSE_FAULT_CDC
"""
)


def restore_fault_cdc(source):
    parameter = "  parameter integer PER_CAUSE_FAULT_CDC = 0,\n"
    checks = """    if (PER_CAUSE_FAULT_CDC !== 0 && PER_CAUSE_FAULT_CDC !== 1)
      $fatal(1, "PER_CAUSE_FAULT_CDC must be zero or one");
    if (PER_CAUSE_FAULT_CDC && !DISTRIBUTED_FAST_FAULT)
      $fatal(1, "PER_CAUSE_FAULT_CDC requires DISTRIBUTED_FAST_FAULT");
"""
    for addition in (parameter, checks):
        if source.count(addition) != 1:
            raise ValueError("nonunique CDC inverse addition")
        source = source.replace(addition, "", 1)
    if source.count(CDC_BODY) != 1:
        raise ValueError("CDC body is not the exact reviewed addition")
    return source.replace(CDC_BODY, LEGACY, 1)

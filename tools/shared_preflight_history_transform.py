"""Share same-edge preflight evidence without delaying any guard output."""
from private_replay_sequence_transform import transform,undo
TOP_CHANGES = [
  [
    "module starlink_pss_fft_private_replay_sequence_impl #(",
    "module starlink_pss_fft_shared_preflight_history_impl #("
  ],
  [
    "  wire preparation_fault_now = |preflight_events_now;",
    "  wire preparation_fault_now = |preflight_events_now;\n  // Same-edge sticky evidence shared by both guards. This is diagnostic history,\n  // not current admission/publication permission. Common async epoch reset\n  // matches both guards even when asserted between fast-clock edges.\n  reg [5:0] shared_preflight_history;\n  always @(posedge fft_clk or negedge fast_running)\n    if (!fast_running) shared_preflight_history <= 0;\n    else shared_preflight_history <= shared_preflight_history | preflight_events_now;"
  ],
  [
    "  starlink_pss_result_guard_owner_view #(.USE_COMPLETED_INPUT_FAULT(1),",
    "  starlink_pss_result_guard_shared_preflight #(.USE_COMPLETED_INPUT_FAULT(1),"
  ],
  [
    "    .USE_PREFLIGHT_REASON_ONLY(REGISTERED_SCHEDULING),",
    "    .USE_PREFLIGHT_REASON_ONLY(REGISTERED_SCHEDULING),\n    .USE_SHARED_PREFLIGHT_HISTORY(REGISTERED_SCHEDULING),"
  ],
  [
    "    .preflight_fault_evidence_now(preparation_fault_now),",
    "    .preflight_fault_evidence_now(preparation_fault_now),\n    .shared_preflight_history(shared_preflight_history),"
  ]
]
GUARD_CHANGES = [
  [
    "module starlink_pss_result_guard_owner_view #(",
    "module starlink_pss_result_guard_shared_preflight #("
  ],
  [
    "  parameter integer USE_PREFLIGHT_REASON_ONLY = 0,",
    "  parameter integer USE_PREFLIGHT_REASON_ONLY = 0,\n  // Caller supplies the sticky six-cause history from the SAME edge/reset as\n  // this guard. It replaces only duplicated preflight diagnostic storage.\n  parameter integer USE_SHARED_PREFLIGHT_HISTORY = 0,"
  ],
  [
    "  input wire preflight_fault_evidence_now,",
    "  input wire preflight_fault_evidence_now,\n  input wire [5:0] shared_preflight_history,"
  ],
  [
    "  output reg [7:0] fault_reasons,",
    "  output wire [7:0] fault_reasons,"
  ],
  [
    "  reg active_private, awaiting_ack;",
    "  reg [7:0] private_fault_reasons;\n  assign fault_reasons = private_fault_reasons |\n    {7'b0, (USE_SHARED_PREFLIGHT_HISTORY ? (|shared_preflight_history) : 1'b0)};\n  initial begin\n    if ((USE_SHARED_PREFLIGHT_HISTORY !== 0 && USE_SHARED_PREFLIGHT_HISTORY !== 1) ||\n        (USE_SHARED_PREFLIGHT_HISTORY === 1 && USE_PREFLIGHT_REASON_ONLY !== 1))\n      $fatal(1,\"shared preflight history requires a known reason-only caller\");\n  end\n  reg active_private, awaiting_ack;"
  ],
  [
    "      fault_reasons <= 0;",
    "      private_fault_reasons <= 0;"
  ],
  [
    "      fault_reasons <= fault_reasons | faults_now |\n        {7'b0, (USE_PREFLIGHT_REASON_ONLY && preflight_fault_evidence_now)};",
    "      private_fault_reasons <= fault_reasons | faults_now |\n        {7'b0, (USE_PREFLIGHT_REASON_ONLY && !USE_SHARED_PREFLIGHT_HISTORY && preflight_fault_evidence_now)};"
  ]
]

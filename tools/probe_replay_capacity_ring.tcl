# Observe real register endpoints without changing checkpoint or constraints.
if {$argc != 4 || [version -short] ne "2022.2"} {error "expected ROUTED_DCP SHA NEW_OUTPUT"}
lassign $argv checkpoint expected output expect_ring
if {$expect_ring ni {0 1}} {error "explicit FIFO expectation required"}
if {[file exists $output] || [lindex [exec sha256sum $checkpoint] 0] ne $expected} {error "unapproved checkpoint or existing output"}
file mkdir $output
set_param general.maxThreads 2
open_checkpoint $checkpoint
set f [open [file join $output endpoints.txt] {WRONLY CREAT EXCL}]
puts $f "checkpoint_sha256=$expected"
puts $f "design=[current_design]"
puts $f "expect_ring=$expect_ring"
foreach {label pattern} {
  kernel_next_ce *joiner/kernel_rom/expected_next_block_start_reg*/CE
  forward_position_ce *forward_buffer/output_position_reg*/CE
  ring_slot0_ce *replay_fifo/slot0_reg*/CE
  ring_slot1_ce *replay_fifo/slot1_reg*/CE
  ring_count *replay_fifo/count_reg*/D
  ring_read_slot *replay_fifo/read_slot_reg/D
  ring_write_slot *replay_fifo/write_slot_reg/D
  kernel_index *joiner/kernel_rom/expected_bin_index_reg*/D
  kernel_history *joiner/kernel_rom/have_previous_block_reg*/D
  descriptor_ce *forward_buffer/descriptor_reg*/CE
  descriptor_data *forward_buffer/descriptor_reg*/D
  output_occupancy *output_identity_stage/full_reg/D
  output_publication *output_bank/request_toggle_reg*/D
  product_publication *product_bank/request_toggle_reg*/D
  occupancy *product_identity_stage/full_reg/D
  identity *product_identity_stage/output_identity_good_reg/D
} {
  set pins [get_pins -quiet -hierarchical -filter "NAME =~ $pattern"]
  if {[string match "ring_*" $label] && !$expect_ring} {continue}
  if {![llength $pins]} {error "missing $label endpoint"}
  if {$label ni {descriptor_ce descriptor_data output_publication product_publication kernel_next_ce kernel_index kernel_history forward_position_ce ring_slot0_ce ring_slot1_ce ring_count} && [llength $pins] != 1} {error "ambiguous $label endpoint"}
  puts $f "$label.pins=[llength $pins]"
  set paths [get_timing_paths -to $pins -delay_type max -max_paths 1]
  if {[llength $paths] != 1} {error "missing $label timing path"}
  puts $f "$label.slack=[get_property SLACK $paths]"
  puts $f "$label.start=[get_property STARTPOINT_PIN $paths]"
  puts $f "$label.end=[get_property ENDPOINT_PIN $paths]"
  report_timing -to $pins -delay_type max -max_paths 20 -file [file join $output $label.rpt]
}
close $f
close_design
if {[lindex [exec sha256sum $checkpoint] 0] ne $expected} {error "checkpoint changed during observation"}
puts REPLAY_RING_ENDPOINTS_OBSERVED_NOT_FULL_SIGNOFF

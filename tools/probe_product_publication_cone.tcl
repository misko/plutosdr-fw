# Observe the exact routed worst publication cone; no timing exceptions or edits.
if {$argc != 3 || [version -short] ne "2022.2"} {error "expected CHECKPOINT SHA OUTPUT"}
lassign $argv checkpoint expected output
if {[file exists $output] || [lindex [exec sha256sum $checkpoint] 0] ne $expected} {error "checkpoint/output identity"}
file mkdir $output
set_param general.maxThreads 2
open_checkpoint $checkpoint
set f [open [file join $output cone.txt] {WRONLY CREAT EXCL}]
puts $f "checkpoint=$expected"
foreach name {
 {product_bank/balanced_preflight.comparisons[0].split_banks.banks[1].bank_leaf_equal_inferred_i_15}
 {handoff_group_equal_inferred_i_3}
 {completion_gate/private_facts.snapshot_good[5]_i_3}
 {product_bank/private_facts.snapshot_good[5]_i_1}
 {product_bank/awaiting_ack_i_5}
 {cutover/awaiting_ack_i_4}
 {owners[0].result_guard/request_toggle_i_2_comp}
 {product_bank/request_toggle_i_1__0}
} {
 set cell [get_cells -quiet -hierarchical -filter [format {NAME == "%s"} $name]]
 if {[llength $cell]!=1} {error "missing exact routed cell $name"}
 puts $f "CELL $name [get_property REF_NAME $cell] INIT=[get_property INIT $cell]"
 foreach pin [lsort [get_pins -of_objects $cell]] {
  set nets [get_nets -segments -of_objects $pin]
  puts $f "PIN $pin [get_property DIRECTION $pin]"
  puts $f "NETS $nets"
  puts $f "DRIVERS [get_pins -quiet -leaf -of_objects $nets -filter {DIRECTION == OUT}]"
 }
}
close $f
close_design
if {[lindex [exec sha256sum $checkpoint] 0] ne $expected} {error "checkpoint changed"}
puts PUBLICATION_CONE_INSPECTED_NO_SIGNOFF

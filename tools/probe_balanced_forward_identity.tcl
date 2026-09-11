# Observe the implemented comparison cone; never add timing exceptions.
if {$argc != 3 || [version -short] ne "2022.2"} {error "expected ROUTED_DCP SHA NEW_OUTPUT"}
lassign $argv checkpoint expected output
if {[file exists $output] || [lindex [exec sha256sum $checkpoint] 0] ne $expected} {error "unapproved checkpoint or existing output"}
file mkdir $output
set_param general.maxThreads 2
open_checkpoint $checkpoint
set f [open [file join $output comparator.txt] {WRONLY CREAT EXCL}]
puts $f "checkpoint_sha256=$expected"
foreach {label pattern} {
  groups *forward_buffer/capture_descriptor_groups_equal*
  tiles *forward_buffer/capture_descriptor_tiles_equal*
  final *forward_buffer/capture_descriptor_equal
} {
  set nets [get_nets -quiet -hierarchical -filter "NAME =~ $pattern"]
  puts $f "$label.nets=[llength $nets]"
  if {![llength $nets] && $label ne "final"} {close $f;error "missing implemented $label identity nets"}
  # The unkept final four-input AND may be folded into its consumer LUT.
  # All kept group/tile cones must still be observed, including their fanin.
  foreach net $nets {
    set drivers [get_pins -quiet -of_objects $net -filter {DIRECTION == OUT}]
    foreach pin $drivers {
      set driver [get_cells -quiet -of_objects $pin]
      puts $f "$label.net=[get_property NAME $net] driver=[get_property NAME $driver] ref=[get_property REF_NAME $driver]"
      set cells [all_fanin -flat -only_cells -to $pin]
      set carries [filter $cells {REF_NAME =~ CARRY*}]
      puts $f "$label.fanin_cells=[llength $cells] carries=[llength $carries]"
      if {[llength $carries]} {close $f;error "carry chain remains upstream of balanced $label comparison"}
    }
  }
}
close $f
report_timing -through [get_nets -quiet -hierarchical -filter {NAME =~ *forward_buffer/capture_descriptor_tiles_equal*}] \
  -delay_type max -max_paths 20 -file [file join $output comparator_paths.rpt]
close_design
if {[lindex [exec sha256sum $checkpoint] 0] ne $expected} {error "checkpoint changed during observation"}
puts BALANCED_FORWARD_IDENTITY_NETLIST_OBSERVED_NO_CARRY_NOT_FULL_SIGNOFF

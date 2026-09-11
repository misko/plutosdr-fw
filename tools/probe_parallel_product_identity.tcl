# Observe actual implemented comparators and the late selector path, no exceptions.
if {$argc != 3 || [version -short] ne "2022.2"} {error "expected ROUTED_DCP SHA NEW_OUTPUT"}
lassign $argv checkpoint expected output
if {[file exists $output] || [lindex [exec sha256sum $checkpoint] 0] ne $expected} {error "unapproved checkpoint or existing output"}
file mkdir $output
set_param general.maxThreads 2
open_checkpoint $checkpoint
set f [open [file join $output comparator.txt] {WRONLY CREAT EXCL}]
puts $f "checkpoint_sha256=$expected"
foreach label {held retiring} {
  set nets [get_nets -quiet -hierarchical -filter "NAME =~ *product_identity_stage/match_$label*"]
  puts $f "$label.nets=[llength $nets]"
  if {![llength $nets]} {error "missing implemented $label comparator"}
  foreach net $nets {
    set pins [get_pins -quiet -of_objects $net -filter {DIRECTION == OUT}]
    if {![llength $pins]} {error "missing comparator driver"}
    foreach pin $pins {
      set driver [get_cells -of_objects $pin]
      set cells [all_fanin -flat -only_cells -to $pin]
      puts $f "$label.driver=[get_property NAME $driver] ref=[get_property REF_NAME $driver] fanin=[llength $cells] carries=[llength [filter $cells {REF_NAME =~ CARRY*}]]"
    }
  }
}
set selectors [get_nets -quiet -hierarchical -filter {NAME =~ *product_writer_metadata_load*}]
set destinations [get_pins -quiet -hierarchical -filter {NAME =~ *product_identity_stage/output_identity_good_reg*/D}]
if {![llength $selectors] || ![llength $destinations]} {error "missing selector or certificate endpoints"}
set paths [get_timing_paths -through $selectors -to $destinations -delay_type max -max_paths 1]
if {![llength $paths]} {error "missing physical selector-to-certificate path"}
puts $f "selector.nets=[llength $selectors]"
puts $f "selector.slack=[get_property SLACK $paths]"
puts $f "selector.start=[get_property STARTPOINT_PIN $paths]"
puts $f "selector.end=[get_property ENDPOINT_PIN $paths]"
close $f
report_timing -through $selectors -to $destinations -delay_type max -max_paths 20 -file [file join $output selector_paths.rpt]
close_design
if {[lindex [exec sha256sum $checkpoint] 0] ne $expected} {error "checkpoint changed during observation"}
puts PARALLEL_PRODUCT_IDENTITY_NETLIST_OBSERVED_NOT_FULL_SIGNOFF

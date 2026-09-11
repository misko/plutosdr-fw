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
    set segments [get_nets -quiet -segments $net]
    set pins [get_pins -quiet -leaf -of_objects $segments -filter {DIRECTION == OUT}]
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
set selector_segments [get_nets -quiet -segments $selectors]
set selector_drivers [get_pins -quiet -leaf -of_objects $selector_segments -filter {DIRECTION == OUT}]
puts $f "selector.logical=$selectors"
puts $f "selector.segments=$selector_segments"
puts $f "selector.drivers=$selector_drivers"
puts $f "certificate.pins=$destinations"
foreach pin $destinations {
  set segments [get_nets -quiet -segments -of_objects $pin]
  puts $f "certificate.segments=$segments"
  set drivers [get_pins -quiet -leaf -of_objects $segments -filter {DIRECTION == OUT}]
  puts $f "certificate.drivers=$drivers"
  foreach driver $drivers {
    set cell [get_cells -of_objects $driver]
    puts $f "certificate.driver_type=[get_property REF_NAME $cell]"
    foreach input [get_pins -of_objects $cell -filter {DIRECTION == IN}] {
      puts $f "certificate.input=$input nets=[get_nets -segments -of_objects $input]"
    }
  }
}
flush $f
report_timing -to $destinations -delay_type max -max_paths 20 -file [file join $output certificate_paths.rpt]
# The optimizer factors selector terms into the final LUT; the old aggregate
# selector net need not feed it. Prove both kept comparisons reach that LUT,
# and measure ALL timing paths to the real certificate register instead.
set final_segments [get_nets -quiet -segments -of_objects $destinations]
set final_drivers [get_pins -quiet -leaf -of_objects $final_segments -filter {DIRECTION == OUT}]
if {[llength $final_drivers] != 1} {error "ambiguous final certificate driver"}
set final_cell [get_cells -of_objects $final_drivers]
if {[get_property REF_NAME $final_cell] ne "LUT6"} {error "unexpected final certificate logic"}
foreach label {held retiring} {
  set nets [get_nets -quiet -hierarchical -filter "NAME =~ *product_identity_stage/match_$label*"]
  set sinks [get_pins -quiet -leaf -of_objects [get_nets -segments $nets] -filter {DIRECTION == IN}]
  set found 0
  foreach sink $sinks {
    if {[get_cells -of_objects $sink] eq $final_cell} {set found 1}
  }
  puts $f "$label.direct_to_final_lut=$found"
  if {!$found} {error "comparison does not directly reach final certificate LUT"}
}
set old_paths [get_timing_paths -quiet -through $selector_drivers -to $destinations -delay_type max -max_paths 1]
puts $f "selector.aggregate_path_present=[llength $old_paths]"
set paths [get_timing_paths -to $destinations -delay_type max -max_paths 1]
if {[llength $paths] != 1} {error "missing certificate endpoint timing"}
puts $f "certificate.slack=[get_property SLACK $paths]"
puts $f "certificate.start=[get_property STARTPOINT_PIN $paths]"
puts $f "certificate.end=[get_property ENDPOINT_PIN $paths]"
close $f
close_design
if {[lindex [exec sha256sum $checkpoint] 0] ne $expected} {error "checkpoint changed during observation"}
puts PARALLEL_PRODUCT_IDENTITY_NETLIST_OBSERVED_NOT_FULL_SIGNOFF

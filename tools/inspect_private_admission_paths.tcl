# Read-only inspection: private fact control fan-in and original timing source.
if {$argc!=3 || [version -short] ne "2022.2"} {error "DCP SHA NEW_OUTPUT required"}
lassign $argv source_dcp expected output
if {[file exists $output] || [file pathtype $output] ne "absolute" || [lindex [exec sha256sum $source_dcp] 0] ne $expected} {error "fresh output / source pin"}
file mkdir $output
set_param general.maxThreads 2
open_checkpoint $source_dcp
set cells [get_cells -hier -regexp {^admission_gate/private_facts\.snapshot_good_reg\[[0-9]+\]$}]
if {[llength $cells]==0} {error "private fact registers missing"}
set f [open [file join $output controls.txt] {WRONLY CREAT EXCL}]
puts $f "payload_registers=[llength $cells]"
foreach cell [lsort $cells] {
  puts $f "$cell.type=[get_property REF_NAME $cell]"
  foreach pin_name {R S CLR PRE CE} {
    set pin [get_pins -quiet -of_objects $cell -filter "REF_PIN_NAME == $pin_name"]
    if {[llength $pin]==0} {continue}
    set starts [all_fanin -flat -startpoints_only -only_cells -to $pin]
    puts $f "$cell.$pin_name.startpoints=$starts"
    foreach start $starts {
      set type [get_property REF_NAME $start]
      if {$type in {GND VCC}} {continue}
      if {$pin_name eq "CE" && [regexp {^admission_gate/(snapshot_valid|consumed)_reg$} $start]} {continue}
      error "nonlocal private payload control: $pin <- $start"
    }
  }
}
close $f
set from [get_pins -hier -regexp {^slow_reset_fast_reg\[1\]/C$}]
if {[llength $from]!=1} {error "old reset source missing"}
set f [open [file join $output paths.txt] {WRONLY CREAT EXCL}]
foreach {name pattern} {payload_data {^admission_gate/private_facts\.snapshot_good_reg\[0\]/D$} payload_reset {^admission_gate/private_facts\.snapshot_good_reg\[0\]/R$} validity {^admission_gate/snapshot_valid_reg/D$} consumed {^admission_gate/consumed_reg/D$}} {
  set to [get_pins -quiet -hier -regexp $pattern]
  if {$name ne "payload_reset" && [llength $to]!=1} {error "expected endpoint missing: $name"}
  puts $f "$name.source=$from\n$name.destination=$to\n$name.pin_count=[llength $to]"
  set paths {}
  if {[llength $to]==1} {set paths [get_timing_paths -quiet -from $from -to $to -max_paths 1 -delay_type max]}
  puts $f "$name.path_count=[llength $paths]"
  if {[llength $paths]==1} {
    puts $f "$name.slack_ns=[get_property SLACK [lindex $paths 0]]"
    report_timing -from $from -to $to -max_paths 1 -delay_type max -file [file join $output ${name}.rpt]
  }
}
close $f
close_design
if {[lindex [exec sha256sum $source_dcp] 0] ne $expected} {error "checkpoint changed"}
set f [open [file join $output receipt.txt] {WRONLY CREAT EXCL}]
puts $f "source_sha256=$expected\nscript_sha256=[lindex [exec sha256sum [info script]] 0]"
puts $f "private_payload_control_local=true\nconstraints_changed=false\nphysical_signoff=false\ndeployment_eligible=false"
close $f
puts PRIVATE_ADMISSION_STRUCTURE_PASS_NOT_DEPLOYMENT_PROOF

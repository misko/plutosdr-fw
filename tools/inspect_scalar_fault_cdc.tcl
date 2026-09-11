# Require the restored one-bit registered fault source, not a waived OR tree.
if {$argc!=3 || [version -short] ne "2022.2"} {error "DCP SHA NEW_OUTPUT required"}
lassign $argv source_dcp expected output
if {[file exists $output] || [file pathtype $output] ne "absolute" || [lindex [exec sha256sum $source_dcp] 0] ne $expected} {error "fresh output / source pin"}
file mkdir $output
set_param general.maxThreads 2
open_checkpoint $source_dcp
set s0 [get_cells -hier -regexp {^fast_fault_slow_reg\[0\]$}]
set s1 [get_cells -hier -regexp {^fast_fault_slow_reg\[1\]$}]
if {[llength $s0]!=1 || [llength $s1]!=1} {error "missing fault synchronizer stages"}
foreach cell [list $s0 $s1] {
  if {[get_property ASYNC_REG $cell] ne "1"} {error "missing fault ASYNC_REG"}
}
set d0 [get_pins -of_objects $s0 -filter {REF_PIN_NAME == D}]
set starts [all_fanin -flat -startpoints_only -only_cells -to $d0]
if {[llength $starts]!=1} {error "fault crossing must have exactly one registered source"}
set src [lindex $starts 0]
if {![regexp {^fast_fault_reg.*$} $src] || ![string match "FD*" [get_property REF_NAME $src]]} {error "not the scalar fault register or its replica"}
set q [get_pins -of_objects $src -filter {REF_PIN_NAME == Q}]
if {[llength $q]!=1 || [get_nets -of_objects $q] ne [get_nets -of_objects $d0]} {error "logic before fault synchronizer"}
set q0 [get_pins -of_objects $s0 -filter {REF_PIN_NAME == Q}]
set d1 [get_pins -of_objects $s1 -filter {REF_PIN_NAME == D}]
set ends [all_fanout -flat -endpoints_only -from $q0]
if {[llength $ends]!=1 || [lindex $ends 0] ne $d1} {error "fault first-stage fanout is not isolated"}
set f [open [file join $output controls.txt] {WRONLY CREAT EXCL}]
puts $f "source=$src\ndestination=$d0\nsource_net=[get_nets -of_objects $q]\nfirst_stage_endpoints=$ends"
close $f
close_design
if {[lindex [exec sha256sum $source_dcp] 0] ne $expected} {error "checkpoint changed"}
set f [open [file join $output receipt.txt] {WRONLY CREAT EXCL}]
puts $f "source_sha256=$expected\nscript_sha256=[lindex [exec sha256sum [info script]] 0]"
puts $f "direct_registered_fault_source=true\nfirst_stage_fanout_clean=true"
puts $f "constraints_changed=false\nphysical_signoff=false\ndeployment_eligible=false"
close $f
puts SCALAR_FAULT_CDC_STRUCTURE_PASS_NOT_PHYSICAL_SIGNOFF

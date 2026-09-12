if {$argc != 2} {error "expected DCP SHA"}
lassign $argv checkpoint expected
if {[lindex [exec sha256sum $checkpoint] 0] ne $expected} {error "checkpoint mismatch"}
set_param general.maxThreads 2
open_checkpoint $checkpoint
foreach pattern {*result_guard/*fault_reasons*/D *admission_gate/*snapshot*/D *result_guard/*active_private*/D} {
 puts "PATTERN $pattern"
 foreach p [lsort [get_pins -quiet -hierarchical -filter "NAME =~ $pattern"]] {
  puts "REAL_PIN $p CELL [get_property REF_NAME [get_cells -of_objects $p]]"
 }
}
close_design
if {[lindex [exec sha256sum $checkpoint] 0] ne $expected} {error "checkpoint changed"}
puts PIN_ENUMERATION_COMPLETE

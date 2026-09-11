# Read-only query of every synthesized FFT status payload bit to publication.
if {$argc!=3 || [version -short] ne "2022.2"} {error "DCP SHA NEW_OUTPUT required"}
lassign $argv source_dcp expected output
if {[file exists $output] || [file pathtype $output] ne "absolute" || [lindex [exec sha256sum $source_dcp] 0] ne $expected} {error "fresh output / source pin"}
file mkdir $output
set_param general.maxThreads 2
open_checkpoint $source_dcp
set cells [get_cells -hier -regexp {^shared_xfft/U0/i_synth/axi_wrapper/gen_status_channel\.status_fifo/gen_real_time\.data_out_reg\[[0-9]+\]$}]
set old_source [get_pins -hier -regexp {^shared_xfft/U0/i_synth/axi_wrapper/gen_status_channel\.status_fifo/gen_real_time\.data_out_reg\[0\]/C$}]
set to [get_pins -hier -regexp {^output_bank/request_toggle_reg/D$}]
if {[llength $cells]==0 || [llength $old_source]!=1 || [llength $to]!=1} {error "expected actual FFT/publication endpoints missing"}
set f [open [file join $output paths.txt] {WRONLY CREAT EXCL}]
puts $f "status_registers=[llength $cells]\noriginal_source=$old_source\ndestination=$to"
set index 0
foreach cell [lsort $cells] {
  set from [get_pins -of_objects $cell -filter {REF_PIN_NAME == C}]
  if {[llength $from]!=1} {error "status register clock missing"}
  set paths [get_timing_paths -quiet -from $from -to $to -max_paths 1 -delay_type max]
  puts $f "bit$index.source=$from\nbit$index.path_count=[llength $paths]"
  if {[llength $paths]==1} {
    puts $f "bit$index.slack_ns=[get_property SLACK [lindex $paths 0]]"
    report_timing -from $from -to $to -max_paths 1 -delay_type max -file [file join $output bit${index}.rpt]
  }
  incr index
}
close $f
close_design
if {[lindex [exec sha256sum $source_dcp] 0] ne $expected} {error "checkpoint changed"}
set f [open [file join $output receipt.txt] {WRONLY CREAT EXCL}]
puts $f "source_sha256=$expected\nscript_sha256=[lindex [exec sha256sum [info script]] 0]"
puts $f "constraints_changed=false\nphysical_signoff=false\ndeployment_eligible=false"
close $f
puts REPLAY_FENCE_PATHS_RECORDED_NOT_DEPLOYMENT_PROOF

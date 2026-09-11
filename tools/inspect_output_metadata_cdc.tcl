# Read-only routed-checkpoint inspection. No constraints, placement or routing.
if {$argc != 3 || [version -short] ne "2022.2"} {error "expected Vivado2022.2 DCP SHA NEW_OUTPUT"}
lassign $argv source_dcp expected output
if {[file pathtype $source_dcp] ne "absolute" || [file pathtype $output] ne "absolute" || [file exists $output]} {error "absolute source and fresh output required"}
if {[lindex [exec sha256sum $source_dcp] 0] ne $expected} {error "checkpoint pin"}
set_param general.maxThreads 2
file mkdir $output
open_checkpoint $source_dcp
foreach {name period} {source_100 10.0 island_175 5.714} {
  set clock [get_clocks -quiet $name]
  if {[llength $clock]!=1 || abs([get_property PERIOD $clock]-$period)>0.00001} {error "clock pin $name"}
}
set writer_cells [get_cells -hier -regexp {^output_bank/metadata_in_hold_reg\[[0-9]+\]$}]
set reader_cells [get_cells -hier -regexp {^output_bank/metadata_out_hold_reg\[[0-9]+\]$}]
if {[llength $writer_cells]!=37 || [llength $reader_cells]!=37} {error "expected all 37 metadata registers per domain"}
set inventory [open [file join $output paths.tsv] {WRONLY CREAT EXCL}]
puts $inventory "bit\tsource\tdestination\tsource_clock\tdestination_clock\tdata_delay_ns\tslack_ns"
for {set bit 0} {$bit<37} {incr bit} {
  set src [get_cells -hier -regexp [format {^output_bank/metadata_in_hold_reg\[%d\]$} $bit]]
  set dst [get_cells -hier -regexp [format {^output_bank/metadata_out_hold_reg\[%d\]$} $bit]]
  if {[llength $src]!=1 || [llength $dst]!=1} {error "missing or duplicate metadata bit $bit"}
  set q [get_pins -of_objects $src -filter {REF_PIN_NAME == Q}]
  set d [get_pins -of_objects $dst -filter {REF_PIN_NAME == D}]
  set source_clock [get_clocks -of_objects [get_pins -of_objects $src -filter {REF_PIN_NAME == C}]]
  set destination_clock [get_clocks -of_objects [get_pins -of_objects $dst -filter {REF_PIN_NAME == C}]]
  if {$source_clock ne "island_175" || $destination_clock ne "source_100"} {error "unexpected bit clocks"}
  set paths [get_timing_paths -quiet -from $q -to $d -max_paths 1 -delay_type max]
  if {[llength $paths]!=1} {error "missing timed crossing $bit"}
  set report [report_timing -from $q -to $d -max_paths 1 -delay_type max -return_string]
  set f [open [file join $output bit_${bit}_max.rpt] {WRONLY CREAT EXCL}];puts $f $report;close $f
  if {![regexp {Data Path Delay:\s*([0-9.]+)ns} $report unused delay]} {error "missing datapath delay"}
  puts $inventory "$bit\t$q\t$d\t$source_clock\t$destination_clock\t$delay\t[get_property SLACK [lindex $paths 0]]"
}
close $inventory
# Record the actual control synchronizers and capture enable fan-in. This is
# implementation evidence, not a metastability/MTBF or handshake proof.
set f [open [file join $output controls.txt] {WRONLY CREAT EXCL}]
foreach name {request_sync acknowledge_sync} {
  for {set bit 0} {$bit<2} {incr bit} {
    set cell [get_cells -hier -regexp [format {^output_bank/%s_reg\[%d\]$} $name $bit]]
    if {[llength $cell]!=1 || [get_property ASYNC_REG $cell] ne "1"} {error "missing ASYNC_REG control stage $name $bit"}
    puts $f "$name.$bit.cell=$cell"
    puts $f "$name.$bit.clock=[get_clocks -of_objects [get_pins -of_objects $cell -filter {REF_PIN_NAME == C}]]"
    puts $f "$name.$bit.input_starts=[all_fanin -flat -startpoints_only -to [get_pins -of_objects $cell -filter {REF_PIN_NAME == D}]]"
  }
}
set capture [get_cells -hier -regexp {^output_bank/metadata_out_hold_reg\[0\]$}]
puts $f "capture_enable_starts=[all_fanin -flat -startpoints_only -to [get_pins -of_objects $capture -filter {REF_PIN_NAME == CE}]]"
close $f
report_cdc -details -file [file join $output cdc.rpt]
report_exceptions -file [file join $output exceptions.rpt]
report_clock_interaction -file [file join $output clocks.rpt]
close_design
if {[lindex [exec sha256sum $source_dcp] 0] ne $expected} {error "checkpoint changed"}
puts OUTPUT_METADATA_CDC_INSPECTION_PASS_NO_CONSTRAINT_OR_DEPLOYMENT_CHANGE

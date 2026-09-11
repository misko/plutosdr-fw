# Standalone memory/controller cost only, not integrated FFT timing closure.
if {$argc!=3 || [version -short] ne "2022.2"} {error "SOURCE SHA NEW_OUTPUT required"}
lassign $argv source expected output
if {[file exists $output] || [file pathtype $output] ne "absolute" || [lindex [exec sha256sum $source] 0] ne $expected} {error "fresh output / source pin"}
file mkdir $output
file copy [info script] [file join $output runner.tcl]
set runner_sha [lindex [exec sha256sum [info script]] 0]
set_param general.maxThreads 2
read_verilog -sv $source
synth_design -top starlink_pss_forward_return_bank -part xc7z010clg400-1 -mode out_of_context -flatten_hierarchy rebuilt -directive AreaOptimized_high -control_set_opt_threshold 4
create_clock -name island_175 -period 5.714 [get_ports clk]
write_checkpoint [file join $output synthesized.dcp]
opt_design
place_design
phys_opt_design
route_design
write_checkpoint [file join $output routed.dcp]
report_utilization -file [file join $output utilization.rpt]
report_route_status -file [file join $output route_status.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -max_paths 20 -file [file join $output timing_unqualified.rpt]
report_timing -from [get_clocks island_175] -to [get_clocks island_175] -max_paths 20 -file [file join $output internal_paths.rpt]
report_exceptions -file [file join $output exceptions.rpt]
write_xdc [file join $output constraints.xdc]
if {[llength [get_cells -quiet -hier -filter {IS_BLACKBOX == 1}]]} {error "black box"}
set rams [get_cells -hier -filter {REF_NAME == RAMB18E1}]
if {[llength $rams]!=1 || [llength [get_cells -hier -filter {REF_NAME == RAMB36E1}]]!=0} {error "payload must fit exactly one RAMB18"}
set starts [all_fanin -flat -startpoints_only -to [get_ports capture_ready]]
if {[llength $starts]==0 || [lsearch -exact $starts output_ready]>=0} {error "capture capacity depends combinationally on replay READY"}
set write_pins [get_pins -of_objects $rams -filter {REF_PIN_NAME =~ WE*}]
if {[llength $write_pins]==0} {error "RAM write enable not found"}
foreach pin $write_pins {
  if {[lsearch -exact [all_fanin -flat -startpoints_only -to $pin] output_ready]>=0} {error "RAM write control depends on replay READY"}
}
set f [open [file join $output structure.txt] {WRONLY CREAT EXCL}]
puts $f "ram_cells=$rams\nwrite_pins=$write_pins\ncapture_ready_startpoints=$starts"
close $f
close_design
if {[lindex [exec sha256sum $source] 0] ne $expected || [lindex [exec sha256sum [info script]] 0] ne $runner_sha} {error "source or runner changed"}
set f [open [file join $output receipt.txt] {WRONLY CREAT EXCL}]
puts $f "source_sha256=$expected\nscript_sha256=$runner_sha"
puts $f "routed_dcp_sha256=[lindex [exec sha256sum [file join $output routed.dcp]] 0]"
puts $f "ramb18=1\ncapture_ready_decoupled=true\nram_write_decoupled=true"
puts $f "standalone_only=true\nreceiver_integration=false\nphysical_signoff=false\ndeployment_eligible=false"
close $f
puts FORWARD_RETURN_BANK_ROUTE_RECORDED_NOT_RECEIVER_SIGNOFF

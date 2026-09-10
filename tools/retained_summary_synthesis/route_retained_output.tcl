# Exact separately approved synthesized DCP. No source selection or timing waiver.
if {$argc != 3 || [version -short] ne "2022.2"} { error "expected Vivado2022.2 SOURCE_DCP EXPECTED_SHA NEW_OUTPUT" }
lassign $argv source_dcp expected output
foreach requested [list $source_dcp $output [info script]] {
  if {[file pathtype $requested] ne "absolute" || [lsearch -exact [file split $requested] ..]>=0} { error "absolute lexical paths required" }
  set p $requested
  while {1} {
    if {![catch {file type $p} kind] && $kind eq "link"} { error "symlink path forbidden" }
    set parent [file dirname $p];if {$parent eq $p} { break };set p $parent
  }
}
if {[file exists $output]} { error "refusing route overwrite" }
if {![regexp {^[0-9a-f]{64}$} $expected] || [lindex [exec sha256sum $source_dcp] 0] ne $expected} { error "unapproved source DCP identity" }
set runner_sha [lindex [exec sha256sum [info script]] 0]
file mkdir $output
set routed [file join $output retained_output_routed.dcp]
set routed_sha ""
set_param general.maxThreads 2
set status [catch {
  file copy [info script] [file join $output probe.tcl]
  open_checkpoint $source_dcp
  if {[llength [get_cells -quiet -hier -filter {IS_BLACKBOX == 1}]]} { error "black box in qualified runtime" }
  foreach {name period} {source_100 10.0 island_175 5.714} {
    set clock [get_clocks -quiet $name]
    if {[llength $clock]!=1 || abs([get_property PERIOD $clock]-$period)>0.00001} { error "unexpected inherited clock $name" }
  }
  opt_design
  place_design
  phys_opt_design
  route_design
  # Preserve exact routed artifact before an observational report can fail.
  write_checkpoint $routed
  set routed_sha [lindex [exec sha256sum $routed] 0]
  set f [open [file join $output dcp_receipt.txt] {WRONLY CREAT EXCL}]
  puts $f "source_dcp_sha256=$expected\nrouted_dcp_sha256=$routed_sha\nrunner_sha256=$runner_sha";close $f
  report_route_status -file [file join $output route_status.rpt]
  report_utilization -file [file join $output utilization.rpt]
  report_utilization -hierarchical -hierarchical_depth 6 -file [file join $output hierarchy.rpt]
  report_clocks -file [file join $output clocks.rpt]
  write_xdc [file join $output inherited_constraints.xdc]
  report_clock_interaction -file [file join $output clock_interaction.rpt]
  report_exceptions -file [file join $output exceptions.rpt]
  report_timing_summary -delay_type min_max -report_unconstrained -max_paths 20 -file [file join $output timing_unqualified.rpt]
  check_timing -verbose -file [file join $output check_timing_unqualified.rpt]
  report_cdc -details -file [file join $output cdc_unqualified.rpt]
  set f [open [file join $output paths.txt] {WRONLY CREAT EXCL}]
  puts $f "scope=exact_retained_output_100_175_OOC_diagnostic\nblack_boxes=0\ntiming_qualified=false\ndeployment_eligible=false"
  foreach from {source_100 island_175} {
    foreach to {source_100 island_175} {
      foreach kind {max min} {
        set paths [get_timing_paths -quiet -from [get_clocks $from] -to [get_clocks $to] -delay_type $kind -max_paths 20]
        puts $f "$from.$to.$kind.reported_paths=[llength $paths]"
        if {[llength $paths]>0} {
          set path [lindex $paths 0]
          puts $f "$from.$to.$kind.slack=[get_property SLACK $path]"
          puts $f "$from.$to.$kind.start=[get_property STARTPOINT_PIN $path]"
          puts $f "$from.$to.$kind.end=[get_property ENDPOINT_PIN $path]"
        } elseif {$from eq $to} { close $f;error "missing internal timing path $from $kind" }
        report_timing -from [get_clocks $from] -to [get_clocks $to] -delay_type $kind -max_paths 20 -file [file join $output ${from}_${to}_${kind}.rpt]
      }
    }
  }
  close $f
  close_design
} result options]
set after_status [catch {
  if {[lindex [exec sha256sum $source_dcp] 0] ne $expected} { error "source DCP changed during observation" }
  foreach path [list [info script] [file join $output probe.tcl]] {
    if {[lindex [exec sha256sum $path] 0] ne $runner_sha} { error "route runner changed" }
  }
  if {$routed_sha ne "" && [lindex [exec sha256sum $routed] 0] ne $routed_sha} { error "routed DCP changed during observations" }
} after_result after_options]
set f [open [file join $output run_outcome.txt] {WRONLY CREAT EXCL}]
puts $f "run_status=$status\nrun_result=$result\nrun_options=$options\nafter_status=$after_status\nafter_result=$after_result\nafter_options=$after_options";close $f
if {$status} { return -options $options $result }
if {$after_status} { return -options $after_options $after_result }
puts RETAINED_OUTPUT_ROUTE_OBSERVATIONS_RECORDED_NOT_A_PHYSICAL_RELEASE_PASS

# Exact offered-summary runtime; unbound until reviewed original actual success. Synthesis only; no route or timing waiver.
if {$argc != 2 || [version -short] ne "2022.2"} { error "expected Vivado2022.2 PREPARED_SHA NEW_OUTPUT" }
lassign $argv expected output
set prepared [file dirname [info script]]
if {[file tail [info script]] ne "synthesize_retained_summary.tcl"} { error "exact frozen runner filename required" }
foreach requested [list $prepared $output] {
  if {[file pathtype $requested] ne "absolute" || [lsearch -exact [file split $requested] ..]>=0} { error "absolute lexical paths required" }
  set p $requested
  while {1} {
    if {![catch {file type $p} kind] && $kind eq "link"} { error "symlink path forbidden" }
    set parent [file dirname $p];if {$parent eq $p} { break };set p $parent
  }
}
if {[string first "[file normalize $prepared]/" "[file normalize $output]/"]==0} { error "output must be outside prepared inputs" }
if {[file exists $output]} { error "refusing synthesis overwrite" }
if {![regexp {^[0-9a-f]{64}$} $expected] || [lindex [exec sha256sum [file join $prepared SHA256SUMS]] 0] ne $expected} { error "prepared source identity" }
proc check_prepared {prepared} {
  set saved [pwd];cd $prepared
  set failed [catch {exec sha256sum -c SHA256SUMS --quiet} message options]
  cd $saved
  if {$failed} { return -options $options $message }
}
check_prepared $prepared
set python /home/mouse9911/.local/share/uv/python/cpython-3.11.16-linux-x86_64-gnu/bin/python3.11
if {[lindex [exec sha256sum $python] 0] ne "2874a0b9344d06b7767aebb1e6e25a759ffcbdb544e99400ecc74dc6092d1174"} { error "tested Python identity" }
set qualified [file join $prepared qualified]
set cli [file join $qualified source_snapshot tools prepare_starlink_retained_summary_actual.py]
set qualified_sha UNBOUND_PENDING_ACCEPTED_SUMMARY_ACTUAL
if {![regexp {^[0-9a-f]{64}$} $qualified_sha]} { error "unbound reviewed actual source" }
set py [list env -u PYTHONHOME -u PYTHONPATH -u PYTHONOPTIMIZE -u LD_LIBRARY_PATH $python -B $cli]
puts [exec {*}$py verify $qualified --expected $qualified_sha --live]
file mkdir $output
set inputs [file join $output inputs]
set wrapper "";set generated_before "";set dcp_sha ""
set_param general.maxThreads 2
set status [catch {
  file copy $qualified $inputs
  foreach name {synthesize_retained_summary.tcl clocks.xdc threads.tcl SHA256SUMS} {
    file copy [file join $prepared $name] [file join $output $name]
  }
  puts [exec {*}$py verify $inputs --expected $qualified_sha --live]
  source [file join $inputs profile.tcl]
  set rtl_names {}
  foreach name $compiled_names {
    if {([string match */retained_output/*.v $name] || [string match */retained_output_summary_candidate/*.v $name]) && ![string match */tb/* $name]} { lappend rtl_names $name }
  }
  if {[llength $rtl_names] != 16} { error "exact16 runtime required" }
  set kernels [lsearch -all -inline -glob $vector_names */upper_edge_pss_kernel_q17.mem]
  if {[llength $kernels] != 1} { error "exact kernel required" }
  set kernel [file join $inputs [lindex $kernels 0]]
  set project [file join $output project]
  create_project retained_output_synthesis $project -part xc7z010clg400-1
  set_property target_language Verilog [current_project]
  source [file join $inputs source_snapshot hdl library starlink_pss_acquisition retained_output_actual reference create_shared_realtime_xfft_ip.tcl]
  set wrapper [file join $project retained_output_synthesis.gen sources_1 ip starlink_pss_fft512_bfp18_rt_candidate synth starlink_pss_fft512_bfp18_rt_candidate.vhd]
  pss_create_shared_realtime_xfft_ip $wrapper
  set generated_before [exec sha256sum $wrapper]
  if {[lindex $generated_before 0] ne "a3a650654118016012bdfb8553114ee4a89866466d8ca774fa0f281640168a68"} { error "qualified generated wrapper changed" }
  set f [open [file join $output generated_ip_before.txt] {WRONLY CREAT EXCL}];puts $f $generated_before;close $f
  foreach name $rtl_names {
    set compiled_file [file join $inputs $name]
    add_files -fileset sources_1 -norecurse $compiled_file
    set_property file_type SystemVerilog [get_files -of_objects [get_filesets sources_1] $compiled_file]
  }
  add_files -fileset constrs_1 -norecurse [file join $output clocks.xdc]
  set_property top starlink_pss_fft_bank_owned_retained_output_probe [get_filesets sources_1]
  set generics [list KERNEL_ROM_FILE=$kernel ENABLE_RETAINED_OUTPUT=1 REGISTERED_SCHEDULING=1 BOUNDARY_ROUND_SAT=1 REGISTER_OPERANDS=1 LOCAL_FIRST_ADMISSION=1 PRIVATE_DESCRIPTOR_OFFER=1 CLOSED_INPUT_CUTOVER=1 INPUT_OFFER_FAULT_SUMMARY=1]
  set_property generic $generics [get_filesets sources_1]
  if {[get_property GENERIC [get_filesets sources_1]] ne $generics} { error "exact retained/R1/B1/O1/L1/private-offer/closed-input/offered-summary generics" }
  set_property STEPS.SYNTH_DESIGN.ARGS.FLATTEN_HIERARCHY rebuilt [get_runs synth_1]
  set_property STEPS.SYNTH_DESIGN.ARGS.DIRECTIVE AreaOptimized_high [get_runs synth_1]
  set_property -dict [list {STEPS.SYNTH_DESIGN.ARGS.MORE OPTIONS} {-mode out_of_context}] [get_runs synth_1]
  create_ip_run [get_ips starlink_pss_fft512_bfp18_rt_candidate]
  set ip_run [get_runs starlink_pss_fft512_bfp18_rt_candidate_synth_1]
  set_property strategy Flow_AreaOptimized_high $ip_run
  foreach run [list $ip_run [get_runs synth_1]] {
    set_property STEPS.SYNTH_DESIGN.ARGS.CONTROL_SET_OPT_THRESHOLD 4 $run
    set_property STEPS.SYNTH_DESIGN.TCL.PRE [file join $output threads.tcl] $run
  }
  set f [open [file join $output effective_profile.txt] {WRONLY CREAT EXCL}]
  puts $f "top=starlink_pss_fft_bank_owned_retained_output_probe\ngenerics=$generics\nruntime_files=$rtl_names\nprepared_sha=$expected\nqualified_sha=$qualified_sha\npart=xc7z010clg400-1\nthreads=2\nOOC=true\nroute_invoked=false";close $f
  launch_runs $ip_run -jobs 2;wait_on_run $ip_run
  if {[get_property STATUS $ip_run] ne "synth_design Complete!"} { error "FFT synthesis failed" }
  launch_runs synth_1 -jobs 2;wait_on_run synth_1
  if {[get_property STATUS [get_runs synth_1]] ne "synth_design Complete!"} { error "retained synthesis failed" }
  open_run synth_1
  if {[llength [get_cells -quiet -hier -filter {IS_BLACKBOX == 1}]]} { error "black box in complete runtime" }
  foreach {name period} {source_100 10.0 island_175 5.714} {
    set clock [get_clocks -quiet $name]
    if {[llength $clock] != 1 || abs([get_property PERIOD $clock]-$period)>0.00001} { error "unexpected effective clock $name" }
  }
  write_checkpoint [file join $output retained_output_synth.dcp]
  set dcp_sha [lindex [exec sha256sum [file join $output retained_output_synth.dcp]] 0]
  set f [open [file join $output dcp_receipt.txt] {WRONLY CREAT EXCL}];puts $f "retained_output_synth.dcp.sha256=$dcp_sha";close $f
  report_utilization -file [file join $output utilization.rpt]
  report_utilization -hierarchical -hierarchical_depth 6 -file [file join $output hierarchy.rpt]
  report_clocks -file [file join $output clocks.rpt]
  set f [open [file join $output constraint_inputs.txt] {WRONLY CREAT EXCL}]
  foreach constraint [get_files -all -quiet *.xdc] {
    if {![file isfile $constraint]} { close $f;error "effective XDC file missing: $constraint" }
    puts $f "path=$constraint\nsha256=[lindex [exec sha256sum $constraint] 0]"
    set properties [list_property $constraint]
    foreach property {SCOPED_TO_REF SCOPED_TO_CELLS USED_IN USED_IN_SYNTHESIS USED_IN_IMPLEMENTATION IS_ENABLED PROCESSING_ORDER} {
      if {[lsearch -exact $properties $property]>=0} { puts $f "$property=[get_property $property $constraint]" } else { puts $f "$property=<not defined>" }
    }
  }
  close $f
  write_xdc [file join $output inherited_constraints.xdc]
  report_clock_interaction -file [file join $output clock_interaction.rpt]
  report_exceptions -file [file join $output exceptions.rpt]
  report_timing_summary -delay_type min_max -report_unconstrained -max_paths 20 -file [file join $output timing_unqualified.rpt]
  check_timing -verbose -file [file join $output check_timing_unqualified.rpt]
  report_cdc -details -file [file join $output cdc_unqualified.rpt]
  set f [open [file join $output resource_and_paths.txt] {WRONLY CREAT EXCL}]
  puts $f "black_boxes=0\nsynthesis_only=true\ntiming_qualified=false\ndeployment_eligible=false"
  foreach {label ref} {dsp48e1 DSP48E1 ramb18e1 RAMB18E1 ramb36e1 RAMB36E1} {
    puts $f "$label=[llength [get_cells -quiet -hier -filter REF_NAME==$ref]]"
  }
  foreach from {source_100 island_175} {
    foreach to {source_100 island_175} {
      foreach kind {max min} {
        set paths [get_timing_paths -quiet -from [get_clocks $from] -to [get_clocks $to] -delay_type $kind -max_paths 20]
        puts $f "$from.$to.$kind.reported_paths=[llength $paths]"
        report_timing -from [get_clocks $from] -to [get_clocks $to] -delay_type $kind -max_paths 20 -file [file join $output ${from}_${to}_${kind}.rpt]
      }
    }
  }
  close $f
  close_project
} result options]
set ip_status [catch {
  set f [open [file join $output generated_ip_after.txt] {WRONLY CREAT EXCL}]
  if {$wrapper ne "" && [file isfile $wrapper]} {
    set generated_after [exec sha256sum $wrapper];puts $f $generated_after
    if {$generated_before eq "" || $generated_before ne $generated_after} { close $f;error "generated IP changed" }
  } else { puts $f not_generated;if {$generated_before ne ""} { close $f;error "generated IP vanished" } }
  close $f
} ip_result ip_options]
set after_status [catch {
  check_prepared $prepared
  foreach name {synthesize_retained_summary.tcl clocks.xdc threads.tcl SHA256SUMS} {
    if {[lindex [exec sha256sum [file join $prepared $name]] 0] ne [lindex [exec sha256sum [file join $output $name]] 0]} { error "copied synthesis asset changed" }
  }
  puts [exec {*}$py verify $qualified --expected $qualified_sha --live]
  puts [exec {*}$py verify $inputs --expected $qualified_sha --live]
  if {$dcp_sha ne "" && [lindex [exec sha256sum [file join $output retained_output_synth.dcp]] 0] ne $dcp_sha} { error "generated DCP changed after synthesis" }
} after_result after_options]
set f [open [file join $output run_outcome.txt] {WRONLY CREAT EXCL}]
puts $f "run_status=$status\nrun_result=$result\nrun_options=$options\nip_status=$ip_status\nip_result=$ip_result\nafter_status=$after_status\nafter_result=$after_result";close $f
if {$status} { return -options $options $result }
if {$ip_status} { return -options $ip_options $ip_result }
if {$after_status} { return -options $after_options $after_result }
puts RETAINED_SUMMARY_SYNTHESIS_RECORDED_NOT_TIMING_OR_DEPLOYMENT_PASS

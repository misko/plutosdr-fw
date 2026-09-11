# Experimental actual generated FFT and same-constraint subsystem synthesis.
# A successful command is not routed timing closure or a receiver release.
if {$argc!=4 || [version -short] ne "2022.2"} {error "Vivado2022.2 MODE PREPARED SHA OUTPUT required"}
lassign $argv mode inputs expected output
if {$mode ni {sim ack synth}} {error "explicit experiment mode required"}
if {[lindex [exec sha256sum [file join $inputs SHA256SUMS]] 0] ne $expected} {error "source inventory identity"}
set saved [pwd];cd $inputs;exec sha256sum -c SHA256SUMS --quiet;cd $saved
set_param general.maxThreads 2
source [file join $inputs profile.tcl]
create_project staged_fft [file join $output project] -part xc7z010clg400-1
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]
source [file join $inputs create_shared_realtime_xfft_ip.tcl]
set wrapper [file join $output project staged_fft.gen sources_1 ip starlink_pss_fft512_bfp18_rt_candidate synth starlink_pss_fft512_bfp18_rt_candidate.vhd]
pss_create_shared_realtime_xfft_ip $wrapper
set wrapper_sha [lindex [exec sha256sum $wrapper] 0]
if {$wrapper_sha ne "a3a650654118016012bdfb8553114ee4a89866466d8ca774fa0f281640168a68"} {error "generated FFT changed"}
set channel [open [file join $output generated_fft.sha256] {WRONLY CREAT EXCL}];puts $channel $wrapper_sha;close $channel
foreach name $runtime_names {
  add_files -fileset sources_1 -norecurse [file join $inputs $name]
  set_property file_type SystemVerilog [get_files [file join $inputs $name]]
}
if {$mode in {sim ack}} {
  add_files -fileset sim_1 -norecurse [file join $inputs tb_fft_staged_output.sv]
  foreach name $vector_names {add_files -fileset sim_1 -norecurse [file join $inputs $name]}
  set_property file_type {Memory Initialization Files} [get_files -of_objects [get_filesets sim_1] *.mem]
  set_property top [expr {$mode eq "ack" ? "tb_ack_only" : "tb"}] [get_filesets sim_1]
  set_property xsim.simulate.runtime all [get_filesets sim_1]
  set_property xsim.simulate.custom_tcl [file join $inputs run_retained_output_actual.tcl] [get_filesets sim_1]
  launch_simulation -simset sim_1 -mode behavioral
  close_sim
} else {
  add_files -fileset constrs_1 -norecurse [file join $inputs clocks.xdc]
  set_property top starlink_pss_fft_staged_output_impl [get_filesets sources_1]
  set generics [list KERNEL_ROM_FILE=[file join $inputs upper_edge_pss_kernel_q17.mem] REGISTERED_SCHEDULING=1 BOUNDARY_ROUND_SAT=1 REGISTER_OPERANDS=1 LOCAL_FIRST_ADMISSION=1 PRIVATE_DESCRIPTOR_OFFER=1 CLOSED_INPUT_CUTOVER=1 INPUT_OFFER_FAULT_SUMMARY=1 CONTEXTUAL_DESTINATION_SUMMARY=1 REPLAY_QUIET_PUBLICATION=1 PRIVATE_QUARANTINE_OFFER=1 SPLIT_PREFLIGHT_IDENTITY=1]
  set_property generic $generics [get_filesets sources_1]
  set_property STEPS.SYNTH_DESIGN.ARGS.FLATTEN_HIERARCHY rebuilt [get_runs synth_1]
  set_property STEPS.SYNTH_DESIGN.ARGS.DIRECTIVE AreaOptimized_high [get_runs synth_1]
  set_property -dict [list {STEPS.SYNTH_DESIGN.ARGS.MORE OPTIONS} {-mode out_of_context}] [get_runs synth_1]
  create_ip_run [get_ips starlink_pss_fft512_bfp18_rt_candidate]
  set ip_run [get_runs starlink_pss_fft512_bfp18_rt_candidate_synth_1]
  set_property strategy Flow_AreaOptimized_high $ip_run
  foreach run [list $ip_run [get_runs synth_1]] {
    set_property STEPS.SYNTH_DESIGN.ARGS.CONTROL_SET_OPT_THRESHOLD 4 $run
    set_property STEPS.SYNTH_DESIGN.TCL.PRE [file join $inputs threads.tcl] $run
  }
  launch_runs $ip_run -jobs 2;wait_on_run $ip_run
  if {[get_property STATUS $ip_run] ne "synth_design Complete!"} {error "FFT synthesis failed"}
  launch_runs synth_1 -jobs 2;wait_on_run synth_1
  if {[get_property STATUS [get_runs synth_1]] ne "synth_design Complete!"} {error "subsystem synthesis failed"}
  open_run synth_1
  if {[llength [get_cells -quiet -hier -filter {IS_BLACKBOX == 1}]]} {error "black box in subsystem"}
  write_checkpoint [file join $output staged_output_synth.dcp]
  report_utilization -file [file join $output utilization.rpt]
  report_utilization -hierarchical -hierarchical_depth 6 -file [file join $output hierarchy.rpt]
  report_clocks -file [file join $output clocks.rpt]
  report_timing_summary -delay_type min_max -report_unconstrained -max_paths 20 -file [file join $output timing_unqualified.rpt]
  check_timing -verbose -file [file join $output check_timing_unqualified.rpt]
  report_cdc -details -file [file join $output cdc_unqualified.rpt]
  report_exceptions -file [file join $output exceptions.rpt]
  write_xdc [file join $output inherited_constraints.xdc]
}
if {[lindex [exec sha256sum $wrapper] 0] ne $wrapper_sha} {error "generated FFT changed during execution"}
set saved [pwd];cd $inputs;exec sha256sum -c SHA256SUMS --quiet;cd $saved
close_project
puts "STAGED_FFT_EXPERIMENT_FINISHED mode=$mode no_receiver_or_deployment_claim"

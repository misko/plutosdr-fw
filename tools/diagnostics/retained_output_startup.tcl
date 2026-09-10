# Diagnostic only: unchanged design/stimulus/assertions; never a numerical PASS.
# Run solely in a new parent-approved owner directory with copied frozen inputs.
# Exact escaped hierarchy discovered in the original tb_behav snapshot.
set island {/tb/dut/\retained.island }
set names {}
foreach name {
  fft_clk clk resetn fft_resetn fast_cycles actual_jobs actual_commits
  payload_checks payload_join_occupied payload_product_occupied
  forward_checks forward_cycles
} { lappend names /tb/$name }
foreach name {
  fast_running slow_running state core_release core_aresetn
  job_valid job_ready job_accept config_valid config_ready
  completion_accept completion_receipt any_fast_fault external_fault_now
  cutover_reasons cutover_fault_now guard_fault
  core_input_valid core_input_ready certified_input_beat certified_input_complete
  core_output_valid core_status_valid event_frame
  event_last_unexpected event_last_missing event_input_halt
} { lappend names $island/$name }
foreach name {
  clk resetn core_resetn job_accept job_inverse producer_closed config_accept
  input_beat input_complete raw_frame raw_output raw_status raw_vendor_faults
  admission_allowed configuration_allowed fault_now routed_inverse fault_reasons
  known owner_open owner_inverse configured quiet_released reset_flushed
  fresh_frame fresh_full low_count
} { lappend names $island/cutover/$name }
if {[llength $names] != 66 || [llength [lsort -unique $names]] != 66} {
  error "startup diagnostic exact 66-object inventory"
}
# get_objects treats escaped paths as patterns. Resolve by literal equality
# against enumerated handles, then use those returned handles without rewriting.
set all_objects [get_objects -r *]
set selected {}
foreach wanted $names {
  set hits {}
  foreach object $all_objects {
    if {[string equal $object $wanted]} { lappend hits $object }
  }
  if {[llength $hits] != 1} { error "startup object missing/duplicate: $wanted" }
  lappend selected [lindex $hits 0]
}
# No recursive/wildcard wave logging and no hierarchy writes or force/release.
foreach object $selected { log_wave $object }
set values [open startup_values.tsv {WRONLY CREAT EXCL}]
puts $values "phase\tobject\tvalue"
foreach object $selected {
  puts $values "before\t$object\t[get_value -radix bin $object]"
}
flush $values
puts "RETAINED_STARTUP_DIAGNOSTIC_ONLY objects=66 bound_ns=250 expected_original_failure_cycle=31"
# Original health assertion is expected to stop at 174285723 fs before a job.
# Reaching the cap or a different assertion is an unreproduced diagnosis, not PASS.
set status [catch {run 250 ns} result options]
foreach object $selected {
  puts $values "after\t$object\t[get_value -radix bin $object]"
}
close $values
puts "RETAINED_STARTUP_DIAGNOSTIC_RETURN run_status=$status result=$result qualification=none"
if {$status} { return -options $options $result }

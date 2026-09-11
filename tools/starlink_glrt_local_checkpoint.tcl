# Convert the verified complete EDIF component to an unplaced hierarchical DCP.
# No clocks, false paths or fixture registers are added by this conversion.
if {$argc!=2 || [version -short] ne "2022.2"} { error "requires Vivado 2022.2, netlist bundle, fresh output" }
set input [file normalize [lindex $argv 0]]
set output [file normalize [lindex $argv 1]]
if {[file exists $output]} { error "output exists" }
exec bash -c {cd "$1" && sha256sum --status -c outputs.sha256} -- $input
exec sha256sum --status -c $input/source-hashes.txt
file mkdir $output
create_project -in_memory -part xc7z010clg400-1
read_edif $input/starlink_glrt_local_control.edf
link_design -top starlink_glrt_local_control -part xc7z010clg400-1 -mode out_of_context
if {[llength [get_cells -hier -filter {IS_BLACKBOX == 1}]]} { error "unresolved component cell" }
write_checkpoint $output/starlink_glrt_local_control.dcp
foreach name {starlink_glrt_local_control.edf starlink_glrt_local_control_stub.v source-hashes.txt} {
  file copy $input/$name $output/$name
}
set fd [open $output/source-hashes.txt a]
set script [file normalize [info script]]
puts $fd "[lindex [exec sha256sum $script] 0]  $script"
close $fd
set fd [open $output/outputs.sha256 {WRONLY CREAT EXCL}]
foreach name {starlink_glrt_local_control.edf starlink_glrt_local_control_stub.v starlink_glrt_local_control.dcp source-hashes.txt} {
  puts $fd "[lindex [exec sha256sum $output/$name] 0]  $name"
}
close $fd
puts "LOCAL_CONTROL_CHECKPOINT_READY_NOT_BOARD_TIMING_VERIFIED"
exit

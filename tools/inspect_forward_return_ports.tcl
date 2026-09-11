# Read-only check of the actual inferred simple-dual-port write controls.
if {$argc!=3 || [version -short] ne "2022.2"} {error "DCP SHA NEW_OUTPUT required"}
lassign $argv source expected output
if {[file exists $output] || [lindex [exec sha256sum $source] 0] ne $expected} {error "fresh output/source pin"}
file mkdir $output
set_param general.maxThreads 2
open_checkpoint $source
set ram [get_cells -hier -filter {REF_NAME == RAMB18E1}]
if {[llength $ram]!=1} {error "single RAMB18 required"}
set f [open [file join $output ports.txt] {WRONLY CREAT EXCL}]
foreach property {RAM_MODE READ_WIDTH_A READ_WIDTH_B WRITE_WIDTH_A WRITE_WIDTH_B} {
  puts $f "$property=[get_property $property $ram]"
}
if {[get_property RAM_MODE $ram] ne "SDP" || [get_property WRITE_WIDTH_B $ram]!=36} {error "expected 36-bit SDP writer B"}
set pins [get_pins -of_objects $ram -filter {REF_PIN_NAME =~ WEBWE* || REF_PIN_NAME == ENBWREN || REF_PIN_NAME =~ ADDRBWRADDR*}]
if {[llength $pins]<10} {error "missing complete write controls"}
set nonconstant 0
foreach pin $pins {
  set starts [all_fanin -quiet -flat -startpoints_only -to $pin]
  puts $f "$pin=$starts"
  if {[llength $starts]>0} {incr nonconstant}
  if {[lsearch -exact $starts output_ready]>=0} {error "writer depends combinationally on replay ready"}
}
if {$nonconstant<3} {error "vacuous write controls"}
close $f
close_design
if {[lindex [exec sha256sum $source] 0] ne $expected} {error "DCP changed"}
set f [open [file join $output receipt.txt] {WRONLY CREAT EXCL}]
puts $f "source_sha256=$expected\nscript_sha256=[lindex [exec sha256sum [info script]] 0]"
puts $f "sdp_write_controls_decoupled=true\nreceiver_integration=false\nphysical_signoff=false\ndeployment_eligible=false"
close $f
puts FORWARD_RETURN_WRITE_PORTS_DECOUPLED_NOT_INTEGRATION_SIGNOFF

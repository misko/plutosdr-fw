# Read-only mapped-design inventory. Name survival is NOT a factorization proof.
# No synthesis/optimization/constraint command is permitted in this observer.
proc pss_bank_identity_inspect {output} {
  set destination [file join $output bank_identity_mapped_inventory.txt]
  set f [open $destination {WRONLY CREAT EXCL}]
  set families [list \
    [list preflight_source {bank_local_preflight[./]banks\[0\][./]balanced}] \
    [list preflight_product {bank_local_preflight[./]banks\[1\][./]balanced}] \
    [list preflight_fallback {balanced_preflight[./]comparisons\[0\]}] \
    [list preflight_expected {balanced_preflight[./]comparisons\[1\]}] \
    [list guard_source {input_guard[./]bank_local_identity[./]banks\[0\][./]balanced}] \
    [list guard_product {input_guard[./]bank_local_identity[./]banks\[1\][./]balanced}] \
    [list guard_fallback {input_guard[./]balanced_identity}]]
  puts $f [list scope SYNTHESIZED_SOURCE_BOUND_OBSERVATION_NOT_TIMING_OR_FACTORING_PASS]
  puts $f [list generics [get_property GENERIC [get_filesets sources_1]]]
  puts $f [list factorization_verified false]
  set nets [get_nets -hier -quiet *]
  set complete 1
  set observed 0
  foreach family $families {
    lassign $family label pattern
    set selected {}
    foreach {kind width} {leaf_equal 24 group_equal 4} {
      for {set index 0} {$index<$width} {incr index} {
        set matches {}
        set expression [format {(^|[./])%s[./]%s\[%d\]$} $pattern $kind $index]
        foreach net $nets {
          if {[regexp $expression [get_property NAME $net]]} {lappend matches $net}
        }
        puts $f [list match $label $kind $index count [llength $matches] objects $matches]
        if {[llength $matches] != 1} {set complete 0}
        foreach net $matches {
          incr observed
          lappend selected $net
          puts $f [list net [get_property NAME $net] keep [get_property KEEP $net]]
          set drivers [get_pins -quiet -of_objects $net -filter {DIRECTION == OUT}]
          puts $f [list drivers $drivers]
          foreach driver $drivers {
            set cells [get_cells -quiet -of_objects $driver]
            foreach cell $cells {
              puts $f [list driver_cell $cell ref [get_property REF_NAME $cell]]
            }
          }
          # Endpoints stop at sequential boundaries; they are not all-time
          # causes, CDC proofs, or an RTL port-equivalence certificate.
          puts $f [list fanin_startpoints [all_fanin -flat -startpoints_only -to $net]]
          puts $f [list fanin_cells [all_fanin -flat -only_cells -to $net]]
          puts $f [list fanout_endpoints [all_fanout -flat -endpoints_only -from $net]]
        }
      }
    }
    set selected [lsort -unique $selected]
    if {[llength $selected]} {
      foreach kind {max min} {
        report_timing -through $selected -delay_type $kind -max_paths 5 \
          -file [file join $output bank_identity_${label}_${kind}.rpt]
      }
    } else {
      puts $f [list timing_paths $label NOT_QUERIED_NO_MATCHING_NETS]
    }
  }
  puts $f [list observed_kept_objects $observed]
  puts $f [list all_expected_kept_names_observed $complete]
  puts $f [list required_review {Both source/product cones, retained selected-metadata fallbacks, expected-product comparison, endpoint identities, merging and complete critical paths. Missing names are not evidence the unwanted path disappeared.}]
  close $f
}

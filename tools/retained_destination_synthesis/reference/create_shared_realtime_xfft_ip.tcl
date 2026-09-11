# Fixed, separately named experimental IP. Never switch the legacy IP's
# throttle scheme through an environment variable or a cached component.xml.
# The caller supplies the generated synthesis-wrapper path in its own project.
proc pss_create_shared_realtime_xfft_ip {wrapper_path} {
  if {[version -short] ne "2022.2"} { error "realtime XFFT requires Vivado 2022.2" }
  set module_name starlink_pss_fft512_bfp18_rt_candidate
  if {[llength [get_ips -quiet $module_name]]} {
    error "refusing to reuse an existing realtime XFFT IP"
  }
  create_ip -name xfft -vendor xilinx.com -library ip -version 9.1 -module_name $module_name
  set_property -dict [list \
    CONFIG.channels {1} CONFIG.transform_length {512} \
    CONFIG.target_clock_frequency {200} CONFIG.implementation_options {automatically_select} \
    CONFIG.target_data_throughput {40} CONFIG.run_time_configurable_transform_length {false} \
    CONFIG.data_format {fixed_point} CONFIG.input_width {18} CONFIG.phase_factor_width {16} \
    CONFIG.scaling_options {block_floating_point} CONFIG.rounding_modes {convergent_rounding} \
    CONFIG.aresetn {true} CONFIG.xk_index {true} CONFIG.throttle_scheme {realtime} \
    CONFIG.output_ordering {natural_order} CONFIG.cyclic_prefix_insertion {false} \
    CONFIG.memory_options_data {block_ram} CONFIG.memory_options_phase_factors {block_ram} \
    CONFIG.memory_options_reorder {block_ram} CONFIG.complex_mult_type {use_mults_resources} \
    CONFIG.butterfly_type {use_xtremedsp_slices} \
  ] [get_ips $module_name]
  generate_target all [get_ips $module_name]
  if {![file isfile $wrapper_path]} { error "missing generated realtime XFFT wrapper" }
  set channel [open $wrapper_path r]
  set wrapper [read $channel]
  close $channel
  set required_generics {
    C_S_AXIS_CONFIG_TDATA_WIDTH 8 C_S_AXIS_DATA_TDATA_WIDTH 48
    C_M_AXIS_DATA_TDATA_WIDTH 48 C_M_AXIS_DATA_TUSER_WIDTH 24 C_M_AXIS_STATUS_TDATA_WIDTH 8
    C_THROTTLE_SCHEME 0 C_CHANNELS 1 C_NFFT_MAX 9 C_ARCH 1 C_HAS_NFFT 0
    C_USE_FLT_PT 0 C_INPUT_WIDTH 18 C_TWIDDLE_WIDTH 16 C_OUTPUT_WIDTH 18
    C_HAS_SCALING 1 C_HAS_BFP 1 C_HAS_ROUNDING 1 C_HAS_ACLKEN 0 C_HAS_ARESETN 1
    C_HAS_OVFLO 0 C_HAS_NATURAL_INPUT 1 C_HAS_NATURAL_OUTPUT 1 C_HAS_CYCLIC_PREFIX 0
    C_HAS_XK_INDEX 1 C_DATA_MEM_TYPE 1 C_TWIDDLE_MEM_TYPE 1 C_BRAM_STAGES 0
    C_REORDER_MEM_TYPE 1 C_USE_HYBRID_RAM 0 C_OPTIMIZE_GOAL 0 C_CMPY_TYPE 1 C_BFLY_TYPE 1
  }
  foreach {name value} $required_generics {
    if {![regexp "${name} => ${value}(,|\n)" $wrapper]} {
      error "unexpected generated realtime XFFT generic $name"
    }
  }
  set entity_start [string first "ENTITY $module_name IS" $wrapper]
  set entity_stop [string first "END $module_name;" $wrapper]
  if {$entity_start < 0 || $entity_stop <= $entity_start} {
    error "missing generated realtime XFFT entity"
  }
  set entity [string range $wrapper $entity_start $entity_stop]
  foreach forbidden {m_axis_data_tready m_axis_status_tready event_status_channel_halt event_data_out_channel_halt} {
    if {[string first $forbidden $entity] >= 0} {
      error "unexpected realtime XFFT entity port $forbidden"
    }
  }
  return $module_name
}

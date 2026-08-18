# Two asynchronous domains: 100 MHz processor, 61.44 MHz receive (l_clk).
create_clock -period 10.000 -name s_axi_aclk [get_ports s_axi_aclk]
create_clock -period 16.276 -name l_clk      [get_ports l_clk]
set_clock_groups -asynchronous \
  -group [get_clocks s_axi_aclk] -group [get_clocks l_clk]

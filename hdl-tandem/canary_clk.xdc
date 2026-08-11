# l_clk = DATA_CLK = 2 x 30.72 MS/s = 61.44 MHz, per design contract D-1/B3
create_clock -period 16.276 -name l_clk [get_ports l_clk]

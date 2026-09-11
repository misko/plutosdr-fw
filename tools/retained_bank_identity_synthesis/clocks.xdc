# Resource-probe clocks only. No false paths, clock groups, I/O timing claim,
# CDC qualification, placement or implementation. Generated IP is unchanged.
create_clock -name source_100 -period 10.000 [get_ports clk]
create_clock -name island_175 -period 5.714285714 [get_ports fft_clk]

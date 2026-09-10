# Independent175MHz processing clock: generated candidate, not integrated

The current receiver cannot obtain a175MHz FFT clock by changing its shared
FCLK1 frequency. In HDL `aa1b2d52db4a4fd376ce77786d2201431015a83b`,
`projects/pluto/system_bd.tcl` sets FCLK0 to100MHz and FCLK1 to200MHz, connects
FCLK1 to both acquisition `fft_clk` and AD9361 `delay_clk`, and uses FCLK0 for
the CPU/pilot/DMA domain. Preserve the200MHz radio delay reference and the
independent source-rate ADC clock.

Root generated an isolated Clocking Wizard6.0 candidate with Vivado2022.2 for
xc7z010clg400-1,100MHz already-buffered input,175MHz requested output, MMCM,
BUFG output, active-low reset and a `locked` output. Generation completed
2026-09-10T01:07:31UTC with exit0. No receiver project, FPGA image or radio was
modified. This verifies an actual generated implementation configuration, not
an achieved board frequency, reset behavior, physical timing or RF calibration.

The generated primitive settings are `DIVCLK_DIVIDE=2`,
`CLKFBOUT_MULT_F=20.125`, `CLKOUT0_DIVIDE_F=5.750`, and
`CLKIN1_PERIOD=10.000ns`:100*20.125/2/5.75=175MHz. The emitted wrapper contains
one MMCME2_ADV and two BUFG instances (feedback/output), with no added input
buffer. These are generated instance counts, not measured post-route resources.
The retained failed full receiver's clock report has0/2 MMCM,0/2 PLL and3/32
BUFGCTRL used; that is an inventory, not proof of placement or routing capacity
for the new clock and its loads.

Before selecting a175MHz receiver profile:

- Add an explicit experiment-only clock source and verify actual generated
  frequency/connection. Leave the board's FCLK1/AD9361 delay reference at200MHz.
- Hold the complete island epoch reset on reset or loss of MMCM lock. Qualify
  asynchronous assertion, synchronized release in both domains, pending-bank
  purge, no stale output, loss/reacquisition and clean recovery. Existing
  ideal-clock simulations do not execute a real MMCM lock/reset lifecycle.
- Audit derived-clock relationships, buffers, jitter/uncertainty and physical
  clock resources in the complete design. The earlier isolated route explicitly
  lacks `HD.CLK_SRC`; its timing is not a replacement for this audit.
- Add exact new bank endpoints to bounded CDC constraints/audits. The existing
  shared XDC matches `transform_service/input_mailbox` and `output_mailbox`,
  not `island/source_bank` and `output_bank`; its quiet unmatched queries must
  not be interpreted as constrained crossings. Preserve descriptor hold/ACK
  contracts, first-stage bounds and ordinary second-stage timing. No blanket
  asynchronous clock groups or removal of metadata paths.
- Update the receiver's INIT/routed audits to require the actual bank-owned
  core and source/product/output ownership structures. Old exact hierarchy
  queries should fail closed until the new composition is explicitly supported.

If the final engine closes at200MHz, this extra clock may be unnecessary.
The current175MHz diagnostic still fails internal setup(-2.557ns); generating
a clock does not fix that path or qualify a full receiver build.

Archive `20260910-bank-island-clock-generation.tgz` contains the root-authored
reproducer, generation log/journal, full IP property report and scope receipt,
not generated vendor RTL or binaries. SHA256:
`99c835aac9a86456aab9db7f7cd472078e289cd89a6aef54ffe75f181e1465b8`.
Local generated-wrapper identities:

- Primitive wrapper: `ca069bc37de99c84459775ff8a21f9a04156b9fb7fc735325568d6a8bd52dc5a`
- Top wrapper: `862789262b9799660e3acde6330a38542a24e92d628b08e3530aaeec84ed22f7`
- IP properties: `76c57e709dbc093188e8284ba3fc7bd9d31678f43c8de5eff1d9df5580476d37`
- Reproducer: `d2b7e0e96fa1706611e171bfc02f484738996723c64d463169c379f21365ceff`

Local output: `/tmp/starlink-bank-route.I50MDJ/clock175-v1/`.

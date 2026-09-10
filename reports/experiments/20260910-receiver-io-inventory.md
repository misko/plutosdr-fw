# Saved receiver board-I/O gaps: identified, not waived

The read-only audit of the last full idle-admission receiver identifies the
13 missing input-delay constraints as `rx_data_in[0:11]` and `rx_frame_in`.
The two missing output-delay constraints are `enable` and `txnrx`. These are
actual board ports, not ports introduced by the new bank-owned OOC study.

Both setup and hold reports from the RX ports to their IDDR data pins show
`Slack: inf` and no path group. This is missing external launch timing, **not a
positive timing margin**. The previously reported positive internal `rx_clk`
slack does not qualify the AD9361-to-FPGA board interface. No input/output
delay, exception or clock was added by this audit.

## Exact saved design and observation

Input is the unchanged routed checkpoint:
`hdl/projects/pluto/shared-realtime-idle-admission-v1/pluto.runs/impl_1/system_top_postroute_physopt.dcp`.

```text
checkpoint SHA256 f7c337695f06dbe95e8659569f4cb7ce9f56c681efb0fc473dc58c70bd121e8e
audit TCL SHA256 8e6b3c9d833abc589bfc02b4c33cbbc121381655e5b74c17c4345b13528556a8
archive SHA256 8c9035b910e5419138667f59ffe78af7d7b55eb461efbc6689a03875110d6bce
```

The checkpoint hash is identical before and after inspection. Final audit
`/tmp/starlink-bank-route.I50MDJ/receiver-io-inventory-v2` exited zero at
03:02:39 UTC on2026-09-10. The additive helper is committed in HDL `9759cf12`.
It checks exact checkpoint identity, receiver AD9361/PS7 hierarchy, all13 RX
ports and actual delay-controller reference clock, and exports saved port,
clock, exception and unconstrained timing reports. It performs no synthesis,
placement, routing or design/constraint mutation.

Measured saved clocks:

- `rx_clk_in` supplies `rx_clk`, period16.270ns (the existing maximum-rate
  constraint, not a measurement of live sample rate).
- The actual single IDELAYCTRL is
  `i_system_wrapper/system_i/axi_ad9361/inst/i_dev_if/i_rx_frame/i_delay_ctrl`.
  Its REFCLK is `clk_fpga_1`, period5.000ns/200MHz. This must remain200MHz when
  a separate175MHz transform clock is integrated.
- All RX data/frame paths terminate in the existing receive IDDRs through
  IBUF and IDELAYE2. The audit lists each input and its actual endpoints.

The audit still reports13 missing input and2 missing output delays, with zero
missing clocks, multiple clocks or unconstrained internal endpoints. The
saved overall setup failure is unchanged: WNS−1.269ns/TNS−125.326ns,355 failing
endpoints; hold+0.002ns. That is the **older full receiver**, not the newer
isolated175MHz bank-control route's−2.438ns result.

## Reproduction and retained attempts

Run `hdl/projects/pluto/audit_receiver_io_checkpoint.tcl` with Vivado2022.2 and
three arguments: checkpoint path, exact expected SHA256, and a new output
directory. Existing evidence is rejected, including file/directory/symlink
targets. The new13 admission/preservation/source-policy tests pass; combined
with the previous bank CDC audit tests,23 pass. Ruff passes.

V1 exited1 before generating timing reports because it incorrectly expected
the in-memory design NAME to equal the HDL top name. Opening a checkpoint
instead creates `checkpoint_system_top_postroute_physopt`. V2 replaces that
incorrect name assumption with exact actual AD9361 and PS7 hierarchy checks;
it does not weaken timing or change the checkpoint. V1's frozen helper and
full log are retained alongside V2. Archive
`20260910-receiver-io-inventory.tgz` contains both attempts, final reports and
logs, but no checkpoint or vendor IP. Neither attempt is a physical pass.

## Remaining release work

1. Establish the actual selected AD9361 digital interface mode and source
   timing bounds, including programmed receive clock/data delay and supported
   calibration settings, with board clock/data skew. Use evidence-supported
   min/max timing on the correct DDR edges; do not invent zero-delay inputs or
   waive the thirteen data/frame ports.
2. Establish the external timing/protocol contract of `enable` and `txnrx`.
   Keep their qualification separate from RX data and from removed TX sample
   processing. Their names are not evidence that they can be ignored.
3. Apply only reviewed, source-specific constraints in a fresh complete receiver
   experiment, preserving AD9361's200MHz reference. Recheck all external setup,
   hold and internal/CDC/reset paths with the actual bank/native-fine/pilot/DMA
   composition. Report the selected programmable-delay assumptions explicitly.
4. Perform actual15/30/60MS/s RX calibration and bounded receiver tests on the
   allocated .18 canary before any .17 PPU Ethernet deployment. Calibration
   results and static timing evidence are complementary, not substitutes.

No radio was accessed or allocated. No PPU, Linux, receiver runtime, deployed
firmware, clock or physical constraint changed.

## Source-backed follow-up, not applied constraints

Analog Devices' AD9361 Rev.G data sheet, page8, specifies the1.8V CMOS
DATA_CLK-to-data delay as0..1.5ns and DATA_CLK-to-RX_FRAME delay as0..1.0ns.
These are different bounds; the frame must not inherit an invented identical
data-bus delay. The table also specifies45..55% clock pulse width. Board skew,
selected programmable delays and their supported operating assumptions are
still needed before translating these into this receiver's constraints.
[AD9361 data sheet](https://www.analog.com/media/en/technical-documentation/data-sheets/AD9361.pdf).

UG-570 distinguishes asynchronous SPI state-machine control from ENABLE/TXNRX
pin control. Therefore a source- and runtime-verified SPI-only contract may
justify treating those two controls differently from sampled RX data, but their
names alone cannot establish such a contract or authorize an exception.
[AD9361 reference manual, pages26–27](https://www.analog.com/media/en/technical-documentation/user-guides/ad9361.pdf).

Local Linux pin `4357f41a721df9d89a66be7a2a3f921a71d46bad` gives relevant
**build intent**, not live radio readback:

- `arch/arm/boot/dts/zynq-pluto-sdr.dtsi` selects CMOS/full-port, RX frame pulse,
  RX-only digital tuning (`skip-mode=1`) and omits ENSM pin-control/FDD options.
  No explicit receive clock/data delay properties appear there.
- `drivers/iio/adc/ad9361.c` initially defaults absent receive delay properties
  to zero. `ad9361_conv.c` subsequently programs receive delay register0x006
  during interface tuning; absence from the DTS is not proof of zero live delay.
- The existing FPGA `library/xilinx/common/ad_data_in.v` uses loadable IDELAYE2
  taps, with elaborated initial value0 and a runtime load/readback interface.
  Static timing at that elaborated value does not prove every programmed tap.

Important hardware-test boundary: the debugfs timing-analysis operation is
**not passive inspection**. In `ad9361_conv.c`,
`ad9361_dig_interface_timing_analysis` saves state, mutes TX, changes ENSM mode,
injects internal RX PRBS, sweeps16x16 clock/data delays, then restores state.
The debugfs read path in `ad9361.c` invokes it only after its command is armed.
Treat that entire operation as an explicitly reserved, bounded .18 calibration
test with before/after state verification, not as an unannounced .17 status read.
No such hardware operation was run during this audit.

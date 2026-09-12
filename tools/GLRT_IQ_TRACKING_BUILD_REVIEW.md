# Radio .20 GLI1 build review, 2026-09-12

Scope: bounded commissioning of the exact v4 30/60 MHz boards under
`/srv/bulk/leo/glrt-deployment-20260909/radio20-iq-tracking-20260912`.
This is an engineering review for a bench deployment, not live qualification.

| Native rate | Setup slack | Hold slack | LUT | BRAM | DSP |
| --- | --- | --- | --- | --- | --- |
| 30 MHz | +0.078 ns | +0.024 ns | 9102/17600 | 28.5/60 | 28/80 |
| 60 MHz | +0.085 ns | +0.022 ns | 9901/17600 | 34.5/60 | 36/80 |

Both routed designs generated bitstreams with no failing internal setup/hold
paths. Full audit reports retain the warnings; no blanket CDC waiver was added.
Both contain one native tracking engine, scheduler, result queue and DMA, with
no acquisition engine, local-search engine or legacy scoring engine.

The two CDC-11 paths are asynchronous reset assertions from `sys_rstgen` to
`acquisition_reset_source_sync[0]/CLR` and `counter_reset_release[0]/CLR`.
Source inspection confirms dedicated two-stage ASYNC_REG synchronizers with
local synchronous release. Data state consumes the second-stage outputs;
the acquisition epoch additionally waits for source reset acknowledgements.
These are reset fanout paths, not unsynchronized sample/descriptor buses.

The three CDC-6 buses are Gray-coded FIFO pointers and a monotonic dropped-word
counter. Existing 7.5 ns datapath bounds and 2 ns bus-skew bounds remain active.
Minimum routed skew slack is +0.888 ns at 30 MHz and +0.791 ns at 60 MHz.
The CDC-15/17 clock-enable and held-data mux warnings belong to the unchanged
ADI register-transfer/clock-monitor shell. The new GLT1 controller and native
engine run in the same 100 MHz fabric domain after the ingress FIFO.

The ADI source-synchronous RX pins have no explicit input delays in this board
flow. Internal timing closure therefore does not prove the receive interface.
Commissioning must configure the exact native sample clock, run current-rate
AD9361 RX-only digital tuning and verify the PN eye, then check live continuity,
CDC/pacer loss counters and descriptor retirement. The 15 methodology I/O-delay
warnings remain visible (13 RX pins and two control outputs).

Independent U-Boot extraction, GNU cpio inspection and DFU suffix checks passed
for both packages. Each exact FIT is below the .20 Micron first-16-MiB firmware
boundary. Deployment must use the .20 serial-bound PPU profile and production
qualification lease, attest the saved bootloader/flash/address, verify both
source and written FIT hashes, and retain the exact v0.49 rollback image.
The bench window is authorized by the user; RF testing remains bounded to
at most 30 minutes. Calibration and hardware transport results are outstanding.

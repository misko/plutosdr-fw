# Gain-series v4 RC8 disabled-timestamp counter candidate

RC8 is an unpromoted, RAM-boot-only candidate. It retains RC7b's routed TX
pipeline diagnostics and fixes a false discard counter exposed by the first
hardware test that actually drove the DMA-to-DAC path.

## RC7b evidence and RCA

RC7b passed its clean offline build and packaging gates with routed setup WNS
`+0.332 ns` and hold WHS `+0.017 ns`. On two RAM-booted PlutoPlus radios it
also passed:

- protocol-v2 compatibility at 524,288 samples per channel;
- protocol-v3 gain observations every 2,048 samples;
- simultaneous two-radio direct USB;
- 100 protocol-v3 frames per radio round-tripped through a V7 Zarr store; and
- direct-IP parity with the USB inner frame.

The original RF test used the FPGA DDS, which bypasses the modified
DMA/timestamp FIFO. A follow-up test instead transmitted a cyclic IIO buffer,
selected AD9361 digital TX-to-RX loopback, and captured through direct USB.
Both radios observed all DMA and DAC pipeline boundaries, proving end-to-end
activity through the wrapper. However, with the timestamp interval register at
zero, the reported discard counters still climbed to `865370` and `848025`.

The root cause was an omitted `timestamp_en` condition in the discard-state
process. While timestamping was disabled, arbitrary IQ payload bits were still
compared with the synchronized timestamp and incremented the diagnostic count.
The transparent data path itself did not discard those words because its ready
and write logic correctly selected the disabled-timestamp branch.

## RC8 change

RC8 clears the per-transfer discard decision whenever timestamping is disabled.
This prevents normal IQ words from being interpreted as timestamps and keeps
the discard count at zero in transparent mode. It also replaces two ambiguous
unsized one-bit constants with explicit `1'b0` connections.

A focused Icarus simulation supplies 16 deliberately late-looking IQ words
while the timestamp interval is zero. The test failed before the fix with a
discard count of 16 and passes after the fix with a count of zero. The existing
full wrapper test now asserts the same invariant, and the FIFO-reset,
TX-diagnostic-latch, and syntax simulations remain green.

## External RF fixture finding

The external TX2-to-attenuator/splitter-to-RX1/RX2 release gate remains a hard
promotion requirement, but its current failure is not specific to RC7b. The
same failure reproduced after restoring the preserved production QSPI image.
After a physical reboot, one production radio recovered a coherent external
tone while one branch remained weak; the other radio still received no
external tone from either logical TX channel. AD9361 internal loopback found
the correct tone on both radios, which narrows the outstanding issue to analog
RF routing or the external fixture.

Do not weaken or waive this gate. Repair and verify both attenuated fixtures,
then run at least three independent two-radio RC8 RAM boots with the external
TX gate before the downstream USB, IP, and Zarr gates. Never write an RC8
candidate to QSPI.

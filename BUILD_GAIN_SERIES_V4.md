# Gain-series v4 candidate build and promotion

This branch is source-complete but not a released or rover-approved image.
It adds protocol-v3 gain observations bracketed by the same FPGA sample counter
that timestamps each IQ frame. The USB and IP control planes expose the same
CRC-protected time-anchor record so a host can map exact frame counters onto
its monotonic clock without GNSS/PPS wiring.

For the exact no-hardware build, validation, artifact-attestation, and GitHub
prerelease procedure on Kalman, follow
[`KALMAN_GAIN_SERIES_V4_HANDOFF.md`](KALMAN_GAIN_SERIES_V4_HANDOFF.md).

## Pinned source

```text
firmware                  codex/firmware-gain-series-v4
buildroot      f30cea63c  codex/buildroot-gain-series-v4
USB gadget     c7431bb2a  codex/gadget-gain-series-v3
IP gadget      11d0cbb4c  codex/gain-series-v3
HDL            4e9d71240  codex/hdl-sample-counter-v3
HDL Quantulum  26eae2aff  codex/hdl-quantulum-gain-series-v3
```

The authoritative complete values are in
`manifests/gain-series-v4-source.yaml`.

The USB and IP daemons may start before the host configures the AD9361 RX
path. Their time-anchor reader therefore requires the counter register to be
readable at daemon startup, but does not require it to be moving yet.
Protocol-v3 stream startup independently requires an advancing counter and
fails closed if the sample-counter HDL is absent or stale.

## Source and host checks

```bash
git clone --branch codex/firmware-gain-series-v4 --recurse-submodules \
  https://github.com/misko/plutosdr-fw.git plutosdr-fw-gain-series-v4
cd plutosdr-fw-gain-series-v4
scripts/build_gain_series_candidate.sh source-check
scripts/test_gain_series_hdl.sh
```

Expected result: `SOURCE GRAPH OK` and at least 20 coherent CDC updates.

## FPGA build gate

Vivado 2022.2 is required. An older released XSA must not be reused: it lacks
the ARM-visible counter connection and protocol v3 will correctly fail closed.

```bash
cd plutosdr-fw-gain-series-v4
scripts/build_gain_series_candidate.sh image
```

The image command always rebuilds the pinned HDL and replaces
`build/system_top.xsa` before packaging. It will not silently reuse an XSA left
by another checkout or firmware version.

Before packaging firmware, Vivado must report:

- no locked or stale `util_cpack2_timestamp` IP;
- `cpack_timestamp/timestamp_cpu` connected to
  `axi_ad9361/up_adc_gpio_in`;
- timing and CDC checks pass;
- the generated bitstream is from the candidate HDL commits above.

If the IP metadata checksum is stale, reopen/package the
`hdl-quantulum/util_cpack2_timestamp` IP and update its checksums with Vivado;
do not suppress an IP-lock or port-mismatch error.

## Firmware package

Use the toolchain and reproducibility workflow in `BUILD.md`. The candidate
entry point performs the source, architecture, dependency, clean-tree and
Vivado-version checks before building the DFU. It must be run only after the
new XSA exists; it does not flash a radio.

Record SHA-256, `/opt/VERSIONS`, FPGA bitstream hash, and gadget build ID in a
new release manifest. Do not edit the immutable v3 manifest.

## Hardware promotion

1. Keep rover configs on protocol v2.
2. RAM boot the candidate on one radio; never flash it first.
3. Verify `iio_reg -u <uri> cf-ad9361-lpc 0x800000B8` advances.
4. Verify inline frame timestamps and the register low word describe one
   monotonic counter modulo 2^32.
5. Collect USB and IP time anchors; require request IDs, CRC, counter extension,
   and monotonic fit to pass. Report best/median/p99 round trip and the fitted
   host-clock uncertainty rather than claiming UTC accuracy.
6. Capture 100 protocol-v3 frames and reopen the V7 Zarr.
7. Repeat concurrently on both radios, then run the existing restart soak.
8. Compare IQ ordering, phase, throughput, sequence gaps, USB failures, and
   observation overflow against protocol v2.
9. The offline builder may publish an explicitly unpromoted prerelease candidate
   for this campaign. Only after every hardware gate passes, promote the accepted
   RC through the normal release and SPF-pinning process, then run the QSPI
   promotion procedure with the v3 image retained for rollback.

Protocol v3 intentionally rejects frames without an overlapping gain
observation. Equal observations mean only that no difference was observed at
those reads; they do not rule out a change-and-return between reads.

## RC1 hardware finding carried into RC2

RC1 proved the FPGA counter and time-anchor path on two radios, but its first
protocol-v3 DMA block could predate the first ARM gain observation. The USB and
IP workers now discard the startup-prefetched block after the sampler is ready
and permit a bounded sequence-zero retry; they still fail closed if any emitted
frame lacks an overlapping observation. Direct IP also paces UDP batches below
the PlutoPlus 100-Mbit/s link rate instead of overflowing a host receive queue.
These changes were hardware-checked from RAM on two radios before requesting
RC2, but the rebuilt RC2 bytes remain untested until the full campaign passes.

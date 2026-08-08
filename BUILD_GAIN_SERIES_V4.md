# Gain-series v4 candidate build and promotion

This branch is source-complete but not a released or rover-approved image.
It adds protocol-v3 gain observations bracketed by the same FPGA sample counter
that timestamps each IQ frame.

## Pinned source

```text
firmware                  codex/firmware-gain-series-v4
buildroot      d748b5643  codex/buildroot-gain-series-v4
USB gadget     0df6c86f8  codex/gadget-gain-series-v3
IP gadget      4cf0df925  codex/ip-gadget-gain-series-v3
HDL            4e9d71240  codex/hdl-sample-counter-v3
HDL Quantulum  da54b0943  codex/hdl-quantulum-gain-series-v3
```

The authoritative complete values are in
`manifests/gain-series-v4-source.yaml`.

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
5. Capture 100 protocol-v3 frames and reopen the V7 Zarr.
6. Repeat concurrently on both radios, then run the existing restart soak.
7. Compare IQ ordering, phase, throughput, sequence gaps, USB failures, and
   observation overflow against protocol v2.
8. Only after every gate passes, create a release tag/asset, update SPF pins,
   and run the normal QSPI promotion procedure with the v3 image retained for
   rollback.

Protocol v3 intentionally rejects frames without an overlapping gain
observation. Equal observations mean only that no difference was observed at
those reads; they do not rule out a change-and-return between reads.

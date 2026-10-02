# Local issue-119 qualification

This is a private, locally qualified kernel and iiOD update of the exact v0.59
image used by radio `1040007c4a94000211000b009186843ef2`. It is not an official
versioned release. See `reports/2026_10_02_issue_119.md` for the changed acceptance
criteria: ordinary RFPLL registers are stale during working Fast Lock recalls.

## Build

Use Linux commit `d3611e575b09fa4e43be99a513423cb1ab3f4d37`, the baseline kernel
configuration, and the Linaro GCC 7.3-2018.05 ARM hard-float toolchain. The
baseline is release DFU `plutoplus-spf-dual-rx-counter-fix-ca7f38f9f3a1-pluto.dfu`,
SHA-256 `1fa69d2784efbcabaaaed5bc5f5d625deabfd7da725627c9634a694db5bd9df0`.
`dumpimage -T flat_dt -p 4` extracts its kernel, and Linux's
`scripts/extract-ikconfig` extracts the configuration. Build with `ARCH=arm`,
`CROSS_COMPILE` pointing to `arm-linux-gnueabihf-`, and a dedicated `O` directory.
The candidate's configuration was verified byte-for-byte against the baseline.

Run the production-function fault-injection tests from the kernel tree:

```sh
python3 tools/testing/selftests/ad9361-fastlock/run.py
```

Build iiOD from libiio commit `345cd699236bce30eb5eed6d0e6adec6e2746360`
with the unchanged metadata source `3294365ff44da26b261be4a2ccb241b7896d23ad`:

```sh
scripts/issue119/build_iiod.sh /absolute/libiio /absolute/metadata \
  /absolute/host/share/buildroot/toolchainfile.cmake \
  /absolute/host/arm-buildroot-linux-gnueabihf/sysroot /absolute/iiod-build
```

Set `TMPDIR` to a writable build directory if needed. Package the new zImage,
iiOD, and matching library while preserving the remaining v0.59 payloads:

```sh
python3 scripts/issue119/package.py --base /absolute/baseline.dfu \
  --kernel /absolute/kernel/arch/arm/boot/zImage \
  --iiod /absolute/iiod-build/artifacts/iiod \
  --libiio /absolute/iiod-build/artifacts/libiio.so.0.25 --out /absolute/candidate
```

The packager validates the baseline digest, preserves archive ownership and
unchanged payloads, replaces the kernel and those two userspace binaries, and
updates `/opt/VERSIONS`. It creates FIT, DFU, FRM and a checksum manifest. FRM includes the existing updater's 32-character MD5 plus newline.

## Hardware

`recall_probe.c` builds with the same cross compiler and the kernel UAPI
`linux/adi_rx_counter.h`. Copy its static executable to `/tmp/issue119_recall`.
`hardware.py` requires libiio Python bindings, NumPy, the exact candidate
firmware identity, and the operator-confirmed TX2 attenuator/tee fixture. Set
`SSH_WRAPPER` to an executable that runs a command on the serial-attested radio,
using private credentials and a verified per-boot SSH key. Supply a new evidence
directory as the sole positional argument.

The test runs four TX frequencies, three repetitions of six recalls including
same-profile recalls, and both receive channels. It compares tone-band energy
against mismatched profiles and verifies restoration. It analyzes a 4096-sample
interior IQ window, excluding the v0.59 FPGA's periodic counter prefixes. It
retains spectra summaries and receipts rather than full IQ. The C process caps
itself at 128 commands; descriptor closure restores the RX LO.

Qualify in RAM before a persistent canary. For this radio, the tested FIT plus
flash offset and erase rounding ends below the 16 MiB address boundary. The
on-device updater writes the firmware partition and `fit_size`; verify the FIT
hash and protected partitions before rebooting. Keep the prior release DFU/FRM
and a private firmware-partition backup for rollback. Re-attest the USB serial,
firmware identity, boot ID, and flash contents after reboot.

`scan_matrix.py` uses the v0.59-compatible PPU runtime to run eight RX-only
scan cells: dual RX at 2.5/5/7.5/10 MS/s, each in manual and slow-attack mode.
Supply a new evidence directory. Each session is bounded to five seconds and
checks the terminal receipt and restoration.

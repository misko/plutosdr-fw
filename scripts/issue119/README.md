# Local issue-119 qualification

This is a private, locally qualified kernel-only update of the exact v0.54 RC1
image used by radio `1040007c4a94000211000b009186843ef2`. It is not an official
versioned release. See `reports/2026_10_02_issue_119.md` for the changed acceptance
criteria: ordinary RFPLL registers are stale during working Fast Lock recalls.

## Build

Use Linux commit `74973ff563fe6c5f95591da40e3fb89c52657ee7`, the baseline kernel
configuration, and the Linaro GCC 7.3-2018.05 ARM hard-float toolchain. The
baseline is release DFU `plutoplus-spf-counter-utc-v1-rc1-0ffdfe964247-pluto.dfu`,
SHA-256 `3611adb9d38d5db9e6e94453a195194022dd7c7ba0ca649234f783d1bb016ada`.
`dumpimage -T flat_dt -p 4` extracts its kernel, and Linux's
`scripts/extract-ikconfig` extracts the configuration. Build with `ARCH=arm`,
`CROSS_COMPILE` pointing to `arm-linux-gnueabihf-`, and a dedicated `O` directory.
The candidate's configuration was verified byte-for-byte against the baseline.

Run the production-function fault-injection tests from the kernel tree:

```sh
python3 tools/testing/selftests/ad9361-fastlock/run.py
```

Package the built zImage without rebuilding the FPGA or root filesystem:

```sh
python3 scripts/issue119/package.py --base /absolute/baseline.dfu \
  --kernel /absolute/kernel/arch/arm/boot/zImage --out /absolute/candidate
```

The packager validates the baseline digest, retains cpio ownership and all
payloads, updates `/opt/VERSIONS`, and creates FIT, DFU, FRM and a checksum
manifest. FRM includes the existing updater's 32-character MD5 plus newline.

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
interior IQ window, excluding the v0.54 FPGA's periodic counter prefixes. It
retains spectra summaries and receipts rather than full IQ. The C process caps
itself at 128 commands; descriptor closure restores the RX LO.

Qualify in RAM before a persistent canary. For this radio, the tested FIT plus
flash offset and erase rounding ends below the 16 MiB address boundary. The
on-device updater writes the firmware partition and `fit_size`; verify the FIT
hash and protected partitions before rebooting. Keep the prior release DFU/FRM
and a private firmware-partition backup for rollback. Re-attest the USB serial,
firmware identity, boot ID, and flash contents after reboot.

# Pluto+ SPF IQ direct-async + RAM queue v1

Release tag: `v0.46-plutoplus-spf-iq-direct-async-ring-v1`

This is the hardware-qualified, persistent production release of the
direct-async single-receiver IQ transport. It overlaps DMA acquisition with
iiOD TCP delivery. Optional RAM slots extend the same ordered DMA descriptor
queue: RAM is overflow capacity, not a separate capture, prefill, or output
path. When RAM is disabled, the direct path allocates and copies no ring IQ.

## What changed since RC1

- The exact non-RC firmware identity was built from merged firmware `main`.
- The exact image passed RAM boot, physical-1-GbE throughput, finite direct,
  combined DMA/RAM, standalone-ring, client-loss recovery, RF restoration,
  persistent installation, power-cycle, and QSPI byte-attestation gates.
- Pluto Plus Utils now primes the required pyadi scan layout with a bounded
  two-buffer queue before restoring the requested DMA depth. This avoids
  transient CMA double allocation when arming the qualified 15-buffer profile.
- Pluto Plus Utils contains a distinct, exact-hash persistent promotion policy.

## Required matched versions

Do not substitute stock libiio, an unmodified PyPI `pylibiio`, or a different
firmware artifact.

| Component | Required version, ref, or commit |
| --- | --- |
| firmware release | `v0.46-plutoplus-spf-iq-direct-async-ring-v1` |
| firmware source | `f182a8fa0811d2e70186b8f75d06ff4d5d896140`; immutable tag `iq-direct-async-ring-v1-source/fw-v1` |
| original refreshed base | `origin/main` at `4f15c87033e332293711ad679a50af0109c72862` |
| Buildroot | `a929267288a80a31407a3af06345c088979bcc2e`; tag `iq-direct-async-ring-v1-rc1-source/buildroot-v2` |
| radio and host libiio | API/SONAME 0.25 at `b7303fded264e10473bbbb084afade8f1b1373d1`; tag `iq-direct-async-ring-v1-rc1-source/libiio-v1` |
| SPF metadata provider | ABI 3 / `RadioMetadataV6` at `3294365ff44da26b261be4a2ccb241b7896d23ad` |
| HDL | `145bd47e55d5c5537e0ba49d53cb25a5393f66ba`; `ddr-burst-v1-rc4-source/hdl-v1` |
| Linux | `93174a1c049ca6ee42f042dbe93f0fb06fbc9cd7`; `ddr-burst-v1-rc3-source/linux-v1` |
| U-Boot | `1ff0468e9bea29b0a768a7bf52db8d025c521b9a`; `gain-series-v4-rc2-source/u-boot-xlnx` |
| Pluto Plus Utils | package 0.1.0, Python 3.11+; `main` at `d3e5cfeb1bae07357c711e4277053bb97fd5cee7` or later |
| host qualification/promotion implementation | `605384fc1095196e5a5946bc08e633394675c0c1` |
| Vivado | 2022.2, build 3671981 |
| ARM toolchain | Linaro GCC 7.3-2018.05, GCC 7.3.1 |

The `rc1-source` names on the Buildroot and libiio tags are historical immutable
source-lock names. The full release intentionally reuses those exact qualified
dependencies; the firmware tag and device identity are non-RC.

The host native library and generated Python binding must both be built from
`b7303fd`. The radio daemon must run with `iiod -r 1`, or the equivalent
supervised `--rw-cpu-affinity 1` used by this image.

## Release assets

Protected Actions run
[33408049625](https://github.com/misko/plutosdr-fw/actions/runs/33408049625),
attempt 1, built the exact release from clean merged `main`. The integrated
routed verdict is `PASS` and `firmware_release_eligible: true`.

| Asset | SHA-256 |
| --- | --- |
| `plutoplus-spf-iq-direct-async-ring-v1-f182a8fa0811.tar.gz` | `c91ab1fdd68fd66ca6f871d190c994417012bc6957f2b242ada680a9edab086e` |
| `plutoplus-spf-iq-direct-async-ring-v1-f182a8fa0811-pluto.dfu` | `ac51893dac8a914621aa8eb6f5c65d324ae8f09812033aa4880dc1dad8e6d739` |
| `plutoplus-spf-iq-direct-async-ring-v1-f182a8fa0811-pluto.frm` | `8a18aa951ba4d0e24534d2e15eec624587b07c92be991b0cb7f0d1669cad241e` |
| rootfs | `d80bbd7d8f4c9f997b318f815cd1664e5d8b97580bac5478e532bf117aa6d09b` |
| FIT body, 12,821,527 bytes | `8dc973cd808a49392d26e69336c3b5c32dbece6903f69b30698873caa1bf79c5` |
| packaged `/usr/sbin/iiod` | `cf950bdcdefa56ff90690e90fad8ce64151997c707ae3236b967b4bcfc6e9ec6` |
| packaged `libiio.so.0.25` | `7333f76edb775ebea3a51911c42dc5f3e45fb1e082676a867b7fa90b5d61168a` |

The DFU and FRM carry the same FIT body. `/opt/VERSIONS` reports:

```text
device-fw v0.46-plutoplus-spf-iq-direct-async-ring-v1
hdl ddr-burst-v1-rc4-source/hdl-v1
buildroot iq-direct-async-ring-v1-rc1-source/buildroot-v2
linux ddr-burst-v1-rc3-source/linux-v1
u-boot-xlnx gain-series-v4-rc2-source/u-boot-xlnx
```

## Hardware qualification

The exact image ran on serial `1040007c4a94000211000b009186843ef2`
over physical 1 GbE. Three independent direct-DMA captures at 30.72 MS/s used
15 DMA buffers and 23 frames of 1,048,576 CI16 samples:

| Run | Application `read_block()` rate | Gaps / overflows |
| ---: | ---: | ---: |
| 1 | 71.05 MB/s | 0 / 0 |
| 2 | 72.12 MB/s | 0 / 0 |
| 3 | 71.76 MB/s | 0 / 0 |

These figures use Pluto Plus Utils' layout-validated `raw-complex64` decoder so
the acceptance result measures transport plus the supported vectorized host
path. The default pyadi conversion path remains supported but measured below
70 MB/s on this host.

The combined 10-DMA + 13-RAM profile repeated three 23-frame captures with zero
gaps. Every run spilled six frames into RAM, drained the same six in FIFO order,
and completed with high-water 6. A standalone 8-DMA/15-RAM capture at 20 MS/s
returned 23/23 frames with zero gaps, high-water 15, one wrap, and
`target_complete`.

The complete 5/10/15/25 MS/s by 3/10-second ladders executed all eight cells in
both ringless and RAM-extension modes with no command or allocation failures.
The source outruns the link at sustained 25 MS/s; counters report those gaps
instead of hiding them. The finite 23-frame 30.72-MS/s acceptance profile is
the zero-gap 70 MB/s gate.

Two deliberate 200 MB ring-client losses, alternating RX0 and RX1, each
recovered into gapless ring and ordinary-IIO probes without restarting Linux or
iiOD. The final health check had zero active RX/TX buffers, zero fault flags,
DDS disabled, and TX1/TX2 at -80 dB.

Persistent installation was then performed on directly attached serial
`winbond-db6968136727402c`. After a user power cycle, the radio returned from
QSPI as the exact v0.46 identity. The guarded reconciliation read `/dev/mtd3`
and matched FIT SHA-256 `8dc973cd...`; USB/IIO identity, ordinary RX, direct,
DMA/RAM spill/drain, standalone ring, abrupt-client recovery, AD9361/2R2T, TX
safety, and 5.8 GHz tune/readback/exact restoration all passed again.

## Install

Read [IIO_DIRECT_ASYNC_INSTALL.md](IIO_DIRECT_ASYNC_INSTALL.md) before writing a
radio. The supported persistent route is the exact-hash Pluto Plus Utils
profile, not an unguarded copy command:

```bash
pluto firmware flash /absolute/path/plutoplus-spf-iq-direct-async-ring-v1-f182a8fa0811-pluto.dfu \
  --usb-sysfs-path /sys/bus/usb/devices/EXACT_PATH \
  --profile iq-direct-async-ring-v1-release-persistent-promotion
```

Review the dry-run plan. Execute only when the serial, current firmware, USB
path, DFU/FIT hashes, and target version are exact:

```bash
pluto firmware flash /absolute/path/plutoplus-spf-iq-direct-async-ring-v1-f182a8fa0811-pluto.dfu \
  --usb-sysfs-path /sys/bus/usb/devices/EXACT_PATH \
  --profile iq-direct-async-ring-v1-release-persistent-promotion \
  --execute --confirm 'FLASH EXACT_SERIAL'
```

The updater writes only the Pluto+ `qspi-linux` firmware partition. Never use a
full firmware ZIP, `boot.frm`, `boot.dfu`, or `uboot-env.dfu` on Pluto+.

## Known limits

- Direct mode is finite, single-receiver, and accepts 1 through 64 frames per
  wire request. The ladder splits longer cells into bounded segments.
- The qualified 70 MB/s path requires physical 1 GbE, `iiod -r 1`, 15 DMA
  buffers, 1,048,576-sample frames, and `raw-complex64` host decoding.
- A Pluto USB 2.0 Ethernet gadget cannot establish the 70 MB/s gate. It remains
  suitable for low-rate functional and recovery qualification.
- RAM extension improves ordered queue capacity and continuity. It performs
  explicit Zynq RAM copies and is not the maximum-throughput mode.
- Sustained 25 MS/s offers 100 MB/s, above this radio/link path. Gaps there are
  expected and explicitly counter-accounted.

## Rollback

Keep the previous hardware-qualified DFU/FRM and checksums until post-install
tests pass. Roll back only the firmware partition with the previous release's
own exact persistent profile. Do not rewrite the Pluto+ bootloader or U-Boot
environment as part of a firmware rollback.

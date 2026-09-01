# v0.48 Pluto+ direct-async IQ v3

Release: `v0.48-plutoplus-spf-iq-direct-async-v3`  
Status: **hardware-qualified full release**  
Protected build: [run 33481347855](https://github.com/misko/plutosdr-fw/actions/runs/33481347855)  
Built source: `e3078376a6e1a8c6ea841dc69966b3880e020c70`

## Outcome

V0.48 fixes the long direct-async session failure tracked by issue #72. V0.47
could return terminal `ENODATA` after a queued IQ frame aged beyond the finite
gain/RSSI metadata-coverage window. V0.48 classifies that frame as `ESTALE` and,
when the default drop-backlog policy is active, retires it and the queued stale
backlog while keeping the original finite host request alive.

The exact protected-build bytes completed one 60-second, 1,431-frame, 6.002 GB
25 MS/s request over physical 1 GbE without segmentation, re-arm, `ENODATA`, or
another terminal failure. Application payload remained above 70 MB/s in the
3-, 10-, and 60-second gates.

This is a full release, not an RC and not a RAM-only release. The exact DFU/FIT
passed volatile fleet qualification, persistent installation, QSPI readback,
an independent guarded reboot, repeated QSPI readback, TX-safe checks, and a
post-reboot direct capture. The release is persistent-reboot qualified; an
all-power-removed cold boot was not performed in this qualification and is not
claimed.

## What changed

- The SPF provider returns `ESTALE` when a real IQ frame is older than provable
  gain or RSSI metadata coverage.
- In `drop-backlog` mode, radio iiOD retires the uncovered frame, releases all
  queued-but-unsent DMA and RAM-backed frames, rebases exact ABI-3 loss
  metadata, and continues filling the same finite target.
- The TCP frame already in flight is never withdrawn.
- `preserve-backlog` remains available and retains the ordered backlog; it
  fails closed if metadata cannot be proved.
- More than `DMA capacity + 8` consecutive stale frames still fails closed,
  preventing an unbounded recovery loop.
- Host libiio snapshots terminal direct-session status before cancelling a
  failed socket, allowing Pluto Plus Utils to report the radio-side reason.

RAM remains an extension of the same FIFO. It is not a separate capture
session, it does not create periodic buffering/re-arming boundaries, and it
cannot increase steady-state link bandwidth. When drop-backlog fires, only
queued-but-unsent frames are retired so the queue can refill with current RF
time.

## Exact release stack

| Layer | Required immutable version |
| --- | --- |
| firmware protected build | `e3078376a6e1a8c6ea841dc69966b3880e020c70` |
| recovery implementation ancestor | `322b67f9580d215c1f8362735c877f7c5ee2f89e`; `iq-direct-async-v3-source/fw-v1` |
| Buildroot/rootfs | `1c337a0b8d8126c9d1ed785607bc5ea52e7fed22`; `iq-direct-async-v3-source/buildroot-v1` |
| radio and host libiio | 0.25 at `0d323080a0a1067da8c7adbadfd03ee186a40ec2`; `iq-direct-async-v3-source/libiio-v1` |
| libiio source archive | SHA-256 `66ccc7230ebe75c477c4dfc147aa86289c3f896c0a0d6b3b6c964e152d89c266` |
| SPF metadata provider | ABI 3 / `RadioMetadataV6` at `3294365ff44da26b261be4a2ccb241b7896d23ad` |
| HDL | `145bd47e55d5c5537e0ba49d53cb25a5393f66ba`; `ddr-burst-v1-rc4-source/hdl-v1` |
| HDL Quantulum | `364b3dc7e770c3971d1f41a75c00e6cae76e2e6d` |
| Linux | `93174a1c049ca6ee42f042dbe93f0fb06fbc9cd7`; `ddr-burst-v1-rc3-source/linux-v1` |
| U-Boot | `1ff0468e9bea29b0a768a7bf52db8d025c521b9a`; `gain-series-v4-rc2-source/u-boot-xlnx` |
| Pluto Plus Utils | `main` merge `246ead24fd9c9052a978340a0905408afcb3b8aa` or later |
| PPU exact persistent profile | `0a21ce250b44006a7880ae35dc30d11673fd2180` |
| Vivado | 2022.2 build 3671981 |
| ARM toolchain | Linaro GCC 7.3-2018.05, GCC 7.3.1 |

The radio reports libiio `0.25 (0d32308)`. Both the native host library and
generated Python binding must come from that same source tree. Stock libiio,
the earlier v0.47 `8f66f35` build, or an unmodified PyPI-only `pylibiio`
installation is not the v0.48 direct-async host runtime.

The packaged `/opt/VERSIONS` is:

```text
device-fw v0.48-plutoplus-spf-iq-direct-async-v3
hdl ddr-burst-v1-rc4-source/hdl-v1
buildroot iq-direct-async-v3-source/buildroot-v1
linux ddr-burst-v1-rc3-source/linux-v1
u-boot-xlnx gain-series-v4-rc2-source/u-boot-xlnx
```

The integrated routed design passed with WNS 0.767 ns and WHS 0.019 ns.

## Exact release assets

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| `plutoplus-spf-iq-direct-async-v3-e3078376a6e1.tar.gz` | 134,226,947 | `4839ef4e97b2c7d2f56363219184ec48db8fbdab67f1b6d8388f531ca79836fd` |
| `plutoplus-spf-iq-direct-async-v3-e3078376a6e1-pluto.dfu` | 12,825,587 | `cc87c36a3aad609a64b45f4a02eecf916b99a3099fa523eed1bf4526ed98995a` |
| DFU/FRM FIT body | 12,825,571 | `db777ac93d5c6f0be0cf2799808a4d06fe39264ee1e99e76001509394d75f1df` |
| `plutoplus-spf-iq-direct-async-v3-e3078376a6e1-pluto.frm` | 12,825,604 | `98341f4d5e926684c092b2addc283852a56f999ba57b4e89ea30a306785e81e0` |
| `iq-direct-async-v3-source.yaml` | 2,596 | `8f9b4aa76958a63aee3927ca7a4d57bbec18b3c9afacca4dbe46dd64a7ce9b22` |

Use `iq-direct-async-v3-SHA256SUMS` to verify downloaded release files. The
tarball also contains `SHA256SUMS` and `PAYLOAD_SHA256SUMS`; both must pass
before using a member.

## Hardware qualification

### Four-radio volatile fleet gate

The exact DFU was RAM-booted with PPU on four serial/path-bound attached USB
radios. All four returned as v0.48, AD9361, paired RX, and TX-safe. Each then
returned 15/15 frames at 5 MS/s for three seconds through its isolated USB
Ethernet route with zero gaps, zero missing samples, and zero overflow.

| Radio | Application payload |
| --- | ---: |
| `104000…3ef2` | 18.070 MB/s |
| `104000…003a` | 18.259 MB/s |
| `winbond…172c` | 18.225 MB/s |
| `winbond…402c` | 18.093 MB/s |

### Physical-1-GbE 25 MS/s gate

These cells used 1,048,576 samples/frame, 47 DMA buffers, no RAM ring, and
default drop-backlog. Every requested output frame was returned from one
capture segment.

| Window | Frames | Payload | Gap events | Missing samples | Source coverage |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 3 s | 72/72 | **73.571 MB/s** | 2 | 20,971,520 | 78.26% |
| 10 s | 239/239 | **74.088 MB/s** | 7 | 73,400,320 | 77.35% |
| 60 s | 1,431/1,431 | **72.823 MB/s** | 53 | 552,599,552 | 73.08% |

“Source coverage” is delivered sample positions divided by delivered plus
counter-proven missing sample positions. It is not wall-clock throughput. A
25 MS/s CI16 source offers 100 MB/s, above the sustained application rate, so
gaps are expected; the release guarantees explicit accounting and finite
request completion, not impossible lossless transport over a slower consumer.

### RAM/drop-backlog ladder

The 11-DMA + 32-slot (128 MiB) ladder used 5/10/15/20/25 MS/s over 3- and
20-second windows. All ten cells completed without a terminal failure. Both
windows were gapless at 5, 10, and 15 MS/s; the 3-second 20 MS/s cell was also
gapless. At 20 and 25 MS/s over 20 seconds, the ring filled and reported exact
spill/drain/drop counters.

### Matched 25 MS/s, 20-second policy matrix

| Queue | Policy | Frames | Payload | Gap events | Missing samples | Source coverage |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 11 DMA | preserve | 477/477 | 75.016 MB/s | 143 | 153,092,096 | 76.57% |
| 11 DMA | drop | 477/477 | 72.779 MB/s | **21** | 178,257,920 | 73.72% |
| 11 DMA + 32 RAM | preserve | 477/477 | 65.606 MB/s | 198 | 213,909,504 | 70.04% |
| 11 DMA + 32 RAM | drop | 477/477 | 60.311 MB/s | **12** | 298,844,160 | 62.60% |

Drop-backlog reduced separate gap events by 85.3% ringless and 93.9% with RAM.
It deliberately trades some source coverage for fewer timeline breaks and
fresher delivered data. In RAM preserve, all 365 spilled frames drained and
the 32-slot high-water mark was reached. In RAM drop, `357 spilled = 155
drained + 202 dropped`.

### Persistent return

PPU profile `iq-direct-async-v3-release-persistent-promotion` installed the
exact image on `winbond-db6968136727402c`. Flash receipt
`016eb590-5fb4-42e3-9568-afe0f4d4254c` recorded the full write/eject/return and
TX-safe sequence. Read-only reconciliation matched `/dev/mtd3` to FIT
`db777a…d1df`. Guarded reboot receipt
`7605359b000b474994626df2e602691b` proved same-topology v0.48/AD9361 return;
after expected SSH-key rotation, repeat reconciliation and a 15/15-frame,
zero-gap 5 MS/s capture passed.

## Operation and installation

Follow [`IIO_DIRECT_ASYNC_INSTALL.md`](IIO_DIRECT_ASYNC_INSTALL.md). The safe
path is:

1. download the exact named release and verify `iq-direct-async-v3-SHA256SUMS`;
2. install PPU `246ead24…` or later and run its matched libiio installer;
3. require `pluto environment` to report `libiio 0.25 (0d32308)` with IP and
   USB backends;
4. run a PPU-only read-only flash plan using profile
   `iq-direct-async-v3-release-persistent-promotion`;
5. execute only the serial-specific confirmation phrase printed by that plan;
6. enroll the newly generated SSH host key through PPU after each reboot; and
7. reconcile the receipt read-only to the exact QSPI FIT hash.

Do not write `boot.frm`, `boot.dfu`, `uboot-env.dfu`, or a full firmware ZIP to
a Pluto+ when installing this release. The qualified update changes only the
firmware FIT (`pluto.frm`/`pluto.dfu`) and leaves the established bootloader
tuple intact.

## Compatibility and rollback

- Requires a Pluto+ with AD9361/2R2T setup and metadata ABI 3.
- A radio reporting AD9363A can still physically tune to 5.8 GHz after correct
  setup, but release qualification requires live AD9361 identity and four RX
  scan elements.
- The default overrun policy is drop-backlog; select preserve only when stale
  ordered delivery is more important than gap-event count and RF recency.
- V0.47 remains the rollback release. Rollback is another guarded persistent
  firmware operation using its own exact PPU profile, hashes, and receipt; do
  not substitute its host `8f66f35` runtime while operating v0.48.

The public PPU evidence and visual are in the
[`Issue #72 recovery qualification report`](https://github.com/misko/pluto-plus-utils/tree/main/reports/2026-09-01-issue-72-direct-async-recovery).
The immutable release record is
[`manifests/iq-direct-async-v3.yaml`](manifests/iq-direct-async-v3.yaml).

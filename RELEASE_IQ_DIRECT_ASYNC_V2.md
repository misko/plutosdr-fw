# Pluto+ SPF IQ direct-async v2

Release tag: `v0.47-plutoplus-spf-iq-direct-async-v2`

This is the full production release of the direct-async single-receiver IQ
transport. One iiOD request keeps a DMA producer/consumer session alive for up
to 4,096 frames. Optional RAM slots extend the same ordered queue; they are not
a second capture session. V2 adds an explicit radio-side overrun policy:

- `drop-backlog` (default) preserves the frame already entering TCP, retires
  every queued-but-unsent DMA or RAM frame, accounts for the discontinuity in
  ABI-3 metadata, and refills the original host target. It minimizes stale-data
  latency and the number of separate gap events.
- `preserve-backlog` retains every queued frame. It usually gives better total
  source-time coverage when a sustained source outruns the link, at the cost of
  many smaller discontinuities and older delivered RF time.

Neither policy hides loss, clears the in-flight TCP frame, ends the host
request, or periodically re-arms the DMA session.

The exact image passed its RAM, performance, recovery, persistent-write,
QSPI-byte, all-power-removed cold-boot, RF-restoration, ordinary-IIO, and
TX-safe gates.

## Required matched versions

Do not substitute stock libiio, an unmodified PyPI `pylibiio`, an older ABI-3
runtime, or a different firmware artifact.

| Component | Exact required version, ref, or commit |
| --- | --- |
| firmware release | `v0.47-plutoplus-spf-iq-direct-async-v2` |
| protected firmware source | `2bab87dcd9b18c8f957ae781603e88160c8509cc`; immutable tag `iq-direct-async-v2-source/fw-v1` |
| v2 integration | `22adfc967` (overrun policy), `35d3c9242` (full-build staging), `f6286c515` (source-graph retirement), merged by `2bab87dcd` |
| Buildroot | `3e1dd15acf361cc06e202e9e59e907dd379a13c3`; tag `iq-direct-async-v2-source/buildroot-v1` |
| radio and host libiio | API/SONAME 0.25 at `8f66f353c9a70a5524988ceb588b0e9271c2390d`; tag `iq-direct-async-v2-source/libiio-v1` |
| SPF metadata provider | ABI 3 / `RadioMetadataV6` at `3294365ff44da26b261be4a2ccb241b7896d23ad`; tag `iio-throughput-sampler-wake-v5-source/metadata-v1` |
| HDL | `145bd47e55d5c5537e0ba49d53cb25a5393f66ba`; tag `ddr-burst-v1-rc4-source/hdl-v1` |
| HDL Quantulum | `364b3dc7e770c3971d1f41a75c00e6cae76e2e6d`; source ref `ddr-burst-v1-rc5-source/hdl-quantulum-v1` |
| Linux | `93174a1c049ca6ee42f042dbe93f0fb06fbc9cd7`; tag `ddr-burst-v1-rc3-source/linux-v1` |
| U-Boot | `1ff0468e9bea29b0a768a7bf52db8d025c521b9a`; tag `gain-series-v4-rc2-source/u-boot-xlnx` |
| Pluto Plus Utils | package 0.1.0, Python 3.11+; `main` at `9f9a2bd6d059833bc7d9259a48eabff8e20642ad` or later |
| host long-session/overrun implementation | merge `d5435901dd7a37619d71db9fdd0d0f1fb368b0bd`; commits `5d0ba26`, `e1fddf6`, `1b05e53` |
| RAM qualification / inspection / persistent promotion / repeat reconciliation | `675fd156ab03e51428c16a60095489385f720d24`, `1554dc8b25893e25ce6015373a5d89d813636f98`, `cb7c81127688e00dc0990e7b9d7cea3d05b7b936`, `a6c0ae65cb6818afbd3e0e20be457868e87f50f6` |
| Vivado | 2022.2, software build 3671981, IP build 3669848 |
| ARM toolchain | Linaro GCC 7.3-2018.05, GCC 7.3.1 |

The host native library and generated Python binding must both come from exact
libiio `8f66f35`. The radio daemon must run with `iiod -r 1`, or the image's
supervised equivalent `--rw-cpu-affinity 1`.

The protected image contains:

```text
device-fw v0.47-plutoplus-spf-iq-direct-async-v2
hdl ddr-burst-v1-rc4-source/hdl-v1
buildroot iq-direct-async-v2-source/buildroot-v1
linux ddr-burst-v1-rc3-source/linux-v1
u-boot-xlnx gain-series-v4-rc2-source/u-boot-xlnx
```

## Exact release assets

Protected Actions run
[33440908273](https://github.com/misko/plutosdr-fw/actions/runs/33440908273),
attempt 1, built clean merged `main`. Its integrated routed verdict is `PASS`,
`firmware_release_eligible` is true, WNS is 0.767 ns, and TNS is 0.

| Object | Bytes | SHA-256 |
| --- | ---: | --- |
| `plutoplus-spf-iq-direct-async-v2-2bab87dcd9b1.tar.gz` | 134,209,404 | `04866f2d3e420326f70184f654d28e4a42d4251c0a97765a3eae3b367c63d8eb` |
| `plutoplus-spf-iq-direct-async-v2-2bab87dcd9b1-pluto.dfu` | 12,826,123 | `b97564524058b4b57e73ccfa60cdf1acbefaac05f90b16ccd460b0a8bb6c307d` |
| `plutoplus-spf-iq-direct-async-v2-2bab87dcd9b1-pluto.frm` | 12,826,140 | `e56728f87fea150d0f0b057deed2f1878ecb830bab3e81ddaba84dc8a7449451` |
| `iq-direct-async-v2-source.yaml` | 2,571 | `8686c67e6cb19d7f75ef9cc171a4f1598430b8e1f39fa346bc41b9856cad414b` |
| `iq-direct-async-v2.yaml` | 6,298 | `f534ca8a7d08535409c846f350c266d76d5525d284158e43030f82a700974d56` |
| FIT body | 12,826,107 | `7a198f961cd6765ebd831c21314baac0f962650541af671911c23e76db33cbc2` |
| rootfs | 7,209,668 | `f36534f2867068f3706c69ff66c1c20637ad4e34ae9e4f8b0e75e19eecc0ccfc` |
| `system_top.bit` | 969,580 | `b5455aa572afbe898c91334166785969b2656902174c33bae97554acc5f2cab3` |
| `system_top.xsa` | 839,659 | `6d14c9d6b33478e421492ec19eb7e193ad70a4585f04752846fea23bf98483e1` |
| packaged `/usr/sbin/iiod` | — | `edd4136cbeafa102735920ab25f763eed62c7d2c2cc565d00cf5266538f1ff07` |
| packaged `/usr/lib/libiio.so.0.25` | — | `cb78e69b58636ee3241dfe736c1e7f79637a90d171fdb090831d3e21b369d6c7` |

The DFU and FRM contain the same FIT body. Verify the downloadable objects with
`iq-direct-async-v2-SHA256SUMS`; then verify the archive's own `SHA256SUMS` and
`PAYLOAD_SHA256SUMS` before using any extracted member.

## Hardware qualification

The exact final image was RAM-booted on AD9361 serial
`winbond-db620818a328172c` and tested over its physical 1 GbE address. The
ringless 15-DMA, 1,048,576-sample-frame speed ladder produced:

| Rate | 3-second payload | 3-second gaps | 10-second payload | 10-second gaps |
| ---: | ---: | ---: | ---: | ---: |
| 5 MS/s | 18.981 MB/s | 0 | 19.566 MB/s | 0 |
| 10 MS/s | 38.986 MB/s | 0 | 39.527 MB/s | 0 |
| 15 MS/s | 59.286 MB/s | 0 | 59.473 MB/s | 0 |
| 25 MS/s | 73.876 MB/s | 1 event / 10,485,760 samples | 73.546 MB/s | 8 events / 75,497,472 samples |

Thus the sustained application path exceeds 70 MB/s. Three independent
23-frame captures were gapless. Their short-session averages were 68.15,
69.94, and 69.33 MB/s, so this release does not claim that every startup-heavy
23-frame measurement exceeds 70 MB/s.

The exact 200 MB extension used 12 DMA frames plus 50 one-million-sample RAM
slots. It remained gapless for 3 seconds at 25 MS/s (68.314 MB/s, 33 spills,
high-water 22). At 10 seconds it delivered 60.741 MB/s with five gap events,
139 million missing samples, 164 spills, 68 drains, and 96 evictions. RAM
extends queue capacity and can defer a gap, but Zynq CPU copies reduce maximum
transport throughput.

One-session 250-frame, 1.000 GB timeline captures compared both policies with
and without RAM. Every row returned the requested 250 frames and had zero host
request re-arms:

| Queue and policy | Payload | Gap events | Missing samples | Source-time coverage |
| --- | ---: | ---: | ---: | ---: |
| 12 DMA, default drop | 71.624 MB/s | 9 | 90,000,000 | 73.53% |
| 12 DMA, preserve | 73.067 MB/s | 73 | 78,000,000 | 76.22% |
| 12 DMA + 200 MB RAM, default drop | 59.966 MB/s | 4 | 137,000,000 | 64.60% |
| 12 DMA + 200 MB RAM, preserve | 66.009 MB/s | 65 | 66,000,000 | 79.11% |

This is the intended meaning of the default: it produces fewer, larger
discontinuities and fresher output after pressure. It does not claim fewer
missing samples or higher coverage when 25 MS/s continuously offers 100 MB/s
to a slower path.

Ordinary dual-RX refill, abrupt-client recovery, exact settings restoration,
idle DMA/RAM status, TX mute, the persistent AD9361/2R2T U-Boot tuple, and a
5.8 GHz RX-LO tune/readback with exact prior-LO restoration all passed.

## Persistent promotion evidence

Pluto Plus Utils wrote only the exact firmware partition to serial
`winbond-db620818a328172c` through persistent profile
`iq-direct-async-v2-release-persistent-promotion`. Guarded receipt
`799b4564-e4a2-474b-b2e1-9a8923e6d82e` records the serial-bound write, return as
v0.47/AD9361, metadata ABI 3, v2 capability readback, and TX-safe state. A
separate read-only reconciliation hashed `/dev/mtd3` and matched the exact FIT
SHA-256 `7a198f96...cbc2`.

After all power sources were removed for at least 10 seconds, the same USB path
and serial returned directly as v0.47/AD9361 with ABI 3, tandem capability, and
a passing ordinary dual-RX refill. Authenticated read-only postflight verified
the persistent AD9361/2R2T tuple, tuned RX LO to exactly 5.8 GHz, and restored
the exact prior LO. At `2026-08-31T23:07:11.082553+00:00`, repeated guarded
reconciliation matched `/dev/mtd3` FIT SHA-256 `7a198f96...cbc2`, re-attested
the serial/firmware, and confirmed TX-safe state. No repair or QSPI write ran
during cold-boot verification.

## Install, limits, and rollback

Follow [IIO_DIRECT_ASYNC_INSTALL.md](IIO_DIRECT_ASYNC_INSTALL.md). Pluto+ users
must use the exact PPU persistent profile; do not copy a full ZIP, `boot.frm`,
`boot.dfu`, or `uboot-env.dfu`.

Important limits:

- direct mode supports exactly one selected receiver and at most 4,096 frames
  per request;
- physical 1 GbE, matched libiio `8f66f35`, `iiod -r 1`, and vectorized
  `raw-complex64` decoding are required for the measured performance profile;
- Pluto USB 2.0 Ethernet is useful for functional tests but cannot establish a
  70 MB/s gate; and
- sustained 25 MS/s CI16 offers 100 MB/s, so loss is expected whenever the
  consumer remains slower than the source, regardless of buffer capacity.

Retain the previous hardware-qualified v0.46 DFU/profile until post-install
checks pass. Roll back only the firmware partition with that release's own
exact guarded profile. Never rewrite the Pluto+ bootloader or U-Boot
environment during routine upgrade or rollback.

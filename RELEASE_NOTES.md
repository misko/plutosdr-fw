# Release notes

## Version history at a glance

| Release | Date | Status | What it added |
|---|---|---|---|
| `gain-rssi-v2` | 2026-07-26 | superseded | first direct-USB v2 metadata frame: per-buffer RX1/RX2 gain + RSSI |
| `fingerprint-v1` | 2026-07-28 | superseded | passive gadget build-identity query |
| `fingerprint-v2` | 2026-08-02 | superseded | dual-Pluto simultaneous startup fix on 16 MiB usbfs hosts |
| `fingerprint-v3` | 2026-08-02 | last stable | supervised recovery of a crashed direct-USB gadget |
| `gain-series-v4-rc1` | 2026-08-09 | **rejected** | protocol-v3 gain series; failed on hardware |
| `gain-series-v4-rc2` | 2026-08-09 | offline only | startup-prefetch fix + bounded direct-IP pacing |
| `gain-series-v4-rc11` | 2026-08-09 | qualified | first protocol-v3 candidate to pass on hardware |
| `gain-series-v4-rc12` | 2026-08-10 | qualified | direct-IP frame/timing parity, verified TX mute |
| RC13 – RC15 | — | never released | source tags only |
| `gain-series-v4-rc16` | 2026-08-10 | qualified | 320-frame / 1.25 GiB direct-IP burst at 21.33 MiB/s |
| `gain-series-v4-rc17` | 2026-08-10 | qualified | direct-IP control lifecycle rewritten around worker ownership |
| `gain-series-v4` | 2026-08-11 | superseded | RC17's source with the version label corrected |
| **`libiio-metadata-v5`** | 2026-08-12 | **current hardware-qualified** | frame metadata through the standard libiio USB and IP/TCP transports |
| `libiio-metadata-v6-rc3` | 2026-08-17 | **RAM-only candidate** | bounded teardown/reset diagnostics and Winbond identity support for #32/#33 |
| `libiio-metadata-v6-rc4` | 2026-08-17 | **unreleased, RAM-only** | fail-closed TX boot state, recoverable identity diagnostics, and W25Q256FV support for #34/#33 |

**A note on the numbering.** The trailing number does not mean the same thing
across families. `gain-rssi-v2` names the *direct-USB metadata protocol* version
2. `fingerprint-v1..v3` is a separate series tracking the passive-fingerprint
work, which is why v1 follows v2. `gain-series-v4` is the protocol-**v3** gain
series. `libiio-metadata-v5` and `v6-rc3` then move that metadata into the
standard libiio transports. Read the family name, not the digit.

## v0.39-plutoplus-spf-libiio-metadata-v6-rc4 (unreleased)

RC4 is under four-board RAM-only qualification for
[issue #32](https://github.com/misko/plutosdr-fw/issues/32),
[issue #33](https://github.com/misko/plutosdr-fw/issues/33), and
[issue #34](https://github.com/misko/plutosdr-fw/issues/34). It must not be
written to serial flash until the complete hardware matrix passes.

RC4 initializes every active AD9361 TX path at exactly `-80 dB`, then an
independent startup gate zeros and verifies every DDS control and writes and
verifies every TX gain before exposing USB services. A mute failure returns to
RAM DFU. An identity failure exposes a clearly labelled, per-boot Ethernet/ACM
diagnostic gadget while withholding USB-IIO and direct-SDR functions.

The attached blank-serial W25Q256 hardware exposed a second RC4 red: Zynq QSPI
skips SFDP parsing, so a UID reader installed only by the BFPT callback never
appears in sysfs. The corrected candidate installs the common FV/JV opcode
`4Bh` UID reader in the unconditional post-SFDP fixup and retains the BFPT hook
only for addressing-mode discrimination. A source regression test now guards
that controller-specific path.

The Winbond board's 2023 U-Boot also contains a malformed legacy `attr_val`
test that rewrites `mode=1r1t`. Removing the redundant `attr_name`/`attr_val`
pair while retaining `compatible=ad9361` was red/green tested across a real
U-Boot/RC4 RAM reboot: `mode=2r2t` persisted, both TX gains read `-80 dB`, and
all eight DDS values read zero. Detailed acceptance criteria and live evidence
are maintained in [`SPF_LIBIIO_METADATA_V6_RC4.md`](SPF_LIBIIO_METADATA_V6_RC4.md).

## v0.39-plutoplus-spf-libiio-metadata-v6-rc3

Published as a prerelease on 2026-08-17. This is a **hardware-untested,
RAM-boot-only candidate** for [issue #32](https://github.com/misko/plutosdr-fw/issues/32)
and [issue #33](https://github.com/misko/plutosdr-fw/issues/33). Do not install
it persistently until the hardware promotion gates below pass on both Micron
and Winbond boards.

### Identity and downloads

| | |
|---|---|
| release | [`v0.39-plutoplus-spf-libiio-metadata-v6-rc3`](https://github.com/misko/plutosdr-fw/releases/tag/v0.39-plutoplus-spf-libiio-metadata-v6-rc3) |
| firmware source | [`ff999e906018966557e275f8ec96e3c490869de8`](https://github.com/misko/plutosdr-fw/commit/ff999e906018966557e275f8ec96e3c490869de8) |
| `device-fw` | `v0.39-plutoplus-spf-libiio-metadata-v6-rc3` |
| DFU | [`plutoplus-spf-libiio-metadata-v6-rc3-ff999e906018-pluto.dfu`](https://github.com/misko/plutosdr-fw/releases/download/v0.39-plutoplus-spf-libiio-metadata-v6-rc3/plutoplus-spf-libiio-metadata-v6-rc3-ff999e906018-pluto.dfu) |
| DFU sha256 | `091ec7ded71f84057927dbf4c0a155ee61a1ceb4166e8fa2aca352685ef4aa23` |
| source bundle | [`plutoplus-spf-libiio-metadata-v6-rc3-ff999e906018.tar.gz`](https://github.com/misko/plutosdr-fw/releases/download/v0.39-plutoplus-spf-libiio-metadata-v6-rc3/plutoplus-spf-libiio-metadata-v6-rc3-ff999e906018.tar.gz) |
| bundle sha256 | `5242b95ae6903d8246c9afa6079681c62b22efa42568ff87e91a326ea14b5a34` |
| build | [CI run `31987898232`](https://github.com/misko/plutosdr-fw/actions/runs/31987898232) |
| detailed plan | [`SPF_LIBIIO_METADATA_V6_RC3.md`](https://github.com/misko/plutosdr-fw/blob/ff999e906018966557e275f8ec96e3c490869de8/SPF_LIBIIO_METADATA_V6_RC3.md) |
| source manifest | [`libiio-frame-metadata-v6-rc3-source.yaml`](https://github.com/misko/plutosdr-fw/blob/ff999e906018966557e275f8ec96e3c490869de8/manifests/libiio-frame-metadata-v6-rc3-source.yaml) |

### What RC3 changes

For #32, RC3 fixes a confirmed unbounded `pthread_join()` in metadata-sampler
teardown by imposing a 500 ms deadline and exiting only the owning daemon if
the worker cannot be safely reclaimed. iiOD is supervised and can restart
without rebooting Linux. RC3 also records boot and iiOD generations and retains
kernel-console and userspace pmsg evidence in ramoops across a watchdog reset.
The reported whole-board reset is real, but the existing evidence does **not**
prove that the teardown defect caused it; the new diagnostics are intended to
distinguish a daemon failure, kernel stall, watchdog reset, and power event.

For #33, the kernel exposes the factory eight-byte UID of a confirmed
W25Q256JV through `spi-nor/unique_id`. Userspace preserves the historical
Micron serial byte-for-byte and encodes a Winbond UID as
`winbond-<16 lowercase hex>`. Missing, malformed, all-zero, and all-ones IDs
fail closed before gadget bind, preventing the former empty-serial and repeated
empty-hash MAC behavior.

### Validation and promotion blockers

The source graph, native identity fixtures, bounded-teardown unit test, iiOD
supervisor tests, ARM kernel objects, Pluto DTB, FPGA build, packaged firmware,
and artifact attestations pass offline. Routed timing is WNS 0.504 ns and WHS
0.014 ns, with zero failing endpoints.

Promotion still requires RAM-only hardware validation:

1. On one Micron and one W25Q256JV board, verify nonempty, stable, distinct
   USB/IIO serials; agreement across `/etc/serial`, configfs, and libiio; and
   distinct locally administered MAC addresses.
2. Run the exact #32 two-radio, 936-slot repeated retune/capture/close soak with
   no boot-ID change, unexplained iiOD-generation change, metadata failure, or
   resource growth.
3. Force iiOD termination and prove supervised recovery without a boot-ID
   change and with the iiOD generation advancing.
4. Force a watchdog reset and prove that the previous kernel console and pmsg
   records are present in `/sys/fs/pstore`.

RC4 qualification additionally found that the prior 256 MiB default CMA pool
cannot be placed around Pluto's fixed ramoops region. The resulting zero-CMA
boot makes 4 MiB IIO receive blocks fail as high-order page allocations. RC4
uses a 64 MiB CMA pool and requires successful repeated USB and local-IP 4 MiB
captures, with no allocator warnings, before promotion.

## v0.38-plutoplus-spf-libiio-metadata-v5

Hardware-qualified on two PlutoPlus units and persistently flashed on
2026-08-12. This is the current stable baseline while v6 RC3 remains a
RAM-only candidate. It adds capture index, hardware sample sequence/time
anchor, start/end gain and RSSI, and in-frame gain observations to ordinary
libiio buffers over USB and IP/TCP without changing the IQ byte layout.

| | |
|---|---|
| release | [`v0.38-plutoplus-spf-libiio-metadata-v5`](https://github.com/misko/plutosdr-fw/releases/tag/v0.38-plutoplus-spf-libiio-metadata-v5) |
| firmware source | `d7c87a9a28094ee6f0b23cb47df9ff737b5a69d8` |
| DFU sha256 | `948b46506febacb087f3955be86015e074f8c0e3370a9dfc6a942e735d97f882` |

The qualified continuous metadata limits were 2 MS/s over USB and 3 MS/s over
IP/TCP on the tested hardware and network. Both radios passed the complete host
libiio 0.25 and 0.26 matrices, rebooted from QSPI, retained the exact v5
identity, and passed the post-reboot USB/TCP metadata smoke. Its later field
reports are tracked in #32 and #33; v6 RC3 is the candidate corrective release.

## v0.38-plutoplus-spf-gain-series-v4

Hardware-qualified on two PlutoPlus units on 2026-08-11, both RAM-booted and
persistently flashed.

### Identity

| | |
|---|---|
| firmware source | `95e952326e6a1b0547897a67ec041df7ff783a28` |
| `device-fw` | `v0.38-plutoplus-spf-gain-series-v4` |
| DFU sha256 | `6920c58bedcdeafabd083efa7e961834b01b3c78e1eb30acbdd0f4e0b24b14d7` |
| bundle sha256 | `0ef5024424c5d7c0e708be2dfa0499bfb1785712fdec16a3c8573b80d3b08968` |
| build | CI run `31513472001` |

### What changed since RC17

**The version label, and nothing else in the source graph.** All five submodule
pins — buildroot, hdl, hdl-quantulum, linux, u-boot-xlnx — are byte-identical to
RC17. RC17 shipped stamped `v0.38-plutoplus-spf-gain-series-v4-rc16-7-g1f3fe`
because `git describe` ran before its tag existed and therefore named the
*previous* release. This build stamps the intended string explicitly.

**This is not a byte-identical rebuild of RC17, and should not be described as
one.** The release commit is `95e952326`, not RC17's `1f3fe0cbe`: same firmware
source plus the release tooling that pins the version string. The build
timestamp differs. What is reproduced is every embedded identity, not the image
hash.

### Offline validation

`PASS OFFLINE` on all gates: source graph, host preflight, coherent-counter
simulation, clean Vivado FPGA rebuild and XSA export, routed timing
(WNS 0.504 ns, WHS 0.014 ns — the same figures RC17 reported), timestamp FIFO
bus-skew constraints, no CDC-10 combinational-before-synchronizer paths, DFU
suffix / FIT layout / XSA layout / packaged-rootfs identity, packaged ARM gadget
binaries and mass-storage legal page, and final SHA-256 verification.

### Hardware validation

Two PlutoPlus units, serials `104000bac495…` and `1040007c4a94…`.

| Phase | Gates |
|---|---|
| RAM-booted | 16 / 16 |
| Persistently flashed to QSPI | 16 / 16 |
| After host reboot | 9 / 9 |

Coverage: direct-USB v2 baseline (6), TX2 loopback at 30 dB attenuation (2),
protocol-v3 including all four direct-IP gates and the V7 zarr round trip (7),
and the v2-frames V7 zarr round trip (1). Every firmware identity was confirmed
with `hw_serial` asserted on the same connection, because a RAM reload rotates
both DHCP leases and USB addresses.

Representative measurements:

- **TX2 loopback** — coherence 0.99999914, tone SNR 21.6 / 32.6 dB, phase
  difference −6.79° with within-capture standard deviation 0.048°.
- **direct-IP** — fitted sample rate 3,000,196 Hz against 3 MS/s nominal
  (+65 ppm) from 9 anchors, frame-time uncertainty 380 µs.
- **buffered burst** — 48 frames, 201 MB payload, zero duplicate fragments,
  zero expired, zero rejected, zero receive-queue overflows.

Persistence was verified across a wall power cycle and a host reboot, not only
across the flasher's own reset.

### Known caveats

**The buffered-burst throughput gate passed by 1.5%.** Aggregate 20.30 MiB/s
against a 20.0 MiB/s floor; the gate scores the aggregate, but cycle 0 alone ran
at 18.45 MiB/s, below the threshold, rising to 21.89 by cycle 2. This was a
3-cycle run, where a slow first cycle carries more weight than in the 20-cycle
configuration RC17 was qualified with. Treat first-cycle throughput as warm-up,
and prefer more cycles when measuring.

**The time-anchor uncertainty gate is capture-length dependent.** At 16 frames ×
524288 samples the fitted clock reported 5.28 ms uncertainty against the 5.0 ms
default, because `fit_sample_clock` uncertainty grows with extrapolation beyond
the anchor window. This is parameterisation, not a defect — the same tests pass
at their intended 3 × 32768. Do not run the smoke gates at burst parameters.

**The gadget SHA is unchanged from RC17** (`2e8e40ade5dcf3c7880a5ebb58419ad7c37ed552`).
Version-conditional flashers that compare device-fw *and* gadget SHA can still
distinguish the two, but anything keying on the gadget SHA alone cannot.

**Not covered by this qualification:** AD9361 RF-DC tracking (4 tests, writes
shared chip state), gadget-supervisor crash recovery, interrupted-collection
fail-closed behaviour, the parallel two-radio direct-IP rate ladder, and the
mixed-transport frequency soak. These re-prove RC17-era behaviour rather than
catching build-environment drift, which was the risk this release carries.

### Flashing

Persistent installation writes **only `pluto.frm` to `/dev/mtdblock3`** (the
`qspi-linux` FIT partition), via the on-device mass-storage updater. Never flash
`boot.frm` or a full `*-fw-*.zip`: those rewrite the FSBL/U-Boot in
`mtdblock0/1`, which is the source of the historical PlutoPlus v0.38 bricks.

Two traps worth knowing, both of which report success while doing the wrong
thing:

1. A version-conditional flasher that reads the *active* firmware will skip
   every radio when a matching image is already RAM-booted — precisely the state
   left by a RAM-boot acceptance campaign. Reboot to QSPI first.
2. `/opt/VERSIONS` is not proof of a successful flash. A RAM-booted radio reports
   the new string regardless of what is in `mtd3`. Only a power cycle followed by
   a re-read proves persistence.

---

## Version history in detail

### `v0.38-plutoplus-spf-gain-rssi-v2` — 2026-07-26

The first direct-USB capture firmware. Adds the versioned v2 metadata frame
carrying per-buffer RX1/RX2 gain and RSSI endpoint snapshots, while retaining
standard USB-IIO for radio configuration. Tested with a single PlutoPlus.

Firmware `dd6b1f4d`, buildroot `6d5b0298`, gadget `54610e01`.
DFU sha256 `f3cd4d68…`.

Its release notes carry a provenance caveat worth remembering: the binary was
built and tested *before* the source-publication commit existed, so a clean
rebuild yields a different checksum because the version text embeds Git state.

### `v0.38-plutoplus-spf-gain-rssi-fingerprint-v1` — 2026-07-28

Adds a passive gadget build-identity query, so a host can bind a hardware
compatibility fingerprint at boot. The query starts no RX/TX DMA and does not
modify RF state. First release on the Quantulum PlutoPlus timestamp HDL.

### `v0.38-plutoplus-spf-gain-rssi-fingerprint-v2` — 2026-08-02

Fixes simultaneous dual-Pluto startup on Raspberry Pi hosts running the default
16 MiB usbfs memory pool — the gadget had been advertising the uint32 arithmetic
ceiling rather than the frame size it actually supports.

- advertises the supported 524,288-sample dual-RX limit
- rejects oversized versioned RX requests in the gadget
- bounded finite-stream buffer allocation

Validated on Rover 3 with two radios: 5/5 on the original simultaneous-open
regression, 4/4 focused, and a pass on the exact release artifact.

Firmware `7b7fb140`, gadget `27a7eed7`. DFU sha256 `5f8220bc…`.

### `v0.38-plutoplus-spf-gain-rssi-fingerprint-v3` — 2026-08-02

Supervised recovery of a crashed direct-USB gadget: bounded UDC unbind,
readiness-checked restart, rebind — while keeping standard USB-IIO available for
control. Recovery preserves serial, physical path and boot ID while producing a
fresh process nonce.

Qualified on Rover 1 with two radios: simultaneous production-size capture, 20
lifecycle cycles per radio, rolling streams, 3/3 SIGKILL recovery per radio.

Firmware source `dac99758`, **built from candidate `f53dd006`**, buildroot
`f37fe105`, gadget `2072e1d0`. DFU sha256 `86f2115e…`.

> The v3 tag points at `dac99758`, but the shipped binary was built from
> `f53dd006`, three commits earlier — so `git checkout <tag>` gives source that
> did not build that release. This is also why the image reports
> `…-fingerprint-v2-8-gf53d`: `git describe` ran before the v3 tag existed.
> Tagging before building prevents both.

### `v0.38-plutoplus-spf-gain-series-v4-rc1` — 2026-08-09 — **hardware rejected**

First protocol-v3 gain-series candidate. Retained for provenance, never promoted.

Protocol-v3 RX failed on **both** radios before the first bulk frame: DMA began
filling before the ARM gain sampler finished starting up, leaving the first IQ
frame with zero overlapping gain observations. The gadget failed closed, which is
the correct behaviour.

Firmware `d0e29715`. DFU sha256 `53a24a19…`.

### `v0.38-plutoplus-spf-gain-series-v4-rc2` — 2026-08-09 — offline only

Carries RC1's fixes: bounded startup-frame alignment in USB and IP, plus paced
direct-IP UDP batches. Offline validation passed with WNS 0.076 ns, WHS 0.008 ns.
Never completed a hardware campaign.

Firmware `aed638ff`. DFU sha256 `8aa50f09…`.

Its notes record a measurement that still holds: a steady 524,288-sample frame
carries roughly **18–20** CPU gain observations, not one every 2,048 samples,
because local register-read speed is the limiting factor.

### `v0.38-plutoplus-spf-gain-series-v4-rc11` — 2026-08-09 — qualified

First protocol-v3 candidate to pass on hardware. Production protocol-v2 baseline,
persistent 2R2T verification, and eight independent two-radio volatile loads
without shared-hub failure.

Firmware `8fd497c3`, gadget `e14eae63`. DFU sha256 `4caca323…`.

### `v0.38-plutoplus-spf-gain-series-v4-rc12` — 2026-08-10 — qualified

Adds direct-IP frame/timing parity and verified TX mute after every transition.
Campaign: three independent shared-hub RAM boot epochs, physical TX2 loopback
after every boot, protocol-v2 compatibility, 100 fresh protocol-v3 STARTs per
radio, simultaneous direct USB, 100 production-sized V7 records per radio,
malformed direct-IP datagram survival. Both radios were restored to the preserved
QSPI image and passed 6/6 post-rollback tests.

Firmware `fa5f95f0`, gadget `e14eae63`, direct-IP gadget `e44821f6`.
DFU sha256 `2209e23c…`.

### RC13 – RC15 — never released

Source tags exist (`gain-series-v4-rc13-source/…` through `rc15`) covering
direct-IP performance and UDP GSO work, but no release was published and no
hardware campaign completed against them.

### `v0.38-plutoplus-spf-gain-series-v4-rc16` — 2026-08-10 — qualified

Direct-IP throughput work. Campaign added a **320-frame / 1.25 GiB maximum finite
direct-IP burst at 21.33 MiB/s with zero loss or reassembly errors**, on top of
RC12's gates. Both radios restored to the preserved QSPI image, 6/6 post-rollback.

Firmware `867e1854`, gadget `2e8e40ad`, direct-IP gadget `7cae12eb`.
DFU sha256 `27aca409…`.

RC16 was later found to have a **control-rearm failure** under sustained
low-rate simultaneous sessions, which RC17 fixes.

### `v0.38-plutoplus-spf-gain-series-v4-rc17` — 2026-08-10 — qualified

Replaces the blocking direct-IP control lifecycle with explicit worker ownership,
readiness and cleanup handshakes, bounded request replay, stale-request
rejection, and safe legacy/v3 DMA exclusion.

Campaign: three independent two-radio RAM boot epochs, physical TX2 loopback on
both radios after every boot, protocol-v2 compatibility, 100 fresh protocol-v3
USB starts per radio, simultaneous direct USB, 100 production V7 records per
radio, malformed direct-IP recovery, and a 20-cycle buffered direct-IP burst.
A separate low-rate regression ran **120 simultaneous radio sessions from 1–3
MS/s without the RC16 control-rearm failure**, and a 1–30 MS/s ladder completed
66 more finite sessions with no integrity or lifecycle failures.

Firmware `1f3fe0cb`, gadget `2e8e40ad`, direct-IP gadget `b066059e`, buildroot
`56b7bc54`. DFU sha256 `88a606f1…`.

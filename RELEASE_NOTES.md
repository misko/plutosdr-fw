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
| **`gain-series-v4`** | 2026-08-11 | **current** | RC17's source with the version label corrected |

**A note on the numbering.** The trailing number does not mean the same thing
across families. `gain-rssi-v2` names the *direct-USB metadata protocol* version
2. `fingerprint-v1..v3` is a separate series tracking the passive-fingerprint
work, which is why v1 follows v2. `gain-series-v4` is the protocol-**v3** gain
series. Read the family name, not the digit.

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


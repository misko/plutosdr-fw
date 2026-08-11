# Release notes

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

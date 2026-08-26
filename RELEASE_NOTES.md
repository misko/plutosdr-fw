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
| `libiio-metadata-v5` | 2026-08-12 | superseded | frame metadata through the standard libiio USB and IP/TCP transports |
| `libiio-metadata-v6-rc3` | 2026-08-17 | **RAM-only candidate** | bounded teardown/reset diagnostics and Winbond identity support for #32/#33 |
| `libiio-metadata-v6-rc4` | 2026-08-17 | **hardware-qualified, persistent prerelease** | fail-closed TX boot state, recoverable identity diagnostics, and W25Q256FV support for #34/#33 |
| `libiio-metadata-v6` | 2026-08-17 | superseded | final RC4 graph, exact release identity, four-board persistent qualification |
| **`tandem-agc-v7`** | 2026-08-19 | **current hardware-qualified** | paired RX1/RX2 AGC, ABI-2 metadata control, synchronous close, and four-board persistent qualification |
| `tandem-agc-v8-rc1` | 2026-08-21 | **hardware-qualified persistent prerelease** | device-side cached AD9361 temperature in each fresh metadata frame |
| `tandem-agc-v8-rc2` – `rc4` | 2026-08-22 – 2026-08-25 | superseded candidates | bounded batch lifecycle, Linux cleanup, and corrected request/pulse handoff; RC4 was invalidated by the later stale-small-ADC recovery change |
| `tandem-agc-v8-rc5` | 2026-08-26 | **development; no release artifact** | forward-only candidate route and exact-byte build/deploy/evidence gates for the post-RC4 RTL |

**A note on the numbering.** The trailing number does not mean the same thing
across families. `gain-rssi-v2` names the *direct-USB metadata protocol* version
2. `fingerprint-v1..v3` is a separate series tracking the passive-fingerprint
work, which is why v1 follows v2. `gain-series-v4` is the protocol-**v3** gain
series. `libiio-metadata-v5` and `v6-rc3` then move that metadata into the
standard libiio transports. Read the family name, not the digit.

## v0.41-plutoplus-spf-tandem-agc-v8-rc5 — 2026-08-26 — **development; not hardware-authorized**

RC5 is the forward-only candidate for the stale-small-ADC-latch recovery added
after RC4. RC4's protected source lock, routed build, artifact, and hardware
reports therefore cannot authorize the current RTL and will not be moved or
relabelled.

The release route now has an RC5 source manifest plus owner-only build mapping,
an exact candidate/evidence index, a guarded exact-serial RAM deployer, and
candidate-bound release and muted-64-frame lifecycle harnesses. The trusted
package regenerates timing, route, DRC, methodology, CDC, bus-skew, and
utilization reports from the packaged routed DCP and checks their complete
inventory and reviewed resource ceilings against a committed policy. It also
builds, verifies, checksums, and attests a
`pluto.frm` whose FIT bytes must exactly match the candidate DFU. The final
release verifier no longer treats a missing `dfu-suffix` tool as a successful
skipped check.
The RAM receipt additionally requires equal pre/post SHA-256 readback of the
exact `qspi-linux` `/dev/mtdblock3` partition, so a candidate transition cannot
claim unchanged persistent firmware from command intent alone.

Earlier scoped OOC evidence for firmware commit `2d15b897e` validates at WNS
`+3.765 ns` and WHS `+0.079 ns`, with zero failing endpoints. That evidence is
explicitly nonauthorizing for firmware and predates the final RC5 tooling
commit, so clean OOC and integrated routes must be rerun on the eventual
protected RC5 source lock.

No RC5 DFU has been built, deployed, or tested on radio hardware as of this
entry, and no QSPI write is authorized. The current exact-release ABI does not
expose enough internal detector/latch state for a deterministic stale-latch RF
test without adding release-only debug interfaces. RC5 therefore uses the
deterministic RTL suite at both clock ratios as the authority for that internal
FSM and keeps the guarded `BLOCKED` observer as optional diagnostic evidence.
Hardware promotion still requires the complete external paired-behavior,
lifecycle, transient/modulated, soak, teardown, and safety campaign on all four
radios.

## v0.41-plutoplus-spf-tandem-agc-v8-rc1 — 2026-08-21 — **hardware-qualified persistent prerelease**

RC1 adds AD9361 temperature to standard-libiio ABI-2 frame metadata without
changing the 56-byte extension or adding another USB/TCP transaction. A
device-side iiOD worker samples `ad9361-phy/temp0/input` at most once per
second. Each frame copies the cached millidegree-Celsius value when its last
successful sample is no more than ten seconds old; otherwise the one field is
omitted/invalid. Frame capture never performs a temperature IIO read.

The exact release is firmware commit
[`62a5c228a992a286869266ba884979656df82b5d`](https://github.com/misko/plutosdr-fw/commit/62a5c228a992a286869266ba884979656df82b5d),
built and attested by
[run `32533280971`](https://github.com/misko/plutosdr-fw/actions/runs/32533280971).
Its DFU SHA-256 is
`9e88b2bcf28416528bfcf4c92bf10aa59dd01ddab6a6741dc6d78ae7325d9cd3`,
FIT-body SHA-256 is
`ca4cf900d9c52d8da89681d311267c6f114425144369cea522c42487da2b88d1`,
and bundle SHA-256 is
`8918ef4422a897dd32b4778db1c8086c8c7ed3663345227748248117f3bbd96b`.
Routed timing closed at WNS `0.770 ns` and WHS `0.027 ns` with zero failing
endpoints.

The byte-identical artifact was RAM-booted and then persistently installed on
both attached Winbond Pluto+ radios. USB and TCP tandem-HOLD captures reported
temperature on both units. In the 64-frame RAM lifecycle test, 62 frames had a
valid temperature; the first frame from each cold worker correctly omitted it.
Mean metadata capture time was 33.0 and 33.2 ms, synchronous close was 19.2 and
11.1 ms, and ordinary receive handoff was 132.7 and 120.7 ms. A focused cache
trace produced one initial invalid frame followed by five frames with the same
cached value, as designed.

Guarded persistent promotion verified the staged image hash, QSPI FIT bytes,
reboot return identity, exact firmware version, and safe TX state on both
radios. The final command-line readings were 35.965 C and 40.351 C. A host-side
USB return-attestation compatibility bug found during the first RAM run was
fixed in pluto-plus-utils commit `c89fb7a`; the device itself remained on the
expected v8 image and TX-safe state.

This remains an RC prerelease because only the two attached Winbond units were
available. The prior release's four-board, attenuated physical-loopback,
three-band AUTO/event matrix was not repeated for this temperature-only change.

## v0.40-plutoplus-spf-tandem-agc-v7 — 2026-08-19 — **hardware-qualified release**

Tandem AGC v7 controls RX1 and RX2 as one coherent gain pair. Standard-libiio
ABI-2 metadata sessions select HOLD or AUTO, report one ownership epoch and
matched endpoint gains, and expose bounded events, faults, overflow state, and
the active gain-table region. A stalled owner rolls back through the watchdog;
boot and every test exit leave TX1/TX2 at `-80 dB` with DDS disabled.

The exact release is firmware commit
[`e0049c2d0077770eeb1f6850b957878a373623d9`](https://github.com/misko/plutosdr-fw/commit/e0049c2d0077770eeb1f6850b957878a373623d9),
built and attested by
[run `32214045747`](https://github.com/misko/plutosdr-fw/actions/runs/32214045747).
Its embedded identity is `v0.40-plutoplus-spf-tandem-agc-v7`; DFU SHA-256 is
`4fe286f9756e3c721d5322ba9c18831f43ab4678c34bb9ef7f238cbb1236debe`,
FIT-body SHA-256 is
`4c19876d09082adfdbd255726e84be397eb4e18a4c0d96b9722d7d543c2ebae7`,
and bundle SHA-256 is
`5468827aa7eca6badd69a518df6bf70ef4220e3f39cdca66b7ba8e3fb452fbb4`.
Routed timing closed at WNS `0.770 ns` and WHS `0.027 ns` with zero failing
endpoints.

The intermittent pre-slot `EBUSY` release blocker was traced to network CLOSE
ordering in iiOD: an acknowledgement could precede destruction of the
exclusive kernel buffer by its separate worker. libiio commit
[`015e4924113d4996667f80b880c34cbf7d1147de`](https://github.com/misko/libiio/commit/015e4924113d4996667f80b880c34cbf7d1147de)
makes CLOSE synchronous with the real teardown. No retry was added.

The byte-identical artifact was RAM-booted, then persistently written to QSPI
on all four local Pluto+ radios. Each board survived the flash boot plus two
additional guarded reboot epochs with the same serial, USB topology, static LAN
address, tandem ABI, and safe TX state. The final hardware gates passed at
915 MHz, 2.45 GHz, and 5.8 GHz on both RX channels: 12/12 persistent band checks,
the expected gain-table IDs 1/2/3, bidirectional AUTO events, watchdog rollback,
zero clipping, and minimum cross-channel coherence above 0.9978.

Across RAM and persistent modes, the four boards completed 72/72 no-retry
metadata lifecycle cells, 576 retunes, and 1,344 frames without `EBUSY`,
`EPIPE`, a reboot, an iiOD-generation change, or a leaked buffer. Persistent
close latency stayed below 51 ms. Every final readback was tandem IDLE with
zero fault/overflow and TX1/TX2 at `-80 dB`.

This release resolves
[#40](https://github.com/misko/plutosdr-fw/issues/40) and the tandem release
gates tracked in pluto-plus-utils
[#13](https://github.com/misko/pluto-plus-utils/issues/13) and
[#21](https://github.com/misko/pluto-plus-utils/issues/21). The older
[#32](https://github.com/misko/plutosdr-fw/issues/32) 936-slot, three-power-epoch
endurance and reset-diagnostic campaign remains an explicit non-blocking
follow-up. No segmentation code, calibration history, or core SPF production
code changed for this release.

## v0.39-plutoplus-spf-libiio-metadata-v6 — 2026-08-17 — **hardware-qualified release**

v6 promotes RC4's exact component graph with the final embedded identity
`v0.39-plutoplus-spf-libiio-metadata-v6`. Source commit
[`e3700cc7268132eb6baa4bc88d8f3320dc7148b9`](https://github.com/misko/plutosdr-fw/commit/e3700cc7268132eb6baa4bc88d8f3320dc7148b9)
was built and attested by
[run `32045625826`](https://github.com/misko/plutosdr-fw/actions/runs/32045625826).
The DFU SHA-256 is
`8ffbb0bf0912285636ddbcf0b00e12deaca0f55612faf7d29efa067b22e61352`;
the deployment-bundle SHA-256 is
`c4845f769962eff1dadd7639b5cefbaf63b29c06f97678b60624eaf9960c7267`.
Routed timing closed at WNS `0.504 ns` and WHS `0.014 ns`, with zero failing
endpoints.

The exact final artifact was RAM-booted on three Micron PlutoPlus boards and
the front-port Winbond board. All four returned on their expected USB paths and
serials with 2R2T, 64 MiB CMA, TX1/TX2 at `-80 dB`, and all eight DDS controls
zero. The complete direct-USB hardware file passed 6/6 and both physical
TX2-to-tee-to-attenuator-to-RX1/RX2 tests passed across all four boards before
persistent installation.

Only the `qspi-linux` FIT partition was then written: `.14` and `.15` over
Ethernet using verified `pluto.frm`, and `.17` and `.18` through path-pinned
SPI-flash DFU using only `firmware.dfu`. Every radio retained its identity and
LAN address, booted v6 from QSPI with `fit_size=C2BE33`, and survived a second
independent reboot.

Post-persistence qualification passed the direct-USB hardware file (6/6), 64
standard-libiio USB/TCP ordinary/metadata cells at 1/3/10/30 MS/s, repeated and
simultaneous protocol-v3 capture, V7 Zarr round-trip, the `.14` 16-frame/64 MiB
direct-IP burst, and both physical TX2 loopback tests. Final readback on every
board showed TX1/TX2 at `-80 dB`, eight zero DDS controls, unchanged boot IDs,
and healthy CMA.

During the final persistent run, the front-port `.14` host link dropped once.
Firmware recovered exactly as designed: Ethernet and the Linux boot ID stayed
live, CMA was released, and the supervised gadget returned on path `3-10.2`
with the same serial. The host's five-second rediscovery budget was shorter
than the firmware's ten-second missing-STOP watchdog plus USB re-enumeration.
SPF [commit `f1c297da`](https://github.com/misko/spf/commit/f1c297da)
extends that bounded host budget to 15 seconds; its receiver unit file passed
27/27 and the formerly failing four-radio hardware file then passed 6/6.

## v0.39-plutoplus-spf-libiio-metadata-v6-rc4 — 2026-08-17 — **hardware-qualified persistent prerelease**

RC4 completed four-board RAM and persistent qualification for
[issue #32](https://github.com/misko/plutosdr-fw/issues/32),
[issue #33](https://github.com/misko/plutosdr-fw/issues/33), and
[issue #34](https://github.com/misko/plutosdr-fw/issues/34).

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

Four-board receive stress reproduced the front-port radio's USB disappearance
without a radio reboot: Ethernet `.14` and the boot ID stayed live, but the
finite direct-USB worker retained 32 MiB CMA and direct-IP START failed with
`-EIO`. RC4 now arms a ten-second finite-write watchdog after the final DMA
submission and keeps it armed until the host explicitly sends STOP. A short or
failed write, or a missing STOP after host link loss, invokes normal cleanup
and the existing supervised UDC rebind. The same investigation found and fixed
a provenance error where the manifest named gadget `907978b0` while Buildroot
compiled `ab270f9e`; the corrected graph consistently pins gadget `1bbe9f0e`.

The corrected RAM-only candidate at commit `e9e675e6d` was built and attested
by [run `32002024507`](https://github.com/misko/plutosdr-fw/actions/runs/32002024507)
(DFU SHA-256
`a92aa9c02cba8292a7f8bb034db455f164cb5428c61ecd14941f70ee45c5763f`).
It completed two exact-image RAM boot epochs on three Micron boards and the
Winbond board. Every boot exposed 2R2T and 64 MiB CMA with TX1/TX2 at `-80 dB`
and all DDS controls zero; the Winbond identity and static `.14` address
survived both boots.

Receive qualification passed 60 production-size 4 MiB lifecycle captures,
all-four gadget crash/recovery, the 1/3/10/30 MS/s standard-libiio TCP matrix,
protocol-v3/Zarr, direct-IP malformed/one-frame gates, and the physical TX2
loopback suite. A deliberately missing host STOP reproduced the formerly fatal
condition and automatically re-enumerated the same front-port serial/path in
12 seconds without a Linux reboot or 32 MiB CMA leak.

After applying the documented transient host tuning (`usbfs_memory_mb=128`,
`net.core.rmem_max=134217728`), five consecutive back-to-back four-radio USB
runs passed both one-frame and three-frame rolling captures. All four USB
device numbers remained unchanged through the post-test watchdog window. The
front-port `.14` radio then passed the maximum 16-frame direct-IP burst: 64 MiB
at 21.90 MiB/s with a 256 MiB effective receive buffer and zero duplicate,
expired, rejected, or overflowed frames.

That stress exposed a host lifecycle defect rather than a new RC4 firmware
failure: an immediate STOP-followed-by-GET_STATUS could collide in the
FunctionFS ep0 hand-off window, causing `LIBUSB_ERROR_PIPE`/`EIO` and a clean
supervised gadget restart. SPF
[commit `f109c204`](https://github.com/misko/spf/commit/f109c204) now checks
status first, avoids redundant STOP on an already-idle worker, and fences a
real STOP with an explicit IDLE assertion. The corrected sequence passed 51
unit/recovery tests and the five-run four-board hardware stress above.

Injected identity failure also passed on the Winbond board: recovery exposed
only labelled network/ACM/storage interfaces with RF services withheld, then
restored the real serial and RF interfaces after removing the RAM-only
injection.

The explicitly labelled release image was rebuilt from firmware commit
`28643c5f185a894a36ac0f37c2271f23acfd9f0e` and attested by
[run `32040690713`](https://github.com/misko/plutosdr-fw/actions/runs/32040690713).
Its embedded `device-fw` is
`v0.39-plutoplus-spf-libiio-metadata-v6-rc4`; DFU SHA-256 is
`dda63fae2fbc969cbb980eb188c621b14fcb55c9d849c36f28e8e4294186d27a`.
All four exact USB paths then RAM-booted that formal image with their expected
serials, 2R2T, 64 MiB CMA, TX1/TX2 at `-80 dB`, and all eight DDS controls at
zero. The complete direct-USB hardware file passed 6/6, including ten
production lifecycle captures per board and both simultaneous tests. The
formal image also repeated the `.14` 16-frame direct-IP burst at 21.88 MiB/s
with zero loss/reassembly/socket-overflow counters. Device numbers remained
unchanged through the final watchdog window. No QSPI writes were performed.

Persistent qualification then wrote only the `qspi-linux` FIT partition on
all four attached PlutoPlus radios. The Winbond `.14` and Micron `.15` radios
were updated over their LAN addresses; the Micron `.17` and `.18` radios were
updated through USB serial-flash DFU. Every board booted the formal RC4 FIT,
retained its expected serial, LAN identity, 2R2T mode, 64 MiB CMA, and exact
`fit_size=c2be37`, then survived a second independent reboot with the same
identity and firmware version.

The post-persistence matrix passed the complete direct-USB hardware file
(6/6), 64 standard-libiio USB/TCP cells across ordinary and metadata modes at
1/3/10/30 MS/s, repeated and simultaneous four-radio protocol-v3 streaming,
the V7 Zarr round trip, the `.14` 16-frame/64 MiB direct-IP burst, and both
physical TX2 loopback tests on every board. Final cleanup and a 15-second idle
window left TX1/TX2 at `-80 dB` and all eight DDS raw controls at zero on all
four radios; the fragile front-port `.14` device retained USB path `3-10.2`
and remained reachable at its static LAN address.

One host-side timing assertion was not stable at its strict 5 ms uncertainty
limit: individual USB control round trips reached 7.96 ms while frame
continuity, fitted sample clocks, and all data-path tests remained valid. A
diagnostic run with a 10 ms reporting ceiling measured 1.01–6.69 ms total
uncertainty across the four radios. This is recorded as host scheduling/USB
latency and does not change the RC4 firmware result.

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

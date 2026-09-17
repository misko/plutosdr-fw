# Feature 103: buffered adaptive scan sessions

## Status and scope

This document is the implementation, test, deployment, and verification plan for
[firmware feature request #103](https://github.com/misko/plutosdr-fw/issues/103).

The first release is deliberately bounded:

- one physical receiver, RX0;
- CI16 IQ;
- frequencies and one analog bandwidth supplied at session setup;
- fast frequency changes using preloaded AD9361 fastlock profiles;
- firmware-owned weighted channel selection;
- periodic, asynchronous host feedback;
- complete-visit admission and buffering;
- fixed-rate sessions at 10, 15, 20, and 30 MS/s;
- optional mixed-rate visits up to 30 MS/s, gated separately;
- no 60 MS/s ADC or exported-IQ mode;
- no RX1 or simultaneous dual-RX operation;
- no independent pilot/decision stream in this release.

The authorized qualification radios are RX0 on serials
`1040007c4a94000211000b009186843ef2` and
`104000b29905000e17000800065934759d`. The implementation request authorizes
bounded qualification and RAM-first deployment on those exact units; persistent
installation remains gated by the acceptance and rollback checks below. At
plan review it was reachable at
`ip:192.168.1.18` and ran `v0.50-plutoplus-spf-counter-rx-v1`, metadata ABI 3,
with exact 50-buffer/200 MB DMA admission. Those observations are preflight
facts and must be re-attested immediately before deployment. Each bounded
campaign must stay within 30 minutes.

## Implementation ledger

This ledger records evidence, not completion claims. The feature remains
default-off and is not ready for deployment until every remaining item is
closed.

As of 2026-09-16:

- Linux branch `codex/feature-103`, commits `8c2927f1bdb6`, `d20eb1d417d4`,
  `5ad4fbc32889`, and `21b0090b491a`, adds descriptor-owner
  scan capability discovery, setup-time RX fastlock profile/frequency/CRC
  attestation, source-counter-bracketed recalls and restoration, plus an
  owner-only coherent source-counter snapshot for dwell pacing independent of
  DMA block completion. Descriptor-close remains the crash fallback. Ordinary
  sysfs LO and fastlock mutation remains excluded while the counter lease is
  owned. Capability discovery now rejects unsupported physical topologies
  before advertising adaptive scan, and a dedicated volatile Rev.C device tree
  removes 2R2T, explicitly selects RX0/TX0, and programs the AXI core for 1R1T.
- libiio branch `codex/feature-103` contains prerequisite direct-segment rearm
  commit `737d910`, scheduler/visit/radio core commit `7657d3b`, deterministic
  capacity simulation commit `556f8f0`, strict wire protocol commit `f75838e`,
  restoration receipt commit `47319ad`, session lifecycle commits `fcb2bfb`,
  `50579ae`, and `fa34857`, and production iiOD data/control integration commit
  `23e4edf`.
- PPU branch `codex/feature-103`, commits `0deb084`, `d5887e8`, and `82310bf`,
  provides byte-identical Python codecs and a strict iiOD client for capability
  discovery, setup, visit/IQ streaming, asynchronous feedback, application
  acknowledgements, terminal validation, and cleanup.
- The scheduler tests replay 256 activity masks and validate source binding,
  bounded feedback acknowledgements, fairness, and deterministic selection.
- The visit-queue tests cover 24,000 DMA-boundary combinations, shared leases,
  gaps, cancellation, age/capacity admission, and release retry. ASan/UBSan
  builds pass with warnings promoted to errors.
- The 300-second real-queue simulation with 50 one-million-sample blocks and a
  200 MB cap measures 97.2% full-session duty at 10 MS/s/240 ms, 100% planned
  delivery at 10 MS/s/120 ms, and 92.2% full-session duty at
  15 MS/s/240 ms with 55 MB/s drain. At 15 MS/s and 60 MB/s it delivers every
  planned visit and reaches 97.2% of measured payload capacity. The 20 and
  30 MS/s overload cells retain only complete visits and emit whole-visit
  skips.
- The new kernel objects cross-compile with the v0.50 ARM toolchain, the UAPI
  layout compiles for ARM EABI5, kernel `checkpatch --strict` and `diff --check`
  pass, and the native scheduler, queue, radio-UAPI, lifecycle, and capacity
  sanitizer tests pass.
- The complete provider-enabled iiOD cross-builds for ARM with the pinned v0.50
  Buildroot toolchain. The legacy provider-disabled iiOD build also passes,
  preserving default-off behavior. The production path uses a source-time
  scheduler thread, scatter/gather visit sends, independent `SCANFEEDBACK` and
  `SCANACK` commands, explicit terminal records, and restoration before final
  transport drain.
- A RAM-only FIT/DFU candidate was assembled from the unchanged qualified FPGA
  and Rev.C DTB, kernel `5ad4fbc32889`, iiOD/libiio `23e4edf`, and the v0.50
  root filesystem. RC1 (`559bc93c…69cbf5`) reached DFU download but did not
  boot because its FIT component hashes used SHA-256 while the deployed U-Boot
  has `CONFIG_SHA256` disabled. Receipt
  `97ab6f9ab7584e7daa9bec90139513b5` records the fail-closed unknown return.
  RC1 is retained immutably and prohibited from persistence.
- Corrected RC2 uses the same payloads and the qualified image's MD5 FIT hash
  algorithm. Its exact identities are DFU
  `fbc591ecbbeac83f8b24fc169fd675a834aa5e00aa5b779e79c7c097d9c61c81`
  and FIT
  `6cf16e9884fc46a362f3fcc9b61ea752c4cac89e69a8b12b3da2dbbe9b602c0e`.
  PPU commit `a58b8f1` admits RC1/RC2 only through immutable RAM profiles and
  tests that no persistent profile accepts either artifact.
- Historical exact-radio evidence then proved its installed Rev.C environment
  selects physical 2R2T (`iio,buffer-counter-metadata-topology-supported=0`).
  RC2 is therefore retained as a diagnostic artifact but is not eligible for
  the live adaptive-scan campaign: it would boot but correctly reject scan
  acquisition. RC3 narrows only the volatile device tree to physical RX0/1R1T,
  keeps the qualified FPGA and fixed-bandwidth design, and also gates
  `GET_SCAN_CAPS` on that topology. Its exact identities are DFU
  `7e5a551f5cfe9fd3d913527c5d4f3bcfb0b5d544301d5e96ab1ca0bbf2701fae`
  and FIT
  `565549cb08a2fe6245bddf863ccc6cfe3516e57a0dba0e2fe77322ca9039e3b2`.
  The FIT is 13,184,047 bytes, uses MD5 component hashes supported by the
  deployed U-Boot, and is byte-identical to the DFU body; the DFU suffix is
  bound to `0456:b673`. RC3 has no persistent companion.
- RC3 was downloaded to the first exact radio in volatile DFU mode, but did
  not return at the exact USB path after detach. Receipt
  `646c738dc1a14124b051c4df1e8ec968` records the fail-closed unknown result;
  no QSPI write occurred. The source-built RC3 DTB was not byte-derived from
  the qualified Rev.C DTB, so RC3 is retired from live use. RC4 preserves the
  qualified DTB byte graph and changes only the three reviewed topology facts:
  remove 2R2T, select RX0/TX0, and select the AD9364-width DDS core. Its exact
  DFU identity is
  `f03f4b25da2e97fe67946aa4250df7ba6e7d04f844a8c8c3d232e2cd62d204be`
  and FIT identity is
  `52f8216403f38e595a5ec8bd8d3509d01a480c5ebc055be5fdd3d836692c2a94`.
  RC4 is 13,188,343 FIT bytes, RAM-only, and must replace RC3 in every live
  boot receipt and campaign evidence check.
- PPU commits `9959935`, `939df83`, and `f0c8f33` add strict whole-stream
  setup/terminal binding, fail-closed truncated-socket tests, exact
  source-counter acceptance metrics, and a scanner adapter whose shadow and
  adaptive modes run the same detector. Shadow mode never transmits feedback;
  adaptive mode sends periodic source-bound active/quiet observations, while
  `UNKNOWN` remains distinct from quiet.
- PPU commits `c937a09`, `224ae47`, `a2ed81a`, and `3a4eaf0` add the bounded
  exact-radio lifecycle: RX0-only factor-one setup through 30 MS/s, independent
  fixed bandwidth, TX mute, fastlock compilation/double-read/CRC binding,
  prepare-failure restoration, campaign-final restoration, application-ACK
  correlation, and a bounded retry for the narrow race between delivery and
  provider completion. The focused PPU suite now passes 134 tests with Ruff
  and strict mypy clean; the ASan/UBSan C policy/session/queue suite also
  remains green.
- PPU commit `731e29e` adds a deterministic hash-bound CI16 energy detector
  with per-visit dBFS evidence for shadow and adaptive runs. A direct newc
  archive parse proves the candidate's final `/usr/sbin/iiod` and
  `/usr/lib/libiio.so.0.25` payload hashes are `72d4aafc…dd695` and
  `ce67ffdc…d5780f`; the base symlinks resolve `libiio.so -> libiio.so.0 ->
  libiio.so.0.25`, and every ARM hard-float runtime dependency is present.
- PPU commits `7955a6d`, `2f60118`, `5b6b577`, `12332a1`, `895376e`, and
  `b4d179d` add private atomic campaign evidence, require the exact successful RC3
  RAM-return receipt, provide an RF-independent controlled-activity detector,
  measure selection-share changes at the firmware-reported application
  boundary, build canonical fixed-rate campaign setups, and attest the RC3
  return as the physical RX0/1R1T layout with topology support `1`. Thus duty,
  feedback transport, and weighting can be qualified independently of ambient
  RF before the energy-detector fidelity lane. The complete focused adaptive
  and deployment-safety suite passes 1,252 tests; targeted Ruff and strict mypy
  checks are clean.
- PPU commit `bd0865f` drains ready application acknowledgements while IQ is
  still streaming. This closes a campaign-length defect in which a 300-second
  run could exhaust the firmware's 64-entry ACK mailbox even though short
  tests passed. A 100-feedback bounded-mailbox regression now proves streaming
  drain, and RC4 is the only candidate accepted by new campaign evidence.
- PPU commits `ee040b2`, `c7d5fe8`, and `8c387c6` move pinned SSH attestation
  before the RAM-transition mutation receipt, require distinct successful RC4
  receipts from both authorized serials, and provide the deterministic
  receipt-gated `pluto-feature103-qualify` command used below.

### Packaging RCA and RC6 qualification reset

The `.18` disappearance is a firmware boot-transition failure, not evidence of
an intermittent USB cable, Ethernet saturation, or a damaged radio. Host USB
logs show the expected runtime-to-DFU transition, a complete download, and the
DFU detach; they do not show link resets, over-current, or enumeration errors.
The device returns to its qualified v0.50 QSPI image after a physical power
cycle. No failed attempt wrote QSPI.

Two independent candidate defects were found:

1. RC3/RC4 accidentally carried an older FPGA bitstream
   (`5c3c6da4...07e4`) instead of the v0.50-qualified bitstream
   (`b96891fa...e93c`). This is a real provenance defect and those images are
   retired.
2. More decisively, RC5 used every byte-exact qualified payload but rebuilt a
   simplified FIT with only `fdt@3`/`config@9` and a noncanonical DTB hash
   node. That image also completed DFU download and failed to return. This
   isolates the common immediate failure boundary to FIT/container generation,
   rather than the feature kernel, DTB, FPGA, or userspace.

These findings produce durable release protections, not a one-off local-image
workaround. `scripts/feature103/package_candidate.py` now hard-pins the
qualified parent DFU/FIT and FPGA/rootfs identities, extracts all three parent
DTBs, preserves the canonical `fdt@1..3` and `config@0..10` graph, leaves DTBs
unhashed like the release FIT, preserves the rootfs inventory, and emits only
RAM candidates. Its offline invariant suite passes. Host tooling quarantines
RC1--RC5 from the executable registry and pins each RC6 stage by DFU hash, FIT
hash, and FIT size.

RC6 must be qualified in this exact fail-fast order:

1. `parent`: the byte-for-byte v0.50 qualified DFU. This proves the USB/DFU/
   U-Boot RAM-transition path independently of packaging.
2. `repack`: the same payloads in the full canonical FIT layout. This proves
   the corrected packager independently of feature code.
3. `kernel`: change only the kernel.
4. `rx0`: additionally change only the reviewed RX0/1R1T Rev.C DTB facts.
5. `full`: additionally replace iiOD, libiio, and `opt/VERSIONS` while
   preserving every rootfs archive entry.

Every stage requires exact serial and USB-path binding, a private pinned SSH
host key before mutation, byte/hash validation before DFU transfer, a successful
return receipt, TX-safe attestation, and no persistent-write capability. Stop
at the first failed stage, retain its receipt and boot-console log, physically
recover the unit, and do not try any later stage. RC6 full identities are DFU
`b7730848...95b6`, FIT `f5283f93...0798`, and FIT size 13,185,399 bytes; the
complete machine-readable identities are in
`build/feature103-rc6/feature103-rc6-manifest.json`.

At the RC6 stage, still required before deployment were physical power-cycle
recovery of the first qualification radio to its unchanged v0.50 QSPI image,
the final full-stage
return on both radios, scanner shadow-mode integration with the production
scanner detector, live mid-session socket failure and RF signal-fidelity tests,
and the bounded per-radio hardware campaigns and rollback verification below.
`192.168.1.17` was explicitly excluded after read-only IIOD attestation proved
it belongs to a third serial. Persistent installation remains prohibited until
both authorized radios independently pass every applicable gate.

### RC8--RC12 live qualification findings

The canonical RC6/RC7 bisection succeeded on serial
`104000b29905000e17000800065934759d`: byte-exact parent, canonical repack,
feature kernel, all-FIT-slot RX0 topology, and full userspace each returned at
the exact USB path with TX-safe receipts. This proved that the earlier `.18`
disappearances were candidate boot/container failures rather than Ethernet
load or random cable loss. The two authorized radios select different FIT
configs (`config@9`/`fdt@3` and `config@0`/`fdt@1`), so the RX0 transform must
remain present in every DTB slot.

RC8 adds Linux commit `104af780d1668dfc239804fba62215930d85af2b`.
Fastlock changes RFPLL registers without updating the clock framework's cached
rate; setup therefore falsely rejected every profile except the last ordinary
LO tune. RC8 validates frequency through the driver's register-backed RFPLL
recalculation instead. Its kernel, RX0, and full stages returned successfully
on the second radio. Host profile compilation now also accounts for the AD9361
ALC byte changing during recall: it validates recalls, reloads the immutable
profile words, and binds the setup to their CRCs. It forces a distinct ordinary
LO transition before leaving fastlock so a matching cached clock value cannot
suppress deactivation.

Live transport then exposed provider defects that simulations had not covered.
libiio commit `7918bb9b77a99a9630e5625c47f59bc0c5f7c5a5`
makes the nominal boundary close idempotent when a DMA gap already made that
dwell terminal; this prevents an explicit `INVALID_GAP` from becoming a fatal
`EINVAL`. Commit `ee2f40d2616581719f9dd5726d0d6ff8334f3a9c`
timestamps feedback from the scan session's mutex-protected coherent counter
watermark instead of issuing a competing owner ioctl from the feedback TCP
connection. RC10 contains both changes. Its full DFU is
`cdd25fcb2fa422d515500f0f144bae0c1d543405e1a0bdbd687b6a939950074a`,
its FIT is
`95760da77b70cefaf1ee9bb0d43c2d012846893f8edee8f50645c39c3c4daf5f`,
and its FIT size is 13,185,287 bytes. The manifest is
`build/feature103-rc10/feature103-rc10-manifest.json` with SHA-256
`2892afdef3e8fd4e7f6b4f728c96fd5b3f023157ebc8aac9ef9b34df7e5ea306`.

RC10 falsified the counter-ioctl crash hypothesis: a two-second adaptive run
again timed out and produced supervisor `status=139`. A 49 MiB ARM core dump
resolved the crash to `spf_visit_queue_reap()` calling
`iio_buffer_block_release()` after the parent buffer had already been
destroyed. The initiating fault was independent: feedback and ACK lookup took
`thdlist_lock`, while the scan stream held that same lock across multi-megabyte
Ethernet writes. Feedback could therefore starve until the host's ten-second
socket timeout. Cancellation then entered the invalid buffer/block teardown
order and crashed.

libiio commit `cb6b02ab4b995a370e54fe2f8a4623357e6413b4` closes both ownership
boundaries. Scan control now uses a dedicated provider-lifetime mutex that is
never held by IQ transport, and teardown returns all provider-owned DMA blocks
before destroying their parent libiio buffer. RC11 contains that fix. Its full
DFU is `d6c129c9562920e671826efeb3d3eebc0cd3cb95ac91d27fa59dadd9e718526c`,
its FIT is
`f4563a66b72c832abec4da78dc688c6153926922212c0de6ea5b2e2449d87067`,
and its FIT size is 13,185,431 bytes. The exact manifest is
`build/feature103-rc11/feature103-rc11-manifest.json` with SHA-256
`e7ba98ced211f9e4cfd02aada94b1183e4be15247238a72a408b5a19bdefb4cc`.

The first 20 MS/s RC11 cell then failed deterministically at visit 1. The
wire record looked like an admitted visit with zero transition, interval, and
Fast Lock CRC fields, but consuming the diagnostic stream exposed terminal
errno `ERANGE`. The owner snapshot was near 3.2 billion samples while the DMA
timestamp and restoration receipt were near 20.4 billion: session creation had
extended a coherent 32-bit owner counter against zero before any full-width DMA
timestamp was available. This loses the counter epoch after a wrap and lets the
DMA producer advance beyond the scheduler's apparent time.

libiio commit `61fdcc844ef8c78b7c3d2b044295565eb8d01ce4` defers visit zero until the
first completed DMA block provides the authoritative 64-bit epoch, rebases the
owner snapshot against that timestamp, discards the pre-retune block from every
dwell, and only then schedules and recalls the first target. Pre-admission
failures now serialize coherent `CANCELLED` records rather than zero-filled
`ADMITTED` placeholders. Native, sanitizer, queue/capacity, transport, and ARM
provider builds pass. RC12 contains this fix. Its full DFU is
`9f401b3b1309db28d67e6b5380e6872f310ed1e2c3d9f073ee6d8aad5ac9fa05`,
its FIT is
`71b397ae007013b3b8ac6a017a4897f617e7db8be097708f61ff6aa0b15feac7`,
its FIT size is 13,187,283 bytes, and its manifest is
`build/feature103-rc12/feature103-rc12-manifest.json` with SHA-256
`27a23f804115f7bb21565ac26b82b34e48d4f2602e0b3ee5ea6d219e3f5edd5e`.

Hardware also showed that the four-buffer default cannot admit a 240 ms dwell
at 10 MS/s with one-million-sample provider blocks and two headroom blocks.
The host now reads the original count, sets 16 buffers for the bounded scan,
and restores the exact original count afterward. This is 64 MB of CI16 DMA
storage and admits 10 and 15 MS/s dwell windows without approaching the 200 MB
queue ceiling. A two-second RC9 no-feedback run delivered seven complete
visits (67.2 MB) with no skips or gaps and exact restoration; active feedback
then reproduced the feedback-control failure now addressed in RC11.

RC9's iiod crash (`status=139`) caused its supervisor to restart FunctionFS.
The radio stayed healthy and reachable over Ethernet, but `/sys/class/udc`
became empty and the host USB device did not re-enumerate. This explains the
observed dropout mechanism: it is a firmware process/gadget recovery defect,
not a corrupt QSPI image. A physical power cycle restores the unchanged QSPI
image. No qualification attempt has written QSPI.

At completion of the adaptive-scan matrix, RC12 was the sole executable
feature-103 candidate and remained RAM-only. RC1--RC11 are quarantined. Before
any persistence decision, both authorized
radios must return RC12 full, independently pass the 10 MS/s `>95%` and
15 MS/s `>=90%` 30-second controlled-feedback cells, show applied ACKs and an
increased active-target selection share, restore radio settings and kernel
buffer count exactly, and pass a power-cycle rollback check.

Both authorized radios passed that RAM qualification gate on RC11. Serial
`1040007c4a94000211000b009186843ef2` returned at USB path `3-11` under receipt
`9ce11b880100456a958329bc18c296ee`; its 10 and 15 MS/s cells retained
95.899% and 95.896% duty. Serial `104000b29905000e17000800065934759d`
returned at `3-8` under receipt `51c45eefcc764a648fc8f09515354b2d`;
its cells retained 95.892% and 95.897% duty. Every cell delivered 119/119
whole visits with zero skips, gaps, or cancellations. The active target's
selection share increased from 66.7% at the first applied-feedback boundary to
73.3--78.4% afterward. Both units retained iiOD PID 213, supervisor generation
1/restart 0, reconciled all accepted feedback with terminal ACKs, restored the
original RF settings and four-buffer count, and exited Fast Lock.

The four private campaign receipts have SHA-256 identities
`852d5357889758561cf1e8616907571bb8264b0d0970aae3fc1300cea34282d1`,
`6b43d03e69b14e69bd661c5915755dc53c590d92714c40eadb04914af7a0b416`,
`90e96e4359c31e65c2a4465474cc7564cfe86d318885112215ca78f015e619ae`,
and `6fefcc6a5b5ebd5d2515a4eef2a63921c4d68f68681ea2d9055ccb91a2ddfeeb`.
A post-campaign reboot returned
the units to the exact persistent firmware recorded before RAM transition:
`v0.50-plutoplus-spf-counter-rx-v1` on `...843ef2` and
`v0.51-plutoplus-spf-iq-direct-async-v5` on `...34759d`, with their original
serials, USB paths, and supervisor generation 1. This verifies volatile
rollback and that qualification did not write QSPI. A true removal-of-power
cold-return check remained a separate physical gate at that point.

Those RC11 receipts remain diagnostic evidence but do not qualify the changed
RC12 bytes. RC12 therefore repeated the full matrix on both radios. Serial
`...843ef2` returned exact RC12 at path `3-11` under receipt
`6583b9ae88904b028fe6c5b540540b99`; serial `...34759d` returned at path `3-8`
under receipt `3b550e55b00a48d193c21b44d99780a9`. The fleet receipt replay binds both to
the RC12 DFU/FIT identities above and rejects every earlier candidate.

At 10 MS/s the two radios retained 95.903% and 95.902% full-session duty; at
15 MS/s they retained 95.892% and 95.897%. Every mandatory cell delivered
119/119 whole visits with zero skips, invalid gaps, or cancellations. Active
target selection increased from 66.7% before its first applied-feedback
boundary to 71.6--78.4% afterward. At 20 MS/s the radios retained 63.92% and
63.91% duty, each delivering 26/39 visits and explicitly skipping 13. At
30 MS/s they retained 31.96% each, delivering 13/39 and explicitly skipping
26. Both upper-rate cells had zero invalid or cancelled visits: overload sheds
only complete dwells, never partial IQ. Every cell restored the exact original
RF state and four-buffer count and exited Fast Lock. Both iiOD processes stayed
at their original RAM-boot PID with supervisor generation 1.

The eight RC12 campaign evidence SHA-256 identities, ordered by radio then
10/15/20/30 MS/s, are
`7b8e174daa000beee40b141cbe99b664c886401dd53cf1ac4421688d8f9a4528`,
`be0c27fa47e81e0e03407ae2715654e683a4adb7c702cec9455b3c7ed9701b28`,
`66655a07f0c6ae3e009eba95a4383b4f0060d20586e9e4bdf4b2564ad0cee3c8`,
`e6f1068b3d6ca452f378c1b128cdb036ea3bdc0b315801f1dba47a9406ec15e0`,
`a10aeaacb670efa768dc927a517a765f0421ed3ae175d51161427b9a0b229861`,
`f323e3d5e12a73e490d20ea48ba4b1d3b27d02e40750bfd593a5594f29b5134b`,
`e3773e167a673d28e579fb927497b57fc21a919987588cd8ef16f61dfa140ea3`,
and `8cf4454e1ea6386e367d59bdb17e8e8f4f1587c5d235d590cea7aabb1efca171`.
The `pluto-feature103-verify` release oracle now pins those eight identities and
replays the two named RC12 RAM-boot receipts. It rejects non-private or
non-canonical evidence, duplicate/missing cells, any earlier candidate,
changed scheduler or queue geometry, inconsistent source-counter accounting,
unreconciled accepted feedback, absent applied active feedback, a
non-increasing active-target share, a failed duty/integrity gate, or inexact
RF/buffer/Fast-Lock restoration. It derives all results from the records rather
than trusting their stored `passed` flags. The exact live replay passes schema
`pluto-plus-utils.feature-103-release-matrix.v1` with both boot receipts and
all eight cells.

Post-campaign reboots returned `...843ef2` to
`v0.50-plutoplus-spf-counter-rx-v1` and `...34759d` to
`v0.51-plutoplus-spf-iq-direct-async-v5`, at their exact USB paths with
supervisor generation 1. This independently verifies volatile rollback and no
QSPI write. The post-RC12 host audit passes 4,757 PPU tests, strict mypy over
125 source files, repository-wide Ruff, 32 firmware packaging/release-oracle
tests, the focused native and sanitizer C suites, and the provider-enabled ARM
iiOD build. The later removal-of-power receipt below closes the cold-return
gate for both radios.

The crash-sensitive live disconnect path also passes RC12. On `...843ef2`, the
host received one complete 9.6 MB visit and then closed the IQ socket without a
protocol close. Provider ownership became available immediately; the first
restoration attempt exactly restored RF state and the four-buffer count and
left Fast Lock inactive. iiOD remained PID 213 with supervisor generation 1.
An immediate fresh 10 MS/s adaptive session then passed at 95.938% duty with
exact restoration; its evidence SHA-256 is
`3ae0254adeec1fdd960ff8424f88660be8cb218e71943caa838896182b096953`.
The subsequent reboot again returned the exact persistent
`v0.50-plutoplus-spf-counter-rx-v1` image at USB path `3-11`.

A later apparent `.18` dropout had a different signature and must not be
conflated with the RC9 iiOD/FunctionFS failure. USB path `3-11` remained fully
enumerated, the serial and persistent v0.50 image were exact, iiOD remained PID
213, and the USB network path answered normally. The physical Ethernet PHY was
up at 1 Gb/s/full duplex with carrier, but the host's neighbor entry was
`FAILED`; after the radio originated one ping to the host, the host learned its
current MAC and `.18` immediately answered at sub-millisecond latency. This is
an asymmetric Ethernet neighbor/startup condition, not an adaptive-scan crash
or corrupt image. The observation does not by itself identify the lower-level
MAC/ARP cause, so future reachability checks should retain USB-path health and
neighbor state instead of classifying every lost LAN ping as a firmware crash.

The physical cold-return gate has a frozen pre-cycle challenge from
2026-09-16T22:36:29Z. At `3-11`, serial `...843ef2` was USB device instance 72,
ran persistent `v0.50-plutoplus-spf-counter-rx-v1`, had `/opt/VERSIONS`
SHA-256 `e6313dcc0e94b121d37b271d72ad621bf2b86936a926f9c4eaea8b2e44e29032`,
boot UUID `804472fc-4ea7-4b12-b071-8450e8e55393`, and iiOD PID/start ticks
213/354. At `3-8`, serial `...34759d` was USB device instance 69, ran
persistent `v0.51-plutoplus-spf-iq-direct-async-v5`, had `/opt/VERSIONS`
SHA-256 `43a3876e0793a632e8b6234e64d9fa3cd38aecc73c5f3af8c2e827234b00992f`,
boot UUID `be2646a3-cbb5-4513-83d5-0670834d7653`, and iiOD PID/start ticks
218/353. A passing post-cycle record must follow an operator-confirmed removal
of every power source for at least ten seconds; it must retain both exact
serial/path/firmware/VERSIONS identities while changing both USB device
instances and boot UUIDs, then pass TX-safe, iiOD, and ordinary-capture checks.
The operator then confirmed both radios were power-cycled. They returned as USB
instances 74 and 73 with new boot UUIDs
`79e8b566-e4cb-4fa8-928a-fba34a37cf49` and
`9f44c0a0-8632-4eb7-8434-141142307918`, while both serials, paths, persistent
firmware versions, and `/opt/VERSIONS` hashes remained exact. USB-anchored SSH
reenrollment attested each rotated key. Both PHYs had carrier, both passed
TX-safe checks, and each persistent iiOD delivered exactly 4,000,000 bytes for
a bounded 1,000,000-sample RX0 CI16 capture, retained its process/start
identity, and left all IIO buffers disabled. The pinned eight-cell RC12 release
oracle then replayed successfully. The private cold-return receipt is
`a03f23216f654107a88b508d62224294.json`, SHA-256
`be85cbcc13ba1fe22c3a78bbc31517ad65a9c9fb42d3dbd8891cb9f9c79284a7`.

### TX2 fixture and RC13 qualification reset

The conducted-RF fixture on each authorized radio is physical TX2 through a
30 dB attenuator and a passive tee into RX0 and RX1. The feature image still
scans one physical receiver, RX0, but its qualification DDS must therefore use
physical TX2 rather than TX1. Linux commit
`eeefe8c6228eede6206197e941aa7024d5ac60d2` makes that one device-tree change:
the volatile feature topology is RX0/1R1T with
`adi,1rx-1tx-mode-use-tx-num = <2>`. It does not enable dual-RX adaptive scan,
change bandwidth during a session, or widen the 30 MS/s release boundary.

RC13 contains that topology correction. Its exact identities are DFU
`1554cc43e2af0efe494eae570140adb57a2162b3cc7aa531e6f00dd9ca9b23f2`,
FIT `a836a026f9e49572805c402ce24886b88beb23dbf12bbad5e7a1cb921f253c25`,
and manifest
`f0b2ceaab0822709e093ca70b51b1b4b28f519f40d613684971dca531f614201`.
The FIT is 13,187,271 bytes. All three DTB slots independently read back RX
selector 1 and TX selector 2. Firmware commit
`3154d637b50e79d9d751c0c83ade0037ad99c293` binds those facts in the package
manifest and static packaging oracle. RC13 is RAM-only and has no persistent
profile.

PPU commits `c857c900945359adb3f5124b9021848bc61e4835` and
`81d01297a267cad1d52bcb2bc0f832aefc87969e` add a fail-closed fixture oracle
and an opt-in exact-serial hardware test. The oracle requires one stable tone
on both receiver legs; it checks frequency/alias, SNR, level, clipping,
cross-leg coherence and balance, plus early/middle/late stability. Synthetic
tests reject either missing leg, the wrong or negative alias, excess imbalance,
settling or fading, and clipping. Hardware initialization calibrates while
muted, applies a bounded TX2 attenuation while DDS is off, enables DDS only
after the two-RX topology is proven, and always disables DDS and returns both
TX gains to -80 dB in cleanup.

Both persistent images were deliberately placed in verified 2R2T mode only to
test the physical fixture. With TX2 gain -10 dB and the 30 dB attenuator
(40 dB effective attenuation), serial `...843ef2` measured a 100,020.926 Hz
tone at -16.570/-17.190 dBFS with 34.655/34.729 dB SNR, zero clipping, and
0.999951 coherence. TX1 produced only the rejected noise floor. Serial
`...34759d` measured 100,020.926 Hz at -27.391/-25.653 dBFS with
32.383/33.121 dB SNR, zero clipping, and 0.999745 coherence. The combined
exact-serial hardware test passed, and both radios finished with TX1/TX2 at
-80 dB and DDS disabled. A subsequent read-only check found four RX scan
channels on each persistent 2R2T image and both TX gains still at -80 dB.

This evidence validates the fixture, the TX2 port choice, and the host-side
signal oracle; it does **not** transfer RC12's adaptive-scan qualification to
changed RC13 bytes. RC12 remains the fully matrix-qualified historical
candidate. RC13 becomes promotable only after it repeats, on both radios, the
10/15/20/30 MS/s matrix, feedback weighting, exact restoration, abrupt-client
cleanup, volatile rollback, and removal-of-power cold-return checks. The
10 MS/s `>95%` and 15 MS/s `>=90%` full-session duty gates remain unchanged.

### RC14 main synchronization and live matrix

Before release, the feature branches were refreshed from their current
upstreams. Firmware merge `250b3e2a7` incorporates `origin/main` through PR
#104. PPU merge `159fccd` incorporates `origin/main` through PR #117. libiio
merge `d249dd280dda480f524f37adc9157a24dae2b6d1` incorporates its compatible
`origin/master`, including negotiated direct-async peer limits and synchronous
USB-pipe teardown while retaining the adaptive provider. The Linux repository
has no `main`; its `master` is a 95,293-commit kernel-generation migration from
the qualified Pluto base, so that unrelated migration was inspected, rejected
from this release, and cleanly aborted rather than folded into feature 103.

The merged userspace source changes the release bytes, so RC13 evidence was not
reused. RC14 is the new RAM-only candidate: DFU
`99ae82e5e6a5eb4f02394463112e9d41fd90ff8343cbfbf95a4ec15e97853db1`,
FIT `26db9c700ad5b2cf01a3a9fc841f847bc0d06f7a1660cbbd3f181dcc4bdf048e`,
and manifest
`bd787fe59e7fa6627b4438376e2d8dc00268f5afb5ee5cb8c6d55d3f854d1c22`.
The FIT is 13,200,115 bytes; all three DTB slots independently retain RX
selector 1 and TX selector 2. Firmware commit `b4626fae0` packages this exact
source graph. PPU commits `01a5d36`, `971ac83`, and `d351011` bind the RAM
profile, require RC14 receipts for new campaigns, and pin the resulting release
matrix without changing the historical RC12 receipt verifier.

Both authorized radios returned exact RC14 at their exact USB paths with
TX-safe receipts `03ec88632d854ec68282358f89cdb8d0` and
`c9bad49b41d6423ba2d23eb923182b33`. The eight-cell controlled-feedback matrix
then passed on both radios. At 10 MS/s they retained 95.888% and 95.900% duty;
at 15 MS/s they retained 95.887% and 95.899%. Every mandatory cell delivered
119/119 complete visits with zero skips. At 20 MS/s each delivered 26/39 and
skipped 13 whole visits, retaining 63.921% and 63.906%; at 30 MS/s each
delivered 13/39 and skipped 26 whole visits, retaining 31.960% and 31.957%.
Every cell had zero invalid or cancelled visits, reconciled accepted feedback,
increased the active target's post-application selection share, restored the
exact RF state and four-buffer count, and left Fast Lock inactive.

The pinned evidence SHA-256 identities, ordered by radio then 10/15/20/30
MS/s, are
`114beef6e7bc43ea0b0500335e2e57f2dab169ad60f7bdb17b53698cfdf6b0da`,
`4ca0173b179d6457067be3052bb9da3b04671401a944085056ccdfb4711dd7d9`,
`fba438897f03066d0e8a87731348aad99ef818df78ce9d746dcd462f05d86747`,
`270861e218d728ea7740948069d2c9385485237e27066c4581a979cc4638b82f`,
`85fb3e5f2cbf8ac134ae28ba60660ddf00b942a022881c327ba10a3744a9c35e`,
`27974eeaed663d963d28e52faf8c28e3c34488076a84c9034c97a9b3bbdcfb86`,
`953784c24338ecc120f2308d60f499da0135a5005fddb19635df2e71e80a3c49`,
and `b5578716a78b523ec6af078ff963dec356e4ec6c2fd8332eb7503aeda4696039`.
The RC14 fleet oracle replays these exact private records successfully. One
initial `.18` campaign connection encountered the already-diagnosed stale LAN
neighbor condition; USB and iiOD stayed healthy, a bounded ping restored the
neighbor, and the unchanged cell then passed. `.15` required the same
radio-originated neighbor seed after RAM return.

The matrix closes RC14's performance, integrity, weighting, and restoration
gates. Abrupt-client cleanup also passed on both radios: each transport was
closed after its first complete 9,600,000-byte visit and before the terminal
record, capabilities reopened immediately, the exact RF and four-buffer state
was restored, and Fast Lock was inactive. Fresh three-second recovery campaigns
then retained 95.876% and 95.959% duty. Their evidence SHA-256 identities are
`798d5ac025d475475ec9c526efec968aee2314055160db8fb6d00abc82a8b757`
and `7990deea36bfc74bfb70fe5ae4f9428e42afc74d4c2a7c03bef493c848301609`.

Both volatile rollbacks now pass as well. The first radio initially exposed a
PPU attestation defect: the correct persistent 2R2T return was compared with
the temporary RC14 1R1T topology and was conservatively reported `unknown`.
PPU commit `926b04a` binds the expected return layout from the named qualified
profile and tests both SSH and independent USB/iiOD return paths. Repeating the
exact transition produced successful TX-safe receipts
`ad4e21d24b6b4d01b12c0867a446d919` for serial
`1040007c4a94000211000b009186843ef2` returning to
`v0.50-plutoplus-spf-counter-rx-v1`, and
`0e0ffa2c3a064615a046380219dc3b6e` for serial
`104000b29905000e17000800065934759d` returning to
`v0.51-plutoplus-spf-iq-direct-async-v5`. Both returned with four RX scan
channels and tandem AGC present.

The pre-cold-return boot identities were
`e967484e-91ea-4564-8e4e-fde97676bb35` and
`2a953b5d-0530-4b18-a7ae-560eade0e97e`, respectively. The operator then removed
power from both radios. They re-enumerated on the same physical USB paths as
new device instances `usb:3.99.5` and `usb:3.98.5`, with changed boot identities
`387f7b41-16c8-4452-842e-2095f6a58846` and
`b9ccbbaa-5f97-425b-abde-e16236afdc8e`. Exact-USB and pinned-SSH inspection
confirmed the same serials, exact persistent firmware versions, AD9361, four RX
scan channels, tandem AGC, the live-qualified `ad9361-2r2t-set-attr-pair`
persistent U-Boot tuple, TX-safe readback, and successful 5.8 GHz LO
set/readback/restoration. Fresh bounded dual-RX refills delivered 65,536 samples
per channel and 524,288 wire bytes on each radio in 87 ms and 244 ms. This
closes the operator-confirmed removal-of-power cold-return gate; no RC12
evidence or software reboot was substituted.

The host doctor still reports historical disconnect counters from the deliberate
DFU, reboot, and power-removal transitions. Radio 1 also has two older port-log
errors from the previously investigated bad-image episode. They are not new
post-cold data-plane failures: both fresh post-cold refills, exact identities,
firmware inspections, route restorations, and RF restoration checks passed.

The first v0.52 trusted-build attempt was stopped before publication or radio
deployment when release review found that the generic image path still packed
the ordinary Rev.C device trees. Those bytes would boot, but a radio retaining
its 2R2T environment would correctly omit adaptive-scan capability. The
protected adaptive-scan route now applies RC14's byte-proven RX0/TX2 narrowing
to all three FIT device-tree slots before `mkimage`, and packaging extracts and
revalidates all three DTBs from the final DFU. A regression check confirmed the
transform produces the exact RC14 DTB hashes for RevA, RevB, and RevC, while an
ordinary 2R2T DTB fails the new packaging check. Generic firmware routes remain
unchanged. Only an artifact built after this correction is release-eligible.

That corrected trusted-build attempt then exposed a separate integration-test
link defect before rootfs completion: Buildroot enables
`test_spf_counter_metadata`, but the target did not link the adaptive scheduler,
radio, protocol, policy, and visit-queue objects now called by the provider.
Production `iiod` linked, but the release correctly stopped. libiio commit
`5518228d9181` adds those exact test dependencies; its ARM provider target links
and passes under qemu-arm. Buildroot source lock `e2de8a933b36` pins that commit
and its verified GitHub archive. No failed-build bytes were packaged or loaded.

## Desired behavior

The host defines the legal scan at setup. Firmware then owns all dwell-boundary
decisions and continues scanning if the host is delayed or disconnected.

```text
setup: frequencies + fixed bandwidth + dwell/rate pattern + baseline weights
                                      |
                                      v
firmware selects target -> fastlock recall -> settle -> complete valid dwell
                                      |
                                      v
host receives complete visit(s) -> analyzes IQ -> periodically sends feedback
                                      |
                                      v
firmware validates feedback -> updates weights -> applies at a later boundary
```

The host reports what it observed. It does not directly command the next hop.
An active observation increases that channel's probability of being selected;
quiet observations decay its boost toward baseline. Minimum exploration and
maximum-revisit constraints prevent starvation.

Frequency selection and IQ sample-rate selection are separate decisions. The
session has one analog bandwidth. Hopping changes only the LO using the
setup-time fastlock profiles; it must not rewrite bandwidth or perform ordinary
LO configuration in the acquisition loop.

## Architectural principles

1. **Negotiate before allocating.** Reject unsupported topology, rates,
   bandwidth, schedules, queue bounds, or feedback guarantees before touching
   the radio.
2. **Admit complete visits, not arbitrary frames.** An admitted visit is
   delivered intact or explicitly invalidated by an unexpected acquisition
   fault. Congestion produces an intentional whole-visit skip.
3. **Keep control independent of IQ draining.** Feedback must not wait for a
   finite IQ segment to drain or rearm.
4. **Bound both bytes and age.** A large but stale queue is not useful to an
   adaptive scanner.
5. **Preserve exact source time.** Retunes, settling, valid IQ, intentional
   skips, and unexpected gaps remain distinguishable intervals.
6. **Acceptance is not application.** Firmware reports both whether feedback
   entered the mailbox and the first dwell on which it influenced selection.
7. **Fail closed.** Unknown versions, mixed runtime pins, wrong sessions, and
   unschedulable requests are rejected rather than coerced.

## Versioned session contract

Introduce a new major session version. Existing HOPR/HOPS/HOPT versions and
metadata ABI 3 semantics remain unchanged.

### Capability discovery

The provider advertises at least:

- supported request, visit, feedback, acknowledgement, and terminal versions;
- RX masks and simultaneous-RX restrictions;
- fastlock/profile capacity;
- supported physical and exported rates;
- dwell bounds and granularity;
- fixed-bandwidth requirement;
- DMA and optional DDR capacity;
- output formats;
- queue byte and queue-age limits;
- feedback mailbox capacity and maximum accepted age;
- guaranteed receipt-to-application bound for admitted configurations;
- supported overload and fallback policies;
- source-counter clock and rate-mapping model.

### Setup request

The request contains:

- session ID, policy generation, request version, and request digest;
- RX0 selection and CI16 format;
- the single session analog bandwidth;
- total source-time duration;
- valid dwell duration, separate guard and filter-settling bounds;
- channel IDs, RF frequencies, optional digital offsets, gain, and fastlock
  profile data or validated profile identities;
- baseline channel weights;
- minimum exploration and maximum revisit settings;
- allowed dwell-rate sequence or a deterministic repeated pattern;
- maximum dwell extension, if enabled;
- queue byte, queue age, and overload behavior;
- feedback maximum age and application-delay request;
- deterministic scheduler seed for replayable qualification.

Admission verifies every frequency/profile and reads back its identity before
arming. The provider computes the worst-case memory and byte-rate budget and
returns the exact admitted contract. It never silently reduces a rate, changes
bandwidth, changes RX, or alters a policy bound.

### Visit and execution records

Every planned dwell reaches one explicit outcome:

- `DELIVERED`: complete valid IQ is present;
- `SKIPPED_CAPACITY`: no complete buffer reservation was available;
- `SKIPPED_AGE`: admitting it would violate the queue-age bound;
- `SKIPPED_POLICY`: a pre-authorized lower-rate or deferral rule was used;
- `INVALID_GAP`: an unexpected DMA/source gap intersected an admitted visit;
- `CANCELLED` or `FAILED`: terminal lifecycle interrupted the visit.

The record includes session/generation, visit and event sequence, channel,
actual frequency, fixed bandwidth, RX, physical/output rate, source-counter
intervals, valid/guard/settling intervals, filter identity, selection reason,
effective weight, feedback basis, and exact skip/failure reason.

Hop and tuning history is emitted even for visits with no IQ. A terminal record
closes the final visit and accounts for every source interval through cleanup.

## Firmware-owned weighted scheduler

The scheduler runs only at dwell boundaries. It combines soft weights with hard
fairness constraints.

Conceptually:

```text
effective_weight[channel] =
    baseline_weight
    * bounded_activity_boost
    * freshness_decay
    * revisit_urgency
```

Eligible channels are selected by a deterministic seeded weighted lottery.
Hard constraints override probability in this order:

1. ownership, TX safety, counter integrity, and memory safety;
2. session duration and complete-visit admission;
3. maximum revisit and minimum exploration;
4. queue-age and feedback-age limits;
5. adaptive weights and optional dwell extensions.

Initial policy defaults should remain configuration, not wire constants. A
reasonable qualification profile is:

- equal baseline weights;
- active boost up to 3x, with an explicit maximum;
- quiet results decay the boost toward baseline rather than dividing abruptly;
- unknown or unhealthy results do not count as quiet;
- activity boosts decay with source time unless reconfirmed;
- a three-second maximum revisit;
- a nonzero exploration floor for every channel;
- a one-second maximum feedback age at receipt;
- a one-second maximum receipt-to-application delay for an admitted session.

No channel may reach zero probability. An active channel must not monopolize the
schedule. If feedback stops or becomes unhealthy, weights decay to the baseline
distribution and scanning continues.

## Asynchronous host feedback

Feedback may be submitted individually or in periodic batches. A record binds
to the evidence that produced it:

- session ID and policy generation;
- monotonically increasing feedback sequence;
- source visit and event sequence;
- channel ID and exact valid source-counter interval;
- active, quiet, or unknown outcome;
- optional confidence/score or requested bounded adjustment;
- detector configuration digest;
- observation and host-send times where available.

The provider validates ownership, generation, channel, counters, age, and
configuration before changing scheduler state. A newer update may supersede an
older unapplied update for the same channel. Out-of-order updates are allowed
inside a negotiated bounded window; the host is not required to manufacture a
result for every missing visit.

There are two observable responses:

1. A receipt: `accepted`, `rejected`, `duplicate`, `expired`, `superseded`,
   `wrong_session`, or `mailbox_full`.
2. An application event: feedback sequence, old/new effective weight, and the
   first visit and source counter whose selection considered the update.

The mailbox is bounded by count, bytes, and age. Overflow rejects the new item
without corrupting capture ownership. Feedback never relabels IQ already
acquired.

## Complete-visit buffering and transport

The current direct-async mechanism is a frame FIFO. The new provider adds a
visit layer over continuously acquired DMA blocks.

Before starting a valid interval, it reserves the worst-case number of leases
needed through the visit's end and its closing boundary. It admits the visit
only when:

- enough leases and descriptor slots are free;
- projected buffered bytes stay within the negotiated cap;
- projected oldest-visit age stays within the negotiated cap;
- the requested rate-pattern budget remains schedulable.

Completed visits should be represented as scatter/gather slices over owned DMA
blocks. Boundary blocks may be reference-counted by adjacent visits. This avoids
making a mandatory ARM-side copy at the full source rate. A lease is released
only after all visits referencing it are sent or explicitly discarded.

The IQ data command remains active for the session. It does not use short
finite segments whose drain/rearm boundary controls when feedback can be sent.
Feedback uses the session-owned control connection/mailbox concurrently.

At 120 ms, one RX CI16 visit contains:

| Output rate | IQ bytes | Drain time at 60 MB/s |
| ---: | ---: | ---: |
| 10 MS/s | 4.8 MB | 80 ms |
| 15 MS/s | 7.2 MB | 120 ms |
| 20 MS/s | 9.6 MB | 160 ms |
| 30 MS/s | 14.4 MB | 240 ms |

Buffering smooths bursts; it cannot sustain a permanent input/output deficit.
At 20 MS/s the ideal 60 MB/s transport ceiling is 75% before protocol costs.
Admission must intentionally choose which whole visits survive.

## Rate sequences and Ethernet utilization

The host may request a deterministic repeated dwell-rate sequence, for example:

```text
[10, 15, 15, 20, 15, 15] MS/s
```

The provider calculates predicted payload using valid dwell, transition time,
metadata, and terminal drain. A short HOLD preflight measures current transport
goodput. Qualification sequences target percentages of that measured value,
not an assumed Ethernet number:

- 70%: control;
- 85%: normal sustained load;
- 90-95%: intended operating region;
- 100%: capacity boundary;
- 105-115%: deliberate overload.

The rate-sequence compiler returns the exact repeated sequence, expected bytes,
expected utilization, rounding error, and whether it can meet all revisit and
exploration constraints. Runtime admission uses observed drain rate and queue
age, so clustered 20/30 MS/s visits can be deferred even if the long-term
average is feasible.

### Mixed-rate implementation gate

Fixed-rate 10/15/20/30 MS/s sessions are mandatory. Mixed-rate visits are a
separate promotion gate.

No implementation in this release may use a 60 MS/s ADC clock. One possible
mixed-rate design is a fixed 30 MS/s source clock with:

- 30 to 30 MS/s bypass;
- 30 to 20 MS/s rational 2/3 resampling;
- 30 to 10 MS/s decimation by 3.

The rational path must meet FPGA timing, resource, passband, stopband, phase,
group-delay, reset, and overflow gates. All output samples map to the unchanged
30 MHz source-counter domain. If this path is not qualified, the release still
ships complete-visit fixed-rate sessions and does not advertise mixed-rate
execution.

Fifteen MS/s can be supported as a fixed physical-rate session. It need not be
part of the first fixed-30 mixed sequence unless an independently qualified
30-to-15 path is included.

## Host and application ownership

The metadata/provider and iiOD layers own:

- version and capability negotiation;
- exclusive radio/session ownership;
- fastlock execution and restoration;
- scheduler state and feedback mailbox;
- DMA lease and complete-visit ownership;
- exact source-time, skip, and terminal accounting.

Pluto Plus Utils owns:

- strict C/Python wire codecs;
- exact serial/runtime/capability admission;
- session lifecycle and restoration checks;
- visit decoding and source-counter reconstruction;
- feedback submission and receipt/application correlation.

The scanner owns:

- IQ analysis and detector configuration;
- conversion of scientific results to active/quiet/unknown observations;
- persistence of IQ, execution history, and feedback latency;
- policy configuration exposed to operations.

## Deterministic verification before RF

### Protocol and scheduler

- Golden C/Python byte vectors for capabilities, setup, visits, skips,
  feedback, receipts, applications, cancellation, and terminal records.
- Reject unknown versions, nonzero reserved bytes, unsupported rates, changed
  bandwidth, invalid profiles, wrong RX, and unschedulable bounds.
- Model-based scheduler tests with a deterministic source clock and seed.
- With no feedback, visit shares converge to baseline weights.
- Repeated active feedback materially raises a channel's share.
- Quiet feedback decays that share toward baseline.
- Unknown/missing feedback does not become quiet evidence.
- Exploration and maximum-revisit constraints hold under every activity mask.
- Duplicate, stale, out-of-order, wrong-session, and superseded feedback has
  the specified observable outcome.
- Batched updates reach the same scheduler state as equivalent accepted
  individual updates.
- Identical requests, counters, and feedback produce identical schedules.

### Queue and capacity simulation

Use the real 50-buffer/200 MB geometry with configurable 55-65 MB/s drain,
10/15/20/30 MS/s visits, 120/150/240 ms dwells, measured transition
distributions, network jitter, socket stalls, and bursty feedback.

For 70, 85, 90, 95, 100, 105, and 115% target loads, assert:

- every admitted visit is intact;
- no unadmitted visit is reported as captured;
- skips and unexpected gaps have exact, nonoverlapping intervals;
- queue bytes and oldest age remain bounded;
- predicted and actual byte rates agree within a frozen tolerance;
- sustainable cases deliver every planned valid interval;
- overloaded cases shed complete visits according to policy;
- the executed rate mix remains within tolerance of the requested mix;
- exploration and revisit bounds survive pressure;
- initial and terminal buffered bytes are included in throughput accounting.

Reproduce the current scattered-loss behavior with a frame FIFO, then show that
visit admission converts it into intact visits plus explicit skips. Compare the
result with a calculated whole-visit bound; do not hard-code the historical 19%
result as a universal baseline.

### Ownership and failure injection

- ASan/UBSan and TSan runs where supported.
- Failure at every reserve, acquire, fill, close, enqueue, send, acknowledge,
  release, cancel, restore, and terminal transition.
- Slow consumers, control disconnect, IQ disconnect, daemon death, host death,
  cancellation with queued visits, and reconnect attempts.
- No overwrite, double release, use-after-release, deadlock, cross-session
  mutation, unbounded allocation, or poisoned subsequent session.
- Exact cleanup and settings restoration after every failure.

### Signal and rate fidelity

- Inject tones and pilot-like signals across the passband plus out-of-band
  interferers.
- Compare exported IQ with an independent offline reference.
- Freeze amplitude, passband ripple, stopband rejection, phase, CFO, timing,
  alias, and overflow tolerances before hardware promotion.
- Test rate changes only at visit boundaries and exclude all filter-reset and
  settling samples from valid IQ.
- Verify exact output-to-source mapping through every supported transition.

## Hardware qualification

All runs use the authorized serial, RX0, fixed bandwidth, pinned runtime, and
identical channel/dwell geometry unless the named factor is under test.
Preflight records serial, firmware/FIT, kernel, iiOD, capabilities, TX-safe
state, radio settings, active owners, and available storage. Cleanup verifies
the exact restored state and a fresh ordinary capture.

Before an RC13 adaptive campaign, prove the conducted fixture independently on
the persistent 2R2T image:

```sh
PLUTO_TX2_LOOPBACK_SERIALS="SERIAL_1,SERIAL_2" \
PLUTO_TX2_LOOPBACK_ATTENUATION_DB=30 \
PLUTO_TX2_LOOPBACK_TX_GAIN_DB=-10 \
LD_PRELOAD=.venv/lib/libiio.so.0.25 \
.venv/bin/pytest -q -s tests/hardware/test_tx2_splitter_hardware.py
```

This is an intentional RF-transmission test and therefore requires all three
environment variables. It must resolve both exact serials, prove 2R2T before
transmission, use only physical TX2, observe the tone on both RX legs, and
verify mute/cleanup even on failure. Run the synthetic oracle tests without
hardware first. After the fixture passes, RAM-boot exact RC13 and repeat the
release matrix with new RC13-bound receipts and evidence; the RC12 oracle must
continue rejecting those records until the new matrix identities are reviewed
and pinned.

Use the receipt-gated `pluto-feature103-qualify` command for every cell. It
accepts only the two authorized serials and an exact successful RC12 RAM-return
receipt, requires deterministic session/generation/seed and detector settings,
performs a dry run unless `--execute` and the serial-specific confirmation are
both supplied, writes atomic private evidence, and never writes QSPI. For
example, first inspect a controlled 10 MS/s cell:

```sh
uv run pluto-feature103-qualify \
  --serial SERIAL --uri ip:ADDRESS --ram-receipt RC12_RECEIPT \
  --evidence NEW_EVIDENCE_PATH --mode adaptive --detector controlled \
  --session 1 --generation 1 --seed 103 \
  --rate 10000000 --bandwidth 8000000 --duration-ms 30000 --dwell-ms 240 \
  --frequencies 960000000,1190312500 --weights 1,1 --active-targets 1
```

Repeat with `--execute --confirm "QUALIFY FEATURE 103 SERIAL"` only after the
dry-run JSON binds the intended radio, RC12 hashes, setup, and evidence path.
Energy-detector cells replace `--active-targets` with the frozen
`--energy-threshold-dbfs`. Final fleet promotion requires distinct successful
RC12 boot receipts and independent campaign evidence from both serials.
Replay the complete release matrix with the fail-closed oracle; each option is
required, and the command itself pins the approved evidence identities:

```sh
uv run pluto-feature103-verify \
  --ram-receipt "SERIAL_1=RC12_RECEIPT_1" \
  --ram-receipt "SERIAL_2=RC12_RECEIPT_2" \
  --evidence RADIO1_10M.json --evidence RADIO1_15M.json \
  --evidence RADIO1_20M.json --evidence RADIO1_30M.json \
  --evidence RADIO2_10M.json --evidence RADIO2_15M.json \
  --evidence RADIO2_20M.json --evidence RADIO2_30M.json
```

### Campaign A: transport and complete visits

1. Ten-to-thirty-second smoke cells at 10, 15, 20, and 30 MS/s.
2. A measured-goodput HOLD control.
3. Four 300-second cells changing one factor at a time: current baseline,
   alternate overrun policy, long-lived transport, complete-visit admission.
4. Report both capture-window and end-to-end time including terminal drain.

### Campaign B: weighted feedback

1. Baseline weights with no feedback.
2. Shadow feedback: compute proposals but execute the baseline schedule.
3. Active feedback with controlled active/quiet channel scripts.
4. Delayed, batched, stale, duplicate, and disconnected-host cases.
5. Verify selection shares, exploration, revisit bounds, fallback, receipts,
   and first-applied events.

### Campaign C: capacity staircase

Use 240 ms visits for the principal efficiency gate and run deterministic
sequences targeting 70, 85, 90, 95, 100, 105, and 115% of measured goodput.
Repeat the 90-105% boundary cells enough to establish reproducibility. Include
a clustered 20/30 MS/s pattern followed by compensating 10 MS/s visits.

### Campaign D: mixed-rate promotion

Run only after fixed-rate acceptance and FPGA/offline fidelity gates. Start
with muted or injected-tone short visits, then sustainable low-rate sessions
with isolated 20/30 MS/s bursts. Mixed rate remains unadvertised unless all
counter, filter, timing, queue, and restoration gates pass.

## Metrics

Keep these quantities distinct:

```text
planned-valid delivery =
    union(delivered complete valid intervals) / union(planned valid intervals)

full-session retained duty =
    union(delivered complete valid intervals) / full source-time interval
```

The second denominator includes transitions and intentional skips. Do not
remove skipped time, add overlapping loss categories, or double-count RXs.

Every run reports:

- raw source coverage and payload MB/s;
- complete-visit duty and planned-valid delivery;
- planned, admitted, delivered, skipped, invalid, and cancelled visit counts;
- per-channel/rate time, selection share, and revisit distribution;
- transition, filter-settling, intentional-skip, and unexpected-gap intervals;
- gap-length and contiguous-run distributions;
- queue byte/visit high-water, oldest age, and initial/final occupancy;
- DMA acquisition, metadata, socket, feedback, and terminal-drain timing;
- CPU and memory use;
- observation-to-receipt and receipt-to-application p50/p95/max;
- accepted, applied, rejected, expired, duplicate, and superseded feedback.

## Acceptance gates

### Correctness

- Every nominally admitted visit is delivered intact.
- Every loss or skip is explicit and source-bound.
- No guard, transition, or filter-settling samples appear in valid IQ.
- No channel/rate labels cross a visit boundary.
- Queue memory and age remain inside the negotiated bounds.
- Feedback application meets the negotiated maximum delay.
- No fairness, ownership, restoration, or subsequent-session failure.
- Unsupported configurations fail during setup without changing the radio.

### Duty and utilization

The measured transition fraction in the motivating configuration was about
5.48%. With 120 ms valid dwells, even lossless capture therefore has an overall
duty ceiling near 94.5%. Keep transition-limited duty separate from transport
delivery.

- 10 MS/s, 240 ms dwell: greater than 95% full-session retained duty.
- 10 MS/s, 120 ms dwell: greater than 99% planned-valid delivery; do not require
  impossible greater-than-95% full-session duty unless measured transition
  overhead falls below 5%.
- 15 MS/s: at least 90% full-session retained duty with the declared dwell.
- 20 MS/s: reproducible material improvement over the current complete-visit
  baseline; approximately 70% is the provisional stretch target, to be frozen
  after simulation and measured overhead review.
- Near-capacity sequence: at least 95% of measured sustainable payload goodput
  without violating queue-age or revisit bounds.
- Deliberate overload: 100% integrity among admitted visits and 100% explicit
  accounting of skipped visits.

Numerical tolerances and statistical confidence must be frozen before the
candidate hardware campaign, not selected after observing its results.

## Delivery and deployment sequence

1. Start from a clean worktree and the immutable v0.50 source graph; do not
   build from a mixed submodule checkout.
2. Integrate the direct-async lifecycle recovery and peer-limit negotiation
   prerequisites tracked by issues #101 and #102.
3. Land codecs, capability negotiation, scheduler model, queue simulator, and
   golden tests without enabling the provider.
4. Add fixed-rate complete-visit transport and the independent feedback
   mailbox behind a default-off build option.
5. Integrate PPU and scanner shadow mode.
6. Stage matched iiOD/libiio binaries from temporary storage on a separate
   port against the qualified v0.50 kernel/FPGA where possible.
7. Run authorized fixed-rate and shadow campaigns. Keep stock iiOD available
   for immediate rollback.
8. If kernel or FPGA changes are required, build a hash-pinned source graph and
   RAM-boot the exact candidate before any persistent write.
9. Qualify active weighting and the capacity staircase.
10. Qualify and advertise mixed-rate execution only as the separate promotion
    gate.
11. Publish matched firmware, iiOD/libiio, PPU, and scanner identities with
    immutable manifests and evidence.
12. Permit persistent installation only after offline gates, RAM boot, bounded
    hardware campaigns, exact FIT attestation, reboot, restoration, and scanner
    resumption all pass.

Retain v0.50 and its known FIT as the rollback target through post-deployment
verification. This feature must never imply that metadata ABI 3 alone makes an
arbitrary host/provider combination compatible.

## Explicitly deferred work

- all 60 MS/s ADC and output modes;
- per-visit AD9361 clock reconfiguration;
- RX1 and dual-RX scheduling;
- an independent continuous decision stream;
- packed/lossy IQ formats;
- arbitrary host-directed next-hop commands;
- fleet-wide persistent promotion.

These require separate design and qualification and must not delay the useful
first outcome: high-duty, complete, source-attested visits with fast frequency
hopping and bounded adaptive feedback through 30 MS/s.

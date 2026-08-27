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
| `tandem-agc-v8-rc5` | 2026-08-26 | **rejected; no release artifact** | complete candidate route reached the trusted build, but integrated placement was 17 slices over the available device capacity |
| `tandem-agc-v8-rc6` | 2026-08-26 | **rejected; diagnostics only** | fully routed and timing-clean, then rejected by stale post-route report policy before packaging |
| `tandem-agc-v8-rc7` | 2026-08-26 | **rejected before evidence/hardware** | successful integrated build; bundle rejected because checksum/member order depended on locale and shell-array order |
| `tandem-agc-v8-rc8` | 2026-08-26 | **successful indexed build; not deployed** | deterministic bundle and verified candidate index; hardware transition blocked by an over-scoped serial-specific proof |
| `tandem-agc-v8-rc9` | 2026-08-26 | **successful indexed build; rejected before hardware transition** | removed the redundant transition-proof input; first execute exposed duplicate-IP routing and factory-password transport gaps before reboot or DFU |
| `tandem-agc-v8-rc10` | 2026-08-26 | **successful indexed build; zero candidate deployments** | trusted build and evidence passed; first execute reached DFU but stopped before candidate download because the selected b674 device omitted its USB serial |
| `tandem-agc-v8-rc11` | 2026-08-26 | **successful indexed build; zero candidate deployments** | serialless-b674 topology resolution passed, but dfu-util rejected the single-ID selector before transferring the b673-suffixed DFU |
| `tandem-agc-v8-rc12` | 2026-08-26 | **successful indexed build; observed RAM boot, no deployment receipt; not hardware-qualified** | paired DFU download/detach succeeded on db696, but the ephemeral RAM SSH host key prevented receipt publication |
| `tandem-agc-v8-rc13` | 2026-08-26 | **source-locked; trusted run queued without a job; superseded before artifact/hardware** | removed the unsatisfiable retained host-key pin and advanced the measured RAM receipt to v4 |
| `tandem-agc-v8-rc14` | 2026-08-26 | **successful indexed build; zero RAM transitions; superseded** | native utility ownership was integrated, but live preflight exposed global libiio discovery and capability-name defects before reboot/DFU |
| `tandem-agc-v8-rc15` | 2026-08-26 | **successful indexed build; zero candidate downloads; superseded** | exact DFU transition reached b674, then failed closed on the real-kernel sysfs symlink before candidate bytes transferred |
| `tandem-agc-v8-rc16` | 2026-08-26 | **successful indexed build; observed safe RAM boot, no valid deployment receipt; superseded** | RAM boot and containment checks passed, but the device-plan bridge confused release frame schema v5 with live IIO buffer ABI v2 |
| `tandem-agc-v8-rc17` | 2026-08-26 | **four safe RAM deployments and lifecycle passes; full campaign blocked before USB; superseded** | host-libiio replay resolved the firmware wrapper beneath the distinct libiio repository |
| `tandem-agc-v8-rc18` | 2026-08-26 | **four safe RAM deployments and lifecycle passes; one marginal full-test result; superseded** | trusted build/evidence and muted lifecycle passed on all four; db696 steady characterization found one native-fast-attack cell 0.27332 dB above its quality ceiling, then canonical checkpoint key ordering blocked the authorized retry before USB |
| `tandem-agc-v8-rc19` | 2026-08-26 | **four safe RAM deployments and lifecycle passes; full steady policy rejected; superseded** | resume passed; native-fast cells reached -2.47 dBFS without clipping against the shared -3.0 dBFS ceiling |
| `tandem-agc-v8-rc20` | 2026-08-26 | **trusted build and four RAM/lifecycle passes; full campaign failed; superseded** | 2.45-GHz weak-SNR contamination plus two settle/measurement-boundary oracle failures; no passing full/soak campaign |
| `tandem-agc-v8-rc21` | 2026-08-27 | **successful indexed build and pilot RAM/lifecycle; 1.05-GHz campaign failed; superseded** | exposed FPGA power-period/event-spacing mismatch: 16,400 samples observed where the contract requires 17,408 |
| `tandem-agc-v8-rc22` | 2026-08-27 | **successful indexed build; db696 RAM/lifecycle and 11/11 steady policies passed; transient oracle invalid; superseded** | fixed exact power periods/event spacing; the transient harness rejected a fully retained startup convergence before its stable pre-attack suffix |
| `tandem-agc-v8-rc23` | 2026-08-27 | **active development; not hardware-qualified** | retains RC22 firmware and treats fully accounted startup AUTO convergence as conditioning only, requiring an exact quiet suffix before response timing |

**A note on the numbering.** The trailing number does not mean the same thing
across families. `gain-rssi-v2` names the *direct-USB metadata protocol* version
2. `fingerprint-v1..v3` is a separate series tracking the passive-fingerprint
work, which is why v1 follows v2. `gain-series-v4` is the protocol-**v3** gain
series. `libiio-metadata-v5` and `v6-rc3` then move that metadata into the
standard libiio transports. Read the family name, not the digit.

## v0.41-plutoplus-spf-tandem-agc-v8-rc23 — 2026-08-27 — **active development; not hardware-qualified**

RC23 retains RC22's exact firmware and external source graph. It corrects the
transient evidence policy exposed by RC22 hardware: startup AUTO convergence is
retained and validated as conditioning, but can never prove attack or release
direction. Only the final eight fully-pre-attack frames may anchor timing, and
they must be contiguous, event-free, gap-free, endpoint-stable, RF-stable, and
constant in cumulative transition count. Any transition or hidden evidence in
that suffix remains fatal; the attack/release events and direction proof remain
unchanged.

RC23 keeps exact authorizing centers 1.05, 1.55, 2.05, and 5.8 GHz. The full
2.45-GHz matrix still runs and retains complete evidence, but an isolated
cleanup-verified RF-quality failure is nonbinding. Identity, metadata, missing
evidence, fault/FIFO/overflow, and cleanup failures remain fatal.

RC23 uses branch `codex/firmware-tandem-agc-v8-rc23`, version
`v0.41-plutoplus-spf-tandem-agc-v8-rc23`, manifest
`manifests/tandem-agc-v8-rc23-source.yaml`, package prefix
`plutoplus-spf-tandem-agc-v8-rc23`, and source lock
`refs/tags/tandem-agc-v8-rc23-source/firmware-v1`.

## v0.41-plutoplus-spf-tandem-agc-v8-rc22 — 2026-08-27 — **successful indexed build; db696 RAM/lifecycle and 11/11 steady policies passed; transient oracle invalid; superseded**

RC22 is the forward-only correction for the timing-contract defect measured on
RC21. The power divider now emits a tick every programmed `N` valid samples,
not `N+1`, and the tandem controller can accept a gain decision only on that
tick. With cooldown `N`, consecutive accepted events are therefore separated
by at least `(N+1) * power_measurement_samples`, exactly matching the provider
and release oracle. Cycle-accurate stress tests independently prove a 12-sample
tick and a `17 * 12 = 204` sample cooldown/event interval so either half of the
fix fails closed.

RC22 retains the exact authorizing centers 1.05, 1.55, 2.05, and 5.8 GHz. The
full 2.45-GHz matrix still runs last and retains complete evidence, but an
isolated cleanup-verified RF-quality failure is nonbinding. Identity, metadata,
missing evidence, fault/FIFO/overflow, and cleanup failures remain fatal; RC22
makes no 2.4-GHz RF-performance claim.

Trusted run `33045015785` passed and produced exact candidate evidence. The
db696 pilot passed RAM-only deployment, unchanged-QSPI and safe-state checks,
and the full v5 muted metadata lifecycle. All eleven 1.05-GHz steady policies
then passed across manual fixed gain, native slow attack, native fast attack,
and tandem AUTO, directly proving the RC21 event-spacing defect fixed. The
transient campaign retained a startup AUTO convergence followed by more than
eight contiguous quiet pre-attack frames, but the RC22 host oracle required
every pre-attack frame to remain at transition count zero. That assumption—not
the RC22 firmware—invalidated the phase. RC22 has no passing full/soak campaign
and is not hardware-qualified.

RC22 uses branch `codex/firmware-tandem-agc-v8-rc22`, version
`v0.41-plutoplus-spf-tandem-agc-v8-rc22`, manifest
`manifests/tandem-agc-v8-rc22-source.yaml`, package prefix
`plutoplus-spf-tandem-agc-v8-rc22`, and source lock
`refs/tags/tandem-agc-v8-rc22-source/firmware-v1`.

## v0.41-plutoplus-spf-tandem-agc-v8-rc21 — 2026-08-27 — **successful indexed build and pilot RAM/lifecycle; 1.05-GHz campaign failed; superseded**

RC21 retained the exact RC20 firmware and external source graph. It fixed the
settle-to-measurement evidence boundary with continuous metadata accounting,
one bounded full-attempt restart, atomic retained failure evidence, and a
128 MiB write-on-failure IQ ledger. Its authorizing hardware matrix uses exact
ordered centers 1.05, 1.55, 2.05, and 5.8 GHz. Every radio also runs the same
full manual/native-slow/native-fast/tandem matrix at fixed 2.45 GHz. A complete,
cleanup-verified RF-quality-only failure there is recorded as
`diagnostic_failed` and does not enter the release denominator; any identity,
metadata, missing-evidence, fault/FIFO/overflow, or cleanup failure is fatal.
RC21 made no 2.4-GHz RF-performance claim. Its trusted workflow run
`33041851068` and candidate index passed. The db696 pilot passed RAM-only
deployment, unchanged-QSPI attestation, final safe state, and the full v5 muted
metadata lifecycle. Its 1.05-GHz full steady campaign then stopped at the
zero-cooldown policy because the provider could not prove both AUTO directions
from the retained cadence. A separate instrumented transient diagnostic made
the underlying firmware defect exact: paired events arrived every **16,400**
samples while the published cooldown contract requires **17,408**. The RTL
counted `N+1` samples per power period and allowed decisions between ticks.
RC21 has no passing full or soak campaign and is not hardware-qualified.

RC21 uses branch `codex/firmware-tandem-agc-v8-rc21`, version
`v0.41-plutoplus-spf-tandem-agc-v8-rc21`, manifest
`manifests/tandem-agc-v8-rc21-source.yaml`, package prefix
`plutoplus-spf-tandem-agc-v8-rc21`, and source lock
`refs/tags/tandem-agc-v8-rc21-source/firmware-v1`.

## v0.41-plutoplus-spf-tandem-agc-v8-rc20 — 2026-08-26 — **trusted build and four RAM/lifecycle passes; full campaign failed; superseded**

RC20 retains RC19's firmware implementation, external source graph,
deterministic package, native `pluto-plus-utils` device lifecycle, and every
release safety/evidence guard. It changes one fixed RF-quality policy only:
native fast attack accepts a maximum tone of `-2.0 dBFS`; manual fixed gain,
native slow attack, and tandem AUTO retain `-3.0 dBFS`. Zero clipping remains
mandatory, and SNR, coherence, phase stability, frequency, gain behavior,
metadata continuity, QSPI equality, cleanup, and all TX/fixture limits are
unchanged. The limit is not exposed as an operator-tunable CLI option.

RC20 uses branch `codex/firmware-tandem-agc-v8-rc20`, version
`v0.41-plutoplus-spf-tandem-agc-v8-rc20`, manifest
`manifests/tandem-agc-v8-rc20-source.yaml`, package prefix
`plutoplus-spf-tandem-agc-v8-rc20`, and source lock
`refs/tags/tandem-agc-v8-rc20-source/firmware-v1`.

RC20 locked commit `63108b832a3618631386afdf530f19acb7905bca`,
passed trusted workflow run `33020653933`, and produced candidate index
`326d1c985665fb20f69a5bf00351c833971a15240c6c8c7d187811d4fe96d397`.
All four radios passed RAM-only deployment and lifecycle. The full campaign
never qualified: attempt 1 recorded weak-rung SNR failures at 2.45 GHz without
raw IQ, and attempts 2/3 stopped on settle/measurement-boundary assertions that
discarded the offending frame. RC20 has no passing transient, modulated, soak,
campaign-qualified index, or promotion evidence.

## v0.41-plutoplus-spf-tandem-agc-v8-rc19 — 2026-08-26 — **four safe RAM deployments and lifecycle passes; full steady policy rejected; superseded**

RC19 retains RC18's firmware implementation, external source graph,
deterministic package, device operator, and release guardrails. It changes only
multi-phase checkpoint replay: canonical JSON is allowed to sort phase-object
keys, while resume requires the exact phase-key set and revalidates each stored
phase specification against the current requested plan. RC19 uses branch
`codex/firmware-tandem-agc-v8-rc19`, version
`v0.41-plutoplus-spf-tandem-agc-v8-rc19`, manifest
`manifests/tandem-agc-v8-rc19-source.yaml`, package prefix
`plutoplus-spf-tandem-agc-v8-rc19`, and source lock
`refs/tags/tandem-agc-v8-rc19-source/firmware-v1`.

RC19 locked exact commit `70949a18a7f42d99fdd5356b128f37b7c7fa2b7e`.
Trusted run `33015979913`, attempt 1, succeeded with artifact ID `9625051298`.
Its verified candidate-index SHA-256 is
`f099bdfba1e529730b7012d6a75c995d73165994daaa00501eb2e5bcbca57e81`;
bundle SHA-256 is
`48bc63f64db25352323687f8fa8e2fa8c244a6fff99b7f97344208d83f757919`;
DFU SHA-256 is
`a786dbc78b72e43474485d9af73765fda7e0fd4f9a47a3fadfd98fc1152b3242`;
and FIT SHA-256 is
`cb9d7027b775443bcc99535c96cf38effce132727827c2ba1bc796bf579f9283`.
All four exact radios completed RAM-only deployment with unchanged QSPI and
verified safe state, then passed the 64-frame muted metadata lifecycle plus
cancel/reopen checks.

The full steady campaign then exposed a policy mismatch, not clipping or
signal corruption. Native fast attack produced zero-clipping, high-SNR,
coherent dual-RX captures between `-3.00` and `-2.47 dBFS`; the shared
`-3.0 dBFS` maximum rejected those cells on db696, db620, and R17. Cleanup
passed after every stop. R18 separately saw one strict tandem transition-count
continuity rejection; that rule is unchanged and must pass on retry. RC19 has
no passing full campaign, no soak result, and is not hardware-qualified.

## v0.41-plutoplus-spf-tandem-agc-v8-rc18 — 2026-08-26 — **four safe RAM deployments and lifecycle passes; one marginal full-test result; superseded**

RC18 retains RC17's firmware bytes, external source graph, deterministic
packaging, v5 release/evidence schema, v2 live buffer ABI, and pushed
`pluto-plus-utils` commit
`2654f34eb909904ec65bc0526e0f8977cb30e2ed`. It corrects the durable
host-libiio replay validator to resolve the indexed release wrapper beneath the
firmware runner repository rather than the separate pinned libiio repository.
RC18 uses branch `codex/firmware-tandem-agc-v8-rc18`, version
`v0.41-plutoplus-spf-tandem-agc-v8-rc18`, manifest
`manifests/tandem-agc-v8-rc18-source.yaml`, package prefix
`plutoplus-spf-tandem-agc-v8-rc18`, and source lock
`refs/tags/tandem-agc-v8-rc18-source/firmware-v1`.

RC18 locked exact commit `ac7bbfebe7f0a2d639c8e68bc0efe493f950d389`.
Trusted run `33011655732` succeeded with artifact ID `9623402489`, bundle
SHA-256 `fe4bce0e3d2bc06d1fb814d1f05263e1b6482453957a003b42e03bafddc0f90d`,
DFU SHA-256 `6379598f554c33622b817fd28a5ff34b1bf74b0519d8e4608b315fa0699b105a`,
FIT SHA-256 `e354aedae7c229e3372c1b2799c91c8966dff48f0375af6fccb372b7cdafe012`,
and candidate-index SHA-256
`8eea002ab8267ed4a53cad38cdc926cb961904baea83bb3ec9c3d136ed3360ee`.
All four exact radios completed RAM-only deployment with unchanged QSPI and
the verified safe state, then passed the 64-frame muted metadata lifecycle and
cancel/reopen checks. The first db696 full comparison reached the steady
characterization: every cell except one passed, with zero clipping and strong
coherence/SNR. Native fast attack at level 5 and TX -35 dB measured -2.72668
dBFS against a -3.0 dBFS maximum. Cleanup passed. The explicitly authorized
retry stopped before USB because canonical JSON sorted phase-object keys while
the loader required execution-order iteration. RC18 therefore has no passing
full campaign or soak result and is not hardware-qualified.

## v0.41-plutoplus-spf-tandem-agc-v8-rc17 — 2026-08-26 — **four safe RAM deployments and lifecycle passes; full campaign blocked before USB; superseded**

RC17 retains RC16's firmware implementation, external source graph, and pushed
`pluto-plus-utils` main commit
`2654f34eb909904ec65bc0526e0f8977cb30e2ed`. The firmware-to-utility bridge
now keeps two exact contracts distinct: the release index remains
`frame-metadata-v5`, while the live IIO context and utility receipt require
`frame-metadata-v2`. RC17 uses branch
`codex/firmware-tandem-agc-v8-rc17`, version
`v0.41-plutoplus-spf-tandem-agc-v8-rc17`, manifest
`manifests/tandem-agc-v8-rc17-source.yaml`, package prefix
`plutoplus-spf-tandem-agc-v8-rc17`, and source lock
`refs/tags/tandem-agc-v8-rc17-source/firmware-v1`.

RC17 locked exact commit `f74d082e789564f0adc81c62b82e924e3e913eb1`.
Trusted run `33006829961` succeeded with artifact ID `9621479267`, bundle
SHA-256 `52c30ab1131cbe60e2ed891041e7832d9f914e07a86ff47a6072bf5b1d3ead51`,
DFU SHA-256 `be9df081618df4879a037f6b6b949fc755f12bbaf07540d3c8c4654c6d06ea93`,
and candidate-index SHA-256
`25b9f0b33fae40ebc1c09cb4f27051e1664d9ec85d6929de2903f765427b74cc`.
All four exact radios completed RAM-only deployment with unchanged QSPI and the
verified safe state, then passed the 64-frame muted metadata lifecycle plus
cancel/reopen checks. The first full comparison stopped before opening USB:
the durable host-libiio validator compared the committed firmware wrapper path
against the distinct libiio repository path. No RF phase ran. RC17 therefore
has four valid deployment receipts and four lifecycle passes, but no full or
soak qualification and no persistent write.

## v0.41-plutoplus-spf-tandem-agc-v8-rc16 — 2026-08-26 — **successful indexed build; observed safe RAM boot, no valid deployment receipt; superseded**

RC16 retains RC15's firmware implementation and complete external source graph.
It pins pushed `misko/pluto-plus-utils` main commit
`2654f34eb909904ec65bc0526e0f8977cb30e2ed`, which accepts the real kernel
`/sys/bus/usb/devices/<topology>` symlink while still binding the resolved node
to the exact topology. It also provides a guarded recovery/attestation command
for an unknown transition, including an already-returned runtime and an explicit
expected persistent firmware identity. RC16 used branch
`codex/firmware-tandem-agc-v8-rc16`, version
`v0.41-plutoplus-spf-tandem-agc-v8-rc16`, manifest
`manifests/tandem-agc-v8-rc16-source.yaml`, package prefix
`plutoplus-spf-tandem-agc-v8-rc16`, and source lock
`refs/tags/tandem-agc-v8-rc16-source/firmware-v1`.

RC16 locked exact commit `8ad724edad93cb81cb0647fb202a17b9e8c0a95d`.
Trusted run `33002865124`, attempt 1, succeeded with artifact ID `9619942296`.
The outer ZIP SHA-256 is
`2dc53d08c72cd0aa35286333474521406d25b4fd4b3f8207bbf5dda2795e4a9f`;
bundle SHA-256 is
`4260ef263ed5167ddaf6f2394e8db3527871e8376199dd384c1713a88142344a`;
DFU SHA-256 is
`42f95fc67949069c7d24fe61bbf6043103e66326760dc1a1ca475c65306daa20`;
and candidate-index SHA-256 is
`781a34867dc27c336e75d59b3444f4e84bd958f088d679775eaa9ea7366d0f23`.

On db696 the utility completed the exact sealed paired-selector RAM download
and detach. The same topology/serial returned with a new boot ID and exact RC16
firmware; `qspi-linux` remained SHA-256
`066487d9d135dd492a75fe04912d0e18efae565b0666ae72c40ee4fbbb31d9b8`,
and the measured final state was TX gains `[-80,-80]`, all DDS values zero,
selectors `[3,3,3,3]`, tandem `IDLE`, FIFO 0, and faults 0. The temporary `/32`
route was removed. Receipt publication failed closed because the plan expected
the v5 release/evidence frame schema as the live IIO buffer ABI, while the
device correctly exposed ABI 2. The durable unknown-receipt SHA-256 is
`470cd86373fecd65c0464d995880418317fb8c089feb4a0eb802791dd791010f`.
RC16 therefore has one observed safe RAM deployment, zero valid passing
deployment receipts, no persistent write, and no hardware qualification.

## v0.41-plutoplus-spf-tandem-agc-v8-rc15 — 2026-08-26 — **successful indexed build; zero candidate downloads; superseded**

RC15 retained RC14's firmware implementation and complete external source graph.
It pins pushed `misko/pluto-plus-utils` main commit
`5ab8361211e747387c5dfa854f5ae65a6a4dac87`, which opens the exact
topology-bound USB-IIO URI directly, cross-checks the live serial, model, and
firmware, preserves the already-found tandem capability, and defaults execution
to its own clean source checkout. Every route, password-only SSH, paired DFU,
sealed-input, QSPI-equality, and safe-state guard remains unchanged. RC15 uses
branch `codex/firmware-tandem-agc-v8-rc15`, version
`v0.41-plutoplus-spf-tandem-agc-v8-rc15`, manifest
`manifests/tandem-agc-v8-rc15-source.yaml`, package prefix
`plutoplus-spf-tandem-agc-v8-rc15`, and source lock
`refs/tags/tandem-agc-v8-rc15-source/firmware-v1`.

RC15 locked exact commit `5e84a0cdd19f7635e688821d926ee7eca39c7eab`.
Trusted run `32998047232`, attempt 1, succeeded with artifact ID `9618005590`.
Bundle SHA-256 is
`8329a2de2b62815192fc0e2b4fbe5835e6f434ab6c4b1fdbe34ddd409eb5e4d3`;
DFU SHA-256 is
`0f431cf97958085d129ca1beebefa4793a9c66df5a7040cdb25f4a7ed74fd6f2`;
FIT SHA-256 is
`0a293879252b30101bd76ce830140532e27a843b7856a7bb793c094e620f2cc7`;
and candidate-index SHA-256 is
`82838fe2e8d980c6097c80634c890eae30aac678f52708aafe07c112ad9e5dd9`.
On db696 the guarded execute passed pre-attestation and requested RAM mode, but
the exact b674 resolver rejected the real kernel sysfs symlink before any
candidate download. The unknown receipt SHA-256 is
`1bb16cb1e72a458fcd9a4a6d2b298978de62fa38845483bcbc01c73914abe4a6`.
Corrected utility recovery returned the same radio to persistent RC1, proved
the pre-attempt `qspi-linux` digest unchanged and the final safe state, and
removed the `/32` route; recovery receipt SHA-256 is
`e82d8ae9aff57ff255aea0347b1bcc60f7f800546d6e3a847a192f65fc10b6ee`.
RC15 therefore has no candidate download or valid deployment receipt and is
immutable but superseded by RC16.

## v0.41-plutoplus-spf-tandem-agc-v8-rc14 — 2026-08-26 — **successful indexed build; zero RAM transitions; superseded**

RC14 retained RC13's firmware implementation and complete external source graph.
Its release-process change makes pushed `misko/pluto-plus-utils` main commit
`9ef137768d59925acf21d5cd3ff71d1cb523dba7` the sole live device operator.
`plutosdr-fw` produces a private release-candidate plan pinned to that repository,
version, and commit, and validates the original utility USB inventory, per-radio
operation plan, and measured RAM receipt without translating them.

The utility transaction retains the exact serial/topology resolver, private
password-only SSH with host-key files disabled for ephemeral RAM keys, owned
`192.168.2.1/32` route lease, paired `0456:b673,0456:b674` selector, sealed DFU
input, new boot identity, equal pre/post `qspi-linux` digest, full final safe
state, and verified route cleanup. It authorizes no `-S`, `-R`, persistent
target, or QSPI write. RC14 used branch
`codex/firmware-tandem-agc-v8-rc14`, version
`v0.41-plutoplus-spf-tandem-agc-v8-rc14`, manifest
`manifests/tandem-agc-v8-rc14-source.yaml`, package prefix
`plutoplus-spf-tandem-agc-v8-rc14`, and source lock
`refs/tags/tandem-agc-v8-rc14-source/firmware-v1`.

RC14 locked exact commit `2fb96f7a207848e6579293addbaa27fc0a59f5a9`.
Trusted run `32993231088`, attempt 1, succeeded and uploaded artifact ID
`9616104711`. The outer ZIP SHA-256 is
`bb3f9e0ddaea5b3d4ced996379da97caa1c743ac6349a34e7f5e9df671b4ed21`;
bundle SHA-256 is
`90d4833a74fcad8c0f183d6bc6ff4ea7e32844bfbe27f2869fc2ac6b57ee1804`;
DFU SHA-256 is
`3baa589e7eba8ea763b4f84b966163614cf9f7274f898a2e181168ca72d88ce7`;
FIT SHA-256 is
`2e9b7485b4bdb19d2c4f88316a899f92afc0ba424e61493e7c0179e6f1c6f358`;
and candidate-index SHA-256 is
`7fb1616eee706350b124a84a053ea2340d25de9fa4a2366c421fc06fc78f306d`.
The exact index passed live and detached semantic replay.

The first db696 execute failed before I/O because the tool-repository default
resolved to the firmware working directory. With the explicit repository, the
utility's libiio 0.26 global discovery returned errno 26 on an unrelated
backend. With the release-pinned libiio runtime, preflight then found the exact
tandem device but incorrectly derived an empty capability set from numeric IIO
ids. All failures occurred before `device_reboot ram`, DFU, or receipt
publication; routes were removed and db696 remained exact RC12 and safe.
A bounded patched-code preflight later proved direct `usb:3.29.5` attestation,
unchanged QSPI, full mute/IDLE state, and route cleanup, but cannot authorize the
immutable RC14 tool identity. Therefore RC14 has zero RC14 RAM transitions and
zero valid receipts; RC15 advances the corrected tool commit.

## v0.41-plutoplus-spf-tandem-agc-v8-rc13 — 2026-08-26 — **source-locked; trusted run queued without a job; superseded before artifact/hardware**

RC13 was the forward-only candidate after RC12 built and indexed successfully
and completed one observed RAM transition on db696, but could not publish its
measured receipt. RC13 retains RC12's firmware implementation, external source
graph, deterministic package, exact serial/topology resolver, paired
`0456:b673,0456:b674` selector for both `-D` and `-e`, per-radio `/32` route,
IIO/model checks, QSPI equality check, and final safe-state checks. It changes
only the SSH host-key boundary, receipt schema, and release lineage.

Pluto RAM boots generate a fresh Dropbear key. RC13 therefore removes the
`--known-hosts` and `--known-hosts-sha256` CLI inputs and the
`known_hosts_sha256` receipt member. Receipt schema v4 requires password-only
SSH through `sshpass -f`, exact interface binding, one password prompt, and
these exact options: `StrictHostKeyChecking=no`,
`UserKnownHostsFile=/dev/null`, and `GlobalKnownHostsFile=/dev/null`, together
with `PasswordAuthentication=yes`, `PubkeyAuthentication=no`,
`KbdInteractiveAuthentication=no`, `CheckHostIP=no`, and `UpdateHostKeys=no`.
The exact USB serial/topology, returned b673 serial, Pluto+ IIO model, isolated
route, new boot ID, equal pre/post QSPI digest, safe runtime, and paired DFU
commands remain mandatory.

RC13 locked exact commit `3361acb3446b517854ca1cfc144d28c4dd853743`.
Owner dispatch `32985347441`, attempt 1, remained queued without an allocated
job and was superseded before it produced an artifact, candidate index, receipt,
or hardware access. The RC13 route uses branch `codex/firmware-tandem-agc-v8-rc13`, version
`v0.41-plutoplus-spf-tandem-agc-v8-rc13`, manifest
`manifests/tandem-agc-v8-rc13-source.yaml`, package prefix
`plutoplus-spf-tandem-agc-v8-rc13`, and source lock
`refs/tags/tandem-agc-v8-rc13-source/firmware-v1`. RC12's source lock, trusted
build, artifact, candidate index, and observed no-receipt incident remain
immutable. RC13's host-key correction remains historical; RC15 replaces its
device-operation/evidence harness before any four-radio campaign.

## v0.41-plutoplus-spf-tandem-agc-v8-rc12 — 2026-08-26 — **successful indexed build; observed RAM boot, no deployment receipt; not hardware-qualified**

RC12 locked exact commit
`12261ed055d4488d64aa7ff5353b680a37c3f93d` at source lock
`refs/tags/tandem-agc-v8-rc12-source/firmware-v1`. Owner-dispatched trusted run
`32978460325`, attempt 1, completed successfully and retained artifact ID
`9611124509`, named
`plutoplus-main-12261ed055d4488d64aa7ff5353b680a37c3f93d-32978460325-1`.
Its outer ZIP SHA-256 is
`9ceb66dc670811ec7d717788edb3257f1c56db68ad9a035dd8df2b1e43106429`;
verified candidate-index SHA-256 is
`a339c99eb7d16980b33249d5a8a5e8c0693a4d22cbf6333c5ce0b3aa2b0151cd`;
bundle SHA-256 is
`789aa4d9e8fc672a2040abeee89a34de5f62dafd9e933628ac09d0aac21444c2`;
DFU SHA-256 is
`6ffe6ddf898986b1fd6629db796b6b10422a4e5a00da268e0f63d1d258db52a0`;
and FIT SHA-256 is
`5db1c49f954e630e4d2a41860bc6bf3f1a6e58749c5c382398caa30887781957`.
The complete build, artifact, and evidence index passed and remain immutable.

On `winbond-db6968136727402c` at exact topology `3-7`, the first attempt
stopped at the initial runtime SSH command with exit 255 on the stale retained
RC1 host key, before reboot or DFU. The temporary `/32` route was removed, no
deployment receipt was published, and persistent RC1 remained safe. The exact
current key was then enrolled with the isolated serial-attested utility;
enrollment receipt
`/tmp/tandem-agc-v8-rc12-hardware-prep.bqEWh8/enrollment-receipts/65362d728b3144aa9687d7df16502731.json`
records success and has SHA-256
`11107591e5c48cd8c335c4e8bf9387f1e92459ac8d09d98383071d5670b1d9d7`.

The second attempt passed the initial checks, sent `device_reboot ram`, and
found the unique exact-topology serialless b674 device. It completed
paired-selector `-D` and `-e`, then returned exact `0456:b673` as devnum 29 on
topology `3-7` running RC12. Both postboot and cleanup SSH calls exited 255. The retained RC1
ED25519 fingerprint was
`SHA256:ls0RSRupYX9ZJKe9Kh3t9yJHvt54NZTyA+A91ObNGCU`; the topology-bound,
serial-attested RC12 RAM fingerprint was
`SHA256:hihAeih3cGjJhpmjkNkPA3qgv55XlUc4OmnJDWniRc8`. The cause is exact:
`/etc/init.d/S50dropbear` starts Dropbear with `-R` and has no persistent host key,
so each RAM boot generates a different key and a preboot pin cannot
authenticate the postboot image.

No deployment receipt, retained deploy log, or retained SSH stderr was
published, and the candidate hardware directory is empty. A later exact
runtime observation found URI `usb:3.29.5`, boot UUID
`f6977760-dda6-431f-8517-733e8402b3c6`, the exact Pluto+ model, and RC12 in a
safe state: TX gains `[-80,-80]`, every DDS raw value zero, DAC selectors
`[3,3,3,3]`, tandem `IDLE`, FIFO level 0, and fault flags 0. Current
`qspi-linux` is 31,457,280 bytes with SHA-256
`066487d9d135dd492a75fe04912d0e18efae565b0666ae72c40ee4fbbb31d9b8`,
but no preboot QSPI digest was retained. Therefore postboot QSPI equality is not claimed.
The tool issued no QSPI write or persistent-target command. The exact
`/32` route is absent and every peer NIC was restored.

RC12 has one observed successful RC12 RAM deployment.
It has zero valid receipt-authorized deployments and is not hardware-qualified.
RC13 corrects only the unsatisfiable ephemeral-host-key boundary, receipt
schema, and lineage.

## v0.41-plutoplus-spf-tandem-agc-v8-rc11 — 2026-08-26 — **successful indexed build; zero candidate deployments**

RC11 locked exact source commit
`4c332666ff054e21e10c1a8137fd5f1cbc73b568` and source ref
`refs/tags/tandem-agc-v8-rc11-source/firmware-v1`. Trusted run `32970312166`,
attempt 1, routed all 32,908 nets, used 74 of 80 DSPs, and closed timing at WNS
`+0.645 ns`, WHS `+0.022 ns`, and minimum bus skew `+8.606 ns`. Artifact ID
`9607927415` was retained as
`plutoplus-main-4c332666ff054e21e10c1a8137fd5f1cbc73b568-32970312166-1`.

Its outer ZIP SHA-256 is
`583c52462725c037ba73aca32d78472ea6784b43764e13ab92996b322ee5b3d3`;
bundle SHA-256 is
`91410b15e458eac1a2190dd0fa40ee540b6f7e6bde9e71c70125a9f86dc05c09`;
DFU SHA-256 is
`1dd94789dddefb7220caad75fb063ad0fdd2a8f3204f2f4fa48bd1cca2d31481`;
FIT SHA-256 is
`50e1544eef70715ac523485391602cbff541596947c9f0a93f17685286bccb34`;
source-manifest SHA-256 is
`31693bca03606742978351a1e920c917ad8c0337dba33081666f754fe530eb60`;
and verified candidate-index SHA-256 is
`ef8017c539f42d936bcde054e85864e331d4b383167201573c30419d98100831`.
The immutable RC11 index/archive binds the defective deployer at SHA-256
`bb17001e7b65d34a71363de4240d8e771c8b3fd1d1229a5e0d14e7bf677bf44e`
and receipt replay binder at SHA-256
`299afafb3d08c68a4a3a282164b2f1411e71d508e60cbfbbc1007c1569c927dd`.

On `winbond-db6968136727402c` at pre-attested topology `3-7`, the guarded
execute passed its runtime and QSPI baseline, sent `/usr/sbin/device_reboot ram`,
and reached unique exact serialless `0456:b674`. The RC11 planner invoked
`dfu-util -d 0456:b674 -p 3-7 -a firmware.dfu -D /proc/self/fd/5`; it returned
non-zero exit status 64 before transferring any candidate bytes because the
trusted DFU suffix identifies b673. The reproduced diagnostic said File ID `0456:b673` does not match device `(0000:0000 or 0456:b674)`; in full:

```text
Error: File ID 0456:b673 does not match device (0000:0000 or 0456:b674)
```

The wrapper's complete terminal error was:

```text
ERROR: deployment failed (Command '['dfu-util', '-d', '0456:b674', '-p', '3-7', '-a', 'firmware.dfu', '-D', '/proc/self/fd/5']' returned non-zero exit status 64.); safe cleanup also failed (timed out waiting for 0456:b673 on 3-7: expected exactly one 0456:b673 USB device for serial 'winbond-db6968136727402c'; found [])
```

Cleanup timed out waiting for b673 because the radio remained in b674.

Exact-topology recovery with the paired `0456:b673,0456:b674` selector and
`-e` returned exact-serial b673, persistent RC1, devnum 27, in a verified safe
IIO state with the temporary `/32` route absent. Zero candidate bytes were
transferred, RC11 has zero candidate deployments, no receipt was produced, and
no QSPI write occurred. There is no retained selector-failure log, so no log
digest is claimed. The existing
`/tmp/tandem-agc-v8-rc11-deploy-db696.log` SHA-256
`55140cc3f1058fd62dd0178d35bcc7fef905eb46d65e5bac69ebdd9c644a38ee`
belongs to the earlier pre-enrollment SSH stop, not this selector failure.
RC11's commit, branch, lock, run, artifact, candidate index, and
zero-deployment history remain immutable. RC12 changes only the paired
normal/DFU selector boundary and lineage.

## v0.41-plutoplus-spf-tandem-agc-v8-rc10 — 2026-08-26 — **successful indexed build; zero candidate deployments**

RC10 locked exact source commit
`1b3ba3dbe942b9880f21ca99dda1de5227794c3d` and source ref
`refs/tags/tandem-agc-v8-rc10-source/firmware-v1`. Trusted run `32964460396`,
attempt 1, routed all 32,908 nets, used 74 of 80 DSPs, and closed timing at WNS
`+0.645 ns`, WHS `+0.022 ns`, and minimum bus skew `+8.606 ns`. Artifact ID
`9605679961` was retained as
`plutoplus-main-1b3ba3dbe942b9880f21ca99dda1de5227794c3d-32964460396-1`.

Its outer ZIP SHA-256 is
`273f4b02cf7438c1c5983ea3b87140000d947cc3dc30c7d0631847c5d934ba2c`;
bundle SHA-256 is
`144aaef4ebab18e7b859f0855421060bcaae8031db3acc1d3b195561f1a2047d`;
DFU SHA-256 is
`c0a086eb945d27f728a7fb2504de85ef648fc1dcc1d70a928f9d8c999e523913`;
FIT SHA-256 is
`7e725f5094f224126f98d923e2cb8668af69d2d79132a81f3ee5a74ff75d48cd`;
source-manifest SHA-256 is
`5c04a354075ef7ce98958b82ab8ef03277461f24621b88f4a4d2bda5b6d0931f`;
and verified candidate-index SHA-256 is
`827cc1e6d5d36a7a7f6b61b5238dae7df986d0708eef4c2f4a2e41f2f2461b58`.

On radio `winbond-db6968136727402c` at pre-attested topology `3-7`, route,
authentication, runtime, and QSPI baseline checks passed and
`/usr/sbin/device_reboot ram` transitioned the device to exact `0456:b674`.
That DFU device omitted its USB serial, so RC10's exact-serial resolver failed
closed before any `dfu-util -D`. Consequently zero candidate bytes were
downloaded, RC10 has zero candidate deployments, no receipt was published, and
there was no QSPI write. Exact-topology `dfu-util -e` recovered the persistent RC1
safe runtime, and the temporary `192.168.2.1/32` route was removed and is
absent. RC10's commit, branch, lock, run, artifact, candidate index, and zero-
deployment history remain immutable. RC11 changes only the serialless-b674
transition boundary.

## v0.41-plutoplus-spf-tandem-agc-v8-rc9 — 2026-08-26 — **successful indexed build; rejected before hardware transition**

RC9 removed RC8's redundant historical transition-proof input without
changing firmware behavior or the deterministic package contract. Exact source
commit `9f47ef1746eaf356e53fe52cd9eb608ee8421c62` passed the complete offline and
routed OOC gates. Trusted Actions run `32957388515`, attempt 1, fully routed
32,908 of 32,908 nets and closed timing at WNS `+0.645 ns`, WHS `+0.022 ns`,
and minimum bus skew `+8.606 ns`.

The trusted run produced bundle SHA-256
`5f3eb4a772fb808f4598c4cc11d6a10936fecdaf045636d33ddfeaeaa9927dc7`,
DFU SHA-256
`407c560be90cfdbf459b92f1f76352f83f09cabf9c5f336375bd85868454975`,
FIT SHA-256
`19e85e9b1c6ca12e41f8566fcff609a781aedfc9f0135b7c042aa25872a60115`,
and verified candidate-index SHA-256
`d2784863cfb74c34e98a2295a1b7532fc19f7f93ef90045b726055f1f99d3efd`.

The first live execute stopped during its initial SSH read, before
`device_reboot ram`, DFU download, detach, reboot, or receipt publication.
Competing `192.168.2.0/24` routes selected another attached serial and strict
known-hosts verification caught the mismatch. A temporary exact `/32` route
then selected the intended radio, but the key-only SSH policy could not
authenticate to the factory password-only image. The diagnostic route was
removed. No radio changed state and RC9 had zero deployments. Its branch,
source lock `refs/tags/tandem-agc-v8-rc9-source/firmware-v1`, run, artifact,
and candidate index remain immutable successful reproduction history. RC10
changes only the host route/authentication boundary and measured receipt.

## v0.41-plutoplus-spf-tandem-agc-v8-rc8 — 2026-08-26 — **successful indexed build; not deployed**

RC8 was the forward-only candidate after RC7's successful trusted build exposed
a reproducibility defect at the packaging boundary. It retained RC7's external
source graph, firmware RTL, placed-and-routed behavior, and integrated
validation policy. The candidate-only change made archive inventories,
checksum inputs, and bundle members use one explicit bytewise order independent
of runner locale and shell-array discovery order.

Trusted Actions run `32952343526`, attempt 1, built exact source commit
`cc62b65ea8082aad0625a891f0b79b81c78e78c7`. Vivado routed 32,908 of 32,908
nets, placed 4,399 of 4,400 slices, used 74 of 80 DSPs, and closed timing at
WNS `+0.645 ns`, WHS `+0.022 ns`, and bus-skew minimum `+8.606 ns`. The run
produced deterministic bundle SHA-256
`d55b58e489a58c3c8868f4bfcec4a7901c229a25e801c172bf2dd1fa08965c77`,
DFU SHA-256
`2c74f06bff072d9c3250e5e028e18ddda4f700f5960cd07153432f1a081a8f49`,
and FIT SHA-256
`30f7816ea2f1b66aff928613b95748f952cafbb35bc7320a05bfdd5e3075b9d8`.
The verified candidate index SHA-256 is
`d94b9c37a8c6f1e5935df5ae4bdfd03be49b7aba40236a32386382a0f09004a8`.

No radio was touched. The deployer still required a redundant historical
transition-proof input, so RC8 stopped with zero hardware deployment. Its
branch, exact source lock
`refs/tags/tandem-agc-v8-rc8-source/firmware-v1`, run, artifact, and candidate
index remain immutable successful reproduction history. RC9 removes only that
redundant host-side input and versions the receipt accordingly; firmware
behavior and deterministic package implementation are unchanged.

## v0.41-plutoplus-spf-tandem-agc-v8-rc7 — 2026-08-26 — **rejected before evidence or hardware**

RC7 is the forward-only candidate after RC6's trusted build completed FPGA
implementation but was rejected by obsolete post-route report assumptions. It
retains RC6's external source graph and firmware RTL; the candidate change is
the fail-closed validator correction needed to recognize Vivado's legitimate
routed report state and the reviewed DSP/CDC inventory without accepting
missing, malformed, unrouted, or unsafe reports.

RC7's exact source lock is
`refs/tags/tandem-agc-v8-rc7-source/firmware-v1`. Trusted Actions run
`32948720383` successfully built and fully routed that source and passed the
integrated report gate. It uploaded a bundle with SHA-256
`7f13d6dd3f814af1a1e0d06d65535d2f60499b4bb3c0ab0e5cc4e7b8c8836f34`.
Before evidence assembly, review found that archive/checksum ordering depended
on locale and shell-array order, so those bytes were rejected. There was no
deployment, no hardware use, and no candidate evidence index. RC7's branch,
source lock, run, and bundle are immutable reproduction history. RC8 advanced
only the deterministic packaging boundary.

## v0.41-plutoplus-spf-tandem-agc-v8-rc6 — 2026-08-26 — **rejected; post-route policy failed**

RC6 was the forward-only candidate after RC5's integrated placement failure. It
keeps RC5's stale-small-ADC-latch recovery and external source graph, but
replaces three mutually exclusive eight-bit dwell counters with one shared
eight-bit counter and a two-bit qualification-class tag. A two-bit binary token
replaces the former stale-latch episode booleans, and the redundant eight-bit
`event_index` shadow is removed. Only the wide `pwr_div` and `evt_seq`
accumulators carry `use_dsp = "yes"`. The tag prevents ordinary increase,
stale-conflict, and re-arm qualification from inheriting one another's partial
dwell credit when the live evidence class changes.

The final RC6 source commit and immutable lock resolve to
`fb1cb04085fda4854f964481d5d5427b6934d58b`. Trusted Actions run
`32944830787`, attempt 1, accepted that exact source and completed integrated
implementation: Vivado routed 32,908 of 32,908 nets. It placed 4,399 of 4,400
slices, used 74 of 80 DSPs, and closed timing at WNS `+0.645 ns`, WHS
`+0.022 ns`, and the bus-skew minimum was `+8.606 ns`.

Packaging then failed closed because the committed integrated validator still
expected stale report-state, DSP, and CDC policy details. The run uploaded
diagnostics only. It produced no deployment bundle, candidate index, or DFU,
and nothing from RC6 was deployed to a radio. Its branch, manifest, exact
firmware identity, and
`refs/tags/tandem-agc-v8-rc6-source/firmware-v1` remain immutable reproduction
history. RC7 advances the validator and release lineage without changing the
RC6 RTL implementation.

## v0.41-plutoplus-spf-tandem-agc-v8-rc5 — 2026-08-26 — **rejected; integrated placement failed**

RC5 was the first forward-only candidate for the stale-small-ADC-latch recovery
added after RC4. RC4's protected source lock, routed build, artifact, and
hardware reports could not authorize that RTL and were not moved or relabelled.

RC5 introduced a source manifest, owner-only build mapping, exact evidence-index
tooling, a guarded exact-serial RAM deployer, and candidate-bound release and
muted-64-frame lifecycle harnesses. The trusted package regenerates timing,
route, DRC, methodology, CDC, bus-skew, and utilization reports from the
packaged routed DCP and checks their complete inventory and reviewed resource
ceilings against a committed policy. After a successful integrated route, it
would also build, verify, and checksum a `pluto.frm` whose FIT bytes exactly
match the candidate DFU. The final release verifier no longer treats a missing
`dfu-suffix` tool as a successful skipped check.
The RAM receipt additionally requires equal pre/post SHA-256 readback of the
exact `qspi-linux` `/dev/mtdblock3` partition, so a candidate transition cannot
claim unchanged persistent firmware from command intent alone.

The final RC5 source commit and immutable source lock resolve to
`af2e1821436996188fd32cc1cf8a0f8a41f31fc1`. Its full hardware-free gate passed
1,093 tests with five hardware tests explicitly deselected, and its clean
commit-bound routed OOC implementation passed at WNS `+3.765 ns` and WHS
`+0.079 ns`, with zero failing endpoints. Trusted Actions run `32933327011`,
attempt 1, accepted the exact RC5 identity and source graph, but the integrated
Vivado build failed placement before artifact upload: 2,357 remaining instances
needed the 2,340 slices available after fixed and macro placement, a 17-slice
shortfall. RC4 had already occupied 4,399 of the device's 4,400 slices, so the
failure is retained as a genuine device-capacity result.

No RC5 DFU, deployment bundle, or candidate evidence index was produced,
deployed, or tested on radio hardware, and no QSPI write was authorized. The
current exact-release ABI does not expose enough internal detector/latch state
for a deterministic stale-latch RF test without adding release-only debug
interfaces. RC5's internal FSM qualification therefore relied on the
deterministic RTL suite at both clock ratios; the guarded `BLOCKED` observer was
optional diagnostic evidence only. RC5 stopped at integrated placement. The
active RC20 route still requires the complete external paired-behavior,
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

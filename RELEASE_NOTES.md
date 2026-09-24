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
| `tandem-agc-v8-rc23` | 2026-08-27 | **successful indexed build; db696 RAM/lifecycle passed; transient response oracle invalid; superseded** | retained exact-cadence paired response events, but the host oracle demanded zero clipping during a deliberately overloaded AUTO response |
| `tandem-agc-v8-rc24` | 2026-08-27 | **successful indexed build and db696 RAM/lifecycle; three transient comparison modes passed; tandem invalid; superseded** | separate host sysfs reads straddled one AUTO transition and manufactured a mixed transition-count/gain snapshot |
| `tandem-agc-v8-rc25` | 2026-08-27 | **successful indexed build and db696 RAM/lifecycle; all four inner transient modes passed; outer replay invalid; superseded** | fixed coherent host status reads; outer replay contradicted the frozen producer policy for startup conditioning and diagnostic response windows |
| `tandem-agc-v8-rc26` | 2026-08-27 | **successful indexed build and four RAM/lifecycle passes; full campaign invalid; superseded** | replay alignment passed, but two db696 full attempts stopped on metadata-provider ENODATA in the same 1.05-GHz low-power matrix |
| `tandem-agc-v8-rc27` | 2026-08-27 | **successful indexed build and four RAM/lifecycle passes; full campaign invalid; superseded** | passed all 1.05-GHz steady policies; two-buffer capture omitted every louder-TX DECREASE event in the authorizing 1.55-GHz cooldown-0 matrix |
| `tandem-agc-v8-rc28` | 2026-08-27 | **successful indexed build and four RAM/lifecycle passes; full campaign invalid; superseded** | all 44 steady and four transient pilot phases passed; unsupported 1.024-MS/s no-FIR modulated rate failed before TX buffer creation |
| `tandem-agc-v8-rc29` | 2026-08-27 | **successful indexed build and four RAM/lifecycle passes; fleet campaign invalid; superseded** | fixed the modulated configuration; fleet attempts exposed late native-AGC settling, cooldown-zero transport loss, and an unreliable 5.8-GHz endpoint |
| `tandem-agc-v8-rc30` | 2026-08-27 | **trusted indexed build; zero candidate deployments; superseded** | all software/build gates passed; mixed ordinary-Pluto/Pluto+ USB inventory failed closed before hardware |
| `tandem-agc-v8-rc31` | 2026-08-27 | **trusted indexed build and three RAM/lifecycle passes; campaign invalid; superseded** | native fast AGC intermittently held one RX chain at the 4.2-GHz strong-signal step |
| `tandem-agc-v8-rc32` | 2026-08-27 | **final release; trusted build passed; hardware campaign failed** | the original db696 campaign failed a binding 1.55-GHz native-fast comparison; a later 30-run, three-radio repetition reproduced four native-fast gain-degradation failures on two radios |
| **`ddr-burst-v1`** | 2026-08-28 | **current hardware-qualified release** | counter-observable single RX plus optional, default-off, two-second device-DDR burst capture through standard libiio; five-board RAM and persistent qualification |
| `ddr-burst-v2-rc1` | 2026-08-28 | **rejected; RAM only** | wrap-safe 8-bit FIFO event accounting and two-frame admission; hardware found deterministic whole-frame loss at 5 ms |
| `ddr-burst-v2-rc2` | 2026-08-28 | **rejected; RAM only** | added an 8 ms pre-hardware floor; cross-device qualification reproduced intermittent loss at that exact boundary |
| `ddr-burst-v2-rc3` | 2026-08-28 | **hardware-qualified release source; final bytes pending** | 12 ms floor passed two-PHY USB/IP, maximum-burst, repeated fresh-context, and abrupt-client recovery gates |
| `ddr-ring-v1-rc1` | 2026-08-29 | **implementation candidate; superseded** | introduced the optional streaming Pluto DDR ring behind ordinary metadata-buffer refills |
| `ddr-ring-v1-rc2` | 2026-08-29 | **hardware-qualified release source; final bytes pending** | fixes the exclusive status boundary; exact candidate passed direct USB, physical Ethernet, wrap, recovery, and ordinary-IIO gates on AD9361 and AD9363A hardware |
| `ddr-ring-prefill-v1-rc1` | 2026-08-29 | **hardware-qualified release source; promoted** | fills a strict contiguous DDR prefix before transport, then completes pressure-limited streams with exact gap metadata instead of terminal overflow |
| **`ddr-ring-prefill-v1`** | 2026-08-29 | **current hardware-qualified release** | exact 200 MB contiguous prefix plus nonterminal ABI-3 pressure-gap completion at 20 MS/s |
| `iio-throughput-coverage-window-v6-rc1` | 2026-08-30 | **hardware-qualified release source; final bytes pending** | prevents queued DMA frames from aging out of gain/RSSI coverage during DDR copy and backpressure |
| `v0.46-plutoplus-spf-iq-direct-async-ring-v1-rc1` | 2026-08-31 | **hardware-qualified RAM-first prerelease; source promoted** | overlaps DMA capture with TCP delivery, optionally extends the same FIFO with RAM-backed descriptors, and exceeds 70 MB/s with the exact packaged runtime over 1 GbE |
| `v0.46-plutoplus-spf-iq-direct-async-ring-v1` | 2026-08-31 | superseded hardware-qualified full release | first non-RC direct/RAM release; exact final image passed guarded persistent installation and cold-boot qualification |
| `v0.47-plutoplus-spf-iq-direct-async-v2` | 2026-08-31 | superseded hardware-qualified full release; rollback target | keeps a whole host target in one DMA session and adds default drop-backlog plus preserve-backlog overrun policies for ringless and RAM-extended queues |
| `v0.48-plutoplus-spf-iq-direct-async-v3` | 2026-09-01 | superseded hardware-qualified full release; rollback target | recovers stale gain/RSSI metadata in drop-backlog mode and completes long finite sessions |
| `v0.49-plutoplus-spf-iq-direct-async-v4` | 2026-09-01 | superseded hardware-qualified full release | authoritative requested/allocated DMA admission, real 50-buffer/200 MB DMA profile, 216 MiB CMA, and persistent return qualification |
| **`v0.52-plutoplus-spf-adaptive-scan-v1`** | 2026-09-17 | **current hardware-qualified full release** | fixed-bandwidth autonomous frequency selection through 30 MS/s, complete-visit admission, and asynchronous source-bound host feedback |
| `v0.53-plutoplus-spf-adaptive-scan-v2-rc1` | 2026-09-20 | **exact-byte RAM-qualified; final promotion source** | near-zero repeated-target retune gaps plus shared-LO paired-RX capture on Pluto+ Rev.C |
| `v0.54-plutoplus-spf-counter-utc-v1-rc1` | 2026-09-20 | **published two-radio functional prerelease; UTC accuracy unqualified** | adds the UTC counter observation provider while preserving v0.53 manual gain, repeated-target fast path, and paired RX |

| `v0.56-plutoplus-spf-adaptive-runtime-rates` | 2026-09-24 | **release route staged; qualification pending** | stable main route for setup-validated adaptive runtime-rate operation; not yet a publication or rollback target |

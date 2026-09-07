# FPGA tracker execution and evidence ledger

Canonical design specification: [FPGA_tracker_60MS.md](FPGA_tracker_60MS.md)

Status: active experimental implementation. **DO NOT MERGE INTO FIRMWARE MAIN.**

Authorized receiver: `104000bac4950008230026001b440a003a` only.

Reserved cabled-bench transmitter: `1040007c4a94000211000b009186843ef2`
at USB topology `3-11` and host interface `enx00e02297811f`. It remains
blocked from access until the physical fixture gate below is attested. Its
physical `TX1` port is not part of the experimental receiver image; it is a
separate ordinary-firmware signal source connected only by attenuated coax.

## Current baseline

- Firmware branch: `codex/starlink-rx-only-do-not-merge`
- Routed 15 MS/s acquisition image:
  `v0.50-plutoplus-starlink-pss-15m-rx-only-dnm-v7`
- Physical RFIC evidence: AD9363A
- Persistent runtime target: `ad9361-1r1t`
- Persistent firmware:
  `v0.48-plutoplus-spf-iq-direct-async-v3`
- Persistent QSPI FIT SHA-256:
  `db777ac93d5c6f0be0cf2799808a4d06fe39264ee1e99e76001509394d75f1df`
- PPU setup receipt:
  `/home/mouse9911/pluto-state/starlink-rx-only-dnm/setup-ad9361-1r1t-20260906/state/setup/receipts/e1ded32ce93644efbfe8b1274a13a204.json`

## Gate ledger

| Gate | State | Evidence required |
| --- | --- | --- |
| M0: AD9361-personality DNM lifecycle | Complete | Offline plan tests, exact-target RAM boot, recovery to persistent `ad9361-1r1t` |
| M1: 120-second continuous map consumer | Complete | Controller tests, zero-loss hardware receipt, recovery proof |
| M2: deterministic 15 MS/s timing | Complete | Simulation plus three exact FPGA timing signatures and verified QSPI recovery |
| M3: cabled-RF 15 MS/s timing | Complete | Positive/muted/positive cabled receipts, final TX mute, RX recovery |
| M4: live-LNB 15 MS/s timing | Offline ready | Repeated on-channel trajectory and off-channel control |
| M5: 30-to-15 decimator/index mapping | Pending | Bit-exact oracle and routed evidence |
| M6: sparse 30 MS/s refinement | Pending | Direct-oracle timing within one source sample |
| M7: 60-to-30-to-15 cascade | Pending | Bit-exact cascade and routed evidence |
| M8: sparse 60 MS/s refinement | Pending | Direct-oracle timing within one source sample |
| M9: live 60 MS/s narrowband run | Pending | 120-second receipt and rollback proof |
| M10: SSS/final frame lock | Pending | Separate frozen policy and live qualification |

## M0/M1 implementation record

The existing acquisition library already provides:

- exact ABI/rate/DDC-contract validation;
- atomic health snapshots;
- oldest-ready-bank selection;
- coherent 20,000-word copy followed by exact-bank release;
- adjacent generation and 1,280,000-sample start-index checks;
- three-map sliding-window storage;
- seven-hypothesis drift extraction; and
- candidate statistics without a detection or frame-lock claim.

The completed M0/M1 implementation is:

1. candidate generation and the DNM launcher explicitly bind
   `ad9361-1r1t` and its exact runtime model;
2. a bounded continuous controller command leaves acquisition enabled,
   copies/releases every map, extracts a candidate from every ready three-map
   window, and emits a final health/continuity summary;
3. a receipt-bound host launcher uploads that controller only to
   `/tmp`, uses PPU's exact radio and route locks, restores RX settings, removes
   the temporary binary, and requires separate PPU recovery; and
4. the complete offline and exact-radio 120-second gates passed.

Implemented offline on 2026-09-06:

- candidate generation now explicitly seals either `ad9363a-1r1t` or
  `ad9361-1r1t`, including the matching live model, while defaulting to the
  historical AD9363A behavior;
- the v8 DNM launcher scopes the inherited v6 lifecycle to the exact
  `ad9361-1r1t` runtime and restores every inherited identity constant;
- `starlink_pss_acqctl monitor` continuously copies/releases maps for a bounded
  interval, computes each three-map candidate window, and emits strict NDJSON
  map and cutoff-health records;
- the host monitor seals the controller binary, PPU handoff, radio identity,
  duration, output receipt, and explicit confirmation before hardware access;
- the host validator requires approximately the rate-derived map count, every
  adjacent generation and 1,280,000-sample index step, zero fault counters,
  exact cleanup, and no PSS/SSS/frame-lock claim; and
- the future 60 MS/s gate now correctly requires wider or resettable hardware
  counters because the current DDC counters saturate rather than wrap.

Offline evidence:

- strict host and static ARM controller builds: PASS;
- native C acquisition/controller self-tests: PASS;
- ASAN/UBSAN acquisition test: PASS;
- focused M0/M1 Python tests: 40 passed;
- complete `tests/test_starlink_pss*.py` regression: 118 passed.

Hardware has not been accessed by this implementation checkpoint. M0 and M1
remain open until the exact AD9361-personality RAM lifecycle, 120-second soak,
and QSPI recovery receipts pass.

No M0/M1 result is a PSS-detection, SSS, or frame-lock claim.

## M0/M1 evidence log

- DNM source commit:
  `4a84693cbef4e96a624d8ae54650b8c74603930f`
- Pushed branch: `origin/codex/starlink-rx-only-do-not-merge`
- Frozen source tags:
  - `starlink-rx-only-dnm-v1-source/firmware-pss-v6-ad9361-probe-v8`
  - `starlink-rx-only-dnm-v1-source/firmware-pss-v6-ad9361-monitor-v1`
- PPU source commit: `7210cda9b0b2452cb607b5e49e689e2d60b6a8b7`
- AD9361-bound candidate plan SHA-256:
  `c45479e78a02d1e6f3079347b3d326b86aa24b0f543261cd5e6e951a1a156091`
- Correct serial-scoped operation plan SHA-256:
  `ce922e901fb87ba4773eb284742da4a0b60bd84c06ab2d9940762bc655157a52`
- Passing RAM receipt SHA-256:
  `bc6d31143d68bfbb7ec09f194c9ad396386fb21221f68b1668e1659c042eb48b`
- Sealed 120-second monitor plan SHA-256:
  `c0b45ce7b62f7db049ca5ce3db2831d2d216bb0b1536e917cb2c4396a7554405`
- Passing monitor receipt SHA-256:
  `fdb8c15bc8cc7c3515566659b334bd6b1ac4a103186e1581bfd82c3a567d6c70`
- Passing recovery receipt SHA-256:
  `599ae7a9f72cb05681ee8d69c9b9cde9ae2b72a7f9b164ed960f07b6ce0c8a97`

The normal soak observed exactly 1,406 maps and 1,404 candidate windows in
120,042 ms. Generations ran from 1 through 1,406. Every adjacent start index
advanced by 1,280,000 canonical samples. Accepted scores advanced by
1,799,777,036 and published maps advanced by exactly 1,406. All transport,
detector, ingress, scheduler, arithmetic, map, and DDC fault fields were zero;
the final ready mask was zero. The receipt expressly records
`pss_detected=false`, `sss_detected=false`, and `frame_lock_claim=false`.

The existing separate negative-stall receipt at
`/home/mouse9911/pluto-state/starlink-rx-only-dnm/private-candidates/candidate-v6-15-acquisition-only-a/hardware/attempt3/progress-v3/progress-receipt.json`
proves that intentionally not releasing the same v6 ping-pong maps increments
discard/overrun telemetry and fails the fault-free epoch.

Recovery proved pre-reset USB departure, a new persistent boot ID, unchanged
`qspi-linux`, `v0.48-plutoplus-spf-iq-direct-async-v3`, `ad9361-1r1t`, one RX,
TX gain at `-80 dB`, shared TX LO powered down, and released host route. A
post-recovery USB inventory proved that all three unallocated radios retained
their original topology, network interface, and device number; only the
authorized `5-2` radio re-enumerated as expected.

All private artifacts are under:

`/home/mouse9911/pluto-state/starlink-rx-only-dnm/fpga-tracker-m0-m1-20260906`

A gate changes to `Complete` only when every corresponding requirement in
`FPGA_tracker_60MS.md` has direct evidence.

## M2 implementation and evidence log

M2 completed on 2026-09-07 using only the allocated radio. The v7 RX-only FPGA
candidate adds a bounded periodic sample injector ahead of the continuous
15 MS/s acquisition path. The temporary static ARM controller loads a
130-sample fixture, substitutes it every 20,000 samples for 130 repetitions,
and tests phase zero, the 19,999-to-zero wrap, and phase 7,311. The controller
starts the deterministic stream one complete period before each target map so
the overlap-save pipeline is warm before any qualified score.

The first hardware attempt exposed a controller-only ABI interpretation bug:
ABI 1.1 has an implicit fixed 15 MS/s rate and therefore no populated DDC rate
register. The corrected controller derives 15/30/60 MS/s from ABI 1.1/1.2/1.3
in the same way as the general acquisition controller.

The next exact-map attempt revealed an oracle error rather than an FPGA timing
error. The XFFT emits 447 valid overlap-save results per block, while a Starlink
period is 20,000 samples; `20000 mod 447 = 332`. Block-floating scaling
therefore sees the periodic fixture at different locations in successive FFT
blocks. Multiplying the first 20,000-score profile by 64 is not a valid oracle
for every low-level map bin. This is explicitly retained in the receipt:
full-map exactness is not claimed, and the mismatch counts remain diagnostics.

The M2 pass criterion is the timing result required by the canonical plan. For
each requested phase, the FPGA must produce a globally unique peak at exactly
that phase, the exact 64-frame peak magnitude `16320`, the exact runner-up
magnitude `7424`, a completed 130-repetition injection, contiguous map
generations, and a fault-free health epoch. The host independently validates
the strict version-2 NDJSON records and receipt. It still makes no live-PSS,
SSS, or frame-lock claim.

Passing FPGA cases:

| Requested phase | Observed phase | Peak | Runner-up | Diagnostic differing bins | Map generation |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 0 | 16,320 | 7,424 | 870 | 3 |
| 19,999 | 19,999 | 16,320 | 7,424 | 873 | 6 |
| 7,311 | 7,311 | 16,320 | 7,424 | 857 | 9 |

All nine maps copied by the controller were generation-contiguous. Final
health flags were zero; the acquisition engine was disabled and flushed after
the run; all three `/tmp` uploads were removed; RX sampling and bandwidth were
restored from 30.72/18 MHz to their original values; and the exact host route
was released.

Source and build evidence:

- FPGA candidate source commit: `02ae824f53bec4495ba8f902d5d26a8958c2d397`
- HDL source commit: `9f3851d33c171a29b28a7b6a5a5469759ad5c79f`
- final M2 host source commit: `392585326cea7ebacbbf438071cb5e4d70a123fc`
- frozen source tag:
  `starlink-rx-only-dnm-v1-source/firmware-pss15-m2-host-v12`
- v7 package SHA-256:
  `8e0e2bfbe8a6c645fe26cb12a24fc3dc89487ad4ba0ea29f4af7cfa8d58c7f9b`
- packaged bitstream SHA-256:
  `7502d3b14516b52a54a66c289c832c3e83859284d657954c158a6e678d325828`
- routed checkpoint SHA-256:
  `34ebbb324746811a3cb45e4da859eba3abc842a4a52d8434a120ef0d1064636e`
- final static ARM controller SHA-256:
  `712d270fffeaa5884b4133a25997f6589a65e38fe57bad051a9a4e4126f0fecc`
- M2 plan SHA-256:
  `ae12d1022c57d607da86c7bd5cce1c7f1fbec4ca481f3c96707056c04883b07a`
- passing M2 receipt SHA-256:
  `9670c8887ed84262f221346ad8acca5554bd3b10a3e589fcbb32e385c2aa8bf9`
- passing recovery receipt SHA-256:
  `fc7d3904424639c44011eb8d88be3925e8eecf1597f27e1485b5296e543efcfb`
- post-recovery serial-restricted inventory SHA-256:
  `b1b36943aaba451197859a09662082a481fb3fc6fa85ee1cf02610f2e6160cd9`

The final recovery proved USB departure and return, a new boot ID, unchanged
`qspi-linux` SHA-256
`07e6163bb27837eef080a885d8b116b7524f3693f2455c86b1d56724eaa77eb7`,
the persistent `ad9361-1r1t` target, firmware
`v0.48-plutoplus-spf-iq-direct-async-v3`, TX-safe state, and a released route.
The final inventory was restricted to serial
`104000bac4950008230026001b440a003a`; it scanned four attached radios and
retained exactly that one.

M3 is the next open gate: repeatable cabled-RF 15 MS/s timing with a separately
declared positive path and negative control. M2 evidence must not be presented
as a live-signal detection result.

## M3 offline implementation checkpoint

The receiver-side cabled qualification contract was implemented without
accessing any radio. It adds:

- an absent-only generator for one 80,000-byte cyclic CI16 frame containing the
  exact 66-sample upper-edge PSS at phase 4,096;
- a scoped monitor v2 wrapper that admits the already-qualified v7 RAM image
  while restoring every historical v1 module constant after each call;
- an explicit physical-fixture declaration command that requires a different
  transmitter serial, a direct coaxial path, no antenna, and at least 30 dB of
  effective attenuation; and
- a campaign qualifier that freezes transmitter sample rate, LO, gain, three
  receiver-monitor plans, and the decision policy before measurement, then
  independently recomputes a positive-A / muted-negative / positive-B result
  and requires a final TX-mute receipt.

The frozen M3 policy requires at least 32 candidate windows per dwell,
peak-to-median at least 1.15, robust z at least 6.0, an 80% positive pass
fraction, an eight-window continuous phase track, no more than a 5% negative
pass fraction, no consecutive negative track, and at least 1.10x median
positive/negative contrast. Phase evolution is checked against the reported
drift hypothesis with a 16-sample residual tolerance. This is a cabled PSS
acquisition/timing claim only; SSS and frame lock remain false.

Deterministic stimulus identities:

- waveform SHA-256:
  `00a3f70878d48ed0f3d60967c41b6c280954270bc69e7af4754439a05afa5829`;
- projected template SHA-256:
  `3c4e6e36250c970c2905ae64d177e0d9d40e941702483f15f11cc57e88edaced`;
- quantized template SHA-256:
  `8037e79412eb6b887c9cd99c2d84a8263c80f0d94e7aec0b1a137f3eee7e2b30`;
  and
- source manifest:
  `manifests/starlink-pss-m3-cabled-dnm-v1-source.yaml`.

The source checkpoint is commit
`b65f66021e9a77aa807b1cbf350d3c59b6462036`, frozen and pushed as
`starlink-rx-only-dnm-v1-source/firmware-pss15-m3-offline-v1`. The generated
mode-0600 waveform and evidence are retained at
`/home/mouse9911/pluto-state/starlink-rx-only-dnm/m3-cabled-20260907/offline-v1/waveform`;
the evidence JSON SHA-256 is
`3fe6b082c567569cb7f41bedbbb76c0ca850a2884ebf375eae605d6890128f1e`.

Focused offline tests include an end-to-end synthetic campaign, strict v7/v1
scope restoration, insufficient-attenuation and antenna rejection, reversed
or inconsistent state rejection, final-mute enforcement, and recomputation
that rejects a modified qualification receipt. The complete
`tests/test_starlink_pss*.py` suite passes 161 tests.

M3 remains open. No transmitter was selected or keyed, and neither the
allocated receiver nor any spare radio was accessed by this checkpoint. A
hardware executor and its stimulus receipts must not be finalized or run until
the physical fixture identifies one otherwise-unused transmitter, confirms
the cabled attenuator chain, and confirms that the transmitter is not owned by
the active acquisition process. If the two radio clocks differ by more than
the current seven-hypothesis drift bank covers, first perform a separate
low-power cabled clock calibration, then freeze a transmitter sample rate
within +/-100 ppm in the final M3 campaign plan.

## M3 guarded executor offline checkpoint

The fail-closed bench executor was completed offline at source commit
`f03666c330d0b5255cf63725a4331947dd59af96`. It is bound in
`manifests/starlink-pss-m3-cabled-dnm-v2-source.yaml` and hard-codes the one
reserved spare transmitter: serial `1040007c4a94000211000b009186843ef2`, USB
topology `3-11`, and host interface `enx00e02297811f`. A fixture naming any
other transmitter cannot produce a valid execution plan.

The executor adds two layers:

1. a low-level single-TX libiio primitive that begins and ends muted, accepts
   only an exact 1R1T CI16 scan layout, validates the complete mode-0600
   waveform before DMA, powers the LO and enables gain only after a verified
   cyclic-buffer push, and mutes gain/selectors/DDS/LO before buffer release;
2. a plan/execute/verify orchestrator that attests the clean PPU checkout,
   resolves the exact serial/topology/interface twice around PPU's shared
   serial lock, rejects another process holding the exact USB device, uses the
   fresh bus/device IIO URI, runs positive-A / muted-negative / positive-B,
   and unconditionally attempts a final mute and deterministic context close.

The installed legacy pylibiio has no public `Context.close()` and no
`Buffer.close()`. The executor therefore uses the same deterministic native
context-destroy pattern already present in PPU, clears the wrapper pointer to
prevent a later double destroy, and uses buffer cancellation followed by
reference release. Both legacy and modern cleanup paths have fake-IIO tests.

Offline evidence for this checkpoint:

- 20 focused transmitter/executor tests: PASS;
- both M3 source-manifest suites (four tests): PASS;
- complete Starlink Python regression: 312 passed;
- strict native C self-tests: PASS;
- ASAN/UBSAN acquisition, injection, and M2 qualification tests: PASS;
- static ARM controller builds: PASS; and
- PPU remained unchanged on clean `main` commit
  `7210cda9b0b2452cb607b5e49e689e2d60b6a8b7`.

No radio was opened, configured, flashed, or keyed while creating this
checkpoint. M3 still has no PSS result. The next gate is operator confirmation
of a direct `TX1 -> attenuator chain -> RX1` path, no antenna, and at least
30 dB measured/effective attenuation (40 dB recommended). Only then may an
execution plan expose its exact one-time confirmation phrase. After the three
receiver dwells, qualification remains offline and PPU recovery of the
allocated receiver remains mandatory. SSS and frame lock stay false.

### Deterministic receiver-context follow-up

An additional offline audit found that the installed legacy pylibiio exposes
neither public `Context.close()` nor `Buffer.close()`. The v2 receiver monitor
previously restored all RX attributes but treated context closure as best
effort. That is acceptable for eventual Python reference cleanup, but too weak
for three back-to-back evidence dwells.

Source commit `3f302560d11bc7daeec66cd24dacc43e738bc288` therefore adds versioned
operational entry points without changing the frozen v1/v2 source graphs:

- `scripts/starlink_pss_monitor_probe_v3.py` wraps the receiver context with
  the modern/legacy deterministic closer from the exact attested PPU checkout;
- a monitor that otherwise succeeds is forced to fail if exactly one context
  was not deterministically closed, including when the inherited cleanup path
  suppresses the close exception; and
- `scripts/starlink_pss_m3_execute_v2.py` forces all three receiver dwells
  through monitor v3 and writes an adjacent mode-0600 runner receipt binding
  the base execution receipt and exact runner/monitor source identities.

The immutable graph is
`manifests/starlink-pss-m3-cabled-dnm-v3-source.yaml`. Eleven focused cleanup
tests and the full 325-test Starlink Python regression pass. No hardware was
accessed, and PPU remains unchanged on clean `main` commit
`7210cda9b0b2452cb607b5e49e689e2d60b6a8b7`.

The pushed deterministic-runner tag was independently expanded into a fresh
temporary tree; all 40 focused M3 monitor/executor/manifest tests passed from
the tagged archive. The exact PPU RX-only lifecycle suite also passes all 24
tests, including its legacy native-context destroy case. Operational commands
must use `/home/mouse9911/gits/pluto-plus-utils/.venv/bin/python` because that
attested environment supplies NumPy and the installed pylibiio binding; direct
execution through the host `/usr/bin/python3` is not an approved environment.

## M3 hardware qualification and evidence log

M3 completed on 2026-09-07 using only the two declared cabled-fixture radios:

```text
1040007c4a94000211000b009186843ef2 TX1
  -> one 30 dB fixed attenuator
  -> 104000bac4950008230026001b440a003a RX1
```

All other RF ports were disconnected and no antenna was present. The separate
transmitter ran the sealed 15 MS/s cyclic PSS waveform at 2.4 GHz and -30 dB
hardware gain for positive A and positive B. The intervening negative dwell
was acquired only after the TX buffer, selectors, DDS sources, and TX LO were
muted.

The first hardware execution exposed that PSMA 1.1 retains its counters until
PL reset. A successful monitor's deliberate shutdown can therefore leave one
`discontinuity_abort_count` even though no observation fault occurred. The
versioned monitor-v2 runner records that inherited shutdown baseline, rejects
a stale ready map or saturated baseline, requires every other baseline fault
field to be zero, and requires all fault fields to remain unchanged throughout
the new observation. Its summary reports bounded-observation deltas. The v7
FPGA image and the frozen v1 controller were not changed.

Passing cabled results:

| Dwell | Candidate windows | Passing windows | Longest track | Median peak/background | Median robust z |
| --- | ---: | ---: | ---: | ---: | ---: |
| Positive A | 56 | 56 | 56 | 4.4652 | 108.40 |
| Muted negative | 56 | 1 | 1 | 1.3497 | 4.93 |
| Positive B | 56 | 56 | 56 | 4.4680 | 108.75 |

Both positive tracks had a median drift of four bins per 64 frames and a
maximum model residual of eight canonical samples. The minimum positive to
negative median contrast was `3.3083x`, exceeding the sealed `1.10x` gate.
Every dwell copied 58 contiguous maps and produced 56 candidate windows with
zero in-observation ingress, scheduler, detector, arithmetic, map, protocol,
or DDC faults.

Final safety and recovery:

- the final TX receipt proves `-89.75 dB`, TX LO powerdown, no cyclic buffer,
  no over-the-air transmission, and successful cleanup;
- deterministic native IIO context closure passed for both radios;
- PPU recovery proved pre-reset USB departure, a new persistent boot,
  byte-identical QSPI, firmware `v0.48-plutoplus-spf-iq-direct-async-v3`,
  runtime target `ad9361-1r1t`, TX-safe state, and released host route; and
- no experimental image was written to persistent storage.

Source and evidence identities:

- monitor-v2 source commit: `a5f354918f276812cedfc6fe9a1b59671bcf1951`;
- source manifest: `manifests/starlink-pss-m3-cabled-dnm-v5-source.yaml`;
- static monitor-v2 binary SHA-256:
  `61bbd6cd86ebb0a986aa62a57564da1748ce04fab0ad17c48a3ace22d5eaee1d`;
- M3 qualification receipt SHA-256:
  `4a866a8e0ef2f7467eb15a5e8050210d21df19d50747fc97bb646cf992e08a31`;
- guarded execution receipt SHA-256:
  `052900765fc5930eb4caa1888eefc4301df6e42ff3848c8ea6734df65b2cd34b`;
- stable-TX runner receipt SHA-256:
  `c7790ec968b87cbf1a4c3d325d84885eef1925fe49b5bc54e9626ec7658697a7`;
  and
- RX recovery receipt SHA-256:
  `97d7238c318fac7f1b021b331cea56e8cab0ef93e4e575e7ef5606ea52d59da5`.

The authoritative private campaign directory is:

`/home/mouse9911/pluto-state/starlink-rx-only-dnm/m3-cabled-20260907/hardware-attempt3`

The hardware verdict is `PASS_M3_CABLED_PSS_ACQUISITION_ONLY`. It validates
the RX/TX coaxial setup and 15 MS/s PSS acquisition/timing. It is not an SSS
result or a frame-lock claim. M4 live-LNB 15 MS/s observation is the next gate.

## M4 live-LNB runner offline checkpoint

The Ethernet-only M4 runner is implemented as
`scripts/starlink_pss_m4_live_v1.py`. It reuses the immutable v7 15 MS/s FPGA
image and the monitor-v2 ARM controller; no FPGA or persistent-radio state is
changed by this checkpoint. Full-rate IQ remains inside the radio. The host
receives only complete phase maps, candidate statistics, health telemetry, and
one bounded 32,768-sample clipping probe whose IQ payload is immediately
discarded.

One execution consists of three 80.5-second roles:

1. channel-4 upper-edge on-channel scan A;
2. a non-overlapping same-channel control slice 50 MHz inward; and
3. the same on-channel scan B.

Each role starts the FPGA detector only once and uses 25 interleaved receiver-LO
points at 100 kHz spacing over +/-1.2 MHz. The first point discards the two maps
needed to fill the rolling detector window. Every later retune waits 200 ms and
discards five maps so RF settling and rolling-window contamination cannot enter
the decision. Exactly 32 subsequent candidate windows are retained per point.
The map-count schedule consumes 922 maps, about 78.7 seconds, and leaves a
bounded tail inside the 80.5-second observation. This scan covers the CFO modes
seen in prior live captures without assuming that one fixed LO remains aligned
throughout the observation.

The runner and offline verifier require the exact receiver serial, LAN host
`192.168.1.17`, interface `enp132s0`, AD9361 1R1T runtime, fresh RAM boot ID,
unchanged QSPI hash, RX-only device-tree surface, 15 MS/s sample and bandwidth
readback, factor-one FPGA path, chronological scan records, zero transport
fault deltas, conservative 32-bit accepted-score counter headroom,
positive/control/positive contrast, complete restoration, and a subsequent PPU
recovery. The plan binds its own runner source and the M4 source manifest so
execution cannot silently drift after sealing.

The remaining M4 hardware prerequisite is physical: remove the attenuated
bench cable, connect only RX1 to the powered outdoor 9.75 GHz LNB, and preserve
power continuously after the fresh volatile v7 RAM boot while moving to the
Ethernet-only location. Fixture sealing also requires the exact LNB model,
polarization, supply voltage, and power-source description. M4 remains open
until the resulting live receipt and recovery receipt pass offline
verification.

### M4 cabled scan preflight and continuous-role revision

On 2026-09-07 the exact M3 fixture was reused for an M4 scan preflight:

```text
1040007c4a94000211000b009186843ef2 TX1
  -> one 30 dB fixed attenuator
  -> 104000bac4950008230026001b440a003a RX1
```

The test exposed and corrected two hardware-only assumptions in the offline
M4 runner. The AD9361 PHY clock must be written before the FPGA capture-rate
attribute when entering 15 MS/s from 30.72 MS/s; commit `42e215cf0` adds that
ordering and a regression test. The v7 detector must also remain enabled for
the complete receiver-LO scan. Starting and stopping it once per LO point can
eventually set the sticky candidate-path health bit during pipeline shutdown.
A single continuous observation with receiver retunes between map groups avoids
that fault and preserves zero-loss map accounting.

Two 119-second continuous scans passed on one fresh RAM epoch:

| Role | Stable windows | Passing windows | Passing LO points | Longest false track | Median point peak/background |
| --- | ---: | ---: | ---: | ---: | ---: |
| Active PSS A | 1,250 | 1,200 | 17 / 25 | n/a | 4.2795 |
| TX-muted control | 1,250 | 7 | 0 / 25 | 1 | 1.3485 |

Each role copied 1,394 contiguous maps in 119.017 seconds and produced 1,392
global candidate windows. Every ingress, scheduler, detector, arithmetic, map,
protocol, and DDC fault counter was zero. Active clipping was zero with maximum
absolute S12 component 1,441. The median active-to-muted point contrast was
`3.1736x`. TX cleanup proved -89.75 dB gain, TX LO powerdown, DAC selectors 3/3,
zero DDS sources, no active buffer, and deterministic context close. RX settings
were restored exactly and the Ethernet boot/QSPI identity was unchanged.

The active response is deliberately not interpreted as one contiguous CFO
bandwidth. The sparse, high-SNR synthetic PSS produces repeatable matched-filter
lobes: the central 0 and +/-100 kHz points track strongly, +200 kHz is the
largest peak, -200 kHz is rejected, and additional stable lobes occur farther
out. The production search must rank LO hypotheses and retain timing continuity;
it must not label the full -1.2 to +1.2 MHz passing-offset extent as capture
bandwidth.

A third 119-second active repeat produced all 25 point measurements but was
correctly rejected by its global gate because the persistent 32-bit
`accepted_scores` counter saturated at `0xffffffff`. At 15 MS/s one PL epoch can
represent about 286.3 seconds before that counter saturates. Therefore the
current 3 x 117.5-second live plan and the current per-point start/stop executor
are not approved for the outdoor run.

The resulting M4 revision uses three continuous roles of 80.5 seconds each.
Each LO point retains exactly 32 stable candidate windows after the initial
two-map fill or five discarded retune/rolling-window maps. The three roles
consume 241.5 seconds of one PL epoch while preserving the frozen
minimum-window policy. Its fail-closed budget permits the monitor validator's
maximum map-count jitter: 946 maps per role, or 3,632,640,000 accepted scores
for all three roles, strictly below the `0xffffffff` saturation value. After
the first role, the runner combines the observed starting count with that full
budget and refuses to continue without sufficient headroom. The plan schema,
receipt schema, verifier, and direct continuous-stream unit test encode the
same schedule. Cabled requalification of this exact production path is the
remaining gate before an LNB is connected.

Private evidence:

- active-A receipt SHA-256:
  `1133b692a64b96757ceab254a1c3b86552319547c5435fab830181456b7b3ffa`;
- muted-control receipt SHA-256:
  `00cccaf8575a03670dbebae723f3de62c54bb26a1b78344ee475b860dcc7dada`;
- expected saturation failure receipt SHA-256:
  `d6d4514208d05ad502442e6846fc8fa1f4c8eb61dc6c0e9f33ac09bc47e21e88`;
- first cleanup/recovery receipt SHA-256:
  `cbbd306ff3ac060941938505687b3614075c0395d478d57d1ada5f102053817d`;
- final cleanup/recovery receipt SHA-256:
  `04bf41cb0ffad490f361e046a1bfa6c358b03997baf7ca4b5a2ec6b21db26bb8`.

The authoritative scan directory is
`/home/mouse9911/pluto-state/starlink-rx-only-dnm/m4-live-20260907/attempt2`.
After testing, `.17` was recovered to persistent
`v0.48-plutoplus-spf-iq-direct-async-v3` with unchanged QSPI, and `.18` remained
positively muted. PPU remained unchanged on clean `main` commit
`7210cda9b0b2452cb607b5e49e689e2d60b6a8b7`.

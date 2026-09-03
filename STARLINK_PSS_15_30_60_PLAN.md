# Starlink PSS 15/30/60 MS/s RX-only development plan

Status: experimental and **DO NOT MERGE INTO FIRMWARE MAIN**. The experimental
FIT/DFU image is RAM-only: it is RAM-booted and is never written to QSPI. PPU
setup may make
deliberate, receipted changes to the persistent U-Boot radio-target environment;
the campaign is incomplete until its final 2R2T restoration gate passes.

Primary target radio: `104000bac4950008230026001b440a003a` only. In runtime,
resolve the exact serial to one direct USB topology/interface, acquire the serial-scoped and
endpoint locks, and revalidate immediately before mutation. During DFU, retain
those locks and accept only the locked topology plus exact VID/PID; reject a
different serial if one is exposed, and re-attest the exact serial/topology on
runtime return. A USB address, serial TTY, network interface, or `usb:B.D.I` URI
is never identity by itself.

Existing serial-bound hardware qualification records identify this exact unit
as a physical AD9363A. Selecting `ad9361-1r1t` changes the compatible/driver
policy and its software bandwidth clamp; it does not turn the die into an
AD9361. Accordingly, this radio can fully qualify the 15 MS/s stage within the
AD9363A bandwidth class. Its 30/60 MS/s trials are useful for FPGA scheduling,
DMA, clock, recovery, and narrowband RF characterization. With
`ad9363a-1r1t` and RF bandwidth at or below 20 MHz, those are in-spec
narrowband/sample-rate trials; requesting more than 20 MHz through the
`ad9361-1r1t` personality is explicitly out of specification. Neither case can
establish full-band Starlink reception. Full-band Gates 4 and 5 need a second
serial-bound radio with physical AD9361/AD9364 attestation; otherwise those
full-band pass states remain open by design.

## 2026-09-02 Stage-15 hardware checkpoints

The corrected ABI 1.1 image has now completed one exact-radio RAM lifecycle and
one scheduled live tracker transaction under the `ad9361-1r1t` driver
personality. The candidate boot, RX-only layout, controller contract,
coefficient commit, sample-clock advance, one capture/correlation/reduction
transaction, success-counter deltas, zero error-counter deltas, recovery, and
final 2R2T restoration all passed. The candidate never wrote QSPI; the full
QSPI partition SHA-256 was identical before, during, and after the RAM trial.

The second trial used the physical unit's native `ad9363a-1r1t` profile. It
proved exact 15,000,000 S/s PHY and capture-core readback, the only advertised
capture alternatives `[15,000,000, 1,875,000]`, FPGA factor 1/bypass, the
RX-only no-DDS/no-TX-DMA layout, and another complete scheduled ABI 1.1 tracker
transaction. All eight success counters advanced exactly once, all nineteen
error counters stayed unchanged, and recovery returned the same persistent
QSPI partition before the final verified `ad9361-2r2t` restoration.

The native checkpoint is deliberately labeled
`STAGE15_NATIVE_AD9363A_RATE_LOCKED_TRACKER_TRANSACTION_PASS`. It supersedes the
trial-eligibility record, but does not upgrade the earlier `ad9361-1r1t` trial
to an exact-rate claim. Both transactions used uncontrolled ambient samples,
so neither winning lag is a Starlink detection.

ABI 1.2 now closes the offline portion of the deterministic accepted-sample
injection gate. A committed 130-sample fixture substitutes only I/Q at a future
absolute accepted-sample index while retaining source-derived strobe, enable,
index, and timestamp. That selected stream fans out to both the exact tracker
and the RX DMA packer. The standalone mux covers pass-through, clean completion,
incomplete/late/overlap rejection, and accepted-index mismatch; the real wrapper
replay matches all 210 frozen packets and drives window zero solely through the
injection mux. A clean non-incremental route passes timing and hold, all three
bundled-CDC skew checks, zero tracker-critical CDC rows, and a one-RAMB18
dual-clock fixture implementation. The corresponding immutable source graph is
`manifests/starlink-pss15-injection-abi12-dnm-v1-source.yaml`.

The exact ABI 1.2 bytes have now completed a native-AD9363A RAM lifecycle at
15,000,000 S/s. Window zero matched all 19 frozen packet invariants; during a
second transaction its 520 encoded bytes appeared exactly once in a concurrent
4,000,000-sample RX DMA capture while the tracker again matched its oracle.
Independent window one matched all 19 of its own invariants and differed from
window zero at eight static packet words. Eight further sequential scheduled
window-zero transactions were deterministic, all eight pipeline flow counters
advanced by eight, and all 19 error counters remained zero. This closes the
deterministic accepted-sample hardware, shared-DMA, oracle-rejection, and short
sequential-repeat portions of Gate 3.

The hardware checkpoint is deliberately labeled
`STAGE15_NATIVE_AD9363A_HARDWARE_INJECTION_AND_DMA_PASS` and indexed by
`manifests/starlink-pss15-injection-abi12-dnm-v2-hardware.yaml`, SHA-256
`2f0aa755e92a34fa77ebed3bca7d57b4ffe93d347ffad52ccf028044a19ce5ad`.
Its external-evidence checksum list has SHA-256
`dd284b22aa89f0f315175e08ad4f2c35f316c6bf5608e105f96a213404c37927`.
It does not claim prequeued queue-depth margin: the eight repeat requests were
submitted sequentially. Gate 3 remains open for frozen
RF-bandwidth/filter/gain and timestamp-slope evidence, prequeued 750-Hz
queue-depth and continuity qualification, and live multi-frame PSS evidence.
Those items remain mandatory before Stage 30. This is not an over-the-air PSS,
frame-alignment, or SSS result.

The next Gate-3 revision was source-frozen in
`manifests/starlink-pss15-batch-clock-dnm-v1-source.yaml`. It reuses the exact
ABI 1.2 RTL and routed XSA and adds a fail-closed host controller for seven-deep
prequeue/refill, ordered NDJSON result capture, aggregate counter gates, and
accepted-sample clock-slope measurements. The offline mock fills all seven
usable command slots, drains and refills twelve ordered requests, rejects
overlapping geometry, overflowing request IDs, saturated counters, bad clock
slope, and immediate next-result publication after release. The immutable
source tag itself predates radio contact; its subsequent exact-radio evidence is
recorded separately below.

The frozen hardware qualification is 15,000,000 S/s, 15 MHz RF bandwidth,
factor-one FPGA capture, FIR disabled, slow-attack gain, five one-second clock
observations on both PPU's capture-counter path and the tracker's 64-bit path,
a 750-request smoke batch, then 45,000 centers at exactly 20,000 samples with
queue target seven and at least 65,536 post-submit samples of lead. Four
overlapping 4,000,000-sample DMA segments must complete while the primary batch
runs. Every flow counter must advance by exactly 45,000, every error-counter
delta must be zero, and all request/center/timestamp steps must be exact. This
closes only RF-path, clock, queue, and continuity evidence; live multi-frame PSS
remains a separate open Gate-3 item.

That hardware run is now complete and indexed by
`manifests/starlink-pss15-batch-clock-dnm-v2-hardware.yaml`, SHA-256
`de8f1d37c16992a0e6729fc125a440649c1c561d1f3b40172f1b6a68afc52d0b`.
Its external-evidence checksum list has SHA-256
`2d4f61732cbbdea4778620b2dfc6f43ce35a6f0ff30f1f0b58329b2584848b38`.
The 750-result smoke filled all seven usable entries and passed. Five one-second PPU counter
observations and five tracker-counter observations passed before/after the
primary work, together with exact 15 MHz RF-bandwidth, FIR-off, slow-attack
gain, and factor-one capture readbacks. The final primary run produced 45,000
ordered results over 60.065 seconds while four 4,000,000-sample DMA segments
completed; every success counter advanced exactly 45,000 and all error
counters remained zero.

The scheduling condition is material. Streaming result JSON over USB Ethernet
failed with four result overruns. Moving JSON to radio-local tmpfs under the
ordinary scheduler still failed at ordinal 232 when lead fell below 65,536
samples, again with four result overruns. Radio-local spooling under
`SCHED_FIFO` priority 80 passed with a minimum measured lead of 128,727 samples.
Therefore the seven-entry queue is qualified only with that real-time policy;
ordinary best-effort Linux scheduling is explicitly unqualified. This is useful
Stage-15 implementation/transport evidence, not live Starlink detection. Live
multi-frame PSS remains open, and this plan does not authorize Stage 30 until
that final Stage-15 item is reviewed.

The ABI 1.2 source-locked RAM-only package also passes offline container
qualification. Its DFU SHA-256 is
`e407f7366e8745713ce582217fdcdae90fea2dbce271017cb5638c14fc2a1a7a`;
the extracted FPGA payload is byte-identical to the qualified XSA bitstream,
the packed rootfs contains the exact ABI 1.2 controller and fixtures, and
`/opt/VERSIONS` names the immutable DNM source locks. The package now has the
scoped hardware-injection/DMA checkpoint above, but the complete firmware and
Gate 3 remain hardware-unqualified and the package remains
persistent-flash-ineligible.

The earlier compatibility-profile index is
`manifests/starlink-pss15-track-one-dnm-v3-hardware.yaml`; the native,
rate-locked successor is
`manifests/starlink-pss15-track-one-dnm-v5-native9363-hardware.yaml`, read with
its retained tool-provenance correction
`manifests/starlink-pss15-track-one-dnm-v6-tool-provenance-erratum.yaml`. The
native lifecycle used PPU `10ae7c74bb85a0e31f01c308bda8e62209b3c0b2`;
exact RX-only rate attestation, the tracker transaction, and final canonical
setup used PPU `main` `c70d46bb420de05112f2e60052025606321fc8f0`. That commit
passes 1,328 tests with 11 skips, Ruff, mypy, and package builds. The selected
radio ended on persistent
`v0.48-plutoplus-spf-iq-direct-async-v3`, verified `ad9361-2r2t`, four RX scan
elements, and quiescent TX outputs.

The reusable signal-path and sample-clock attestation extension passed 1,330
tests with 11 skips plus Python 3.11/3.12/3.13 and browser CI, and merged through
PPU PR #110 to clean PPU `main` commit
`4ca3451ae6de233b00eb31c38c7d4b29ba6b249a`. All later Stage-15 plans and
receipts bind that commit; no radio trial depends on the deleted feature branch.

The first continuous-acquisition work packet is now implemented offline as
`starlink-pss-acquisition-oracle-v1`. It models a 512-sample overlap-save
correlator, exact rational score quantization, bounded phase-map production,
and ARM-side shift-and-sum cadence hypotheses. It is checked against two
independent real 15 MS/s positive chunks, one independent RF-negative chunk,
and deterministic frame-scrambled controls. This is algorithm and data-product
evidence only; it is not an RTL FFT, routed design, radio result, or live-PSS
qualification.

The held-out weaker positive rejects the earlier four-sample-bin proposal: its
robust z falls below the unchanged 6.0 gate for every tested coarse bin at the
64-frame geometry. The retained acquisition-v1 candidate therefore preserves
all 20,000 phase samples, quantizes normalized power to eight bits, accumulates
64 frames into 16-bit stored map words, and exports one 40,000-byte map per
85.333 ms per template. Both real positives pass the existing joint epoch
gates at this geometry while the independent RF negative and both scrambled
controls reject. The complete checkpoint and machine-readable reports are in
`reports/STARLINK_PSS_ACQUISITION_ORACLE_V1.md` and its three referenced JSON
files. The production false-alarm policy remains open pending a predeclared
multi-capture corpus partition.

The authoritative device limits used by these gates are Analog Devices'
[AD9363 data sheet](https://www.analog.com/media/en/technical-documentation/data-sheets/AD9363.pdf)
(up to 20 MHz channel bandwidth) and
[AD9361 data sheet](https://www.analog.com/media/en/technical-documentation/data-sheets/AD9361.pdf)
(up to 56 MHz channel bandwidth); both distinguish converter sample rate from
analog channel bandwidth.

## Governance and merge boundary

PPU remains generic product tooling. Reusable PPU work is reviewed, tested,
and merged to PPU `main` so radio setup and release evidence do not become an
untracked experiment. PPU may model, plan, attest, and receipt explicit AD936x
driver/channel targets:

- `ad9361-2r2t`: legacy/default Pluto+ behavior;
- `ad9363a-1r1t`: native constrained driver and one digital RX stream;
- `ad9361-1r1t`: wider AD9361 driver limits and one digital RX stream.

Those names attest the requested and observed Linux driver profile and stream
geometry; they do not claim to identify the physical RFIC die. PPU must remain
waveform-agnostic and contain no Starlink-specific detector policy.

That distinction is a hard qualification boundary. A driver readback of
`ad9361` does not prove that the soldered device is an AD9361. Before either
30 MS/s or 60 MS/s can claim full intended RF bandwidth, retain a serial-bound
physical-device attestation from an authoritative BOM/vendor record or a clear
board/part-marking inspection. If that evidence is unavailable, an
`ad9361-1r1t` run may still be retained as an experimental sample-rate result,
but it is explicitly unqualified and potentially out of specification for
AD9363 silicon; measured response alone is not relabeled as die identity.

PPU follows a stop-the-line promotion rule throughout the campaign. If a radio
trial exposes a reusable setup, identity, receipt, recovery, or inventory gap,
pause the trial; implement the generic fix on a short-lived PPU branch from
current `main`; run the full offline suite; merge it by pull request; fast-forward
the local PPU `main`; and record that new clean commit in every later operation
plan and receipt. No target-radio trial may depend on an unmerged PPU commit or
an experiment-only copy of PPU logic.

All Starlink waveform, detector, RX-only HDL/Linux, build, and radio-trial work
stays on `codex/starlink-rx-only-do-not-merge` and identically marked submodule
branches. The root `DO_NOT_MERGE_INTO_FIRMWARE_MAIN` marker and DNM source
manifest travel with the experiment. Before any candidate build, record the
firmware-main-side ruleset/required-check identity and live negative-PR results
that separately reject the DNM branch name and a warning marker hidden under an
ordinary renamed path. Experimental
artifacts may be tagged and retained, but this source graph is never merged or
cherry-picked to firmware `main`.

Before the experimental parent advances to a new component gitlink, append both
the reviewed source commit and any separate evidence commit to firmware main's
base-owned gitlink denylist through its strictly append-only policy path. The
same PR must prove the new pins are enforced; executable guard policy remains
immutable. Thus future detector work can continue on the retained DNM branches
without leaving a source-only commit outside the firmware-main promotion guard.

Current control-plane evidence:

- reusable radio lifecycle work is on PPU `main` at
  `8074b228083240860843b0fb4dd4d5b46f06805b` through PPU PR #109;
- generic firmware promotion guard PR #76 merged to firmware `main` as
  `7ef0a768096207526dc39331e0bedbce8c9f02dd` after all four existing required
  checks passed;
- guard PR #80 appended the exact Stage-15 split-reset and routed AXI-tracker
  HDL pins, passed all five checks, and merged to firmware `main` as
  `7a646abc591fbeb6f1c32a1addcebced2e8b1517` before the experimental parent
  advanced its HDL gitlink;
- guard PR #81 appended the exact ABI 1.2 injection HDL source/evidence pins
  and Buildroot controller/package pins, passed all five checks, and merged to
  firmware `main` as `3c9dea6d8f061f55b2615689783dd0e6aa4999c5`
  before the experimental parent advanced either gitlink;
- guard PR #82 appended all three immutable phase-map HDL review pins, passed
  all five checks, and merged to firmware `main` as
  `ae9be3ec411eeebe0ee396b93c0f59e2d9d1940b` before this parent advanced to
  the selected v3 pin;
- guard PR #83 appended the exact overlap-save scheduler HDL pin, passed all
  five checks, and merged to firmware `main` as
  `fed8a275c21abac4360b2a55a2f0bda8828efa4e` before this parent advanced to
  the scheduler pin;
- guard PR #84 appended the exact spectrum-product HDL pin, passed all five
  checks, and merged to firmware `main` as
  `60169ef8c35cca1ce18c062625141c78a4bb2d3b` before this parent advanced to
  the spectrum-product pin;
- guard PR #85 appended the exact energy-cache HDL pin, passed all five checks,
  and merged to firmware `main` as
  `dfe129b6eed7c7d9adbe4bd1d5451442284dce81` before this parent advanced to
  the energy-cache pin;
- guard PR #86 appended the exact rational score-divider HDL pin, passed all
  five checks, and merged to firmware `main` as
  `0c6f96ef4d95426da4c62a4b30828e5535b7b5c4` before this parent advanced to
  the divider pin;
- guard PR #87 appended the exact exponent-aware score-preparation HDL pin,
  passed all five checks, and merged to firmware `main` as
  `bfb0247a374724efde0589dcb259bb1396cf4abd` before this parent advanced to
  the preparation pin;
- guard PR #88 appended the exact 512-entry raw IFFT-result FIFO HDL pin,
  passed all five checks, and merged to firmware `main` as
  `627f1f48e776e174095d34822a8ce3506ed0aebb` before this parent advanced to
  the FIFO pin;
- guard PR #89 appended the exact composed IFFT-candidate score-path HDL pin,
  passed all five checks, and merged to firmware `main` as
  `e1966f5fe20370aa841e16143eb05c94152ea8eb` before this parent advanced to
  the candidate-score-path pin;
- guard PR #90 appended the exact strict XFFT block-adapter HDL pin, passed all
  five checks, and merged to firmware `main` as
  `68ef649d2fd76b62f437148a222f0881d50ea7f2` before this parent advanced to
  the XFFT-adapter pin;
- guard PR #91 appended the exact hash-locked upper-edge kernel-ROM HDL pin,
  passed all five checks, and merged to firmware `main` as
  `250fc46cc57f38aec6a8321990f84460fb73d749` before this parent advanced to
  the kernel-ROM pin;
- firmware `main` strictly requires `experimental firmware merge guard` from
  GitHub Actions app `15368`, in addition to the four preserved checks; and
- active no-bypass tag rulesets protect the
  `starlink-rx-only-dnm-v1-source/*` namespace against update or deletion in
  firmware (ruleset `22043674`), HDL (`22044279`), and Linux (`22044287`).

The two live negative canaries are complete:

- [firmware PR #77](https://github.com/misko/plutosdr-fw/pull/77) at experimental head
  `0ca087edb5f7f67156c55faa7916668e82903742` was rejected by required guard
  [run `33558147580`](https://github.com/misko/plutosdr-fw/actions/runs/33558147580)
  with the exact reason `experimental branch name is
  forbidden: codex/starlink-rx-only-do-not-merge`; and
- [firmware PR #78](https://github.com/misko/plutosdr-fw/pull/78) at ordinary-named canary head
  `d5518234c2e3c0575ea0c5c9b6071cdf75bdff9f` was rejected by required guard
  [run `33558248086`](https://github.com/misko/plutosdr-fw/actions/runs/33558248086)
  because hidden
  `docs/firmware-guard-canary.md` contained an experimental warning marker.

Both PRs are closed with `mergedAt=null`. The temporary PR #78 branch was
removed after its unrelated long checks were cancelled; the real DNM branch
used by PR #77 remains retained. This satisfies the live branch-name and
renamed-content promotion guard gate.

## Fixed geometry and rate strategy

The native waveform model is 240 MS/s, 1024 useful samples, 32 samples of
inverted prefix, and a 750 Hz frame rate. Its exact integer projections are:

| RX/DMA rate | Projected useful/prefix/symbol at RX rate | Samples/frame | Direct taps / qualified lags / raw guard lags | One-bank raw correlation tap-cycles/s | Continuous-acquisition lane |
|---:|---:|---:|---:|---:|---:|
| 15 MS/s | 64 / 2 / 66 | 20,000 | 66 / 61 (`+/-30`) / 65 (`+/-32`) | 3.2175 M | none |
| 30 MS/s | 128 / 4 / 132 | 40,000 | 132 / 121 (`+/-60`) / 129 (`+/-64`) | 12.771 M | required, separately qualified x2 DDC to 15 MS/s |
| 60 MS/s | 256 / 8 / 264 | 80,000 | 264 / 241 (`+/-120`) / 257 (`+/-128`) | 50.886 M | required, separately qualified x4 DDC to 15 MS/s |

The default design separates continuous acquisition from exact tracking.
Acquisition always uses the canonical 15 MS/s, 66-tap geometry: native bypass
at 15 MS/s and separately qualified x2/x4 DDC lanes at 30/60 MS/s. Exact
tracking remains sparse, candidate-gated direct correlation at the full RX
rate; it does not process the continuous stream. The tracking search
qualified half-width is fixed in time at `30/15e6 = 2 us`. For rate multiplier
`m` in `{1,2,4}`, taps are `66m` and the qualified winner aperture has
`60m+1` lags. The capture/raw-trace guard remains `32m` on either side, so the
raw trace has `64m+1` lags and capture length 130, 260, or 520 samples. This
keeps the capture interval at 8.667 us and yields guarded ranges
`p-32..p+97`, `p-64..p+195`, and `p-128..p+391`. Guard tuples are diagnostic
only and cannot win `TRACK_ONE`.

Correlation tap count alone is not a schedule. The direct design computes each
captured sample energy once, forms the first `Ex` window, then updates it by
`Ex[k+1] = Ex[k] - e[k] + e[k+N]`; validated coefficient `Eh` is cached at
commit. With `N=66m`, raw guard count `Lraw=64m+1`, qualified count
`Lq=60m+1`, and capture length `M=N+Lraw-1`, the currently implemented
conservative budget is `M + (Lraw-1) + B*Lraw*N` cycles for `B` coefficient banks,
before small wrapper/publication overhead. Here `B=3` and `B=9` mean all lags
for every bank; they are validation/diagnostic modes, not the one-lag CFO
refiner. A later engine may avoid computing the outer guard tuples, but no rate
gate takes credit for that optimization before bit-exact and routed evidence:

| Rate | `TRACK_ONE` | Three-bank full-aperture validation | Nine-bank full-aperture diagnostic | Declared scheduling consequence |
|---:|---:|---:|---:|---|
| 15 MS/s | 4,484 cycles / 3.363 Mcycles/s | 13,064 / 9.798 Mcycles/s | 38,804 / 29.103 Mcycles/s | all fit a 100 MHz engine |
| 30 MS/s | 17,416 / 13.062 Mcycles/s | 51,472 / 38.604 Mcycles/s | 153,640 / 115.230 Mcycles/s | nine-bank per-frame mode does not fit 100 MHz |
| 60 MS/s | 68,624 / 51.468 Mcycles/s | 204,320 / 153.240 Mcycles/s | 611,408 / 458.556 Mcycles/s | one bank fits 100 MHz; three need a routed 200 MHz engine; nine are diagnostic/offline only |

Normal tracking therefore uses one locked CFO bank. `VALIDATE_BANKS(K)` uses
the full-aperture formula above and is commanded less frequently; the 200 MHz
60-MS/s condition applies only if three full-aperture banks are demanded every
frame. `CFO_REFINE(K)` instead evaluates `K` banks at one already selected lag:
its additional correlation work is only `K*N` cycles, or 594, 1,188, and 2,376
cycles for nine banks at 15, 30, and 60 MS/s. If run from its own N-sample
capture, conservatively add `N` sample-energy cycles; if appended to
`TRACK_ONE`, reuse the selected window's `Ex`. Each ABI mode has a separate
formula, admission deadline, and counter. Queue admission includes measured
wrapper/publication latency and rejects work that cannot finish before its
declared result deadline.

The acquisition x2/x4 DDC lane is now an explicit stage deliverable rather than
an optional replacement for exact tracking. Its mixer, filter coefficients,
integer phase, group delay, rounding, saturation, alias controls, post-filter
template digest, and full-rate timestamp mapping form a new versioned oracle.
The direct full-rate tracker remains the reference exact-timing architecture;
any proposal to decimate that bounded tracker window still requires separate
OOC and complete-route evidence. All architectures preserve
detector-independent full-rate RX DMA.

CI16 complex ingress is 60, 120, and 240 MB/s at 15, 30, and 60 MS/s. Host
bootstrap and capture evidence therefore use bounded DDR captures or segmented
readout unless a separate transport gate proves more; no stage assumes continuous
raw USB streaming, including 15 and 30 MS/s.

Sample rate and RF bandwidth are separate evidence fields. Every rate binds the
requested and read-back sample rate, requested and read-back `rf_bandwidth`,
analog filter state, digital FIR/HB/interpolation-decimation state, rate-governor
state, gain state, occupied PSS slice, and measured complex RF response to the
qualification-policy and template digests. The rate oracle either conditions
its template through that frozen deterministic digital response or declares and
tests an explicit ideal-template mismatch allowance. A 60 MS/s IIO stream is
never used as evidence of a 60 MHz flat RF passband.

A tracked result can be produced after a predicted PSS window plus correlator
pipeline latency. Initial acquisition is different: the continuous FPGA score
and phase-map path must first observe enough complete frames for the bounded ARM
map search to establish sideband, phase, and 750 Hz cadence; sparse exact FPGA
correlation then confirms the candidate and refines CFO. No sub-symbol
acquisition-latency claim is made. Once locked, an N-frame observation window is
`N/750` seconds, while latency from the first through the Nth event is
`(N-1)/750` seconds. Thus four events span 4.00 ms first-to-fourth within a
5.33 ms observation allocation; eight span 9.33 ms within 10.67 ms, plus
pipeline and ARM/FPGA handoff latency.

## What the 15 MS/s evidence says

The provenance-bound capture
`cap-20260831T071200-9184cf0ad6cc` is a real 15 MS/s, 1.1875 GHz, upper-edge
recording. It came from another radio, so it is algorithm evidence, not
qualification of the target radio.

Exact PSS template replay found the first timing evidence at about 6.9 s,
reported candidates in 27 of 237 blocks, evaluated 3,665 windows on a 750 Hz
lattice, and produced robust peak z-scores with median 7.227 and maximum
9.876. This is compelling evidence for exact-template-plus-cadence acquisition,
subject to independent false-alarm controls and target-radio confirmation.

The repeated-delay lag metric did not behave as a useful PSS trigger on the
same real data. Across 210 known template-window starts in the first capture
chunk, the metric had median 0.0162 at the exact start; even the best value in
a +/-66-sample neighborhood had median 0.0540 and maximum 0.255. The committed
threshold of 0.75 therefore produced no events. Lowering the threshold is not
a remedy: at 0.05, background exceeded the threshold for about 5.72% of all
windows and formed 39,813 excursions in that chunk.

Consequently:

- the repeated-delay monitor is diagnostic/status plumbing only;
- its threshold remains immutable at 0.75 for this revision;
- structural positive fixtures must trigger it, while the recorded real PSS
  fixture is explicitly expected not to trigger it;
- a lag event is never reported as PSS, frame alignment, or acquisition; and
- failure of the lag monitor to fire on a live signal is not a reason to lower
  its threshold or weaken a test.

## Detector architecture

1. Preserve formatted RX0 I/Q, full-rate timestamps, DMA data, continuity, and
   overflow reporting independently of all detector logic.
2. Continuously acquire in FPGA at the canonical 15 MS/s rate. A shared
   512-sample overlap-save front end produces 447 valid score positions per
   block for the RF-plan-selected lower or upper PSS template. The first image
   permits exactly one enabled template bank; any concurrent two-edge mode
   requires a new routed resource gate. Normalized power is
   quantized to eight bits and accumulated at full one-sample phase resolution
   into 20,000-bin, 64-frame maps. The ARM sees bounded maps, applies the
   frozen robust epoch policy and a small explicitly trial-corrected cadence
   bank, and returns only top candidates. Nine CFO banks remain a sparse
   post-candidate refinement; they are never independently maximized on every
   frame.
3. Hand only bounded predicted windows to a candidate-gated FPGA exact
   correlator. The current engine emits 65 raw guard lags `[-32,+32]` with 66
   template taps, but `TRACK_ONE` admits only the frozen 61 lags `[-30,+30]`
   to its winner reducer. Normal one-CFO tracking currently performs 3,217,500
   complex tap-MACs/s. An explicitly
   commanded three-bank check is 9,652,500, and an all-nine diagnostic is
   28,957,500. Blind acquisition remains on the continuous canonical-15 FPGA
   score/map path, not this sparse tracker. A three-DSP,
   one-complex-tap-per-cycle engine has ample scheduling margin at 100 MHz;
   generated OOC and full-route reports, not this arithmetic, decide acceptance.
4. Deliver the exact engine in two steps. First preserve all 65 raw
   `{lag,index,C_re,C_im,Ex,Eh}` tuples for one host-selected Q1.15 coefficient
   bank so the host can reproduce every score and tie. Then add the exact
   normalized reducer, nine-bank one-lag CFO refinement, adjacent-bank checks,
   and trace mode. Coefficients are host-quantized with round-to-nearest,
   ties-to-even, digest- and CRC-bound, and never synthesized by a runtime NCO.
   The raw trace remains separately available for diagnostics; normal
   `TRACK_ONE` reduces only `[-30,+30]`. The engine reports candidate measurements only; multi-frame alignment and
   false-alarm policy remain on the host.
5. Scale the sparse direct tracking engine at 30 and 60 MS/s: 132 taps/129
   lags, then 264 taps/257 lags, with sliding `Ex`, cached `Eh`, and an elastic
   tuple FIFO before the bit-serial reducer. In parallel, feed the unchanged
   acquisition engine through independently qualified x2/x4 DDC lanes while
   preserving full-rate DMA and exact source-index mapping.
6. Retain the 0.75 repeated-delay monitor only in a separate diagnostic build
   as the already-qualified AXI/CDC reference. Compile it out of the first
   radio-eligible exact-detector image so its 21 DSPs and control logic cannot
   crowd the useful correlator. It is not upstream of exact search and cannot
   suppress it.
7. Begin SSS only after the complete 15/30/60 PSS ladder has closed, including
   timing, sideband, CFO convention, cadence, false-alarm, radio, and rollback
   evidence. Start SSS in the host; move it into FPGA only if profiling shows a
   justified bounded workload.

Autonomous full-stream acquisition is now in scope through the bounded
15-MS/s overlap-save phase-map design. Linux is not assigned a per-frame
deadline: after ARM candidate selection, a PL fixed-point recurrence generator
schedules confirmation and tracking into an aligned result ring. The state
sequence is `ACQUIRE -> CONFIRM -> LOCK -> TRACK -> HOLDOVER -> ACQUIRE`.
The repeated-delay metric is not promoted into this path without new evidence.

### Stage-15 exact-engine contract

The first exact engine runs at 100 MHz and captures exactly 130 tagged samples
around each predicted center: `p-32` through `p+97`. Each output names the
stored raw timestamp at its first tap; no timestamp is reconstructed from
pipeline latency. Disable, FIFO overflow, or a nonconsecutive accepted index
flushes the job and increments a visible abort counter.

The corrected wrapper ABI 1.1 is frozen for `TRACK_ONE`: software reads a coherent
64-bit accepted-sample index, submits a full-width center index/timestamp and
request ID through a buffered command, and receives an immutable 26-word result
packet through a level interrupt. The candidate queue has seven usable entries
and hardware rejects less than 64 samples of lead. Disable, valid gaps, index
jumps, capture/result overflow, and reset flush affected work; separate
diagnostics make each class observable. Gate 2 still must replay every boundary
case through the host driver and retained real windows. An inferred
pipeline-time center is never accepted as equivalent.

A three-DSP Gauss complex multiplier issues one exact tap per engine clock.
CI16/Q1.15 operands feed signed 17x17 products; Gauss reconstruction is
explicitly widened before rounding or saturation into signed 48-bit real and
imaginary accumulation. The mathematical complex-tap and accumulated-width
bounds are proved separately. The Stage-15 sample-energy sum needs 38 unsigned
bits; the 132- and 264-tap geometries need 39 and 40 unsigned bits respectively
(one additional bit if represented as signed). Each rate re-proves those bounds
and widens normalization cross-products before parameterization; retaining a
48-bit accumulator is sufficient but is not accepted without that proof.
Stage-15 committed coefficient energy is constrained below 31 bits, and exact
normalized-score comparison uses wide rational cross-products rather than a
divider or floating point. The same three DSPs are time-multiplexed for a
bounded sample-energy prepass and
coefficient-commit validation before the one-tap-per-clock complex loop; the
design does not quietly assume two extra squaring multipliers. The raw-result
milestone precedes the winner reducer so its arithmetic can be checked
independently.

The isolated Stage-15 raw milestone intentionally recomputes `Eh` per job and
`Ex` per lag because that makes every emitted tuple independently auditable. It
is not the final 30/60 scheduler. Before scaling geometry, preserve its exact
tuple behavior while moving validated `Eh` to coefficient commit and replacing
per-lag energy prepasses with the sliding-`Ex` schedule above. A differential
test must compare all raw tuples before and after that optimization.

The exact engine replaces the diagnostic monitor in the 4 KiB AXI aperture at
`0x79030000`; both are never present in the radio-candidate shell. ABI 1.1
implements only `TRACK_ONE`, with a 66-tap shadow/active coefficient bank,
61 qualified winner lags, commit generation and energy validation,
double-buffered atomic results, and processed/aborted/overrun diagnostics.
Offsets `0x84..0xb8` expose fourteen sample-domain counters only through an
explicit toggle-requested 448-bit atomic snapshot, never as tearing live binary
CDC. Future
`CFO_REFINE`, `VALIDATE_BANKS`, and `SINGLE_SHOT_TRACE` modes require a new
versioned capability/ABI extension and do not block the first one-bank radio
trial. The host evidence bundle, not the FPGA register file, binds the template
SHA-256/CRC to the acknowledged coefficient generation.

The original 3-DSP, 5-BRAM-equivalent, 2,500-LUT, 2,000-register target was a
planning estimate, not an acceptance override. Routed Stage 15 establishes the
real baseline: exactly 3 DSP48E1s and 5.5 BRAM tiles in the tracker hierarchy;
the corrected core OOC result is 4,267 LUTs and 3,565 registers. The complete shell still
fits, but 30 and especially 60 MS/s must earn their geometry through fresh OOC
and full-route evidence rather than scaling this estimate arithmetically.

The 21-DSP repeated-delay monitor remains a source-locked historical AXI/CDC
reference, but the exact Stage-15 shell compiles it out. No PSS function depends
on it and it is not reintroduced at 30 or 60 MS/s.

The legacy fixed `/8` RX FIR is also not a 30/60 detection lane. It is forced to
bypass for Stage 15 and removed before Stage 30 unless a separately reviewed
consumer proves it is still required. The trusted RX-only baseline currently
uses 28 DSPs; approximately 22 belong to that FIR and 21 more appear only when
the diagnostic monitor is present. Those deltas explain why one RX and no TX
create useful headroom, but only new complete route reports establish the final
resource budget.

Bypass alone does not establish 15 MS/s. The current device tree advertises an
AXI decimation core, so the capture driver interprets its sampling-frequency
write as only factor 1 or factor 8 relative to the RFIC parent, whose source
default is 30.72 MS/s. The Stage-15 image and PPU operation therefore bind one
source-locked transaction: program the PHY parent to exactly 15,000,000 S/s,
force capture/AXI factor 1, and read back both PHY and capture-device rates plus
the PL bypass bit before admitting samples. Gate 4 removes the unused FIR and
its `adi,axi-decimation-core-available` device-tree property together, then
re-proves that 30/60 rate writes reach the converter rather than a stale PL
rate shim.

## Current implementation evidence

The first continuous-acquisition RTL slice is now source-locked at HDL commit
`d291871923c6dc6cc2f30745d2e9d8a6abd3188f`, tagged
`starlink-rx-only-dnm-v1-source/hdl-pss15-phase-map-v3`. It implements the
oracle-selected 20,000-bin, 64-frame, one-sample-resolution phase map as two
segmented simple-dual-port BRAM banks. Deterministic simulation covers
back-to-back tiles without a dropped boundary score, a simultaneous immutable
map read while the other bank fills, exact published sums and metadata, gap
invalidation and clearing, fail-closed lifecycle requests, and a disable on the
drain/publish cycle. Vivado 2022.2 post-opt OOC at 100 MHz uses 542 LUTs, 722
registers, exactly 20 RAMB36E1s, and zero DSPs, with setup WNS `+1.190 ns`, hold
WHS `+0.204 ns`, zero methodology violations, and no nonempty
`check_timing` category. This block still consumes already-normalized scores:
there is no FFT/scorer, AXI/CDC wrapper, shell integration, image, or radio
claim. The RX DMA path is unchanged. Immutable v1 and v2 tags are retained but
superseded after review found, respectively, a shared two-bank read-address mux
and clean-bank reservation leaks across disable; neither was advanced into this
parent graph, built into an image, or used on a radio.

The next offline arithmetic checkpoint is now complete as
`starlink-xfft-bitacc-acquisition-v1`. The selected one-template front end uses
two dedicated 512-point radix-4 burst XFFT v9.1 cores with 24-bit data, 16-bit
phase factors, block-floating scaling, convergent rounding, natural-order
output, and a one-bit Q1.23 spectrum-product safety shift. Across 12,582,717
frozen real score positions, 2,881 differ from the exact integer oracle
(0.02290%), every difference is at most one eight-bit count, and all three
phase/cadence/classification decisions are exactly unchanged. All structural
overlap-boundary PSS injections score 255 and no modeled arithmetic block
overflows. This is a deliberately bounded finite-width acquisition contract,
not a claim that FFT correlations are bit-identical to direct dot products;
the sparse direct tracker remains the exact confirmation stage.

Vivado 2022.2 selects radix-4 burst at the required 20 MS/s target. One 24-bit
core uses 2,189 LUTs, 3,847 registers, 11 RAMB18E1s (5.5 BRAM tiles), and nine
DSPs with post-synthesis setup/hold slack of `+6.411/+0.203 ns` at 100 MHz. Two
cores plus the measured one-template phase map total 4,920 LUTs, 8,416
registers, 31 BRAM tiles, and 18 DSPs before the multiplier, energy window,
FIFOs, normalizer, and shell. The first image therefore enables exactly one
RF-plan-selected lower/upper edge template at a time. Concurrent two-edge
search would duplicate the inverse path and 20-RAMB36 map and is deferred
unless a complete-shell resource study justifies it. Detailed evidence is in
`reports/STARLINK_PSS15_XFFT_BITACC_V1.md`; no Xilinx proprietary C-model file
or generated IP is retained in source.

The IP-independent overlap-save scheduler is now implemented and source-locked
at HDL commit `2c9e564350e1c42d9aa5b14e7ee61929a754f1fd`, tagged
`starlink-rx-only-dnm-v1-source/hdl-pss15-overlap-scheduler-v1`. It accepts the
non-backpressured, gap-tagged CI16 stream with 64-bit absolute indexes, retains
2,048 samples in a two-RAMB36 ring, and emits exact 512-sample ready/valid FFT
frames with 65 samples of overlap and a 447-sample stride. Two deterministic
testbenches cover default-geometry 15-MS/s-equivalent cadence and backpressure,
plus disable, gap, index, descriptor-capacity, and ring-retention restarts. All
fail closed without publishing a partial frame. Vivado 2022.2 post-opt OOC at
100 MHz uses 273 LUTs, 695 registers, exactly two RAMB36E1s, and zero DSPs, with
setup WNS `+2.012 ns`, hold WHS `+0.011 ns`, zero methodology violations, and
no nonempty `check_timing` category. Adding this slice to the isolated two-core
XFFT and phase-map subtotal yields 5,193 LUTs, 9,111 registers, 33 BRAM tiles,
and 18 DSPs before the multiplier, energy window, result FIFO, normalizer, and
shell. This remains slice evidence: no XFFT is yet instantiated in the RTL, no
score reaches the map, and no radio was contacted. Detailed evidence is in
`reports/STARLINK_PSS15_OVERLAP_SCHEDULER_V1.md`.

The exact Q1.23 spectrum-product stage is now implemented and source-locked at
HDL commit `5b2cdd3ba81e98ab3f752f334a34054d0b48f237`, tagged
`starlink-rx-only-dnm-v1-source/hdl-pss15-spectrum-product-v1`. Its three-stage
elastic pipeline calculates the four signed 24-by-24 products, applies the
frozen one-bit safety shift, rounds signed results to nearest with ties to even,
saturates to Q1.23, and carries bin, block-exponent, last, and absolute-start
metadata through stalls. A Python-generated 4,112-vector replay covers signed
half-way ties, extremes, saturation, sustained backpressure, exact metadata,
and fail-closed flush; every result is bit-exact. Vivado 2022.2 post-opt OOC at
100 MHz uses 220 LUTs, 456 registers, exactly eight DSP48E1s, and no BRAM, with
setup WNS `+2.362 ns`, hold WHS `+0.284 ns`, zero methodology violations, and
no nonempty `check_timing` category. The isolated planning subtotal is now
5,413 LUTs, 9,567 registers, 33 BRAM tiles, and 26 DSPs. FFT RTL binding, the
kernel ROM, block-exponent restoration, energy window, result FIFO,
normalizer, phase-map connection, and complete route remain pending. Detailed
evidence is in `reports/STARLINK_PSS15_SPECTRUM_PRODUCT_V1.md`; no radio was
contacted.

The exact 66-sample CI16 energy path is now implemented and source-locked at
HDL commit `8282a4a7b2aef1ff05f40f2342cca71e20521fd5`, tagged
`starlink-rx-only-dnm-v1-source/hdl-pss15-energy-cache-v1`. It calculates the
unsigned 38-bit sliding sum of `I^2 + Q^2`, retains 2,048 results by absolute
candidate-start index, and exposes a ready/valid lookup for the later IFFT
join. Full oldest/newest metadata rejects stale circular aliases; same-cycle
newest writes bypass exactly, while an oldest-entry overwrite collision fails
closed. A 2,500-sample, 15-MS/s-equivalent simulation compares all 2,435
initial windows exactly and also covers rollover boundaries, lookup stalls,
gap/index restarts, disable, two concurrent read/write cases, and 2,443 total
energy writes. Vivado 2022.2 post-opt OOC at 100 MHz uses 469 LUTs, 534
registers, two RAMB36E1 plus one RAMB18E1 (2.5 tiles), and two DSP48E1s, with
setup WNS `+1.960 ns`, hold WHS `+0.056 ns`, zero methodology violations, and
no nonempty `check_timing` category. The isolated planning subtotal is now
5,882 LUTs, 10,101 registers, 35.5 BRAM tiles, and 28 DSPs. The correlation
join, result FIFO, normalizer, FFT binding/controller, phase-map connection,
and complete route remain pending. Detailed evidence is in
`reports/STARLINK_PSS15_ENERGY_CACHE_V1.md`; no radio was contacted.

The exact eight-bit rational divider lane is now implemented and source-locked
at HDL commit `8755d94eefb65cba6155a28c8a4c9c3f2ec69e41`, tagged
`starlink-rx-only-dnm-v1-source/hdl-pss15-score-divider-v1`. It accepts a
69-bit normalized-power numerator and denominator, performs eight restoring
iterations, and computes `round_ties_even(255*numerator/denominator)` exactly.
Zero-denominator, zero-numerator, and unity-or-greater cases retain the same
fixed calculation latency; output stalls and flushes are fail closed. A
Python-generated 4,112-vector replay covers both directions of half-way ties,
full-width random ratios, zero, saturation, metadata order, backpressure, and
flush. Vivado 2022.2 post-opt OOC at 100 MHz uses 599 LUTs, 378 registers, no
BRAM, and no DSP48E1s, with setup WNS `+0.962 ns`, hold WHS `+0.284 ns`, zero
methodology violations, and no nonempty `check_timing` category. Two lanes
therefore add 1,198 LUTs and 756 registers and have an aggregate initiation
capacity of 22.22 million scores/s. The isolated two-lane planning subtotal is
7,080 LUTs, 10,857 registers, 35.5 BRAM tiles, and 28 DSPs. The correlation
power/exponent preprocessor, denominator product, raw-result FIFO, two-lane
dispatcher/ordered merge, FFT binding/controller, phase-map connection, and
complete route remain pending. Detailed evidence is in
`reports/STARLINK_PSS15_SCORE_DIVIDER_V1.md`; no radio was contacted.

The exponent-aware score-ratio preparation pipeline is now implemented and
source-locked at HDL commit
`078e725389c8c790e1f3c3c612b242697f87de77`, tagged
`starlink-rx-only-dnm-v1-source/hdl-pss15-score-prepare-v1`. Three elastic
stages square signed Q1.23 IFFT components, form exact correlation power,
restore it by `2^(2*(1 + Ef + Ei))`, and multiply the unsigned 38-bit window
energy by the selected upper-edge template's 31-bit coefficient energy
`1073742825`. The lower-edge value is `1073776498`; although the RTL parameter
can represent it, lower-edge integration remains unauthorized until a separate
parameter-override replay and OOC gate pass. A numerator that
mathematically exceeds 69 bits becomes all ones, which is exactly equivalent
to `numerator >= denominator` because the denominator always fits 69 bits; no
wrap is permitted. A Python-generated 4,112-vector replay covers signed
extrema, actual `0..2` and full `0..31` block exponents, zero/full energy,
2,862 deliberate numerator saturations, exact metadata, sustained stalls, and
flush. Vivado 2022.2 post-opt OOC at 100 MHz uses 561 LUTs, 581 registers,
exactly four DSP48E1s, and no BRAM, with setup WNS `+0.396 ns`, hold WHS
`+0.269 ns`, zero methodology violations, and no nonempty `check_timing`
category. The isolated planning subtotal is now 7,641 LUTs, 11,438 registers,
35.5 BRAM tiles, and 32 DSPs. The positive but narrow unplaced setup margin is
an explicit complete-route risk. The raw-result FIFO, indexed-energy join,
two-lane dispatcher/ordered merge, FFT binding/controller, phase-map
connection, and complete route remain pending. Detailed evidence is in
`reports/STARLINK_PSS15_SCORE_PREPARE_V1.md`; no radio was contacted.

The raw IFFT-result FIFO is now implemented and source-locked at HDL commit
`7cba0eac1cd83e29846b812caca0f0dfee2523d4`, tagged
`starlink-rx-only-dnm-v1-source/hdl-pss15-raw-result-fifo-v1`. Its 512-entry,
123-bit storage retains signed Q1.23 correlation, both block exponents,
absolute candidate-start index, and block-last identity. The capacity includes
the registered prefetch stage; memory contents are never bulk reset. A
self-checking simulation accepts a complete 447-result inverse-FFT burst at
one result/clock while its consumer is fully stalled, drains every payload bit
in order under backpressure, checks 1,200 concurrent transfers, fills exactly
512 entries, rejects the 513th without state mutation, and proves flush. Vivado
2022.2 post-opt OOC at 100 MHz uses 79 LUTs, 42 registers, exactly two RAMB36E1
tiles, no RAMB18E1, and no DSP48E1, with setup WNS `+3.342 ns`, hold WHS
`+0.011 ns`, zero methodology violations, and no nonempty `check_timing`
category. The isolated planning subtotal is now 7,720 LUTs, 11,480 registers,
37.5 BRAM tiles, and 32 DSPs. The positive but narrow OOC hold result remains
an explicit complete-route risk. IFFT result qualification, the indexed-energy
join, two-lane dispatcher/ordered merge, FFT binding/controller, phase-map
connection, and complete route remain pending. Detailed evidence is in
`reports/STARLINK_PSS15_RAW_RESULT_FIFO_V1.md`; no radio was contacted.

The complete IFFT-candidate-to-score tail is now composed and source-locked at
HDL commit `e12355ec0572c0637932fed0b3846c6a0b52a99c`, tagged
`starlink-rx-only-dnm-v1-source/hdl-pss15-candidate-score-path-v1`. A strict
qualifier checks all 512 IFFT indexes, TLAST, exponents, block identity, and the
447-sample next-block stride, discarding only indexes 0 through 64. The raw
FIFO then joins each of the 447 absolute candidate starts to the exact energy
cache response; miss, identity mismatch, orphan response, framing fault, and
FIFO overflow all latch a quarantine and can never become a zero score. Two
fixed-latency divider lanes preserve input order under output stalls. Five new
tests cover two complete IFFT blocks, 1,000 one-per-clock energy joins, 1,500
ordered two-lane ratios, 4,112 independent arbitrary-precision raw-to-score
vectors, and a real-energy-cache one-block integration. The integrated block
accepts all 512 dense IFFT outputs without backpressure, produces 447 exact
scores, peaks at 344 of 512 FIFO entries, and publishes no score after a forced
cache miss. Vivado 2022.2 post-opt OOC at 100 MHz for the composed tail uses
1,968 LUTs, 1,827 registers, exactly two RAMB36E1 tiles, no RAMB18E1, and four
DSP48E1s, with setup WNS `+0.633 ns`, hold WHS `+0.265 ns`, zero methodology
violations, and no nonempty `check_timing` category. Replacing the prior
independent FIFO/preparation/two-divider sum with this composed result gives an
isolated planning subtotal of 7,850 LUTs, 11,928 registers, 37.5 BRAM tiles,
and 32 DSPs. The generated XFFT wrapper/controller, coefficient ROM, complete
CI16 IQ-to-score replay, phase-map connection, full RX-only route, and hardware
qualification remain pending. Detailed evidence is in
`reports/STARLINK_PSS15_CANDIDATE_SCORE_PATH_V1.md`; no radio was contacted.

The strict generated-XFFT protocol boundary is now implemented and
source-locked at HDL commit `b8657819e56c9a2b836319e9b9b8596fc4ce3204`, tagged
`starlink-rx-only-dnm-v1-source/hdl-pss15-xfft-block-adapter-v1`. One adapter
stretches generated-core reset, sends a fixed forward or inverse configuration
before data, permits one 512-sample block in flight, and binds its absolute
start identity to natural-order TUSER indexes, TLAST, and the independently
reported block exponent. Missing status stalls publication; malformed input,
output, status, or hard XFFT events latch quarantine until explicit common
flush. A mock-core simulation covers 512 exact inputs and outputs through
independent stalls, both direction words, status-before-output, five fault
classes, nonfatal halt telemetry, and flush recovery. The first over-coupled
fault gate correctly failed timing at `-1.018 ns`; the final one-block-aware
architecture passes Vivado 2022.2 post-opt OOC at 100 MHz using 103 LUTs, 111
registers, no BRAM/DSP, setup WNS `+2.328 ns`, hold WHS `+0.269 ns`, zero
methodology violations, and no nonempty `check_timing` category. Two adapters
raise the isolated planning subtotal to 8,056 LUTs, 12,150 registers, 37.5 BRAM
tiles, and 32 DSPs. No generated core is instantiated yet. Detailed evidence
is in `reports/STARLINK_PSS15_XFFT_BLOCK_ADAPTER_V1.md`; no radio was contacted.
Its superseding manifest also corrects the prior candidate-score manifest's
provenance-only `hdl-quantulum` field from the accidentally recorded HDL tag
object `70142c3d...` to the unchanged gitlink
`364b3dc7e770c3971d1f41a75c00e6cae76e2e6d`; the immutable older tag is not
rewritten.

The selected upper-edge PSS frequency-domain kernel is now packaged and
source-locked at HDL commit `a7985ea3ab5b5b867caf8a34f72601c816874041`,
tagged `starlink-rx-only-dnm-v1-source/hdl-pss15-kernel-rom-v1`. The 512
complex signed-Q1.23 bins are packed as `{Q,I}` in one synchronous ROM image.
An independent standard-library verifier freezes both the canonical
little-endian signed-I/Q byte stream at SHA-256
`d96c56b3d6bcd03419a57f23f3ce4929f1e478663119f5cb5ec9b14327b7ff2b`
and the exact memory-file text at SHA-256
`7c89ff2a026f5fab91e655ab969ac07c11bf9715215173dadec07084527aea7d`.
The streaming boundary checks all 512 bin indexes, TLAST, exponent stability,
absolute block identity, and the 447-sample next-block stride before emitting
a coefficient; malformed input latches a fail-closed quarantine until common
flush. Simulation replays all coefficients across three complete blocks,
proves a 512-cycle continuous acceptance run and output stability under stalls,
and injects five separately recovered sequence/metadata faults. The first
split I/Q read form correctly failed the resource gate by duplicating the ROM
in LUT fabric; the final single 48-bit read passes Vivado 2022.2 post-opt OOC
at 100 MHz using 88 LUTs, 229 registers, exactly two initialized RAMB18E1s
(one BRAM tile), and no DSPs, with setup WNS `+3.634 ns`, hold WHS `+0.056 ns`,
zero methodology violations, and no nonempty `check_timing` category. The
isolated planning subtotal is now 8,144 LUTs, 12,379 registers, 38.5 BRAM
tiles, and 32 DSPs. The ROM is a coefficient/metadata sidecar and deliberately
does not carry forward-XFFT I/Q; the composition gate must register the
accepted complex bin beside its lookup and join the pair fail closed.
Generated-XFFT instantiation, CI16-to-Q1.23 conversion, complete 447-score
replay, phase-map connection, full route, and hardware qualification remain
pending. No radio was contacted.

The existing wide-arithmetic repeated-delay diagnostic core has these Vivado
2022.2 post-synthesis out-of-context results at a common 16.666 ns constraint.
They prove neither exact-PSS sensitivity nor full-design routing closure:

| Rate geometry | LUT | FF | LUTRAM | DSP48E1 | Synth WNS |
|---:|---:|---:|---:|---:|---:|
| 15 | 1,597 | 907 | 434 | 21 | +3.523 ns |
| 30 | 1,878 | 921 | 564 | 21 | +3.523 ns |
| 60 | 2,001 | 915 | 694 | 21 | +3.523 ns |

These figures are retained as diagnostic-baseline evidence. The new exact
correlator and any selected x2/x4 detection lane require separate OOC and
full-shell reports. No resource or timing estimate is substituted for a
generated report.

The integrated 15 MS/s diagnostic-monitor shell was rebuilt locally with
Vivado 2022.2 after the geometry, independent-arithmetic fixture, and scoped
bus-skew checks were fixed. It used 6,417/17,600 LUTs (36.46%), 9,187/35,200
registers (26.10%), 1,012/6,000 LUT-memory cells (16.87%), 3/60 BRAM tiles, and
49/80 DSPs. Setup WNS was +1.277 ns, hold WHS was +0.016 ns, and all 15,945
nets routed. The monitor mailbox had +8.019 ns max-delay slack and +8.238 ns
bus-skew slack, with exactly 293 CDC-15 payload rows, two CDC-3 toggle rows,
and no new critical crossing. The routed-checkpoint SHA-256 was
`c81e64767b02ca1a535f487a6dc7c64df7f497d975623c064f94f479ac069f9e`.
This is implementation evidence for diagnostic plumbing, not PSS-detection or
radio qualification.

Trusted Kalman run `33548132920` independently rebuilt and packaged that
monitor shell from clean parent `7d51160fc8526a3b2f00bf4642d9d6b9edbab2e2`,
HDL `0c0d01957e42abeab64db65d0e4b9ac399463e31`, and manifest
`starlink-rx-only-dnm-v1-source.yaml` with HDL tag
`starlink-rx-only-dnm-v1-source/hdl-v3`. It reproduced WNS `+1.277 ns`, WHS
`+0.016 ns`, 6,417 LUTs, 9,187 registers, 3 BRAM tiles, and 49 DSPs. Its clean
artifact `plutoplus-starlink-rx-only-dnm-v1-7d51160fc852.tar.gz` has SHA-256
`4f9020a14a365b94da50d491e441b3ce4d5d9b60261c7ffe9123606a940b4982`;
both internal SHA-256 manifests were independently replayed. The trusted routed
DCP and bitstream hashes are respectively
`3ed5ce509c84f4f70e31b0b704ecf216c95769c08c99af25cd1cb516b72b877e` and
`91c6cad33261da706daba878ff1d5e9275926e75b038b1514cf0eec88e83ab57`.
This remains `PASS OFFLINE / HARDWARE UNTESTED` and is not a detector image.

The isolated Stage-15 raw exact engine now passes six Icarus jobs, 390 bit-exact
tuples, and two mid-job reset aborts: an adversarial protocol/timestamp job,
zero/reused-bank, full-scale endpoints, an all-lag tie, and all 65 lags from the
provenance-bound real capture. The frozen real fixture is
reproduced by both a pure-standard-library integer model and the independent
NumPy waveform oracle. Vivado 2022.2 OOC synthesis for `xc7z010clg400-1` uses
838 LUTs (220 LUT-memory), 650 registers, one RAMB36, and exactly three DSP48E1s
at 100 MHz with setup WNS `+1.778 ns`, zero methodology violations, and no
unconstrained timing category. This is `RAW ARITHMETIC PASS OFFLINE`; it has no
AXI/CDC wrapper, candidate queue, reducer, DMA connection, full route, or radio
claim yet.

That result uses a deliberate two-commit evidence boundary. Reviewed source is
commit `8290233f93177c231a57436710902bbd058d7f82`; the post-source qualification
evidence is commit `d53ac844e1206fa37fb858c30c1301a831c11843`, locked by annotated
tag `starlink-rx-only-dnm-v1-source/hdl-pss15-raw-v1`. The OOC manifest SHA-256
is `f6c3749e220b8d2d1f289dc7c9c82742f9e835cc83f99499551aa1bbd56eae18`,
the real-fixture qualification receipt SHA-256 is
`951b898e5a06b2c413baa6aa6a2e85c1c9d56f43280eeaf274399dc4e6170a5c`,
and the retained synthesized DCP SHA-256 recorded by that manifest is
`48913bd75422491cca98398bec5b23430a998aa432169a18775de45b31c03110`.
Every manifest source, report, DCP, transcript, and fixture digest was replayed
after the source commit. Parent manifest
`starlink-pss15-raw-dnm-v1-source.yaml` pins this exact graph and explicitly
forbids building, booting, releasing, or flashing the still-isolated core.

The superseded Stage-15 `TRACK_ONE` ABI 1.0 milestone was HDL commit
`d30e7b3c1128448b8cfa5a9dbfeec49154a136a5` on
`codex/starlink-rx-only-do-not-merge`, locked by annotated tag
`starlink-rx-only-dnm-v1-source/hdl-pss15-track-one-v1`. It adds the
host-scheduled AXI wrapper,
queued capture, cached `Eh`, sliding `Ex`, exact rational winner reducer, and
atomic 26-word result publication; removes the diagnostic monitor and TX DMA;
and remains elaboration-locked to 15 MS/s. The asynchronous-clock AXI test
loads 66 coefficients, captures 130 tagged samples, evaluates all 65 raw lags,
checks every result word, releases the level IRQ, and proves that sample reset
flushes the whole epoch. The complete underlying scheduler/capture/correlator/
reducer/result-store suite also passes.

The clean Vivado 2022.2 Pluto route at that HDL commit has setup WNS
`+0.519 ns`, hold WHS `+0.014 ns`, zero timing failures, zero routing errors,
and zero tracker Critical CDC rows. Its 64-bit Gray scheduling-index crossing
meets the 10 ns bus-skew constraint with 1.590 ns actual skew. The complete
RX-only shell uses 8,906/17,600 LUTs (50.60%), 11,531/35,200 registers
(32.76%), 8.5/60 BRAM tiles (14.17%), and 31/80 DSPs (38.75%); the tracker
hierarchy accounts for exactly 3 DSP48E1s, 3 RAMB18E1s, and 4 RAMB36E1s. The
routed DCP, bitstream, and XSA SHA-256 values are respectively
`64785b8b5a4e9e5af1ead62d659f4078076aab98c42fc639fb95b2fe4548160a`,
`0e783199a0a56c7742d6079daeb4ebc6ac4750e58f543d4020529275a39b3e49`,
and `44dd4c0525fa67630dbb0f225999d0498a62baf27991fca497d6cfba96ff565d`.
Those route results are retained as historical evidence only. They no longer
close wrapper/integration/route work because ABI 1.0 incorrectly permitted the
outer `[-32,-31,+31,+32]` guard lags to win. Nothing derived from that route is
eligible for a radio boot.

The corresponding ABI 1.0 full firmware container was built and verified
offline from parent source commit
`5cc58ccde59b642aa504399ac148fc999f8cf3e4`, with that graph locked by annotated
tag `starlink-rx-only-dnm-v1-source/firmware-pss15-track-one-v1`. The DFU, FRM,
and FIT SHA-256 values are respectively
`27a1b3381bce882ac961614277091619946a5a3e395c4db0dc8c3c2577a999b5`,
`242df10166f856e4cd68c90d144b9dcaba3cc1e100aa3a6bcf6b1ffe3caa1fbc`,
and `c803d5305c0417b1659212866b171e150e8efe107e724bc581bde762d7e9f976`.
The packaged FPGA payload is byte-identical to the routed bitstream above, and
the packaged XSA is byte-identical to the routed XSA. Rootfs `/opt/VERSIONS`
records the exact firmware, HDL, Buildroot, Linux, and U-Boot identities. The
14-check container verifier passes the image digest, DFU suffix, FIT metadata,
payload digests, embedded identities, tag-to-pin relationships, and gadget
build ID. The offline manifest and checksum list are
`starlink-pss15-track-one-dnm-v1-offline.yaml` and
`starlink-pss15-track-one-dnm-v1-offline-SHA256SUMS`; their own SHA-256 values
are `445b1413b1d91ec6b40bd058bf74a3df1d917dc9a2b6a4142c23cade684714f3`
and `973d999911e23b05b552711bae1dce8e5768a74acc71333e9f57f7a5def5c5f4`.

This is only a reproducible historical container boundary, not a release or
hardware qualification. It is explicitly **superseded, obsolete, and forbidden
for radio use**. No radio, USB/serial interface, network route, or DFU transfer
was used. GCC 15's C23 default required rebuilding the generated host-m4 stage
with `-std=gnu17`; the target build then resumed with its normal flags so the
ARM GCC 7.3 stages retained their supported language mode. No source change was
needed for that host-tool compatibility workaround.

A frozen CI16/Q1.15 one-bank tracking model has been replayed over all 210
first-chunk real windows using the oracle's actual upper-edge, `-100 kHz`,
local-radius-30 semantics. The corrected bit-exact `[-30,+30]` reducer selected
the identical integer lag in 210/210 windows. The superseded `[-32,+32]`
reducer matched only 207/210: windows 141, 195, and 201 were incorrectly won by
outer guard lags. Fixed-versus-float normalized-score absolute error was at most
`1.52e-5`, with median `3.49e-6`. In contrast, allowing each frame to maximize
all nine CFO banks across the proposed 65-lag `[-32,+32]` aperture retained the
block-selected `-100 kHz` bank in only 97/210 windows. These results freeze the
acquisition-versus-tracking split and form a predeclared Stage-15 equivalence
target.

The current ABI 1.1 correction drains all four outer raw tuples,
advertises geometry `{lags=61,capture=130,taps=66}`, and adds atomic telemetry.
The full AXI wrapper now replays the 27,300 retained CI16 samples and all 5,460
expected packet words with 210/210 frozen float-lag agreement and zero errors.
The native mock host controller additionally proves exact ABI/serial refusal,
coefficient I/Q conversion, atomic counter gates, packet validation, and
failure-with-result-retained behavior; a static ARM EABI build passes. The HDL
source is now commit `6a73ee090ff17b48cad2e089daa4d7a1013c993f`, annotated
by the explicitly do-not-merge tag
`starlink-rx-only-dnm-v1-source/hdl-pss15-track-one-v2`. Its fresh route passes
with setup WNS `+0.314 ns`, hold WHS `+0.024 ns`, Gray-index and telemetry
payload skew `1.235 ns` and `1.880 ns`, zero tracker Critical CDC rows, zero
routing errors, and no TX DMA hierarchy. The shell uses 9,176 LUTs, 13,820
registers, 8.5 BRAM tiles, and 31 DSPs. The DCP/bitstream/XSA SHA-256 values are
`3283a9b0855241415cd2b3d3a7ea2cd36363f7d8597291687feb49ba0ca7220b`,
`a1c3e01a78cc71f2984290f98677e9b44acb3f7e2bdf4a86405916a537fb83fe`, and
`eee9d8fd5ade10dfcee674a2dba1acfb413662ff915c9b21b33519a28a2b3a9c`.
Firmware packaging, device-tree/runtime checks, and every radio gate remain
pending.

The trusted full-shell run `33540748707` at parent commit `829380e76240` and
HDL source `091f8d5852fa` also completed implementation and produced a fully
routed RX-only checkpoint. It used 4,429/17,600 LUTs (25.16%), 7,173/35,200
registers (20.38%), 3/60 BRAM tiles (5%), and 28/80 DSPs (35%). Routed setup
WNS was +2.049 ns and hold WHS was +0.006 ns, with zero setup and hold failing
endpoints. Both remaining RX timestamp-FIFO bus-skew constraints were met at
+8.997 ns and +9.413 ns. Packaging then stopped because its inherited policy
expected four RX-plus-TX FIFO constraints; the RX-only shell intentionally has
only the two RX crossings.

Replacement trusted run `33542849550` at parent commit `c9c0c72c1b52` passed
the complete build and packaging workflow with the same routed checkpoint and
source graph. Its outer archive and both internal SHA-256 manifests have been
independently verified. It remains explicitly hardware-untested and is a
comparison baseline, not the detector image to boot. The first radio-eligible
candidate must be rebuilt from a later source-locked exact-engine integration
commit with the diagnostic monitor compiled out, then consumed by the merged
PPU v2 RAM-qualification path.

## RX-only shell and common qualification gates

The experimental shell compiles `MODE_1R1T=1`, disables the AD936x FPGA DAC
datapath and TDD logic, removes TX DMA/packer/interpolation, removes tandem AGC,
removes the second PS high-performance port, and holds the digital TX pins
static. Linux disables the absent TX DMA/DDS/TDD/tandem devices, selects 1R1T,
and skips TX digital-interface tuning.

Every rate must pass all of these common gates:

- source closure: immutable parent/submodule commits, tool versions, waveform
  and template digests, generated-image hashes, and reproducible commands;
- functional closure: for the acquisition FFT, the separately frozen
  finite-width score-error bound plus exact phase/cadence/classification
  agreement; for the sparse confirmation tracker, bit-exact oracle agreement;
  both paths cover index and timestamp mapping, ties, overflow, saturation,
  zero energy, valid gaps, enable changes, index jumps, wrong cadence, and
  negative recordings;
- policy closure: before held-out evaluation, freeze a versioned
  `qualification-policy` containing positive/negative partition IDs and digests,
  raw-index/timestamp tolerance, minimum frames, allowed misses, confirmation
  count, exact score/z thresholds, a stated false-alarm denominator and ceiling,
  tie rules, live observation duration, and every pass/fail limit. Each report
  embeds that policy digest;
- implementation closure: actual RX-only Zynq-7010 full implementation with
  setup and hold WNS >= 0, TNS = 0, THS = 0, no critical DRC, no unconstrained
  detector clocks, and no missed accepted sample in the detection lane. CDC
  acceptance is exactly the source-locked reviewed inherited set: currently one
  overflow-snapshot CDC-1 and one timestamp-snapshot CDC-4 critical row. The
  monitor's 293 CDC-15 warnings and two CDC-3 info rows add no critical row; any
  new or unreviewed critical crossing fails;
- headroom: publish post-route LUT, FF, LUTRAM, BRAM, and DSP use. The initial
  acceptance budget leaves at least 15% of each resource class unused; any
  exception is reviewed before a radio boot and is never hidden by changing a
  threshold, clock, or test vector;
- RX correctness: declare the injection boundary. Under byte-identical,
  deterministic replay/injection, full-rate DMA hashes match a detector-disabled
  control. A hardware-complete claim requires a source-locked RX-path test mux
  or external RF generator driving the accepted-sample path while onboard TX
  remains absent. Sequential live-RF captures are never required to hash equal;
  compare sample counts, achieved clock, timestamp continuity, gap/overflow
  counters, configuration, and oracle-matched events instead. Any selected
  filter lane maps phase and delay exactly to the full-rate index;
- RX-only attestation: only RX voltage channels 0 and 1 are scan-capable, no
  TX DMA/DDS IIO device is live, every exactly inventoried TX hardware-gain
  control is <= -80 dB, the one shared AD936x TX-LO control is powered down,
  and removed-device DT markers match the image. The receipt must not invent a
  second LO or a second 1R1T gain control that the IIO ABI does not expose;
- identity and recovery: exact serial/topology and serial-scoped locks; exact
  USB interface/source and `/32` route; private password file under PPU's
  USB-bound SSH policy; pre/post RAM observations; a new candidate boot ID;
  unchanged `qspi-linux`; and bounded route cleanup. A separate mandatory
  persistent-recovery receipt proves pre-reset USB departure, another new boot
  ID, verified TX quiesce, released route, and restoration of the same persistent
  1R1T baseline;
- recovery eligibility: only a route-released PASS or route-released,
  transition-started UNKNOWN v2 RAM receipt is a recovery source. FAILED,
  unstarted UNKNOWN, or route-not-released UNKNOWN stops the sequence for
  explicit reconciliation and is never passed to `candidate-ram recover`; and
- claims: every report records separate `execution_path`, `stimulus_source`,
  and `claim_scope` fields. Execution distinguishes offline model, RTL
  simulation, routed FPGA, and exact target radio. Stimulus distinguishes
  synthetic vector, recorded-IQ replay, internal accepted-sample test mux,
  external RF generator, unrelated/negative ambient RF, and ambient Starlink.
  Scope distinguishes arithmetic equivalence, accepted-sample-path hardware,
  radio transport, generated-RF detection, and ambient-live detection. Each
  rate records separate `IMPLEMENTATION/RADIO-TRANSPORT PASS`,
  `HARDWARE-INJECTION PASS`, and `LIVE-SIGNAL PASS` states. Passing capture
  plumbing or synthetic hardware injection never becomes a live-signal claim;
  the gate itself states which state permits advancement.

Recovery is an always-run safety epilogue on success, failure, abort, tool
crash, or operator interruption, not merely the last successful campaign gate.
The emergency implementation is pinned to known-good merged PPU commit
`c70d46bb420de05112f2e60052025606321fc8f0`, which preserves the recovery
fixtures and has now exercised exact RX-only rate proof plus final canonical
setup on the selected hardware. The epilogue closes buffers, stops detector
work, performs bounded route cleanup, reconciles receipts, uses
`candidate-ram recover` only for an eligible v2 receipt, and restores/verifies
persistent `ad9361-2r2t`. If persistent setup failed before a RAM receipt exists,
it uses the setup receipt's reconcile/rollback path instead. An indeterminate
identity, route, or transition state forbids blind mutation: retain the locks,
collect evidence, reconcile explicitly, then complete 2R2T restoration. The
campaign remains failed and visibly incomplete until that terminal state is
proved.

## Sequential, testable stage gates

Current status ledger:

- Gate 0: **COMPLETE / HARDWARE-EXERCISED** on the selected unit through PPU
  `c70d46b`, including native-AD9363A setup, exact RX-only rate proof, recovery,
  and final canonical 2R2T setup;
- Gate 2A diagnostic monitor: **COMPLETE OFFLINE** at the source-bound trusted
  run above; it is status plumbing, not PSS;
- Gate 2B one-bank Stage-15 `TRACK_ONE`: the HDL `d30e7b3c` / firmware
  `5cc58cc` ABI 1.0 route and package are **SUPERSEDED / RADIO-FORBIDDEN**.
  ABI 1.1 has 210/210 corrected wrapper replay, a tested static-ARM host API,
  source lock, a passing fresh route and package, exact RX-only runtime layout,
  and one passing hardware tracker transaction. The advanced CFO/trace modes
  remain pending. ABI 1.2 deterministic injection has passing standalone and
  210-window real replay, a tested static-ARM host API, a passing full route, a
  source-locked RAM-only package, exact positive and independent-window packet
  invariants on the target radio, one byte-exact shared RX-DMA observation, and
  eight passing sequential repeat transactions;
- Gate 1 acquisition oracle: **FIRST REAL-DATA ARCHITECTURE CHECKPOINT
  COMPLETE; PRODUCTION CORPUS POLICY OPEN**. The remaining Gate 2
  modes/equivalence bundle is in progress or pending;
- Gate 3: **IMPLEMENTATION/RADIO-TRANSPORT PASS WITH MANDATORY RT POLICY; LIVE
  PSS OPEN** for native
  `ad9363a-1r1t`; its RAM lifecycle, exact 15 MS/s PHY/capture path, factor-1
  FPGA path, deterministic injection, independent-window negative control,
  byte-exact shared RX-DMA observation, RF/filter/timestamp-slope, seven-entry
  prequeue, and 45,000-result 750-Hz continuity with four concurrent DMA
  segments passed. Queue continuity requires radio-local result spooling and
  `SCHED_FIFO` priority 80; ordinary scheduling failed. Live multi-frame PSS
  evidence remains pending;
- Gate 6 epilogue for all Stage-15 trials: **COMPLETE** with verified persistent
  2R2T restoration and unchanged QSPI;
- every 30 MS/s, 60 MS/s, full campaign-close, and SSS gate: pending.

### Gate 0: PPU foundation on `main` - COMPLETE / HARDWARE-EXERCISED

- PPU `origin/main` commit `8074b228083240860843b0fb4dd4d5b46f06805b`
  (PR #109) contains target-aware setup, including merge `d70bf14`, and RX-only
  v2 commit `b668d8a`. All eight GitHub CI checks passed.
- The parallel v2 lifecycle leaves legacy v1/2R2T behavior unchanged and tests
  schema dispatch, exact target readback, missing TX-device expectations,
  safe-state proof, identity locking, explicit recovery eligibility, USB
  departure, and persistent rollback.
- Every trial records the actual clean merged PPU commit. No target-radio RAM
  boot begins without a canonical absent-only private operation/RAM-receipt
  destination and its recorded SHA-256 path.

Original pass artifact: PPU `main` `8074b22`, green CI, 1,311 local tests with
11 hardware or browser skips, target-profile tests, and offline
receipt/recovery fixtures. The hardware checkpoint then exercised the generic
path through exact-route leasing, sysfs-pinned IIO re-enumeration, host-key
rotation, v2 RAM receipts/recovery, and verified 1R1T-to-2R2T restoration at
`fee8444`. Post-trial `f22f3c9` raises only the synchronous setup-execution CLI
window to 180 seconds and passes 1,320 tests with 11 skips, Ruff, mypy, and both
package builds. PPU `10ae7c7` adds source-locked generic rate attestation, and
`c70d46b` adds the direct-libiio RX-only path that does not invent a missing TX
device; the latter passes 1,328 tests with 11 skips plus Ruff, mypy, and package
builds. Starlink code is not part of any PPU commit.

### Gate 1: frozen oracle and 15 MS/s offline acquisition

- Complete for the first architecture checkpoint: exact-integer accelerated
  overlap-save scoring, eight-bit rational quantization, 20,000-bin phase maps,
  64-frame/16-bit accumulation, bounded `+/-10 ppm` cadence hypotheses, two
  independent real positive chunks, one independent RF-negative chunk, and
  deterministic scrambled controls. The retained default is one-sample phase
  resolution; coarse phase bins are rejected by the weaker positive.
- Complete for the finite-width arithmetic checkpoint: 24-bit block-floating
  XFFT v9.1 replay, fixed kernel and product scaling, every structural FFT
  boundary, both kernel digests, all three real captures, maximum one-count
  score error, exact final phase/cadence/classification agreement, zero modeled
  overflow, and a generated one-core OOC resource/timing report.
- Complete for the IP-independent input-scheduling checkpoint: exact
  512/65/447 overlap contents, non-backpressured accepted-sample admission,
  ready/valid output stalls, absolute start indexes, fail-closed lifecycle and
  capacity restarts, two-RAMB36 inference, and 100 MHz post-opt OOC timing.
  Binding generated XFFT IP and producing normalized scores remain pending.
- Complete for the exact spectrum-product checkpoint: Q1.23 complex multiply,
  frozen one-bit safety shift, signed nearest/ties-even rounding, saturation,
  overflow telemetry, transform metadata, elastic stalls, flush, 4,112-vector
  cross-language replay, eight-DSP inference, and 100 MHz post-opt OOC timing.
  FFT binding, exponent restoration through the composed chain, and
  score-to-map composition remain pending.
- Complete for the exact input-energy checkpoint: every 66-sample CI16 window,
  38-bit rolling arithmetic, 2,048-result absolute-index retention, stale/future
  miss rejection, newest-write bypass, oldest-overwrite refusal, lookup stalls,
  fail-closed lifecycle restarts, two-DSP/2.5-BRAM inference, and 100 MHz
  post-opt OOC timing. Correlation joining and normalization remain pending.
- Complete for one exact rational score-divider lane: 69-bit numerator and
  denominator, exact eight-bit ties-to-even quantization, fixed eight-iteration
  calculation latency including zero/saturation cases, 4,112-vector
  cross-language replay, stalls, flush, zero-DSP/zero-BRAM inference, and
  100 MHz post-opt OOC timing. The wide score preprocessor, raw-result FIFO,
  second lane, dispatcher, ordered merge, and IQ-to-score composition remain
  pending.
- Complete for the exact exponent-aware ratio-preparation pipeline: signed
  Q1.23 correlation power, full XFFT exponent range, exact power-of-two
  restoration, exact 38-by-31-bit denominator, fail-closed 69-bit numerator
  saturation, 4,112-vector cross-language replay, elastic stalls/flush, four
  DSPs/no BRAM, and positive 100 MHz post-opt OOC setup/hold timing. Its narrow
  unplaced setup margin remains a composed-route risk; the raw-result FIFO,
  indexed-energy join, two-lane dispatch/merge, and IQ-to-score replay remain
  pending.
- Complete for the raw IFFT-result FIFO: 512 entries, exact 123-bit payload,
  complete 447-result burst absorption with a fully stalled consumer,
  concurrent read/write ordering, exact declared-capacity overflow, flush,
  two-RAMB36 inference, and positive 100 MHz post-opt OOC timing. The narrow
  OOC hold margin remains a composed-route risk; IFFT result qualification,
  indexed-energy joining, and two-lane score composition remain pending.
- Complete for the composed IFFT-candidate-to-score tail: strict 512-result
  framing qualification, 65-result overlap-save discard, absolute-indexed
  energy join, fail-closed miss/mismatch/orphan handling, 512-entry burst FIFO,
  exact exponent-aware ratio, two ordered divider lanes, 4,112-vector integer
  oracle replay, real-energy-cache one-block composition, bounded 344-entry
  measured occupancy, and positive 100 MHz post-opt OOC setup/hold timing. The
  generated-XFFT instantiation, CI16 IQ-to-score composition, phase-map
  connection, and full route remain pending.
- Complete for the strict generated-XFFT boundary: forward/inverse fixed
  configuration, reset stretch, one-block identity, natural-order indexes,
  TLAST, block-floating status/TUSER agreement, padding checks, same-cycle
  malformed-output gating, hard-event quarantine, nonfatal halt telemetry,
  mock-core replay, and positive 100 MHz post-opt OOC timing. Instantiating and
  replaying the generated transform pair remains pending.
- Complete for the selected upper-edge coefficient-ROM boundary: 512 exact
  signed-Q1.23 complex bins, canonical binary and textual SHA-256 locks, one
  synchronous 48-bit read, one-bin-per-clock elastic flow, bin/TLAST/exponent/
  block/stride quarantine, three complete-frame replays, five fault classes,
  one-BRAM-tile inference with nonzero initialization, and positive 100 MHz
  post-opt OOC timing. Generated-XFFT composition and complete CI16-to-score
  equivalence remain pending.
- Freeze native and edge-projected templates, CI16 quantization, capture hashes,
  CFO grid, tie rules, cadence rules, and expected output for the real replay.
- Reproduce the known 750 Hz lattice and robust exact-template peaks; run
  time-shifted, wrong-template, noise-only, and unrelated-capture controls.
- Freeze the common `qualification-policy` artifact before evaluating held-out
  data. It names every positive/negative partition and digest, minimum evaluated
  frames, allowed misses, exact raw-index/timestamp tolerance, multi-frame
  confirmation count, score/z thresholds, false-alarm denominator and ceiling,
  live observation duration, and tie/pass/fail rules.
- Preserve the lag-monitor analysis and its expected no-event result at 0.75.
- Expand the checkpoint into a predeclared multi-capture positive/negative
  partition, include the cadence-bank trial count in the false-alarm policy,
  and freeze the selected map ABI before RTL implementation. The current three
  chunks do not close that production policy.

Pass artifact: a machine-readable replay report with provenance, matched and
missed frames, timing error, score distribution, negative-control rate, and the
exact qualification-policy digest.

### Gate 2: 15 MS/s FPGA tracking and RX-only implementation

- Complete: retain the routed AXI diagnostic monitor only as a separate
  historical plumbing reference; compile it out of the exact shell. The
  one-bank, 65-lag raw correlator proves captured samples, stored raw
  timestamps, coefficient generation, 48-bit accumulators, and every raw tuple
  before reduction.
- Complete for `TRACK_ONE`: the queued-center AXI wrapper, cached `Eh`, sliding
  `Ex`, corrected 61-lag exact rational winner reducer, double-buffered result
  publication, level IRQ, coordinated reset, atomic telemetry, 210-window
  retained replay, and tested host controller. The prior full RX-only route is
  historical only; ABI 1.1 now has a separately validated fresh route.
- Pending before advanced tracking modes: add one-lag nine-bank CFO refinement,
  commanded adjacent-bank validation, and single-shot trace through a new
  capability-versioned ABI. Per-frame CFO switching remains forbidden in normal
  tracking.
- Prove bit-exact equivalence in simulation on structural vectors and bounded
  real-capture windows, including all 210 frozen replay windows, ties,
  enable/gap/index-jump flushing, coefficient rejection, and publication
  overrun accounting. Exercise full-width index wrap plus queued-center lead
  time, depth, late, duplicate, and overlap behavior and every corresponding
  counter.
- Superseded for the v1.0 shell: OOC reports, full RX-only timing/hold/CDC,
  resources, and the source-locked package remain audit evidence but are not
  reusable radio artifacts. Complete for ABI 1.1: fresh OOC/full route, scoped
  CDC and telemetry-bus skew, exact resources, and absence of TX DMA. Complete
  offline for ABI 1.2: deterministic 130-sample accepted-path injection, shared
  tracker/RX-DMA fan-out structure, fail-closed arm/mismatch behavior,
  real-window injection replay, block-RAM CDC implementation, and a fresh full
  route and package. Complete on the exact target radio for ABI 1.2: positive
  and independent-window packet invariants, byte-exact injected-sample
  observation in a concurrent RX DMA capture, and short sequential
  repeatability. Prequeued queue-depth and live-RF work remain Gate-3 items.
- If the exact engine misses its budget, reduce parallelism or scheduling while
  preserving numerical behavior. Do not weaken oracle agreement.

Pass artifact: routed bitstream reports plus a replay/simulation equivalence
bundle at the exact source commits, trigger-ABI test report, coefficient/template
digests, and qualification-policy digest.

### Gate 3: target-radio 15 MS/s RAM qualification

- Recheck for an existing IIO/USB owner before mutation. Stop rather than
  evicting an unrelated process or touching another radio.
- Qualify `ad9363a-1r1t` first, because 15 MS/s fits its documented 20 MHz
  analog-bandwidth class. Repeat transport and safe-state qualification with
  `ad9361-1r1t` without changing the FPGA detector geometry, but label that
  second pass as driver-personality compatibility on this physical AD9363A,
  not evidence of AD9361 silicon.
- At each boot, program the PHY parent to exactly 15,000,000 S/s, command the
  capture core to the same rate/factor 1, and read back both IIO device rates,
  the AXI bypass state, requested/read-back RF bandwidth, FIR/HB state, and
  achieved timestamp slope before loading a candidate window.
- For each profile, execute this indivisible order: PPU setup/reboot/verify the
  1R1T target and retain its setup receipt; build the v2 operation plan; RAM
  execute and qualify; run the separate `candidate-ram recover` command back to
  that same persistent 1R1T baseline; replay-validate the persistent-recovery
  receipt; only then change profile or rate.
- Run detector-disabled and detector-enabled trials. DMA SHA equality is required
  only for byte-identical deterministic replay/injection. For live RF, compare
  sample counts, achieved clock, timestamp continuity, gaps/overflow, exact
  settings, and oracle-matched events while exercising AXI status for the bounded
  policy-defined observation window.
- Prequeue enough predicted centers to prove measured host/USB lead-time and
  queue-depth margin at 750 Hz. Outside deliberately bounded fault injection,
  `late`, `rejected`, `aborted`, `overrun`, capture-overflow, and result-overflow
  deltas must all remain zero for the entire qualification window.
- RTL replay qualifies arithmetic only. A hardware-complete detector-path claim
  requires a source-locked RX-path test mux or external RF generator driving the
  accepted-sample boundary with onboard TX absent. An ambient trial with no
  signal qualifies radio transport and recovery, not live PSS.

Pass artifact for each profile: setup receipt, v2 operation plan, RAM receipt and
SHA-256, candidate/status/capture digests, timing/continuity metrics, and
persistent-recovery receipt and SHA-256. Gate 4 may start after
`IMPLEMENTATION/RADIO-TRANSPORT PASS` plus a deterministic hardware-complete
`HARDWARE-INJECTION PASS`, complete rollback, and reviewed negative controls;
this is the explicitly named 15-MS/s engineering-advancement state.
`LIVE-SIGNAL PASS` additionally requires
multi-frame exact-template agreement under the frozen qualification policy and
remains mandatory before SSS or a live-performance claim.

### Gate 4: 30 MS/s direct-first full-rate qualification

- Start only after the explicitly named 15-MS/s engineering-advancement bundle
  above is reviewed. Ambient `LIVE-SIGNAL PASS` may remain separately pending;
  it is never implied by advancing the implementation ladder.
- Compile out the diagnostic monitor and remove the unused legacy `/8` FIR.
  Remove its decimation-core device-tree advertisement in the same source
  change. Preserve 30 MS/s DMA, prove equal PHY/capture readbacks at factor 1,
  and first parameterize the bounded sparse direct engine for 132 taps, 129
  lags, and a 260-sample tagged capture.
- Qualify normal one-bank tracking at the conservative 13.062 Mcycles/s budget.
  A commanded three-bank full-aperture validation budget is 38.604 Mcycles/s
  at 750 Hz and may be enabled after full route. Nine full-aperture banks every
  frame are explicitly rejected at a 100 MHz engine; the nine-bank one-lag
  refiner is separately budgeted; blind acquisition remains on the canonical
  15 MS/s FPGA score/map path.
- Implement a deterministic x2 lane for continuous acquisition while retaining
  the direct 30 MS/s exact tracker. Its anti-alias response, phase/delay
  mapping, rounding, saturation, source-index convention, and post-filter
  template digest are a distinct oracle. The x2 output must reproduce the
  selected 15 MS/s phase-map decisions within the predeclared tolerance; it is
  never used to relabel reduced-rate timing as exact 30 MS/s timing.
- On the required exact AD9363A serial, first run `ad9363a-1r1t` with read-back
  RF bandwidth at or below 20 MHz as an in-spec narrowband/sample-rate trial.
  Use `ad9361-1r1t` only for an explicitly out-of-spec greater-than-20-MHz
  characterization and retain requested, clamped/read-back bandwidth, and the
  measured sweep. Neither qualifies full-band 30 MS/s reception. A separate
  physically attested AD9361/AD9364 target is required for the full-band pass
  state and repeats the identity, RF-response, live, and rollback gates under
  its own serial.
- Repeat all offline, implementation, safe-state, capture-continuity, live,
  and rollback gates. No offline-only result is hardware qualification.

Pass artifact: selected-architecture equivalence and rationale, routed 30 MS/s
reports, exact-AD9363A in-spec narrowband transport/injection receipt, any
separate greater-than-20-MHz experiment explicitly marked out of specification,
full-rate capture evidence, and rollback proof.
The independent `30-MS/s FULL-BAND PASS` additionally requires the physically
attested AD9361/AD9364 serial and its bound RF/live evidence. Gate 5 engineering
may start after `IMPLEMENTATION/RADIO-TRANSPORT PASS`, `HARDWARE-INJECTION PASS`,
negative controls, and rollback at 30 MS/s; full-band Gate 5 work additionally
requires `30-MS/s FULL-BAND PASS`.

### Gate 5: exact 60.000 MS/s direct-first qualification

- Start only after the explicitly named 30-MS/s engineering-advancement state
  above closes. Full-band qualification additionally requires the 30-MS/s
  full-band pass and the same physically attested AD9361/AD9364 serial. Record
  the achieved sample clock and measured analog filter settings; an
  `ad9361-1r1t` readback alone is insufficient.
- On the exact AD9363A, separate an in-spec `ad9363a-1r1t`, <=20-MHz
  narrowband/sample-rate trial from any explicitly out-of-spec
  `ad9361-1r1t`, greater-than-20-MHz characterization. Neither receives the
  full-band pass state.
- Preserve 60 MS/s DMA into DDR and first parameterize the direct engine for 264
  taps, 257 lags, and a 520-sample tagged capture. Normal one-bank tracking is
  budgeted at 51.468 Mcycles/s and must close in a 100 MHz engine. Three
  full-aperture banks every frame require 153.240 Mcycles/s and are permitted
  only after a separate 200 MHz full-route closure; otherwise schedule that
  validation less often. Nine full-aperture banks every frame fit neither clock
  and remain host/offline diagnostics; nine banks at one selected lag use the
  much smaller `CFO_REFINE` budget.
- Re-run all timing/resource checks at achieved clocks and stress DDR ingress,
  bounded readout backpressure, expected overflow reporting, thermal behavior,
  and long-run timestamp continuity. Use bounded DDR captures or segmented
  readout; do not imply that USB can continuously carry 240 MB/s CI16 ingress.
- Implement an x4 DDC for continuous acquisition while retaining the direct
  60 MS/s exact tracker. Its quantized response, source-index phase, and group
  delay require a new versioned template digest and cannot inherit direct-15
  identity merely because its output rate is 15 MS/s.
- The AD9361 nominal 56 MHz analog RF bandwidth is not described as a flat
  60 MHz passband. This gate requires requested and observed `60,000,000` S/s
  under a predeclared clock-tolerance policy. A 61.44 MS/s result is not renamed
  to 60: it is a separate follow-on with either a new fractional-rate oracle or
  a proved `125/128` resampler to exact 60 MS/s (`125/512` directly to 15 MS/s),
  including new phase, delay, and filter evidence. If RF response, timing, or
  transport fails, retain the evidence and stop; do not reinterpret a narrower
  capture as full-rate qualification.

Pass artifact: selected-architecture equivalence and rationale, routed
60.000-MS/s reports, exact-AD9363A in-spec narrowband transport/injection
receipt, any greater-than-20-MHz trial explicitly marked out of specification,
sustained detector/DMA-ingress metrics, bounded capture evidence, RF-response
record, and rollback. `60.000-MS/s FULL-BAND PASS` exists only for a physically
attested AD9361/AD9364 target with the bound bandwidth, response, and live-signal
evidence.

### Gate 6: always-run campaign closure and radio restoration

- After all planned PSS trials, or immediately after any failed/aborted stage has
  reached a safe reconciled state, use the pinned known-good merged PPU path to
  restore the persistent target to `ad9361-2r2t`; reboot the ordinary persistent
  image and verify exact target readback, the expected two-RX/two-TX IIO
  inventory, TX safe state, boot identity, route release, and unchanged
  persistent image hash.
- Replay-validate and retain the final setup/recovery receipts. The campaign is
  not complete while the target radio remains in either 1R1T profile, DFU, an
  experimental RAM image, or an indeterminate receipt state. Gate 6 is therefore
  a `finally` path for every Gate 3/4/5 exit, not a reason to continue after a
  stop condition.

Pass artifact: a sealed final 2R2T restoration bundle bound to the exact radio,
PPU commit, persistent image, boot ID, topology, route cleanup, and receipt
hashes.

### Gate 7: SSS, only after the complete PSS ladder closes

- Freeze an SSS oracle and test vectors only for a rate with qualified PSS
  timing, CFO, sideband, cadence, and false-alarm behavior.
- Demonstrate host SSS recovery from PSS-gated windows before budgeting FPGA
  logic. Report timing evidence separately from decoded identity/content.
- Any FPGA SSS block receives its own functional, resource, timing, radio, and
  rollback gates; it does not inherit qualification merely from PSS.

## Stop rules and evidence ledger

Every build and trial records parent/submodule commits, tool versions, waveform
digests, rate and selected direct/DDC geometry, schedule/clock budget, Vivado
reports, image hashes, PPU commit, target and sealed receipt, radio
serial/topology, live RF/IIO attestation, capture hashes, detector configuration,
raw-tuple and reduced-result metrics, rollback proof, and the evidence label.

Stop advancement immediately, then enter the bounded safety epilogue, on
identity drift, route contention, an unexpected owner, a
live TX device, unexpected scan channels, source-lock mismatch, negative timing
or hold slack, a critical DRC, resource-budget breach, an unexpected DMA gap or
overflow during a qualification run, timestamp-map disagreement, oracle
disagreement, or missing rollback evidence. Deliberate fault-injection tests may
cause a declared capture/result overflow only inside their bounded test case;
the exact expected counters, flush, rejection, and recovery state must match
before continuing. No stage is skipped because a later rate happens to
synthesize, and no failed gate is converted into a pass by changing terminology
or lowering a threshold.

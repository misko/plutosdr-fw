# Starlink PSS 15/30/60 MS/s RX-only development plan

Status: experimental and **DO NOT MERGE INTO FIRMWARE MAIN**. The experimental
FIT/DFU image is RAM-boot-only and is never written to QSPI. PPU setup may make
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

| RX/DMA rate | Projected useful/prefix/symbol at RX rate | Samples/frame | Direct taps/lags | One-bank correlation tap-cycles/s | Optional measured fallback |
|---:|---:|---:|---:|---:|---:|
| 15 MS/s | 64 / 2 / 66 | 20,000 | 66 / 65 (`+/-32`) | 3.2175 M | none |
| 30 MS/s | 128 / 4 / 132 | 40,000 | 132 / 129 (`+/-64`) | 12.771 M | x2 to 15 only if measured better |
| 60 MS/s | 256 / 8 / 264 | 80,000 | 264 / 257 (`+/-128`) | 50.886 M | x4 to 15 only if measured better |

The default 30 and 60 MS/s design is sparse, candidate-gated direct correlation
at the full RX rate; it does not process the continuous stream. The search
half-width is fixed in time at `32/15e6 = 2.133333 us`. For rate multiplier
`m` in `{1,2,4}`, taps are `66m`, half-width is `32m`, lags are `64m+1`, and
capture length is taps plus lags minus one: 130, 260, or 520 samples. This keeps
the capture interval at 8.667 us and yields ranges `p-32..p+97`,
`p-64..p+195`, and `p-128..p+391`.

Correlation tap count alone is not a schedule. The direct design computes each
captured sample energy once, forms the first `Ex` window, then updates it by
`Ex[k+1] = Ex[k] - e[k] + e[k+N]`; validated coefficient `Eh` is cached at
commit. With `N=66m`, `L=64m+1`, and capture length `M=N+L-1`, the conservative
full-aperture budget is `M + (L-1) + B*L*N` cycles for `B` coefficient banks,
before small wrapper/publication overhead. Here `B=3` and `B=9` mean all lags
for every bank; they are validation/diagnostic modes, not the one-lag CFO
refiner:

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

An independent x2/x4 DDC lane remains an alternative, not an assumption. Its
mixer, filter coefficients, integer phase, group delay, rounding, saturation,
alias controls, post-filter template digest, and full-rate timestamp mapping
must form a new versioned oracle and materially beat the direct design in OOC
and full-route evidence. Either architecture preserves detector-independent
full-rate RX DMA.

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
pipeline latency. Initial acquisition is different: host bootstrap must first
collect and search enough data to establish template, sideband, CFO, phase,
and 750 Hz cadence. No sub-symbol acquisition-latency claim is made. Once
locked, an N-frame observation window is `N/750` seconds, while latency from the
first through the Nth event is `(N-1)/750` seconds. Thus four events span 4.00 ms
first-to-fourth within a 5.33 ms observation allocation; eight span 9.33 ms
within 10.67 ms, plus pipeline and host/FPGA handoff latency.

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
2. At 15 MS/s, acquire with the existing host golden search: exact lower/upper
   PSS templates, explicit CFO hypotheses, deterministic tie handling, and
   multi-frame 750 Hz cadence. Refine the nine CFO banks across repeated-frame
   evidence, then lock one block-selected CFO for local frame tracking. Do not
   maximize nine banks independently on every frame; that changes the oracle
   and preferentially selects noise.
3. Hand only bounded predicted windows to a candidate-gated FPGA exact
   correlator. The engine supports 65 trial lags `[-32,+32]` and 66 template
   taps. Normal one-CFO tracking is 3,217,500 complex tap-MACs/s. An explicitly
   commanded three-bank check is 9,652,500, and an all-nine diagnostic is
   28,957,500. Blind acquisition remains on the host. A three-DSP, one-complex-
   tap-per-cycle engine has ample scheduling margin at 100 MHz; generated OOC
   and full-route reports, not this arithmetic, decide acceptance.
4. Deliver the exact engine in two steps. First publish all 65 raw
   `{lag,index,C_re,C_im,Ex,Eh}` tuples for one host-selected Q1.15 coefficient
   bank so the host can reproduce every score and tie. Then add the exact
   normalized reducer, nine-bank one-lag CFO refinement, adjacent-bank checks,
   and trace mode. Coefficients are host-quantized with round-to-nearest,
   ties-to-even, digest- and CRC-bound, and never synthesized by a runtime NCO.
   The engine reports candidate measurements only; multi-frame alignment and
   false-alarm policy remain on the host.
5. Scale the sparse direct engine first at 30 and 60 MS/s: 132 taps/129 lags,
   then 264 taps/257 lags, with sliding `Ex` and cached `Eh`. An independently
   qualified x2/x4 DDC is considered only if generated OOC and full-route
   evidence shows a material advantage while preserving full-rate DMA.
6. Retain the 0.75 repeated-delay monitor only in a separate diagnostic build
   as the already-qualified AXI/CDC reference. Compile it out of the first
   radio-eligible exact-detector image so its 21 DSPs and control logic cannot
   crowd the useful correlator. It is not upstream of exact search and cannot
   suppress it.
7. Begin SSS only after the complete 15/30/60 PSS ladder has closed, including
   timing, sideband, CFO convention, cadence, false-alarm, radio, and rollback
   evidence. Start SSS in the host; move it into FPGA only if profiling shows a
   justified bounded workload.

An autonomous full-stream blind FPGA search is deliberately deferred. If host
bootstrap is later unacceptable, compare an overlap-save FFT correlator or a
separately proven coarse stage against the same recordings and negative
controls as a new reviewed scope. The repeated-delay metric is not promoted to
that role without new evidence.

### Stage-15 exact-engine contract

The first exact engine runs at 100 MHz and captures exactly 130 tagged samples
around each predicted center: `p-32` through `p+97`. Each output names the
stored raw timestamp at its first tap; no timestamp is reconstructed from
pipeline latency. Disable, FIFO overflow, or a nonconsecutive accepted index
flushes the job and increments a visible abort counter.

Before wrapper RTL freezes, the versioned ABI must define how `p` is delivered:
a full-width accepted-sample index/timestamp and explicit wrap rule, the host
queue operation, queue depth and minimum lead time, and deterministic treatment
of late, duplicate, or overlapping centers. Disable, valid gaps, index jumps,
capture/result overflow, and reset flush every affected request and increment
separate rejected, late, aborted, and overrun counters. Gate 2 tests every case;
an inferred pipeline-time center is never accepted as equivalent.

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

The exact engine receives a distinct 16 KiB AXI aperture at `0x79040000`; the
diagnostic monitor remains read-only at `0x79030000`. Its versioned ABI has
separate `TRACK_ONE`, `CFO_REFINE`, `VALIDATE_BANKS`, and `SINGLE_SHOT_TRACE`
modes, shadow/active coefficient banks, commit generation and validation
status, double-buffered results, and processed/aborted/overrun counters. A
configuration becomes active only after host readback, SHA-256 verification,
CRC/energy validation, and an idle-boundary generation acknowledgement.

The initial measured-budget target for the exact correlator, control, and
result block is at most 3 DSP48E1s, 5 BRAM36 equivalents, 2,500 LUTs, and 2,000
registers. Detection-lane DDC resources at 30/60 MS/s are budgeted separately.
Every number remains provisional until both OOC and complete Zynq-7010 route
reports exist.

The 21-DSP repeated-delay monitor is temporary integration instrumentation. Its
source-locked routed build remains the reference for AXI visibility and CDC,
but the first radio-eligible exact image compiles it out. No PSS function
depends on keeping it.

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

A frozen CI16/Q1.15 one-bank tracking model has also been replayed over all 210
first-chunk real windows using the oracle's actual upper-edge, `-100 kHz`,
local-radius-30 semantics. It selected the identical integer lag in 210/210
windows. Fixed-versus-float normalized-score absolute error was at most
`1.52e-5`, with median `3.49e-6`. In contrast, allowing each frame to maximize
all nine CFO banks across the proposed 65-lag `[-32,+32]` aperture retained the
block-selected `-100 kHz` bank in only 97/210 windows. These results freeze the
acquisition-versus-tracking split and form a predeclared Stage-15 equivalence
target.

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
- functional closure: bit-exact oracle agreement for score, hypothesis, index,
  timestamp mapping, ties, overflow, saturation, zero energy, valid gaps,
  enable changes, index jumps, wrong cadence, and negative recordings;
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
`8074b228083240860843b0fb4dd4d5b46f06805b` until a later merged PPU revision
passes the same recovery fixtures. The epilogue closes buffers, stops detector
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

- Gate 0: **COMPLETE - SOFTWARE ONLY / HARDWARE UNTESTED**;
- Gate 2A diagnostic monitor: **COMPLETE OFFLINE** at the source-bound trusted
  run above; it is status plumbing, not PSS;
- Gate 2B raw exact arithmetic: **COMPLETE OFFLINE**; its wrapper, sliding-energy
  scheduler, reducer, integration, and full route remain pending;
- Gate 1 and the rest of Gate 2B: in progress or pending;
- every target-radio, 30 MS/s, 60 MS/s, campaign-close, and SSS gate: pending.

### Gate 0: PPU foundation on `main` - COMPLETE SOFTWARE ONLY

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

Pass artifact: PPU `main` `8074b22`, green CI, 1,311 local tests with 11 hardware
or browser skips, target-profile tests, and offline receipt/recovery fixtures.
Starlink code is not part of that commit. Attached-radio behavior remains
untested until Gate 3.

### Gate 1: frozen oracle and 15 MS/s offline acquisition

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

Pass artifact: a machine-readable replay report with provenance, matched and
missed frames, timing error, score distribution, negative-control rate, and the
exact qualification-policy digest.

### Gate 2: 15 MS/s FPGA tracking and RX-only implementation

- Treat the already routed AXI diagnostic monitor as a completed, separate
  plumbing reference without calling it a detector. Complete the one-bank,
  65-lag raw-result exact correlator at 100 MHz, then compile the monitor out of
  the radio candidate. Prove captured samples, stored raw timestamps,
  coefficient-bank identity, 48-bit accumulators, and all 65 raw tuples before
  adding a winner reducer.
- Add the queued-center wrapper and convert `Eh`/`Ex` scheduling to cached and
  sliding form. Differentially prove that all 65 raw tuples remain identical to
  the isolated milestone, including under result backpressure.
- Add the exact rational reducer, one-lag nine-bank CFO-refinement mode,
  commanded adjacent-bank validation, double-buffered result publication, and
  single-shot trace. Per-frame CFO switching is forbidden in normal tracking.
- Prove bit-exact equivalence in simulation on structural vectors and bounded
  real-capture windows, including all 210 frozen replay windows, ties,
  enable/gap/index-jump flushing, coefficient rejection, and publication
  overrun accounting. Exercise full-width index wrap plus queued-center lead
  time, depth, late, duplicate, and overlap behavior and every corresponding
  counter.
- Run OOC reports, then full RX-only shell implementation and every common
  timing, DRC, resource-headroom, DMA-equivalence, and device-tree gate.
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
  refiner is separately budgeted and blind acquisition remains on the host.
- Only after the direct design has exact replay, OOC, and complete-route results,
  prototype a deterministic x2 lane if warranted. Its anti-alias response,
  phase/delay mapping, rounding, saturation, and post-filter template digest are
  a distinct oracle. Select it only if measured evidence materially beats the
  direct design, never merely because it reuses the 15 MS/s tap count.
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
- Prototype an x4 DDC only if the routed direct result leaves a concrete need.
  Its quantized response requires a new versioned template digest and cannot
  inherit direct-15 identity merely because its output rate is 15 MS/s.
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

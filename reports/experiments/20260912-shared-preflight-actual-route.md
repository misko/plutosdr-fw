# Shared preflight diagnostic history — DO NOT MERGE

This is an isolated FPGA PSS controller/actual-FFT/buffer experiment, not the
separate native GLRT project and not a deployed receiver release. The native
60 MS/s fine search and independent 2.5 MS/s CI16 inspection stream remain
mandatory receiver requirements. No radio, PPU or main branch was changed.

Branch (FW and HDL):
`codex/starlink-rx-only-do-not-merge-shared-preflight-evidence`.

## What changed

The runtime derives directly from the lean private-replay baseline, not the
slower product-capacity or replay-ring candidates. Six preflight causes now
accumulate into a shared same-edge, asynchronously reset history register.
Both result guards reuse that diagnostic history instead of separately
reducing the current six-cause vector into their diagnostic bit. All current
admission/publication vetoes remain unchanged. This adds no replay queue,
changes no FFT arithmetic, and introduces no diagnostic latency.

Both original result guards run beside the actual FFT simulation. Every guard
input is shared; every output and 17 private-state fields are compared on both
sides of every fast edge. Inherited direct register-fault injections are
explicitly mirrored into corresponding private storage and reference storage.

Healthy actual FFT results remain 64,512 exact numerical words and 4,178 fast
clocks. CSV SHA256:
`df33d4b05c4ae65191af85f9e6748a484773d0a659051a5fad7112b8a717d8c8`.
The 5,215-clock short-service ceiling is unchanged. This does not prove
continuous RX throughput.

## Physical result: not promoted

Frozen 100/175 MHz OOC recipe, actual FFT, no timing exceptions added:

| Metric | Lean private replay | Shared preflight |
| --- | ---: | ---: |
| WNS | -1.182 ns | -1.318 ns |
| TNS | -349.709 ns | -453.574 ns |
| Failing setup endpoints | 930 | 1,049 |
| LUT | 2,756 | 2,729 |
| FF | 5,908 | 5,913 |
| RAMB18 / DSP | 16 / 21 | 16 / 21 |
| Short service clocks | 4,178 | 4,178 |

The routed checkpoint is source-matched and fully routed (8,491 nets, no
routing errors). Hold +0.029 ns, pulse +1.830 ns. Internal setup FAILS;
114 inputs and 124 outputs remain unqualified in this isolated context.
Full-board clock/CDC/reset signoff is not implied.

Explicit endpoint inventories, not guessed register names:

- Six shared-history D pins: worst -0.682 ns.
- Sixteen private guard-reason D pins: worst -0.494 ns.
- Two guard-active D pins: worst -1.318 ns.
- Admission-consumed D pin: -1.307 ns.
- Registered fast-fault D pin: +1.403 ns.
- Kernel next-start CE: -0.622 ns; forward replay-position CE: -0.594 ns.
- Product/output publication: -0.727 / -0.632 ns.

Worst path is fast epoch release through output fault/ledger logic, guard
capacity, admission request/permit and finally owner-0 active state:
nine logic levels, 7.025 ns data delay. Moving the diagnostic reduction helped
that local cone but did not close the architecture's other control paths.

## Verification and retained rejected attempts

The initial full inherited 82-case actual FFT campaign passed, including
1,708,758 original-guard comparisons per owner, but had zero direct preflight
fault edges. That is insufficient to qualify the new history inputs.

The extended campaign adds all six causes, X/Z descriptor comparisons, and
both one-sided raw resets with fresh recovery. Its first run passed the six
known-cause cases, then exposed a pre-existing observer error: Boolean OR is
not equivalent to the RTL's sticky procedural `if` update for X/Z predicates.
Version 3 changes only that expected-value model to match the original RTL
conditional; all current fault/publication assertions and original guards
remain present. The failed run is retained, not relabelled as a pass.

The first relocated scoped regression had 2,264 passes and one failure from a
historical path-string identity check. Resolving the test's input alias to the
original canonical prepared directory fixes the fixture without relaxing the
source-hash or same-source checks. A separate component run initially expected
the wrong Python exception class; its failed XML is retained too.

Final results: **2,266 scoped tests pass** (159.876 s), and **all 92 actual
FFT fault/reset/stall cases pass** (369.817 s). Each original guard compares
exactly for 1,850,180 checks, including 12 known preflight fault edges; both
X/Z cases and both raw-reset cases pass with fresh 512-word recovery. The
original 28 delayed guard-fault observations remain present. No assertion
was skipped around unknown inputs or injected faults.

Source FW commit: `1d50e40dc32b80b33fa4f0b6aa19d981678e7bb4`.
HDL commit: `3da1ba9365416fa4a133ddedd8efe54bca7a8fa2`.
Both source commits are pushed on the branch above.

Healthy/synth prepared pin:
`c21c9d3295511b48dd0a090eb4802b53b4e130848732de6398e1bed1b75283db`.
Extended v3 pin:
`bebd79f01e5e9f52138850c3ad0181cdf80a8e2dfae36905a21ff375876f7fbc`.
All 43 runtime source files are identical between those profiles.
Routed DCP SHA256:
`246c4f9d713c77e07dacea6ae815855ee928952bb1a383314a3e783f8fa718f7`.

## Next architecture decision

Do not automatically stack this slower-routed variant on the lean baseline.
Compare a bounded admission-grant experiment against the lean parent:

1. Separate a stable job request from the current cross-block readiness tree.
   Capacity/fault facts already have registers, but the request currently
   reintroduces current guard/cutover capacity into the permit path.
2. Define an explicit held-bank, held-descriptor ownership contract. If capacity
   is not ready, retry acquisition rather than freezing a rejected snapshot.
   A private grant is not permission to publish or to bypass current faults.
3. Before implementation, enumerate grant capture, consumption, revocation,
   reset and candidate expiry. Prove no stale grant, duplicate job, descriptor
   substitution, bank reuse or core launch after quarantine.
4. Measure actual FFT arithmetic, added service clocks, complete boundary
   tests, and routed admission/kernel/publication endpoints. Reject a variant
   that merely moves the critical path or misses the throughput budget.
5. Only after isolated timing passes, integrate the complete receiver at its
   actual board clocks (including the 200 MHz IDELAY reference), verify
   continuous native + inspection DMA/Ethernet, then qualify .18 and deploy
   reversibly to .17 through PPU.

No TX removal, clock-exception waiver, relaxed fault checking, dropped native
fine search, or removed inspection stream is part of this plan.

## Artifact location and hardware scope

Verified archive: `reports/evidence/20260912-shared-preflight-evidence.tgz`
(26,170,354 bytes, 108,656 regular members including generated regression
fixtures and retained rejected attempts). SHA256:
`f128737c4529a69b6e89e1ed23f1bb3e30aa772cd1a46738d8db1982325c14df`.
The archive is tracked on this bulk-volume experiment branch, not duplicated
into the nearly-full PRIMARY object store. The adjacent receipt records
sequential payload SHA256/inventory/CRC verification and unchanged sources.

Artifacts: `/srv/bulk/leo/starlink-pss-preflight.RVtFMZII/experiment.AZdWieXD`.
The build moved to bulk storage because the original root volume is nearly
full. These independent clones use Git object alternates; do not delete their
original repositories. Historical input directory links are aliases only.

Canary .18: `1040007c4a94000211000b009186843ef2`.
Outdoor .17: `104000bac4950008230026001b440a003a`, Ethernet-only PPU,
RX1 powered LNB, no transmitter attached. .14/.20/.21 are excluded.
PRIMARY HDL remains pinned at `0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.

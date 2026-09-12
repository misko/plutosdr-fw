# Guard storage driven by checked completion pulse — DO NOT MERGE

**Functional proof passes. Targeted timing improves, but complete timing is
still unclosed and this is not deployable.** No PRIMARY HDL promotion.

FW/HDL branch: `codex/starlink-rx-only-do-not-merge-guard-pulse`.
Runtime parent: retry-admission top/guard, not the rejected ownership-lock or
abort-echo variants retained in Git history. The original descriptor lock and
completion adapter remain active. All 43 runtime parent files are unchanged;
one selectable top and one guard bring the frozen inventory to 45 files.

## Implementation and exact timing contract

The existing guard `commit_pulse` register already records the fully checked
final handshake. This experiment uses that receipt to update private active
and ACK storage on the following edge. Effective state still changes on the
same edge as the original:

```verilog
wire completion_receipt = commit_pulse === 1'b1;
wire active_private = active_storage && !completion_receipt;
wire awaiting_ack = ack_storage || completion_receipt;
```

Private active storage clears from the receipt. ACK storage takes the receipt,
but a same-edge legal ACK clear has priority; otherwise an immediate ACK would
be incorrectly resurrected after the pulse falls. Case equality is necessary:
an unknown final commit does not take the original procedural-if transition,
so an X pulse must not clear active or create an ACK wait.

No new register or payload RAM is added. The original final-commit expression,
current publication vetoes, ACK permission, fault-reason accumulation,
descriptor checks and all remaining state are unchanged. Exact source
transformations restrict the runtime changes.

Same-input original guards run alongside the actual FFT candidate. Every output,
effective active/ACK state and all other private fields are compared before
and after every fast edge. Only the two new storage representations may differ;
their intentional one-edge differences must actually be observed. Original
fault-register injections are mirrored to the reference, without changing the
candidate's injection targets or any assertion/deadline.

## Verified tests

**2,390 scoped tests pass**, 164.874 s: 133 inherited modules plus two new
guard-pulse modules. Not the entire repository suite.
The preceding 2,383-case scope also passes (166.619 s).

The final 30 new cases cover exact RTL deltas, source/witness gates and:
- Complete 512-input/512-output frames in both directions.
- Immediate and delayed ACK, both private-ACK modes, late qualification,
  unknown completion pulse, final-edge fault, pulse-edge fault and reset.
- 4,096 four-state preflight vectors and 20,000 randomized cycles per ACK mode.
- Five broken implementations rejected: missing active view, missing ACK view,
  logical rather than case-equality receipt, missing delayed active clear, and
  wrong ACK-clear priority.
- Conditional and adjacent mirrored fault-injection syntax; missing and
  duplicated injections must be rejected.

Each complete component comparison records 165,712 checks, 44 pulse/storage
observations, 30 immediate ACK observations and 25 unknown pulses.
These immediate-ACK cases are component proof; the actual FFT/buffer campaign
does not happen to ACK during the completion pulse.

Healthy actual FFT: **64,512 exact numerical words**, **4,178 clocks**,
177,346 comparisons per original guard, 18 pulses and 18 intentional storage
differences per guard. No added externally visible latency; the original
5,215-clock short-service ceiling is unchanged.

Full actual FFT campaign: **all 92 fault/reset/stall cases pass**, 357.029 s.
Each original guard matches across **1,851,082 checks**. Forward/inverse pulse
and storage-difference counts are 171/129. All 316 job admissions still match
the original admission certificate; all inherited 28 delayed guard-fault
observations remain. Main, auxiliary and synthesis use the same 45 runtime files.

CSV SHA256:
`df33d4b05c4ae65191af85f9e6748a484773d0a659051a5fad7112b8a717d8c8`.

These are actual generated-FFT/buffer simulations, not continuous receiver,
IIO/DMA or RF qualification.

### Retained rejected harness preparations

No runtime RTL changed while correcting these test-generator failures:

1. Auxiliary v1 appended a second force to a single-statement if/else, causing
   a compile error near else.
2. v2 wrapped the paired injections but adjacent releases became endbegin,
   causing a compile error near release.
3. v3 preserves statement scope and token separation; all 92 cases pass.

The initial standalone syntax fixture also used the reserved SystemVerilog
keyword design as a module name. Its rejected compile is retained; the corrected
fixture now proves the valid generator compiles and the two earlier generators
fail for conditional and adjacent layouts. Final component-v4 has 30 passes.
Helpers/preparations are versioned; failed evidence is not overwritten or
counted as a successful campaign.

## Routed measurements — incomplete

Same frozen 100/175 MHz OOC recipe and actual FFT/buffers; no added exceptions:

| Metric | Retry-admission parent | Guard-pulse |
| --- | ---: | ---: |
| Worst setup | -1.269 ns | -1.236 ns |
| Same-175 MHz worst | -1.001 ns | -0.998 ns |
| Total negative slack | -295.708 ns | -299.750 ns |
| Failing endpoints | 811 | 764 |
| LUT / FF | 2,739 / 5,920 | 2,747 / 5,911 |
| RAMB18 / DSP | 16 / 21 | 16 / 21 |
| Short service | 4,178 clocks | 4,178 clocks |

8,555 nets fully routed, zero routing errors. Hold +0.035 ns; pulse +1.830 ns.
114 inputs and 124 outputs remain unqualified. Overall worst is an unqualified
held-tag 175-to-100 MHz crossing; it is not waived. Same-domain timing still
fails independently.

The same new probe measures the original storage pins in the parent and the
retimed storage pins in the candidate, also checking the unchanged completion
registers. Every group must have real pins:

| Endpoint | Parent | Guard-pulse |
| --- | ---: | ---: |
| Active storage | -0.908 ns | -0.549 ns |
| ACK storage | -0.888 ns | -0.580 ns |
| Checked completion pulse | -0.874 ns | -0.533 ns |
| Guard reasons | -0.669 ns | -0.575 ns |
| Admission snapshot valid | +0.009 ns | -0.471 ns |
| Admission consumed | -0.040 ns | -0.523 ns |
| Global registered fault | +0.320 ns | +2.064 ns |

Kernel-next CE now has +0.006 ns, but output publication worsens to -0.998 ns
and product publication to -0.772 ns. The mixed aggregate result is not a
release pass or proof that every endpoint improved.

The worst same-clock path starts at engine metadata bit 66, passes through
preflight identity/header equality and preparation_fault_now, and reaches
the output-bank request toggle: eight levels, 6.705 ns data delay, about 76%
routing. This is the next measured target.

## Next exact change: phase-specific publication fault reduction

Inspection shows:
- preflight events are zero when preparing is false;
- quiet publication independently requires preparing to be false.

A prospective proof covers all **262,144 four-state combinations** of preparing,
fast-running, six preflight-event bits and the remaining fault term. It proves:

```verilog
(!preparing && !(other_fault || preparation_fault_now))
    === (!preparing && !other_fault)
```

Here preparation_fault_now is the reduction of the original phase-gated event
vector, not an arbitrary independent signal. The proof checks that the current
RTL retains these premises and rejects mutants omitting the phase condition
or another fault. It is **not yet a runtime change**, routing result, or general
permission to remove preflight validation.

Next implement a separate quiet-publication fault view omitting only this
phase-inactive term. Keep the original full predicate for reference/diagnostics,
the nonquiet branch unchanged, all acquisition-time preflight checks, sticky
cause evidence and every remaining current veto. Compare the original complete
publication predicate before/after every fast edge, including X/Z conditions,
preparation-to-active transitions, faults, both resets and recovery. Run the
actual FFT/buffers and all fault cases, then route and compare all endpoint groups.

This candidate is a reasonable measured basis for that next experiment because
the targeted guard storage paths improve without added service latency; retain
the retry-admission/lean comparisons. No automatic full-receiver promotion is
authorized by the scoped results.

## Full deployment gates remain open

Native 60 MS/s fine search, independent 2.5 MS/s CI16 IIO inspection, causal
acquisition/CFO/fine processing, eight high/low targets with 120 ms valid dwells
over 300 s and independent host GLRT remain required.

After subsystem closure: full receiver route at actual board clocks, CDC/reset/
I/O qualification, sustained native and inspection DMA/Ethernet, actual 60 MS/s
RX calibration, serial-verified .18 canary, reversible pinned Ethernet PPU
deployment to .17, real reception/replay comparison and clean stop/restart.
The 200 MHz IDELAY reference is not changed or waived.

No radios, PPU or main branches were touched. PRIMARY HDL remains
`0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.
.18 canary: `1040007c4a94000211000b009186843ef2`.
.17 outdoor Ethernet-only LNB RX1 receiver:
`104000bac4950008230026001b440a003a`.
.14/.20/.21 remain excluded.

## Reproducibility

Artifacts: `/srv/bulk/leo/starlink-pss-preflight.RVtFMZII/guard-pulse-artifacts.EqZnBaxQ`.

Main/synthesis pin:
`96cef71c3f92a4a9f4dea6d477073aa92652604a6becd4e05a33e84fb89bf36e`.
Final auxiliary pin:
`9b35ca5ab8b519cd9d8dfcae2ed13f1918e5395daf6dfc7add16670a631eaf6b`.
Synthesis DCP:
`8875019c7931443e91cd30bc376a4f08ae0eafd8f171442d8903e5591311028b`.
Routed DCP:
`88bc8c9aac81ac91d6941e9192e0dcd2ca428af3dd4d68cce3d0d038c2290001`.

Archive recording freshly checks numerical/original-guard/admission witnesses,
45 runtime files, prepared source hashes, final regression XML/source hashes,
both unmutated component guard copies and frame templates, prospective phase
proof inputs/logs, and all route/probe inputs and checkpoints.

Verified archive: `reports/evidence/20260912-guard-pulse-evidence.tgz`,
10,165,616 bytes / 873 regular members. SHA256:
`edeb1f02b37606f5e56ea4bc08d6907ee9e136abc94eeb2ce5e163522517972b`.
The adjacent receipt records per-member hashes, inventory, gzip CRC and
unchanged-source verification, including rejected harness evidence.

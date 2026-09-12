# Local fault views without abort echoes — DO NOT MERGE

**Functionally verified over the scoped tests; physically rejected.**
Do not promote this candidate or deploy it. It does not close FPGA timing.

FW/HDL branch: `codex/starlink-rx-only-do-not-merge-abort-echo`.
Git history includes the archived ownership-lock experiment, but the runtime
parent is the earlier retry-admission implementation. The rejected ownership
lock is NOT active: the original descriptor-lock register is retained.
All 43 retry-admission runtime files are unchanged; four selectable new files
(top, identity stage, descriptor ledger, completion adapter) bring the frozen
runtime inventory to 47.

## Exact implementation

The global abort was reaching completion through multiple nested copies of
the same fault. This experiment adds local-fault views while retaining every
original output and current fault/abort check:

- Identity stage: a local view includes its sticky fault, local bank/reset
  conditions and invalid controls, excluding only the separately supplied
  upstream global abort. Its original fault and sequential logic are unchanged.
- Descriptor ledger: a local view includes sticky fault, rejected pending
  commands and invalid controls, excluding its caller-supplied abort.
  Its original fault and sequential logic are unchanged.
- Completion adapter: its own scalar fault already includes the ledger abort.
  It combines that immediate veto with the ledger's local view, avoiding
  re-importing the same abort through the child fault reduction.
- Top: only the completion adapter consumes the stage's local bank-fault view.
  It still receives global abort directly. Original bank faults remain wired
  to guards, diagnostics and publication checks.

No additional register, buffering, arithmetic, clock cycle or publication delay
is introduced. Exact source transformations constrain every runtime edit.
The original completion adapter runs alongside the candidate in the actual
FFT bench, receiving the original full bank-fault signal. Comparisons cover
18 outputs and 31 internal fields before and after every fast edge. This
includes ledger state and immediate scalar-fault behavior, not just final data.

## Verified results

**2,360 scoped tests pass**, 153.439 s: 132 inherited modules and one new
30-case module. This is not the entire repository suite.

New tests cover:
- Exact changes to all four runtime modules.
- 4,096 four-state stage-fault absorption vectors.
- 16,384 four-state ledger-fault absorption vectors. The parent sticky fault
  is known after coordinated reset; its scalar fault is a case-inequality
  reduction and therefore known. The test states this contract explicitly.
- Mutants dropping a sticky or intrinsic fault are rejected in both views.
- Original/candidate full mailbox-state equivalence through real dual-clock
  RAM, allocation, completion, backpressure, abort, reset and fresh recovery.
- Missing, duplicated, weak and vacuous result witnesses are rejected.

Healthy actual FFT: **64,512 numerical words exact**, **4,178 clocks**,
177,096 complete mailbox comparisons and 18 completions. No healthy fault-view
difference and no added latency. The short-service ceiling remains 5,215 clocks.

All **92 actual FFT fault/reset/stall cases pass**, 355.950 s.
The original mailbox remains identical across 1,841,886 checks, with
129 completions, **102 removed abort echoes** and 11,930 quarantine checks.
All 316 admissions still match the original certificate. The inherited
28 delayed guard-fault observations remain covered. Main, auxiliary and
synthesis profiles use the same 47 runtime files.

Numerical CSV SHA256:
`df33d4b05c4ae65191af85f9e6748a484773d0a659051a5fad7112b8a717d8c8`.

These are actual FFT/buffer simulations, not continuous-RX, DMA/IIO or RF proof.

## Physical result — not promoted

Same frozen 100/175 MHz OOC route, no added timing exceptions:

| Metric | Retry-admission parent | Local fault views |
| --- | ---: | ---: |
| Worst setup | -1.269 ns | -1.309 ns |
| Same-175 MHz worst | -1.001 ns | -1.309 ns |
| Total negative slack | -295.708 ns | -488.882 ns |
| Failing endpoints | 811 | 971 |
| LUT / FF | 2,739 / 5,920 | 2,740 / 5,912 |
| RAMB18 / DSP | 16 / 21 | 16 / 21 |
| Short service | 4,178 clocks | 4,178 clocks |

8,547 nets fully routed, zero routing errors. Hold +0.014 ns; pulse +1.830 ns.
114 inputs and 124 outputs remain unqualified. No physical/receiver signoff.

The worst path now begins at the fast-reset-release register and passes
through the high-fanout running signal, ledger fault/readiness, completed-input
fault and forward final commit into the guard's ACK-wait register:
eight logic levels, 7.016 ns data delay, about 77% routing.
This is a same-clock failure, independent of the unqualified metadata crossings.
The reset-release dependency is not waived.

The same endpoint probe was rerun on both pinned routed checkpoints:

| Endpoint | Parent | Local fault views |
| --- | ---: | ---: |
| Guard reasons | -0.669 ns | -1.035 ns |
| Admission snapshot valid | +0.009 ns | -0.536 ns |
| Admission snapshot good D | -0.697 ns | -1.035 ns |
| Guard active | -0.908 ns | -1.202 ns |
| Admission consumed | -0.040 ns | -0.585 ns |
| Global registered fault | +0.320 ns | +1.174 ns |

All 16 original diagnostic pins and 35 snapshot-data pins are present.
Other candidate endpoints: forward-position CE -1.045 ns, kernel-next CE
-0.300 ns, output occupancy -0.067 ns, output publication -1.058 ns,
product publication -1.287 ns. Removing duplicate abort logic did not
produce an aggregate timing improvement.

## Next implementation: reuse the existing registered completion pulse

Do not stack this rejected candidate. Select an explicit retry-admission or
lean runtime parent. Stop treating another combinational fault regrouping
as the main path to closure.

The guard already registers the fully checked final handshake in
`commit_pulse`. Prototype retiming its private active/ACK storage from that
existing receipt instead of driving all storage directly from the long
same-cycle final-commit expression. Preserve visible effective occupancy on
the original edge using the pulse:

- Effective active storage is masked while the completion pulse is **known 1**.
- Effective ACK wait includes a completion pulse that is **known 1**.
- Private active storage clears from the pulse on the following edge.
- Private ACK storage takes the pulse, but a same-edge legal ACK clear must
  take priority. This covers a destination that acknowledges during the pulse.
- Use case equality for the known-pulse view. An X completion pulse must not
  retire state: the original procedural `if (final_commit)` would not do so.
- All original current completion/publication predicates, guard reason
  accumulation, diagnostics, expiry, reset and admission fences stay intact.

This is a testable design proposal, NOT implemented or proved in this
checkpoint. First compare every visible guard output and effective occupancy
against the original, including X/Z faults, coincident status/final beats,
immediate/delayed ACK, both reset inputs and fresh recovery. Verify the two
private storage changes cannot create any output, reuse or job-start permission.
Then run the actual FFT/buffers, preserve the service ceiling, route early and
compare all endpoint groups. No additional full-payload bank is required.

If this does not shorten the actual routed completion path, evaluate an
explicit registered final-qualification boundary with a measured cycle budget,
rather than accumulating smaller algebraic changes.

## Full deployment gates remain open

Preserve native 60 MS/s fine search, independent 2.5 MS/s CI16 IIO inspection,
causal acquisition/CFO/fine processing, eight high/low targets with 120 ms valid
dwells over 300 s, and independent host GLRT comparison.

After subsystem closure: actual-board-clock full receiver route and CDC/reset
qualification, continuous native/inspection DMA and Ethernet, actual 60 MS/s
RX calibration, serial-verified .18 canary, reversible pinned Ethernet PPU
deployment to .17, real reception/replay comparison and clean stop/restart.
The 200 MHz IDELAY reference is not lowered or waived.

No radio, PPU or main branch was changed. PRIMARY HDL remains
`0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.
.18 canary serial: `1040007c4a94000211000b009186843ef2`.
.17 outdoor Ethernet-only LNB RX1 serial:
`104000bac4950008230026001b440a003a`.
.14/.20/.21 remain excluded.

## Reproducibility

Artifacts: `/srv/bulk/leo/starlink-pss-preflight.RVtFMZII/abort-echo-artifacts.v8kAemUZ`.

Main/synthesis pin:
`de16680339cc5fcbddd421ec7f788a5bda61bf4c64978f444dea7e8f5211c6ed`.
Auxiliary pin:
`1580a93d469b7ba7ca2ba8fd08a8c0920f86fabe6e9e6e87ff553c195d1f2955`.
Synthesis DCP:
`100416cf9ef8e25b05d5572d9af032b8b763760588fc668ae07395d4310cd444`.
Routed DCP:
`6d4e2f114d2272f321d62e07841786727e74bfdc819b27d8cf2910e0d23f7ff6`.

Verified archive: `reports/evidence/20260912-abort-echo-evidence.tgz`,
8,903,939 bytes / 458 regular members. SHA256:
`b2378bd0f536ae1b39b2eb35a095f2ed01d9da20d373a43a47ec60a30f2eb54b`.
Recorder rechecks original-mailbox and admission witnesses, numerical results,
frozen sources, matching runtime inventories, final regression source hashes/
XML, route/probe inputs and DCPs. The adjacent receipt records per-member SHA256,
inventory, gzip CRC and unchanged-source verification.

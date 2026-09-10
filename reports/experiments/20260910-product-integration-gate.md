# Product integration: real-controller review and READY counterexamples

Parent reviewed the complete frozen P1 controller and the160-line proposed
P1-only integration design. The next authorized implementation is ADDITIVE
primitive interface variants and offline tests, not a top replacement, new
vendor run or route. Existing848-qualified sources/tests, canonical d9c sealed
bank and P1 remain unchanged.

## Real-controller obligations

The existing controller distinguishes discovery, preflight, actual admission,
core configuration/input enable, result completion and delayed ACK draining.
Its requirements cannot be met by simply replacing the old bank's ports:

- Forward admission needs reusable capacity before a producer reference exists;
  active product READY is correctly false at that point.
- Inverse discovery/VERIFY/ARM need a checked first word without popping it;
  core VALID correctly remains false until the inverse consumer is enabled.
- The actual forward guard's ACK-clearing event must produce a retained,
  health-qualified receipt that survives until scheduler consumption after
  result busy clears. A one-clock handoff pulse is insufficient.
- Independent expected70-bit descriptor and forward-admitted two-bit lease
  must bind the checked head before inverse admission; an alias comparison or
  the old one-bit consume generation is not equivalent evidence.
- Full downstream delivery fault cannot feed back combinationally into core
  VALID. Keep full current/global/result faults and independent raw causes,
  same-token verdicts and duplicate-start checks at appropriate boundaries.
- A new late raw output/status/frame/input event after qualified forward
  closure must still immediately veto publication/ACK. Waiting for sticky
  result_fault alone is insufficient.
- A paused slow clock requires a fresh common-epoch purge receipt before BOTH
  source-reader release and source-fault sampling. Reset synchronizers alone
  do not establish that the slow writer observed reset.

The primitive extension will expose checked head, retained handoff, immutable
descriptor/lease and narrow current evidence. It must preserve all75 raw
offered-word checks, including stalled observations, and default-old source
restoration. The independent FFT agent is auditing ACK/current-fault and
descriptor/lease obligations in parallel; its review is not yet complete.

## Independently executed missing actual-READY seam

Parent created a separate copied testbench against frozen v1:
adapter SHA `054cccffabc661a90b2c8a20d63675db4ce64aa271bb09836b207691369f6fbd`,
reader SHA `30c8cb1dee84c2ebc4289cf101e85572d9655621db6075957557bab445251074`.
Only the copy receives a new stable-before-edge force of the actual exposed
`dut.product_ready` to0 when position37 or511 is offered. Real unchanged guard,
spectrum arithmetic, adapter and bank remain in the fixture.

Both cases exit1 with `PRODUCT_LOGICAL_TAKE_DIVERGED`: the external arithmetic
handshake is stopped, but the bank reconstructs private readiness and still
accepts the word. Parent probe exits0 only after confirming both expected
counterexamples and unchanged source hashes. This is an integration-boundary
gap under the existing real-top READY fault-injection requirement, not a claim
that the original848 fixture failed under its original connections.

The interface fix must bind arithmetic retirement and private bank acceptance
to the SAME actual sampled READY. Simply qualifying bank input_valid with READY
would also hide raw closed/unknown offers. Preserve an independent ungated raw
observer and test READY-low closed/X/Z offers; execute a missing-observer mutant
as well as missing-actual-READY qualification. No raw diagnostic may silently
disappear as a consequence of the fix.

All old848 tests must still pass. Extended tests must cover these exact READY
witnesses, checked head before RUN, stable head through stalls, retained ACK,
independent descriptor/lease/phase binding, missing receipts and current verdict
at handoff/release. Require source/control graph and logical-state accounting
before top integration. Keep original actual FFT vectors, READY/status faults
and5215-cycle/29.8us service limits for later controller evaluation.

Parent counterexample archive `20260910-product-ready-parent.tgz`:86,783 bytes,
SHA `5165db0343c8565e381646519c8c57dc45460a3e588f328aac6133e1b9363b4f`.
It contains the probe, complete copied fixture, compile/run receipts and both
failing logs. Recovery `product-ready-parent.qnxeGgeA`; tar comparison exited0.

## Parallel progress and preserved evidence

Parent independently verifies immutable Git bytes for clean actual archive
at FW `27ca617027c7ffb0ce19998d75e048f26b92f334`: all four parts and210 safe
regular members. The recorded-history archive at FW
`3df5cd42414a0b18d848f48281caedf727dfe457` has all26 safe regular members
verified; its external WDB reference resolves to the exact member/hash of the
verified actual archive. Nothing was extracted or executed. Owner reports
both commits pushed and remote-verified on its existing DNM branch.
Parent verifier/receipt archive `20260910-inverse-portable-parent.tgz`:1871 bytes,
SHA `5ba9c637fdc9217b8ab1dc4a99f0b8a3139303dd996cedd037541e80ba4ebf16`;
tar comparison exited0.

The separate retained-output prototype is implementing two guard contexts,
fresh epoch purge and explicit core reset/config cutover. Its preliminary
declared control addition is223 bits (extra guard180 + owner17 + cutover17 +
barrier9), above the original illustration; whole-source and mapped costs
remain pending. The modeled eight-cycle dispatch remains unmeasured. This is
not an approved union with the product adapter.

No radio/PPU/main/production-gitlink/clock/threshold change. The last P1 route
still fails WNS-1.492ns. Full receiver timing/CDC/IO, actual60 RX calibration,
causal native fine with canonical15 coarse acquisition, independent2.5 MS/s
IIO, eight-target120ms/300s scanning, `.18` canary and `.17` Ethernet/RF
deployment remain the completion requirements.

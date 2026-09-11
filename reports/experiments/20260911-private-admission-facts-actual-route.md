# Private admission facts: local path removed, subsystem setup still fails

DO NOT MERGE or deploy. Branch (FW/HDL):
`codex/starlink-rx-only-do-not-merge-private-admission-facts`.
FW `be1292429`, HDL `36ae980a0`.

The 36-bit admission snapshot now has opt-in private payload capture independent
of reset/request/quarantine clearing. Original validity, consumption and permit
logic are unchanged; invalid payload cannot authorize a job. Default callers,
including the completion certificate, retain original behavior. Two runtime
files change; all other compiled modules remain exact. No added RTL latency.

## Verified behavior

- **745 regression tests pass in 87.77 s**, including 14 new component/source
  tests. Default/private modes at four widths each perform 12224 checks with
  four-state controls/data. Four unsafe variants are rejected.
- Nine new actual-evidence tests pass, plus seven overlapping archive tests:
  **754 distinct regression/new-evidence tests**, not counting rerun subsets.
- Both actual FFT campaigns pass (209.09 s main / 141.15 s auxiliary). All
  **64512 numerical records and CSV bytes match the parent**. Service remains
  3663/3663/4929/11729/3663/3663 clocks.
- Main witness: 500645 checks, 266 valid/owned observations, 500193 invalid
  payload differences. Auxiliary: 334066 / 125 / 333816. Permit/control and
  valid payload match a default-mode reference; invalid differences are private.
  All inherited fault/reset/ACK/publication/recovery cases remain passing.
- Historical source comparisons and mutation selectors required test-only
  maintenance. Failed initial diagnostics are retained; the complete final
  regression passes. Runtime/bench were frozen throughout actual runs.

## Physical result and decision

Unchanged 100/175 MHz OOC route completes in 55.72 s. The old reset source has
no path to the private snapshot bit-zero reset pin; its data path is +0.271 ns.
Inspection finds 35 surviving payload registers with only local validity and
consumption startpoints on CE. Smaller validity/consumption paths remain
−0.288 / −0.293 ns. An initial stale-name inspection was corrected for Vivado's
generated-block naming; checkpoint and constraints never changed.

**Whole subsystem: WNS −1.661 ns / TNS −474.560 ns / 944 failing endpoints.**
Parent: −1.560 ns / −479.076 ns / 837. Worst slack and endpoint count regress,
so this is not promoted as a timing improvement.

New worst path runs from the actual FFT status FIFO bit zero through shared
fault logic to `output_bank/request_toggle_reg/D`: nine logic levels, 7.372 ns
data delay, including 5.800 ns routing. Next map that predicate by ownership
and phase, separating private bookkeeping from genuine current publication
vetoes. Prove any partition before changing authorization. More isolated
register edits have not demonstrated overall closure; no features added yet.

8473 nets route without errors; hold/pulse pass. 2819 LUTs, 5804 registers,
21 DSPs, 15 RAMB18s. Reset CDC structure remains qualified at the prior scope:
nine CDC-3 info, 208 CDC-15 bundled-data warnings, no CDC-1/CDC-10 critical.
114 inputs / 124 outputs remain unconstrained in OOC. No board-level signoff.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection remain
required. Full receiver timing/CDC/reset, board clocks, actual 60 MS/s RX
calibration and sustained IIO/Ethernet still precede reversible `.18` canary
and `.17` PPU Ethernet-only deployment with rollback, 120 ms valid dwells,
300 s scans and blind host GLRT. No radio, PPU/main or primary HDL changes.

## Evidence

[Archive](20260911-private-admission-facts-evidence.tgz),
[readback receipt](20260911-private-admission-facts-evidence.json):
39920423 bytes / 11756 verified members, SHA256
`99a5425acd2edfb9034502336ed6c5796df0ff45de219741d3f6bbcb0ccc9880`.
Includes pinned sources, actual logs/CSV, checkpoints, inspections, tests and
retained failed diagnostics. No raw local evidence was deleted.

Prepared: `e589b35765220ac3784105df0c96f38f40a1e276a746c79767bc7c57600ff203`.
Routed DCP: `456b3dbb87310f1c68a0188f4568d72552091b8b7e86b9ec81e52a90c7254d1e`.
Parent: [completion receipt route](20260911-completion-mailbox-stage-actual-route.md).

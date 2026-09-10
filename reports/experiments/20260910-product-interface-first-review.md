# First additive interface snapshot: behavior PASS, structural gate FAIL

Parent independently compiled the frozen first interface snapshot and repeated
all20 behavioral cases, all PASS. This does not include the owner's three
source-inverse tests, unfinished full fault matrix or actual controller/vendor
qualification. The complete connectivity audit still finds a feedback path,
so no top integration or physical trial is approved.

Frozen issuer
`65ddceaceb9a3242ce06c83c55cd168647571f02257119206932043e7186c7aa`,
reader `bffc0b294dca53c89f8d98250d497eba844f3df7a6a767cf6ef5b36355d38130`,
fixture `91f7bf1ba3e53f5d6a9f614eb42ff1c3bca6c42824f33dcdef62e5149a22dfd7`,
case include `1f299e6d98c2acbeead8892a09604f6c6af6f63838b7e98bd78a6589ac61db0c`.
All nine compiled source hashes are externally pinned in the parent replay;
original and copied files are unchanged after execution. Canonical d9c,
guards and spectrum arithmetic remain the old exact files.

## Demonstrated interface behavior

- Actual exposed READY-low at interior37 stops both sampled transfers and
  leads to expected quarantine without publication/handoff.
- READY-low at final511 holds four clocks, then completes all512 transfers
  and actual lease release after READY resumes.
- Closed new, X and Z offers remain visible while READY is low and trigger
  immediate publication/handoff veto plus retained reasons.
- Checked head is visible before RUN without a pop; removing GOOD hides it.
- Head/admission exports have distinct register sources. This is NOT proof
  of the future controller's independent lease/descriptor binder.
- Handoff receipt persists after the actual guard ACK and is immediately
  hidden on each of eight current fault causes; wrong-phase handoff is blocked.
- Eight healthy leases retain512 exact products each.

## Remaining structural backedge

Parent applied the reviewed complete-node parser to its independently compiled
netlist, SHA `20912467b094871907c2b00db192a012d43a05fce329ca5879ee6cdaaffe2044`.
All3246 nodes, including36LS concatenation nodes, are traversed. It finds:

`invalid_admission -> issuer_current -> bank_live -> bank.output_valid ->
reader.closed_offer -> queue_validation_fault -> direct_clean -> handoff_valid
-> destination_ready -> job_ready -> forward_job_accept -> invalid_admission`.

The new fixture removed the old full guard.fault_now feedback, but that alone
does not remove acceptance-derived backedges. The implementation owner has the
complete source-alias path and is separating these dependencies. Do not hide
current raw events or simply discard duplicate/invalid publication witnesses
to make a graph green. The first20PASS/structuralFAIL snapshot remains intact.

Archive `20260910-product-interface-parent-v1.tgz`:90,718 bytes, SHA
`3954218af445fc2a0278818e5df0808d07d3bd3069b3d9c9a27c7d5358c6667f`.
Contains fresh compiled sources/netlist, all20 run receipts/logs, replay and
complete graph audit/result. Tar comparison exited0. Recovery:
`product-interface-parent.bGlYti6z` under the persistent20260910 root.

Parallel retained-output composition reports17 initial scripted cases passing,
including nominal8-clock dispatch/3645 recurrence and parked-reader4911–4912
recurrence that waits for actual ACK. Parent has not repeated that snapshot;
full guard/fault/graph qualification remains pending, with no vendor run.
The independent graph-scope audit reports that final inverse-sealed proofs
already used the correctedLS-aware parser; its earlier defective attempt was
recorded FAIL before final qualification. No blanket numerical invalidation.

No radio/PPU/production/main/clock/threshold changes. Full receiver timing,
actual60 calibration, canonical15 coarse/native fine and pilot2.5 IIO,
120ms/300s scanner and `.18` then `.17` deployment remain required.

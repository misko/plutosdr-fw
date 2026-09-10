# Exact111 physical preparation — offline only

43 tests pass in 82.78 seconds, original handle 96286, exit 0. No synthesis,
route, radio or runtime change. Tested FW `b0b43802603c18472c65c159a36424785441af1a`
and HDL `26cc65a7f473ba3f528c90524df35ff0b25b7466` freeze two new helpers
and their tests. All seven runtime sources remain the passing ae50 design.

Prepared input: `/tmp/starlink-completed-input.5EaJuD/exact-control-physical-prepared-v1`.
Its 18-file SHA256SUMS identity is
`99862b8d88414de6b2b4171df2a1a61bf5849ef2effed3c875de9904c366f158`.
Preparation handle 27436 exited 0. No project exists in this freeze.

Admission replays the original frozen actual receipt verifier and independent
qualified-status accounting, checks original exit 0 and complete before/after
inventories, and verifies both historical main CSVs and matching nonempty extra
CSVs. It admits only the passed R1/D1/S1/extras1/175/QUICK0 inventory
`8e9251fe06e41917e9e0b5ebceef36db444bc39770efe7acb940dbfcc4ed7906`.
That actual result remains **qualified-status**, not raw217 equivalence:
1,246,258 = 953,795 raw-equal + 292,463 invalid-status-only observations.

The generated synthesis adapter explicitly binds all three candidate knobs to 1.
A literal whole-body inverse restores the original synthesis Tcl. Only input
admission/layout, parameter forwarding/readback and integrity/provenance receipts
change. Part xc7z010clg400-1, source100/island175 resource XDC, generated FFT IP
factory, AreaOptimized_high/OOC directives, control-set threshold 4 and two-thread
limits remain unchanged. Route Tcl is copied byte-for-byte, with no invocation.
The source closure is seven RTL files plus kernel memory, IP factory, XDC and
thread Tcl; the synthesis copy additionally contains the exact adapted Tcl.

Both Tcl Python children use explicit Python -B with PYTHONHOME, PYTHONPATH and
LD_LIBRARY_PATH removed only from their child environment. A poisoned-parent
Tcl mock exercises both audits and reaches only the create_project trap, proving
the parent's three values stay unchanged. No Vivado executes in these tests.

The separate one-shot external synthesis owner records before/after inventories
and audit outcomes even for launch exceptions, nonzero tool exit or copied-source
corruption. It never retries. Raw process return code is separate from verified
completion: exit 0 alone fails without exactly one original terminal marker,
all eight nonempty DCP/resource/report products, a zero-black-box receipt and
the complete matching copied-source closure. Stubbed pre-Tcl exit 0, missing or
duplicate marker, missing DCP, empty resource receipt and nonzero black boxes
are rejected. Mock files are not physical evidence.

Retained attempts: v1 21 PASS/19.73s (12653), v2 26 PASS/29.12s (13966),
v3 30 PASS/37.63s (2751), v4 37 PASS/59.71s (24681), v5 43 PASS/82.78s
(96286); every original handle exited 0. Earlier versions lacked later reviewed
environment/completion gates and are not the final acceptance contract. Ruff is
clean after correcting authoring-time formatting/exception-lint findings.

Compact archive: `hdl/library/starlink_pss_acquisition/evidence/exact-control-physical-offline-v1/`.
It contains final prepared inputs, all prior changed-source snapshots/test logs,
final mocked audit receipts and tests. Large test-copy CSVs and prior unrelated
projects remain local and are not duplicated. The actual-evidence dependency is
the already archived passing combined run; its live absolute path is intentional.

Next action requires source-specific authorization: one synthesis using the
frozen external owner command in the archive README. A subsequent route requires
successful matched-DCP, actual-clock, parameter and zero-black-box review. No
achieved timing, area saving, CDC/IO qualification or replacement eligibility is
claimed by preparation. Existing physical negatives remain unchanged.

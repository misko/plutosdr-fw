# Producer-final fence actual preparation — offline only

Prepared and tested, **not executed with the vendor FFT**. Runtime remains the
separately reviewed default-off producer fence. No new cycles, banks, arithmetic,
reset changes, physical runs, or inverse sealed-bank composition are included.

## Pins and exact proposed selection

Tested FW `e2abf283b08e73c439bade8b5df5335aeb9410f5`, HDL
`eb20e3940e69d28c7d26d05877e3006549da86c0`.

Prepared directory:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/product-final-actual-prepared-v1`

- 65-file inventory SHA256: `7adf2efa0a242b89ccfbb387b00210e76841ba544cbae4cef97efc861acf59b2`.
- Frozen runner: `2d3b5008f0d087614000ae518421cd9d800aadeb98a747f47fce01d8e76cc6e3`.
- Preparation helper: `39141329e600b15c2ff9357d952d3cd148d6db3126fff2c394108073db49b853`.
- Observer: `632273d1d31829964a2197d1cb967dbceb9ee72ac77cda213c172fb7d9ba1087`.
- Binding: `4b04032bb8eda1d597cc03b972c02839880caf4b28bf70de2176dda43fca3211`.

Explicit R/D/S/C/K/M/P=1, extras=1, FAST_MHZ=175, QUICK_MUTATION=0. Option P=0
is separately admitted/elaborated offline, not proposed as another vendor run.
The proposed future initial execution is one P=1 run after source-specific
approval. Expected duration is roughly the previous 617-second actual run plus
the small observer overhead; this estimate is not a measured runtime.

## Source and numerical continuity

The input is the successful original 10102 K1/M1 actual at
`rom-relocated-actual-v2.CWJkzwEi/rom-actual-prepared-v1` under the same recovery
parent. Its complete 56-file inventory is fixed to `6f5eddb9…`. Admission requires
the four nonempty zero owner statuses, exact stored before/after inventory and
runner identities, original full source verification, old frozen result gates,
and both complete main and extra CSV pairs. Original 23845 quota failure remains
unchanged and is not treated as passing evidence.

Only top module substitution, explicit P parameter/forwarding, additive observer
include/terminal call, and matching runner admission/receipt entries change.
Whole bench and runner edits invert to the complete accepted bytes. Every other
inherited source, helper, vector, reference, and observer is hash-bound to the
original 56-file inventory, not merely rehashable new metadata. Both additive
runtime modules also invert completely to their old source. All seven previous
runtime modules and old K1/M1 variants remain literal.

The independently driven internal reference remains **dec20 R1/D0/S0**, not the
new candidate. Main CSV SHA256 remains
`25ab9d06ca0e03f280540cda625a7826b3c4cbaa6322ce3266c59e1fbad94122` for both files;
extra CSV SHA256 remains
`b965d12603a64111fa9c6ea36cb0f12189945ad4d9be7cf4fbd883980c4ec4a0` for both files.
No new expected data, latency, stimulus, or old fatal was substituted.

## Existing observation inventory and force seam

The raw 217 fields remain literal. The qualified-status observer compares the
other 216 fields unconditionally. Only all eight `core_status_data` bits may
differ when **both** status-valid bits are exactly zero; the valids themselves
remain exact. There is no product-bank or inactive guard-data exception here.
The original valid/reserved-bit checks and status accounting stay unchanged.

The product mailbox contributes these 18 unconditional fields:
`request_toggle`, `acknowledge_toggle`, `request_sync`, `acknowledge_sync`,
`metadata_in_hold`, `metadata_out_hold`, `write_position`, `reading`,
`read_all_loaded`, `read_address`, `read_output_position`, `read_payload`,
`read_valid`, `input_ready`, `input_fault`, `input_framing_fault_now`,
`output_valid`, and `output_ready`. Nine additional wrapper fields are
`product_bank_{valid,read_ready,data,position,last,metadata,ready,fault,framing_fault_now}`.
`product_commit_authorized`, controller state, and all old global reasons are
also unconditional. This is public/state trace coverage, not a claim that the
217-field observer directly compares all 512 unobserved RAM cells; the separate
fast paired-mailbox proof compares those cells.

Old stimulus deliberately forces product-bank ready/valid/metadata/position/last
aliases. An extra input-only mailbox instance would not inherit these output
forces. Therefore no such instance, force mirroring, or observation mask was
added. The original independently driven complete reference already applies
the same old stimulus and compares all listed state/output fields.

## New sampled contract and limits

The added observer receives actual mailbox/controller/guard signals only. At
posedge it settles active propagation with `#0`, then reproduces the original
mailbox's nested procedural branch. Unknown framing takes the same else branch;
unknown running likewise does not take the known-low reset branch. Every
actually evaluated final authorization is compared with the old full predicate,
before any phase condition. Forced, unqualified, and unknown states do not skip
that comparison. The predicted old request-toggle transition is checked at
`+1 ps`, with no DUT drive, stall, or timing change.

Natural ownership uses the internal toggle/ack/read state, not deliberately
forced public ready/valid aliases. A qualified sampled final additionally requires
closed completed input, forward guard/controller phase, raw input fault equal to
duplicate-start fault, and no handoff fault. Public-alias overlaps are counted
separately and do not suppress any sampled or publication assertion. The unchanged
complete-reference comparison retains its original `+2 ps` schedule.

Terminal coverage is frozen before actual evaluation: nonzero pre/post checks
(equal), sampled/authorized/closed finals, reset samples, inverse-owned reads,
owned stalls, private-core reset samples, and at least two current-fault edges.
Sampled authorization must equal authorized+vetoed+unknown counts. Vetoed final,
malformed final, unknown final, nonsampled private, and forced public-overlap
counts are always reported, even if zero; no claim that unchanged actual vectors
necessarily reach each of those local witness classes. The fast tests supply
the separate missing-veto and malformed/four-state evidence. Existing old extra
final-fault/ownership/reset gates remain additional mandatory gates.

This does not qualify the separately found paused-slow reset gap. Both existing
source reset behavior and all old reset stimulus remain unchanged.

## Executed offline evidence

Original 92567: **60 PASS in 26.99 s**, exit 0: 34 new preparation/observer tests
plus the unchanged 26 local-fence tests. Ruff PASS. New tests include complete
source inverses, explicit P0/P1 full harness Icarus elaboration only, rehashed
old/new helper/reference/vector/observer corruption, missing/duplicated/mismatched
bindings, failed/empty prior statuses, no-overwrite/symlink/closure failures,
exact receipt accounting, and CLI verification from `/`.

The standalone observer fixture executes all 1,024 four-state branch tuples:
36 sampled finals, 18 unknown authorizations. It is a literal mailbox-transition
fixture, **not real controller/FFT reachability proof**. Sampled/X-framing,
ownership, phase, and publication mismatches each trigger the precise assertion;
removing that assertion escapes and is rejected by the unchanged required-fatal
acceptance check. An unqualified final cannot hide an authorization difference.

Initial 50014 (22 PASS / 7 FAIL, 2.40 s) is preserved: seven standalone fixtures
failed elaboration because wildcard counter outputs lacked identifiers. Explicit
open output ports fixed only that fixture. Corrected 81647 passed 29 tests in
2.36 s; additive provenance negatives and the prior 26 tests produced final 60.

Portable archive:
`hdl/library/starlink_pss_acquisition/evidence/producer-final-actual-preparation-v1/`.
Its tar inventory records every regular member hash and preserved local symlink
identity. The complete original failed attempts and prepared source bundle are
included. No vendor project exists in the prepared directory.

## Proposed execution boundary — not authorized or launched here

Use the frozen runner above with Vivado 2022.2, SuSE parent LD_LIBRARY_PATH,
non-/tmp TMPDIR, and log/journal options before `-tclargs`; it retains maxThreads2.
The unique future owner must first verify the exact external 65-file manifest
and absent project/log targets, then persist original exit plus pre/post source
receipts even on failure. After execution require all old runner gates and the
frozen new helper's `verify_result`, which composes the old ROM/CDC/exact/status
receipt validators with the new sampled-final receipt. No actual run, retry,
synthesis, route, radio, or promotion is authorized by this document.

The unique owner is now prepared offline at
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/product-final-actual-owner-v1/owner.sh`,
SHA256 `62e4fa75b645f200b9c6bbccc0a43cf6e7cda0c2f58d04245128f5da9b24cb68`.
`check_owner_inverse.py` verifies all eight literal path/pin/helper/scope
replacements restore the old `4c5db6e2…` owner after removing exactly the new
three-line stored-before/after snapshot assertion. Bash syntax passes. This
check does not execute the owner. Old failure audits, full CSV checks, unique
terminal marker, and generated-IP after-only inventory remain unchanged.

Proposed command, **only after separate launch approval**:

```
env -u PYTHONHOME -u PYTHONPATH TMPDIR=/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/product-final-actual-owner-v1/tmp bash /home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/product-final-actual-owner-v1/owner.sh
```

Root independently repeated final 60 tests: original 48393 exited 0, 60 PASS in
28.28 s, all five checked source hashes unchanged. The independent prepared CLI
and all 65 manifest entries also pass. These remain offline preparation results.

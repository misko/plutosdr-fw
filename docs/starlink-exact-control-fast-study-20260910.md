# Exact-control candidates: fast tests only, no physical eligibility

Two independent, default-off options are implemented and fast-tested:
`DISTRIBUTED_FAST_FAULT` and `PRIVATE_NEXT_START_SCRATCH`. Final focused
selection: **137 passed / four existing physical skips**. Expanded oracle
regression: **818 passed / ten existing physical skips / seven failures**,
all seven the previously known missing Linux-submodule files. No actual FFT,
synthesis, route, radio or receiver run was performed for this source.

Tested RTL: `ae50b1889fd10cd762fb60266aecbb7c163e1d1a`; final test-source FW:
`0200ef776055daf66821b870a7459c25d9ebe65d`. Baseline HDL:
`dec20d6371f2d77b6e09c4bcdda2f3d7f8715776`. The seven current RTL files
match every non-mutant focused freeze before/after testing. The source delta
is only wrapper, joiner parameter plumbing and ROM: 55 added/10 removed lines.
All other RTL, actual-core bench stimulus/assertions and kernel coefficients
are unchanged. Both options remain zero even when REGISTERED_SCHEDULING=1;
future opt-in requires explicit selection. All public parameter entries
reject −1, 2, X and Z using case inequality, independently of child checks.

## Exact changes and intended physical effects

The distributed ledger partitions every non-self term of the existing
`any_fast_fault` into 12 sticky bits, ordered low to high:
input_fault_now, input_guard_fault, source_fault_fast[1], vendor_fault_now,
kernel_fault, product_overflow, product_bank_fault,
product_bank_framing_fault_now, handoff_fault_now, result_fault,
output_bank_fault, preparation_fault_now.
Each bit uses the same fast_running reset and `else if (cause) set` semantics;
`fast_fault` is their OR. Consequently, after the identical reset,
OR(Q[next]) = OR(Q) OR any definitely asserted cause, exactly the old scalar
recurrence, including X/Z-only causes not satisfying a procedural `if`.
It does not register an existing reason OR one cycle later. Original raw
external/any-fast-fault expressions, detailed reason ledgers, publication
fences, controller, arithmetic, ownership and ACK logic remain literal.
Logical cost is 12 sticky FF instead of one plus a reduction; mapped area
and timing are unmeasured. The intended cut ends raw causes at local FFs
instead of a shared cross-stage OR before one D pin. The new registered-Q
reduction may still be a critical fan-out path; no closure claim is made.

Scratch mode changes only the existing 64-bit expected_next_block_start
write: it may compute input_block_start_index+447 when input_ready and
expected_bin_index==511, even on invalid or malformed input. All other ROM
state, checks, pulses, kernel payload/validity and accepts retain their exact
old writes. A healthy final acceptance rewrites the same value on the same
edge before index0 can consult it; a malformed final latches unchanged
quarantine. Occupied/stalled input holds the scratch value. Only values not
currently used by a checked next-block identity may differ. This adds no
logical FF, DSP or RAM; it aims to remove input_valid/current-fault and
protocol_error gating from those 64 CEs. There is no raw-private retirement
substitution, removal of identity checks or added arithmetic latency.

Neither candidate addresses the previous −1.868 ns BREG0 operand path or
−1.852 ns rounding/overflow path. The earlier −1.907 ns physical failure
remains immutable and unpromoted. Operand/rounding pipelines were not changed.

## Independent fast proof scopes

The new selection has **49 tests**, including the compatibility-only inverse.
It generates independent whole seven-module reference copies directly from
dec20d63, renaming module identifiers only. Candidate and reference never
share the new predicate, ledger or scratch logic.

Eight wrapper combinations cover both options and both scheduling modes.
Each compares **57,651 edges**, all 4,096 simultaneous current-cause masks
from reset, all masks again with scalar state already sticky, complements,
156 X/Z/known-one rows and both one-sided resets. Every step reapplies and
asserts the actual 12 forced constituent signals in both wrappers, then
compares raw fences, old/new scalar transitions, public outputs, controller
state, detailed reasons, commit/ACK and ownership signals. Wrapper→joiner→ROM
parameter propagation is checked by an invalid scratch-only observation.

These are **quiescent vendor-stub forced snapshots**, including deliberately
inconsistent cause combinations. They are not active FFT/state/phase-lifecycle
coverage or proof of global-fault-at-final token handling. No healthy input
assumption is used to make the scalar recurrence pass. Icarus warns that
procedural-force RHS is evaluated only on execution; explicit every-step
reapplication and applied-cause assertions address that limitation. Warnings
are retained, not suppressed.

Four standalone ROM combinations (scratch × balanced identity) compare
**70,890 transitions each**, all public outputs including invalid-cycle
kernel payload and every other state register. They cover **128** all-bit
corruption cases: each of 64 bits in malformed final metadata and each bit
in the next-block identity, plus **266** occupied-stall rows, bad final
ordinal/TLAST/exponent, invalid X/Z bubbles, reset/flush and healthy 447-step
wrap. There are **66 actual next-identity consumptions**, with pre-edge
scratch/equality checks even for malformed incoming words. Enabled mode
exhibits **658** allowed private scratch differences, default zero. These
are actual ROM transitions with hostile input, not merely assumed legal
snapshots; they are still not vendor FFT numerical proof.

All 12 omitted-cause mutants fail. Lost stickiness, wrong reset and bitwise-OR
X propagation fail; scratch overwrite-at-start, overwrite-during-stall,
bit63 truncation and wrong447 stride fail. Invalid parameter tests isolate
each public entry by keeping children valid. No expected mutation failure,
numeric tolerance or old assertion is relaxed.

## Retained failures and compatibility composition

Initial fast v1: **31 passed / one failed** (session36134). The not-sticky
mutant was rejected by an earlier uninitialized raw-fence mismatch rather
than the test's expected scalar-transition marker. Its full failing source,
log and original harness are retained. The revised mutant preserves unknown
startup and removes stickiness only once fast_running is definitely1; the
same expected scalar-mismatch witness then passes. No candidate RTL bug was
hidden. Intermediate v2 passes40; case-inequality/X/Z additions pass48 in v3.

The original prior-suite run (session50472) is retained as **83 passed /
four existing skips / five inverse failures**. Older payload, forward,
balanced, preflight and held-phase inverse chains did not strip the new
default-off options. Approved compatibility changes add only imports and
composition of the separately tested exact inverse. A new whole-Python-body
inverse restores all three changed prior files to FW01c89ea0 byte-for-byte:
all old expected bytes, golden pins, comparisons and mutation witnesses stay
literal. The five affected tests now pass as part of the137-pass selection.

Expanded regression's seven failures remain FileNotFoundError at Linux
gitlink `4357f41a721df9d89a66be7a2a3f921a71d46bad`: five map-driver tests,
the DMA geometry/backend test and the pilot lifecycle test. Exact IDs and
tracebacks are in regression.log. The ten explicit skips are four actual
input-cursor, two metadata-tree, two phase-mode and two occupancy physical
measurements. No submodule was initialized or skip reason changed. Ruff and
handwritten-source diff checks pass.

## Evidence and next gate

Original processes, all terminal and collected: smoke11030 exit0 (3 passes),
initial36134 exit1, intermediate78251 exit0 (40), final90982 exit0 (48),
prior50472 exit1, focused34865 exit0 (137/4), expanded63619 exit1
(818/10/7,180.33 seconds). All run directories/logs are under
`/tmp/starlink-completed-input.5EaJuD/exact-control-*`.

Archive `hdl/library/starlink_pss_acquisition/evidence/exact-control-fast-v1/`
contains the exact RTL diff, source hashes, common frozen candidate/reference
sources, all new test/inverse dependencies, per-case compile/simulation logs
and source inventories, each mutant source delta, both preserved failures
and final regression logs. The31 raw transition CSVs are losslessly gzip
compressed; decompressed bytes match uncompressed_trace_hashes.txt. Per-case
source files omitted as duplicates are the byte-identical common files in
frozen_sources, verified against input_sources.sha256. SHA256SUMS covers the
archive. Original uncompressed runs remain in their unique temporary paths.

Stop for source/report review. Active actual-core shadow coverage with the
unchanged healthy/fault vectors is a later gate, followed only if explicitly
authorized by physical measurement. This package establishes neither a
timing pass nor receiver, normalization, pilot-export, board-I/O or RF fitness.
No actual FFT, synthesis/route, radio, PPU, production BD, main, push or
promotion action was taken.

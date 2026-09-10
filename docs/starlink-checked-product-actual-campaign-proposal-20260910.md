# Checked product: proposed actual-core campaign, not an execution approval

Next step is bounded OFFLINE preparation, then review of one proposed enabled
vendor run. No new runtime edit, actual run, synthesis, route, inverse-bank union,
retained-output scheduling union or radio action is included in this proposal.
The actor result is functional integration evidence, not FFT qualification.

## Frozen sources and reusable baseline

Candidate runtime is exactly the five additive modules tested at FW
`ed1d85745779e2ac9d324efdb6ed2618569edd76` / HDL
`65cff8a983b2fd8489634939c363f2de230fc512`, plus their unchanged dependencies:

- `starlink_pss_fft_bank_owned_checked_product.v` (`56f341f0...`),
  `starlink_pss_realtime_checked_product_input_guard.v` (`7e0b6e67...`),
  `starlink_pss_realtime_result_guard_observe.v` (`b052874e...`),
  `starlink_pss_product_sealed_observe.v` (`38632315...`),
  `starlink_pss_checked_product_read_observe.v` (`222d0993...`).
- Unchanged publication bank (`76d6985a...`), canonical source/output mailbox,
  P1 product mailbox, join/ROM/product arithmetic, canonical P1 top/input/result
  guards for inverse/reference closure: the exact14-module list in
  `tests/starlink_oracle/test_checked_product_top.py:20`.
- Explicit `CHECKED_PRODUCT_BANK=1` and R/D/S/C/K/M/P=1111111; extras1,
  FAST_MHZ175, QUICK_MUTATION0. The control actor is EXCLUDED from the vendor
  compilation; the real generated entity has the same name as its replacement.

The actual baseline remains original50316, not a newly reconstructed expected
run: persistent `product-final-actual-prepared-v1` / `product-final-actual-owner-v1`
under `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
Its65-file manifest is
`7adf2efa0a242b89ccfbb387b00210e76841ba544cbae4cef97efc861acf59b2`;
runner `2d3b5008f0d087614000ae518421cd9d800aadeb98a747f47fce01d8e76cc6e3`;
one-shot owner `62e4fa75b645f200b9c6bbccc0a43cf6e7cda0c2f58d04245128f5da9b24cb68`.
Source-specific admission must recheck this entire inherited inventory, not
only a rehashable new metadata map. No source may be fetched from current main.

Reuse the exact factory `create_shared_realtime_xfft_ip.tcl`, SHA256
`0795ea7e6aa981d78080ac22fa4ba6355da59d6829ceb409dda07a54f7f9420d`:
Vivado2022.2, xc7z010clg400-1, XFFT9.1, realtime512,18-bit fixed/BFP,
16-bit twiddle, convergent rounding, natural order, one channel, block RAM,
DSP multipliers, runtime forward/inverse configuration. Preserve its complete
generated generic/entity checks, including absent output/status READY ports.
The factory's200MHz IP target is an unchanged generation parameter, NOT a
change to the actual100/175MHz clocks (slow initial phase1.3ns). Two tool threads.

All seven vector/memory files remain byte-exact members of the baseline:
`samples_ci16.mem`, `forward_q17.mem`, `product_q17.mem`, `inverse_q17.mem`,
`forward_exponents.mem`, `inverse_exponents.mem`, `upper_edge_pss_kernel_q17.mem`.
Do not generate replacement FFT answers from the actor.

## Two proof scopes; the old runner cannot be called unchanged

The baseline bench is `frozen_sources/tb_starlink_pss_fft_bank_owned_slice.sv`.
Its original217-field comparison and complete24-column CSV contain private
state, lease width, product mailbox toggle/cursor data and absolute clock
positions. Enabled staged ownership deliberately changes these; the old P1
sampled-final monitor also names a mailbox branch that no longer exists.
Calling that old runner with a renamed top would therefore be invalid.

1. **Disabled compatibility, offline first.** Whole-source inverse restores
   original P1 and all inherited bench bodies. A literal hierarchy-only mapping
   can reach `original_product_bank.product_bank` in mode0. Keep old217/216,
   qualified-status accounting, old sampled-final monitor, all old assertions
   and historical CSV requirements intact in this branch. Current actor proof
   already compares194 runtime fields unconditionally; vendor mode0 is not
   automatically required or authorized solely to repeat that evidence.
2. **Enabled changed-latency contract.** Add a separately named bench/observer
   branch with an explicit list of replaced comparison blocks and whole-body
   restoration. Do NOT describe this as raw217 PASS, old216 equality, unchanged
   CSV, or the old sampled-final fence PASS. Keep original reference sources,
   historical full CSVs and all old failures immutable; use the passed baseline
   as history, not a retimed fake live reference. The first proposed vendor run
   needs only the candidate FFT; local old guard/ROM/arithmetic shadows do not
   need a second FFT. Whether a later mode0 vendor control is useful is a
   separate decision after preparation review, not an automatic second run.

Retain input-port-fed frozen ROM and arithmetic shadows without invalid
coefficient masks; construct the unchanged old result-guard shadow from the
candidate's ACTUAL input ports/ACK capacity, not reconstructed old mailbox
timing. Keep exact current/sticky reason recurrences, full raw status checks
whenever valid, scalar-vs-per-cause CDC recurrence using actual fast_fault,
and same-edge independent raw-event publication/ACK vetoes. Qualified invalid
status differences are the only existing invalid-status exception; no analogous
mask may be introduced for coefficients, product metadata, leases or reasons.

Input checker comparison must distinguish source/full-identity mode from
checked-product mode. For the latter, independently prove raw75-bit offered
checks (including stalls), exact same-token GOOD/data/ordinal/TLAST/lease,
actual core handshake, completed-input count, and origin/head binding. A raw
fault may take the reviewed checking latency to mature, but its bad token must
never be delivered or published. This is not old raw-fault-cycle equivalence.

## Stimulus reuse and explicit hierarchy seams

Preserve original sample/value, phase and fault-case matrices as source text
where their interfaces remain the same:32 nominal blocks, six repeated-stall
blocks, four reset stages, delayed forward status/held final, actual READY-low,
late raw faults, provisional output-prefix quarantine,11 handoff cases,
8 registered boundaries,84 preflight rows,12 active-input fault rows, expected
cache checks and four phase-aware extra epochs. Profile1 still inserts three
100MHz ingress clocks every13words and stalls four of17 output clocks.

The following changes need an explicit reviewed binding table BEFORE execution:

- Producer `product_*` corruption, real exported `product_bank_ready` force and
  raw vendor signals retain their physical targets. They cannot be substituted
  with an unforced internal capacity or a producer-VALID mask.
- Old forced `product_bank_metadata/position/last` on RUN is now a post-checker
  transport upset, outside the frozen GOOD-link trust boundary. For enabled
  mode, bind these named corruption intents to the actual raw offered bank
  tuple before validation, at the corresponding first/interior/final token;
  assert no unsafe core accept, seal, handoff or release. Preserve the original
  forced-alias rows in the disabled/history branch; do not silently remove them
  or pretend this is arbitrary post-checker wire-corruption equivalence.
- ACK/VERIFY/ARM origin-binding faults need independently corrupted exported
  head/descriptor/lease receipts, not only an internally invalid queue slot.
  Keep actual ACK identity checks and new start binding separately witnessed.
- Existing preflight raw/private-ready differences and harmless private
  advancement on new faults remain permitted only with unchanged emitted-start,
  public-ACK/publication/reuse quarantine. Widened lease comparisons are explicit.
- Keep phase-aware extra fault drives and all old1ps current-fence checks.
  Add separate checked-bank seal/ACK/read/release cases; do not make extra
  epochs substitute for the original current faults. If a literal assertion
  cannot retain its meaning, stop and present the exact seam, not a new mask.

## Absolute result gates, fixed before any vendor launch

Numerical/ownership gates are inherited, not relative to the new actor:
all512 forward words/exponents, all512 fixed-point products, all512 inverse
words/full75-bit metadata, exact ordinal/TLAST and block start/447 progression;
no missing/duplicated/reordered accepted token or early complete publication.
No source overwrite before real consumption, no product reuse until actual
final core delivery AND check/queue drain, no fake final output ACK. Exactly one
frame/status per healthy transform, valid status reserved bits and exponent
checks unchanged, at least two actual held core-reset clocks, no spontaneous
halt/fault. Preserve25000-clock drain and1500000-clock bench watchdogs.

Retain complete candidate raw CSV, not just a filtered event CSV. The historical
main pair has589950lines /35655334bytes /SHA256
`25ab9d06ca0e03f280540cda625a7826b3c4cbaa6322ce3266c59e1fbad94122`;
extra pair33180lines /2055036bytes /SHA256
`b965d12603a64111fa9c6ea36cb0f12189945ad4d9be7cf4fbd883980c4ec4a0`.
Those remain exact baseline identities, NOT expected enabled CSV hashes.
Enabled accepted-tuple traces must match the immutable numerical vectors and
declared event-relative baseline projection, with complete row/count accounting
and explicit latency/state deltas; no dropped fault epochs or final rows.

Measure real admission/config/first-last input/output/commit, product take/seal/
publication/actualACK, inverse emitted start, last core take/drained release,
final slow output ACK and next forward admission for EVERY healthy job. The
passed P1 registered core measured config_delta3,512 inputs over513 clocks,
last-input to first-output781 and commit_delta1810. Preserve these intra-core
contracts unless actual evidence first reveals a documented interface change;
do not assert actor512-clock input span as vendor behavior. Measured P1 nominal
maximum4548 and repeated-stall maximum4828 are comparisons, not new limits.
Both declared profiles must still meet the original29.8us/5215-fast-clock
service target including real final slow ACK. Report exact extra latency;
actor+8 is a hypothesis for this run, not permission to exceed the absolute
service target or conceal a demand hole.

New positive receipts must show real source purge/rejoin, independently bound
forward origin, actual ACK and persistent receipt, all512 checked deliveries,
drain-before-release and fault-edge vetoes. Preserve old two final faults,
three held-final stalls, two one-sided resets and four healthy recoveries in
the inherited extra suite. Separate bounded paused-clock/reset epochs should
use distinct frozen numerical fixtures for old/fresh data and a compliant
held-prefix remainder; no promise of512-word capture with fast clock stopped,
continuous ADC backpressure, or arbitrary old inverse-owner paused reset.

Preparation tests must reject changed inherited observer/vector/factory,
missing/duplicate/zero/X/Z settings, actor inclusion, missing RTL, weakened
numeric/receipt checks, wrong fault binding, unsafe early GOOD/ACK/release,
lost origin/purge and complete-graph backedges. Source-pinned offline tests and
parent review precede ONE possible175MHz evaluation. Budget roughly the prior
9m49s tool run, not a timeout/restart allowance. Use new non-/tmp owner/project/
TMPDIR, exact pre/post inventories even failure, original tool exit separate
from strict terminal/CSV/receipt status, full logs/WDB/IP-after identities.
No command or owner has been prepared or launched for this proposal.

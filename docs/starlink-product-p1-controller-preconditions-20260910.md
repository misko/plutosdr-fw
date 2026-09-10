# Sealed product: actual P1 controller preconditions

Read-only source review, following the independently reviewed primitive
partition. No RTL changes, test execution, vendor tools or physical claim.
The 1444-test primitive/real-guard actor result is not a full P1-controller
proof. This note supplements, rather than rewrites, the earlier independent
P1 audit and its explicitly superseded old graph claim.

## Source scope

Read-only FW `/tmp/starlink-rom-prefetch.j829ht/fw`, tested FW
`26ac490e38e9ad74c3b7e80e096541d5edc17f2b`, report-only successor
`ce25a80b37faee37ae841cea117a34977c0f1542`, HDL
`c4befff9a74bbf3743c3ce00eec2bbedbb09fd77`. Original P1 HDL is
`c144694706b0582668606b6224462c0e8850148d`.

Within `hdl/library/starlink_pss_acquisition`, abbreviations below mean:

- **P1:** `starlink_pss_fft_bank_owned_product_fence.v`, SHA256
  `8923b42b3574fc1418eee99c5f5819f173c73fbf7b8bb65726a7ab3a5d8a6f7c`.
- **Issuer:** `starlink_pss_product_sealed_interface.v`, SHA256
  `5e060a23903641c8f0c0ec7a0afae22428d1ad15829d1af9985ca0a662de5669`.
- **Reader:** `starlink_pss_checked_product_read_interface.v`, SHA256
  `b29a700232c9ee0d62dc4cbade48e266bcf6bce4665eff670f9232584194ec3e`.
- **Result/input guard:** the unchanged `starlink_pss_realtime_result_guard.v`
  and `starlink_pss_realtime_input_guard.v` in that HDL pin.

## Admission is ownership, not the entire current certificate

Bind producer ownership on the real **forward** `job_accept` (P1 194–197),
using `engine_metadata`, not the moving source head. WAIT captures the engine
descriptor/phase; VERIFY checks it; ARM consumes the admission receipt
(487–496). Source N+1 may become visible once N's last source input is read
(390–391); that must not change N's producer/certificate identity.

Capture an independent controller `forward_origin_lease[1:0]` and valid bit on
that same accepted forward job. Do not first learn the expected lease from
the inverse head: issuer-admitted and reader-head tags otherwise derive from
the same issuer register. P1's existing consume-generation is one bit, not the
new two-bit bank lease. Preserve the independent expected 70-bit descriptor
capture at P1 477–478. Its private-final observation is **not** authorization:
issuer completion must come only from the exact final retirement at 480–481,
never private-valid, the later result-commit pulse, or bank publication.

P1 `job_accept` is not a certificate of every current preflight comparison.
`descriptor_certified` is registered, while result guard 274–275 adds fresh
preflight evidence directly to reason Q, not its idle-ready predicate. A fresh
ARM mismatch can coincide with private acceptance. This is inherited behavior,
not permission to start a bad job: epoch quarantine must suppress the later
emitted `input_job_start` (P1 112–116, 482–496). Distinguish normal-stream
D0/D1 invariants from arbitrary forced header/private-state corruption; the
latter may legitimately produce a rejected issuer capture and diagnostic Q.

## Independent head binding is needed at ACK, not only inverse admission

Old P1 242–253 independently checks metadata/position/TLAST at **forward ACK**.
Checking only the inverse VERIFY stage would allow an ACK that old P1 rejects,
even if no bad core input eventually escapes. A locally self-consistent wrong
issuer descriptor plus matching reader descriptor is a useful counterexample:
GOOD proves raw words matched that descriptor, not that it belongs to P1's job.

Before actual ACK require checked head validity, position0/last0, all 75 bits
equal `{5'b0, expected_product_metadata}`, and head lease equal the independently
forward-admitted origin with valid ownership. Keep health separate from the
state/GOOD-only ACK capacity. Repeat the independent binding through inverse
WAIT/VERIFY/ARM, including head versus captured engine metadata, and retain a
product-job-bound certificate through actual input completion. Discovery uses
`read_head_valid`, not `core_valid`, which intentionally stays low before start.

The additive input-guard seam must be inverse-only and conditional on that
bound job plus each checked token. Source jobs retain their full 70-bit guard.
Keep ordinal/TLAST/duplicate/delivery/current verdict checks. Do not feed full
input-fault or certified-input events back into the reader's validity cone.
For legal connected operation prove reader take equals actual core handshake
and input certificate on every demanded edge. Post-checker forced tuple/cursor
corruption may advance a private queue while the real guard rejects delivery;
test quarantine/no release/no result, rather than falsely claiming all forced
private pops remain cycle-identical. Toggle the legacy product generation at
actual checked final consumption, never at final RAM prefetch.

## Four different readiness/receipt roles

1. Before forward admission use `reusable` for free capacity; `product_ready`
   is zero without a producer reference. After acceptance, preserve owned
   `reservation` through ARM and receipt consumption. Driving live reservation
   directly from reusable would falsely fault the first healthy owned edge.
2. During forward returns, guard retirement, joiner acceptance, multiplier
   output acceptance and bank private take must share the correct sampled
   READY seams (P1 254–255, 308–309, 328). Idle capacity must not masquerade as
   producer READY; raw closed/unowned/X offers remain observable when stalled.
3. During forward ACK, guard mailbox capacity is issuer `handoff_capacity`.
   Actual issuer handoff equals the exact result-guard ACK-clear event:
   `awaiting_ack && mailbox_input_ready && !protocol_fault && !idle_fault_now`
   (guard 363). Independent head/current fault checks must reach that event.
4. After the one-shot ACK, P1 completion_accept (376–379) needs the persistent
   health-qualified `handoff_owned`, not the vanished pulse. Product release
   still waits for 512 actual inverse inputs and queue/checker drain.

At ACK edge h, guard busy is still high before the edge. Earliest scheduler
completion acceptance is h+1; its receipt is consumed at h+2. Retain the raw
output/status/frame/input checks at both boundaries and the epoch fence on
the later emitted start. On a fresh fault, private scheduler advancement is
not itself an escape; a public ACK, reuse or unsafe sampled start is.

The shared live-fault bus must remain a source-specific scalar partition.
Real raw vendor/output/status/frame orphans after forward closure, overflow,
duplicate start, synchronized source fault and sticky reasons remain live.
D0/D1 qualified-diagnostic Q, reader offer feedback, issuer6 bank-valid feedback,
or the aggregate result-guard fault must not be ORed back indiscriminately.
Keep full original global/result reasons and exact ACK-event checks even when
local reader predicates use an independent no-feedback partition.

## Disabled path and common epoch

Use generate-level selection or literal zero ties for all new diagnostics in
the default legacy top. Issuer ownership/transfer outputs are disabled at
option0, but its new diagnostic exports are observational: for example
`current_faults=8'hff` can assert `handoff_fault_now` while disabled. A default
top ORing that output into legacy faults is not a literal legacy passthrough.

P1 51–62 asynchronously invalidates both local reset releases, but source-bank
writer request/fault state clears on an actual slow edge. With slow clock
paused, fast_running can recover before that purge. Gating only product rearm
does not purge stale source prefetch or prevent old source_fault re-quarantine
(P1 73, 81–82). Add the separately proved *barrier pattern*, not another branch's
unreviewed source union: slow-purged Q clears on either raw reset, goes high
only after slow_running is sampled on an actual slow edge, then crosses two
fast synchronizer stages. Gate both source reader reset and source-fault
sampling until that receipt. The preceding slow edge has executed the purge.

Keep core reset held and park in WAIT before entering VERIFY until peer purge
and product epoch rearm are complete. Waiting inside VERIFY would consume its
63-cycle preparation age. Rearm must not require source_valid0: a completely
new 512-word source can legally fill while fast is paused. Product/controller
ownership uses the common epoch, never ordinary per-transform core reset.
Two-bit lease freshness remains conditional on drained references and this
explicit rearm; it does not solve arbitrary delayed-reference ABA by equality.

## Honest state, latency and remaining paths

For the proposed topology, a small controller allowance is **8 logical bits**:
origin lease2+valid1, widen existing held lease by1, bound-job1, slow purge1 and
fast purge synchronizer2. A separate guard-local mode latch adds1 if needed.
Existing engine/expected metadata, admission/completion receipts and issuer
handoff_seen are reusable; no extra 70-bit controller descriptor is necessary.
This is a design allowance, not implemented or mapped utilization.

Do not describe the replacement as merely +8 bits. The frozen new primitive
has 760 logical register bits (issuer93+reader350+bank317) and one 512×36 RAM.
The selected old P1 mailbox has 213 register bits: 140 metadata, 27 cursors,
36 read payload, six toggle/synchronizer bits and four flags/fault bits.
Thus the literal standalone replacement is **+547 register bits**, before the
controller/barrier allowance (+555 or +556 total under the plan), not an area
saving. The three queue slots include 108 payload register bits; they add no
payload BRAM or DSP. Synthesis can optimize this differently; no LUT/FF/timing
measurement is made here.

Healthy actor evidence reports final take→seal2→publication3,
publication→ACK10, ACK→first input2, final input→release1. Only the first pair
of check/publication edges is directly the bank pipeline contract. The real
P1 scheduler retains additional ACK receipts, reset, VERIFY/ARM and config;
the actor's 1555 clocks are not its service interval. Startup purge adds an
actual slow-edge receipt and two fast synchronization stages, plus rearm,
not a per-pair fixed cost. Keep original 5215 fast-clock service bound at175,
8192 guard and all original drain/stall limits. Measure actual complete pair
events; no blanket +8/+12 or shifted whole-CSV equivalence is established.

The raw offered product-metadata→framing→global-result path is structurally
targeted by the staged verdict. Surviving paths include independent held-head
metadata→ACK/preflight comparison; source/forward metadata→input guard; ROM
metadata/read-enable logic; inverse result/status/fault control; and unchanged
slow output publication/512-word drain/ACK. No inverse-output branch is joined
here. Full receiver resource/timing, continuous-source energy/scoring, native
fine and pilot concurrency remain outside this primitive/controller audit.

## Smallest distinguishing top tests before any actual-core preparation

- Same descriptor across successive physical leases; self-consistent stale
  head with independently current controller origin. Reject at ACK and again
  before inverse start. Mutate each independent comparison separately.
- Current header/head/lease changes at VERIFY, ARM acceptance, admission
  receipt consumption and actual input-start. Separate private advance from
  certified delivery; exercise missing origin/bound checks, not only reader
  slot mutations that already self-quarantine.
- Force exported producer READY low on held final and on a nonfinal return;
  count guard/join/product/bank events independently. Keep raw orphan/X offers
  visible. Restore-backedge mutants must fail from an acyclic complete graph.
- Raw faults at publication, exact ACK, h+1 completion acceptance, h+2 receipt
  consumption, actual start and final inverse input/release; retain detailed
  reasons and all unchanged numerical tuples, not merely stopped traffic.
- Disabled option with hostile new diagnostic pins must remain legacy-exact.
  Both reset sides with slow paused: naturally full old source and naturally
  sticky old source-fault are separate fixtures; then fill a fresh complete
  source before fast rejoin. No stale prefetch, re-quarantine or rearm deadlock.

These are integration proof obligations, not reported executed tests. No
runtime, simulated receiver, RF accuracy or physical promotion follows.

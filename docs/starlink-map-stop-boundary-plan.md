# Map-publication stop fence: implementation plan

Status: proposed, not implemented or hardware-qualified. This is a bounded
prerequisite for a fixed-frequency paired pilot-IQ/map/fine recorder, not a
replacement for the 300 s scanner, independent GLRT, or subsequent 30/60 MS/s
work. The first admitted implementation is the shared-XFFT 15 MS/s image.

## 1. Behavioral contract

`STOP_AT_MAP_BOUNDARY(ticket)` finishes the map tile already admitted when the
request reaches the phase-map clock, publishes its final RAM write, forbids
admission of the next tile, and then stops coarse production. It preserves
both ready banks, reads, releases, and IRQ delivery. It does not flush the
pilot, stop the fine scheduler, drain every future FFT transaction, establish
RF health, or prove host delivery.

| State at engine acceptance | Required action |
| --- | --- |
| `WAIT_BANK` | Admit no tile; preserve ready banks. |
| `WAIT_FRAME` | Admit no first score; return the untouched reservation to the clean pool. |
| `FILL` | Finish this tile with all existing continuity/error checks active. |
| `DRAIN` | Publish this tile; do not reserve or accept the next tile. |
| Registered publication outstanding | Wait for its final write and ready assertion. |

Gate both first-score admissions, including the speculative next-bank RAM
read, with `!(stop_pending || accepting_stop_now)`. Gating only the registered
pending bit is one clock too late. A score admitted before the request reaches
the engine belongs to the current tile and must finish, even if the host has
not yet observed the preceding map.

The existing final-score sequence is: accept final score and enter `DRAIN`;
queue publication/metadata on the next clock; commit the final registered RAM
write and assert ready on the following clock. A simple acknowledgment point
is one further clock, with no `update_pending`, `write_pending`, or
`publish_pending` and no unfinished `FILL`/`DRAIN`. No ready bank is cleared to
make this happen, and the other bank need not be free.

After this fence, disable coarse production without `acquisition_flush`.
The shared score engine currently resets outstanding future transactions on
disable; call this a completed-map publication fence, not a full FFT drain.
Keep the pilot-controlled conditioner enabled independently. A stop-specific
parked state must also consume/ignore already-produced, intentionally excluded
post-boundary scores without entering the ordinary discard/overrun branches.

## 2. Exact source and generation meanings

For last complete map start `S`, let `E = S + 20,000 * 64`:

- Nominal candidate-start interval: `[S, E)` in original 15 MS/s source units.
- Span: 1,280,000 candidates, or 85.333333 ms nominal exposure.
- `E` is the last accepted candidate index plus one, not the ADC index at the
  host request, engine acceptance, publication, or acknowledgment time.
- Late-emerging scores may describe much older IQ. This receipt provides no
  live-source lag or elapsed-wall-clock guarantee.

The full processing support is a separate quantity. Under the explicitly
qualified 512-point FFT / 447-candidate-stride contract, with externally
attested scheduler origin `O`:

```text
B(k) = O + 447 * floor((k - O) / 447)
exact full-block dependency envelope = [B(S), B(E - 1) + 512)
unknown-origin conservative envelope = [S - 446, E + 511)
```

Do not clamp negative bounds or infer `O` from the first map received. These
are dependency bounds, not equal-weight sample contributions. Pilot center
lattice, raw filter history, fine full-capture support, and the actual recorded
IQ interval must still be joined independently. No GLRT search is seeded by
the FPGA answer. Extend this profile to 30/60 MS/s only after qualifying their
actual coordinate and processing contracts.

`terminal_generation` is the actual last hardware publication generation at
the fence, not the request number, IRQ count, or number of maps received by the
host. Its receipt must wait for ready, not merely for the existing
pre-publication generation increment. Retain the
last complete map's metadata even if its bank has already been released.

`HAS_MAP` means a complete map exists in hardware publication history since
hardware reset; it does not claim a map was produced in this visit. A recorder
must bind the receipt to its explicit observation identity and before-start
generation baseline. With no publication history, generation/start/end are
zero and `HAS_MAP=0`; these are sentinels, not an observed interval.

Check endpoints without u64 wrap. Reject a tile crossing the u64 boundary and
conservatively fail qualification at saturated publication generation
`0xffffffff`, where uniqueness is not attestable by the existing counter.

Stopping after the host receives generation N can finish at M greater than N:
another tile may already be active. Retain and validate through actual M.
Exact stop-after-N would require a target-generation command armed before N
finishes; it is explicitly outside this first increment.

## 3. Proposed two-word PSMA ABI

Reserve a new explicitly admitted shared-15 ABI: proposed version `0x00010006`
and capability bit 9 (`capabilities=0x0000033f`). These values are a proposal
to freeze with the implementation, not an existing supported image. Keep all
existing register offsets and STATUS bits unchanged. The aperture remains
256 bytes; `0xf8` and `0xfc` are its only presently unused words.

| Offset | Write | Read |
| --- | --- | --- |
| `0xf8 STOP_TICKET` | Full-strobe u32 ticket command | Last engine-accepted ticket |
| `0xfc STOP_WORD` | Full-strobe selector 0..11; other bits zero | Selected u32 receipt word |

There is no read auto-increment. Bad command strobes/values are rejected, not
byte-merged. A bad selector leaves the previous selector unchanged and records
command error. Window reads and valid selector writes never request a stop,
release a map, clear health, or acknowledge a fault.

| Word | Meaning |
| --- | --- |
| 0 | Magic `0x50535354` (`PSST`) |
| 1 | Version/count `0x0001000c` (v1, 12 words) |
| 2 | State flags below; all other bits zero |
| 3 | Last engine-accepted ticket |
| 4 | Terminal ticket; meaningful only with `TERMINAL_VALID` |
| 5 | Terminal hardware publication generation |
| 6, 7 | Terminal map start, low/high u32 |
| 8, 9 | Terminal candidate end-exclusive, low/high u32 |
| 10 | Sticky failure-reason bits for this accepted operation |
| 11 | Last command status code |

State flags: bit 0 `PENDING` (request staged or accepted, not terminal), bit 1
`TERMINAL_VALID`, bit 2 `BOUNDARY_COMPLETE`, bit 3 `FAILED`, bit 4 `HAS_MAP`,
bit 5 live coarse acquisition enable. Reserved bits must read zero.
`BOUNDARY_COMPLETE` is structural, not a health or delivery verdict. Failure
may coexist with a completed boundary; a partial-tile abort must not set it.

Proposed failure-reason bits: 0 detector/upstream health, 1 map health, 2
bridge health, 3 explicit abort, 4 unrepresentable source bound, 5 exhausted
publication generation. Reserved bits are zero. Keep original diagnostic
counters available; this summary does not replace them. An observed late
fault may set `FAILED`/reason after boundary completion without changing the
terminal coordinate tuple. Never erase a real late fault to preserve success.

Command codes: 0 accepted/idempotent (or reset idle; read ticket/state to
distinguish), 1 malformed write/selector, 2 invalid ticket sequence, 3 busy,
4 acquisition not enabled, 5 known fatal health. Rejected commands change
neither ticket history nor the terminal coordinate tuple. Valid selector
writes do not erase command status.

### Ticket lifecycle and stable reads

- Ticket zero is invalid. A new operation requires exactly `accepted + 1`,
  with no u32 wrap. Ticket exhaustion requires a new hardware-reset epoch.
- A write returning on AXI is only a bus outcome. Acceptance is when the
  engine consumes the request and applies its same-clock admission fence;
  only then does accepted-ticket readback advance.
- Repeating the staged/accepted ticket is idempotent, including after a lost
  response. A different request while pending is busy. A completed old ticket
  never initiates another stop in a later acquisition.
- New requests require coarse acquisition enabled and no pending operation.
  Known fatal health rejects new admission; a subsequently occurring fault
  fails an already accepted operation.
- Ticket history survives ordinary CONTROL disable, flush, and re-enable.
  A new acquisition invalidates `TERMINAL_VALID` and releases the parked
  admission fence but does not reuse tickets. Retain old coordinate words as
  invalid historical data until the next terminal tuple replaces them.
- Hardware reset clears history. A vanished ticket/changed epoch is missing
  evidence, not successful cancellation. Bind host records to boot/observation
  identity externally; this ABI cannot manufacture that identity.
- Freeze the terminal coordinate tuple while valid. Driver window reads hold
  its short mutex, bracket the words with ticket/state checks, and retry a
  changed view at most three times before returning a retained error. This
  detects pending-to-terminal changes; it is not an atomic multi-attribute
  RF observation. Re-check health and lifecycle separately.

Reuse stable existing map metadata where safe; avoid a second accumulator,
RAM allocation, or wide high-fanout datapath control. Any register reuse must
still meet the validity/restart rules and stable terminal reads above.

## 4. Fault priority and timeout behavior

Retain the exact legacy CONTROL semantics: bit 0 enables, bit 1 pulses flush;
0 immediately disables and 2 disables plus flush. Existing 1/3 combinations
retain their meanings. Do not implement the new command as another CONTROL
bit whose write could accidentally clear enable.

While `FILL` is completing, all existing index, phase, discontinuity, and
arithmetic checks remain active. Genuine detector/ingress/map/bridge faults
win over simultaneous graceful completion. If an abort is necessary, execute
the existing partial-FILL invalidation exactly once, including the real
`discontinuity_abort_count` increment; do not jump to a parked state first and
bypass its accounting. Complete maps already published remain intact.

CONTROL 0/2 while a request is pending marks explicit-abort failure and follows
the legacy disable/flush path. No stopped reader/buffer is resurrected. A
normal fence intentionally avoids only the next-tile admission, discard, and
overrun branches; it never forgives preexisting nonzero counters. Preserve the
shared-service fatal health mask `0x57ff`; denominator-zero remains diagnostic.

The source can stop providing scores mid-tile. A first implementation needs
no fabricated FPGA timeout-success state: poll with a bounded host deadline
(proposed default 1 s, maximum 5 s). Native IIO operations also need finite
timeouts; an overall poll budget does not itself interrupt an outstanding
network call or guarantee teardown by that exact wall-clock instant. The
nominal 85.33 ms tile span is not a hard completion deadline. Timeout retains
the accepted ticket, pending state, partial data, and raw errors. A subsequent
explicit abort is a distinct operation/outcome. Test true fault pulses on the
acknowledgment edge and fresh post-stop health to catch delayed diagnostics.

## 5. Linux and host milestones

Add a typed u32 `acquisition_stop_request` write attribute and read-only
`acquisition_stop` receipt attribute. Proposed wire line: `PSST 1 12` followed
by exactly the 12 eight-digit lowercase hex window words and newline. Keep
`PSMH 1 46` acquisition-health layout unchanged and retain both raw lines.

The request path takes the existing IRQ mutex briefly, checks capability,
streaming/enable/fault state, submits the ticket, and verifies engine acceptance
with a short bounded MMIO poll. It does not wait for a tile under that mutex.
Status reads take independent short locks; waiting callers release it between
polls so the IRQ thread can copy and release both banks. Initial short-command
poll budget may reuse the existing 10 ms bounded MMIO convention; a missing
acceptance is an error, never implicit success.

Successful producer stop updates the acquisition-enabled cache from hardware
but leaves `streaming` and `irq_live` true. Do not use `map_stop_on_fault()` for
success: it disables IRQ. Leave actual fault handling fail-closed and retain
raw/error evidence; healthy draining is not promised following a true fault.

These are separate milestones, in order:

1. Requested write and observed engine acceptance.
2. Matching structural terminal ticket, valid bounds, no stop failure.
3. IRQ copy/push/release through terminal generation, with fresh healthy
   acquisition receipt. An empty ready mask alone does not prove delivery.
4. Host retains every expected raw map chunk/generation through that boundary,
   plus pilot/fine data and all negative/error receipts; durable data is not
   proved by the kernel's aggregate delivery counter.
5. Bounded readers finish/join; only then close buffers and context. Cancel an
   actually outstanding failed read only under the existing honest cleanup
   contract. Do not disable the map buffer before steps 2–4.

The receipt read must expose rather than hide missing/changing state. Window,
health, driver lifecycle, and host persistence are separate observations; no
combined helper may label them a single atomic RF snapshot.

## 6. Implementation slices and qualification gates

| Slice | Changes | Required executable evidence |
| --- | --- | --- |
| A: map core | Admission fence, terminal/abort states, final-publication ack | Small RTL exhausts all score positions/states, request with next phase-0 on DRAIN, final-write edges, both banks ready, read/release concurrent, no-input pending; compare exact map contents and bounds. |
| B: wrapper/control | Thread stop signals through IQ-to-map/top; synchronous PSMA window/tickets; disable coarse only after fence | AXI tests cover full/partial writes, selector bounds, ticket replay/busy/exhaustion, reset/restart, changing receipt, retained IRQ/ready, unchanged CONTROL 0/1/2/3. |
| C: driver | Explicit ABI/capability admission, typed request/read receipt, short mutex phases | Compile actual C in MMIO harness; interleave request/polls with IRQ draining, both 200-chunk maps, late fault and copy/push/release errors, timeout, lost response/idempotent query, strict reserved/ABI checks. |
| D: full datapath | Existing shared-XFFT and independent pilot path; no new scanner orchestration | Real bursty score latency, mid-transform stop, continuously running pilot, identical complete maps, no false tail/reset health faults, exact source-support joins; retain negatives and failures. |
| E: implementation | Synthesis/place/route of this feature-enabled image | Actual resource delta and timing closure, not estimates or synthesis-only evidence. |
| F: reusable PPU then fixed-frequency deployment | Explicit strict receipt/profile support and bounded stop/drain integration | Fake-IIO lifecycle/error tests, malformed receipts, late health failure, incomplete host map history, no unsafe close; later authorized radio test with paired raw IQ/maps/fine and independent GLRT. |

Across A–D, retain legacy regression assertions: disable during partial FILL
still increments real abort, disable at DRAIN still publishes, normal
overrun/read/release/protocol faults still count, and successful graceful stop
does not create any such faults. Include u64 endpoint and saturated generation
cases. A failed physical gate blocks deployment, not completion of remaining
software or science milestones.

## 7. Concrete files and compatible rollout

Primary RTL:

- `hdl/library/starlink_pss_acquisition/starlink_pss_phase_map.v`: first-score
  predicates and FILL/DRAIN/registered-publication edges.
- `hdl/library/starlink_pss_acquisition/starlink_pss_iq_to_phase_map.v`: map
  enable/fault interaction and stop-port threading.
- `hdl/library/axi_starlink_pss_acquisition/axi_starlink_pss_acquisition.v`:
  synchronous control wiring and independent conditioner/pilot enable.
- `hdl/library/axi_starlink_pss_acquisition/axi_starlink_pss_phase_map_sync.v`:
  new explicit capability/version, two-word window, ticket and terminal state.
- `linux/drivers/iio/adc/adi_starlink_pss_map.c`: capability admission, shared
  fatal mask, short request/read transactions, IRQ/cache lifecycle.

Extend `tb_starlink_pss_phase_map.sv`, synchronous AXI rate/health testbenches,
and `tests/starlink_oracle` actual-driver contract/health MMIO harnesses; add a
dedicated stop testbench/harness where clearer. Update affected stubs and
legacy instantiations with explicit disabled stop inputs. The separate
asynchronous `axi_starlink_pss_phase_map` wrapper must not advertise this
capability without its own qualified CDC handshake.

Keep legacy images' ABI/capabilities and behavior unchanged. Do not silently
label the new feature ABI 1.5 or admit unknown versions. Update Linux and PPU
strict health/map/profile readers explicitly for proposed 1.6, preserving the
shared-service fatal bit and the proven 15 MS/s geometry. Old hosts must reject
the new image clearly until updated. New PPU code remains reusable/mergeable
on PPU main; experimental firmware remains on its separate do-not-merge-main
branch. No flashing is authorized by this document.

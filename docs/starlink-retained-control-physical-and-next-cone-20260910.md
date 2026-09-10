# Retained control candidate: diagnostic physical result

**Timing still fails.** Parent synthesis 56000 and route 96174 exited 0, but
that is tool completion, not timing, CDC or deployment qualification. No runtime
or constraint changes follow from this report.

Frozen preparation/source: FW `e0f87f3239ba6bbd543421cff389d2887edf0f86`, HDL
`569e62f80f46a73f33e91c245395c4b811f329bf`; four runtime candidates remain exact
HDL `468cb764` bytes. Both candidate options are 1. The actual seven-context
qualification, factory, clocks, directives and all previous fences are unchanged.

Recovery root: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.

| Measurement | Synthesis 56000 | Route 96174 |
|---|---:|---:|
| Parent directory | `retained-control-synth-parent.9xhaMMns` | `retained-control-route-parent.rza0KS8U` |
| Tool wall time | 187.758 s | 62.760 s |
| LUT / FF | 2242 / 4759 | 2333 / 4764 |
| DSP48 / RAMB18 | 21 / 15 | 21 / 15 |
| Black boxes | 0 | 0 |
| Setup WNS / TNS | unplaced observation only | -2.697 / -981.622 ns |
| Setup failing endpoints | not a routed result | 848 |
| Hold worst / failing endpoints | not a routed result | +0.037 ns / 0 |
| Routed nets / routing errors | not routed | 7233 / 0 |

Synthesis adds 3 LUT and 1 FF relative to the preceding retained synthesis.
All 110 prepared files and both source copies match; the mapped hierarchy still
has one FFT and three payload banks. Five critical CDC findings remain; no
waiver or hardware-clock qualification is implied. The parent's first route
resource-audit attempt failed on whitespace parsing; its original script and
failure text are preserved alongside the corrected successful audit.

Synthesized DCP SHA:
`193cf14408ca768d403f1ef4bba913c07bf24a94bb88fb647941b95a03dd1482`.
Routed DCP SHA:
`2ec838aa9a0a6f5ee297e506a07a842a1aa597f0e08241dc5bbf93b9493c1f3f`.
The unchanged route runner is `034d1eaa197757b762644acd0cad9dc267338ae23fd5d757290c8485d0f1ac9a`.

## Exact remaining cones

`route/island_175_island_175_max.rpt` SHA:
`31d824f0f861803dbd3d9eebdfa797472b0848ea06f618623c17fe5dd059abcb`.
The worst path is entirely in `island_175`: product-bank held **read** metadata
bit 8 to retained-owner reason bit 6. It has 10 LUT levels and 8.085 ns data delay
(1.690 logic + 6.395 routing). It is not an asynchronous-clock rounding artifact.
WNS improved 1.371 ns versus the previous retained route's -4.068 ns, but remains
worse than the separate older P1 -1.492 ns result. These are distinct candidates,
not a union or proof of comparable end-to-end capacity.

Fifteen of the top 20 paths start at read metadata. Destinations include retained
publication/reservation/lease/request/transfer state, both guards' private active
state, cutover owner/configuration/quiet/fresh-frame state and scheduler completion
receipt. The second path, to retained publication, is -2.660 ns. Therefore merely
registering reason bit 6 would not remove the remaining authority paths.

The other five paths start at product-bank held **write** metadata bit 14. One
ends at forward-committed state (-2.594 ns); four reach kernel-ROM block-start
register enables (-2.422 to -2.403 ns). They originate in product write framing,
not the read-side comparator. The checked-product branch addresses a separate
write/read validation boundary; it has not been combined with this scheduler.

Source mapping, under `hdl/library/starlink_pss_acquisition/`:

* `retained_output/baseline/starlink_pss_realtime_input_guard_local_admission.v:79`
  builds per-word metadata validity; lines 89–100 build current errors and then
  certified beat/end using `!fault_now`.
* `retained_output_closed_candidate/starlink_pss_core_job_cutover.v:25` and 36–38
  use those certified controls for known-state/early-result current faults.
* `retained_output_closed_candidate/starlink_pss_fft_retained_output_impl.v:242`
  combines input, cutover, retained, bank, raw and registered faults into external
  fault. Lines 288–289 re-combine this with both guards' current faults; guard
  lines 166–168 themselves already include external fault.
* Top lines 330–350 send common fault to retained ownership, and send qualified
  admission/configuration/completion events back into the cutover state machine.
  Top lines 421–424 qualify completion on full current health and quiet raw ports.
* `retained_output/starlink_pss_retained_output_owner.v:37` keeps current fault on
  real-reader release; lines 58–74 use it on admission/publication and sticky
  reason capture. Its own `fault_now` at line 30 deliberately excludes common
  fault. This is a long acyclic current path plus registered sticky feedback,
  not a newly demonstrated combinational cycle.

Mapped LUT names under `epoch_barrier/fault_reasons` are optimizer labels, not
evidence that the source epoch-barrier module implements such a reason register.

## Next boundary: proposal only

First separate module-local current causes from inherited global summaries.
For a guard whose current fault is `E OR local`, the repeated top-level
`E OR G0(E) OR G1(E)` can be expressed as one `E OR local0 OR local1`, while
leaving the original diagnostic outputs/recurrences literal. This OR factoring
is exact but may synthesize identically; it is **not a claimed timing cut**.

The substantive serial dependency remains input error → certified event →
cutover/guard error → shared error. A minimal candidate to investigate later is
a **fault-summary-only offered-beat/end view**, separate from delivered-beat
certification. The original direct input current fault must remain an immediate
veto. Only if that fault is proven clear could a summary use a metadata-independent
offer, with the original certified-event counters, full diagnostics, payload
checks, publication, real ACK and reset authority left intact. No offer may
become a physical FFT delivery or a publication certificate.

This needs an exact reachable-known premise or a separately reviewed fail-closed
rule. Bare Boolean absorption is insufficient: `I || (!I && L)` is X at I=X,
L=1, whereas `I || L` is 1. Case-known checks can likewise change unknown-control
classification. No equivalence or public-output waiver is asserted here.

Before implementation, require old/new four-state summary comparisons, real
pre/post-final input boundaries, simultaneous malformed input with raw output/
status, duplicate start, current bank faults, real old-inverse ACK during next-F
input, held-final publication and both raw reset sides. Missing local causes,
unqualified offered events and one-cycle delayed global faults must be negative
controls. A bad metadata word coincident with a real ACK must still veto release
on that edge; registering the common fault alone fails that requirement.

Even a successful read-summary separation leaves the five write-framing/ROM
paths. The next prioritized comparison is the independently actual-qualified
checked-product candidate's physical result. No further retained-runtime
implementation, branch union, clock relaxation or vendor run is authorized here.

## Portable measured evidence

`artifacts/retained-control-physical-v1.tar.gz`, SHA
`167ba4bc8a6d81e2ed794135ea417e4e514625af4ae376c3b0d2514501e0ec95`:
6,277,719 bytes; 205 safe regular members / 204 hash-and-length receipts.
It includes both DCPs, every final report/constraint/owner receipt, the preserved
initial audit failure, exact preparation and generated FFT wrapper. Full raw
inventories cover synthesis 227 files / 33,916,027 bytes; route 41 / 5,905,623;
preparation 111 / 952,826. Generated project payloads remain intact in place.
All raw before/after inventories match. Packaging invokes no vendor tools.

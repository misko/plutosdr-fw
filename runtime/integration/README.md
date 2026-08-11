# Stage 5 integration patches

Two repositories outside this worktree have to change for the FPGA gain events
to reach a calibration. Both changes are captured as patches rather than edits
because neither tree is checked out here: the gadget lives in a source tag, and
`spf` is a separate repository.

| Patch | Applies to | What it changes |
| --- | --- | --- |
| `gadget_events_valid.patch` | `gain-series-v4-rc14-source/gadget` | producer-armed validity flag, exact in-buffer change bits, a rejection for self-inconsistent frames, and the regression test |
| `spf_host_tandem_events.patch` | `misko/spf` @ main | decodes the two formerly-reserved words, adds `tandem_gain_series.py`, adds its test |
| `spf_zarr_gain_events.patch` | `misko/spf` @ main | stores the decoded fields, bumps the gain-series schema to 2, fixes an exact-version reader check |
| `gadget_event_producer.patch` | `gain-series-v4-rc17-source/ip-gadget-final-v2` | drains the block's FIFO per frame and passes the events to the builder |

Both were dry-run applied against pristine checkouts. The gadget patch was
built and run against RC14's own `test_spf_radio_frame_v3.c`, which passes
before and after, including its golden CRC — the patch changes flags, never
bytes, for any frame an existing producer builds.

## The defect the gadget patch fixes

`SPF_META_FPGA_EVENTS_VALID` was set from `gain_event_count != 0`. That makes
two physically different frames identical on the wire:

| | events | old flag | new flag |
| --- | --- | --- | --- |
| no producer armed | 0 | clear | clear |
| armed, gain genuinely held | 0 | clear | **set** |
| armed, gain moved | n | set | set |

The middle row is the whole point. A frame in which the gain never moved is a
*complete* answer — it says the IQ needs no gain correction at all — but under
the old rule a consumer could not tell it from "no producer ran here" and had
to discard it. Since a quiet frame is the common case once the loop settles,
the flag was unusable exactly when it mattered.

Validity is now carried explicitly as `gain_events_valid` in the build args.
Every existing caller omits it, gets `false`, and behaves precisely as before,
so the change is invisible until a producer opts in.

## Deployment ordering — firmware must not lead the host

`GainEventV3.unpack()` **raises `ProtocolError` if either reserved word is
non-zero.** Verified against `spf` at HEAD:

    ProtocolError: gain event reserved fields must be zero

So firmware that populates those words will have every frame rejected by any
host that predates `spf_host_tandem_events.patch`. Two things keep that from
becoming a field failure, and both must hold:

1. **Host first.** `spf_host_tandem_events.patch` ships before any firmware
   that drains events. It is backward compatible — a zeroed record still
   decodes — so it is safe to deploy ahead of the firmware.
2. **Capacity is the gate.** The drain writes at most the frame's negotiated
   `gain_event_capacity`, which the host chooses. A host that never requests
   event capacity never receives a populated record, whatever the firmware
   supports.

This is the same ordering hazard as the tag-protection item in the plan's
cross-cutting list: a producer that leads its consumer is not a compatible
change, however additive it looks.

## The Zarr round-trip loses the decode without the third patch

The v7 store already had `gain_event_sample_sequence` and `gain_event_flags`,
which between them say only *"the gain moved, here"*. The index it moved to,
why, and the sequence number that makes a dropped event detectable all live in
what protocol v3 calls the reserved words — so a store written without the
third patch preserves the events and discards the only part of them a
calibration can use. Schema 2 adds `gain_event_index`, `gain_event_detail`
(reason and direction, packed as on the wire) and `gain_event_sequence`.

The bump exposed a reader bug worth fixing on its own account.
`recover_interrupted_v7.py` gated on

    source.attrs.get("gain_series_schema_version") == 1

An exact-equality check on a version number means every future schema reads as
*absent*: a schema-2 store would have been recovered as though it had no gain
series at all, silently and with no error. Changed to `>= 1`.

## Test status, stated plainly

| Patch | Built | Tested |
| --- | --- | --- |
| `gadget_events_valid.patch` | yes | RC14's own suite, before and after |
| `spf_host_tandem_events.patch` | yes | round-trip + 200-case cross-check vs C |
| `spf_zarr_gain_events.patch` | no | needs numpy/zarr, absent on this host |
| `gadget_event_producer.patch` | **no** | see below |

The producer patch is **not compile-tested here.** `thread_read_v3.c` includes
`<spf/...>` headers that are installed by the Buildroot package, and that
sysroot is not present on this machine. What *is* tested is everything the
patch calls: `spf_tandem_fifo_drain`, `spf_tandem_drain_frame` and
`spf_tandem_reconstruct` are exercised end-to-end, from four register windows
through to a per-sample series, in `test_spf_tandem_fifo.c`. The patch itself
is 40 lines of wiring between tested pieces, but it is wiring that has not been
through a compiler, and it should be treated that way at integration.

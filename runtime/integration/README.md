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

## What is NOT in these patches

The gadget's `thread_read_v3.c` call site — passing `gain_events`,
`gain_event_count`, `gain_event_overflow_count` and `gain_events_valid` from
`spf_tandem_drain_frame()` — is not patched here, because it needs the FPGA
FIFO reader, which needs the AXI block, which is Stage 3's blocked timing
closure. The drain and its result struct are shaped to drop straight into that
call site when it unblocks: every field the builder wants is already a field of
`spf_tandem_drain_result_t`.

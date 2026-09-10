# Retained native source binding, version 1

`python3 -m tools.starlink_glrt_native_binding` consumes explicitly named
`--journal`, `--recording`, `--owner`, `--protocol`, `--summary`,
`--final-snapshot`, `--iq` files and an `--episode-index` (0 or 1). It writes a
new `--output` file with schema `starlink-glrt-native-source-binding/v1`.
The command performs no RF collection, discovery, recovery or firmware write.

This producer-side adapter reads the retained commissioning owner's episode
receipt and emits a narrow public port. Application consumers do not need
to parse commissioning implementation details or import firmware tools.
Its input owner format is the acquired-controller multi-episode receipt;
older single-episode commissioning formats are not implicitly inferred.

The adapter requires unchanged radio identity, boot, firmware FIT and idle/TX
state across the retained owner run; completed and exported coarse capture;
exact source-file/IQ hashes and byte counts; healthy stopped GLF1 coordinates;
the owner's exact bootstrap seed; runtime and native inventory agreement;
and every retained native pilot inside the coarse source interval. The
recording export is regenerated from the raw journal and compared in full.
When the owner episode contains `journal_sha256`, that sealed digest must also
match. Older receipts without this field remain explicitly retrospective.
CLI hashing rejects an IQ file whose size or modification metadata changes
while it is read. Existing output files are not overwritten.

The binding includes export, journal, owner, coarse protocol, summary, final
snapshot and IQ SHA-256 values; radio serial, Ethernet host, boot ID, firmware
and FIT identity; source visit, native epoch and owner episode index; the
60 MHz/2.5 MHz geometry, native signal origin and last coarse-output center;
and original runtime result, owner status, head and supported counts.
Native endpoints are decimal strings to preserve u64 precision in browser JSON.
The integer mapping is `native_origin + 24 * output_sample`; the group delay
is 1,272 native samples and is already included in the stated signal origin.

`source_correspondence_verified: true` means correspondence within the supplied
retained owner evidence. The explicit evidence mode is
`retrospective_retained_owner_correspondence`. This is not a radio-signed
attestation or proof that those files could not have been replaced before
review. Consumers must pin the binding file's own digest at their handoff.
It is not original native IQ or proof of numerical/physical accuracy.
`radio_signed_attestation`, `acquisition_verified`,
`original_native_iq_verified` and `physical_precision_qualified` remain false.

A cleanly retained failed runtime can produce source-associated evidence:
its negative runtime result and original owner status remain unchanged.
Binding must not promote that run to success or authorize automatic restart.
Source association does not supply UTC or resolve physical frame ambiguity.
Version 1 fields and semantics are fixed; incompatible changes require a new
schema version.

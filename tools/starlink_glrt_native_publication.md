# Publishing a retained native episode

`python3 -m tools.starlink_glrt_native_publication` accepts explicit
`--journal`, `--owner`, `--protocol`, `--summary`, `--final-snapshot`, `--iq`,
`--episode-index` and `--output` arguments. The output's parent must already
exist. No existing output directory, including an incomplete publication,
is overwritten or automatically resumed.

The producer validates the complete raw journal, regenerates its recording
export, rehashes stable coarse IQ and validates the owner/source correspondence
before creating output. It retains these exact named payloads:

- `journal.glrj`: original journal bytes.
- `recording.json`: the version 1 native recording port.
- `source-binding.json`: the version 1 retained-owner source binding.
- `owner-receipt.json`: original owner receipt bytes.
- `coarse-protocol.json`: original coarse protocol bytes.
- `coarse-summary.json`: original stopped coarse summary bytes.
- `coarse-final-snapshot.txt`: original final GLF1 snapshot bytes.

Each payload is written exclusively and fsynced. The directory is synced,
then the final manifest is fsynced under a temporary name and linked into
`manifest.json` without replacement. The directory is synced again. A payload
failure leaves no complete manifest. Consumers must require and validate the
manifest and all declared artifact hashes; an output directory alone is not
proof of publication. A storage failure is not an instruction to resume RF.

Published directories have mode 0755 and their payloads and manifest have mode
0644, set explicitly before final publication even under a private producer
umask. These selected evidence files are intended for the read-only application
account. Original commissioning files and existing ancestor permissions are not
changed; the caller must select a traversable publication parent.

The manifest schema is `starlink-glrt-native-recording-bundle/v1`. It contains
`publication_status: complete`, radio serial, boot ID, FIT hash, source visit,
native epoch, owner episode index, original runtime result and owner status,
head/supported counts and the retrospective evidence mode. Its `artifacts`
mapping contains exactly the seven names above, each with SHA-256 and byte
count. Coarse IQ is referenced by its SHA-256 and byte count with
`embedded: false`; it remains in the original recording rather than being
duplicated into each episode. The CLI returns the manifest's own digest for
the application handoff.

Publication completion means all declared files were retained. It does not
promote a failed runtime or qualify acquisition, original native IQ or
physical precision. Those qualification fields remain false. This port and
its nested recording/source-binding ports have immutable version 1 semantics.

The prepared v16 commissioning operator invokes publication after stopping
RF, exporting retained files, reconciling radio state and saving the owner
receipt. It writes a separate `recording-publication.json` with each episode's
manifest/digest or publication error. A missing bootstrap is reported as no
native result; a seeded episode whose evidence is incomplete fails publication.
Publication never rewrites the original owner outcome. Overall operator
success additionally requires complete publication. This post-stop hook has
unit coverage but has not yet run on recovered hardware.

The prepared operator then invokes `leo.cli.native_recording_register` through
the host application's own Python environment for each complete publication.
It retains a separate `recording-registration.json`, verifies the returned
recording ID, bounds each invocation to 30 seconds, and continues to the next
publication after an individual failure. Missing or failed publications do not
launch registration. Owner/runtime outcomes remain unchanged, and operator
success additionally requires complete registration. This is a public CLI
handoff, with no application-module imports into the radio runtime. Registered
files alone do not attest production UI deployment.

# Native journal recording port, version 1

`python3 -m tools.starlink_glrt_native_recording --journal JOURNAL --epoch EPOCH
--output OUTPUT.json` exports one closed GLRJ1 journal without radio access.
The output uses schema `starlink-glrt-native-journal-recording/v1`. Existing
outputs are not overwritten. An invalid, partial, misassociated or uncleared
journal produces no output. Publication occurs only after the complete file
has been written and fsynced; the destination directory is then fsynced.

This is a recording interchange port, not a hardware commissioning receipt.
Consumers do not need to import the FPGA/firmware repository. The recording
owner must bind `journal_sha256` to a verified radio, boot, source epoch and
coarse capture. An epoch alone is not a globally unique radio identifier.
This port does not establish acquisition provenance, rerun the numerical
solver, retain original native IQ, or qualify physical timing/CFO accuracy.
The explicit qualification fields remain false. Separate evidence is needed
for each such claim; changing a field in this artifact is not that evidence.

`measurements` preserves every associated head and estimate in execution order,
including rejected estimates and faulted arithmetic. `supported` means only
that the retained estimate has rejection mask zero and the associated head
has complete fault-free arithmetic. It does not mean the episode completed
successfully or that there was a detected satellite. Consult the owning
runtime's termination evidence separately. No unsupported CFO value should be
used as a tracking update.

Each measurement carries journal-local epoch, result sequence, global frame,
batch tag and repeat ordinal; native start, phase seed/step, sample count and
hardware fault; all seven integer moments; and the retained delay, residual
CFO, total CFO, coherence, linearized coherence and rejection mask. The
`drained` counters retain actual configured/admitted/late/unavailable/expired/
cancelled/dropped work; `final` records the verified clearance. Retained
descriptors are intent, and may include a write that was never admitted.
They must not replace the execution accounting in heads and drained counters.

Native sample indexes and integer moments use decimal **strings** so browser
JSON does not round their 64-/69-bit values. Consumers must subtract integer
sample anchors before converting small differences to floating point. The
smaller Q16/Q32/Q48 fields and u32 counters are exact JSON integers.

The source rate is 60,000,000 samples/s, with a 79,200-sample pilot. The timing
estimate is the scheduled integer start plus `delay_s * source_rate_hz`, on
the native pilot-template axis. This is not a calibrated physical frame epoch
or UTC time. The pilot center lies 79,199/2 samples after the scheduled start;
the doubled offset is retained as an integer. CFO is receiver-relative and
uncalibrated. This port performs no rate fit or cross-epoch concatenation.

Version 1 is additive to GLRJ1/GLS1 and changes neither wire format. Its fields
and meanings are fixed; incompatible changes require another schema version.

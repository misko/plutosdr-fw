# Retained control candidate: frozen actual-harness recipe

This is preparation only. The parent owns any separately authorized vendor run.
The machine contract is `tests/starlink_oracle/retained_control_actual_recipe.json`.
It is frozen before running the new scripted harness.

Reuse the qualified v5 seven contexts, factory, original vectors, exact physical
input and output lane/padding checks, causal frame records (including both aborted
forward jobs), complete CSV clock/event joins, and all original service bounds.
Only the four already tested candidate runtime source paths are substituted;
their bytes must not change. Both candidate options are explicitly one and read
back at wrapper and implementation boundaries. No clock or arithmetic changes.

All three original guard references receive an independently wired literal copy
of the **original full completed-input fault predicate**. The existing full
136-bit forward shadow and both unconditional original guard state shadows stay
intact, including invalid output metadata. A mismatch is a preserved failure,
not grounds for a blanket shadow mask.

The new read-only witnesses check every accepted descriptor on its actual edge,
held descriptors while active/parked and through real ACK, and the closed-input
premise both before the sampled edge and after settling. The final input edge
still has complete=0 and cannot use a public completed-return path. All three
public paths must have known-one completion and a clear original full predicate.
The full unrestricted diagnostic/ACK behavior remains independently observed by
the old shadows; no reduced-predicate replacement enters those gates.

Frozen counts follow the unchanged orchestration: 21 forward and 19 inverse
admissions; 38 complete final inputs plus two aborted forward prefixes; 19 real
forward ACKs and 17 real inverse ACKs (the other two completed inverse banks are
discarded by the existing reset scenarios). New receipts use `RCAND_`, separate
from the unchanged old parser: one flags, 40 joined admissions, two owner totals,
one proof total. The original verifier consumes the complete, unfiltered log and
CSV first. New receipts cannot replace missing original evidence.

This is a known available-source scheduling campaign, not continuous 15 MS/s or
native 60 MS/s acquisition, lower-clock closure, causal timing, RF or physical
qualification. The existing routed candidate is still timing-failing; no new
physical result is implied by this preparation.

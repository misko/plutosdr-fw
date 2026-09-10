# Paired60 expired-command contract, frozen before evaluation

This additive test schedules one deliberately expired native request while the
already qualified common-source canonical15 bank175 coarse path and independent
2.5 MS/s PIL1 path continue. It must report expected rejection, never healthy
native service or an RF miss. No runtime, healthy60 bench/helper/verifier, original
69 numerical files, source samples, clocks or arithmetic may change.

The machine contract is `tests/starlink_oracle/high_rate60_late_recipe.py`.
The healthy source is FW `7c62a3382baef4b922cec92c1e71c0fa67061970`, HDL
`88195cd9029a0c66f642fe21045ff70053fc46de`; the externally pinned healthy bundle is
`b5f7d48a96217691d7a034634d3bdc7006e489066e571d93b00ce2ed5f741714`.

## Command and source coordinates

The unchanged center is 34359740384 and the 520-sample capture would start at
34359740256, using 264 native taps. The new command trigger is start + 32 =
34359740288. Require the actual sample-domain handshake in the closed window
[34359740288, 34359740448], on an enabled consecutive original-source sample.
The scheduler uses next index = handshake index + 1, so its signed lead must be
34359740256 − (handshake index + 1), or −193 through −33. Its late predicate must
be set, with duplicate/overlap and last-admitted-valid clear. The request remains
0x60000520 and coefficient generation 0x60000001. Pilot visit 0x60000052 is fixture
context, not a native packet field. No native packet exists in this case.

The existing30 late contract budgets eight public transactions (two current-index
reads, five descriptor writes, one submit), each at most 24 control cycles, plus
8 entry cycles and 32 wrapper/FIFO CDC cycles: 8 × 24 + 8 + 32 = 232 ≤ 256.
At true60 source / 100 MHz control, 256 control cycles cover 153.6 raw periods;
the independently frozen 160-slot window is conservative. These are simultaneous
gates, not alternatives: verify trigger, actual handshake coordinate, elapsed
control cycles, request identity and uninterrupted source cadence. Reuse the
unchanged current-index low-capture witness and public high/low coherence gates,
including capture lag ≤ 2, return lag ≤ 31 and pair duration ≤ 48 control cycles.

Keep two disabled CDC prime beats separate from the original 16,423 raw samples
[34359735211, 34359751634), with no tail. The original 3111-sample preroll and
startup drain/pause remain; all 13,312 post-preroll samples must be uninterrupted
at the original true60 edge/phase relation. Source valid stops only after those
samples; source/control/FFT clocks continue for telemetry and final observation.

## Rejection, empty-native and independent healthy paths

Require exactly one public submit, wrapper handshake, FIFO acceptance and sample
handshake. At the accepting sample edge, observe rejected = late = 1, admission
and all other capture-event counters zero. This local observation is distinct
from subsequent public telemetry visibility through clock-domain crossings.

Before explicit coefficient-ready, whitelist only the actual coefficient-energy,
flush, check, copy and copy-finish states, with source disabled and strobe zero.
After ready, require the actual native correlation engine idle and busy zero on
every checked edge, with exact 264-tap generation/energy. No broad busy exception.
Reject any unknown protocol/state flag. All pending/capture/raw/qualified/reducer,
result, packet access/release and IRQ activity is forbidden through the entire
source, retained map lifetime, both audits, map release and final quiet interval.

Use the existing15 expired regression's 31-register public counter/status audit,
with this60 identity and energy, twice: generations 1 and 2, exactly 62 register
reads, never result register 0x54. Both audits show rejected = late = 1, all other
job/capture/result counters zero and empty result status. The first follows the
physical rejection; the second follows complete source-off and coarse STOP while
the complete map remains retained. Bound each telemetry generation at 512 control
cycles; 31 counter reads, status, generation recheck and IRQ/status are 34 more
transactions. Thus 512 + 34 × 24 = 1328 cycles per audit. Allow 8 settle and 32
entry cycles and require final late observation ≤ 2048 cycles after source-off.
Finish with the unchanged 256-control-cycle no-stale interval after public map
release and all final reads. Retain the global 160,000-cycle watchdog.

The map still has exactly 894 admitted scores and 447 independently checked words;
all visible FFT stage words/scores and both enabled-prefix DDC ledgers remain
exact. PIL1 still delivers all 512 original CI16 words and exact support/snapshot.
This trigger precedes the first FFT transfer, so do not require FFT work at the
instant of rejection. Require actual FFT-domain forward transfers and pilot
acceptance after physical rejection while the native path remains empty. There
is no native capture/compute overlap or native result-release witness to invent.

## Preparation and limits

Derive minimal context adapters with an exact full-source inverse back to pinned
healthy files. Preserve numerical helpers rather than fork their arithmetic.
Freeze imported source closure, compile-only inputs, parser-only synthetic
receipts and mutation tests separately from actual evidence. Test wrong identity,
stale/coherent index readback, missing/duplicate/non-late rejection, early capture,
nonempty counters, source/oracle/clock/state mutations and changed source hashes.

One future vendor simulation is planned, but not authorized by this preparation.
This is reduced-map digital scheduling/ownership evidence under ideal clocks and
a static known center, not causal acquisition, RF accuracy, full-map/750 Hz
capacity, IIO delivery, host ABI support or physical60 qualification.
